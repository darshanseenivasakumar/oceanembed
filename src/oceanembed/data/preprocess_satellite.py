"""Regrid REAL satellite L4 fields onto the frozen 0.25 deg NIO grid.

OWNER: Unit B (Darshan).

Produces data/processed/satellite_grids.npz with EXACTLY the surface keys `preprocess.py` writes
(times, sst, sss, ssh, u, v, land_mask, source) so downstream code is identical -- only the SOURCE
of the surface fields changes. There is no subsurface `temp`: satellites cannot see it. That is the
whole point of the project, and it is why validation here must use Argo.

UNIT CONVERSIONS (each one is a silent-failure risk if missed):
  analysed_sst  KELVIN -> degC   (-273.15)          [VERIFIED: 300.7 K == 27.6 degC]
  sos           0.001  == PSS-78 -> used as-is
  adt           m      -> used as our `ssh`          (see the caveat in download_satellite.py)
  ugos/vgos     m/s    -> used as our `u`/`v`        (GEOSTROPHIC only; GLORYS also has ageostrophic)

Run:  python -m oceanembed.data.preprocess_satellite
"""
from __future__ import annotations
import glob as _glob
import os
import numpy as np
import xarray as xr
from oceanembed import config

IN_DIR = os.path.join(config.DATA_RAW, "satellite")
OUT = os.path.join(config.DATA_PROCESSED, "satellite_grids.npz")

# Physically plausible bounds. A conversion mistake (Kelvin left in, salinity in the wrong scale)
# breaks these long before it reaches a model, instead of silently producing wrong temperatures.
BOUNDS = {"sst": (-2.0, 40.0), "sss": (20.0, 42.0), "ssh": (-3.0, 3.0),
          "u": (-5.0, 5.0), "v": (-5.0, 5.0)}


def _coords(ds):
    lat = "latitude" if "latitude" in ds.coords else "lat"
    lon = "longitude" if "longitude" in ds.coords else "lon"
    return lat, lon


def _regrid(da) -> np.ndarray:
    ds = da.to_dataset(name="v")
    lat, lon = _coords(ds)
    ds = ds.sortby(lat).sortby(lon).interp({lat: config.LAT, lon: config.LON}, method="linear")
    arr = ds["v"].values.astype("float32")
    return arr[0] if arr.ndim == 3 else arr           # drop a length-1 time axis


def _check(name: str, arr: np.ndarray, date) -> None:
    lo, hi = BOUNDS[name]
    fin = arr[np.isfinite(arr)]
    if fin.size and (fin.min() < lo or fin.max() > hi):
        raise ValueError(
            f"{name} on {date} is out of physical range [{lo},{hi}]: "
            f"{fin.min():.2f}..{fin.max():.2f}. Check the unit conversion "
            f"(Kelvin vs degC, salinity scale) before trusting anything downstream."
        )


def run(in_dir: str = IN_DIR, out_path: str = OUT) -> str:
    dates = sorted({os.path.basename(f).split("_")[1].split(".")[0]
                    for f in _glob.glob(os.path.join(in_dir, "*_*.nc"))})
    if not dates:
        raise FileNotFoundError(f"no satellite files in {in_dir} -- run download_satellite first")

    times, fields = [], {k: [] for k in ["sst", "sss", "ssh", "u", "v"]}
    for ds_str in dates:
        p_sst = os.path.join(in_dir, f"sst_{ds_str}.nc")
        p_ssh = os.path.join(in_dir, f"ssh_{ds_str}.nc")
        p_sss = os.path.join(in_dir, f"sss_{ds_str}.nc")
        if not all(os.path.exists(p) for p in (p_sst, p_ssh, p_sss)):
            print(f"[sat-pre] {ds_str}: incomplete triple, skipping")
            continue

        with xr.open_dataset(p_sst) as d:
            sst = _regrid(d["analysed_sst"]) - 273.15          # KELVIN -> degC
        with xr.open_dataset(p_ssh) as d:
            ssh = _regrid(d["adt"]); u = _regrid(d["ugos"]); v = _regrid(d["vgos"])
        with xr.open_dataset(p_sss) as d:
            sss = _regrid(d["sos"])

        vals = dict(sst=sst, sss=sss, ssh=ssh, u=u, v=v)
        for k, a in vals.items():
            _check(k, a, ds_str)
            fields[k].append(a)
        times.append(np.datetime64(f"{ds_str[:4]}-{ds_str[4:6]}-{ds_str[6:]}", "D"))

    if not times:
        raise RuntimeError("no complete satellite date triples found")

    times = np.array(times, dtype="datetime64[D]")
    order = np.argsort(times)
    times = times[order]
    out = {k: np.stack(v)[order] for k, v in fields.items()}
    land_mask = np.isnan(out["sst"]).all(axis=0)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    np.savez_compressed(out_path, times=times, land_mask=land_mask,
                        source=np.array("satellite-l4"), **out)
    print(f"[sat-pre] wrote {out_path}: T={len(times)}, span {times.min()}..{times.max()}, "
          f"land cells={int(land_mask.sum())}")
    for k in ["sst", "sss", "ssh", "u", "v"]:
        a = out[k][np.isfinite(out[k])]
        print(f"    {k:4s} {a.min():7.2f} .. {a.max():7.2f}   mean {a.mean():7.2f}")
    return out_path


if __name__ == "__main__":
    run()
