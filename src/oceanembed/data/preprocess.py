"""Regrid raw GLORYS NetCDF to the frozen 0.25 deg NIO grid and depths -> processed npz.

OWNER: Unit B (Darshan). Testable with a synthetic GLORYS file (scripts/make_synthetic_glorys.py).

Output: data/processed/grids.npz with keys
  times    datetime64[D]        (T,)
  sst,sss,ssh,u,v  float32      (T, 100, 240)      # surface fields
  temp     float32              (T, 100, 240, 11)  # temperature at config.DEPTHS
  land_mask bool                (100, 240)         # True = land (surface NaN)

VERIFY before trusting real data: latitude ascending?, longitude convention?, depth sign, units.
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


def run(raw_glob: str | None = None, out_path: str | None = None) -> str:
    raw_glob = raw_glob or os.path.join(config.DATA_RAW, "*.nc")
    out_path = out_path or os.path.join(config.DATA_PROCESSED, "grids.npz")
    files = sorted(_glob.glob(raw_glob))
    if not files:
        raise FileNotFoundError(f"no NetCDF matched {raw_glob}")
    print(f"[preprocess] opening {len(files)} file(s)")
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])

    latn = _find_coord(ds, "latitude", "lat", "nav_lat")
    lonn = _find_coord(ds, "longitude", "lon", "nav_lon")
    depthn = _find_coord(ds, "depth", "deptht", "lev")
    timen = _find_coord(ds, "time", "time_counter")

    # Ensure ascending coords so interpolation is well-defined
    ds = ds.sortby(latn).sortby(lonn).sortby(depthn)

    # Regrid horizontally to the frozen grid
    ds = ds.interp({latn: config.LAT, lonn: config.LON}, method="linear")

    T = ds.sizes[timen]
    surf = {}
    for var, name in [("thetao", "sst"), ("so", "sss"), ("uo", "u"), ("vo", "v")]:
        surf[name] = ds[var].isel({depthn: 0}).transpose(timen, latn, lonn).values.astype("float32")
    surf["ssh"] = ds["zos"].transpose(timen, latn, lonn).values.astype("float32")

    # Interp temperature to our DEPTHS -> (T, depth, lat, lon) -> (T, lat, lon, depth).
    # extrapolate: DEPTHS[0]=0 m is slightly above GLORYS's shallowest level (~0.49 m) -> treat as surface.
    temp = ds["thetao"].interp({depthn: config.DEPTHS}, method="linear",
                               kwargs={"fill_value": "extrapolate"})
    temp = temp.transpose(timen, latn, lonn, depthn).values.astype("float32")

    times = np.asarray(ds[timen].values).astype("datetime64[D]")
    land_mask = np.isnan(surf["sst"][0])  # surface NaN on first frame == land

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    np.savez_compressed(out_path, times=times, temp=temp, land_mask=land_mask, **surf)
    print(f"[preprocess] wrote {out_path}: T={T}, grid={config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}, "
          f"land cells={int(land_mask.sum())}")
    return out_path


if __name__ == "__main__":
    run()
