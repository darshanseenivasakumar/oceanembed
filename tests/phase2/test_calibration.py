"""F4 calibration tests. Owner: Unit A (Arjhun).

Two kinds here, deliberately separated:

  UNIT       — the code does what the code intends (shapes, guards, IO).
  SCIENTIFIC — the METHOD recovers a known truth and improves a real metric out of sample.

Only the second kind is evidence that recalibration works. PHASE2_STATUS.md keeps TESTED and
VALIDATED apart because passing either of these still does not mean the numbers are right on the
real ocean — that needs artifacts/argo_error_by_depth.json, which is gitignored and absent here.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from oceanembed import config
from phase2.reliability import calibration as cal

D = config.N_DEPTHS
RNG = np.random.default_rng(config.SEED)


def synthetic_case(n=4000, true_scale=None, sigma_level=0.30, seed=0):
    """Residuals drawn from N(0, (scale*sigma)^2) with a REPORTED sigma that is too small.

    This is the D-016 situation in miniature: the model claims `sigma_level`, reality is
    `true_scale` times worse. A correct estimator must recover `true_scale`.
    """
    rng = np.random.default_rng(seed)
    true_scale = np.full(D, 4.0) if true_scale is None else np.asarray(true_scale, dtype="float64")
    sigmas = np.abs(rng.normal(sigma_level, sigma_level * 0.15, (n, D)))
    residuals = rng.normal(0.0, 1.0, (n, D)) * sigmas * true_scale
    return residuals, sigmas, true_scale


# ============================================================ SCIENTIFIC
def test_recovers_a_known_overconfidence_factor():
    """THE core scientific check: if sigma is truly 4x too small, alpha must come back ~4."""
    residuals, sigmas, truth = synthetic_case(true_scale=np.full(D, 4.0))
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.allclose(res.alphas, truth, rtol=0.10), (
        f"estimator is biased: recovered {res.alphas[:3]} for a true factor of {truth[:3]}"
    )


def test_recovers_a_depth_varying_factor():
    """Miscalibration is depth-dependent — worst at the thermocline. One global factor would
    over-correct the surface, so the estimator must resolve depth structure."""
    truth = np.linspace(1.0, 5.0, D)          # mild at surface, severe at depth
    residuals, sigmas, _ = synthetic_case(true_scale=truth, seed=1)
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.allclose(res.alphas, truth, rtol=0.12)
    assert res.alphas[-1] > res.alphas[0] * 2, "depth structure was flattened"


def test_calibration_improves_ence_on_held_out_data():
    """The honest test: ENCE must fall on rows the factors were NOT fitted on."""
    residuals, sigmas, _ = synthetic_case(true_scale=np.full(D, 3.5), seed=2)
    res = cal.fit_from_samples(residuals, sigmas)
    assert res.ence_after < res.ence_before, (
        f"ENCE did not improve out of sample: {res.ence_before:.4f} -> {res.ence_after:.4f}"
    )
    assert res.ence_after < 0.15, f"still poorly calibrated after scaling: {res.ence_after:.4f}"


def test_calibration_ratio_moves_toward_one():
    """sigma/RMSE should approach 1 after scaling. <1 is the dangerous, overconfident side."""
    residuals, sigmas, _ = synthetic_case(true_scale=np.full(D, 4.0), seed=3)
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.nanmean(res.ratio_before) < 0.4, "test fixture is not overconfident to begin with"
    assert np.allclose(res.ratio_after, 1.0, atol=0.12), (
        f"post-calibration ratio off: {res.ratio_after}"
    )


def test_d016_thermocline_scenario():
    """The Phase-1 measurement, reproduced: sigma ~0.30 degC at 75 m, real error 1.22 degC.

    Numbers from docs/DECISIONS.md D-016 / predict.py's docstring, measured against 879 real
    Argo profiles. A correct method recovers ~4x and lands the corrected sigma on the measured
    error.
    """
    measured_error, reported_sigma = 1.22, 0.30
    rng = np.random.default_rng(4)
    n = 3000
    sigmas = np.full((n, D), reported_sigma)
    residuals = rng.normal(0.0, measured_error, (n, D))

    res = cal.fit_from_samples(residuals, sigmas)
    expected = measured_error / reported_sigma        # ~4.07
    assert np.allclose(res.alphas, expected, rtol=0.10), (
        f"expected ~{expected:.2f}x correction, got {res.alphas.mean():.2f}x"
    )
    corrected = float(np.mean(res.apply(sigmas)))
    assert abs(corrected - measured_error) < 0.15, (
        f"corrected sigma {corrected:.3f} should land near the measured error {measured_error}"
    )


def test_well_calibrated_input_is_left_alone():
    """A method that 'fixes' already-good uncertainty is broken. alpha must be ~1."""
    residuals, sigmas, _ = synthetic_case(true_scale=np.ones(D), seed=5)
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.allclose(res.alphas, 1.0, rtol=0.10)


def test_underconfident_input_is_scaled_down():
    """Calibration is two-sided: over-wide error bars are also wrong, just not dangerous."""
    residuals, sigmas, _ = synthetic_case(true_scale=np.full(D, 0.25), seed=6)
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.allclose(res.alphas, 0.25, rtol=0.15)
    assert (res.alphas < 1.0).all()


# ============================================================ HONESTY GUARDS
def test_summary_fit_is_never_marked_validated():
    """A summary cannot be held out, so it must refuse to claim validation."""
    rmse = np.linspace(0.3, 1.3, D)
    rmv = np.full(D, 0.30)
    res = cal.fit_from_summary(rmse, rmv)
    assert res.is_validated is False
    assert res.held_out is False
    assert "DESCRIPTIVE ONLY" in res.note


def test_summary_fit_ratio_after_is_one_by_construction_and_says_so():
    """ratio_after == 1 here proves nothing; the note must prevent it being read as success."""
    res = cal.fit_from_summary(np.linspace(0.3, 1.3, D), np.full(D, 0.30))
    assert np.allclose(res.ratio_after, 1.0)
    assert "proves nothing" in res.note
    assert res.ence_after is None, "ENCE needs per-sample binning; a summary cannot supply it"


def test_sample_fit_is_marked_validated():
    residuals, sigmas, _ = synthetic_case(seed=7)
    assert cal.fit_from_samples(residuals, sigmas).is_validated is True


def test_fit_and_eval_rows_are_disjoint():
    """Fitting and scoring the same rows would make any calibration look perfect."""
    residuals, sigmas, _ = synthetic_case(n=1000, seed=8)
    res = cal.fit_from_samples(residuals, sigmas, fit_frac=0.5)
    n_fit = int(res.fitted_on.split()[0])
    n_eval = int(res.evaluated_on.split()[0])
    assert n_fit + n_eval == 1000, "split lost or duplicated rows"
    assert n_fit > 0 and n_eval > 0


def test_sparse_depths_are_flagged():
    """0 m routinely has ~32 Argo obs against ~2,400 elsewhere (Phase-1 finding)."""
    residuals, sigmas, _ = synthetic_case(n=500, seed=9)
    residuals[:, 0] = np.nan          # simulate an almost-unsampled surface level
    sigmas[:, 0] = np.nan
    res = cal.fit_from_samples(residuals, sigmas)
    assert 0 in res.unreliable_depths


# ============================================================ UNIT
def test_apply_leaves_shape_and_scales_correctly():
    res = cal.fit_from_summary(np.full(D, 1.2), np.full(D, 0.3))
    sigma = np.full((7, D), 0.3, dtype="float32")
    out = res.apply(sigma)
    assert out.shape == (7, D) and out.dtype == np.float32
    assert np.allclose(out, 1.2, rtol=1e-4)


def test_apply_rejects_a_wrong_depth_axis():
    res = cal.fit_from_summary(np.full(D, 1.0), np.full(D, 1.0))
    with pytest.raises(AssertionError):
        res.apply(np.ones((4, D + 2), dtype="float32"))


def test_zero_sigma_does_not_produce_an_infinite_factor():
    residuals, sigmas, _ = synthetic_case(n=600, seed=10)
    sigmas[:, 2] = 0.0
    res = cal.fit_from_samples(residuals, sigmas)
    assert np.isfinite(res.alphas).all()
    assert res.alphas[2] == pytest.approx(1.0), "a depth with no usable sigma must default to no-op"


def test_ence_is_zero_for_perfectly_calibrated_data():
    rng = np.random.default_rng(11)
    sigmas = np.abs(rng.normal(1.0, 0.3, 6000))
    residuals = rng.normal(0.0, 1.0, 6000) * sigmas
    assert cal.ence(residuals, sigmas, n_bins=10) < 0.12


def test_ence_is_large_for_badly_calibrated_data():
    rng = np.random.default_rng(12)
    sigmas = np.full(6000, 0.3)
    residuals = rng.normal(0.0, 1.2, 6000)
    assert cal.ence(residuals, sigmas, n_bins=10) > 1.0


def test_ence_returns_nan_rather_than_a_number_it_cannot_support():
    assert np.isnan(cal.ence(np.array([0.1, 0.2]), np.array([0.3, 0.3])))


def test_rejects_mismatched_shapes():
    with pytest.raises(AssertionError):
        cal.fit_from_samples(np.zeros((10, D)), np.zeros((10, D - 1)))


def test_rejects_wrong_depth_count():
    with pytest.raises(AssertionError):
        cal.fit_from_samples(np.zeros((10, D - 3)), np.zeros((10, D - 3)))


# ============================================================ IO
def test_load_measured_error_explains_how_to_produce_a_missing_file():
    with pytest.raises(FileNotFoundError, match="eval_satellite_vs_argo"):
        cal.load_measured_error("/nonexistent/argo_error_by_depth.json")


def test_load_measured_error_reads_the_real_schema(tmp_path):
    """Schema copied from scripts/eval_satellite_vs_argo.py, not invented here."""
    p = tmp_path / "argo_error_by_depth.json"
    p.write_text(json.dumps({
        "measured_against": "independent Argo floats, test year",
        "n_profiles": 879,
        "depths": list(config.DEPTHS),
        "rmse_satellite": [round(0.3 + 0.05 * k, 3) for k in range(D)],
        "rmse_glorys": [round(0.31 + 0.05 * k, 3) for k in range(D)],
        "n_obs_per_depth": [32] + [2400] * (D - 1),
    }), encoding="utf-8")

    got = cal.load_measured_error(str(p), source="satellite")
    assert got["n_profiles"] == 879
    assert got["rmse"].shape == (D,)
    assert got["n_obs"][0] == 32


def test_load_measured_error_refuses_a_mismatched_depth_axis(tmp_path):
    """Aligning by position against a different depth list would silently pair 500 m with 700 m."""
    p = tmp_path / "argo_error_by_depth.json"
    p.write_text(json.dumps({
        "depths": [0, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500],   # the OLD 11-level set
        "rmse_satellite": [0.3] * 11,
        "n_obs_per_depth": [100] * 11,
    }), encoding="utf-8")
    with pytest.raises(AssertionError, match="depth axis"):
        cal.load_measured_error(str(p))


def test_null_entries_become_nan_not_zero(tmp_path):
    """A depth with no Argo coverage is unknown, not zero error."""
    p = tmp_path / "argo_error_by_depth.json"
    rmse = [None] + [0.5] * (D - 1)
    p.write_text(json.dumps({
        "depths": list(config.DEPTHS), "rmse_satellite": rmse,
        "n_obs_per_depth": [0] + [2400] * (D - 1),
    }), encoding="utf-8")
    got = cal.load_measured_error(str(p))
    assert np.isnan(got["rmse"][0]) and got["rmse"][1] == 0.5
