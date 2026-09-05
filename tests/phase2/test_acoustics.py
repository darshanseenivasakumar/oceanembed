"""Sound speed, the sonic layer and the SOFAR axis. Owner: Unit A (Arjhun).

Every failure guarded here produces a NUMBER, not an error: a sound channel found in ten metres of
water, an axis reported at the bottom of the grid, a duct depth of zero that means "no duct". A
shape check sees none of them.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.derived import acoustics as AC
from phase2.derived import profile_features as pf

Z = np.asarray(base.DEPTHS, dtype="float64")
D = base.N_DEPTHS
BUNDLE = os.path.join("data", "processed", "daily_sat", "v001", "2025.npz")


def tropical_column():
    """Warm surface, sharp thermocline, cold deep: sound speed falls all the way to 1000 m and has
    NOT turned around -- the real North Indian Ocean case, 95% of the basin."""
    t = np.array([29.0, 28.9, 28.7, 28.0, 27.0, 25.0, 22.0, 19.0,
                  17.0, 15.5, 13.0, 11.0, 9.0, 7.5, 5.0])
    return np.full(D, 35.0), t


def channelled_column():
    """A column whose sound speed genuinely turns around inside 1000 m -- the ~5% case. Built by
    cooling fast then letting the pressure term win."""
    t = np.array([29.0, 28.0, 26.0, 22.0, 18.0, 12.0, 8.0, 6.0,
                  5.2, 4.8, 4.4, 4.2, 4.1, 4.05, 4.0])
    return np.full(D, 35.0), t


# ==================================================== sound speed over a field

def test_sound_speed_field_keeps_salinity_first():
    """The module-wide convention. A caller who followed Mackenzie's printed c(T,S,D) would get a
    plausible number, so the ordering is pinned here as well as in test_physics."""
    S, t = tropical_column()
    c = AC.sound_speed_field(S, t)
    assert c.shape == (D,)
    assert abs(float(AC.sound_speed_field(np.array([35.0]), np.array([25.0]),
                                          np.array([1000.0]))[0]) - 1550.744) < 5e-3


def test_mismatched_inputs_raise_rather_than_broadcasting():
    with pytest.raises(ValueError):
        AC.sound_speed_field(np.zeros((4, 15)), np.zeros((4, 14)))
    with pytest.raises(ValueError):
        AC.sound_speed_field(np.zeros((4, 9)), np.zeros((4, 9)))


def test_the_envelope_mask_flags_the_plume():
    S, t = tropical_column()
    assert AC.in_envelope(S, t).all()
    fresh = S.copy()
    fresh[:3] = 12.0                                  # Ganges/Meghna surface layer
    assert not AC.in_envelope(fresh, t)[:3].any()
    assert AC.in_envelope(fresh, t)[3:].all()


# ==================================================== sonic layer depth

def test_a_surface_maximum_is_no_duct_and_keeps_its_depth():
    """0.0 m with reason NO_DUCT is a finite, meaningful answer -- "the duct is absent" -- and
    17.5% of the real basin is like that. Nulling it would be rule 8 in the other direction."""
    S, t = tropical_column()
    depth, why = AC.sonic_layer_depth(AC.sound_speed_field(S, t))
    assert why == AC.NO_DUCT
    assert depth == 0.0
    assert AC.SLD_LABEL[why] == "no surface duct"


def test_a_real_duct_is_found_at_its_own_depth():
    """A near-surface temperature inversion makes a genuine duct: sound speed rises to a maximum
    below the surface, then falls."""
    S = np.full(D, 35.0)
    t = np.array([27.0, 27.4, 27.9, 28.4, 28.2, 27.0, 24.0, 21.0,
                  18.0, 16.0, 13.0, 11.0, 9.0, 7.5, 6.5])
    depth, why = AC.sonic_layer_depth(AC.sound_speed_field(S, t))
    assert why == AC.OK
    assert 10.0 <= depth <= 50.0


def test_a_land_column_is_no_data_not_a_duct_at_zero():
    depth, why = AC.sonic_layer_depth(np.full(D, np.nan))
    assert np.isnan(depth) and why == AC.NO_DATA


# ==================================================== the SOFAR guard

def test_a_shelf_column_cannot_have_a_sound_channel():
    """THE bug this guard exists for, found by clicking 8.25 N 78.00 E on the page.

    That cell is the Palk Strait: three finite levels, about ten metres of water. Without the
    column requirement it reported "axis resolved" at 5 m -- a five-metre dip in a ten-metre column
    presented as a SOFAR channel. On real GLORYS T/S, 336 of 848 supposedly-resolved cells (40%)
    were shelf artifacts exactly like it.
    """
    c = np.full(D, np.nan)
    c[:3] = [1543.3, 1543.2, 1543.4]                  # a dip at 5 m, in 10 m of water
    depth, why = AC.sofar_axis(c)
    assert np.isnan(depth)
    assert why == AC.TOO_SHALLOW
    assert AC.SOFAR_LABEL[why] == "water too shallow for a sound channel"

    # and the guard is what does it: relax the requirement and the artifact comes straight back
    depth_relaxed, why_relaxed = AC.sofar_axis(c, min_column_m=0.0)
    assert why_relaxed == AC.OK and depth_relaxed == 5.0, (
        "the guard must be the only thing standing between this column and a fabricated axis")


def test_a_full_depth_column_that_never_turns_around_says_the_axis_is_below_the_grid():
    """94.75% of the real basin. Reporting 1000 m would be the edge of the grid as a measurement."""
    S, t = tropical_column()
    depth, why = AC.sofar_axis(AC.sound_speed_field(S, t))
    assert np.isnan(depth) and why == AC.BELOW_GRID
    assert AC.SOFAR_LABEL[why] == "axis below 1000 m"


def test_a_genuine_channel_inside_the_grid_is_found():
    """The ~5% case must still work, or the guard has simply switched the feature off."""
    S, t = channelled_column()
    c = AC.sound_speed_field(S, t)
    depth, why = AC.sofar_axis(c)
    assert why == AC.OK
    assert 100.0 <= depth <= 900.0
    assert c[int(np.argmin(c))] == c.min()


def test_the_column_requirement_is_stated_as_a_constant_not_buried():
    assert AC.SOFAR_MIN_COLUMN_M == 1000.0


# ==================================================== the error budget

def test_temperature_dominates_the_sound_speed_error_budget():
    """The claim that makes an acoustic product from a temperature model defensible."""
    b = AC.error_budget(20.81, 35.19, 100.0, t_rmse=0.9078, s_rmse=0.2695)
    assert b["from_temperature_m_s"] > 2.0
    assert 0.0 < b["from_salinity_m_s"] < 0.5
    assert b["dominance"] > 5.0
    assert b["temperature_share"] > 0.8


def test_cold_water_is_MORE_temperature_dominated_not_less():
    """The budget must move with conditions rather than return a remembered constant -- and the
    direction it moves in is not the intuitive one.

    Mackenzie's quadratic term is negative, so dc/dT = 4.591 - 0.106T + 7.1e-4 T^2 FALLS as water
    warms: 4.08 m/s per degC at 5 degC against 2.11 at 29. The salinity coefficient
    1.340 - 0.01025T weakens far less. So a cold deep column is roughly 10.5x temperature-dominated
    where a warm surface one is 6.7x -- the opposite of the guess that warm water, being more
    variable, must be more temperature-sensitive.
    """
    warm = AC.error_budget(29.0, 35.0, 0.0, t_rmse=0.9078, s_rmse=0.2695)
    cold = AC.error_budget(5.0, 35.0, 1000.0, t_rmse=0.9078, s_rmse=0.2695)
    assert warm["dominance"] != cold["dominance"], "the budget is a constant, not a calculation"
    assert cold["dominance"] > warm["dominance"]
    assert cold["dominance"] > 9.0 and warm["dominance"] < 8.0


def test_a_zero_salinity_error_gives_infinite_dominance_rather_than_dividing_by_zero():
    b = AC.error_budget(25.0, 35.0, 100.0, t_rmse=0.9078, s_rmse=0.0)
    assert b["from_salinity_m_s"] == 0.0
    assert b["dominance"] == float("inf")


# ==================================================== whole-field, and against real data

def test_layer_maps_partition_every_cell():
    S = np.full((3, 4, D), 35.0)
    t = np.broadcast_to(tropical_column()[1], (3, 4, D)).copy()
    t[0, 0] = np.nan                                   # a land column
    m = AC.layer_maps(S, t)
    for key in ("sld", "sofar"):
        assert sum(m[key]["counts"].values()) == 12
    assert m["sofar"]["counts"][pf.NO_DATA] == 1


@pytest.mark.skipif(not os.path.exists(BUNDLE), reason="satellite bundle not on this machine")
def test_on_real_data_the_categories_partition_the_basin_exactly():
    """The arithmetic that proves the guard is not quietly eating cells.

    MEASURED 2026-09-05 on 2025-09-09: 8,502 below grid + 471 resolved = 8,973, which is exactly
    the number of cells with water at all 15 levels; plus 2,859 too shallow = 11,832 ocean cells,
    the same total artifacts/export_timing.json records.
    """
    z = np.load(BUNDLE, allow_pickle=True)
    S, t = z["salinity"][100], z["temp"][100]
    m = AC.layer_maps(S, t)
    c = m["sound_speed"]

    counts = m["sofar"]["counts"]
    full_depth = int(np.isfinite(c).all(axis=-1).sum())
    ocean = int(np.isfinite(c).any(axis=-1).sum())

    assert sum(counts.values()) == base.N_LAT * base.N_LON == 24000
    assert counts.get(pf.AT_DEEPEST_LEVEL, 0) + counts.get(pf.OK, 0) == full_depth, (
        "every full-depth column must be either resolved or below-grid, and nothing else")
    assert counts.get(pf.COLUMN_TOO_SHALLOW, 0) == ocean - full_depth
    assert counts.get(pf.NO_DATA, 0) == 24000 - ocean


@pytest.mark.skipif(not os.path.exists(BUNDLE), reason="satellite bundle not on this machine")
def test_on_real_data_every_resolved_axis_is_at_an_interior_depth():
    """The shelf artifacts reported axes at 5, 10, 20, 30 m. With the guard the surviving cells
    must all sit well inside the column -- no surface levels, and never the deepest one."""
    z = np.load(BUNDLE, allow_pickle=True)
    m = AC.layer_maps(z["salinity"][100], z["temp"][100])
    d = m["sofar"]["depth"]
    got = d[np.isfinite(d)]
    assert got.size > 100, "too few resolved axes for this to mean anything"
    assert got.min() >= 100.0, f"an axis at {got.min()} m is a shelf artifact, not a channel"
    assert got.max() < 1000.0, "an axis at the deepest level is the grid edge, not a measurement"


@pytest.mark.skipif(not os.path.exists(BUNDLE), reason="satellite bundle not on this machine")
def test_on_real_data_the_sofar_axis_is_unresolvable_for_the_vast_majority():
    """The finding that decides what this feature can ship. If this ever drops well below 90% the
    acoustics page's central caveat needs re-measuring before it is shown to anyone."""
    z = np.load(BUNDLE, allow_pickle=True)
    m = AC.layer_maps(z["salinity"][100], z["temp"][100])
    c = m["sound_speed"]
    full = int(np.isfinite(c).all(axis=-1).sum())
    below = m["sofar"]["counts"].get(pf.AT_DEEPEST_LEVEL, 0)
    assert below / full > 0.90, f"only {below / full:.1%} of full-depth cells are below-grid"
