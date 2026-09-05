"""Depth-of-a-feature primitives. Owner: Unit A (Arjhun).

A depth is a single number that always looks plausible, so shape tests prove nothing here. These
check against hand-computed crossings, against the OLD function's documented failure, and against
real data for the one claim that decides whether a product can ship at all.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.derived import profile_features as pf
from phase2.derived import transect as T

DEPTHS = np.asarray(config.DEPTHS, dtype="float64")
D = config.N_DEPTHS


def sigma_theta_column():
    """A realistic potential-density column: light at the top, heavier down. Crosses 24.0 between
    100 m (23.91) and 125 m (24.97)."""
    return np.array([21.50, 21.52, 21.60, 21.85, 22.10, 22.60, 23.20, 23.91,
                     24.97, 25.58, 26.10, 26.55, 26.90, 27.10, 27.25])


# ==================================================== the reason this module exists

def test_the_old_isotherm_finder_returns_nan_on_every_point_of_a_density_section():
    """The claim that motivated this module, as an executable check.

    `transect.isotherm_depth` returns NaN unless the SURFACE value already exceeds the threshold
    (transect.py:159). Density INCREASES with depth, so its surface value is below every interior
    threshold and the function fails on every column -- silently, as a blank contour line that
    reads as "no isopycnal here" rather than as "this function cannot answer this question".
    """
    col = sigma_theta_column()
    assert col[8] > 24.0 > col[7], "the fixture must actually cross 24.0, or this proves nothing"

    old = T.isotherm_depth(col, DEPTHS, 24.0)
    assert np.isnan(old), "if this ever stops being NaN, the old function was fixed -- re-read both"

    new, reason = pf.crossing_depth(col, DEPTHS, 24.0, direction="increasing")
    assert reason == pf.OK
    assert 100.0 < new < 125.0

    # and over a whole section, so the failure is visible at the scale a page would hit it
    section = np.tile(col, (40, 1))
    old_line = T.isotherm_line({"temperature": section, "depths": DEPTHS}, 24.0)
    assert np.isnan(old_line).all()
    line, reasons = pf.contour_line(section, DEPTHS, 24.0, direction="increasing")
    assert np.isfinite(line).all()
    assert pf.tally(reasons) == {pf.OK: 40}


def test_the_old_finder_is_still_right_for_the_isotherm_it_was_written_for():
    """Not a regression suite for `transect.py` -- a check that this module did not "fix" something
    that was never broken. The shipped D26 path is frozen and must keep agreeing."""
    temp = np.array([29.5, 29.4, 29.2, 28.8, 28.0, 27.0, 26.4, 25.5,
                     24.0, 22.5, 19.0, 15.0, 11.0, 9.0, 6.0])
    old = T.isotherm_depth(temp, DEPTHS, 26.0)
    new, reason = pf.crossing_depth(temp, DEPTHS, 26.0, direction="decreasing")
    assert reason == pf.OK
    assert abs(old - new) < 1e-9


# ==================================================== crossings: value, then every reason

def test_the_interpolated_depth_matches_a_hand_computed_bracket():
    col = sigma_theta_column()
    # bracket is 100 m (23.91) -> 125 m (24.97); fraction to 24.0 is (24.0-23.91)/(24.97-23.91)
    want = 100.0 + ((24.0 - col[7]) / (col[8] - col[7])) * (125.0 - 100.0)
    got, reason = pf.crossing_depth(col, DEPTHS, 24.0, direction="increasing")
    assert reason == pf.OK
    assert abs(got - want) < 1e-9


def test_direction_is_enforced_and_the_refusal_is_named():
    """The same column, the same threshold, the wrong direction. This must NOT come back as
    `outside_profile_range` -- the threshold IS attained; the caller asked the other way."""
    col = sigma_theta_column()
    depth, reason = pf.crossing_depth(col, DEPTHS, 24.0, direction="decreasing")
    assert np.isnan(depth)
    assert reason == pf.WRONG_DIRECTION


def test_a_threshold_the_column_never_reaches_is_a_different_fact_again():
    col = sigma_theta_column()
    depth, reason = pf.crossing_depth(col, DEPTHS, 99.0, direction="either")
    assert np.isnan(depth) and reason == pf.OUTSIDE_PROFILE_RANGE


def test_land_is_no_data_not_never_crosses():
    """The 6bb088f bug in one line: a land column and a warm-to-the-bottom column are different
    facts, and reporting both as one is what put "17 land points" under a temperature caption."""
    depth, reason = pf.crossing_depth(np.full(D, np.nan), DEPTHS, 26.0)
    assert np.isnan(depth) and reason == pf.NO_DATA

    warm = np.full(D, 28.0)
    depth, reason = pf.crossing_depth(warm, DEPTHS, 26.0, direction="decreasing")
    assert np.isnan(depth) and reason == pf.OUTSIDE_PROFILE_RANGE
    assert pf.NO_DATA != pf.OUTSIDE_PROFILE_RANGE


def test_a_single_finite_level_cannot_bracket_anything():
    col = np.full(D, np.nan)
    col[0] = 29.0
    depth, reason = pf.crossing_depth(col, DEPTHS, 26.0)
    assert np.isnan(depth) and reason == pf.TOO_FEW_LEVELS


def test_multiple_crossings_are_reported_rather_than_silently_resolved():
    """An inversion crosses 26 degC three times. Returning the first is fine; implying it was the
    only one is not -- 2.3% of real density columns are non-monotone."""
    col = np.array([29.0, 28.0, 27.0, 25.0, 24.0, 25.5, 26.5, 27.2,
                    26.8, 25.0, 22.0, 18.0, 14.0, 10.0, 6.0])
    depth, reason = pf.crossing_depth(col, DEPTHS, 26.0, direction="decreasing")
    assert reason == pf.MULTIPLE_CROSSINGS
    assert np.isfinite(depth), "the first crossing is still a usable contour point"
    # hand-computed: bracket 10 m (27.0) -> 20 m (25.0), so 26.0 falls exactly halfway
    assert abs(depth - 15.0) < 1e-9
    # the same column asked the other way finds the ONE upward crossing, and calls it unique
    up, up_reason = pf.crossing_depth(col, DEPTHS, 26.0, direction="increasing")
    assert up_reason == pf.OK and 50.0 < up < 75.0


def test_a_midcolumn_gap_is_bridged_not_treated_as_the_end_of_the_water():
    """A NaN at 125 m is a hole in the data, not the seafloor. The bracket must form across it
    between the two levels that really do straddle the threshold."""
    col = sigma_theta_column().copy()
    col[8] = np.nan                                   # remove the level just past the crossing
    depth, reason = pf.crossing_depth(col, DEPTHS, 24.0, direction="increasing")
    assert reason == pf.OK
    assert 100.0 < depth < 150.0


# ==================================================== extrema, and the asymmetry

def test_an_interior_minimum_is_found_and_returned():
    c = np.array([1540, 1539, 1538, 1535, 1530, 1520, 1510, 1500,
                  1495, 1492, 1490, 1488, 1487, 1489, 1495.0])
    depth, reason = pf.extremum_depth(c, DEPTHS, "min")
    assert reason == pf.OK and depth == 500.0


def test_a_minimum_on_the_deepest_level_is_refused_because_the_real_one_is_below_the_grid():
    """The finding that decides what feature 7 can ship. A monotonically falling profile has NOT
    reached its minimum inside 0-1000 m; reporting 1000 m would put the edge of the grid on a map
    as if it were a measurement."""
    depth, reason = pf.extremum_depth(np.linspace(1540.0, 1490.0, D), DEPTHS, "min")
    assert np.isnan(depth)
    assert reason == pf.AT_DEEPEST_LEVEL


def test_a_maximum_at_the_surface_keeps_its_depth_because_no_duct_is_a_real_answer():
    """The deliberate asymmetry with the test above. A sound-speed maximum at the surface means
    the sonic layer is absent -- physics, not a gap -- and 17.5% of the real basin is like that.
    Nulling it would be rule 8 in the other direction."""
    c = np.linspace(1540.0, 1490.0, D)
    depth, reason = pf.extremum_depth(c, DEPTHS, "max")
    assert reason == pf.AT_SHALLOWEST_LEVEL
    assert depth == 0.0, "a flagged answer, not a discarded one"
    assert reason in pf.FINITE_REASONS


def test_below_m_restricts_the_search_window():
    c = np.array([1540, 1520, 1500, 1480, 1470, 1465, 1470, 1480,
                  1490, 1495, 1500, 1505, 1510, 1515, 1520.0])
    whole, r1 = pf.extremum_depth(c, DEPTHS, "min")
    assert r1 == pf.OK and whole == 50.0
    deep, r2 = pf.extremum_depth(c, DEPTHS, "min", below_m=200.0)
    assert r2 == pf.AT_SHALLOWEST_LEVEL and deep == 200.0


def test_a_window_that_excludes_every_level_says_so():
    depth, reason = pf.extremum_depth(np.linspace(1540, 1490, D), DEPTHS, "min", below_m=5000.0)
    assert np.isnan(depth) and reason == pf.NO_LEVELS_BELOW


@pytest.mark.parametrize("bad,kwargs", [("sideways", {}), ("min", {"kind": "middle"})])
def test_bad_arguments_raise_rather_than_returning_a_plausible_nan(bad, kwargs):
    col = sigma_theta_column()
    with pytest.raises(ValueError):
        if kwargs:
            pf.extremum_depth(col, DEPTHS, kwargs["kind"])
        else:
            pf.crossing_depth(col, DEPTHS, 24.0, direction=bad)


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        pf.crossing_depth([1.0, 2.0], DEPTHS, 1.5)


# ==================================================== the whole-field wrappers

def test_the_field_wrapper_codes_each_reason_and_counts_them():
    grid = np.full((4, 3, D), np.nan)
    grid[0, 0] = sigma_theta_column()                       # -> ok
    grid[1, 1] = np.full(D, 10.0)                           # -> outside_profile_range
    grid[2, 2, 0] = 21.0                                    # -> too_few_levels
    #                                                          the rest stay NaN -> no_data
    out = pf.crossing_depth_field(grid, DEPTHS, 24.0, direction="increasing")

    assert out["depth"].shape == (4, 3)
    assert out["reason"].dtype == np.int8
    assert out["counts"][pf.NO_DATA] == 9
    assert out["counts"][pf.OK] == 1
    assert out["counts"][pf.OUTSIDE_PROFILE_RANGE] == 1
    assert out["counts"][pf.TOO_FEW_LEVELS] == 1
    assert np.isfinite(out["depth"][0, 0])
    assert np.isnan(out["depth"][1, 1])
    assert out["reason_meanings"][int(out["reason"][0, 0])] == pf.OK


def test_the_reason_codes_are_stable_because_a_saved_map_outlives_the_run_that_made_it():
    """Integer codes end up in artifacts and in rendered maps. Reordering REASONS would silently
    relabel every one already written, so the first entries are pinned."""
    assert pf.REASONS[0] == pf.OK
    assert pf.REASON_CODE[pf.OK] == 0
    assert len(set(pf.REASON_CODE.values())) == len(pf.REASONS)
    assert all(pf.CODE_REASON[v] == k for k, v in pf.REASON_CODE.items())


# ==================================================== against real data

BUNDLE = os.path.join("data", "processed", "daily_sat", "v001", "2025.npz")


@pytest.mark.skipif(not os.path.exists(BUNDLE), reason="satellite bundle not on this machine")
def test_on_real_data_the_sound_speed_minimum_is_below_the_grid_almost_everywhere():
    """The measurement that decides whether a SOFAR-axis map can be shipped at all.

    If this ever drops well below 90%, either the bundle changed or the sound-speed function did,
    and the acoustics page's central caveat needs re-measuring before it is shown to anyone.
    """
    from phase2.physics.seawater import sound_speed

    z = np.load(BUNDLE, allow_pickle=True)
    c = sound_speed(z["salinity"][100], z["temp"][100], DEPTHS)
    full = np.isfinite(c).all(axis=-1)
    assert full.sum() > 5000, "too few full-depth cells for this to mean anything"

    k = np.argmin(np.where(np.isfinite(c), c, np.inf), axis=-1)
    frac_at_bottom = float(((k == D - 1) & full).sum() / full.sum())
    assert frac_at_bottom > 0.90, f"only {frac_at_bottom:.1%} at the deepest level"

    # and the primitive must actually refuse those, not report 1000 m
    i, j = np.argwhere((k == D - 1) & full)[0]
    depth, reason = pf.extremum_depth(c[i, j], DEPTHS, "min")
    assert np.isnan(depth) and reason == pf.AT_DEEPEST_LEVEL
