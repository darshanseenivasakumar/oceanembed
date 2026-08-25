"""Unit C tests for the anomaly product. Owner: Mitun + Niru."""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from oceanembed.products.anomaly import (
    DEFAULT_K,
    anomaly,
    flag_extremes,
    standardized_anomaly,
    summarize,
)

H, W, D = config.N_LAT, config.N_LON, config.N_DEPTHS
RNG = np.random.default_rng(config.SEED)


@pytest.fixture
def clim():
    """(12,100,240,11) climatology: cools with depth, with a mild seasonal cycle."""
    base = np.linspace(28.0, 9.0, D)[None, None, None, :]
    season = np.sin(2 * np.pi * np.arange(12) / 12)[:, None, None, None]
    return np.broadcast_to(base + season, (12, H, W, D)).astype("float32").copy()


@pytest.fixture
def pred(clim):
    return clim[5].copy()


# --- anomaly (degC) ---------------------------------------------------------
def test_prediction_equal_to_climatology_gives_zero(clim, pred):
    assert np.allclose(anomaly(pred, clim, 6), 0.0, atol=1e-6)


def test_anomaly_is_a_plain_difference_in_degrees(clim, pred):
    a = anomaly(pred + 1.5, clim, 6)
    assert np.allclose(a, 1.5, atol=1e-5), "anomaly must be degC, not sigma"


def test_uses_the_month_it_is_given(clim, pred):
    """month is 1-based; off-by-one here would silently compare against the wrong season.

    Compares month 1 against month 4, not month 7 -- the fixture's sin(2*pi*m/12) cycle is zero
    at BOTH month 1 and month 7, so that pair cannot detect an indexing error at all.
    """
    assert np.allclose(anomaly(clim[0].copy(), clim, 1), 0.0, atol=1e-6)
    assert not np.allclose(anomaly(clim[0].copy(), clim, 4), 0.0, atol=1e-6)
    # month is 1-based: month=4 must select index 3, not index 4.
    assert np.allclose(anomaly(clim[3].copy(), clim, 4), 0.0, atol=1e-6)


def test_rejects_a_single_profile_rather_than_broadcasting(clim):
    """predict.py passes (1,1,11); broadcasting would make [0,0] read the SW corner silently."""
    with pytest.raises(AssertionError):
        anomaly(np.zeros((1, 1, D), dtype="float32"), clim, 6)


def test_rejects_a_mis_shaped_climatology(pred):
    with pytest.raises(AssertionError):
        anomaly(pred, np.zeros((11, H, W, D), dtype="float32"), 6)


@pytest.mark.parametrize("bad", [0, 13, -1])
def test_rejects_an_out_of_range_month(clim, pred, bad):
    with pytest.raises(AssertionError):
        anomaly(pred, clim, bad)


def test_land_nan_propagates(clim, pred):
    pred[:10, :10, :] = np.nan
    a = anomaly(pred, clim, 6)
    assert np.isnan(a[:10, :10, :]).all()
    assert np.isfinite(a[50:, 50:, :]).all()


# --- standardized anomaly (sigma) -------------------------------------------
def test_standardized_is_dimensionless_and_scale_free(clim, pred):
    """Doubling the anomaly everywhere doubles degC but leaves sigma units unchanged."""
    noise = RNG.normal(0, 1.0, (H, W, D)).astype("float32")
    z1 = standardized_anomaly(pred + noise, clim, 6)
    z2 = standardized_anomaly(pred + 2 * noise, clim, 6)
    assert np.allclose(z1, z2, atol=1e-4)


def test_standardized_has_unit_spread_per_depth(clim, pred):
    z = standardized_anomaly(pred + RNG.normal(0, 2.0, (H, W, D)), clim, 6)
    per_depth = np.nanstd(z.reshape(-1, D), axis=0)
    assert np.allclose(per_depth, 1.0, atol=0.05)


def test_uniform_anomaly_is_zero_sigma_not_infinite(clim, pred):
    """A constant offset is unremarkable spatially; dividing by ~0 must not yield inf."""
    z = standardized_anomaly(pred + 3.0, clim, 6)
    assert np.isfinite(z).all() and np.allclose(z, 0.0, atol=1e-5)


def test_standardized_keeps_land_nan(clim, pred):
    pred[:5, :5, :] = np.nan
    assert np.isnan(standardized_anomaly(pred, clim, 6)[:5, :5, :]).all()


# --- extremes ---------------------------------------------------------------
def test_flag_extremes_is_boolean_and_correctly_shaped(clim, pred):
    f = flag_extremes(pred + RNG.normal(0, 2.0, (H, W, D)), clim, 6)
    assert f.shape == (H, W, D) and f.dtype == bool


def test_a_strong_outlier_is_flagged(clim, pred):
    p = pred + RNG.normal(0, 0.5, (H, W, D)).astype("float32")
    p[40, 120, 3] += 25.0
    assert flag_extremes(p, clim, 6, k=DEFAULT_K)[40, 120, 3]


def test_land_is_never_flagged_extreme(clim, pred):
    p = pred + RNG.normal(0, 1.0, (H, W, D)).astype("float32")
    p[:8, :8, :] = np.nan
    assert not flag_extremes(p, clim, 6).any(axis=2)[:8, :8].any()


def test_a_larger_k_flags_no_more_cells(clim, pred):
    p = pred + RNG.normal(0, 1.0, (H, W, D)).astype("float32")
    assert flag_extremes(p, clim, 6, k=3.0).sum() <= flag_extremes(p, clim, 6, k=1.0).sum()


def test_rejects_a_non_positive_k(clim, pred):
    with pytest.raises(AssertionError):
        flag_extremes(pred, clim, 6, k=0)


# --- summary ----------------------------------------------------------------
def test_summary_reports_k_and_the_sigma_basis(clim, pred):
    """A count of 'extreme' cells is meaningless without k and without what sigma means."""
    s = summarize(pred + RNG.normal(0, 1.0, (H, W, D)), clim, 6)
    assert s["k"] == DEFAULT_K
    assert "NOT climatological" in s["sigma_basis"]
    for key in ("mean_anomaly_degC", "max_abs_anomaly_degC", "n_extreme", "n_ocean"):
        assert len(s[key]) == D, f"{key} must have one entry per depth"


def test_summary_counts_only_ocean_cells(clim, pred):
    pred[:10, :, :] = np.nan
    s = summarize(pred, clim, 6)
    assert all(n == (H - 10) * W for n in s["n_ocean"])
