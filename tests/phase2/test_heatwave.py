"""Marine-heatwave detection engine -- tested on synthetic series with known answers.

No bundle, no download: every case here is a hand-built temperature series where the correct event
set is obvious by construction, so the Hobday persistence + gap logic is verified independently of
the real data. NO tests/phase2/__init__.py exists (it shadows the src/phase2 package under pytest).
"""
from __future__ import annotations

import numpy as np
import pytest

from phase2.events import heatwave as hw


# ------------------------------------------------------------------ exceedances

def test_exceedances_is_strict_and_nan_safe():
    temp = np.array([25.0, 27.0, np.nan, 27.0, 26.0])
    thresh = np.full(5, 26.0)
    ex = hw.exceedances(temp, thresh)
    # strictly above 26: index 1 and 3 only; NaN -> False; equal (26==26) -> False
    assert ex.tolist() == [False, True, False, True, False]


# ------------------------------------------------------------------ persistence

def test_single_event_meets_minimum_duration():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[3:9] = 28.0                       # 6 consecutive days above threshold
    events = hw.detect_events(temp, clim, thresh)
    assert len(events) == 1
    assert (events[0]["start"], events[0]["end"]) == (3, 8)
    assert events[0]["duration_days"] == 6


def test_run_below_minimum_duration_is_not_an_event():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[3:7] = 28.0                       # only 4 consecutive days -> not a heatwave
    assert hw.detect_events(temp, clim, thresh) == []


def test_two_events_within_gap_merge_into_one():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[0:5] = 28.0                       # event A, days 0-4
    temp[7:12] = 28.0                      # event B, days 7-11; gap days 5,6 = 2-day gap
    events = hw.detect_events(temp, clim, thresh)
    assert len(events) == 1                # merged
    assert (events[0]["start"], events[0]["end"]) == (0, 11)
    assert events[0]["duration_days"] == 12  # gap days folded in


def test_two_events_beyond_gap_stay_separate():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[0:5] = 28.0                       # days 0-4
    temp[8:13] = 28.0                      # days 8-12; gap days 5,6,7 = 3-day gap > 2
    events = hw.detect_events(temp, clim, thresh)
    assert len(events) == 2


def test_nan_breaks_persistence():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[0:7] = 28.0                       # would be a 7-day event...
    temp[3] = np.nan                       # ...but a NaN on day 3 splits it into 3+3 days
    assert hw.detect_events(temp, clim, thresh) == []   # neither half reaches 5


# ------------------------------------------------------------------ intensity + category

def test_intensity_metrics_are_measured_from_climatology():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[3:10] = 28.0                      # 7 days, each 3.0 degC above the climatology mean
    ev = hw.detect_events(temp, clim, thresh)[0]
    assert ev["mean_intensity_c"] == pytest.approx(3.0)
    assert ev["max_intensity_c"] == pytest.approx(3.0)
    assert ev["cumulative_intensity"] == pytest.approx(21.0)   # 3.0 * 7 days


def test_category_is_multiple_of_threshold_minus_climatology():
    # level = (temp - clim)/(thresh - clim) = (28-25)/(26-25) = 3.0 -> Severe (category 3)
    cat, name = hw.category_at(28.0, 25.0, 26.0)
    assert (cat, name) == (3, "Severe")
    # a peak just above threshold -> Moderate
    assert hw.category_at(26.1, 25.0, 26.0)[1] == "Moderate"
    # >=4x -> Extreme
    assert hw.category_at(30.0, 25.0, 26.0)[1] == "Extreme"


def test_degenerate_threshold_gap_is_undefined_not_a_crash():
    cat, name = hw.category_at(27.0, 26.0, 26.0)   # thresh == clim -> zero gap
    assert (cat, name) == (0, "Undefined")


# ------------------------------------------------------------------ summarise

def test_summarise_empty_reads_as_no_heatwave():
    s = hw.summarise([])
    assert s["n_events"] == 0 and s["max_category_name"] == "None"


def test_summarise_reports_strongest_and_totals():
    clim = np.full(40, 25.0)
    thresh = np.full(40, 26.0)
    temp = clim.copy()
    temp[0:6] = 27.0                       # mild event
    temp[20:26] = 31.0                     # strong event (level 6 -> Extreme)
    s = hw.summarise(hw.detect_events(temp, clim, thresh))
    assert s["n_events"] == 2
    assert s["total_mhw_days"] == 12
    assert s["max_category_name"] == "Extreme"
    assert s["max_intensity_c"] == pytest.approx(6.0)
