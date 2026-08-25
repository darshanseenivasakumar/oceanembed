"""THE PS EXPERIMENT: reconstruct from REAL SATELLITE observations, validate against REAL ARGO.

OWNER: Unit B (Darshan).

SIH26066 asks for subsurface temperature "from surface satellite observations". This script runs the
model on actual satellite L4 fields and scores it against independent Argo floats -- a different
instrument entirely, never seen in training.

It reports THREE things side by side so the satellite number is interpretable:
  climatology  -- the baseline any model must beat
  GLORYS-driven -- the model on the same fields it was TRAINED on (its ceiling)
  satellite-driven -- the model on real observations (the PS deliverable)

The gap between the last two IS the domain shift, measured end-to-end in degC rather than argued.

FAIRNESS: both sources hold the same 12 monthly dates in 2022, so each Argo profile is matched to
the nearest available date within MAX_DAYS. The same profiles are used for every column.

Run:  python scripts/eval_satellite_vs_argo.py
"""
from __future__ import annotations
import os
import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
warnings.filterwarnings("ignore")
# MC-dropout is stochastic by design, so quoted numbers drifted ~0.001 skill between runs.
# Seeding here (not in Unit A's mc_dropout_predict) makes every reported figure exactly
# reproducible without changing the uncertainty contract.
import torch as _torch; _torch.manual_seed(0); np_seed = 0
from oceanembed import config                      # noqa: E402
from oceanembed.utils import io, grids             # noqa: E402
from oceanembed.inference import predict as P      # noqa: E402
from oceanembed.climatology import climatology_predict  # noqa: E402

MAX_DAYS = 5      # temporal tolerance between an Argo profile and the nearest gridded date


def _profiles():
    """Argo profiles as (lat, lon, date, temps[15]) with NaN where that depth was not sampled."""
    df = io.load_table(config.art("argo_test"))
    df["date"] = pd.to_datetime(df["date"])
    out = []
    for (la, lo, dt), grp in df.groupby(["lat", "lon", "date"]):
        t = np.full(config.N_DEPTHS, np.nan, dtype="float32")
        t[grp["depth_idx"].to_numpy()] = grp["temp"].to_numpy()
        out.append((float(la), float(lo), pd.Timestamp(dt), t))
    return out


def _predict_all(source: str, profs):
    """Model prediction at each Argo profile's cell/date, using `source` surface fields."""
    P.set_source(source)
    times = P._grids()["times"].astype("datetime64[D]")
    preds, keep = [], []
    for k, (la, lo, dt, _) in enumerate(profs):
        d = np.datetime64(dt.date(), "D")
        gap = int(np.min(np.abs((times - d).astype("timedelta64[D]").astype(int))))
        if gap > MAX_DAYS:
            continue
        try:
            o = P.reconstruct(la, lo, dt)
        except Exception:
            continue
        if o["is_land"] or o["profile_mean"] is None:
            continue
        preds.append(o["profile_mean"]); keep.append(k)
    return np.asarray(preds, dtype="float32"), keep


def _metrics(pred, truth):
    """Per-depth RMSE over cells where Argo actually sampled."""
    e = pred - truth
    m = np.isfinite(e)
    rmse_d = np.array([np.sqrt(np.nanmean(e[:, k][m[:, k]] ** 2)) if m[:, k].any() else np.nan
                       for k in range(config.N_DEPTHS)])
    return float(np.sqrt(np.nanmean(e[m] ** 2))), rmse_d, m.sum(0)


def main() -> None:
    for s in ("glorys", "satellite"):
        if not P.source_available(s):
            raise SystemExit(f"{s} grids missing -- build them first")

    profs = _profiles()
    print(f"Argo profiles in test year: {len(profs)}")

    p_glo, keep_g = _predict_all("glorys", profs)
    p_sat, keep_s = _predict_all("satellite", profs)
    common = sorted(set(keep_g) & set(keep_s))          # identical profiles for every column
    if not common:
        raise SystemExit("no profiles matched both sources")
    ig = [keep_g.index(i) for i in common]
    isx = [keep_s.index(i) for i in common]

    truth = np.stack([profs[i][3] for i in common])
    meta = pd.DataFrame({
        "lat": [profs[i][0] for i in common], "lon": [profs[i][1] for i in common],
        "month": [profs[i][2].month for i in common],
        "cell_id": [grids.latlon_to_cell_id(profs[i][0], profs[i][1]) for i in common],
    })
    clim = climatology_predict(meta)

    r_c, d_c, n = _metrics(clim, truth)
    r_g, d_g, _ = _metrics(p_glo[ig], truth)
    r_s, d_s, _ = _metrics(p_sat[isx], truth)

    print("=" * 78)
    print("VALIDATION AGAINST INDEPENDENT ARGO FLOATS   (test year, never seen in training)")
    print(f"  {len(common)} profiles matched within +/-{MAX_DAYS} days of a gridded date")
    print("=" * 78)
    print(f"  {'source':<26s} {'RMSE':>8s}  {'skill vs climatology':>21s}")
    print(f"  {'climatology (baseline)':<26s} {r_c:8.4f}  {'--':>21s}")
    print(f"  {'model on GLORYS fields':<26s} {r_g:8.4f}  {1-r_g/r_c:+21.3f}")
    print(f"  {'model on SATELLITE fields':<26s} {r_s:8.4f}  {1-r_s/r_c:+21.3f}   <- the PS deliverable")
    print()
    print(f"  {'depth':>6s} {'n':>6s} {'clim':>8s} {'glorys':>8s} {'satellite':>10s} "
          f"{'skill_sat':>10s}")
    for k, dep in enumerate(config.DEPTHS):
        sk = 1 - d_s[k] / d_c[k] if np.isfinite(d_c[k]) and d_c[k] > 0 else np.nan
        print(f"  {dep:6d} {n[k]:6d} {d_c[k]:8.3f} {d_g[k]:8.3f} {d_s[k]:10.3f} {sk:+10.3f}")
    # Persist per-depth measured error so the UI can show a REAL number instead of a
    # fabricated confidence label. MC-dropout sigma is uncalibrated (DECISIONS D-016); this is
    # the error the model ACTUALLY made against independent floats at each depth.
    io.save_json({
        "measured_against": "independent Argo floats, test year",
        "n_profiles": int(len(common)),
        "max_days_offset": MAX_DAYS,
        "depths": list(config.DEPTHS),
        "rmse_satellite": [None if not np.isfinite(v) else round(float(v), 3) for v in d_s],
        "rmse_glorys": [None if not np.isfinite(v) else round(float(v), 3) for v in d_g],
        "rmse_climatology": [None if not np.isfinite(v) else round(float(v), 3) for v in d_c],
        "n_obs_per_depth": [int(v) for v in n],
        # Overall figures, so the UI validation panel can show MEASURED numbers instead of
        # computing something from whatever dict it happens to be handed.
        "overall": {
            "satellite": {"rmse": round(float(r_s), 4), "mae": round(float(np.nanmean(np.abs(p_sat[isx] - truth))), 4),
                          "skill_vs_clim": round(float(1 - r_s / r_c), 4)},
            "glorys":    {"rmse": round(float(r_g), 4), "mae": round(float(np.nanmean(np.abs(p_glo[ig] - truth))), 4),
                          "skill_vs_clim": round(float(1 - r_g / r_c), 4)},
            "climatology": {"rmse": round(float(r_c), 4)},
        },
        "note": ("This is measured error, not model confidence. Quote it instead of the "
                 "MC-dropout spread, which D-016 measured as overconfident at the thermocline."),
    }, config.art("argo_error_by_depth.json"))
    print(f"[wrote {config.art('argo_error_by_depth.json')}]")

    print("-" * 78)
    print(f"  DOMAIN-SHIFT COST: {r_s - r_g:+.4f} degC RMSE "
          f"({100*(r_s-r_g)/r_g:+.1f}% vs the GLORYS ceiling)")
    print("  Everything above is scored against a DIFFERENT INSTRUMENT than the model ever saw.")


if __name__ == "__main__":
    main()
