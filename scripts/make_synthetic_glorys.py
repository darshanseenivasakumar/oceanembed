"""Write a small SYNTHETIC GLORYS-shaped NetCDF so preprocess + build_samples can be tested WITHOUT CMEMS.

FAKE data, correct structure (dims time/depth/latitude/longitude; vars thetao,so,zos,uo,vo).
Covers train years (2019-21) and test year (2022) so the split is exercised.

Run:  python scripts/make_synthetic_glorys.py
Owner: Unit B (Darshan).
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config  # noqa: E402

RNG = np.random.default_rng(config.SEED)


def main() -> str:
    # Coarser than the target grid on purpose (preprocess will interp up to 0.25 deg)
    lat = np.arange(4.0, 31.0, 0.5, dtype="float32")     # 54
    lon = np.arange(44.0, 106.0, 0.5, dtype="float32")   # 124
    depth = np.array([0.49, 9.0, 25.0, 50.0, 100.0, 200.0, 300.0, 500.0, 700.0], dtype="float32")
    times = pd.to_datetime(["2019-03-01", "2019-09-01", "2020-03-01", "2020-09-01",
                            "2021-03-01", "2021-09-01", "2022-03-01", "2022-09-01"])
    T, D, Y, X = len(times), len(depth), len(lat), len(lon)

    la = lat[None, None, :, None]
    seas = np.cos(2 * np.pi * (times.dayofyear.to_numpy() / 365.25))[:, None, None, None]
    surf_field = 28 - 0.15 * (la - 5) + 1.5 * seas + RNG.normal(0, 0.3, (T, 1, Y, X))
    decay = np.exp(-depth / 250.0)[None, :, None, None]
    thetao = (surf_field - 6.0) * decay + 6.0 + RNG.normal(0, 0.2, (T, D, Y, X))

    so = 35 + 0.5 * np.sin(la) + RNG.normal(0, 0.1, (T, D, Y, X))
    zos = 0.1 * seas[:, 0] + RNG.normal(0, 0.05, (T, Y, X))
    uo = RNG.normal(0, 0.2, (T, D, Y, X)); vo = RNG.normal(0, 0.2, (T, D, Y, X))

    # Fake land: a NW corner block -> NaN everywhere
    land = np.zeros((Y, X), dtype=bool); land[:6, :6] = True
    for arr in (thetao, so, uo, vo):
        arr[:, :, land] = np.nan
    zos[:, land] = np.nan

    ds = xr.Dataset(
        dict(
            thetao=(["time", "depth", "latitude", "longitude"], thetao.astype("float32")),
            so=(["time", "depth", "latitude", "longitude"], so.astype("float32")),
            uo=(["time", "depth", "latitude", "longitude"], uo.astype("float32")),
            vo=(["time", "depth", "latitude", "longitude"], vo.astype("float32")),
            zos=(["time", "latitude", "longitude"], zos.astype("float32")),
        ),
        coords=dict(time=times, depth=depth, latitude=lat, longitude=lon),
    )
    for v, u in [("thetao", "degrees_C"), ("so", "1e-3"), ("zos", "m"), ("uo", "m s-1"), ("vo", "m s-1")]:
        ds[v].attrs["units"] = u

    os.makedirs(config.DATA_RAW, exist_ok=True)
    out = os.path.join(config.DATA_RAW, "synthetic_glorys.nc")
    ds.to_netcdf(out)
    print(f"[synthetic] wrote {out}: time={T} depth={D} lat={Y} lon={X}")
    return out


if __name__ == "__main__":
    main()
