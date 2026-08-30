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

# Channels 6 and 7 of the frozen contract, from phase2.data.download_wind_daily. Appended in this
# order and no other -- the contract is ["sst","sss","ssh","u","v","wu","wv"] and readers index by
# position, so a reordered write is a silent science bug, not a formatting one.
WIND_KEYS = ["wu", "wv"]
WIND_UNITS = ["m s-1", "m s-1"]
WIND_NPZ = os.path.join(base.DATA_PROCESSED, "wind_daily.npz")


def load_wind(path: str = WIND_NPZ) -> dict | None:
    """Daily-mean wind on config.LAT/LON, keyed BY DATE. None if it was never downloaded.

    The grid is verified here rather than trusted: `download_wind_daily` writes the lat/lon it
    regridded onto, so a bundle built against some other grid must fail loudly instead of being
    stacked into channels 6-7 where nothing would ever look at it again.
    """
    if not os.path.exists(path):
        return None
    z = np.load(path, allow_pickle=False)
    for axis, want in (("lat", base.LAT), ("lon", base.LON)):
        got = z[axis]
        if got.shape != want.shape or not np.allclose(got, want, atol=1e-6):
            raise ValueError(
                f"{path} is on a different {axis} grid than config: "
                f"{got[:3]}... vs {want[:3]}... -- refusing to merge it as a surface channel")
    return {"dates": np.asarray(z["dates"], dtype="datetime64[D]"),
            "wu": z["wu"], "wv": z["wv"]}


def _wind_for(wind: dict, times: np.ndarray) -> np.ndarray:
    """(T, 100, 240, 2) wind aligned to `times` BY DATE, never by position.

    Refuses on any missing day. A NaN wind channel would train fine and quietly mean "no wind
    information for this day" -- the model cannot tell that apart from calm.
    """
    idx = np.searchsorted(wind["dates"], times)
    idx = np.clip(idx, 0, len(wind["dates"]) - 1)
    hit = wind["dates"][idx] == times
    if not hit.all():
        miss = times[~hit]
        raise ValueError(
            f"wind is missing {len(miss)} of {len(times)} days needed by this year, "
            f"e.g. {list(miss[:5])}. Re-run `python -m phase2.data.download_wind_daily --process` "
            f"or build this year with --no-wind and say so beside every number it produces.")
    return np.stack([wind["wu"][idx], wind["wv"][idx]], axis=-1).astype("float32")


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


def build_year(files: list[str], year: int, out_dir: str, with_salinity: bool = True,
               wind: dict | None = None) -> str:
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

    # Wind is joined AFTER the sort, so it aligns to the dates actually written -- joining before
    # would align it to file order, which is not the same thing.
    keys, units = list(SURFACE_KEYS), list(SURFACE_UNITS)
    if wind is not None:
        surface = np.concatenate([surface, _wind_for(wind, times)], axis=-1)
        keys += WIND_KEYS
        units += WIND_UNITS

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
        channels=np.array(keys), units=np.array(units),
        land_mask=land_mask, valid_mask=valid_mask, missing_days=missing,
        provenance=json.dumps({
            "source": "GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D-m)",
            "from": "Darshan's bundle, verified by scripts/phase2/verify_daily_bundle.py",
            "regrid": "oceanembed.data.preprocess._process_one -- reused, not reimplemented",
            "n_files": n, "year": year,
            "channels_note": (f"{len(keys)} of the contract's 7 channels: {keys}"
                              + ("" if len(keys) == 7 else
                                 " -- WIND ABSENT, state that beside every number built on this")),
            "wind_source": (None if wind is None else
                            "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H, hourly -> daily mean, "
                            "block-averaged 0.125->0.25 deg by coordinate "
                            "(phase2.data.download_wind_daily)"),
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
    # `data/raw/daily` never existed: our own launcher (scripts/phase2/download_daily_2025_2026.py)
    # writes GLORYS to data/raw/glorys_daily. The old default sent anyone following the checklist
    # toward a 16 h re-download of files that were already on disk.
    ap.add_argument("--raw-dir", default=os.path.join("data", "raw", "glorys_daily"),
                    help="where download_daily_2025_2026.py put the GLORYS files")
    ap.add_argument("--out-dir", default=os.path.join("data", "processed", "daily"))
    ap.add_argument("--no-salinity", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="first N files only (smoke test)")
    ap.add_argument("--wind", default=WIND_NPZ,
                    help="daily wind npz to merge as channels 6-7; absent = 5 channels")
    ap.add_argument("--no-wind", action="store_true",
                    help="write 5 channels even if wind exists (to reproduce a 5-channel run)")
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

    wind = None if a.no_wind else load_wind(a.wind)
    if wind is None:
        print(f"WIND: absent ({a.wind}) -- writing 5 of the contract's 7 channels. Every "
              f"number built on this bundle must say so.")
    else:
        print(f"WIND: {len(wind['dates'])} days {wind['dates'][0]}..{wind['dates'][-1]}, "
              f"merging as channels 6-7 -> 7 of 7 contract channels")

    print(f"{len(files)} files -> {dict((y, len(v)) for y, v in sorted(by_year.items()))}")
    for year in sorted(by_year):
        build_year(sorted(by_year[year]), year, a.out_dir, with_salinity=not a.no_salinity,
                   wind=wind)
    # NOT "rebuild the climatology from the daily train years" -- that line used to sit here and
    # it contradicts a settled decision. The prior is the 2019-2021 monthly climatology PRECISELY
    # because it is disjoint from 2025-26; the daily train split contains no April or May at all,
    # and 388 days is not a climatology. See scripts/phase2/build_daily_climatology.py.
    print("\nNEXT: train against artifacts/climatology.npy (2019-2021, disjoint from this bundle).")


if __name__ == "__main__":
    main()
