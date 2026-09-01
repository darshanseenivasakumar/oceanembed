"""Re-score a SAVED TS-Cast-NIO checkpoint against independent Argo, and check the number
it produces against the number recorded beside it.

    python scripts/phase2/rescore_checkpoint.py --tag 7ch
    python scripts/phase2/rescore_checkpoint.py --tag 5ch --daily-dir data/processed/daily_5ch

WHY THIS EXISTS
---------------
`docs/EXPERIMENT_LOG.md` records the v2 headline as 0.8612 degC (7ch) against 0.8760 (5ch), from
commit 6e6ba9a. The checkpoints now on disk were retrained AFTER the leakage embargo landed
(a5cdd3a) and their own metrics files report 0.8793 and 0.8682 -- which reverses the sign of the
wind result. Before that correction is written into an append-only scientific record, the numbers
have to be reproduced independently of the training run that first printed them.

So this script does NOT retrain. It reloads the checkpoint from disk, rebuilds the same test
split, embargo, normalization, climatology and Argo collocation, and re-runs the scoring. It
reuses the trainer's OWN modules (dataset, metrics, validate_argo) rather than reimplementing
them: a second implementation that disagreed would only tell us the copy was wrong.

It then compares against the stored metrics JSON and says AGREES or DIFFERS. A checkpoint whose
re-score does not reproduce its own recorded metrics must not be shipped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                       # noqa: E402
from oceanembed.validation import validate_argo as VA       # noqa: E402
from phase2.tscast_nio import config, dataset as D, metrics  # noqa: E402
from phase2.tscast_nio.models.tscast import TSCastNIO       # noqa: E402

MAX_DAYS = 5
TOL = 1e-4          # 4 dp -- the precision the repo quotes its metrics at


def rescore(tag: str, daily_dir: str, t_seq: int, test_samples: int,
            train_samples: int) -> dict:
    ckpt_path = base.art(f"tscast_stage1_{tag}.pt")
    if not os.path.exists(ckpt_path):
        raise SystemExit(f"no checkpoint at {ckpt_path}")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device : {dev}")

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
    model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P,
                      latent=config.LATENT_DIM, residual=True,
                      unet_channels=tuple(config.UNET_CHANNELS), decoder="simple").to(dev)
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

    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus = []
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            mu, _lv = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
    mu = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean

    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    m = metrics.per_depth(mu, truth[keep], clim=clim_at[keep], reference="argo")

    # Per-basin, using the canonical phase2.basins partition -- the SAME per_depth() on each
    # subset. lat/lon are the kept profiles' own coordinates, aligned row-for-row with mu.
    by_basin = metrics.per_depth_by_basin(
        mu, truth[keep], keys["lat"].values[keep], keys["lon"].values[keep],
        clim=clim_at[keep], reference="argo")
    return {"overall": m["overall"], "argo_profiles": int(keep.sum()), "by_basin": by_basin}


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True, help="checkpoint tag, e.g. 7ch or 5ch")
    ap.add_argument("--daily-dir", default="data/processed/daily")
    ap.add_argument("--t-seq", type=int, default=11)
    ap.add_argument("--train-samples", type=int, default=60000)
    ap.add_argument("--test-samples", type=int, default=12000)
    a = ap.parse_args()

    got = rescore(a.tag, a.daily_dir, a.t_seq, a.test_samples, a.train_samples)
    o = got["overall"]
    print(f"\nRE-SCORED  rmse={o['rmse']:.4f}  corr={o['correlation']:.4f}  "
          f"bias={o['bias']:+.4f}  skill={o['skill_rmse_ratio']:+.4f}  n={o['n']}")

    rec_path = base.art(f"tscast_stage1_{a.tag}_metrics.json")
    if not os.path.exists(rec_path):
        print(f"  [warn] no recorded metrics at {rec_path}; nothing to compare against")
        return 0
    with open(rec_path) as f:
        rec = json.load(f)["metrics"]["overall"]
    print(f"RECORDED   rmse={rec['rmse']:.4f}  corr={rec['correlation']:.4f}  "
          f"bias={rec['bias']:+.4f}  skill={rec['skill_rmse_ratio']:+.4f}  n={rec['n']}")

    diffs = {k: abs(o[k] - rec[k]) for k in ("rmse", "bias", "correlation", "skill_rmse_ratio")
             if k in rec}
    worst = max(diffs, key=diffs.get)
    if diffs[worst] <= TOL and o["n"] == rec["n"]:
        print(f"\n  [ok]   AGREES to 4 dp (largest gap {worst} {diffs[worst]:.2e}). The recorded "
              f"metrics are reproducible from the checkpoint on disk.")
        _print_basins(got["by_basin"])
        return 0
    print(f"\n  [FAIL] DIFFERS -- largest gap {worst} {diffs[worst]:.2e}, n {o['n']} vs {rec['n']}."
          f"\n         The checkpoint does not reproduce its own recorded metrics. Do not ship "
          f"this number until the cause is found.")
    _print_basins(got["by_basin"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
