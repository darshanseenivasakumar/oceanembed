"""Unit A tests for observation_priority(). Owner: Arjhun."""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from oceanembed.products.observation_priority import observation_priority

SHAPE = (config.N_LAT, config.N_LON)
RNG = np.random.default_rng(config.SEED)


def _grid(lo=0.0, hi=1.0):
    return RNG.uniform(lo, hi, SHAPE).astype("float32")


def test_shape_dtype_and_range():
    p = observation_priority(_grid(-2, 2), _grid(0, 0.5), _grid(0, 30))
    assert p.shape == SHAPE and p.dtype == np.float32
    assert np.nanmin(p) >= 0.0 and np.nanmax(p) <= 1.0


def test_rejects_wrong_shape():
    bad = np.zeros((10, 10), dtype="float32")
    with pytest.raises(AssertionError):
        observation_priority(bad, _grid(), _grid())


def test_uniform_sparsity_is_neutral_not_zero():
    """THE repo's state today: no argo_test -> _argo_sparsity() returns all-ones.

    Min-max scaling a constant grid gives zeros, which would zero the whole product and
    render a blank panel that looks like a bug. It must be treated as neutral instead.
    """
    uniform = np.ones(SHAPE, dtype="float32")
    with pytest.warns(RuntimeWarning, match="constant"):
        p = observation_priority(_grid(-2, 2), _grid(0, 0.5), uniform)
    assert np.nanmax(p) > 0.1, "uniform sparsity must not flatten priority to zero"
    assert np.isfinite(p).all()


def test_land_stays_nan():
    a, u, s = _grid(-2, 2), _grid(0, 0.5), _grid(0, 30)
    land = np.zeros(SHAPE, dtype=bool)
    land[:10, :20] = True
    a[land] = np.nan
    u[land] = np.nan
    p = observation_priority(a, u, s)
    assert np.isnan(p[land]).all(), "land must stay NaN, not score 0"
    assert np.isfinite(p[~land]).all(), "ocean must be finite"


def test_all_three_factors_are_required():
    """Multiplicative by design: high on one axis alone must not win."""
    high, low = np.full(SHAPE, 0.9, "float32"), np.full(SHAPE, 0.1, "float32")
    a, u, s = low.copy(), low.copy(), low.copy()
    a[50, 100] = 100.0                      # wildly anomalous, but certain and well-observed
    u[50, 100], s[50, 100] = 0.1, 0.1
    a[60, 100] = u[60, 100] = s[60, 100] = 100.0   # high on all three
    p = observation_priority(a, u, s, robust=False)
    assert p[60, 100] > p[50, 100], "a location strong on all three must outrank one strong on anomaly alone"


def test_ranking_matches_the_documented_product():
    """Geometric mean must preserve the exact ordering of the spec's raw product."""
    a, u, s = _grid(0, 1), _grid(0, 1), _grid(0, 1)
    p = observation_priority(a, u, s, robust=False).ravel()
    prod = (_n(a) * _n(u) * _n(s)).ravel()
    order_p, order_prod = np.argsort(p), np.argsort(prod)
    agree = (order_p == order_prod).mean()
    assert agree > 0.99, f"ranking diverged from the documented product ({agree:.3f} agreement)"


def _n(x):
    lo, hi = np.nanmin(x), np.nanmax(x)
    return (x - lo) / (hi - lo)


def test_weights_shift_emphasis():
    a, u, s = _grid(0, 1), _grid(0, 1), _grid(0, 1)
    only_anom = observation_priority(a, u, s, weights=(1, 0, 0), robust=False)
    assert np.corrcoef(only_anom.ravel(), _n(a).ravel())[0, 1] > 0.99


def test_rejects_bad_weights():
    for bad in [(0, 0, 0), (-1, 1, 1)]:
        with pytest.raises(AssertionError):
            observation_priority(_grid(), _grid(), _grid(), weights=bad)


def test_one_all_nan_factor_is_neutral_others_still_rank():
    """One dead factor should not kill the map -- the other two still carry information."""
    with pytest.warns(RuntimeWarning, match="entirely NaN"):
        p = observation_priority(_grid(-2, 2), np.full(SHAPE, np.nan, "float32"), _grid(0, 30))
    assert np.isfinite(p).all() and np.nanmax(p) > 0.1


def test_all_factors_degenerate_returns_nan_not_a_uniform_map():
    """With nothing to rank on, NaN (UI hides the panel) beats all-ones (everything is urgent)."""
    ones = np.ones(SHAPE, dtype="float32")
    with pytest.warns(RuntimeWarning):
        p = observation_priority(ones, ones, ones)
    assert np.isnan(p).all()


def test_land_nan_survives_a_neutral_factor():
    """A neutral factor must not erase land masking coming from the other factors."""
    a, s = _grid(-2, 2), _grid(0, 30)
    a[:5, :5] = np.nan
    with pytest.warns(RuntimeWarning, match="entirely NaN"):
        p = observation_priority(a, np.full(SHAPE, np.nan, "float32"), s)
    assert np.isnan(p[:5, :5]).all()
