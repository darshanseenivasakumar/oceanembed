"""What the pressure-to-depth fix (audit #8) changed in the Argo truth table, level by level.

Compares the regenerated artifacts/argo_daily_period.parquet against the preserved pre-fix copy
argo_daily_period_pres_as_depth_v1.parquet on the profiles the two share.

TWO EFFECTS ARE BUNDLED IN A NAIVE DIFF, AND THIS SEPARATES THEM
  1. the axis fix   -- every level now samples the float at its true depth, ~1% deeper than before
  2. upstream drift -- a re-fetch can return reprocessed (delayed-mode) values for the same float
The axis error at the surface levels is negligible (0.03 m at 5 m, 0.06 m at 10 m), so on shared
profiles the 0/5/10 m disagreement is drift ALONE. If that is ~zero, the deeper disagreement is
the axis fix alone. If it is not, the deeper numbers are a mixture and are labelled as such.

Also reports how many profiles gained or lost a level -- the 1000 m level in particular, because
a float that stopped at 1003 dbar used to be read as reaching 1003 m and now reaches only ~995 m.

Run:  PYTHONPATH=src python scripts/phase2/argo_axis_fix_delta.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

from oceanembed import config
from phase2.data.argo_depth import pressure_read_as_depth_error_m

NEW = config.art("argo_daily_period.parquet")
OLD = config.art("argo_daily_period_pres_as_depth_v1.parquet")
OUT = config.art("argo_axis_fix_delta.json")
KEY = ["lat", "lon", "date"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    for p in (NEW, OLD):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    new, old = pd.read_parquet(NEW), pd.read_parquet(OLD)
    for d in (new, old):
        d["date"] = pd.to_datetime(d["date"])
        d["depth_idx"] = d["depth_idx"].astype(int)

    n_new = new.groupby(KEY).ngroups
    n_old = old.groupby(KEY).ngroups
    m = new.merge(old, on=KEY + ["depth_idx"], how="outer", suffixes=("_new", "_old"),
                  indicator=True)
    shared_prof = m[m["_merge"] == "both"].groupby(KEY).ngroups
    print(f"profiles: old {n_old}  new {n_new}  shared (by lat,lon,date) "
          f"{new.merge(old[KEY].drop_duplicates(), on=KEY).groupby(KEY).ngroups}")

    both = m[m["_merge"] == "both"].copy()
    both["d"] = both["temp_new"] - both["temp_old"]
    lat_mid = float(both["lat"].median())
    axis_err = pressure_read_as_depth_error_m(config.DEPTHS, lat_mid)

    print(f"\n{'level':>6} {'n both':>7} {'only new':>9} {'only old':>9} {'mean dT':>9} "
          f"{'RMS dT':>8} {'|dT|>0.1':>9}   axis shift (m, lat {lat_mid:.1f})")
    per_level = {}
    for di, dep in enumerate(config.DEPTHS):
        sub = both[both["depth_idx"] == di]["d"]
        only_new = int(((m["_merge"] == "left_only") & (m["depth_idx"] == di)).sum())
        only_old = int(((m["_merge"] == "right_only") & (m["depth_idx"] == di)).sum())
        rms = float(np.sqrt(np.mean(sub ** 2))) if len(sub) else float("nan")
        big = float((sub.abs() > 0.1).mean()) if len(sub) else float("nan")
        per_level[dep] = {"n_both": int(len(sub)), "only_new": only_new, "only_old": only_old,
                          "mean_dT": float(sub.mean()) if len(sub) else None, "rms_dT": rms,
                          "frac_abs_gt_0p1": big, "axis_shift_m": float(axis_err[di])}
        print(f"{dep:>6} {len(sub):>7} {only_new:>9} {only_old:>9} {sub.mean():>+9.4f} "
              f"{rms:>8.4f} {big:>9.3f}   {axis_err[di]:.2f}")

    surface = both[both["depth_idx"].isin([0, 1, 2])]["d"]
    drift_rms = float(np.sqrt(np.mean(surface ** 2))) if len(surface) else float("nan")
    verdict = ("upstream drift is negligible at the surface levels, so the deeper disagreement "
               "is the axis fix alone" if drift_rms < 0.005 else
               "the surface levels disagree, so the re-fetch also changed the data itself; "
               "deeper numbers mix drift with the axis fix and must be quoted as such")
    print(f"\nsurface-level (0/5/10 m) RMS disagreement on shared profiles: {drift_rms:.5f} degC")
    print(f"-> {verdict}")

    thousand = per_level[1000]
    print(f"\n1000 m: {thousand['only_old']} comparisons existed only under the old axis "
          f"(floats that reached 1000 dbar but not 1000 m); {thousand['only_new']} exist only "
          f"under the new one")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"what": __doc__.strip().splitlines()[0], "new": os.path.basename(NEW),
                   "old": os.path.basename(OLD), "profiles_old": n_old, "profiles_new": n_new,
                   "profiles_shared": shared_prof, "lat_median": lat_mid,
                   "surface_drift_rms_degC": drift_rms, "verdict": verdict,
                   "per_level": per_level}, f, indent=1)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
