"""How far is our TRAINING TRUTH from reality? GLORYS reanalysis vs independent Argo floats.

    python scripts/phase2/glorys_vs_argo.py

Why this exists
---------------
Our model is trained on GLORYS. A model cannot be more right than what it was taught, so before
blaming the model for its thermocline error we have to ask how good the teacher is. Nobody had
measured that: `artifacts/argo_error_by_depth.json` contains `rmse_glorys`, but that is OUR MODEL
FED GLORYS INPUTS -- not the GLORYS reanalysis itself. This script measures the reanalysis directly
against real floats.

Honesty notes baked in
----------------------
- Argo is independent: never used for training, so this is a fair test of GLORYS.
- Cells are skipped where `valid_mask` says the sea floor is shallower than the level, so we never
  compare against a value under the sea bed.
- A float is never exactly on a grid cell at exactly the grid time, so SOME disagreement is
  collocation mismatch rather than reanalysis error. The script reports a TIGHT subset alongside
  the full set, and reports the distance and time halves SEPARATELY: what survives is the real
  error. Do not lump them -- see the note on TIGHT_KM for why that hid a dead filter.
- The default filter matches the <= 5-day offset used by argo_error_by_depth.json so the numbers
  are comparable to the model's.

Writes artifacts/glorys_vs_argo.json for F8 to read.
"""
from __future__ import annotations

import json
import os
import sys
import warnings

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from oceanembed import config  # noqa: E402

# A 0.25 deg grid puts every point within 19.62 km of a cell centre (worst case, at 5N), and the
# real floats top out at 19.08 km. A 25 km "tight" threshold therefore excluded 0 of 2,455 profiles
# -- it was a no-op being reported as a filter, so the whole 0.02 C shrink came from the time half.
# Caught by Arjhun. 10 km actually bites (mean nearest-cell distance is 10.42 km), and the two
# effects are now reported separately so neither is credited with the other's work.
TIGHT_KM, TIGHT_DAYS = 10.0, 3


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlam = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def collect(max_days: int) -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(ROOT, "artifacts", "argo_test.parquet"))
    with np.load(os.path.join(ROOT, "data", "processed", "grids.npz"), allow_pickle=False) as z:
        temp, times, valid = z["temp"], z["times"].astype("datetime64[D]"), z["valid_mask"]

    rows = []
    for (lat, lon, when), grp in df.groupby(["lat", "lon", "date"], sort=False):
        i = int(np.argmin(np.abs(config.LAT - lat)))
        j = int(np.argmin(np.abs(config.LON - lon)))
        day = np.datetime64(pd.Timestamp(when).date(), "D")
        t = int(np.argmin(np.abs((times - day).astype("timedelta64[D]").astype(int))))
        off_d = int((day - times[t]).astype("timedelta64[D]").astype(int))
        if abs(off_d) > max_days:
            continue
        km = haversine_km(lat, lon, config.LAT[i], config.LON[j])
        for di, argo_t in zip(grp["depth_idx"].to_numpy(), grp["temp"].to_numpy()):
            di = int(di)
            if not valid[i, j, di]:          # sea floor is above this level -- not a real comparison
                continue
            g = temp[t, i, j, di]
            if np.isnan(g) or np.isnan(argo_t):
                continue
            rows.append((di, float(argo_t - g), float(km), abs(off_d)))
    return pd.DataFrame(rows, columns=["depth_idx", "diff", "km", "days"])


def summarise(sub: pd.DataFrame) -> dict:
    out = {}
    for di, grp in sub.groupby("depth_idx"):
        out[int(config.DEPTHS[di])] = {
            "n": int(len(grp)),
            "bias": round(float(grp["diff"].mean()), 3),
            "mean_abs": round(float(grp["diff"].abs().mean()), 3),
            "rmse": round(float(np.sqrt((grp["diff"] ** 2).mean())), 3),
        }
    return out


def show(title: str, table: dict) -> None:
    print(f"\n--- {title} ---")
    print(f"{'depth':>7} {'n':>6} {'bias':>8} {'mean_abs':>9} {'rmse':>7}")
    for d, s in table.items():
        print(f"{d:>7} {s['n']:>6} {s['bias']:>+8.2f} {s['mean_abs']:>9.2f} {s['rmse']:>7.2f}")


def main() -> None:
    model = json.load(open(os.path.join(ROOT, "artifacts", "argo_error_by_depth.json")))
    max_days = model["max_days_offset"]

    print("=" * 74)
    print("GLORYS reanalysis vs INDEPENDENT Argo floats")
    print("=" * 74)
    print(f"matching the model table's filter: offset <= {max_days} days")

    r = collect(max_days)
    allt = summarise(r)
    near = summarise(r[r.km <= TIGHT_KM])
    soon = summarise(r[r.days <= TIGHT_DAYS])
    tight = summarise(r[(r.km <= TIGHT_KM) & (r.days <= TIGHT_DAYS)])
    show(f"ALL matches (n={len(r)})", allt)
    show(f"TIGHT: <= {TIGHT_KM:.0f} km AND <= {TIGHT_DAYS} days", tight)

    worst = max(allt, key=lambda d: allt[d]["mean_abs"])
    deep = float(np.mean([allt[d]["mean_abs"] for d in allt if d >= 500]))
    print(f"\nworst disagreement : {allt[worst]['mean_abs']:.2f} C at {worst} m")
    print(f"deep (>=500 m)     : {deep:.2f} C mean absolute")

    # Decompose it. Crediting "collocation" as one lump hid that the distance half was doing
    # nothing at all, so the time half was silently taking all the credit.
    base = allt[worst]["mean_abs"]
    print(f"\nwhat the {worst} m gap is made of, mean absolute:")
    for label, tbl, n in (("all matches", allt, len(r)),
                          (f"distance <= {TIGHT_KM:.0f} km", near, int((r.km <= TIGHT_KM).sum())),
                          (f"time <= {TIGHT_DAYS} days", soon, int((r.days <= TIGHT_DAYS).sum())),
                          ("both", tight, int(((r.km <= TIGHT_KM) & (r.days <= TIGHT_DAYS)).sum()))):
        if worst in tbl:
            v = tbl[worst]["mean_abs"]
            print(f"  {label:<22} {v:.2f} C   ({v - base:+.2f} vs all, n={n})")
    if worst in tight:
        print(f"-> {tight[worst]['mean_abs']:.2f} C survives the tightest matching, so most of the "
              f"{base:.2f} C is REANALYSIS ERROR, not collocation mismatch")

    print("\n" + "=" * 74)
    print("OUR MODEL (satellite-driven) vs THE REANALYSIS ITSELF, same floats")
    print("=" * 74)
    # A bare threshold on two rounded RMSEs is not a comparison -- at 100 m and 125 m the gap is
    # identical to the eye, and any fixed cutoff labels them differently for no real reason. So
    # bootstrap a 95% interval on the reanalysis RMSE and only claim a difference when our number
    # falls outside it. Anything inside is INDISTINGUISHABLE and must be reported as such.
    rng = np.random.default_rng(config.SEED)
    print(f"{'depth':>7} {'ours':>7} {'GLORYS':>7} {'95% CI':>14} {'clim':>6} {'skill':>7}  verdict")
    comp = {}
    for k, dep in enumerate(model["depths"]):
        ours = model["rmse_satellite"][k]
        clim = model["rmse_climatology"][k]
        di = config.DEPTHS.index(dep)
        d = r.loc[r.depth_idx == di, "diff"].to_numpy()
        if len(d) < 30:
            print(f"{dep:>7} {ours:>7.2f} {'n/a':>7} {'too few floats':>14} {clim:>6.2f} "
                  f"{1 - ours / clim:>+7.3f}  not enough data")
            continue
        boot = np.sqrt((rng.choice(d, (2000, len(d)), replace=True) ** 2).mean(axis=1))
        lo, hi = np.percentile(boot, [2.5, 97.5])
        g = float(np.sqrt((d ** 2).mean()))
        verdict = ("we are BETTER" if ours < lo else
                   "we add error" if ours > hi else "indistinguishable")
        comp[dep] = {"ours": ours, "glorys_reanalysis": round(g, 3),
                     "glorys_ci95": [round(float(lo), 3), round(float(hi), 3)],
                     "clim": clim, "skill_vs_clim": round(1 - ours / clim, 3),
                     "verdict": verdict, "n": int(len(d))}
        print(f"{dep:>7} {ours:>7.2f} {g:>7.2f} {f'[{lo:.2f},{hi:.2f}]':>14} {clim:>6.2f} "
              f"{1 - ours / clim:>+7.3f}  {verdict}")

    n_worse = sum(1 for v in comp.values() if v["verdict"] == "we add error")
    n_same = sum(1 for v in comp.values() if v["verdict"] == "indistinguishable")
    n_better = sum(1 for v in comp.values() if v["verdict"] == "we are BETTER")
    print(f"\nvs the reanalysis: {n_better} depths better, {n_same} indistinguishable, "
          f"{n_worse} worse (of {len(comp)})")

    out = {
        "what_this_is": "GLORYS reanalysis measured against independent Argo floats",
        "not_to_be_confused_with": ("argo_error_by_depth.json rmse_glorys, which is OUR MODEL fed "
                                    "GLORYS inputs -- not the reanalysis itself"),
        "max_days_offset": max_days,
        "tight_definition": {"max_km": TIGHT_KM, "max_days": TIGHT_DAYS},
        "why_not_25km": ("A 25 km threshold excludes 0 of 2,455 profiles on a 0.25 deg grid, whose "
                         "worst-case nearest-cell distance is 19.62 km. Any claim that 'tightening "
                         "to <=25 km changed X' is false -- that filter never bound."),
        "by_depth_near_only": near,
        "by_depth_soon_only": soon,
        "n_comparisons": int(len(r)),
        "by_depth_all": allt,
        "by_depth_tight": tight,
        "model_vs_reanalysis": comp,
        "caveat": ("A float is never exactly on a grid cell at the grid time, so part of every gap "
                   "is collocation mismatch. The TIGHT table is the honest lower bound."),
        "caveat_statistical": (
            "The 95% interval is bootstrapped on the REANALYSIS RMSE only; our model's RMSE is "
            "treated as a fixed stored number because per-profile model residuals are not saved. "
            "A fully paired test would widen the intervals, which would move verdicts TOWARD "
            "'indistinguishable', never away from it. So the large-margin 'we add error' verdicts "
            "at 20-75 m are safe, while the marginal ones (300 m) and the 1000 m 'better' verdict "
            "are the ones that might not survive a paired test. Say this if asked."),
    }
    p = os.path.join(ROOT, "artifacts", "glorys_vs_argo.json")
    json.dump(out, open(p, "w"), indent=2)
    print(f"\nwrote {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    main()
