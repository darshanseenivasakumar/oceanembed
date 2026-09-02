"""The field must equal the point, cell for cell.

`predict_field` batches the whole grid; `TSCastPredictor.reconstruct` answers one cell. They are
two paths to the same number, and the 3-D cube shows one while the Profile tab shows the other --
on the same screen. If they ever disagree, a jury sees two different oceans and neither of us
would notice, because both look plausible.

This is the same class of failure as the GLORYS-fed dashboard (8.01 degC at 100 m, no error) and
the scorer that could not reproduce a checkpoint's own RMSE. Both were caught by comparison, not
by anything raising.
"""
import numpy as np
import pytest

from oceanembed.utils import grids

pytest.importorskip("torch")


@pytest.fixture(scope="module")
def predictor():
    import os

    from oceanembed import config as base
    if not os.path.exists(base.art("tscast_stage1.pt")):
        pytest.skip("no shipped checkpoint on this machine")
    from phase2.tscast_nio.inference import TSCastPredictor
    return TSCastPredictor()


@pytest.fixture(scope="module")
def field(predictor):
    from phase2.tscast_nio.field import predict_field
    return predict_field(predictor, "2026-05-15")


def test_field_temperature_equals_point_temperature(predictor, field):
    """The number the cube shows at a cell IS the number the profile shows there."""
    i, j = grids.nearest_lat_index(15.0), grids.nearest_lon_index(68.0)
    point = predictor.reconstruct(15.0, 68.0, "2026-05-15")["temperature"]
    col = field["temperature"][i, j, :]
    for k, (a, b) in enumerate(zip(point, col)):
        if a is None or not np.isfinite(b):
            continue
        assert abs(a - b) < 1e-3, f"depth index {k}: point {a} vs field {b}"


def test_field_sigma_equals_point_sigma(predictor, field):
    """Calibration is decided by output._calibration_applies_to. The field once made that decision
    itself, checked a key the raw artifact does not have, and silently carried RAW sigma while the
    point record beside it carried CALIBRATED sigma."""
    i, j = grids.nearest_lat_index(15.0), grids.nearest_lon_index(68.0)
    point = predictor.reconstruct(15.0, 68.0, "2026-05-15")["sigma_t"]
    col = field["sigma"][i, j, :]
    for k, (a, b) in enumerate(zip(point, col)):
        if a is None or not np.isfinite(b):
            continue
        assert abs(a - b) < 1e-3, f"depth index {k}: point sigma {a} vs field sigma {b}"


def test_the_field_says_which_inputs_made_it(field):
    """A cube that cannot name its input source is a cube nobody can defend."""
    p = field["provenance"]
    assert p["input_source"] == "satellite"
    assert p["bundle"] and "daily_sat" in p["bundle"]
    assert isinstance(p["sigma_is_calibrated"], bool)
    assert p["sigma_calibration_note"]


def test_land_and_below_seafloor_are_nan_not_numbers(field):
    """Filling them would be inventing water."""
    T, land, valid = field["temperature"], field["land_mask"], field["valid_mask"]
    assert np.all(np.isnan(T[land])), "land carries a temperature"
    assert np.all(np.isnan(T[~valid])), "an invalid cell carries a temperature"
    assert np.isfinite(T[valid]).all(), "a valid ocean cell is NaN"


def test_predicting_a_field_does_not_mutate_the_predictor(predictor, field):
    """`predict_field` borrows ds.index. If it did not restore it, every later point prediction
    would silently answer for the wrong cell."""
    before = predictor.ds.index.copy()
    from phase2.tscast_nio.field import predict_field
    predict_field(predictor, "2026-05-15")
    assert np.array_equal(predictor.ds.index, before)
