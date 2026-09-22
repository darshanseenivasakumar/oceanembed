"""Day-of-year input encoding for the L1 ablation leg -- pure numpy."""
from __future__ import annotations

import numpy as np
import pytest

from phase2.tscast_nio import time_encoding as TE


def test_january_first_is_the_zero_angle():
    assert TE.doy_encoding("2025-01-01").tolist() == pytest.approx([0.0, 1.0])


def test_the_year_end_is_continuous_not_a_cliff():
    gap = np.linalg.norm(TE.doy_encoding("2025-12-31") - TE.doy_encoding("2026-01-01"))
    assert 0.01 < gap < 0.02            # one day of angle, 2*pi/365 ~ 0.0172


def test_mid_year_points_the_opposite_way():
    s, c = TE.doy_encoding("2025-07-02")
    assert c == pytest.approx(-1.0, abs=0.01)
    assert abs(s) < 0.02


def test_leap_years_use_366_days():
    s, c = TE.doy_encoding("2024-12-31")
    assert np.isfinite(TE.doy_encoding("2024-02-29")).all()
    assert np.arctan2(s, c) % (2 * np.pi) == pytest.approx(2 * np.pi * 365 / 366, rel=1e-6)


def test_many_dates_give_n_by_two_float32():
    t = np.arange("2025-06-01", "2025-06-11", dtype="datetime64[D]")
    e = TE.doy_encoding(t)
    assert e.shape == (10, 2) and e.dtype == np.float32
    assert np.allclose(np.hypot(e[:, 0], e[:, 1]), 1.0, atol=1e-6)


def test_n_channels_is_two():
    assert TE.N_CHANNELS == 2
