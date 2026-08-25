"""Unit A tests for MC-dropout uncertainty. Owner: Arjhun.

These guard the properties an uncertainty estimate must have to be honest, not just to run.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from oceanembed import config
from oceanembed.inference import uncertainty as unc
from oceanembed.inference.uncertainty import (
    calibration_ratio,
    mc_dropout_predict,
    relative_uncertainty,
)
from oceanembed.models.mlp_profile import MLPProfile


@pytest.fixture
def stats(tmp_path, monkeypatch):
    """Provide norm_stats.json without touching Unit B's artifact."""
    tm = np.linspace(28.0, 9.0, config.N_DEPTHS).astype("float32")
    ts = np.linspace(2.0, 0.35, config.N_DEPTHS).astype("float32")  # shrinks with depth, like real
    path = tmp_path / "norm_stats.json"
    path.write_text(json.dumps({
        "feat_mean": np.zeros(config.N_FEAT).tolist(),
        "feat_std": np.ones(config.N_FEAT).tolist(),
        "targ_mean": tm.tolist(),
        "targ_std": ts.tolist(),
    }), encoding="utf-8")
    monkeypatch.setattr(unc.io, "load_json", lambda _p: json.loads(path.read_text(encoding="utf-8")))
    return tm, ts


@pytest.fixture
def model():
    torch.manual_seed(config.SEED)
    return MLPProfile()


def _X(n=32):
    return np.random.default_rng(config.SEED).normal(size=(n, config.N_FEAT)).astype("float32")


# --- shapes and basics ------------------------------------------------------
def test_returns_mean_and_std_with_correct_shapes(model, stats):
    mean, std = mc_dropout_predict(model, _X(13), n=8)
    assert mean.shape == std.shape == (13, config.N_DEPTHS)
    assert np.isfinite(mean).all() and np.isfinite(std).all()


def test_std_is_strictly_positive(model, stats):
    """Zero spread would mean dropout is off -- fabricated certainty."""
    _, std = mc_dropout_predict(model, _X(), n=16)
    assert (std > 0).all(), "dropout appears inactive; MC-dropout would report fake confidence"


def test_rejects_too_few_passes(model, stats):
    with pytest.raises(AssertionError):
        mc_dropout_predict(model, _X(4), n=1)


def test_rejects_wrong_feature_count(model, stats):
    with pytest.raises(AssertionError):
        mc_dropout_predict(model, np.zeros((4, config.N_FEAT + 1), dtype="float32"), n=4)


# --- the state-leak bug -----------------------------------------------------
def test_restores_eval_mode(model, stats):
    """Left in train() mode, every later plain forward pass is silently stochastic."""
    model.eval()
    mc_dropout_predict(model, _X(8), n=4)
    assert not model.training, "mc_dropout_predict leaked train() mode to the caller"


def test_restores_train_mode_if_that_was_the_caller_state(model, stats):
    model.train()
    mc_dropout_predict(model, _X(8), n=4)
    assert model.training, "caller's train() mode should be preserved"


# --- outputs are in real units ---------------------------------------------
def test_mean_is_in_real_degrees(model, stats):
    tm, _ = stats
    mean, _ = mc_dropout_predict(model, np.zeros((8, config.N_FEAT), dtype="float32"), n=8)
    assert mean.mean() > 5.0, "mean looks normalized, not degC"
    assert np.allclose(mean.mean(axis=0), tm, atol=3.0)


def test_more_passes_gives_a_more_stable_estimate(model, stats):
    """Sanity on the estimator itself: the std estimate should settle as n grows."""
    X = _X(64)
    torch.manual_seed(0)
    spreads = [mc_dropout_predict(model, X, n=n)[1].mean() for n in (4, 4, 64, 64)]
    small = abs(spreads[0] - spreads[1])
    large = abs(spreads[2] - spreads[3])
    assert large <= small * 1.5, "std estimate should stabilise with more passes"


# --- calibration ------------------------------------------------------------
def test_calibration_ratio_is_one_when_sigma_matches_error():
    rng = np.random.default_rng(0)
    y_true = rng.normal(20, 2, (500, config.N_DEPTHS)).astype("float32")
    err = rng.normal(0, 0.5, y_true.shape).astype("float32")
    ratio = calibration_ratio(np.full_like(y_true, 0.5), y_true, y_true + err)
    assert np.allclose(ratio, 1.0, atol=0.15), f"expected ~1.0, got {ratio}"


def test_calibration_ratio_detects_overconfidence():
    """The dangerous direction: sigma far below the error actually made."""
    rng = np.random.default_rng(0)
    y_true = rng.normal(20, 2, (400, config.N_DEPTHS)).astype("float32")
    y_pred = y_true + rng.normal(0, 1.0, y_true.shape).astype("float32")
    ratio = calibration_ratio(np.full_like(y_true, 0.1), y_true, y_pred)
    assert (ratio < 0.5).all(), "should flag a 10x-too-small sigma as overconfident"


def test_calibration_ratio_rejects_mismatched_shapes():
    a = np.zeros((5, config.N_DEPTHS), dtype="float32")
    with pytest.raises(AssertionError):
        calibration_ratio(a, a, np.zeros((6, config.N_DEPTHS), dtype="float32"))


# --- relative uncertainty ---------------------------------------------------
def test_relative_uncertainty_makes_depths_comparable(stats):
    """0.05 degC at 500 m is NOT the same confidence as 0.05 degC at the surface."""
    _, ts = stats
    sigma = np.tile(ts, (6, 1))          # sigma exactly equal to natural spread at every depth
    rel = relative_uncertainty(sigma)
    assert np.allclose(rel, 1.0, atol=1e-5), "equal-to-natural-spread should map to 1.0 everywhere"


def test_relative_uncertainty_preserves_shape(stats):
    sigma = np.abs(np.random.default_rng(0).normal(0.2, 0.05, (9, config.N_DEPTHS))).astype("float32")
    assert relative_uncertainty(sigma).shape == sigma.shape
