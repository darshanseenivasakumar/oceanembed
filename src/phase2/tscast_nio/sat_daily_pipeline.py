"""Build the SATELLITE daily 0.25 deg bundle -- the PS's actual model input. (Unit A / Arjhun.)

WHAT THIS IS FOR
SIH26066: "estimate the three-dimensional ocean temperature using ONLY surface satellite
observations." The existing bundle in data/processed/daily/ feeds the encoder GLORYS REANALYSIS on
5 of its 7 channels, so what we have been calling a satellite embedding is embedding a reanalysis.
This module builds the real thing.

WHAT STAYS GLORYS, ON PURPOSE
The TARGET. The PS names "Training Target Dataset (Subsurface Temperature): GLORYS Global Ocean
Reanalysis". So temp, salinity, land_mask and valid_mask are read from the existing GLORYS bundle
and are NOT recomputed here. Satellite goes IN; GLORYS is what we train AGAINST. Confusing those
two is the failure this whole module exists to end.

WRITES TO A SEPARATE NAMESPACE
data/processed/daily_sat/v001/ -- never data/processed/daily/, which is canonical GLORYS input and
is not ours to overwrite.

REGRIDDING -- one operator, chosen deliberately [see docs/ARJHUN_EXECUTION_PLAN.md P2]
Every satellite grid is OFFSET from config.LAT/LON. Measured on this machine:

    target config.LAT   5.0000  5.2500  5.5000 ...
    sst    0.05  deg    5.0250  5.0750  ...      offset 0.025
    ssh    0.125 deg    5.0625  5.1875  ...      offset 0.0625
    sss    0.125 deg    5.0625  5.1875  ...      offset 0.0625
    cur    0.25  deg    5.1250  5.3750  ...      offset 0.125  <- HALF A CELL, ~14 km

So "currents are already 0.25 deg, no regrid needed" is FALSE, and shipping them unshifted would
misplace every current value by half a cell. This project has already been bitten once by a ~28 km
cell-lookup error; that is not a mistake worth making twice.

phase2.data.download_wind_daily.regrid_to_config is the better operator (area-preserving block
mean) but it REFUSES a grid that does not nest, and none of these do: SST's 0.05 deg is offset half
a native cell from any nesting arrangement, and SSS/SSH lost their lower half-cell to the request
box (lat_min=5.0 clipped the 4.9375 row). Re-downloading 1,164 files with a wider box to satisfy it
is not a good use of the remaining time.

So: BILINEAR interpolation onto config.LAT/LON, via xarray -- the SAME operator
oceanembed.data.preprocess._process_one already applies to GLORYS. That matters for the satellite-
vs-GLORYS comparison: both legs then reach the frozen grid through the same transform, so a
difference between them is a difference in the DATA, not in how it was resampled.

KNOWN LIMITATION, stated because it is real: bilinear samples the 4 nearest native cells. On the
0.05 deg SST that discards most of a 5x5 neighbourhood and does not average away small-scale noise.
OSTIA is itself an analysis with correlation scales near our target cell size, so the aliasing is
expected to be mild -- [INFERRED], not measured. A block-mean variant is a cheap future ablation.

UNITS AND QUANTITY MISMATCHES -- converted or refused here, never papered over
  * analysed_sst is KELVIN; GLORYS thetao is degC. Converted, and range-checked after.
  * `sos` carries the CF unit string "0.001". The VALUES are practical salinity (~32-37). Asserted,
    because trusting that string literally would be a 1000x error.
  * `adt` is absolute dynamic topography on a mean geoid; GLORYS `zos` is sea surface height above
    geoid. Close analogues that can carry a constant offset. NOT corrected here -- a fitted offset
    is a modelling choice, and the model can learn a constant.
  * uo/vo from GLOBCURRENT are geostrophic + Ekman, matching GLORYS uo/vo semantically. This is the
    channel the PS's OSCAR recommendation is about; see scripts/phase2/download_currents_daily.py.

MISSING DAYS ARE DROPPED, NEVER FILLED
A day enters the bundle only if every satellite channel exists for it. Everything else is recorded
in `missing_days`. There is no imputation anywhere in this file.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess

import numpy as np
import xarray as xr

from oceanembed import config as base
from phase2.tscast_nio import config

SAT_DIR = os.path.join(base.DATA_RAW, "satellite_nrt")
CUR_DIR = os.path.join(base.DATA_RAW, "currents_nrt")
WIND_NPZ = os.path.join(base.DATA_PROCESSED, "wind_daily.npz")
GLORYS_DIR = os.path.join(base.DATA_PROCESSED, "daily")
OUT_DIR = os.path.join(base.DATA_PROCESSED, "daily_sat", "v001")

# (channel, directory, filename prefix, netcdf variable)
SAT_SOURCES = [
    ("sst", SAT_DIR, "sst", "analysed_sst"),
    ("sss", SAT_DIR, "sss", "sos"),
    ("ssh", SAT_DIR, "ssh", "adt"),
    ("u", CUR_DIR, "cur", "uo"),
    ("v", CUR_DIR, "cur", "vo"),
]

# Physical gates. A value outside these means a unit error or a fill value read as data, and the
# build must stop rather than write it. SST bounds are the ones verify_daily_bundle.py already
# justifies for this basin (Somali upwelling at the cold end, the Persian Gulf at the warm end).
RANGES = {
    "sst": (11.0, 38.0),      # degC, AFTER the Kelvin conversion
    "sss": (25.0, 42.0),      # practical salinity; BoB river plumes run genuinely fresh
    "ssh": (-2.0, 2.0),       # m
    "u": (-3.0, 3.0),         # m/s
    "v": (-3.0, 3.0),
}

PROVENANCE_CHANNELS = {
    "sst": dict(product="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2", provider="UKMO",
                data_class="SATELLITE_DERIVED", native_resolution="0.05 deg",
                native_units="kelvin", processed_units="degC",
                processing="K->degC, bilinear to 0.25 deg, GLORYS land mask",
                note="OSTIA L4 analysis: AVHRR, VIIRS, AMSR2, SEVIRI. PS-recommended product."),
    "sss": dict(product="cmems_obs-mob_glo_phy-sss_nrt_multi_P1D", provider="CNR",
                data_class="SATELLITE + INSITU_BLEND", native_resolution="0.125 deg",
                native_units="0.001 (CF string; values are practical salinity)",
                processed_units="psu",
                processing="bilinear to 0.25 deg, GLORYS land mask",
                note="SMOS multi-dimensionally interpolated WITH IN-SITU salinity "
                     "(Buongiorno Nardelli 2016). NOT a pure satellite retrieval -- must not be "
                     "described as one."),
    "ssh": dict(product="cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D",
                provider="CLS/CNES", data_class="SATELLITE_DERIVED",
                native_resolution="0.125 deg", native_units="m", processed_units="m",
                processing="bilinear to 0.25 deg, GLORYS land mask",
                note="DUACS multi-mission altimetry. `adt` vs GLORYS `zos` may carry a constant "
                     "offset; deliberately NOT corrected."),
    "u": dict(product="cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m", provider="CLS/CNES",
              data_class="SATELLITE_DERIVED", native_resolution="0.25 deg (offset half a cell)",
              native_units="m s-1", processed_units="m s-1",
              processing="bilinear half-cell shift to 0.25 deg, GLORYS land mask",
              note="COPERNICUS-GLOBCURRENT total surface current = geostrophic + Ekman. Stands in "
                   "for the PS's PO.DAAC OSCAR_L4_OC_FINAL_V2.0 (Earthdata login unavailable): "
                   "same quantity, resolution and cadence. DOCUMENTED DEVIATION."),
    "v": None,   # filled from "u" at build time; same file, same product
    "wu": dict(product="cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H", provider="CMEMS",
               data_class="SATELLITE_DERIVED", native_resolution="0.125 deg",
               native_units="m s-1", processed_units="m s-1",
               processing="hourly -> daily mean, block-averaged 0.125->0.25 deg BY COORDINATE",
               note="Reused unchanged from the GLORYS bundle: it was always an observational "
                    "product, never reanalysis."),
    "wv": None,  # filled from "wu"
}


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def _regrid(da: xr.DataArray) -> np.ndarray:
    """Bilinear onto the frozen grid. Sorted first: interp on a descending axis returns NaN."""
    latn = "latitude" if "latitude" in da.coords else "lat"
    lonn = "longitude" if "longitude" in da.coords else "lon"
    da = da.sortby(latn).sortby(lonn)
    out = da.interp({latn: base.LAT, lonn: base.LON}, method="linear")
    return np.asarray(out.values, dtype="float32")


def _read_channel(directory: str, prefix: str, var: str, day: str) -> np.ndarray | None:
    """One (100, 240) field for one day, or None if the file is absent."""
    path = os.path.join(directory, f"{prefix}_{day}.nc")
    if not os.path.exists(path):
        return None
    with xr.open_dataset(path) as ds:
        if var not in ds:
            raise ValueError(f"{path}: expected variable {var!r}, found {list(ds.data_vars)}")
        da = ds[var]
        for squeeze in ("time", "depth"):
            if squeeze in da.dims:
                da = da.isel({squeeze: 0})
        field = _regrid(da)
    if field.shape != (len(base.LAT), len(base.LON)):
        raise ValueError(f"{path}: regridded to {field.shape}, expected "
                         f"{(len(base.LAT), len(base.LON))}")
    return field


def _check_range(name: str, field: np.ndarray, day: str) -> None:
    lo, hi = RANGES[name]
    finite = field[np.isfinite(field)]
    if finite.size == 0:
        raise ValueError(f"{name} {day}: every value is NaN after regridding")
    mn, mx = float(finite.min()), float(finite.max())
    if mn < lo or mx > hi:
        raise ValueError(
            f"{name} {day}: range [{mn:.3f}, {mx:.3f}] falls outside the physical gate "
            f"[{lo}, {hi}]. This is a unit error or a fill value read as data -- refusing to "
            f"write it into the bundle.")


def available_days() -> list[str]:
    """YYYYMMDD strings for which EVERY satellite channel exists. No partial days."""
    per_source = []
    for _, directory, prefix, _ in SAT_SOURCES:
        found = {os.path.basename(p).split("_")[-1][:8]
                 for p in glob.glob(os.path.join(directory, f"{prefix}_*.nc"))}
        per_source.append(found)
    return sorted(set.intersection(*per_source)) if per_source else []


def build_year(year: int, days: list[str], out_dir: str = OUT_DIR) -> str | None:
    """Write one year of the satellite bundle. Targets come from the GLORYS bundle unchanged."""
    days = [d for d in days if d.startswith(str(year))]
    if not days:
        return None

    gpath = os.path.join(GLORYS_DIR, f"{year}.npz")
    if not os.path.exists(gpath):
        raise SystemExit(f"the GLORYS bundle {gpath} is required for the TARGET (temp, salinity, "
                         f"land_mask) and is absent. Build it first with daily_pipeline.py.")
    g = np.load(gpath, allow_pickle=True)
    g_days = {str(t).replace("-", "")[:8]: i for i, t in enumerate(g["times"])}
    g_channels = list(g["channels"])
    wind = np.load(WIND_NPZ)
    w_days = {str(d): i for i, d in enumerate(wind["dates"])}

    # A day needs a satellite record AND a GLORYS target AND wind. Anything else is dropped.
    keep = [d for d in days if d in g_days and d in w_days]
    dropped = sorted(set(days) - set(keep))

    land = np.asarray(g["land_mask"], dtype=bool)
    n = len(keep)
    surface = np.full((n, len(base.LAT), len(base.LON), len(config.CHANNELS)), np.nan, "float32")

    for k, day in enumerate(keep):
        for name, directory, prefix, var in SAT_SOURCES:
            field = _read_channel(directory, prefix, var, day)
            if field is None:
                raise RuntimeError(f"{name} {day} vanished between listing and reading")
            if name == "sst":
                # OSTIA is Kelvin. Convert BEFORE the range gate so the gate is meaningful.
                field = field - 273.15
            field[land] = np.nan          # GLORYS land mask: satellite SST contains inland water
            _check_range(name, field, day)
            surface[k, :, :, config.CHANNELS.index(name)] = field

        wi = w_days[day]
        for wname, arr in (("wu", wind["wu"]), ("wv", wind["wv"])):
            f = np.asarray(arr[wi], dtype="float32").copy()
            f[land] = np.nan
            surface[k, :, :, config.CHANNELS.index(wname)] = f
        if (k + 1) % 25 == 0:
            print(f"[sat-bundle] {year} {k + 1}/{n}", flush=True)

    gi = [g_days[d] for d in keep]
    payload = dict(
        times=np.array([f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in keep], dtype="datetime64[D]"),
        surface=surface,
        temp=np.asarray(g["temp"])[gi],
        land_mask=land,
        valid_mask=np.asarray(g["valid_mask"])[gi] if g["valid_mask"].ndim > 2
        else np.asarray(g["valid_mask"]),
        channels=np.array(config.CHANNELS),
        units=np.array(config.CHANNEL_UNITS),
        missing_days=np.array(dropped),
    )
    if "salinity" in g:
        payload["salinity"] = np.asarray(g["salinity"])[gi]

    chans = {}
    for name in config.CHANNELS:
        meta = PROVENANCE_CHANNELS[name]
        if meta is None:                       # v mirrors u; wv mirrors wu
            meta = dict(PROVENANCE_CHANNELS["u" if name == "v" else "wu"])
        chans[name] = meta
    payload["provenance"] = json.dumps({
        "bundle": "satellite daily 0.25 deg, v001",
        "input_source": "satellite",
        "why": "SIH26066 asks for reconstruction from surface SATELLITE observations. The GLORYS "
               "bundle in data/processed/daily/ supplies 5 of 7 surface channels from reanalysis; "
               "this one does not.",
        "target_source": "GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D-m)",
        "target_note": "temp, salinity, land_mask and valid_mask are the PS's named training "
                       "target and are copied from the GLORYS bundle UNCHANGED. Satellite is the "
                       "INPUT; GLORYS is the TARGET. They are not the same thing.",
        "regrid": "bilinear (xarray .interp) onto config.LAT x config.LON -- the same operator "
                  "oceanembed.data.preprocess._process_one applies to GLORYS, so both legs of the "
                  "satellite-vs-GLORYS comparison reach the frozen grid through one transform",
        "regrid_limitation": "bilinear samples the 4 nearest native cells; on the 0.05 deg SST "
                             "that does not average a full 5x5 neighbourhood. [INFERRED] mild, "
                             "not measured.",
        "edge_policy": "The first row (lat 5.0) and first column (lon 45.0) are NaN in every "
                       "satellite channel. Each native grid starts inboard of our domain edge "
                       "(sst 45.025, ssh/sss 45.0625, currents 45.125) because the CMEMS request "
                       "box was cut at exactly 45.0/5.0, so bilinear has nothing outside to "
                       "interpolate from. NaN is deliberate: extrapolating an unobserved "
                       "coastline would fabricate data. Cost is ~1.4% of cells.",
        "land_mask_source": "GLORYS bundle -- satellite SST contains inland water (a Tibetan lake "
                            "at 3.81 degC sits inside our lat/lon box)",
        "missing_data_policy": "a day is included only if EVERY satellite channel exists for it, "
                               "plus a GLORYS target and wind. Others are listed in missing_days. "
                               "No imputation anywhere.",
        "deviation_from_ps": "currents come from CMEMS COPERNICUS-GLOBCURRENT rather than the "
                             "PS's PO.DAAC OSCAR_L4_OC_FINAL_V2.0 (no NASA Earthdata login). Same "
                             "quantity (geostrophic + Ekman), same 0.25 deg daily grid.",
        "channels": chans,
        "n_days": n,
        "dropped_days": dropped,
        "code_commit": _commit(),
    }, indent=1)

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{year}.npz")
    np.savez_compressed(out, **payload)
    print(f"[sat-bundle] wrote {out}: {n} days, {len(dropped)} dropped, "
          f"{len(g_channels)} target channels available")
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--years", nargs="+", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None,
                    help="build only the first N available days (smoke test)")
    a = ap.parse_args()

    days = available_days()
    if not days:
        raise SystemExit("no day has all five satellite channels yet; is the currents download "
                         "still running?")
    if a.limit:
        days = days[:a.limit]
    years = a.years or sorted({int(d[:4]) for d in days})
    print(f"[sat-bundle] {len(days)} complete satellite days, years {years}")
    for y in years:
        build_year(y, days, a.out_dir)


if __name__ == "__main__":
    main()
