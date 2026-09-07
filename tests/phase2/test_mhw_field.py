"""Grid MHW flags + model-vs-truth contingency skill -- verified on synthetic arrays.

No bundle, no download. NO tests/phase2/__init__.py.
"""
from __future__ import annotations

import numpy as np
import pytest

from phase2.derived import mhw_field as mf


def test_event_mask_paints_the_event_span():
    clim = np.full(20, 25.0)
    thresh = np.full(20, 26.0)
    temp = clim.copy()
    temp[3:9] = 28.0                       # a 6-day event
    mask = mf.event_mask(temp, clim, thresh)
    assert mask[3:9].all()
    assert not mask[:3].any() and not mask[9:].any()


def test_event_mask_empty_when_no_event():
    clim = np.full(10, 25.0)
    thresh = np.full(10, 26.0)
    temp = clim.copy()
    temp[2:5] = 28.0                       # only 3 days -> not an event
    assert not mf.event_mask(temp, clim, thresh).any()


def test_compare_detection_counts_and_rates():
    # 10 days: truth MHW on days 0-4; model MHW on days 2-6
    truth = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
    model = np.array([0, 0, 1, 1, 1, 1, 1, 0, 0, 0], dtype=bool)
    c = mf.compare_detection(model, truth)
    # hits = days 2,3,4 = 3; misses = days 0,1 = 2; FA = days 5,6 = 2; CN = 3
    assert (c["hits"], c["misses"], c["false_alarms"], c["correct_negatives"]) == (3, 2, 2, 3)
    assert c["pod"] == pytest.approx(3 / 5)
    assert c["far"] == pytest.approx(2 / 5)
    assert c["csi"] == pytest.approx(3 / 7)
    assert c["frequency_bias"] == pytest.approx(5 / 5)


def test_compare_detection_respects_valid_mask():
    truth = np.array([[1, 1], [0, 0]], dtype=bool)
    model = np.array([[1, 0], [1, 0]], dtype=bool)
    valid = np.array([[True, True], [False, False]])   # ignore the bottom row
    c = mf.compare_detection(model, truth, valid=valid)
    # only top row counts: truth [1,1], model [1,0] -> 1 hit, 1 miss, 0 FA, 0 CN
    assert (c["hits"], c["misses"], c["false_alarms"]) == (1, 1, 0)


def test_zero_denominator_is_none_not_fabricated():
    z = np.zeros(5, dtype=bool)
    c = mf.compare_detection(z, z)          # nothing flagged anywhere
    assert c["pod"] is None and c["far"] is None and c["csi"] is None
