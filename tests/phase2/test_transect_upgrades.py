"""The transect upgrades: multi-key sampling, derived overlays, Argo on a section, sliding.

Owner: Unit A (Arjhun). The original `tests/phase2/test_transect.py` is left alone -- it pins the
behaviour these changes had to preserve, and the first assertion here is that it still does.

Every failure guarded below returns a well-formed answer rather than raising: a contour line that
is blank because the function cannot do the job, a track that quietly shrinks instead of sliding, a
float compared against a model profile read at the wrong place.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.derived import profile_features as pf
from phase2.derived import transect as T

D = config.N_DEPTHS


def a_field(**over):
    """A whole (100, 240, 15) field with a simple, checkable structure."""
    shape = (config.N_LAT, config.N_LON, D)
    z = np.asarray(config.DEPTHS, dtype="float64")
    f = {
        "temperature": np.broadcast_to(30.0 - z / 40.0, shape).copy(),
        "sigma": np.full(shape, 0.5),
        "salinity": np.broadcast_to(34.0 + z / 500.0, shape).copy(),
    }
    f.update(over)
    return f


# ==================================================== multi-key sampling

def test_the_default_keys_are_the_original_pair_so_existing_callers_are_untouched():
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=12)
    sec = T.sample_transect(track, a_field())
    assert set(sec) == {"temperature", "sigma", "lat", "lon", "distance_km", "depths"}
    assert sec["temperature"].shape == (12, D)


def test_extra_keys_are_sampled_through_the_same_nan_strict_path():
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=12)
    sec = T.sample_transect(track, a_field(), keys=("temperature", "sigma", "salinity"))
    assert sec["salinity"].shape == (12, D)
    # the fixture's salinity depends only on depth, so every along-track row must agree
    col = sec["salinity"][np.isfinite(sec["salinity"]).all(axis=1)]
    assert col.size and np.allclose(col, col[0])


def test_asking_for_a_key_the_field_does_not_carry_raises_rather_than_returning_nan():
    """A stage-1 field has salinity=None. Sampling it silently would give an all-NaN section, and
    an all-NaN density overlay is indistinguishable from "no isopycnals here"."""
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=6)
    with pytest.raises(KeyError, match="salinity"):
        T.sample_transect(track, {"temperature": a_field()["temperature"], "salinity": None},
                          keys=("temperature", "salinity"))


def test_a_wrongly_shaped_field_raises_and_names_the_offender():
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=6)
    bad = a_field()
    bad["sigma"] = np.zeros((10, 10, D))
    with pytest.raises(ValueError, match="sigma"):
        T.sample_transect(track, bad)


# ==================================================== derived overlays

def test_add_derived_produces_density_and_sound_speed_in_physical_ranges():
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=20)
    sec = T.add_derived(T.sample_transect(track, a_field(),
                                          keys=("temperature", "sigma", "salinity")))
    for key, lo, hi in [("sigma_theta", 18.0, 30.0), ("sound_speed", 1400.0, 1600.0)]:
        v = sec[key]
        assert v.shape == (20, D)
        got = v[np.isfinite(v)]
        assert got.size and lo < got.min() and got.max() < hi, f"{key} outside {lo}-{hi}"


def test_add_derived_refuses_a_section_with_no_salinity():
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=6)
    with pytest.raises(KeyError, match="salinity"):
        T.add_derived(T.sample_transect(track, a_field()))


def test_the_derived_arrays_are_gapped_exactly_where_the_inputs_are():
    """Density computed across a seafloor gap would bridge the bottom with a number."""
    f = a_field()
    f["temperature"][:, :, 10:] = np.nan
    f["salinity"][:, :, 10:] = np.nan
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=8)
    sec = T.add_derived(T.sample_transect(track, f, keys=("temperature", "sigma", "salinity")))
    assert np.array_equal(np.isfinite(sec["sigma_theta"]), np.isfinite(sec["temperature"]))
    assert not np.isfinite(sec["sound_speed"][:, 10:]).any()


def test_the_density_overlay_needs_the_new_contour_finder_not_the_isotherm_one():
    """The reason the foundation branch exists, at section scale.

    sigma_theta rises with depth, so `isotherm_depth`'s "surface must already exceed the threshold"
    precondition fails at every point and the line comes back blank -- with no error.
    """
    track = T.track_points(10.0, 85.0, 15.0, 95.0, n=30)
    sec = T.add_derived(T.sample_transect(track, a_field(),
                                          keys=("temperature", "sigma", "salinity")))
    level = float(np.nanmedian(sec["sigma_theta"]))

    old = T.isotherm_line({"temperature": sec["sigma_theta"], "depths": sec["depths"]}, level)
    assert not np.isfinite(old).any(), "the old finder unexpectedly worked -- re-read both"

    line, reasons = pf.contour_line(sec["sigma_theta"], sec["depths"], level,
                                    direction="increasing")
    assert np.isfinite(line).sum() > 20
    assert pf.tally(reasons)[pf.OK] > 20


# ==================================================== sliding

@pytest.mark.parametrize("shift", [0.0, 5.0, -12.25, 40.0, -40.0])
def test_sliding_never_changes_the_span_of_the_track(shift):
    """The bug: clipping each endpoint independently lets one end stop at the grid edge while the
    other keeps moving, so the line shrinks and the section quietly becomes a different one."""
    lo, hi = float(config.LON[0]), float(config.LON[-1])
    a, b, used = T.slide(85.0, 95.0, shift, lo, hi)
    assert abs((b - a) - 10.0) < 1e-9, f"span became {b - a}"
    assert lo - 1e-9 <= a <= hi + 1e-9 and lo - 1e-9 <= b <= hi + 1e-9
    assert abs(used) <= abs(shift) + 1e-9


def test_a_shift_that_would_leave_the_grid_is_trimmed_and_says_so():
    lo, hi = float(config.LON[0]), float(config.LON[-1])
    a, b, used = T.slide(85.0, 95.0, 30.0, lo, hi)
    assert used < 30.0, "the request must be trimmed"
    assert abs(b - hi) < 1e-9, "the leading end should stop exactly at the boundary"
    assert abs((b - a) - 10.0) < 1e-9


def test_sliding_works_in_both_directions_and_is_symmetric_in_the_middle():
    lo, hi = float(config.LON[0]), float(config.LON[-1])
    east = T.slide(70.0, 80.0, 5.0, lo, hi)
    west = T.slide(70.0, 80.0, -5.0, lo, hi)
    assert east[2] == 5.0 and west[2] == -5.0
    assert east[0] - 70.0 == 5.0 and 70.0 - west[0] == 5.0


# ==================================================== Argo on a section

class _FakeMatch:
    def __init__(self, lat, lon, prof, off_days=0.0):
        self.latitude, self.longitude = lat, lon
        self.datetime, self.temporal_offset_days = "2026-05-15", off_days
        self.temperature_profile = prof
        self.spatial_offset_km, self.n_levels = 0.0, len([p for p in prof if p is not None])


def test_floats_are_placed_at_their_own_along_track_distance(monkeypatch):
    """A float scattered at the wrong along-track position lands on the wrong water and its error
    colour reads as a model failure somewhere the model never claimed anything."""
    track = T.track_points(10.0, 85.0, 10.0, 95.0, n=41)      # due east, 41 points
    lat, lon, dist = track
    near_start = _FakeMatch(float(lat[2]), float(lon[2]), [25.0] * D)
    near_end = _FakeMatch(float(lat[-3]), float(lon[-3]), [25.0] * D)
    monkeypatch.setattr("phase2.validation.argo_overlay.find_nearest_profiles",
                        lambda *a, **k: [near_end, near_start])

    got = T.floats_near_track(track, "2026-05-15", a_field(), max_km=50.0)
    assert len(got) == 2
    assert got[0]["distance_km"] < got[1]["distance_km"], "results must be sorted along the track"
    assert abs(got[0]["distance_km"] - float(dist[2])) < 1e-6
    assert abs(got[1]["distance_km"] - float(dist[-3])) < 1e-6


def test_a_float_beyond_the_radius_is_dropped_not_snapped_to_the_line(monkeypatch):
    track = T.track_points(10.0, 85.0, 10.0, 95.0, n=41)
    far = _FakeMatch(20.0, 90.0, [25.0] * D)                  # ~1100 km north of the track
    monkeypatch.setattr("phase2.validation.argo_overlay.find_nearest_profiles",
                        lambda *a, **k: [far])
    assert T.floats_near_track(track, "2026-05-15", a_field(), max_km=75.0) == []


def test_a_float_with_no_overlapping_level_is_dropped_rather_than_scored_zero(monkeypatch):
    """All-None profile: there is no error to report, and reporting 0.0 would read as perfect."""
    track = T.track_points(10.0, 85.0, 10.0, 95.0, n=41)
    empty = _FakeMatch(10.0, 90.0, [None] * D)
    monkeypatch.setattr("phase2.validation.argo_overlay.find_nearest_profiles",
                        lambda *a, **k: [empty])
    assert T.floats_near_track(track, "2026-05-15", a_field(), max_km=75.0) == []


def test_the_error_is_model_minus_float_and_the_offsets_travel_with_it(monkeypatch):
    """Sign convention, and the fact that a distant float is a weaker check than a near one -- a
    panel that drops the offsets is overstating its own validation."""
    track = T.track_points(10.0, 85.0, 10.0, 95.0, n=41)
    prof = [20.0] * D                                          # float reads 20 everywhere
    m = _FakeMatch(float(track[0][5]), float(track[1][5]), prof, off_days=-3.0)
    monkeypatch.setattr("phase2.validation.argo_overlay.find_nearest_profiles",
                        lambda *a, **k: [m])
    got = T.floats_near_track(track, "2026-05-15", a_field(), max_km=75.0)[0]

    surface_model = 30.0                                       # the fixture at z = 0
    assert abs(got["error"][0] - (surface_model - 20.0)) < 1e-6, "sign must be model minus float"
    assert got["temporal_offset_days"] == -3.0
    assert got["offset_km"] < 1.0
    assert got["n_levels_compared"] == D
    assert got["rmse"] > 0


# ==================================================== against the real model

BUNDLE = os.path.join("data", "processed", "daily_sat", "v001", "2025.npz")


@pytest.mark.skipif(
    not (os.path.exists(config.art("tscast_stage2_sat_s2.pt")) and os.path.exists(BUNDLE)),
    reason="stage-2 checkpoint or satellite bundle not on this machine")
def test_on_the_real_model_an_isopycnal_is_drawn_where_the_old_finder_drew_nothing():
    """MEASURED 2026-09-05 on an 8N 68E -> 20N 88E section from the stage-2 field: the 24 kg/m3
    isopycnal is resolved at 26 of 60 points by contour_line and at 0 of 60 by isotherm_line."""
    from phase2.tscast_nio import field_cache as FC

    f = FC.field_for("2026-05-15", stage=2, keep=FC.ALL_KEYS)
    track = T.track_points(8.0, 68.0, 20.0, 88.0, n=60)
    sec = T.add_derived(T.sample_transect(track, f, keys=("temperature", "sigma", "salinity")))

    line, reasons = pf.contour_line(sec["sigma_theta"], sec["depths"], 24.0,
                                    direction="increasing")
    tally = pf.tally(reasons)
    assert np.isfinite(line).sum() >= 15, tally
    assert tally.get(pf.NO_DATA, 0) > 0, "this track should cross land, or it is the wrong track"

    old = T.isotherm_line({"temperature": sec["sigma_theta"], "depths": sec["depths"]}, 24.0)
    assert not np.isfinite(old).any()
