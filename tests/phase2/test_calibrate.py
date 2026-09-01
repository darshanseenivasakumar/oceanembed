"""Phase-6 calibration tests.

Each one encodes a way calibration can look like it worked and not have.
"""
import numpy as np
import pytest

from phase2.tscast_nio import calibrate, config

DEP = config.N_DEPTHS
RNG = np.random.default_rng(0)


def _synth(n, sigma_true, sigma_claimed):
    """Errors really distributed N(0, sigma_true), model claiming sigma_claimed."""
    truth = RNG.normal(20, 3, (n, DEP))
    mu = truth + RNG.normal(0, sigma_true, (n, DEP))
    return mu, np.full((n, DEP), float(sigma_claimed)), truth


def test_a_perfectly_calibrated_model_gets_scale_one():
    mu, sig, truth = _synth(4000, 1.0, 1.0)
    s = calibrate.fit_scales(mu, sig, truth)["scales"]
    assert all(abs(v - 1.0) < 0.05 for v in s.values())


def test_an_overconfident_model_is_widened():
    """Claims 0.5 when the real error is 2.0 -- the mixed-layer failure mode."""
    mu, sig, truth = _synth(4000, 2.0, 0.5)
    s = calibrate.fit_scales(mu, sig, truth)["scales"]
    assert all(3.5 < v < 4.5 for v in s.values()), f"expected ~4x widening, got {s[0]:.2f}"


def test_an_underconfident_model_is_narrowed():
    """Claims 3.0 when the real error is 1.0 -- the 1000 m failure mode."""
    mu, sig, truth = _synth(4000, 1.0, 3.0)
    s = calibrate.fit_scales(mu, sig, truth)["scales"]
    assert all(0.25 < v < 0.40 for v in s.values())


def test_scaling_actually_moves_coverage_to_the_gaussian_target():
    """The point of the phase. Fit on one half, evaluate on the OTHER half."""
    mu, sig, truth = _synth(8000, 2.0, 0.5)
    fit, ev = slice(0, 4000), slice(4000, 8000)
    before = calibrate.summarise(calibrate.coverage(mu[ev], sig[ev], truth[ev]))
    s = calibrate.fit_scales(mu[fit], sig[fit], truth[fit])["scales"]
    after = calibrate.summarise(calibrate.coverage(mu[ev], calibrate.apply_scales(sig[ev], s),
                                                   truth[ev]))
    assert before["cov1_mean"] < 0.30, "fixture is not overconfident enough to be a test"
    assert abs(after["cov1_mean"] - 0.683) < 0.03, f"cov1 {after['cov1_mean']} != 0.683"
    assert abs(after["cov2_mean"] - 0.954) < 0.02


def test_a_depth_with_too_few_profiles_is_not_calibrated():
    """A scale factor from a handful of floats reads as solid unless it is simply absent."""
    mu, sig, truth = _synth(10, 2.0, 0.5)
    out = calibrate.fit_scales(mu, sig, truth)
    assert all(v is None for v in out["scales"].values())
    assert all(n == 10 for n in out["n"].values())


def test_uncalibrated_depths_pass_through_unchanged_rather_than_being_dropped():
    sig = np.full((5, DEP), 2.0)
    scales = {d: None for d in config.DEPTHS}
    scales[config.DEPTHS[0]] = 3.0
    out = calibrate.apply_scales(sig, scales)
    assert out[0, 0] == pytest.approx(6.0)
    assert out[0, 1] == pytest.approx(2.0), "an uncalibrated depth must keep its raw sigma"


def test_pit_is_uniform_when_calibrated_and_u_shaped_when_overconfident():
    """PIT shape says WHICH way sigma is wrong; a single coverage number does not."""
    mu, sig, truth = _synth(6000, 1.0, 1.0)
    good = calibrate.pit(mu, sig, truth)
    mu, sig, truth = _synth(6000, 3.0, 0.6)
    bad = calibrate.pit(mu, sig, truth)
    assert good["uniform_deviation"] < 0.01
    assert bad["uniform_deviation"] > good["uniform_deviation"] * 3
    f = bad["fraction"]
    assert f[0] + f[-1] > 0.5, "an overconfident model piles PIT mass in both tails"


def test_pit_detects_a_BIAS_that_variance_scaling_cannot_fix():
    """A sloped PIT means the MEAN is wrong. Widening sigma hides it without fixing it, so the
    diagnostic has to be able to say so."""
    truth = RNG.normal(20, 3, (4000, DEP))
    mu = truth + 2.0                                   # systematically warm, no noise
    sig = np.full((4000, DEP), 1.0)
    f = calibrate.pit(mu, sig, truth)["fraction"]
    assert f[0] > 0.8, "a pure bias should push nearly all PIT mass to one end"


def test_nan_truth_is_excluded_not_counted_as_agreement():
    mu, sig, truth = _synth(500, 1.0, 1.0)
    truth[:, -1] = np.nan                              # below the sea floor
    out = calibrate.fit_scales(mu, sig, truth)
    assert out["scales"][config.DEPTHS[-1]] is None
    assert out["n"][config.DEPTHS[-1]] == 0
    assert out["n"][config.DEPTHS[0]] == 500


def test_the_two_methods_agree_when_residuals_really_are_gaussian():
    """They must only diverge because of tail shape, not because one of them is wrong."""
    mu, sig, truth = _synth(8000, 2.0, 0.5)          # Gaussian errors by construction
    v = calibrate.fit_scales(mu, sig, truth, method="variance")["scales"]
    c = calibrate.fit_scales(mu, sig, truth, method="coverage")["scales"]
    for d in config.DEPTHS:
        assert abs(v[d] - c[d]) / v[d] < 0.06, f"depth {d}: {v[d]:.3f} vs {c[d]:.3f}"


def test_heavy_tails_make_variance_matching_OVERSHOOT_central_coverage():
    """The measured failure, reproduced. Student-t residuals: matching the second moment leaves
    too much mass inside +/-1 sigma, because the variance is carried by the tails."""
    n = 20000
    heavy = RNG.standard_t(df=3, size=(n, DEP))       # heavy-tailed, unit-ish scale
    truth = RNG.normal(20, 3, (n, DEP))
    mu = truth + heavy
    sig = np.ones((n, DEP))
    fit, ev = slice(0, n // 2), slice(n // 2, n)

    sv = calibrate.fit_scales(mu[fit], sig[fit], truth[fit], method="variance")["scales"]
    sc = calibrate.fit_scales(mu[fit], sig[fit], truth[fit], method="coverage")["scales"]
    cov_v = calibrate.summarise(calibrate.coverage(
        mu[ev], calibrate.apply_scales(sig[ev], sv), truth[ev]))["cov1_mean"]
    cov_c = calibrate.summarise(calibrate.coverage(
        mu[ev], calibrate.apply_scales(sig[ev], sc), truth[ev]))["cov1_mean"]

    assert cov_v > 0.72, f"variance matching should overshoot on heavy tails, got {cov_v}"
    assert abs(cov_c - 0.683) < 0.02, f"coverage matching should hit the target, got {cov_c}"


def test_an_unknown_method_is_refused():
    mu, sig, truth = _synth(200, 1.0, 1.0)
    with pytest.raises(ValueError, match="variance"):
        calibrate.fit_scales(mu, sig, truth, method="whatever")
