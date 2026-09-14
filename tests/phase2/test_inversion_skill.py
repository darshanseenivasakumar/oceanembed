"""Inversion skill metrics and the pre-registered adopt/reject rule (E-INV-00) -- synthetic."""
from __future__ import annotations

import numpy as np
import pytest

from phase2.derived import inversion_skill as SK

MODEL = np.array([0.5, 0.0, 0.3, 0.1, np.nan])
TRUTH = np.array([0.4, 0.3, 0.0, 0.05, 0.6])


def test_contingency_counts_hits_misses_and_false_alarms_at_the_threshold():
    c = SK.contingency(MODEL, TRUTH, threshold=0.2)
    assert (c["hits"], c["misses"], c["false_alarms"], c["correct_negatives"]) == (1, 2, 1, 1)
    assert c["pod"] == pytest.approx(1 / 3) and c["far"] == pytest.approx(0.5)
    assert c["csi"] == pytest.approx(0.25)
    assert c["n"] == 5 and c["threshold"] == 0.2


def test_contingency_drops_invalid_columns():
    valid = np.array([True, True, True, True, False])
    c = SK.contingency(MODEL, TRUTH, threshold=0.2, valid=valid)
    assert c["n"] == 4 and c["misses"] == 1


def test_amplitude_stats_use_only_truth_present_columns():
    s = SK.amplitude_stats(MODEL, TRUTH, threshold=0.2)
    # truth-present: idx 0 (0.4), idx 1 (0.3); idx 4 has a NaN model value -> dropped
    assert s["n"] == 2
    assert s["bias"] == pytest.approx(((0.5 - 0.4) + (0.0 - 0.3)) / 2)
    assert s["rmse"] == pytest.approx(np.sqrt(((0.1) ** 2 + (0.3) ** 2) / 2))
    assert s["mean_truth"] == pytest.approx(0.35)
    assert s["bias_fraction"] == pytest.approx(s["bias"] / 0.35)


def test_amplitude_stats_with_nothing_present_are_none_not_zero():
    s = SK.amplitude_stats(np.array([0.0, 0.1]), np.array([0.0, 0.1]), threshold=0.2)
    assert s["n"] == 0 and s["bias"] is None and s["rmse"] is None


def test_depth_error_uses_only_columns_present_in_both():
    md = np.array([50.0, 30.0, np.nan, 75.0])
    td = np.array([30.0, np.nan, 50.0, 100.0])
    both = np.array([True, False, False, True])
    d = SK.depth_stats(md, td, both)
    assert d["n"] == 2 and d["mae"] == pytest.approx((20.0 + 25.0) / 2)


def test_three_seed_summary_refuses_fewer_than_three_seeds():
    s = SK.three_seed_summary({42: 0.31, 43: 0.33})
    assert s["complete"] is False and s["n"] == 2
    s = SK.three_seed_summary({42: 0.30, 43: 0.32, 44: 0.31})
    assert s["complete"] is True
    assert s["mean"] == pytest.approx(0.31) and s["spread"] == pytest.approx(0.02)


CONTROL = {42: {"csi": 0.30, "headline_rmse": 0.9078},
           43: {"csi": 0.32, "headline_rmse": 0.9047},
           44: {"csi": 0.31, "headline_rmse": 0.9084}}


def _leg(csi, rmse):
    return {s: {"csi": c, "headline_rmse": r} for s, c, r in zip((42, 43, 44), csi, rmse)}


def test_adopt_when_every_seed_improves_beyond_control_noise_and_headline_holds():
    v = SK.adopt(_leg((0.40, 0.42, 0.41), (0.9080, 0.9050, 0.9090)), CONTROL)
    assert v["verdict"] == SK.ADOPTED and v["adopted"] is True


def test_reject_when_one_seed_does_not_improve():
    v = SK.adopt(_leg((0.40, 0.31, 0.41), (0.9080, 0.9050, 0.9090)), CONTROL)
    assert v["verdict"] == SK.REJECTED and v["adopted"] is False
    assert any("every seed" in r for r in v["reasons"])


def test_reject_when_the_mean_gain_is_inside_control_noise():
    v = SK.adopt(_leg((0.305, 0.325, 0.315), (0.9080, 0.9050, 0.9090)), CONTROL)
    assert v["verdict"] == SK.REJECTED
    assert any("noise" in r for r in v["reasons"])


def test_reject_when_the_headline_gets_worse_than_the_seed_spread():
    v = SK.adopt(_leg((0.40, 0.42, 0.41), (0.9150, 0.9150, 0.9150)), CONTROL)
    assert v["verdict"] == SK.REJECTED
    assert any("headline" in r for r in v["reasons"])


def test_not_a_result_on_fewer_than_three_seeds():
    two = {42: {"csi": 0.40, "headline_rmse": 0.90}, 43: {"csi": 0.42, "headline_rmse": 0.90}}
    v = SK.adopt(two, CONTROL)
    assert v["verdict"] == SK.NOT_A_RESULT and v["adopted"] is False


def test_headline_tolerance_is_the_measured_seed_spread():
    assert SK.HEADLINE_TOLERANCE_DEGC == 0.004
