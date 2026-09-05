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


def test_provenance_names_the_promoted_run_not_unpromoted(field):
    """The shipped checkpoint IS promoted, so the panel a jury reads must say which run it came from.

    `promoted_from` lives in the metrics artifact, never in the checkpoint, so the original
    `predictor.meta.get("promoted_from")` was always None and every cube / cyclone provenance panel
    displayed "unpromoted" about the frozen, promoted model. Regression: this asserted the exact
    name that promotion recorded, so a silent fallback to "unpromoted" fails here.
    """
    import json
    from oceanembed import config as base

    with open(base.art("tscast_stage1_metrics.json"), encoding="utf-8") as f:
        expected = json.load(f)["promoted_from"]
    assert expected, "the shipped metrics artifact carries no promoted_from to check against"
    assert field["provenance"]["checkpoint"] == expected


def test_an_unpromoted_checkpoint_is_not_credited_with_the_promotion(predictor, tmp_path):
    """Reading the metrics file alone would pin the promotion onto ANY loaded checkpoint.

    A checkpoint whose bytes are not the ones promotion hashed must come back "unpromoted", or the
    provenance panel would launder an experimental model as the shipped one.
    """
    from phase2.tscast_nio.field import _promoted_from

    class _Impostor:
        checkpoint_path = str(tmp_path / "not_the_shipped_weights.pt")

    (tmp_path / "not_the_shipped_weights.pt").write_bytes(b"different bytes")
    assert _promoted_from(_Impostor()) == "unpromoted"
    assert _promoted_from(predictor) != "unpromoted", "the real one should still be credited"


# ==================================================== the device switch

def test_the_device_argument_moves_the_model_and_not_just_the_batch(predictor):
    """The bug a user found by clicking a toggle, as a test.

    `predict_field` sent the INPUT tensors to `device` and left the weights wherever they loaded --
    always CPU, since `TSCastPredictor` loads with `map_location="cpu"`. So `device="cuda"` raised
    `Input type (torch.cuda.FloatTensor) and weight type (torch.FloatTensor) should be the same`,
    and the parameter had never worked in the whole time it existed. It went unnoticed because
    nothing called it: the 4.1x speedup recorded in field.py's header was measured by moving the
    model by hand.

    Runs on CPU too. `device="cpu"` on a CPU-resident model is a no-op through the same code path,
    so the equality below still exercises the argument on any machine; only the speed comparison
    needs a GPU.
    """
    import torch

    from phase2.tscast_nio.field import predict_field

    home = next(predictor.model.parameters()).device
    explicit = predict_field(predictor, "2026-05-15", device=str(home))
    assert next(predictor.model.parameters()).device == home

    implicit = predict_field(predictor, "2026-05-15")
    a, b = explicit["temperature"], implicit["temperature"]
    assert np.array_equal(np.isfinite(a), np.isfinite(b))
    both = np.isfinite(a)
    assert np.allclose(a[both], b[both], atol=1e-6), "naming the resident device changed the answer"


@pytest.mark.skipif(
    not __import__("torch").cuda.is_available(), reason="no CUDA on this machine")
def test_a_cuda_reconstruction_agrees_with_the_cpu_one_and_leaves_the_model_at_home(predictor):
    """Two things at once, because they fail together.

    AGREEMENT: the exported NetCDF is always written on CPU while a page may render on GPU, so the
    two must not disagree by more than float32 noise or a reader comparing them sees two oceans.
    MEASURED 2026-09-05: max |CPU - CUDA| = 6.9e-4 degC over 153,291 cells, against a 0.9078 degC
    headline RMSE.

    RESTORATION: the predictor is a process-wide singleton shared by every page. Leaving it on the
    GPU would silently change the device of every later reconstruction, including the export --
    which field.py's header deliberately keeps on CPU so a file cannot differ in its last digits
    from the page beside it.
    """
    from phase2.tscast_nio.field import predict_field

    home = next(predictor.model.parameters()).device
    assert str(home) == "cpu", "the shipped predictor is expected to rest on CPU"

    cpu = predict_field(predictor, "2026-05-15")
    gpu = predict_field(predictor, "2026-05-15", device="cuda")

    assert str(next(predictor.model.parameters()).device) == "cpu", "left on the GPU"

    for key in ("temperature", "sigma"):
        a, b = cpu[key], gpu[key]
        assert np.array_equal(np.isfinite(a), np.isfinite(b)), f"{key}: NaN pattern differs"
        both = np.isfinite(a)
        worst = float(np.abs(a[both] - b[both]).max())
        assert worst < 1e-3, f"{key}: CPU and CUDA differ by {worst:.2e} degC"
