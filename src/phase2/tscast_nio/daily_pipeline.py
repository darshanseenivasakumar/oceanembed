"""Build the daily bundle of tscast_data_model.md section 2 from Darshan's raw GLORYS files.

REUSES `oceanembed.data.preprocess._process_one` for the surface fields and the temperature
target. That function already does the regrid to the frozen 0.25 deg grid, and it already RAISES
rather than extrapolating when a file does not reach the deepest contract depth -- the 520 m cap
bug. Writing a second regridder here is exactly the D-014 failure (two loaders that can disagree,
one z-scored, a silent 20x error), so this module orchestrates and does not reimplement.

Salinity is extracted separately, because `_process_one` returns temperature only. It is a STAGE-2
target, so a small divergence there cannot affect the stage-1 numbers -- and the surface/temperature
path, which is what stage 1 trains on, comes from the frozen code untouched.

Output: data/processed/daily/YYYY.npz, one file per calendar year.

Run:  PYTHONPATH=src python -m phase2.tscast_nio.daily_pipeline
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
from collections import defaultdict

import numpy as np
import xarray as xr

from oceanembed import config as base
from oceanembed.data import preprocess
from phase2.tscast_nio import config

# The monthly archive carries 5; the contract wants 7. Wind arrives separately (no daily L4 product
# covers 2025-26, so it must come hourly and be averaged). What we WRITE is what we HAVE, and the
# channel list travels with the data so nothing downstream can assume otherwise.
SURFACE_KEYS = ["sst", "sss", "ssh", "u", "v"]
SURFACE_UNITS = ["degC", "psu", "m", "m s-1", "m s-1"]


def _salinity_at_depths(path: str) -> np.ndarray:
    """(T, 100, 240, 15) salinity, regridded the same way preprocess does it."""
    with xr.open_dataset(path) as ds:
        latn = preprocess._find_coord(ds, "latitude", "lat", "nav_lat")
        lonn = preprocess._find_coord(ds, "longitude", "lon", "nav_lon")
        depthn = preprocess._find_coord(ds, "depth", "deptht", "lev")
        timen = preprocess._find_coord(ds, "time", "time_counter")
        ds = ds.sortby(latn).sortby(lonn).sortby(depthn)
        ds = ds.interp({latn: base.LAT, lonn: base.LON}, method="linear")
        d_max = float(ds[depthn].max())
        too_deep = [d for d in base.DEPTHS if d > d_max]
        if too_deep:
            raise ValueError(f"{os.path.basename(path)} reaches only {d_max:.1f} m; "
                             f"{too_deep} would be extrapolated")
        sal = ds["so"].interp({depthn: base.DEPTHS}, method="linear",
                              kwargs={"fill_value": "extrapolate"})
        return sal.transpose(timen, latn, lonn, depthn).values.astype("float32")


def build_year(files: list[str], year: int, out_dir: str, with_salinity: bool = True) -> str:
    n = len(files)
    nlat, nlon, nd = base.N_LAT, base.N_LON, base.N_DEPTHS
    times = np.empty(n, dtype="datetime64[D]")
    surface = np.full((n, nlat, nlon, len(SURFACE_KEYS)), np.nan, dtype="float32")
    temp = np.full((n, nlat, nlon, nd), np.nan, dtype="float32")
    salinity = np.full((n, nlat, nlon, nd), np.nan, dtype="float32") if with_salinity else None

    for k, f in enumerate(files):
        t, surf, tp = preprocess._process_one(f)      # frozen code: regrid + deep-extrap guard
        times[k] = np.asarray(t).ravel()[0]
        for c, name in enumerate(SURFACE_KEYS):
            surface[k, :, :, c] = surf[name][0]
        temp[k] = tp[0]
        if with_salinity:
            salinity[k] = _salinity_at_depths(f)[0]
        if (k + 1) % 25 == 0 or k == n - 1:
            print(f"  [{year}] {k + 1}/{n} {times[k]}", flush=True)

    order = np.argsort(times)
    times, surface, temp = times[order], surface[order], temp[order]
    if with_salinity:
        salinity = salinity[order]

    # Gaps are RECORDED, never interpolated and never silently dropped: a gap the model cannot see
    # is a gap it will learn straight through.
    full = np.arange(times[0], times[-1] + np.timedelta64(1, "D"), dtype="datetime64[D]")
    missing = np.setdiff1d(full, times)

    land_mask = ~np.isfinite(surface[:, :, :, 0]).any(axis=0)          # never any SST -> land
    valid_mask = np.isfinite(temp).all(axis=0)                          # bathymetry, time-invariant

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{year}.npz")
    payload = dict(
        times=times, surface=surface, temp=temp,
        channels=np.array(SURFACE_KEYS), units=np.array(SURFACE_UNITS),
        land_mask=land_mask, valid_mask=valid_mask, missing_days=missing,
        provenance=json.dumps({
            "source": "GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D-m)",
            "from": "Darshan's bundle, verified by scripts/phase2/verify_daily_bundle.py",
            "regrid": "oceanembed.data.preprocess._process_one -- reused, not reimplemented",
            "n_files": n, "year": year,
            "channels_note": "5 of the contract's 7; wind needs the hourly NRT product",
            "code_commit": _commit(),
        }),
    )
    if with_salinity:
        payload["salinity"] = salinity
    np.savez_compressed(path, **payload)

    print(f"  [{year}] wrote {path}  ({os.path.getsize(path)/1e9:.2f} GB)")
    # Coverage is reported over OCEAN cells, not all cells, so it is directly comparable with
    # the F2a OceanCube figure (~75.8% at 1000 m). Over all cells the same mask reads ~37%, which
    # looks like a regression and is not.
    ocean = ~land_mask
    cov1000 = float(valid_mask[:, :, -1][ocean].mean())
    print(f"        {n} days {times[0]}..{times[-1]}, {len(missing)} missing, "
          f"ocean {100*ocean.mean():.1f}% of grid, "
          f"1000 m coverage {100*cov1000:.1f}% of ocean cells")
    return path


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=os.path.join("data", "raw", "daily"))
    ap.add_argument("--out-dir", default=os.path.join("data", "processed", "daily"))
    ap.add_argument("--no-salinity", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="first N files only (smoke test)")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.raw_dir, "*.nc")))
    if a.limit:
        files = files[:a.limit]
    if not files:
        raise SystemExit(f"no NetCDF files in {a.raw_dir}")

    by_year = defaultdict(list)
    for f in files:
        m = re.search(r"(\d{4})\d{4}", os.path.basename(f))
        by_year[int(m.group(1))].append(f)

    print(f"{len(files)} files -> {dict((y, len(v)) for y, v in sorted(by_year.items()))}")
    for year in sorted(by_year):
        build_year(sorted(by_year[year]), year, a.out_dir, with_salinity=not a.no_salinity)
    print("\nNEXT: rebuild the climatology from the daily TRAIN years before training on this.")


if __name__ == "__main__":
    main()
