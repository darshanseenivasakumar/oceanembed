"""Regrid raw GLORYS NetCDF(s) to the frozen 0.25 deg NIO grid and depths -> processed npz.

OWNER: Unit B (Darshan).

Processes ONE FILE AT A TIME and accumulates, so 48 x 54 MB of native-resolution GLORYS never has to
fit in memory at once (each file is ~300x720x32 per variable; the accumulated output is only ~75 MB).

Output: data/processed/grids.npz with keys
  times    datetime64[D]        (T,)
  sst,sss,ssh,u,v  float32      (T, 100, 240)      # surface fields
  temp     float32              (T, 100, 240, 15)  # temperature at config.DEPTHS
  land_mask bool                (100, 240)         # True = land (surface NaN)

VERIFIED against real GLORYS 2026-08-25: latitude ascending, longitude -180..180 (our box is +45..105,
so no wrap issue), depth positive-down starting at 0.494 m, thetao in degrees_C.
"""
from __future__ import annotations
import glob as _glob
import os
import numpy as np
import xarray as xr
from oceanembed import config


def _find_coord(ds: xr.Dataset, *names: str) -> str:
    for n in names:
        if n in ds.coords or n in ds.dims:
            return n
    raise KeyError(f"none of {names} found in dataset coords {list(ds.coords)}")


def _process_one(path: str):
    """Open one GLORYS file, regrid to the frozen grid, return (times, surf dict, temp)."""
    with xr.open_dataset(path) as ds:
        latn = _find_coord(ds, "latitude", "lat", "nav_lat")
        lonn = _find_coord(ds, "longitude", "lon", "nav_lon")
        depthn = _find_coord(ds, "depth", "deptht", "lev")
        timen = _find_coord(ds, "time", "time_counter")

        ds = ds.sortby(latn).sortby(lonn).sortby(depthn)
        ds = ds.interp({latn: config.LAT, lonn: config.LON}, method="linear")

        surf = {}
        for var, name in [("thetao", "sst"), ("so", "sss"), ("uo", "u"), ("vo", "v")]:
            surf[name] = ds[var].isel({depthn: 0}).transpose(timen, latn, lonn).values.astype("float32")
        surf["ssh"] = ds["zos"].transpose(timen, latn, lonn).values.astype("float32")

        # Depth handling, asymmetric ON PURPOSE:
        #  * SHALLOW end: DEPTHS[0]=0 m sits just above GLORYS' shallowest level (0.494 m), a ~0.5 m
        #    gap inside a well-mixed layer -> extrapolating is safe and necessary (without it every
        #    row is NaN-dropped).
        #  * DEEP end: extrapolating past the deepest level INVENTS data. [VERIFIED 2026-08-25] a
        #    520 m download cap actually returned data to 453.9 m, so every 500 m value was
        #    extrapolated 46 m beyond the data and reported as a result. Now we FAIL LOUDLY.
        d_max = float(ds[depthn].max())
        too_deep = [d for d in config.DEPTHS if d > d_max]
        if too_deep:
            raise ValueError(
                f"{os.path.basename(path)} only reaches {d_max:.1f} m, but config.DEPTHS asks for "
                f"{too_deep}. Extrapolating past the data would fabricate values. Re-download with a "
                f"deeper MAX_DEPTH in data/download_glorys.py (must BRACKET the deepest target level)."
            )
        temp = ds["thetao"].interp({depthn: config.DEPTHS}, method="linear",
                                   kwargs={"fill_value": "extrapolate"})
        temp = temp.transpose(timen, latn, lonn, depthn).values.astype("float32")
        times = np.asarray(ds[timen].values).astype("datetime64[D]")
    return times, surf, temp


def run(raw_glob: str | None = None, out_path: str | None = None) -> str:
    """raw_glob defaults to real GLORYS files (glorys_*.nc), falling back to synthetic if none exist.

    Never mixes real and synthetic data — that would silently corrupt training.
    """
    if raw_glob is None:
        real = os.path.join(config.DATA_RAW, "glorys_*.nc")
        raw_glob = real if _glob.glob(real) else os.path.join(config.DATA_RAW, "synthetic_glorys.nc")
    out_path = out_path or os.path.join(config.DATA_PROCESSED, "grids.npz")

    files = sorted(_glob.glob(raw_glob))
    if not files:
        raise FileNotFoundError(f"no NetCDF matched {raw_glob}")
    kind = "REAL GLORYS" if "glorys_" in os.path.basename(files[0]) else "SYNTHETIC"
    print(f"[preprocess] {len(files)} file(s) [{kind}]")

    all_times, all_temp, all_surf = [], [], {k: [] for k in ["sst", "sss", "ssh", "u", "v"]}
    for i, f in enumerate(files, 1):
        times, surf, temp = _process_one(f)
        all_times.append(times)
        all_temp.append(temp)
        for k in all_surf:
            all_surf[k].append(surf[k])
        if i % 10 == 0 or i == len(files):
            print(f"[preprocess]   {i}/{len(files)} files done")

    times = np.concatenate(all_times)
    temp = np.concatenate(all_temp, axis=0)
    surf = {k: np.concatenate(v, axis=0) for k, v in all_surf.items()}

    order = np.argsort(times)          # keep chronological order regardless of glob order
    times, temp = times[order], temp[order]
    surf = {k: v[order] for k, v in surf.items()}

    land_mask = np.isnan(surf["sst"]).all(axis=0)   # land = NaN at EVERY timestep

    # Provenance travels WITH the data, not inferred from a sibling file (docs/DECISIONS.md D-018).
    source = "real-glorys" if kind == "REAL GLORYS" else "synthetic"

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    np.savez_compressed(out_path, times=times, temp=temp, land_mask=land_mask,
                        source=np.array(source), **surf)
    print(f"[preprocess] source={source}")
    print(f"[preprocess] wrote {out_path}: T={len(times)}, grid={config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}, "
          f"land cells={int(land_mask.sum())}, span {times.min()}..{times.max()}")
    return out_path


if __name__ == "__main__":
    run()
