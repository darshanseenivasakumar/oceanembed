"""Exported NetCDF files, written and read back. Owner: Unit A (Arjhun).

WHY THIS FILE EXISTS
Before 2026-09-05 **no test in this repo wrote a product file and read it back**, and
`heat_content.to_xarray` -- the only NetCDF writer -- had zero tests. The consequence was visible on
disk: the shipped `heat_content_2026-05-15.nc` carries seven global attributes and no checkpoint, no
bundle, no input_source, no code_commit. Nothing failed, because nothing looked.

A product file is the one artifact that travels without us standing next to it. These tests are the
standing-next-to-it.

Synthetic arrays throughout, so this runs on any machine with no checkpoint and no bundle. The
real-model round trip lives at the bottom and skips when the checkpoint is absent.
"""
from __future__ import annotations

import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from oceanembed import config as base           # noqa: E402
from phase2.export import netcdf as X           # noqa: E402
from phase2.tscast_nio import config, provenance as P   # noqa: E402

NLAT, NLON, ND = len(base.LAT), len(base.LON), config.N_DEPTHS


def _provenance(**over):
    b = {"model": "tscast-nio-stage1", "checkpoint_sha256": "a" * 64, "seed": 42,
         "T_SEQ": 11, "P": 17, "encoder": "cnn3d", "input_source": "satellite",
         "input_date": "2026-05-15", "clim_train_years": [2019, 2020, 2021],
         "code_commit": "abc1234", "bundle": "data/processed/daily_sat/v001",
         "sigma_is_calibrated": True, "sigma_calibration_note": "fitted on 3423 profiles"}
    b.update(over)
    return b


def _field(stage=1, **over):
    """A field shaped exactly like `predict_field`'s return, with land NaN in a known corner."""
    rng = np.random.default_rng(0)
    t = 25.0 + rng.normal(0, 1, (NLAT, NLON, ND))
    land = np.zeros((NLAT, NLON), bool)
    land[:5, :5] = True                                  # a known land block
    t[land] = np.nan
    valid = np.isfinite(t)
    f = {"date": "2026-05-15", "temperature": t, "sigma": np.abs(rng.normal(0.5, 0.1, t.shape)),
         "valid_mask": valid, "land_mask": land, "stage": stage,
         "salinity": None, "sigma_s": None, "density": None,
         "provenance": _provenance()}
    if stage == 2:
        f["salinity"] = 35.0 + rng.normal(0, 0.5, t.shape)
        f["sigma_s"] = np.abs(rng.normal(0.2, 0.05, t.shape))
        f["density"] = 1025.0 + rng.normal(0, 1, t.shape)
        f["salinity"][land] = np.nan
    f.update(over)
    return f


def _round_trip(tmp_path, field):
    ds = X.field_to_xarray(field)
    p = str(tmp_path / "out.nc")
    X.write_netcdf(ds, p)
    return xr.open_dataset(p)


# --------------------------------------------------------------------------- THE acceptance test


def test_provenance_survives_the_round_trip_and_is_equal(tmp_path):
    """The acceptance criterion, executable.

    "Exported NetCDF carries the full provenance block (input_source, bundle, checkpoint,
    sigma_is_calibrated)" -- asserted by reading the written file back, not by inspecting the
    Dataset in memory. A writer that builds the attrs correctly and then loses them on
    serialisation would pass the weaker check.
    """
    back = _round_trip(tmp_path, _field())
    for key in P.SCHEMA_V5_KEYS:
        assert key in back.attrs, f"§5 key {key!r} did not survive the write"
    assert back.attrs["input_source"] == "satellite"
    assert back.attrs["bundle"] == "data/processed/daily_sat/v001"
    assert back.attrs["checkpoint_sha256"] == "a" * 64
    assert back.attrs["sigma_is_calibrated"] == "true"
    assert back.attrs["clim_train_years"] == "2019, 2020, 2021"


def test_an_unrecorded_provenance_field_is_named_not_dropped(tmp_path):
    """Rule 8 in the artifact that leaves the building. A None must arrive as a stated absence, so a
    reader can tell "we did not record this" from "this file has no such concept"."""
    back = _round_trip(tmp_path, _field(provenance=_provenance(checkpoint_sha256=None)))
    assert "checkpoint_sha256" in back.attrs
    assert back.attrs["checkpoint_sha256"] == P.NOT_RECORDED


# --------------------------------------------------------------------------- shape and units


def test_depth_is_a_real_dimension_in_contract_order(tmp_path):
    back = _round_trip(tmp_path, _field())
    assert back["temperature"].dims == ("lat", "lon", "depth")
    assert back["temperature"].shape == (NLAT, NLON, ND)
    assert list(back["depth"].values) == [float(d) for d in config.DEPTHS], \
        "depths must be the frozen contract list, in order -- never a subset, never reordered"
    assert back["depth"].attrs["positive"] == "down"


def test_it_declares_the_convention_it_actually_follows(tmp_path):
    back = _round_trip(tmp_path, _field())
    assert back.attrs["Conventions"] == "CF-1.8"
    assert back["temperature"].attrs["standard_name"] == "sea_water_potential_temperature"
    assert back["temperature"].attrs["units"] == "degC"


# --------------------------------------------------------------------------- the three rule-8 traps


def test_land_stays_nan_and_never_becomes_zero(tmp_path):
    """The single most damaging thing this file could get wrong: a reader's default _FillValue
    turning a land cell into a 0 degC measurement."""
    field = _field()
    back = _round_trip(tmp_path, field)
    t = back["temperature"].values
    land = field["land_mask"]
    assert np.isnan(t[land]).all(), "land came back as a number"
    assert not (t[land] == 0).any()
    assert np.isfinite(t[~land]).all(), "ocean came back as NaN"
    assert X.NAN_COMMENT in back["temperature"].attrs["comment"]


def test_a_stage1_file_has_no_salinity_variable_at_all(tmp_path):
    """An all-NaN salinity grid would assert "this file has salinity, missing everywhere". A
    stage-1 checkpoint predicts temperature only, so the variable is absent and the file says why."""
    back = _round_trip(tmp_path, _field(stage=1))
    for absent in ("salinity", "salinity_uncertainty", "density"):
        assert absent not in back.data_vars
    assert "stage2_variables" in back.attrs
    assert "absent" in back.attrs["stage2_variables"]


def test_a_stage2_file_carries_salinity_and_density(tmp_path):
    back = _round_trip(tmp_path, _field(stage=2))
    for present in ("salinity", "salinity_uncertainty", "density"):
        assert present in back.data_vars
    assert back["salinity"].attrs["units"] == "psu"
    assert back["density"].attrs["units"] == "kg m-3"
    assert "stage2_variables" not in back.attrs


def test_masks_round_trip_as_flags_not_as_numbers(tmp_path):
    """NetCDF has no bool. A silent float cast is how a mask stops being a mask."""
    field = _field()
    back = _round_trip(tmp_path, field)
    assert back["land_mask"].dtype == np.int8
    assert back["land_mask"].attrs["flag_meanings"] == "ocean land"
    assert np.array_equal(back["land_mask"].values.astype(bool), field["land_mask"])
    assert np.array_equal(back["valid_mask"].values.astype(bool), field["valid_mask"])


def test_the_calibration_caveat_travels_on_the_uncertainty_variable(tmp_path):
    """A reader who slices out sigma must not lose the caveat with it."""
    back = _round_trip(tmp_path, _field())
    a = back["temperature_uncertainty"].attrs
    assert a["is_calibrated"] == "true"
    assert "3423" in a["calibration_note"]


def test_a_wrong_shape_is_refused_not_reshaped(tmp_path):
    with pytest.raises(ValueError, match="expected"):
        X.field_to_xarray(_field(temperature=np.zeros((10, 10, ND))))


def test_to_bytes_produces_a_readable_file(tmp_path):
    """The download-button path must produce the same thing the disk path does."""
    raw = X.to_bytes(X.field_to_xarray(_field()))
    assert isinstance(raw, bytes) and len(raw) > 1000
    p = tmp_path / "from_bytes.nc"
    p.write_bytes(raw)
    back = xr.open_dataset(str(p))
    assert back.attrs["input_source"] == "satellite"
    assert back["temperature"].shape == (NLAT, NLON, ND)


# --------------------------------------------------------------------------- the real model


@pytest.mark.skipif(not __import__("os").path.exists(base.art("tscast_stage1.pt")),
                    reason="no shipped checkpoint on this machine")
def test_the_exported_file_matches_the_field_it_came_from(tmp_path):
    """The only check that catches a STALE provenance string: the sha in the file must equal a hash
    computed here and now, not one carried forward from an earlier run."""
    pytest.importorskip("torch")
    from phase2.tscast_nio.field import predict_field
    from phase2.tscast_nio.inference import TSCastPredictor

    pred = TSCastPredictor()
    field = predict_field(pred, "2026-05-15")
    ds = X.field_to_xarray(field)
    p = str(tmp_path / "real.nc")
    X.write_netcdf(ds, p)
    back = xr.open_dataset(p)

    a, b = back["temperature"].values, field["temperature"].astype("float32")
    assert np.array_equal(np.isnan(a), np.isnan(b)), "the NaN pattern changed through the file"
    assert np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], atol=1e-4)
    assert back.attrs["input_source"] == "satellite"
    assert back.attrs["checkpoint_sha256"] == P.checkpoint_sha256(pred.checkpoint_path)
