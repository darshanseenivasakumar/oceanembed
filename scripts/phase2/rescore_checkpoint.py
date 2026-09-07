"""Re-score a SAVED TS-Cast-NIO checkpoint against independent Argo, check the number it produces
against the number recorded beside it, and write the re-score as its own artifact.

    python scripts/phase2/rescore_checkpoint.py --tag sat_7ch_s42 --daily-dir data/processed/daily_sat/v001
    python scripts/phase2/rescore_checkpoint.py --tag embargo_withUV_s42
    python scripts/phase2/rescore_checkpoint.py --tag sat_7ch_s42 --daily-dir ... --unmasked   # reproduce a pre-2026-09-07 number

WHY THIS EXISTS
---------------
`docs/EXPERIMENT_LOG.md` records the v2 headline as 0.8612 degC (7ch) against 0.8760 (5ch), from
commit 6e6ba9a. The checkpoints now on disk were retrained AFTER the leakage embargo landed
(a5cdd3a) and their own metrics files report 0.8793 and 0.8682 -- which reverses the sign of the
wind result. Before that correction is written into an append-only scientific record, the numbers
have to be reproduced independently of the training run that first printed them.

So this script does NOT retrain. It reloads the checkpoint from disk, rebuilds the same test
split, embargo, normalization, climatology and Argo collocation, and re-runs the scoring. It
reuses the trainer's OWN modules (dataset, metrics, validate_argo, eval_argo) rather than
reimplementing them: a second implementation that disagreed would only tell us the copy was wrong.

SCORING PROTOCOLS (2026-09-07)
------------------------------
Every artifact written before 2026-09-07 was scored under `unmasked_v1`: the model's raw output
compared against Argo at every depth the float sampled -- including the 93 of 12,829 comparisons
below the training target's own seafloor, where `output.build_record` returns None. The current
protocol, `eval_argo.SCORING_PROTOCOL` (`seafloor_masked_v1`), declines those and counts them.

A re-score is therefore compared only against a record made under the SAME protocol: the training
JSON if it names that protocol, else a sibling `tscast_stage1_<tag>_rescore_<protocol>.json`. When
no same-protocol record exists, this script's output BECOMES that record (unless --no-write), so
the number a checkpoint carries under each protocol is always reproducible from disk. The
training-run JSON is never edited.

A checkpoint whose re-score does not reproduce its same-protocol record must not be shipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                                     # noqa: E402
from oceanembed.validation import validate_argo as VA                     # noqa: E402
from phase2.tscast_nio import config, dataset as D, eval_argo as EA, metrics  # noqa: E402
from phase2.tscast_nio.models.tscast import TSCastNIO, assert_architecture_matches  # noqa: E402
from phase2.tscast_nio.train.train_stage1 import calibration as _calibration  # noqa: E402

MAX_DAYS = 5
TOL = 1e-4          # 4 dp -- the precision the repo quotes its metrics at


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def rescore(tag: str, daily_dir: str, t_seq: int, test_samples: int,
            train_samples: int, unmasked: bool = False) -> dict:
    ckpt_path = base.art(f"tscast_stage1_{tag}.pt")
    if not os.path.exists(ckpt_path):
        raise SystemExit(f"no checkpoint at {ckpt_path}")
    protocol = EA.UNMASKED_PROTOCOL if unmasked else EA.SCORING_PROTOCOL

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device : {dev}   scoring protocol: {protocol}")

    d = D.load_daily(daily_dir)
    tr_t, te_t = D.daily_split_indices(d["times"])
    n_before = len(tr_t)
    tr_t = D.embargo_indices(tr_t, t_seq, int(te_t.min()) if len(te_t) else None)
    print(f"embargo: dropped {n_before - len(tr_t)} of {n_before} training targets")
    print(f"data   : {len(d['times'])} steps, {len(d['channels'])} channels "
          f"{[str(c) for c in d['channels']]}, T_SEQ={t_seq}")

    clim = np.load(base.art("climatology.npy"))
    # ds_tr is rebuilt ONLY to recover the exact normalization the checkpoint was trained under.
    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=t_seq, max_samples=train_samples, seed=base.SEED,
                             clim=clim, return_clim=True)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=t_seq, max_samples=test_samples,
                             seed=base.SEED + 1, clim=clim, return_clim=True)

    ck = torch.load(ckpt_path, map_location=dev, weights_only=False)
    enc = ck.get("encoder", "cnn3d")
    # built_t_seq, never T_SEQ: the encoder is CONSTRUCTED at 1 while T_SEQ is the data window,
    # and the wrong construction loads the same state_dict and predicts differently (harness.py).
    model = TSCastNIO(enc, len(d["channels"]), t_seq=int(ck.get("built_t_seq", 1)), p=config.P,
                      latent=int(ck.get("latent", config.LATENT_DIM)),
                      residual=bool(ck.get("residual", True)),
                      unet_channels=tuple(ck.get("unet_channels") or config.UNET_CHANNELS),
                      decoder=ck.get("decoder", "simple")).to(dev)
    assert_architecture_matches(model, ck, "rescore_checkpoint")
    model.load_state_dict(ck["state_dict"])
    model.eval()
    print(f"loaded : {os.path.basename(ckpt_path)}  encoder={enc}  seed={ck.get('seed')}")

    # ---- the same independent-Argo collocation the trainer uses ----
    argo_df = pd.read_parquet(base.art("argo_daily_period.parquet"))
    keys, truth = VA.pivot_profiles(argo_df)
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)
    print(f"argo   : {int(keep.sum())} independent profiles within +/-{MAX_DAYS} d")

    truth = np.asarray(truth, dtype="float64").copy()
    baseline_ok = EA.baseline_exists_mask(la[keep], lo[keep], d["valid_mask"], d["land_mask"])
    if unmasked:
        refusals = {"scoring_protocol": protocol, "n_refused_below_seafloor": 0,
                    "n_profiles_on_land": 0, "per_depth_refused": [0] * config.N_DEPTHS,
                    "why": "unmasked_v1 reproduces artifacts written before 2026-09-07 and "
                           "declines nothing"}
    else:
        truth[keep], refusals = EA.apply_seafloor_mask(truth[keep], la[keep], lo[keep],
                                                       d["valid_mask"], d["land_mask"])
        print(f"mask   : {refusals['n_refused_below_seafloor']} comparisons below the target's "
              f"seafloor declined, {refusals['n_profiles_on_land']} profile(s) on a land cell; "
              f"{int(baseline_ok.sum())} of {int(keep.sum())} profiles sit on a real climatology")

    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus, lvs = [], []
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            mu, lv = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
            lvs.append(lv.cpu().numpy())
    mu = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * ds_te.y_std

    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    m = metrics.per_depth(mu, truth[keep], clim=clim_at[keep], reference="argo",
                          baseline_ok=baseline_ok)
    cal = _calibration(mu, sigma, truth[keep])

    # Per-basin, using the canonical phase2.basins partition -- the SAME per_depth() on each
    # subset. lat/lon are the kept profiles' own coordinates, aligned row-for-row with mu.
    by_basin = metrics.per_depth_by_basin(
        mu, truth[keep], keys["lat"].values[keep], keys["lon"].values[keep],
        clim=clim_at[keep], reference="argo")
    return {"metrics": m, "calibration": cal, "by_basin": by_basin,
            "argo_profiles": int(keep.sum()), "scoring_protocol": protocol,
            "refusals": refusals, "ckpt_path": ckpt_path, "ck_meta": {
                k: v for k, v in ck.items() if k != "state_dict"}}


def _print_basins(bb: dict) -> None:
    """Show per-basin overall skill and per-depth RMSE, with the profile counts each rests on so a
    basin with few floats is not presented as equal to one with many."""
    from phase2.tscast_nio import config as _c
    pf = bb["profiles"]
    print("")
    print("PER-BASIN (phase2.basins canonical partition)")
    print(f"  profiles: total {pf['total']}  |  Arabian {pf['arabian_sea']}  "
          f"Bay of Bengal {pf['bay_of_bengal']}  unassigned {pf['unassigned']}")
    s = pf['arabian_sea'] + pf['bay_of_bengal'] + pf['unassigned']
    print(f"  reconcile: {pf['arabian_sea']} + {pf['bay_of_bengal']} + {pf['unassigned']} "
          f"= {s}  (== total {pf['total']}: {s == pf['total']})")
    for name in ("arabian_sea", "bay_of_bengal"):
        blk = bb["by_basin"][name]
        if blk.get("n_profiles", 0) == 0:
            print(f"  {name:14s}: no profiles")
            continue
        o = blk["overall"]
        print(f"  {name:14s}: rmse={o['rmse']:.4f}  skill={o['skill_rmse_ratio']:+.4f}  "
              f"bias={o['bias']:+.4f}  n={o['n']}")
    a, b = bb["by_basin"]["arabian_sea"], bb["by_basin"]["bay_of_bengal"]
    if a.get("n_profiles", 0) and b.get("n_profiles", 0):
        print("")
        print(f"  {'depth':>6} {'Arabian RMSE':>13} {'nA':>5} {'BoB RMSE':>10} {'nB':>5}")
        for i, dep in enumerate(_c.DEPTHS):
            print(f"  {dep:>6} {a['rmse'][i]:>13.3f} {a['n'][i]:>5} "
                  f"{b['rmse'][i]:>10.3f} {b['n'][i]:>5}")


def _same_protocol_record(tag: str, protocol: str) -> tuple[dict | None, str | None, str | None]:
    """(overall, filename, protocol_of_training_json). Only a record under `protocol` counts."""
    training = base.art(f"tscast_stage1_{tag}_metrics.json")
    sibling = base.art(f"tscast_stage1_{tag}_rescore_{protocol}.json")
    training_proto = None
    for cand in (training, sibling):
        if not os.path.exists(cand):
            continue
        with open(cand, encoding="utf-8") as f:
            rec = json.load(f)
        proto = rec.get("scoring_protocol", EA.UNMASKED_PROTOCOL)
        if cand == training:
            training_proto = proto
        if proto == protocol:
            return rec["metrics"]["overall"], os.path.basename(cand), training_proto
    return None, None, training_proto


def write_rescore(tag: str, daily_dir: str, got: dict) -> str:
    """The re-score as a full metrics record of the same checkpoint, beside the training JSON.

    Schema-compatible with the training-run JSON so `promote_run.py --rescore` and
    `freeze_headline.py` read it unchanged. `code_commit` keeps the TRAINING commit, because that
    is what promote_run's embargo guard checks; the scoring code's commit is recorded separately.
    """
    protocol = got["scoring_protocol"]
    out_path = base.art(f"tscast_stage1_{tag}_rescore_{protocol}.json")
    training = base.art(f"tscast_stage1_{tag}_metrics.json")
    rec: dict = {}
    if os.path.exists(training):
        with open(training, encoding="utf-8") as f:
            rec = json.load(f)
    payload = {k: v for k, v in rec.items()
               if k not in ("metrics", "calibration", "checkpoint_sha256", "promoted_from",
                            "promoted_at", "promotion_note", "promoted_metrics_source",
                            "scoring_protocol", "refusals")}
    payload.update({
        "metrics": got["metrics"],
        "calibration": got["calibration"],
        "by_basin": got["by_basin"],
        "argo_profiles": got["argo_profiles"],
        "max_days_offset": MAX_DAYS,
        "scoring_protocol": protocol,
        "refusals": got["refusals"],
        "argo_table": EA.argo_table_provenance(base.art("argo_daily_period.parquet")),
        "tag": tag,
        "daily_dir": daily_dir,
        "checkpoint": os.path.basename(got["ckpt_path"]),
        "checkpoint_sha256": _sha256(got["ckpt_path"]),
        "rescored_from": os.path.basename(training) if rec else None,
        "training_code_commit": rec.get("code_commit"),
        "rescore_code_commit": _commit(),
        "rescored_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "rescore_note": (
            f"The SAME checkpoint bytes as {os.path.basename(got['ckpt_path'])}, scored under "
            f"{protocol} by scripts/phase2/rescore_checkpoint.py. The training-run JSON "
            f"({os.path.basename(training)}) is unchanged and remains the record under its own "
            f"protocol. `code_commit` is the training commit; the scoring code is "
            f"`rescore_code_commit`."),
    })
    if "code_commit" not in payload and rec.get("code_commit"):
        payload["code_commit"] = rec["code_commit"]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, allow_nan=True)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True, help="checkpoint tag, e.g. sat_7ch_s42")
    ap.add_argument("--daily-dir", default="data/processed/daily")
    ap.add_argument("--t-seq", type=int, default=11)
    ap.add_argument("--train-samples", type=int, default=60000)
    ap.add_argument("--test-samples", type=int, default=12000)
    ap.add_argument("--unmasked", action="store_true",
                    help="score under unmasked_v1, i.e. exactly as every artifact written before "
                         "2026-09-07 was scored. For reproducing historical numbers only.")
    ap.add_argument("--no-write", action="store_true",
                    help="do not write tscast_stage1_<tag>_rescore_<protocol>.json")
    a = ap.parse_args()

    got = rescore(a.tag, a.daily_dir, a.t_seq, a.test_samples, a.train_samples, a.unmasked)
    protocol = got["scoring_protocol"]
    o = got["metrics"]["overall"]
    ref = got["refusals"]
    print(f"\nRE-SCORED  rmse={o['rmse']:.4f}  corr={o['correlation']:.4f}  "
          f"bias={o['bias']:+.4f}  skill={o['skill_rmse_ratio']:+.4f}  n={o['n']}   "
          f"[{protocol}: {ref['n_refused_below_seafloor']} declined]")
    if "skill_rmse_ratio_real_baseline" in o:
        print(f"           skill where the climatology is REAL: "
              f"{o['skill_rmse_ratio_real_baseline']:+.4f} on "
              f"{o['n_profiles_real_baseline']} profiles (n={o['n_real_baseline']}); the other "
              f"{o['n_profiles_filled_baseline']} sit on a basin-mean fill")

    # Compare BEFORE writing, or a first re-score would trivially agree with itself.
    recorded, recorded_from, training_proto = _same_protocol_record(a.tag, protocol)

    written = None
    if not a.no_write:
        written = write_rescore(a.tag, a.daily_dir, got)
        print(f"wrote      {os.path.relpath(written)}")

    if recorded is None:
        print(f"\n  [new]  no record under {protocol} for this checkpoint"
              + (f" (the training JSON is {training_proto})" if training_proto else "")
              + (f"; this re-score is now that record." if written else
                 "; run without --no-write to create one."))
        _print_basins(got["by_basin"])
        return 0

    print(f"RECORDED   rmse={recorded['rmse']:.4f}  corr={recorded['correlation']:.4f}  "
          f"bias={recorded['bias']:+.4f}  skill={recorded['skill_rmse_ratio']:+.4f}  "
          f"n={recorded['n']}   [{protocol}, from {recorded_from}]")
    diffs = {k: abs(o[k] - recorded[k])
             for k in ("rmse", "bias", "correlation", "skill_rmse_ratio") if k in recorded}
    worst = max(diffs, key=diffs.get)
    if diffs[worst] <= TOL and o["n"] == recorded["n"]:
        print(f"\n  [ok]   AGREES to 4 dp (largest gap {worst} {diffs[worst]:.2e}). The recorded "
              f"metrics are reproducible from the checkpoint on disk.")
        _print_basins(got["by_basin"])
        return 0
    print(f"\n  [FAIL] DIFFERS -- largest gap {worst} {diffs[worst]:.2e}, n {o['n']} vs "
          f"{recorded['n']}.\n         The checkpoint does not reproduce its own same-protocol "
          f"record. Do not ship this number until the cause is found.")
    _print_basins(got["by_basin"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
