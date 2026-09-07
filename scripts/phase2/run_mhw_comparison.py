"""Model-vs-GLORYS marine-heatwave detection comparison, per depth.

OWNER: Unit A (Arjhun / MHW feature).

THE QUESTION: does the model's reconstruction see the same heatwaves the GLORYS truth shows?
Both fields are scored against the SAME threshold, so the baseline's warming bias is common to both
and cancels in the contingency table -- this stays valid even while the pilot baseline over-flags
absolute counts.

HONEST LABELLING OF WHAT RUNS HERE
The satellite-input bundle (data/processed/daily_sat/v001) is NOT on this machine, so the model is
run in GLORYS-INPUT mode: checkpoint tscast_stage1_7ch.pt on data/processed/daily. That measures
reconstruction fidelity given REANALYSIS inputs -- the comparator leg, not the satellite deliverable.
The satellite-driven version needs the satellite bundle; re-run with that checkpoint+bundle to get it.
The output JSON records which leg produced it so the two can never be confused.

BASELINE: monthly pilot (grids.npz, 2019-2022) unless --daily-baseline points at a downloaded
day-of-year baseline. Pilot is labelled not-Hobday-compliant in the output.

Run:  PYTHONPATH=src python scripts/phase2/run_mhw_comparison.py            # all 388 days, GPU if present
      PYTHONPATH=src python scripts/phase2/run_mhw_comparison.py --days 20  # quick dry run (first 20 days)
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch

from oceanembed import config
from phase2.derived import mhw_baseline as mb
from phase2.derived import mhw_field as mf
from phase2.tscast_nio.field import predict_field
from phase2.tscast_nio.inference import TSCastPredictor

#: Default when nothing is passed: the GLORYS-input comparator this script was written against.
#: It does not exist on every machine -- pass --checkpoint to run the SATELLITE deliverable leg,
#: which is the one the problem statement asks about. The cache and output are derived from the
#: checkpoint so the two legs can never overwrite each other's numbers (added 2026-09-07).
MODEL_CKPT = "artifacts/tscast_stage1_7ch.pt"          # GLORYS-input comparator
CACHE = "artifacts/mhw_model_field_glorys.npz"
OUT = "artifacts/mhw_comparison.json"


def _load_truth():
    d25 = np.load("data/processed/daily/2025.npz", allow_pickle=True)
    d26 = np.load("data/processed/daily/2026.npz", allow_pickle=True)
    temp = np.concatenate([d25["temp"], d26["temp"]], axis=0)
    times = np.concatenate([d25["times"], d26["times"]])
    return temp, times, d25["land_mask"], d25["valid_mask"]


def _leg_paths(ckpt: str) -> tuple[str, str, str]:
    """(cache, out, leg label) for a checkpoint, so the satellite and GLORYS legs stay separate."""
    import torch as _t
    from phase2.tscast_nio.dataset import bundle_for_checkpoint
    meta = _t.load(ckpt, map_location="cpu", weights_only=False)
    bundle, how = bundle_for_checkpoint(meta, ckpt)
    sat = "daily_sat" in str(bundle)
    tag = "satellite" if sat else "glorys"
    leg = (f"SATELLITE-INPUT -- the PS deliverable leg. Bundle {bundle} ({how})." if sat else
           f"GLORYS-INPUT comparator, NOT the satellite deliverable. Bundle {bundle} ({how}).")
    return (f"artifacts/mhw_model_field_{tag}.npz", f"artifacts/mhw_comparison_{tag}.json", leg)


def _model_field(times, days: int, ckpt: str = MODEL_CKPT, cache: str = CACHE):
    """Model temperature for the first `days` dates, GPU if available, cached to disk (resumable)."""
    dates = [str(np.datetime64(t, "D")) for t in times[:days]]
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        if int(z["n"]) >= days:
            print(f"[cache] reusing model field for {days} days from {cache}", flush=True)
            return z["temp"][:days]
    p = TSCastPredictor(checkpoint=ckpt)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    p.model.to(dev)                                     # move MODEL to gpu (the 5x speedup)
    print(f"[model] {ckpt} on {dev}; inferring {days} days ...", flush=True)
    out = np.full((days, config.N_LAT, config.N_LON, config.N_DEPTHS), np.nan, dtype="float32")
    t0 = time.time()
    for k, d in enumerate(dates):
        out[k] = predict_field(p, d)["temperature"]
        if (k + 1) % 20 == 0 or k == days - 1:
            el = time.time() - t0
            print(f"[model] {k+1}/{days}  {el/ (k+1):.1f}s/day  eta {el/(k+1)*(days-k-1)/60:.0f} min",
                  flush=True)
    np.savez_compressed(cache, temp=out, n=days)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=388, help="first N consecutive days (default all 388)")
    ap.add_argument("--checkpoint", default=MODEL_CKPT,
                    help="model to run. Pass artifacts/tscast_stage1.pt for the SATELLITE "
                         "deliverable leg; the default is the GLORYS-input comparator.")
    a = ap.parse_args()
    if not os.path.exists(a.checkpoint):
        raise SystemExit(
            f"{a.checkpoint} is not on this machine. Pass --checkpoint; "
            f"artifacts/tscast_stage1.pt is the promoted satellite deliverable.")
    cache, out_path, leg = _leg_paths(a.checkpoint)
    print(f"leg: {leg}", flush=True)

    truth, times, land, valid = _load_truth()
    days = min(a.days, truth.shape[0])
    truth = truth[:days].astype("float64")
    times = times[:days]
    print(f"detection window: {times[0]} .. {times[-1]}  ({days} days)", flush=True)

    # monthly pilot baseline from on-disk 2019-2022
    g = np.load("data/processed/grids.npz", allow_pickle=True)
    clim12, thr12 = mb.monthly_climatology_threshold(g["temp"], g["times"], pct=mb.PERCENTILE)

    model = _model_field(times, days, ckpt=a.checkpoint, cache=cache).astype("float64")

    per_depth = {}
    for z, depth_m in enumerate(config.DEPTHS):
        thr_s = mb.map_monthly_to_series(thr12[:, :, :, z], times)
        clm_s = mb.map_monthly_to_series(clim12[:, :, :, z], times)
        mflags = mf.mhw_day_flags_grid(model[:, :, :, z], clm_s, thr_s, land)
        tflags = mf.mhw_day_flags_grid(truth[:, :, :, z], clm_s, thr_s, land)
        cmp = mf.compare_detection(mflags, tflags, valid=valid[:, :, z])
        per_depth[int(depth_m)] = cmp
        pod = cmp["pod"]; csi = cmp["csi"]
        print(f"[depth {depth_m:>4} m] POD={pod if pod is None else round(pod,3)}  "
              f"CSI={csi if csi is None else round(csi,3)}  "
              f"truth_days={cmp['n_truth_mhw_days']}  model_days={cmp['n_model_mhw_days']}", flush=True)

    result = {
        "what": "model-vs-GLORYS marine-heatwave detection agreement, per depth",
        "model_leg": leg,
        "checkpoint": a.checkpoint,
        "baseline": "MONTHLY PILOT (grids.npz 2019-2022), not Hobday day-of-year -- absolute counts "
                    "inflated by warming trend; the model-vs-truth agreement cancels that bias",
        "window": [str(times[0]), str(times[-1])], "n_days": days,
        "min_duration_days": 5, "max_gap_days": 2, "percentile": mb.PERCENTILE,
        "per_depth": per_depth,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
