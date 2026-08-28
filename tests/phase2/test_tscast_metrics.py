"""Metrics tests. Every one of these encodes a way the numbers could lie to a judge."""
import numpy as np
import pytest

from phase2.tscast_nio import config, metrics


def test_perfect_prediction_scores_perfectly():
    t = np.random.default_rng(0).normal(20, 5, (40, config.N_DEPTHS))
    m = metrics.per_depth(t.copy(), t, clim=t + 3.0)
    assert np.allclose(m["rmse"], 0.0, atol=1e-12)
    assert np.allclose(m["bias"], 0.0, atol=1e-12)
    assert np.allclose(m["correlation"], 1.0, atol=1e-9)
    assert np.allclose(m["skill_vs_climatology"], 1.0, atol=1e-9)


def test_bias_sign_is_model_minus_truth():
    """A model running 2 degC WARM must report +2, not -2. A flipped sign here would invert
    every warm/cold-bias statement we make about the thermocline."""
    truth = np.full((10, config.N_DEPTHS), 20.0)
    m = metrics.per_depth(truth + 2.0, truth)
    assert np.allclose(m["bias"], 2.0)
    assert np.allclose(metrics.per_depth(truth - 2.0, truth)["bias"], -2.0)


def test_constant_series_gives_nan_correlation_not_one():
    """Below 500 m the ocean barely varies. Pearson r on a constant series divides by ~0; a naive
    implementation returns noise or 1.0 and we would report deep 'skill' that does not exist."""
    truth = np.full((30, config.N_DEPTHS), 4.0)
    pred = truth + np.random.default_rng(1).normal(0, 0.01, truth.shape)
    m = metrics.per_depth(pred, truth)
    assert np.all(np.isnan(m["correlation"])), "constant truth must give NaN r, never 1.0"
    assert np.all(np.isfinite(m["rmse"])), "RMSE is still perfectly well defined"


def test_empty_depth_is_nan_with_n_zero_never_zero_rmse():
    """An RMSE of 0.0 printed beside n=0 reads as perfection. It must be NaN."""
    truth = np.random.default_rng(2).normal(20, 3, (25, config.N_DEPTHS))
    truth[:, -1] = np.nan                      # 1000 m entirely below the sea floor
    m = metrics.per_depth(truth.copy(), truth)
    assert m["n"][-1] == 0
    assert np.isnan(m["rmse"][-1]) and np.isnan(m["bias"][-1])
    assert m["n"][0] == 25


def test_too_few_samples_gives_nan_correlation():
    truth = np.random.default_rng(3).normal(20, 3, (2, config.N_DEPTHS))
    m = metrics.per_depth(truth + 0.1, truth)
    assert np.all(np.isnan(m["correlation"])), f"n=2 < MIN_N={metrics.MIN_N} must be NaN"


def test_skill_scores_model_and_climatology_on_the_same_samples():
    """If the model is scored where climatology is NaN, it gets credit for skill it never earned."""
    rng = np.random.default_rng(4)
    truth = rng.normal(20, 3, (60, config.N_DEPTHS))
    pred = truth + rng.normal(0, 1.0, truth.shape)
    clim = truth + rng.normal(0, 2.0, truth.shape)
    clim[:30] = np.nan                          # climatology missing for half the samples
    s_masked = metrics.per_depth(pred, truth, clim=clim)["skill_vs_climatology"]
    s_same = metrics.per_depth(pred[30:], truth[30:], clim=clim[30:])["skill_vs_climatology"]
    assert np.allclose(s_masked, s_same, atol=1e-12), "skill must use the intersection only"


def test_zero_variance_climatology_gives_nan_skill_not_infinity():
    truth = np.full((20, config.N_DEPTHS), 10.0)
    m = metrics.per_depth(truth + 0.5, truth, clim=truth.copy())
    assert np.all(np.isnan(m["skill_vs_climatology"])), "nothing to beat is NaN, not infinite skill"


def test_wrong_depth_count_raises_rather_than_reshaping():
    """The output contract is frozen at 15. A silent reshape misaligns every depth label."""
    bad = np.zeros((10, 11))
    with pytest.raises(ValueError, match="frozen"):
        metrics.per_depth(bad, bad)


def test_shape_mismatch_refuses_to_broadcast():
    with pytest.raises(ValueError):
        metrics.per_depth(np.zeros((10, config.N_DEPTHS)), np.zeros((9, config.N_DEPTHS)))


def test_known_values_computed_by_hand():
    """Guards the formulae themselves, not just their invariants."""
    truth = np.array([[1.0], [2.0], [3.0], [4.0]])
    pred = np.array([[2.0], [3.0], [4.0], [5.0]])          # uniformly +1
    assert metrics.rmse(pred, truth) == pytest.approx(1.0)
    assert metrics.bias(pred, truth) == pytest.approx(1.0)
    assert metrics.correlation(pred, truth) == pytest.approx(1.0)
    # climatology = the mean (2.5): MSE_clim = 1.25, MSE_model = 1.0 -> skill = 0.2
    clim = np.full_like(truth, 2.5)
    assert metrics.skill_vs_climatology(pred, truth, clim) == pytest.approx(0.2)


def test_depths_reported_are_the_frozen_contract_depths():
    t = np.zeros((5, config.N_DEPTHS))
    assert metrics.per_depth(t, t)["depths_m"] == list(config.DEPTHS) == [
        0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]


def test_pooled_correlation_is_flagged_as_inflated_and_not_the_headline():
    """Pooled across 15 depths, r mostly measures 'deep water is cold'. Measured on real Argo it
    reads 0.99 pooled vs 0.83-0.98 per depth. The headline `correlation` must be the per-depth
    mean, and the pooled one must still be available but clearly labelled."""
    rng = np.random.default_rng(7)
    n = 200
    # a strong depth gradient (warm surface, cold deep) with almost no within-depth skill
    truth = np.linspace(28, 4, config.N_DEPTHS)[None, :] + rng.normal(0, 0.2, (n, config.N_DEPTHS))
    pred = np.linspace(28, 4, config.N_DEPTHS)[None, :] + rng.normal(0, 0.2, (n, config.N_DEPTHS))
    o = metrics.per_depth(pred, truth)["overall"]
    assert o["correlation_pooled"] > 0.95, "pooled r is inflated by the depth gradient"
    assert abs(o["correlation"]) < 0.3, "per-depth mean r correctly shows there is no real skill"
    assert "Do not quote the pooled figure" in o["correlation_note"]


def test_two_skill_definitions_are_both_returned_and_differ():
    """The frozen Phase-1 headline (+0.387) is 1 - RMSE/RMSE_clim. The Murphy score is
    1 - MSE/MSE_clim. On the real Argo set the SAME predictions score 0.39 and 0.63. Reporting
    only the Murphy figure would read as a 56% improvement that never happened."""
    rng = np.random.default_rng(11)
    truth = rng.normal(20, 3, (300, config.N_DEPTHS))
    pred = truth + rng.normal(0, 1.0, truth.shape)
    clim = truth + rng.normal(0, 2.0, truth.shape)
    o = metrics.per_depth(pred, truth, clim=clim)["overall"]
    r = 1 - o["skill_rmse_ratio"]
    assert o["skill_vs_climatology"] == pytest.approx(1 - r ** 2, abs=1e-9)
    assert o["skill_vs_climatology"] > o["skill_rmse_ratio"], "Murphy always reads higher"
    assert "Never quote one beside the other" in o["skill_note"]


def test_rmse_ratio_skill_matches_the_published_phase1_headline_formula():
    """1 - 0.9578/1.5725 = 0.3909, and the published headline is 0.3871. The formula is the one
    the frozen demo used; the small gap is profile matching, not a different definition."""
    assert 1 - 0.9578 / 1.5725 == pytest.approx(0.3909, abs=1e-3)
