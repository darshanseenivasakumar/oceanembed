"""MHW baseline (climatology + threshold) builders -- verified on synthetic series.

No bundle, no download. NO tests/phase2/__init__.py (it shadows src/phase2 under pytest).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase2.derived import mhw_baseline as mb


def test_day_of_year_is_leap_aware():
    d = pd.to_datetime(["2020-01-01", "2020-12-31", "2021-12-31"])   # 2020 is a leap year
    assert mb.day_of_year(d).tolist() == [1, 366, 365]


def test_monthly_builder_matches_hand_grouped_percentile():
    dates = pd.date_range("2019-01-01", periods=36, freq="MS")       # exactly 36 monthly steps
    month = dates.month.to_numpy()
    # deterministic per-month values with one hot outlier every third month
    month_f = month.astype("float64")
    temp = np.where(np.arange(36) % 3 == 2, month_f + 10.0, month_f)
    clim, thresh = mb.monthly_climatology_threshold(temp, dates, pct=90.0)
    for m in range(1, 13):
        pool = temp[month == m]
        assert clim[m - 1] == pytest.approx(pool.mean())
        assert thresh[m - 1] == pytest.approx(np.percentile(pool, 90.0))
    # threshold is always >= climatology (a high percentile cannot sit below the mean here)
    assert np.all(thresh >= clim - 1e-9)


def test_doy_builder_shape_and_constant_field():
    dates = pd.date_range("2019-01-01", "2021-12-31", freq="D")      # 3 years daily
    temp = np.full((len(dates), 2, 2), 20.0)                         # constant field
    clim, thresh = mb.doy_climatology_threshold(temp, dates)
    assert clim.shape == (366, 2, 2) and thresh.shape == (366, 2, 2)
    # percentile/mean of a constant is that constant, and smoothing preserves it
    assert np.allclose(clim, 20.0) and np.allclose(thresh, 20.0)


def test_doy_builder_keeps_nan_where_no_data():
    dates = pd.date_range("2019-01-01", "2020-12-31", freq="D")
    temp = np.full((len(dates), 3), 18.0)
    temp[:, 1] = np.nan                                              # a permanently-masked cell
    clim, thresh = mb.doy_climatology_threshold(temp, dates)
    assert np.isnan(clim[:, 1]).all() and np.isnan(thresh[:, 1]).all()
    assert np.isfinite(clim[:, 0]).all()                            # a valid cell stays finite


def test_map_to_series_aligns_curve_onto_dates():
    curve = np.arange(1, 367, dtype="float64")                      # curve[d-1] == d
    dates = pd.to_datetime(["2026-01-01", "2026-02-01"])            # doy 1 and 32
    got = mb.map_to_series(curve, dates)
    assert got.tolist() == [1.0, 32.0]


def test_map_monthly_to_series_aligns_by_month():
    curve = np.arange(1, 13, dtype="float64")                       # curve[m-1] == m
    dates = pd.to_datetime(["2026-03-10", "2026-07-20"])           # months 3 and 7
    got = mb.map_monthly_to_series(curve, dates)
    assert got.tolist() == [3.0, 7.0]
