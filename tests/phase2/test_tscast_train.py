"""Stage-1 training-utility tests, focused on the calibration measurement.

artifacts/mc_calibration.json carries an explicit warning:

    "ratio = RMSE(pred - argo) / RMS(mc_sigma), aggregated per depth THEN divided. Averaging
     per-point ratios inflates the shallow end roughly 2x because sigma is in the denominator;
     do not quote numbers produced that way."

If our ratio used the wrong method we would be comparing our number against MC-dropout's
1.56-3.54 on a different scale, and any apparent improvement would be an artefact of arithmetic.
"""
import numpy as np
import pytest

from phase2.tscast_nio import config
from phase2.tscast_nio.train.train_stage1 import calibration

N, DEP = 4000, config.N_DEPTHS


def _case(err_sd, sigma, rng_seed=0):
    rng = np.random.default_rng(rng_seed)
    truth = rng.normal(20, 3, (N, DEP))
    pred = truth + rng.normal(0, err_sd, (N, DEP))
    return pred, np.full((N, DEP), sigma), truth


def test_ratio_is_one_when_sigma_equals_the_real_error():
    pred, sigma, truth = _case(err_sd=1.2, sigma=1.2)
    for v in calibration(pred, sigma, truth).values():
        assert v["ratio"] == pytest.approx(1.0, abs=0.05)


def test_ratio_above_one_means_overconfident():
    """MC-dropout's failure mode: sigma too NARROW. Must read > 1, matching D-016's convention."""
    pred, sigma, truth = _case(err_sd=2.0, sigma=1.0)
    for v in calibration(pred, sigma, truth).values():
        assert v["ratio"] > 1.5, "an under-stated sigma must read ABOVE 1"


def test_ratio_below_one_means_underconfident():
    pred, sigma, truth = _case(err_sd=0.5, sigma=2.0)
    for v in calibration(pred, sigma, truth).values():
        assert v["ratio"] < 0.5, "an over-stated sigma must read BELOW 1"


def test_uses_aggregate_then_divide_not_the_mean_of_per_point_ratios():
    """The exact method mc_calibration.json warns about. With a heavy-tailed sigma the two
    disagree badly, and only the aggregate form is comparable to the published 1.56-3.54."""
    rng = np.random.default_rng(3)
    truth = np.zeros((N, DEP))
    pred = rng.normal(0, 1.0, (N, DEP))
    sigma = np.abs(rng.lognormal(0.0, 0.9, (N, DEP))) + 0.05     # heavy-tailed, some tiny values

    got = calibration(pred, sigma, truth)[config.DEPTHS[3]]["ratio"]

    k = 3
    aggregate = (np.sqrt(np.mean((pred[:, k] - truth[:, k]) ** 2))
                 / np.sqrt(np.mean(sigma[:, k] ** 2)))
    per_point = np.mean(np.abs(pred[:, k] - truth[:, k]) / sigma[:, k])

    assert got == pytest.approx(aggregate, abs=1e-3)
    assert abs(aggregate - per_point) > 0.2, (
        "this fixture no longer separates the two methods, so the test proves nothing")


def test_depths_with_too_few_samples_are_omitted_not_reported_as_zero():
    """A calibration ratio computed from a handful of floats reads as solid unless it is absent."""
    rng = np.random.default_rng(5)
    truth = rng.normal(20, 3, (10, DEP))
    pred = truth + 0.5
    sigma = np.full((10, DEP), 0.5)
    assert calibration(pred, sigma, truth) == {}, "n=10 is too few to quote a calibration ratio"


def test_below_seafloor_nans_are_excluded_from_the_ratio():
    pred, sigma, truth = _case(err_sd=1.0, sigma=1.0)
    truth[:, -1] = np.nan                     # 1000 m below the sea floor everywhere
    out = calibration(pred, sigma, truth)
    assert config.DEPTHS[-1] not in out
    assert config.DEPTHS[0] in out
