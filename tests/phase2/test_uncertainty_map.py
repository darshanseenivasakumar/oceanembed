"""The uncertainty page's claims, checked against the artifact and the model. Unit A (Arjhun).

The failure worth catching here is not a crash. It is a page titled "uncertainty" that renders the
RAW network variance while its caption says calibrated -- a wrong claim about the model's own
honesty, on the one page whose whole subject is honesty.

The build spec's acceptance check for this feature was "sigma range at the rendered depth is finite
and within the calibration artifact's known range (~0.89-1.46)". Those are dimensionless SCALE
FACTORS that multiply sigma; sigma itself is in degC. The check as written compares two different
quantities and would pass or fail for the wrong reason. What is checked instead: that the sigma the
page draws is the raw sigma multiplied by exactly those factors.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.tscast_nio import config as v2config

pytest.importorskip("torch")

DATE = "2026-05-15"
CAL_PATH = base.art("uncertainty_calibration.json")


def _have_model():
    return (os.path.exists(base.art("tscast_stage1.pt"))
            and os.path.isdir(os.path.join("data", "processed", "daily_sat", "v001")))


pytestmark = pytest.mark.skipif(
    not _have_model(), reason="checkpoint or satellite bundle not on this machine")


@pytest.fixture(scope="module")
def cal():
    if not os.path.exists(CAL_PATH):
        pytest.skip("no calibration artifact on this machine")
    with open(CAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fields():
    """The shipped field, and the same field with calibration switched off.

    Two whole-field reconstructions, so this is the slow test in the file -- but it is the only way
    to prove the multiplication actually happened rather than trusting a boolean flag that another
    boolean flag sets.
    """
    from phase2.tscast_nio import field_cache as FC
    from phase2.tscast_nio.field import predict_field

    p = FC.get_predictor(1)
    calibrated = predict_field(p, DATE)
    saved = getattr(p, "calibration", None)
    if not saved:
        pytest.skip("the loaded predictor carries no calibration to switch off")
    try:
        p.calibration = None
        raw = predict_field(p, DATE)
    finally:
        p.calibration = saved
    return calibrated, raw


# ==================================================== is it calibrated at all

def test_the_shipped_field_reports_its_sigma_as_calibrated(fields):
    """The page reads this flag rather than assuming. If it ever goes False the page must say so
    in a warning, so a silent flip here would be a silent downgrade there."""
    calibrated, _ = fields
    assert calibrated["provenance"]["sigma_is_calibrated"] is True, (
        calibrated["provenance"].get("sigma_calibration_note"))


def test_switching_the_calibration_off_is_visible_in_the_provenance(fields):
    """The control for the test above: the flag must be capable of being False, or asserting it is
    True proves nothing."""
    _, raw = fields
    assert raw["provenance"]["sigma_is_calibrated"] is False
    assert "no calibration" in raw["provenance"]["sigma_calibration_note"].lower()


# ==================================================== the multiplication itself

def test_the_sigma_on_screen_is_the_raw_sigma_times_the_published_per_depth_scale(fields, cal):
    """The real acceptance check for this feature.

    Not "sigma looks plausible" -- sigma always looks plausible. The ratio of what the page draws
    to what the network emitted must equal, depth by depth, the factors recorded in the artifact.
    """
    calibrated, raw = fields
    scales = cal["scales"]
    assert len(scales) == v2config.N_DEPTHS

    for k, z in enumerate(v2config.DEPTHS):
        want = float(scales.get(str(int(z)), scales.get(int(z))))
        a = np.asarray(calibrated["sigma"])[:, :, k]
        b = np.asarray(raw["sigma"])[:, :, k]
        both = np.isfinite(a) & np.isfinite(b) & (b > 0)
        assert both.sum() > 100, f"{z} m: too few cells to compare"
        ratio = a[both] / b[both]
        assert np.allclose(ratio, want, rtol=1e-5), (
            f"{z} m: page shows raw x {ratio.mean():.5f}, artifact says x {want:.5f}")


def test_calibration_does_not_move_the_temperature_only_the_uncertainty(fields):
    """A scale factor applied to the wrong array would change the prediction itself, which nothing
    downstream could catch -- the field would still be a plausible ocean."""
    calibrated, raw = fields
    a, b = calibrated["temperature"], raw["temperature"]
    assert np.array_equal(np.isfinite(a), np.isfinite(b))
    both = np.isfinite(a)
    assert np.array_equal(a[both], b[both]), "calibration altered the temperature field"


# ==================================================== what the map draws

def test_sigma_is_finite_and_strictly_positive_wherever_there_is_water(fields):
    """A zero or negative sigma would render as maximum confidence -- the most dangerous possible
    value to fabricate on a page about doubt."""
    calibrated, _ = fields
    sig = np.asarray(calibrated["sigma"])
    temp = np.asarray(calibrated["temperature"])
    water = np.isfinite(temp)
    assert water.sum() > 100_000
    assert np.isfinite(sig[water]).all(), "a water cell has no sigma"
    assert (sig[water] > 0).all(), "a water cell has sigma <= 0"


def test_sigma_is_absent_exactly_where_temperature_is(fields):
    """Land and below-seafloor must be blank in BOTH, or the map draws a confidence for a cell it
    has no prediction for."""
    calibrated, _ = fields
    assert np.array_equal(np.isfinite(np.asarray(calibrated["sigma"])),
                          np.isfinite(np.asarray(calibrated["temperature"])))


def test_the_page_can_claim_the_peak_sits_at_the_thermocline(fields):
    """The page's `how_to_read` states the uncertainty peak is at the thermocline. That is a claim
    about the ocean, so it is checked rather than asserted in prose: the basin-median sigma must be
    largest somewhere in 50-200 m, the depth band where temperature falls fastest here.

    Measured 2026-09-05 on 2026-06-23: peak at 100 m (median 1.197 degC), minimum at 500 m (0.265).
    If this ever moves out of that band the caption is wrong and needs rewriting, not relaxing.
    """
    calibrated, _ = fields
    sig = np.asarray(calibrated["sigma"])
    med = np.array([np.median(sig[:, :, k][np.isfinite(sig[:, :, k])])
                    for k in range(v2config.N_DEPTHS)])
    peak = float(v2config.DEPTHS[int(np.argmax(med))])
    assert 50.0 <= peak <= 200.0, f"median sigma peaks at {peak} m, outside the thermocline band"
    assert med.max() > 2.0 * med.min(), "sigma barely varies with depth -- the panel says nothing"


def test_the_largest_calibration_correction_is_also_at_the_thermocline(cal):
    """The page tells a reader the biggest correction is at the thermocline. Two independent
    signals -- the raw model is least certain there AND was most overconfident there -- and the
    page states both, so both are pinned."""
    scales = {int(k): float(v) for k, v in cal["scales"].items()}
    worst = max(scales, key=lambda z: scales[z])
    assert 50 <= worst <= 200, f"largest scale is at {worst} m"
    assert scales[worst] > 1.2


# ==================================================== the numbers the page quotes about itself

def test_the_page_quotes_a_coverage_that_is_below_nominal_and_says_so(cal):
    """A page about uncertainty that overstated its own uncertainty would be self-refuting. These
    are read from the artifact at render time, never hardcoded, so this test guards the CLAIM --
    that the gap is real and worth displaying -- rather than the digits."""
    after = cal["summary_after"]
    assert after["cov2_mean"] < after["target_cov2"], (
        "coverage now meets nominal -- the page's 'improved, not calibrated' wording is stale")
    assert 0.85 < after["cov2_mean"] < 0.95
    assert cal["n_eval_profiles"] > 100
    assert cal["split"], "the fit/eval split date must be stated or the coverage means nothing"


def test_the_calibration_was_fitted_and_scored_on_disjoint_data(cal):
    """Coverage measured on the profiles the scales were fitted to would be meaningless."""
    assert cal["n_fit_profiles"] > 0 and cal["n_eval_profiles"] > 0
    assert cal["method_used"] in ("coverage", "variance")
    assert cal.get("is_shipped_model") is True
