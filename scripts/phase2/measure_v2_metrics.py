"""Measure RMSE + correlation + bias per depth against independent Argo -- PS req 12, 13, 14.

Writes artifacts/tscast_baseline_metrics.json: the INCUMBENT (Phase-1 MLP) scored on the three PS
metrics. Correlation had never been computed anywhere in this repo; bias was computed inside
validate_argo.py but never persisted or shown. This is the baseline the v2 model must beat.

Uses the same +/-5 day collocation filter as scripts/eval_satellite_vs_argo.py, so the RMSE column
is comparable to the published artifacts/argo_error_by_depth.json.

Run:  PYTHONPATH=src python scripts/phase2/measure_v2_metrics.py
"""
from __future__ import annotations

import json
import subprocess

import numpy as np
import pandas as pd

from oceanembed import config
from oceanembed.inference import predict
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import metrics

MAX_DAYS = 5


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def measure(source: str = "satellite") -> dict:
    predict.set_source(source)
    keys, truth = VA.pivot_profiles(VA.load_argo())
    pred = VA.predict_at_argo_points(keys)

    times = np.asarray(predict.available_dates(), dtype="datetime64[D]")
    dates = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    gap = np.array([int(np.min(np.abs((times - d).astype("timedelta64[D]").astype(int))))
                    for d in dates])
    keep = gap <= MAX_DAYS

    clim = np.load(config.art("climatology.npy"))
    lat_i = np.clip(np.searchsorted(config.LAT, keys["lat"].values) - 1, 0, config.N_LAT - 1)
    lon_i = np.clip(np.searchsorted(config.LON, keys["lon"].values) - 1, 0, config.N_LON - 1)
    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, lat_i, lon_i, :]

    out = metrics.per_depth(pred[keep], truth[keep], clim=clim_at[keep], reference="argo",
                            window={"start": "2022-01-01", "end": "2022-12-31"})
    out["model"] = "phase1-mlp (incumbent baseline)"
    out["source"] = source
    out["max_days_offset"] = MAX_DAYS
    out["n_profiles_matched"] = int(keep.sum())
    out["n_profiles_total"] = int(len(keep))
    out["code_commit"] = _commit()
    out["what_this_is"] = (
        "The INCUMBENT Phase-1 MLP on the three PS metrics. The v2 TS-Cast model must beat this "
        "on the same profiles, the same filter and the same climatology, or it is not an "
        "improvement."
    )
    return out


def main() -> None:
    m = measure()
    path = config.art("tscast_baseline_metrics.json")
    with open(path, "w") as f:
        json.dump(m, f, indent=1)

    print(f"{'depth':>6} {'n':>5} {'RMSE':>7} {'corr':>7} {'bias':>8} {'skill':>7} {'RMSEclim':>9}")
    for i, d in enumerate(m["depths_m"]):
        print(f"{d:>6} {m['n'][i]:>5} {m['rmse'][i]:>7.3f} {m['correlation'][i]:>7.3f} "
              f"{m['bias'][i]:>+8.3f} {m['skill_vs_climatology'][i]:>7.3f} "
              f"{m['rmse_climatology'][i]:>9.3f}")
    o = m["overall"]
    print(f"\nOVERALL  rmse={o['rmse']:.4f}  corr={o['correlation']:.4f} (per-depth mean; "
          f"pooled {o['correlation_pooled']:.4f} is inflated)  bias={o['bias']:+.4f}  "
          f"skill={o['skill_rmse_ratio']:.4f} (1-RMSE/RMSEclim, the Phase-1 headline "
          f"definition; Murphy 1-MSE/MSEclim reads {o['skill_vs_climatology']:.4f} -- "
          f"NOT interchangeable)")
    print(f"matched {m['n_profiles_matched']} of {m['n_profiles_total']} profiles "
          f"within +/-{MAX_DAYS} days")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
