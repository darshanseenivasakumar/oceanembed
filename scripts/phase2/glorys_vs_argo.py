"""How good is our TRAINING TRUTH? GLORYS reanalysis vs independent Argo floats.

OWNER: Unit A (Arjhun). PHASE-2. Reads baseline artifacts; modifies nothing.

WHY THIS EXISTS
Everything else in this repo measures OUR MODEL against something. `eval_satellite_vs_argo.py`
scores the model driven by satellite and the model driven by GLORYS. Nothing has ever scored
**GLORYS itself** against an independent instrument -- and GLORYS is what we trained on.

That matters for one reason: a model cannot be more accurate than the truth it was fit to. If the
reanalysis is off by X at some depth, our error at that depth is largely inherited rather than
earned, and the honest claim is "we have reached the ceiling of our training truth", not "our model
is weak here". This script measures X.

It is deliberately model-free. No checkpoint is loaded. The comparison is:

    grids.npz["temp"]  (GLORYS reanalysis, regridded to our grid/depths)   vs   Argo float profiles

REGRIDDING IS INCLUDED ON PURPOSE
`temp` is GLORYS after interpolation onto the frozen 0.25 deg grid and our 15 depth levels. That
interpolation is part of the error, and it is the error our model actually inherited, so it belongs
in the number. This measures "the reanalysis AS WE USE IT", which is the relevant quantity. It is
therefore an upper bound on the native product's own error -- said here so the number is not quoted
as a verdict on GLORYS itself.

MATCHING
Same >=5-day tolerance as the Phase-1 evaluation, so the numbers sit next to
`argo_error_by_depth.json` without a hidden methodology change. A tightened pass
(<=3 days, <=25 km) reports how much of the gap is collocation mismatch rather than real error.

Run:  python scripts/phase2/glorys_vs_argo.py
Out:  artifacts/glorys_vs_argo.json
"""
from __future__ import annotations

import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from oceanembed import config  # noqa: E402
from oceanembed.utils import io  # noqa: E402

MAX_DAYS = 5           # matches scripts/eval_satellite_vs_argo.py, deliberately
TIGHT_DAYS = 3
TIGHT_KM = 25.0
EARTH_RADIUS_KM = 6371.0

OUT = config.art("glorys_vs_argo") if hasattr(config, "art") else os.path.join(
    config.ARTIFACTS, "glorys_vs_argo.json")
if not str(OUT).endswith(".json"):
    OUT = os.path.join(config.ARTIFACTS, "glorys_vs_argo.json")


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def _profiles() -> list[tuple[float, float, pd.Timestamp, np.ndarray]]:
    """Argo as (lat, lon, date, temps[15]) with NaN where that depth was not sampled.

    Same grouping as the Phase-1 script, so the profile set is identical.
    """
    df = io.load_table(config.art("argo_test"))
    df["date"] = pd.to_datetime(df["date"])
    out = []
    for (la, lo, dt), grp in df.groupby(["lat", "lon", "date"]):
        t = np.full(config.N_DEPTHS, np.nan, dtype="float64")
        t[grp["depth_idx"].to_numpy()] = grp["temp"].to_numpy()
        out.append((float(la), float(lo), pd.Timestamp(dt), t))
    return out


def collect() -> dict:
    """Pair every Argo profile with the GLORYS column at the nearest cell and date."""
    g = np.load(os.path.join(config.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    temp = np.asarray(g["temp"], dtype="float64")            # (T, lat, lon, depth)
    times = np.asarray(g["times"]).astype("datetime64[D]")
    land = np.asarray(g["land_mask"], dtype=bool)
    valid = np.asarray(g["valid_mask"], dtype=bool)          # (lat, lon, depth) bathymetry
    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")

    profs = _profiles()
    argo, glo, days, dist, n_land, n_far = [], [], [], [], 0, 0

    for la, lo, dt, t_argo in profs:
        d = np.datetime64(dt.date(), "D")
        gaps = np.abs((times - d).astype("timedelta64[D]").astype(int))
        k = int(np.argmin(gaps))
        if gaps[k] > MAX_DAYS:
            n_far += 1
            continue

        i = int(np.argmin(np.abs(lat - la)))
        j = int(np.argmin(np.abs(lon - lo)))
        if land[i, j]:
            n_land += 1
            continue

        col = temp[k, i, j, :].copy()
        # Bathymetry: never compare against water the sea floor says is not there. 24% of ocean
        # cells are shallower than 1000 m, and Phase 1's shelf bug was exactly this.
        col[~valid[i, j, :]] = np.nan

        argo.append(t_argo)
        glo.append(col)
        days.append(int(gaps[k]))
        dist.append(float(_haversine_km(la, lo, lat[i], lon[j])))

    return {
        "argo": np.asarray(argo), "glorys": np.asarray(glo),
        "days": np.asarray(days), "dist_km": np.asarray(dist),
        "n_profiles_total": len(profs), "n_matched": len(argo),
        "n_dropped_land": n_land, "n_dropped_far_in_time": n_far,
    }


def stats(argo: np.ndarray, glo: np.ndarray) -> dict:
    """Per-depth error of the reanalysis against the floats.

    bias = argo - glorys. NEGATIVE bias means the FLOATS ARE COLDER than the reanalysis,
    i.e. the reanalysis is warm-biased there. Spelled out because a sign error here would
    invert the finding.
    """
    e = argo - glo
    m = np.isfinite(e)
    per = {"mae": [], "rmse": [], "bias": [], "n": []}
    for k in range(config.N_DEPTHS):
        sel = m[:, k]
        if sel.sum() < 5:
            for key in ("mae", "rmse", "bias"):
                per[key].append(None)
            per["n"].append(int(sel.sum()))
            continue
        ek = e[sel, k]
        per["mae"].append(round(float(np.mean(np.abs(ek))), 4))
        per["rmse"].append(round(float(np.sqrt(np.mean(ek ** 2))), 4))
        per["bias"].append(round(float(np.mean(ek)), 4))
        per["n"].append(int(sel.sum()))
    per["overall_mae"] = round(float(np.mean(np.abs(e[m]))), 4)
    per["overall_rmse"] = round(float(np.sqrt(np.mean(e[m] ** 2))), 4)
    per["n_comparisons"] = int(m.sum())
    return per


def main() -> None:
    c = collect()
    base = stats(c["argo"], c["glorys"])

    tight = c["dist_km"] <= TIGHT_KM
    tight_t = c["days"] <= TIGHT_DAYS
    both = tight & tight_t

    out = {
        "what_this_measures": (
            "GLORYS reanalysis (regridded to the frozen 0.25deg grid and 15 depth levels) "
            "against independent Argo floats. NO MODEL IS INVOLVED. This is the accuracy of our "
            "TRAINING TRUTH, so it is the ceiling on what any model fit to it can achieve."
        ),
        "not_to_be_confused_with": (
            "artifacts/argo_error_by_depth.json -> 'rmse_glorys', which is OUR MODEL FED GLORYS "
            "SURFACE INPUTS. That is a model score. This file is the reanalysis itself."
        ),
        "bias_convention": "bias = argo - glorys; NEGATIVE means the floats are COLDER than the "
                           "reanalysis (reanalysis warm-biased)",
        "includes_regridding_error": True,
        "depths": list(config.DEPTHS),
        "max_days_offset": MAX_DAYS,
        "n_profiles_total": c["n_profiles_total"],
        "n_matched": c["n_matched"],
        "n_dropped_far_in_time": c["n_dropped_far_in_time"],
        "n_dropped_land": c["n_dropped_land"],
        "collocation_distance_km": {
            "max": round(float(c["dist_km"].max()), 3),
            "mean": round(float(c["dist_km"].mean()), 3),
            "p95": round(float(np.percentile(c["dist_km"], 95)), 3),
        },
        "baseline": base,
        "tightened": {
            "note": (f"<= {TIGHT_DAYS} days AND <= {TIGHT_KM} km. Reported to separate real "
                     "reanalysis error from collocation mismatch."),
            "n_profiles": int(both.sum()),
            "stats": stats(c["argo"][both], c["glorys"][both]) if both.sum() > 20 else None,
        },
        "tightened_time_only": {
            "note": f"<= {TIGHT_DAYS} days, distance unrestricted",
            "n_profiles": int(tight_t.sum()),
            "stats": stats(c["argo"][tight_t], c["glorys"][tight_t]) if tight_t.sum() > 20 else None,
        },
        "tightened_distance_only": {
            "note": f"<= {TIGHT_KM} km, time unrestricted (within the {MAX_DAYS}-day window)",
            "n_profiles": int(tight.sum()),
            "stats": stats(c["argo"][tight], c["glorys"][tight]) if tight.sum() > 20 else None,
        },
    }

    # ---- COMPATIBILITY: Unit B's F1 page reads this same file --------------------------
    # `app/phase2/collocation_page.py` consumes `by_depth_all` (keyed by depth, with `mean_abs`)
    # and `n_comparisons`. Unit B wrote an independent version of this script with that schema;
    # at merge we agreed to keep THIS one, and regenerating the artifact promptly broke his page
    # with KeyError: 'by_depth_all'.
    #
    # His page is his file and I do not edit it, so the fix belongs here: emit BOTH shapes from
    # the ONE measurement. Same numbers, two spellings -- which is the point. Two files computing
    # one number is the D-014 failure; one file serving two consumers is not.
    out["by_depth_all"] = {
        str(z): {"n": base["n"][k],
                 "bias": base["bias"][k],
                 "mean_abs": base["mae"][k],
                 "rmse": base["rmse"][k]}
        for k, z in enumerate(config.DEPTHS)
        if base["mae"][k] is not None
    }
    out["n_comparisons"] = base["n_comparisons"]
    tight_stats = out["tightened"]["stats"]
    if tight_stats is not None:
        out["by_depth_tight"] = {
            str(z): {"n": tight_stats["n"][k],
                     "bias": tight_stats["bias"][k],
                     "mean_abs": tight_stats["mae"][k],
                     "rmse": tight_stats["rmse"][k]}
            for k, z in enumerate(config.DEPTHS)
            if tight_stats["mae"][k] is not None
        }
    out["tight_definition"] = {"max_km": TIGHT_KM, "max_days": TIGHT_DAYS}

    os.makedirs(config.ARTIFACTS, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)

    # ---- report -------------------------------------------------------------------------
    print("=" * 74)
    print("GLORYS REANALYSIS vs INDEPENDENT ARGO  -- no model involved")
    print("=" * 74)
    print(f"  {c['n_matched']} profiles matched of {c['n_profiles_total']} "
          f"({c['n_dropped_far_in_time']} outside {MAX_DAYS} days, {c['n_dropped_land']} on land)")
    print(f"  {base['n_comparisons']} depth comparisons")
    print(f"  collocation distance: mean {out['collocation_distance_km']['mean']:.1f} km, "
          f"max {out['collocation_distance_km']['max']:.1f} km")
    print(f"\n  {'depth':>6} {'MAE':>8} {'RMSE':>8} {'bias':>8} {'n':>7}   "
          f"(bias<0 = floats colder than reanalysis)")
    for k, z in enumerate(config.DEPTHS):
        mae, rmse, bias, n = (base["mae"][k], base["rmse"][k], base["bias"][k], base["n"][k])
        if mae is None:
            print(f"  {z:>6} {'--':>8} {'--':>8} {'--':>8} {n:>7}")
            continue
        flag = "  <-- worst" if mae == max(x for x in base["mae"] if x is not None) else ""
        print(f"  {z:>6} {mae:8.3f} {rmse:8.3f} {bias:+8.3f} {n:>7}{flag}")
    print(f"\n  overall MAE {base['overall_mae']:.4f}   RMSE {base['overall_rmse']:.4f}")

    print("\n  Does tightening the collocation close the gap?")
    for key in ("tightened_time_only", "tightened_distance_only", "tightened"):
        s = out[key]["stats"]
        if s is None:
            print(f"    {key:26s} too few profiles")
            continue
        k100 = config.DEPTHS.index(100)
        print(f"    {key:26s} n={out[key]['n_profiles']:5d}  "
              f"100 m MAE {s['mae'][k100]:.3f}  (baseline {base['mae'][k100]:.3f}, "
              f"delta {s['mae'][k100] - base['mae'][k100]:+.3f})")
    print(f"\n  wrote {OUT}")


if __name__ == "__main__":
    main()
