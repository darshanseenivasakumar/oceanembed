"""Seasonal climatology + 90th-percentile THRESHOLD for marine-heatwave detection (Hobday 2016).

OWNER: Unit A (Arjhun / MHW feature). PHASE-2 ONLY. Imports config; modifies nothing.

WHAT A HEATWAVE THRESHOLD IS, AND WHY IT NEEDS MANY YEARS
`events.heatwave.detect_events` asks a simple question each day: is the temperature above the
90th-percentile of what is NORMAL for this time of year? "Normal for this time of year" is a curve
over the calendar -- warmer in one season, cooler in another -- built from MANY years so that each
calendar day has a distribution to take a percentile of. One year gives each day a single value and
no distribution, so no day can be "unusually" warm. That is why the baseline is downloaded over
several years and this module turns it into two day-of-year curves: the mean (climatology) and the
90th percentile (threshold).

TWO BUILDERS, ONE DETECTION ENGINE
  * doy_climatology_threshold()  -- the real thing: a day-of-year (1..366) curve from DAILY data,
    Hobday's 11-day pooling window and 31-day smoothing. Use once the multi-year daily baseline is
    downloaded.
  * monthly_climatology_threshold() -- a PILOT from MONTHLY data (e.g. the 48-month grids.npz already
    on disk), so the whole pipeline can be validated end-to-end before the daily download finishes.
    It is coarser (one value per calendar month, held flat across the month) and is labelled as such;
    it is NOT Hobday-compliant and must never be presented as the final baseline.

Both return arrays whose leading axis is the season index (366 days, or 12 months) and whose trailing
axes match the field -- e.g. (366, 100, 240, 15) or (12, 100, 240, 15). `map_to_series` /
`map_monthly_to_series` then align a curve onto the actual dates of a detection series so the three
inputs `detect_events` needs (temp, clim, thresh) are day-for-day aligned.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from oceanembed import config  # baseline config: IMPORTED, never modified

__all__ = [
    "WINDOW_DAYS", "SMOOTH_DAYS", "PERCENTILE",
    "day_of_year", "doy_climatology_threshold", "map_to_series",
    "monthly_climatology_threshold", "map_monthly_to_series",
]

#: Hobday et al. (2016): pool each day-of-year with a +/-5-day window (11 days total) across years,
#: then smooth the resulting curves with a 31-day moving average.
WINDOW_DAYS = 11
SMOOTH_DAYS = 31
PERCENTILE = 90.0


def day_of_year(dates) -> np.ndarray:
    """Calendar day-of-year 1..366 for a datetime64 / parseable array. Feb-29 aware (leap = 366)."""
    d = pd.to_datetime(np.asarray(dates))
    return d.dayofyear.to_numpy().astype("int64")


def _circular_moving_average(curve: np.ndarray, window: int) -> np.ndarray:
    """Moving average along axis 0 (the season axis), wrapping at the year boundary.

    The calendar is circular -- 31 Dec is next to 1 Jan -- so the smoothing must wrap, or the two
    ends of the year would be under-smoothed. Uses a uniform window; NaN cells stay NaN via a
    nan-aware mean.
    """
    n = curve.shape[0]
    if window <= 1:
        return curve.copy()
    half = window // 2
    out = np.full_like(curve, np.nan, dtype="float64")
    idx = np.arange(n)
    for k in range(n):
        sel = (idx[k - half:k + half + 1] if 0 <= k - half and k + half < n
               else np.mod(np.arange(k - half, k + half + 1), n))
        with np.errstate(invalid="ignore"):
            out[k] = np.nanmean(curve[sel], axis=0)
    return out


def doy_climatology_threshold(temp_stack, dates, window_days: int = WINDOW_DAYS,
                              smooth_days: int = SMOOTH_DAYS, pct: float = PERCENTILE):
    """Day-of-year climatology (mean) and threshold (`pct` percentile) from a DAILY multi-year stack.

    temp_stack : (N, ...) daily temperature fields.
    dates      : (N,) datetime64 aligned to axis 0.
    Returns (clim, thresh), each (366, ...): for day-of-year D, pool every day whose day-of-year is
    within +/- window_days//2 of D (circular) across ALL years, then take the mean / percentile;
    finally smooth both curves with a `smooth_days` circular moving average. Cells with no samples
    stay NaN (never invented).
    """
    temp = np.asarray(temp_stack, dtype="float64")
    doy = day_of_year(dates)
    half = window_days // 2
    field_shape = temp.shape[1:]

    clim = np.full((366,) + field_shape, np.nan)
    thresh = np.full((366,) + field_shape, np.nan)
    # precompute, for each target doy 1..366, the member days within the circular window
    for d in range(1, 367):
        offs = np.mod(np.arange(d - half, d + half + 1) - 1, 366) + 1   # target doys, wrapped to 1..366
        mask = np.isin(doy, offs)
        if not mask.any():
            continue
        pool = temp[mask]                       # (M, ...)
        with np.errstate(invalid="ignore"):
            clim[d - 1] = np.nanmean(pool, axis=0)
            thresh[d - 1] = np.nanpercentile(pool, pct, axis=0)

    clim = _circular_moving_average(clim, smooth_days)
    thresh = _circular_moving_average(thresh, smooth_days)
    return clim, thresh


def map_to_series(curve366, dates) -> np.ndarray:
    """Align a (366, ...) day-of-year curve onto the dates of a detection series -> (N, ...)."""
    curve = np.asarray(curve366)
    doy = day_of_year(dates)
    return curve[doy - 1]


# --------------------------------------------------------------- monthly pilot

def monthly_climatology_threshold(temp_stack, dates, pct: float = PERCENTILE):
    """PILOT baseline from MONTHLY data: per-calendar-month mean and `pct` percentile.

    Coarser than the day-of-year builder (12 values, held flat across each month) and NOT
    Hobday-compliant -- it exists only to exercise the full pipeline on the monthly grids.npz already
    on disk while the daily baseline downloads. Returns (clim, thresh), each (12, ...).
    """
    temp = np.asarray(temp_stack, dtype="float64")
    month = pd.to_datetime(np.asarray(dates)).month.to_numpy()
    field_shape = temp.shape[1:]
    clim = np.full((12,) + field_shape, np.nan)
    thresh = np.full((12,) + field_shape, np.nan)
    for m in range(1, 13):
        mask = month == m
        if not mask.any():
            continue
        pool = temp[mask]
        with np.errstate(invalid="ignore"):
            clim[m - 1] = np.nanmean(pool, axis=0)
            thresh[m - 1] = np.nanpercentile(pool, pct, axis=0)
    return clim, thresh


def map_monthly_to_series(curve12, dates) -> np.ndarray:
    """Align a (12, ...) monthly curve onto the dates of a detection series -> (N, ...)."""
    curve = np.asarray(curve12)
    month = pd.to_datetime(np.asarray(dates)).month.to_numpy()
    return curve[month - 1]
