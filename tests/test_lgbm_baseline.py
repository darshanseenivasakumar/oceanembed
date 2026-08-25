"""Unit A tests for the LightGBM baseline. Owner: Arjhun.

Kept fast (few rounds, small slice) -- these test the CONTRACT, not model quality.
Quality is measured honestly on the 2022 test set in scripts/run_slice.py.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from oceanembed.models.lgbm_baseline import (
    load_lgbm,
    predict_lgbm,
    quantile_uncertainty,
    save_lgbm,
    train_boosters,
)

pytest.importorskip("lightgbm")

FAST = dict(num_boost_round=25, stopping_rounds=10)


@pytest.fixture(scope="module")
def data():
    X = np.load(config.art("sample_X.npy")).astype("float32")
    y = np.load(config.art("sample_y.npy")).astype("float32")
    return X[:400], y[:400], X[400:], y[400:]


@pytest.fixture(scope="module")
def models(data):
    Xt, yt, Xv, yv = data
    return train_boosters(Xt, yt, Xv, yv, **FAST)


def test_one_booster_per_depth(models):
    assert len(models) == config.N_DEPTHS


def test_predict_shape_and_dtype(models, data):
    _, _, Xv, _ = data
    out = predict_lgbm(models, Xv)
    assert out.shape == (len(Xv), config.N_DEPTHS)
    assert out.dtype == np.float32 and np.isfinite(out).all()


def test_predict_rejects_bad_feature_count(models):
    with pytest.raises(AssertionError):
        predict_lgbm(models, np.zeros((4, config.N_FEAT + 1), dtype="float32"))


def test_predict_rejects_wrong_booster_count(data):
    _, _, Xv, _ = data
    with pytest.raises(AssertionError):
        predict_lgbm([], Xv)


def test_beats_climatology_on_fixtures(models, data):
    """The baseline must at least beat predict-the-mean, or it is not a baseline."""
    Xt, yt, Xv, yv = data
    rmse = np.sqrt(((predict_lgbm(models, Xv) - yv) ** 2).mean())
    clim = np.sqrt(((yt.mean(axis=0) - yv) ** 2).mean())
    assert rmse < clim, f"lgbm RMSE {rmse:.3f} did not beat climatology {clim:.3f}"


def test_output_is_real_degrees_not_normalized(models, data):
    """Mirrors predict_mlp: REAL degC out. Normalized output would sit near 0."""
    _, _, Xv, _ = data
    out = predict_lgbm(models, Xv)
    assert out.mean() > 5.0, f"output mean {out.mean():.2f} looks normalized, not degC"


def test_save_load_round_trip(tmp_path, models, data):
    _, _, Xv, _ = data
    path = tmp_path / "lgbm_model.pkl"
    save_lgbm(models, str(path))
    reloaded = load_lgbm(str(path))
    assert len(reloaded) == config.N_DEPTHS
    assert np.allclose(predict_lgbm(models, Xv), predict_lgbm(reloaded, Xv), atol=1e-6)


def test_load_rejects_wrong_length(tmp_path, models):
    path = tmp_path / "truncated.pkl"
    save_lgbm(models[:3], str(path))
    with pytest.raises(AssertionError):
        load_lgbm(str(path))


def test_quantile_uncertainty_is_nonnegative_and_shaped(data):
    Xt, yt, Xv, yv = data
    q10 = train_boosters(Xt, yt, Xv, yv, alpha=0.1, **FAST)
    q90 = train_boosters(Xt, yt, Xv, yv, alpha=0.9, **FAST)
    sigma = quantile_uncertainty(q10, q90, Xv)
    assert sigma.shape == (len(Xv), config.N_DEPTHS)
    assert sigma.dtype == np.float32
    assert (sigma >= 0).all(), "a standard deviation can never be negative"


def test_quantile_crossing_warns_and_clamps(data):
    """Independently-fitted quantiles can cross. That must warn, never yield negative sigma."""
    Xt, yt, Xv, yv = data
    lo = train_boosters(Xt, yt, Xv, yv, alpha=0.9, **FAST)   # deliberately swapped
    hi = train_boosters(Xt, yt, Xv, yv, alpha=0.1, **FAST)
    with pytest.warns(RuntimeWarning, match="quantile crossing"):
        sigma = quantile_uncertainty(lo, hi, Xv)
    assert (sigma >= 0).all()
