"""One reconstruction -> one NetCDF file. (Unit A / Arjhun.)

WHY THIS IS A NEW MODULE AND NOT AN EXTENSION OF `heat_content.to_xarray`
That function is shape-bound to the 2-D heat-content triple (lat, lon). A reconstruction is
(lat, lon, depth) plus three optional stage-2 variables. One function serving both would branch on
dict keys -- a second definition of "what a product file is", which is the drift `field.py` was
written to stop. `to_xarray` keeps its job; this one has its own.

WHAT A FILE MUST CARRY, AND WHY
`docs/phase2/tscast_output_schema.md` §5 is a CONTRACT. A file handed to a jury, a reviewer or
INCOIS is the one artifact that travels without us standing next to it, so it must answer on its own:
which checkpoint, which bundle, satellite or reanalysis, was sigma calibrated, which commit. The
shipped `heat_content_2026-05-15.nc` carries seven attributes and none of those -- verified
2026-09-05. That is the gap this closes.

THREE TRAPS, ALL OF THEM RULE 8 (`START_HERE.md`: an absence is not a value)
  * NaN is LAND or BELOW THE SEAFLOOR, never zero. `_FillValue` is set explicitly on every float
    variable so no reader's default turns a missing cell into a measurement of 0 degC.
  * A stage-1 file OMITS the salinity variables entirely rather than writing an all-NaN grid.
    An all-NaN `salinity` asserts "this file has salinity, and it happens to be missing everywhere",
    which is a different and false claim.
  * Booleans become int8 flags with `flag_values`/`flag_meanings`. NetCDF has no bool; a silent
    float cast is how a mask stops being a mask and starts being a number.
"""
from __future__ import annotations

import os

import numpy as np

from oceanembed import config as base
from phase2.tscast_nio import config, provenance as prov

#: h5netcdf, pinned. `to_netcdf()` with no path returns bytes only on some engines: scipy emits a
#: BufferError on close and netcdf4 raises outright. Verified 2026-09-05.
ENGINE = "h5netcdf"

NAN_COMMENT = "NaN = land or below the seafloor; not a measurement of zero"


def _float_var(dims, values, *, units, long_name, standard_name=None, extra=None):
    attrs = {"units": units, "long_name": long_name, "comment": NAN_COMMENT}
    if standard_name:
        attrs["standard_name"] = standard_name
    if extra:
        attrs.update(extra)
    return dims, np.asarray(values, dtype="float32"), attrs


def _flag_var(dims, values, *, long_name, meanings):
    """A boolean mask as an int8 flag, so it can never be read as a quantity."""
    return dims, np.asarray(values, dtype="int8"), {
        "long_name": long_name, "flag_values": np.array([0, 1], dtype="int8"),
        "flag_meanings": meanings, "comment": "flag, not a quantity"}


def field_to_xarray(field: dict, *, extra_attrs: dict | None = None):
    """A `predict_field` result as a CF-1.8 xarray Dataset carrying its full provenance.

    `field` is the dict from `phase2.tscast_nio.field.predict_field`. Its `provenance` is written
    into the global attributes through `provenance.as_netcdf_attrs`, which keeps every key and names
    the unknowns rather than dropping them.
    """
    import xarray as xr

    t = np.asarray(field["temperature"])
    if t.shape != (len(base.LAT), len(base.LON), config.N_DEPTHS):
        raise ValueError(f"expected {(len(base.LAT), len(base.LON), config.N_DEPTHS)}, got {t.shape}")

    stage = int(field.get("stage", 1))
    dims3 = ("lat", "lon", "depth")

    data_vars = {
        "temperature": _float_var(
            dims3, t, units="degC", long_name="reconstructed sea water potential temperature",
            standard_name="sea_water_potential_temperature"),
        "temperature_uncertainty": _float_var(
            dims3, field["sigma"], units="degC",
            long_name="predicted 1-sigma uncertainty on temperature",
            # The calibration state travels ON the variable it qualifies, not only in the global
            # block: a reader who slices out this array must not lose the caveat with it.
            extra={"is_calibrated": "true" if field["provenance"].get("sigma_is_calibrated")
                                   else "false",
                   "calibration_note": str(field["provenance"].get("sigma_calibration_note")
                                           or prov.NOT_RECORDED)}),
        "valid_mask": _flag_var(dims3, field["valid_mask"], long_name="ocean above the seafloor",
                                meanings="invalid valid"),
        "land_mask": _flag_var(("lat", "lon"), field["land_mask"], long_name="GLORYS land mask",
                               meanings="ocean land"),
    }

    if stage == 2 and field.get("salinity") is not None:
        data_vars["salinity"] = _float_var(
            dims3, field["salinity"], units="psu", long_name="reconstructed sea water salinity",
            standard_name="sea_water_salinity")
        data_vars["salinity_uncertainty"] = _float_var(
            dims3, field["sigma_s"], units="psu", long_name="predicted 1-sigma uncertainty on salinity")
        data_vars["density"] = _float_var(
            dims3, field["density"], units="kg m-3", long_name="sea water density from EOS-80",
            standard_name="sea_water_density")

    attrs = {
        "title": "OceanEmbed reconstructed subsurface temperature (TS-Cast-NIO v2)",
        "Conventions": "CF-1.8",
        "institution": "SIH26066 OceanEmbed",
        "date": str(field["date"]),
        # The bundle date and the requested date are DIFFERENT things and are never merged. The
        # `time` coordinate is the date actually reconstructed; a request that snapped is visible in
        # days_from_requested, which comes through the provenance block.
        "summary": ("Temperature reconstructed at 15 standard depths from surface satellite "
                    "observations. NaN is land or below the seafloor."),
    }
    attrs.update(prov.as_netcdf_attrs(field.get("provenance")))
    if stage != 2 or field.get("salinity") is None:
        attrs["stage2_variables"] = ("absent: this is a stage-1 checkpoint, which predicts "
                                     "temperature only. No salinity or density grid is written "
                                     "rather than an all-NaN one.")
    if extra_attrs:
        attrs.update(prov.as_netcdf_attrs(extra_attrs))

    return xr.Dataset(
        data_vars=data_vars,
        coords={
            "lat": ("lat", np.asarray(base.LAT, dtype="float64"),
                    {"units": "degrees_north", "standard_name": "latitude"}),
            "lon": ("lon", np.asarray(base.LON, dtype="float64"),
                    {"units": "degrees_east", "standard_name": "longitude"}),
            "depth": ("depth", np.asarray(config.DEPTHS, dtype="float64"),
                      {"units": "m", "standard_name": "depth", "positive": "down"}),
        },
        attrs=attrs,
    )


def _encoding(ds) -> dict:
    """Explicit _FillValue on every float variable.

    Left to the default, a reader can turn an untouched cell into 0. Here NaN means land or below
    the seafloor and must survive the file as NaN.
    """
    return {name: {"_FillValue": np.nan} for name, v in ds.data_vars.items()
            if np.issubdtype(v.dtype, np.floating)}


def write_netcdf(ds, path: str) -> str:
    """The ONLY place `to_netcdf` is called for a reconstruction."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    ds.to_netcdf(path, engine=ENGINE, encoding=_encoding(ds))
    return path


def to_bytes(ds) -> bytes:
    """In-memory NetCDF, for a browser download that must not touch disk."""
    return bytes(ds.to_netcdf(engine=ENGINE, encoding=_encoding(ds)))


def export_field(predictor, date, path: str, *, batch_size: int = 512) -> dict:
    """predict_field -> Dataset -> file. Returns what was written, with timings.

    Timings are returned rather than printed so a caller can record them; `predict_seconds` is the
    number that replaces the unmeasured estimate that used to sit in `field.py`'s docstring.
    """
    import time

    from phase2.tscast_nio.field import predict_field

    t0 = time.perf_counter()
    field = predict_field(predictor, date, batch_size=batch_size)
    t_predict = time.perf_counter() - t0

    t0 = time.perf_counter()
    ds = field_to_xarray(field)
    t_build = time.perf_counter() - t0

    t0 = time.perf_counter()
    write_netcdf(ds, path)
    t_write = time.perf_counter() - t0

    return {"path": path, "bytes": os.path.getsize(path), "date": str(field["date"]),
            "stage": int(field.get("stage", 1)),
            "variables": sorted(ds.data_vars),
            "predict_seconds": round(t_predict, 2),
            "build_seconds": round(t_build, 2),
            "write_seconds": round(t_write, 2)}
