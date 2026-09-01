"""Verify Darshan's DAILY bundle before anything trains on it.

Refuses rather than warns. A bundle that is subtly wrong -- extrapolated deep levels, a forecast
product silently mixed into a reanalysis archive, temperatures in Kelvin -- trains cleanly and
produces confident numbers that are wrong, which is the failure mode this project has hit before.

THE CHECK THAT MATTERS MOST is the depth bracket. GLORYS depth levels are discrete:

    ..., 453.9, 541.1, 643.6, 763.3, 902.3, 1062.4, ...

A download capped at 520 m stops at 453.9 m, and every 500/700/1000 m value in the contract then
comes from EXTRAPOLATION past the last real level. It looks like data. It trains. It is fabricated.
That already bit this project once (src/oceanembed/data/download_glorys.py documents it), so the
deepest level present must be BELOW the deepest contract depth, not merely near it.

Usage:
    PYTHONPATH=src python scripts/phase2/verify_daily_bundle.py [--dir data/raw/daily] [--full]

    --full  open every file rather than a sample (slow; do this once before training).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

try:
    import xarray as xr
except ImportError:  # pragma: no cover
    sys.exit("xarray is required: pip install xarray netcdf4")

from oceanembed import config

# What the contract requires. Imported, never hardcoded.
DEPTHS = list(config.DEPTHS)
REGION = config.REGION
EXPECTED_VARS = {"thetao", "so", "zos", "uo", "vo"}

# Physical sanity bounds for the North Indian Ocean.
# Bounds set from what the REGION actually does, verified against the real bundle at BOTH ends.
# The Persian Gulf -- shallow, semi-enclosed, and inside our 45-105 E box -- sets both extremes:
#   ceiling  36.34 degC at 24.08N 53.58E on 2025-08-04 (southern Gulf, late summer)
#   floor    13.34 degC at 29.75N 48.33E on 2026-01-17 (head of the Gulf, mid-winter)
# On that same January day the open Arabian Sea held 24.4 degC. Bounds tuned to the open ocean
# clip the marginal seas for being exactly what they are, so these are set wide enough to admit
# the Gulf and no wider.
# Kelvin still fails loudly: it reads ~270-310 across the WHOLE field, not 13 in one basin.
SST_MIN, SST_MAX = 11.0, 38.0
DEEP_MIN, DEEP_MAX = 1.0, 20.0         # degC at 1000 m


class Result:
    def __init__(self) -> None:
        self.checks: list[tuple[bool, str, str]] = []

    def add(self, ok: bool, name: str, detail: str = "") -> bool:
        self.checks.append((bool(ok), name, detail))
        return bool(ok)

    def report(self, title: str) -> bool:
        print(f"\n{title}")
        print("-" * len(title))
        for ok, name, detail in self.checks:
            print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
            if detail:
                for line in detail.splitlines():
                    print(f"          {line}")
        return all(ok for ok, _, _ in self.checks)


def _depth_name(ds) -> str | None:
    for c in ("depth", "deptht", "lev", "z"):
        if c in ds.coords or c in ds.dims:
            return c
    return None


def _coord(ds, *names):
    for n in names:
        if n in ds.coords:
            return ds[n]
    return None


def check_files(directory: str, r: Result) -> list[str]:
    files = sorted(glob.glob(os.path.join(directory, "*.nc")))
    r.add(bool(files), f"{len(files)} NetCDF files found in {directory}")
    if not files:
        return files

    sizes = [os.path.getsize(f) for f in files]
    tiny = [os.path.basename(f) for f, s in zip(files, sizes) if s < 100_000]
    r.add(not tiny, "no truncated/empty files",
          f"suspiciously small: {tiny[:6]}" if tiny else "")
    r.add(True, f"total size {sum(sizes)/1e9:.2f} GB")

    # Dates parsed from filenames, then checked for gaps. A missing day that nobody notices
    # becomes a silent discontinuity the model learns straight through.
    import re
    dates = sorted({m.group(0) for f in files
                    if (m := re.search(r"\d{8}", os.path.basename(f)))})
    if dates:
        d = np.array([np.datetime64(f"{s[:4]}-{s[4:6]}-{s[6:]}") for s in dates])
        gaps = np.diff(d).astype("timedelta64[D]").astype(int)
        missing = int((gaps - 1).clip(min=0).sum())
        r.add(missing == 0, f"date range {d[0]} .. {d[-1]}, {len(d)} unique dates",
              f"{missing} MISSING DAYS inside the range" if missing else "contiguous, no gaps")
    return files


def check_one_file(path: str, r: Result, *, deep_check: bool = True) -> None:
    with xr.open_dataset(path) as ds:
        name = os.path.basename(path)

        have = set(ds.data_vars)
        missing = EXPECTED_VARS - have
        r.add(not missing, f"[{name}] variables present",
              f"missing {sorted(missing)}; has {sorted(have)}" if missing else
              f"{sorted(have & EXPECTED_VARS)}")

        # ---- THE DEPTH BRACKET -------------------------------------------------------------
        dname = _depth_name(ds)
        if dname is None:
            r.add(False, f"[{name}] depth coordinate found", "no depth/deptht/lev/z coordinate")
        else:
            levels = np.asarray(ds[dname].values, dtype="float64")
            deepest = float(levels.max())
            target = float(max(DEPTHS))
            ok = deepest >= target
            r.add(ok, f"[{name}] deepest level {deepest:.1f} m brackets the {target:.0f} m target",
                  f"deepest available level is {deepest:.1f} m, which is ABOVE the {target:.0f} m "
                  f"contract depth. Every value at {target:.0f} m would be EXTRAPOLATED past the "
                  f"last real measurement, not interpolated between two. Re-download with "
                  f"maximum_depth=1100."
                  if not ok else
                  f"levels near the bottom: {np.round(levels[levels > 400], 1).tolist()[:6]}")

            if deep_check and ok:
                # Two real levels must straddle 1000 m, not just one below it.
                below = levels[levels <= target]
                above = levels[levels >= target]
                r.add(below.size > 0 and above.size > 0,
                      f"[{name}] {target:.0f} m sits between real levels "
                      f"{below.max():.1f} and {above.min():.1f} m")

        # ---- values ------------------------------------------------------------------------
        if "thetao" in ds:
            t = ds["thetao"]
            surf = t.isel({dname: 0}, drop=True) if dname else t
            sv = np.asarray(surf.values, dtype="float64").ravel()
            sv = sv[np.isfinite(sv)]
            if sv.size:
                lo, hi = float(sv.min()), float(sv.max())
                r.add(SST_MIN <= lo and hi <= SST_MAX,
                      f"[{name}] SST {lo:.1f}..{hi:.1f} degC",
                      "" if SST_MIN <= lo and hi <= SST_MAX else
                      f"outside {SST_MIN}..{SST_MAX} degC. A whole field at ~270-310 means KELVIN, which "
                      f"would train fine and be wrong by 273 everywhere. A single "
                      f"basin above 36 is more likely the Persian Gulf in August.")

            r.add(np.isfinite(sv).mean() if sv.size else 0 > 0,
                  f"[{name}] surface field is not all-NaN")

            # Temperature must fall with depth in the mean. If it rises, depths are reversed --
            # a bug that trains perfectly well and inverts the entire water column.
            if dname:
                prof = t.mean(dim=[d for d in t.dims if d != dname], skipna=True)
                pv = np.asarray(prof.values, dtype="float64")
                lv = np.asarray(ds[dname].values, dtype="float64")
                order = np.argsort(lv)
                pv, lv = pv[order], lv[order]
                ok_pv = np.isfinite(pv)
                if ok_pv.sum() >= 3:
                    top, bot = float(pv[ok_pv][0]), float(pv[ok_pv][-1])
                    r.add(top > bot + 5.0,
                          f"[{name}] mean profile falls {top:.1f} -> {bot:.1f} degC with depth",
                          "" if top > bot + 5.0 else
                          "temperature does not decrease with depth. Depth axis may be REVERSED.")

                    deep = pv[ok_pv & (lv >= 900)]
                    if deep.size:
                        r.add(DEEP_MIN <= float(deep[-1]) <= DEEP_MAX,
                              f"[{name}] deepest mean {float(deep[-1]):.2f} degC is physical")

        # ---- provenance: reanalysis vs forecast --------------------------------------------
        # NOT a substring scan: "reanalysis" CONTAINS "analysis", so a naive match flags every
        # legitimate file. GLORYS ships a boilerplate title ("... Analysis and Forecast ...") on
        # reanalysis output, so `source` is what actually identifies the product.
        src = str(ds.attrs.get("source", "")).lower()
        title = str(ds.attrs.get("title", "")).lower()
        if src:
            ok = "glorys" in src or "reanalysis" in src
            r.add(ok, f"[{name}] source is a reanalysis product",
                  f"source={src!r}, title={title!r} -- if this is an analysis/forecast product "
                  f"rather than GLORYS reanalysis, it must not be mixed into this archive."
                  if not ok else f"source={src!r}")
        else:
            r.add(False, f"[{name}] source attribute present",
                  "no `source` global attribute -- cannot confirm this is reanalysis")

        # The internal time coordinate must match the filename. Mercator's field_date/bulletin_date
        # attributes are stale template values (field_date 2021-06-30 on a 2025-06-01 file), so
        # they prove nothing either way -- the coordinate is what the data is indexed by.
        if "time" in ds.coords:
            import re as _re
            m = _re.search(r"(\d{8})", name)
            if m:
                t = str(np.asarray(ds["time"].values).ravel()[0])[:10].replace("-", "")
                r.add(t == m.group(1),
                      f"[{name}] internal time {t} matches the filename",
                      "" if t == m.group(1) else
                      f"file is named {m.group(1)} but its data is indexed {t}. A silent offset "
                      f"like this trains cleanly and is wrong by that interval everywhere.")

def check_grid(path: str, r: Result) -> None:
    with xr.open_dataset(path) as ds:
        lat = _coord(ds, "latitude", "lat", "nav_lat")
        lon = _coord(ds, "longitude", "lon", "nav_lon")
        if lat is None or lon is None:
            r.add(False, "lat/lon coordinates present")
            return
        la = np.asarray(lat.values, dtype="float64").ravel()
        lo = np.asarray(lon.values, dtype="float64").ravel()
        r.add(la.min() <= REGION["lat_min"] + 0.3 and la.max() >= REGION["lat_max"] - 0.3,
              f"latitude {la.min():.2f}..{la.max():.2f} covers "
              f"{REGION['lat_min']}..{REGION['lat_max']} N")
        r.add(lo.min() <= REGION["lon_min"] + 0.3 and lo.max() >= REGION["lon_max"] - 0.3,
              f"longitude {lo.min():.2f}..{lo.max():.2f} covers "
              f"{REGION['lon_min']}..{REGION['lon_max']} E")
        if la.size > 1:
            step = float(np.abs(np.diff(np.unique(la))).min())
            need = float(REGION["step"])
            # At or finer than the contract is fine -- 1/12 deg native and an already-regridded
            # 0.25 deg bundle are both usable. COARSER is the defect: regridding up to 0.25 deg
            # would manufacture structure that was never measured.
            r.add(step <= need + 1e-6, f"native step {step:.4f} deg is not coarser than the "
                                       f"{need} deg contract",
                  "" if step <= need + 1e-6 else
                  f"{step:.4f} deg is COARSER than the {need} deg we reconstruct at -- regridding "
                  f"would INVENT detail that was never in the source")


def main() -> None:
    ap = argparse.ArgumentParser()
    # data/raw/daily has never existed on this project; the GLORYS files land in
    # data/raw/glorys_daily. daily_pipeline.py fixed this same stale default on its own side and
    # not here, so the verifier's no-argument form failed on a missing directory.
    ap.add_argument("--dir", default=os.path.join("data", "raw", "glorys_daily"))
    ap.add_argument("--full", action="store_true",
                    help="open every file, not a sample. Slow; run once before training.")
    a = ap.parse_args()

    r = Result()
    print(f"verifying daily bundle in {a.dir}")
    files = check_files(a.dir, r)
    if not files:
        r.report("VERDICT")
        sys.exit("no files -- nothing to verify")

    sample = files if a.full else [files[0], files[len(files) // 2], files[-1]]
    print(f"opening {len(sample)} of {len(files)} files"
          f"{' (--full)' if a.full else ' (first/middle/last; use --full for all)'}")
    for i, f in enumerate(sample):
        check_one_file(f, r, deep_check=True)
    check_grid(sample[0], r)

    ok = r.report("VERDICT")
    print()
    if ok:
        print("ACCEPTED -- files, contract and science all pass. Safe to preprocess.")
    else:
        print("REJECTED -- do NOT train on this bundle. A wrong bundle trains cleanly and")
        print("            produces confident numbers that are wrong; that is the whole point")
        print("            of checking before rather than after.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
