"""Unit C tests for compute_metrics. Owner: Mitun + Niru.

These are the numbers that end up on a slide, so the tests are about whether the metric
MEANS what a reader will think it means -- not just whether it runs.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from oceanembed.validation.metrics import compute_metrics

D = config.N_DEPTHS
RNG = np.random.default_rng(config.SEED)


def realistic_profiles(n=400):
    """Warm surface -> cold deep, with per-profile variation that shrinks with depth."""
    base = np.linspace(28.0, 9.0, D)
    taper = np.linspace(1.0, 0.2, D)
    return (base[None, :] + RNG.normal(0, 2.0, (n, 1)) * taper).astype("float32")


def climatology_of(y):
    return np.repeat(y.mean(axis=0)[None, :], len(y), axis=0)


# --- basics -----------------------------------------------------------------
def test_perfect_prediction_scores_perfectly():
    y = realistic_profiles()
    m = compute_metrics(y, y.copy())
    assert m["rmse"] == pytest.approx(0.0, abs=1e-6)
    assert m["mae"] == pytest.approx(0.0, abs=1e-6)
    assert m["r2"] == pytest.approx(1.0, abs=1e-6)
    assert np.allclose(m["r2_by_depth"], 1.0, atol=1e-6)


def test_rmse_matches_a_hand_computation():
    y = np.full((5, D), 20.0, dtype="float32")
    m = compute_metrics(y, y + 2.0)
    assert m["rmse"] == pytest.approx(2.0)
    assert m["mae"] == pytest.approx(2.0)


def test_rmse_by_depth_has_one_value_per_depth():
    y = realistic_profiles(50)
    m = compute_metrics(y, y + RNG.normal(0, 1, y.shape))
    assert len(m["rmse_by_depth"]) == D
    assert len(m["r2_by_depth"]) == D


def test_rejects_mismatched_shapes():
    y = realistic_profiles(10)
    with pytest.raises(AssertionError):
        compute_metrics(y, y[:5])


def test_is_nan_safe():
    y = realistic_profiles(60)
    p = y + 0.5
    p[0, 0] = np.nan
    m = compute_metrics(y, p)
    assert np.isfinite(m["rmse"]) and np.isfinite(m["mae"])


# --- the reporting trap -----------------------------------------------------
def test_pooled_r2_is_inflated_by_the_depth_gradient():
    """Pins the caveat in the module docstring so nobody quotes r2 innocently.

    Climatology knows NOTHING beyond the average profile, yet pooled R2 scores it ~0.95 because
    the pooled variance is dominated by surface-to-deep temperature change.
    """
    y = realistic_profiles()
    m = compute_metrics(y, climatology_of(y))
    assert m["r2"] > 0.85, (
        f"pooled r2 for climatology was {m['r2']:.3f}; if this ever drops, the docstring "
        "caveat needs revisiting"
    )


def test_per_depth_r2_scores_climatology_at_zero():
    """The honest metric: climatology IS the per-depth mean, so it explains nothing extra."""
    y = realistic_profiles()
    m = compute_metrics(y, climatology_of(y))
    assert np.allclose(m["r2_by_depth"], 0.0, atol=1e-6), (
        "climatology must score exactly 0 on per-depth R2, or the metric is not measuring skill"
    )


def test_per_depth_r2_punishes_a_useless_predictor():
    """One global mean everywhere: pooled R2 says 0.0, per-depth R2 correctly says catastrophic."""
    y = realistic_profiles()
    useless = np.full_like(y, y.mean())
    m = compute_metrics(y, useless)
    assert np.mean(m["r2_by_depth"]) < -1.0


# --- skill vs climatology ---------------------------------------------------
def test_skill_is_zero_when_the_model_equals_climatology():
    y = realistic_profiles()
    clim = climatology_of(y)
    assert compute_metrics(y, clim, y_clim=clim)["skill_vs_clim"] == pytest.approx(0.0, abs=1e-9)


def test_skill_is_positive_when_the_model_beats_climatology():
    y = realistic_profiles()
    clim = climatology_of(y)
    better = y + RNG.normal(0, 0.1, y.shape)
    assert compute_metrics(y, better, y_clim=clim)["skill_vs_clim"] > 0.5


def test_skill_is_negative_when_the_model_is_worse():
    y = realistic_profiles()
    clim = climatology_of(y)
    worse = y + RNG.normal(0, 20.0, y.shape)
    assert compute_metrics(y, worse, y_clim=clim)["skill_vs_clim"] < 0


def test_skill_is_none_without_a_baseline():
    y = realistic_profiles(20)
    assert compute_metrics(y, y + 1.0)["skill_vs_clim"] is None


def test_mis_shaped_baseline_is_rejected_not_broadcast():
    """A (1,11) baseline would broadcast silently and yield a wrong skill number."""
    y = realistic_profiles(30)
    with pytest.raises(AssertionError, match="y_clim must be"):
        compute_metrics(y, y + 0.5, y_clim=y.mean(axis=0)[None, :])
