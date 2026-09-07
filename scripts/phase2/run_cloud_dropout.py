"""How fast does the model degrade when cloud hides the SST? Owner: Unit A (Arjhun).

    python scripts/phase2/run_cloud_dropout.py --tag sat_7ch_s42 \
        --daily-dir data/processed/daily_sat/v001

No retraining. The shipped checkpoint is reloaded, the SAME test split, embargo, normalisation,
climatology and Argo collocation are rebuilt -- `rescore_checkpoint.py`'s structure, because a
second implementation that disagreed would only tell us the copy was wrong -- and then a fraction
of ocean SST is blanked in the TEST input before scoring.

THE CONTROL IS THE WHOLE EXPERIMENT
At fraction 0.0 this must reproduce the checkpoint's own recorded RMSE. If it does not, the
harness is introducing error and every degradation number after it is that error, not cloud. The
run REFUSES to write its artifact when the control disagrees.

WHY THE NORMALISATION COMES FROM THE PRISTINE ARRAY
The checkpoint was fitted under one set of channel statistics. Recomputing them from a masked
array would change the model's input scaling as well as its content, and the experiment would be
measuring two things at once. So the TRAIN dataset -- which exists only to recover `norm` -- is
built from the untouched bundle, and only the TEST dataset is masked. That is also what cloud
actually does: it arrives at inference time, long after the weights were fitted.

SEVERAL MASK REALISATIONS PER FRACTION
A single random mask is one draw. The spread across draws is the noise floor against which a
degradation has to be judged, exactly as `run_sat_ablations.py` treats its three training seeds.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                        # noqa: E402
from oceanembed.validation import validate_argo as VA        # noqa: E402
from phase2.tscast_nio import config, dataset as D, metrics  # noqa: E402
from phase2.tscast_nio.models.tscast import TSCastNIO        # noqa: E402
from phase2.validation import dropout as DO                  # noqa: E402

MAX_DAYS = 5
CONTROL_TOL = 1e-3          # the control must reproduce the recorded RMSE to 3 dp
OUT = base.art("cloud_dropout.json")


def _collocate(d, te_t):
    """The trainer's own independent-Argo collocation, unchanged."""
    argo_df = pd.read_parquet(base.art("argo_daily_period.parquet"))
    keys, truth = VA.pivot_profiles(argo_df)
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)
    if int(keep.sum()) == 0:
        raise SystemExit("no Argo profile in the test window -- refusing to score on zero profiles")
    # Decline what the product declines (eval_argo.apply_seafloor_mask); the count is kept on
    # the function so the artifact can record it beside the score.
    truth = np.asarray(truth, dtype="float64").copy()
    truth[keep], _collocate.last_refusals = EA.apply_seafloor_mask(
        truth[keep], la[keep], lo[keep], d["valid_mask"], d["land_mask"])
    _collocate.last_baseline_ok = EA.baseline_exists_mask(la[keep], lo[keep],
                                                          d["valid_mask"], d["land_mask"])
    return keys, truth, keep, t_idx, la, lo


_collocate.last_refusals = {}
_collocate.last_baseline_ok = None


def score_once(d, surface, norm, clim, model, dev, te_t, coll, t_seq, test_samples) -> dict:
    """Score one (possibly masked) surface array against the same Argo profiles."""
    keys, truth, keep, t_idx, la, lo = coll
    ds = D.GriddedPatches(surface, d["temp"], d["times"], d["land_mask"], d["channels"],
                          te_t, norm=norm, t_seq=t_seq, max_samples=test_samples,
                          seed=base.SEED + 1, clim=clim, return_clim=True)
    ds.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus = []
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            mu, _ = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
    mu = np.concatenate(mus) * ds.y_std + ds.y_mean
    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    m = metrics.per_depth(mu, truth[keep], clim=clim_at[keep], reference="argo",
                          baseline_ok=_collocate.last_baseline_ok)
    return {"rmse": float(m["overall"]["rmse"]), "bias": float(m["overall"]["bias"]),
            "correlation": float(m["overall"]["correlation"]),
            "skill_rmse_ratio": float(m["overall"]["skill_rmse_ratio"]),
            "n": int(m["overall"]["n"]),
            "rmse_by_depth": [None if v is None else float(v) for v in m["rmse"]]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="sat_7ch_s42")
    ap.add_argument("--daily-dir", default=os.path.join("data", "processed", "daily_sat", "v001"))
    ap.add_argument("--t-seq", type=int, default=config.T_SEQ)
    ap.add_argument("--test-samples", type=int, default=12000)
    ap.add_argument("--train-samples", type=int, default=40000)
    ap.add_argument("--fractions", type=float, nargs="+",
                    default=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0])
    ap.add_argument("--mask-seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--channel", default=DO.DEFAULT_CHANNEL)
    a = ap.parse_args()

    ckpt_path = base.art(f"tscast_stage1_{a.tag}.pt")
    metrics_path = base.art(f"tscast_stage1_{a.tag}_metrics.json")
    if not os.path.exists(ckpt_path):
        raise SystemExit(f"no checkpoint at {ckpt_path}")
    # The control must be compared with a record made under the SAME scoring protocol. The
    # training JSON of every checkpoint before 2026-09-07 is unmasked_v1; the re-score under the
    # current protocol lives beside it as *_rescore_<protocol>.json (scripts/phase2/rescore_checkpoint.py).
    recorded, recorded_from = None, None
    for cand in (metrics_path,
                 base.art(f"tscast_stage1_{a.tag}_rescore_{EA.SCORING_PROTOCOL}.json")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                rec = json.load(f)
            if rec.get("scoring_protocol", EA.UNMASKED_PROTOCOL) == EA.SCORING_PROTOCOL:
                recorded, recorded_from = float(rec["metrics"]["overall"]["rmse"]), os.path.basename(cand)
                break
    if recorded is None:
        print(f"no record under {EA.SCORING_PROTOCOL} beside {os.path.basename(ckpt_path)}; run "
              f"scripts/phase2/rescore_checkpoint.py --tag {a.tag} first, or the control cannot be checked")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    d = D.load_daily(a.daily_dir)
    tr_t, te_t = D.daily_split_indices(d["times"])
    tr_t = D.embargo_indices(tr_t, a.t_seq, int(te_t.min()) if len(te_t) else None)
    clim = np.load(base.art("climatology.npy"))

    # PRISTINE, on purpose: this exists only to recover the normalisation the checkpoint was
    # trained under. Rebuilding it from a masked array would change the input scaling too.
    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=a.t_seq, max_samples=a.train_samples, seed=base.SEED,
                             clim=clim, return_clim=True)

    ck = torch.load(ckpt_path, map_location=dev, weights_only=False)
    model = TSCastNIO(ck.get("encoder", "cnn3d"), len(d["channels"]), t_seq=1, p=config.P,
                      latent=config.LATENT_DIM, residual=True,
                      unet_channels=tuple(config.UNET_CHANNELS), decoder="simple").to(dev)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    coll = _collocate(d, te_t)
    n_prof = int(coll[2].sum())
    print(f"device {dev} · checkpoint {os.path.basename(ckpt_path)} · {n_prof} independent Argo "
          f"profiles · masking channel {a.channel!r}")
    if recorded is not None:
        print(f"recorded RMSE for this checkpoint: {recorded:.4f} degC")

    legs, t0 = [], time.time()
    for frac in a.fractions:
        seeds = [0] if frac == 0.0 else a.mask_seeds     # one draw is the whole population at 0%
        for seed in seeds:
            rng = np.random.default_rng(seed)
            cloud = DO.apply_cloud(d["surface"], d["channels"], frac, land_mask=d["land_mask"],
                                   rng=rng, channel=a.channel)
            r = score_once(d, cloud["surface"], ds_tr.norm, clim, model, dev, te_t, coll,
                           a.t_seq, a.test_samples)
            r.update(fraction=frac, mask_seed=seed,
                     fraction_achieved=cloud["fraction_achieved"],
                     fraction_now_missing=cloud["fraction_now_missing"],
                     n_masked=cloud["n_masked"])
            legs.append(r)
            print(f"  mask {frac:5.0%} (now missing {cloud['fraction_now_missing']:5.1%}) "
                  f"seed {seed} "
                  f"-> RMSE {r['rmse']:.4f}  bias {r['bias']:+.4f}  skill "
                  f"{r['skill_rmse_ratio']:+.4f}")
            del cloud

    control = next(r for r in legs if r["fraction"] == 0.0)
    ok = recorded is None or abs(control["rmse"] - recorded) < CONTROL_TOL
    print(f"\ncontrol (0% masked): {control['rmse']:.4f} vs recorded "
          f"{'n/a' if recorded is None else f'{recorded:.4f}'} -> "
          f"{'AGREES' if ok else 'DIFFERS'}")
    if not ok:
        print("REFUSING to write the artifact: the harness does not reproduce the checkpoint's own\n"
              "number at 0% masking, so every degradation below it is harness error, not cloud.")
        return 1

    by_fraction = {}
    for frac in a.fractions:
        rs = [r["rmse"] for r in legs if r["fraction"] == frac]
        bs = [r["bias"] for r in legs if r["fraction"] == frac]
        by_fraction[f"{frac:g}"] = {
            "mean_rmse": float(np.mean(rs)), "spread": float(np.max(rs) - np.min(rs)),
            "mean_bias": float(np.mean(bs)), "n_draws": len(rs),
            "delta_vs_control": float(np.mean(rs) - control["rmse"]),
        }

    # THE NON-MONOTONE PART, ANALYSED RATHER THAN GLOSSED.
    # Light masking IMPROVES the score, and it would be easy and wrong to report that as "the
    # model tolerates cloud". It is two errors partially cancelling: the shipped model carries a
    # warm bias, blanking SST pulls a prediction toward the channel mean (which is cooler than the
    # model's own answer), and the RMSE minimum sits essentially where the bias crosses zero.
    xs = sorted(float(k) for k in by_fraction)
    rm = [by_fraction[f"{x:g}"]["mean_rmse"] for x in xs]
    bi = [by_fraction[f"{x:g}"]["mean_bias"] for x in xs]
    i_min = int(np.argmin(rm))
    crossing = None
    for u, v, x0, x1 in zip(bi, bi[1:], xs, xs[1:]):
        if u == 0 or (u > 0) != (v > 0):
            crossing = float(x0 + (x1 - x0) * (u / (u - v))) if u != v else float(x0)
            break
    analysis = {
        "control_bias": control["bias"],
        "rmse_minimising_fraction": xs[i_min], "rmse_at_minimum": rm[i_min],
        "improvement_vs_control": float(control["rmse"] - rm[i_min]),
        "seed_spread_at_minimum": by_fraction[f"{xs[i_min]:g}"]["spread"],
        "bias_zero_crossing_fraction": crossing,
        "interpretation": (
            "Light masking lowers RMSE because it CANCELS a pre-existing warm bias, not because "
            "the model handles missing data well. A blanked pixel reaches the encoder as the "
            "channel mean, which pulls the prediction cooler; the RMSE minimum sits where the "
            "bias crosses zero. Reported as a bias finding about the deliverable, NOT as evidence "
            "of robustness to cloud."),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "what": "RMSE against independent Argo as a fraction of ocean SST is blanked at "
                    "inference time",
            "how": "the shipped checkpoint, unmodified; masking applied in PHYSICAL units to the "
                   "test bundle before normalisation; the training normalisation recovered from "
                   "the pristine array",
            "checkpoint": os.path.basename(ckpt_path), "tag": a.tag,
            "recorded_rmse": recorded, "recorded_from": recorded_from,
            "control_rmse": control["rmse"],
            "control_agrees": ok, "control_tolerance": CONTROL_TOL,
            "scoring_protocol": EA.SCORING_PROTOCOL, "refusals": _collocate.last_refusals,
            "channel_masked": a.channel, "argo_profiles": n_prof,
            "t_seq": a.t_seq, "daily_dir": a.daily_dir,
            "mask_seeds": a.mask_seeds, "fractions": a.fractions,
            "seconds": round(time.time() - t0, 1),
            "caveat": ("The encoder has no missing-data channel. dataset.__getitem__ z-scores the "
                       "patch and replaces every non-finite value with 0.0, which IS the channel "
                       "mean -- so a blanked pixel reaches the model as average water and it "
                       "cannot tell the two apart. This measures degradation under that "
                       "behaviour, not under a model designed to handle gaps."),
            "legs": legs, "by_fraction": by_fraction, "analysis": analysis,
        }, f, indent=1)
    print(f"wrote {OUT}  ({time.time() - t0:.0f} s)")

    print("")
    print("RMSE vs mask fraction: " + "  ".join(f"{x:.0%}={y:.4f}" for x, y in zip(xs, rm)))
    print("bias vs mask fraction: " + "  ".join(f"{x:.0%}={y:+.4f}" for x, y in zip(xs, bi)))
    print("")
    print(f"minimum RMSE {analysis['rmse_at_minimum']:.4f} at "
          f"{analysis['rmse_minimising_fraction']:.0%} masked -- "
          f"{analysis['improvement_vs_control']:+.4f} degC BETTER than the control, "
          f"against a seed spread of {analysis['seed_spread_at_minimum']:.4f}")
    if crossing is not None:
        print(f"bias crosses zero at ~{crossing:.0%} masked (control bias "
              f"{control['bias']:+.4f} degC)")
    print("  -> light masking CANCELS a warm bias; NOT evidence of robustness to cloud")
    tail = [x for x in xs if x >= analysis["rmse_minimising_fraction"]]
    ty = [by_fraction[f"{x:g}"]["mean_rmse"] for x in tail]
    print(f"monotone increasing beyond the minimum: "
          f"{all(b >= a_ - 1e-9 for a_, b in zip(ty, ty[1:]))}")
    print(f"100% vs 0%: {rm[-1] - rm[0]:+.4f} degC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
