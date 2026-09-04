"""The transect must measure distance correctly, interpolate exactly, and gap across land.

The four risks, in order of how quietly they would corrupt a section:
  1. bilinear_at smoothing a value across a land or seafloor cell instead of leaving a gap.
  2. bilinear_at silently extrapolating outside the grid.
  3. track_points bunching points where the line runs east-west (naive lat/lon spacing).
  4. isotherm_depth disagreeing with the shipped D26 it generalises.
"""
from __future__ import annotations

import os
import numpy as np
import pytest

from phase2.tscast_nio import config
from phase2.derived import transect as T

LAT = np.asarray(config.LAT, dtype="float64")
LON = np.asarray(config.LON, dtype="float64")


# ------------------------------------------------------------------- geometry

def test_haversine_matches_a_hand_computed_distance():
    # 1 degree of latitude is ~111.19 km on this sphere.
    d = float(T.haversine_km(15.0, 65.0, 16.0, 65.0))
    assert d == pytest.approx(111.19, abs=0.5)
    # a known east-west pair: 1 deg lon at 15 N is ~107.4 km
    d2 = float(T.haversine_km(15.0, 65.0, 15.0, 66.0))
    assert d2 == pytest.approx(107.4, abs=0.6)


def test_track_points_are_evenly_spaced_by_distance():
    lat, lon, dist = T.track_points(8.0, 68.0, 20.0, 90.0, n=40)
    assert lat.size == lon.size == dist.size == 40
    # consecutive haversine gaps are near-constant (even in distance, not in degrees)
    seg = T.haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
    assert seg.std() / seg.mean() < 0.02, "points are not evenly spaced by distance"
    # the recorded distance axis matches the actual great-circle distance from the start
    actual = T.haversine_km(lat[0], lon[0], lat, lon)
    np.testing.assert_allclose(dist, actual, atol=1.0)
    # endpoints land exactly on the requested corners
    assert (lat[0], lon[0]) == pytest.approx((8.0, 68.0))
    assert (lat[-1], lon[-1]) == pytest.approx((20.0, 90.0), abs=1e-6)


def test_a_degenerate_track_does_not_blow_up():
    lat, lon, dist = T.track_points(15.0, 65.0, 15.0, 65.0, n=10)
    assert np.allclose(lat, 15.0) and np.allclose(lon, 65.0)
    assert np.allclose(dist, 0.0)


# ---------------------------------------------------------------- bilinear_at

def test_bilinear_is_exact_at_a_grid_node():
    field = np.arange(LAT.size * LON.size, dtype="float64").reshape(LAT.size, LON.size)
    for (i, j) in [(0, 0), (10, 20), (LAT.size - 1, LON.size - 1)]:
        got = T.bilinear_at(field, LAT[i], LON[j], LAT, LON)
        assert got == pytest.approx(field[i, j]), f"node ({i},{j}) not exact"


def test_bilinear_is_correct_strictly_between_four_nodes():
    field = np.zeros((LAT.size, LON.size))
    i, j = 5, 5
    field[i, j], field[i, j + 1], field[i + 1, j], field[i + 1, j + 1] = 10.0, 20.0, 30.0, 40.0
    # dead centre of the cell -> mean of the four corners
    mid_lat = (LAT[i] + LAT[i + 1]) / 2
    mid_lon = (LON[j] + LON[j + 1]) / 2
    assert T.bilinear_at(field, mid_lat, mid_lon, LAT, LON) == pytest.approx(25.0)
    # a quarter of the way in lon, on the lower lat row -> 10*.75 + 20*.25 = 12.5
    q_lon = LON[j] + 0.25 * (LON[j + 1] - LON[j])
    assert T.bilinear_at(field, LAT[i], q_lon, LAT, LON) == pytest.approx(12.5)


def test_bilinear_returns_nan_when_any_corner_is_land():
    field = np.ones((LAT.size, LON.size))
    i, j = 8, 8
    field[i + 1, j + 1] = np.nan                       # one corner is land / below seafloor
    mid_lat = (LAT[i] + LAT[i + 1]) / 2
    mid_lon = (LON[j] + LON[j + 1]) / 2
    assert np.isnan(T.bilinear_at(field, mid_lat, mid_lon, LAT, LON)), (
        "a cell touching land must be a gap, never a blended value"
    )


def test_bilinear_never_extrapolates_outside_the_grid():
    field = np.ones((LAT.size, LON.size))
    assert np.isnan(T.bilinear_at(field, LAT[0] - 0.5, LON[0], LAT, LON))
    assert np.isnan(T.bilinear_at(field, LAT[0], LON[-1] + 0.5, LAT, LON))


# --------------------------------------------------------------- sample_transect

def _synthetic_field(land_cell=None):
    """A field whose temperature increases smoothly with latitude and decreases with depth, so an
    interpolated value is predictable. Optionally punch a land column (all-NaN) at land_cell=(i,j)."""
    temp = np.zeros((config.N_LAT, config.N_LON, config.N_DEPTHS))
    for d in range(config.N_DEPTHS):
        temp[:, :, d] = LAT[:, None] - 0.01 * config.DEPTHS[d]
    sigma = np.full_like(temp, 0.3)
    if land_cell is not None:
        i, j = land_cell
        temp[i, j, :] = np.nan
        sigma[i, j, :] = np.nan
    return {"temperature": temp, "sigma": sigma,
            "land_mask": np.zeros((config.N_LAT, config.N_LON), bool)}


def test_sample_transect_shape_and_surface_values():
    field = _synthetic_field()
    track = T.track_points(6.0, 60.0, 25.0, 60.0, n=30)   # due north, on the 60E meridian
    sec = T.sample_transect(track, field)
    assert sec["temperature"].shape == (30, config.N_DEPTHS)
    assert sec["sigma"].shape == (30, config.N_DEPTHS)
    # surface temp along the track should equal the track latitude (field is lat at depth 0)
    np.testing.assert_allclose(sec["temperature"][:, 0], sec["lat"], atol=1e-6)


def test_a_track_crossing_land_gaps_there_and_only_there():
    i, j = 40, 60                                        # a land column
    field = _synthetic_field(land_cell=(i, j))
    # a track passing straight through that cell's centre
    lat_c, lon_c = LAT[i], LON[j]
    track = T.track_points(lat_c - 1.0, lon_c, lat_c + 1.0, lon_c, n=51)
    sec = T.sample_transect(track, field)
    surf = sec["temperature"][:, 0]
    n_gap = int(np.isnan(surf).sum())
    assert n_gap >= 1, "the land crossing produced no gap"
    assert n_gap < surf.size, "the whole track went NaN - land handling is too aggressive"
    # the gap is where the track is nearest the land cell, not smeared across the whole line
    nearest = int(np.argmin(T.haversine_km(sec["lat"], sec["lon"], lat_c, lon_c)))
    assert np.isnan(surf[nearest])
    assert np.isfinite(surf[0]) and np.isfinite(surf[-1])


# ------------------------------------------------------------------ isotherms

def test_isotherm_depth_matches_a_hand_computed_crossing():
    # 20 m = 27, 30 m = 25, so 26 is crossed exactly halfway between them: depth = 25 m.
    depths = np.asarray(config.DEPTHS, dtype="float64")
    k20, k30 = list(config.DEPTHS).index(20), list(config.DEPTHS).index(30)
    prof = np.empty(depths.size)
    prof[:k20] = 28.0        # 0, 5, 10 m: all warm, above threshold
    prof[k20] = 27.0         # 20 m
    prof[k30] = 25.0         # 30 m  -> first level below 26, brackets the crossing with 20 m
    prof[k30 + 1:] = 20.0    # deeper: colder still
    got = T.isotherm_depth(prof, depths, 26.0)
    assert got == pytest.approx(25.0, abs=1e-9)


def test_isotherm_generalises_the_shipped_d26_exactly():
    """At threshold 26, this must agree with heat_content.d26_from_profile on the same profile -
    it is the same method, and a divergence would mean one of them is wrong."""
    from phase2.derived import heat_content as hc
    rng = np.random.default_rng(3)
    depths = np.asarray(config.DEPTHS, dtype="float64")
    for _ in range(20):
        prof = np.sort(rng.uniform(18.0, 31.0, depths.size))[::-1]   # warm at top, cools with depth
        a = T.isotherm_depth(prof, depths, 26.0)
        b = hc.d26_from_profile(prof, depths)
        if np.isnan(a) or np.isnan(b):
            assert np.isnan(a) and np.isnan(b)
        else:
            assert a == pytest.approx(b, abs=1e-9)


def test_isotherm_is_nan_when_the_surface_is_below_threshold():
    depths = np.asarray(config.DEPTHS, dtype="float64")
    prof = np.full(depths.size, 24.0)                   # never reaches 26 anywhere
    assert np.isnan(T.isotherm_depth(prof, depths, 26.0))


def test_isotherm_line_opens_a_gap_where_the_water_is_too_cold():
    field = _synthetic_field()                          # surface temp = latitude
    # southern points (lat < 26) never reach 26 C at the surface -> isotherm NaN there
    track = T.track_points(10.0, 60.0, 29.0, 60.0, n=20)
    sec = T.sample_transect(track, field)
    line = T.isotherm_line(sec, 26.0)
    assert np.isnan(line).any() and np.isfinite(line).any(), (
        "the isotherm line should be present where warm and gapped where cold"
    )


def test_a_missing_D26_is_not_reported_as_a_cold_surface():
    """Three different things make D26 undefined, and only one of them is a temperature fact.

    `make_transect.py` used to print every NaN D26 as "points below 26 C at the surface". On an
    8N 68E -> 20N 88E track for 2026-05-15 that was wrong for all 22 of them: 17 were LAND (the
    great circle crosses India) and 5 were columns that never cool to 26 C, while the surface read
    30.16-31.29 C throughout. Reporting land as a temperature condition is the same error class as
    letting a missing value read as zero -- and on a cyclone-relevant chart it is the more
    dangerous direction, since "cold surface" is the signal a reader is looking for.
    """
    import numpy as np
    from phase2.derived import transect as T

    depths = np.asarray(config.DEPTHS, dtype="float64")
    warm_to_bottom = np.full(len(depths), 29.0)          # never crosses 26
    all_nan = np.full(len(depths), np.nan)               # land
    cools = np.linspace(30.0, 8.0, len(depths))          # crosses 26 properly

    assert np.isnan(T.isotherm_depth(warm_to_bottom, depths, 26.0))
    assert np.isnan(T.isotherm_depth(all_nan, depths, 26.0))
    d = T.isotherm_depth(cools, depths, 26.0)
    assert np.isfinite(d) and 0.0 < d < 1000.0

    # the reporting must be able to tell them apart -- the source is the guard
    src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                            "scripts", "phase2", "make_transect.py"), encoding="utf-8").read()
    assert "below 26 C at the surface)" not in src, (
        "the old wording is back: it reports land and warm-to-bottom columns as a cold surface")
    for cause in ("no valid water", "never cool to 26 C", "surface already below 26 C"):
        assert cause in src, f"the D26 report no longer distinguishes: {cause}"
