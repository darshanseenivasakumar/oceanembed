"""Tests for the daily wind fetch + regrid — PS requirement 8.

The point of every test here is trap #5: the wind grid is offset from ours, so a regrid that is
right by SHAPE can still be wrong by ~14 km at every cell. These assert on COORDINATES.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from phase2.data import download_wind_daily as W


def _source_grid():
    """The real NRT wind grid over our box [VERIFIED from a live 1-day probe, 2026-08-30]."""
    lat = np.arange(4.9375, 29.8126, 0.125)
    lon = np.arange(44.9375, 104.8126, 0.125)
    return lat, lon


def test_source_grid_shares_no_point_with_our_grid():
    """The trap itself: if these grids overlapped, positional assignment would be harmless."""
    lat, lon = _source_grid()
    assert not np.any(np.isclose(lat[:, None], config.LAT[None, :], atol=1e-9)), (
        "a wind latitude coincides with a config latitude -- the offset this module corrects "
        "for is not present, so re-derive the regrid before trusting it"
    )
    assert not np.any(np.isclose(lon[:, None], config.LON[None, :], atol=1e-9))
    # and every wind point is a real distance from the nearest config point
    d = np.abs(lat[:, None] - config.LAT[None, :]).min(axis=1)
    assert np.allclose(d, 0.0625), f"expected a uniform 0.0625 deg offset, got {np.unique(d)}"


def test_regrid_lands_on_the_config_grid_by_coordinate_not_shape():
    """Shape (100,240) is necessary but proves nothing. Prove the VALUES sit where we claim."""
    lat, lon = _source_grid()
    # A field whose value IS its own latitude: the block mean of a linear field is the cell centre.
    field = np.broadcast_to(lat[:, None], (len(lat), len(lon))).astype(np.float32)
    out = W.regrid_to_config(lat, lon, field)

    assert out.shape == (len(config.LAT), len(config.LON))
    recovered = out[:, 0]
    assert np.allclose(recovered, config.LAT, atol=1e-5), (
        "the regridded field does not reproduce config.LAT -- the output is on some OTHER grid.\n"
        f"  first three recovered: {recovered[:3]}\n  first three config.LAT: {config.LAT[:3]}"
    )

    lonfield = np.broadcast_to(lon[None, :], (len(lat), len(lon))).astype(np.float32)
    assert np.allclose(W.regrid_to_config(lat, lon, lonfield)[0, :], config.LON, atol=1e-5)


def test_regrid_is_the_mean_of_the_four_source_cells():
    lat, lon = _source_grid()
    rng = np.random.default_rng(0)
    field = rng.normal(size=(len(lat), len(lon))).astype(np.float32)
    out = W.regrid_to_config(lat, lon, field)
    # cell (7, 13) must be the mean of source rows 14:16 and columns 26:28
    assert np.isclose(out[7, 13], field[14:16, 26:28].mean(), atol=1e-5)


def test_positional_assignment_would_have_been_wrong():
    """Records WHY the coordinate path exists: the naive shortcut disagrees measurably."""
    lat, lon = _source_grid()
    field = np.broadcast_to(lat[:, None], (len(lat), len(lon))).astype(np.float32)
    correct = W.regrid_to_config(lat, lon, field)
    naive = field[::2, ::2]                      # "just take every other point" -- same shape!
    assert naive.shape == correct.shape
    off = np.abs(naive[:, 0] - config.LAT).max()
    assert off > 0.05, "the naive path happens to agree here; the guard below is then untested"
    assert not np.allclose(naive[:, 0], config.LAT, atol=1e-3)


def test_regrid_refuses_a_grid_that_does_not_nest():
    lat, lon = _source_grid()
    bad_lat = lat + 0.03125                       # a half-cell shift: same shape, wrong place
    field = np.zeros((len(bad_lat), len(lon)), dtype=np.float32)
    with pytest.raises(ValueError, match="do not hold exactly|outside|shifted relative to config"):
        W.regrid_to_config(bad_lat, lon, field)


def test_regrid_refuses_a_grid_that_is_too_coarse():
    lat, lon = _source_grid()
    coarse_lat = lat[::2]                         # 0.25 deg source -> 1 point per cell, not 2
    field = np.zeros((len(coarse_lat), len(lon)), dtype=np.float32)
    with pytest.raises(ValueError, match="do not hold exactly"):
        W.regrid_to_config(coarse_lat, lon, field)


def test_regrid_refuses_points_outside_the_target_grid():
    lat, lon = _source_grid()
    field = np.zeros((len(lat), len(lon)), dtype=np.float32)
    with pytest.raises(ValueError, match="outside"):
        W.regrid_to_config(lat + 10.0, lon, field)


def test_regrid_preserves_leading_axes():
    """A (T, lat, lon) stack must come back (T, 100, 240) -- days must not be collapsed."""
    lat, lon = _source_grid()
    field = np.zeros((5, len(lat), len(lon)), dtype=np.float32)
    assert W.regrid_to_config(lat, lon, field).shape == (5, len(config.LAT), len(config.LON))


def test_request_bounds_cover_the_outermost_cells_not_their_centres():
    b = W.request_bounds()
    assert b["minimum_latitude"] == pytest.approx(float(config.LAT[0]) - 0.125)
    assert b["maximum_latitude"] == pytest.approx(float(config.LAT[-1]) + 0.125)
    assert b["minimum_longitude"] == pytest.approx(float(config.LON[0]) - 0.125)
    assert b["maximum_longitude"] == pytest.approx(float(config.LON[-1]) + 0.125)


def test_months_cover_the_whole_daily_window():
    m = W.month_starts()
    assert str(m[0].date()) == "2025-06-01"
    assert str(m[-1].date()) == "2026-06-01", "the last month must contain the 2026-06-23 end date"
    assert len(m) == 13


def test_variables_match_the_frozen_contract_channels():
    """The contract names wind VELOCITY (wu, wv). Downloading stress instead would be silent drift."""
    assert W.VARIABLES == ["eastward_wind", "northward_wind"]
    doc = open("docs/phase2/tscast_data_model.md", encoding="utf-8").read()
    assert '"wu","wv"' in doc.replace(" ", ""), "channel contract changed -- re-read it"


# ── merging wind into the daily bundle as channels 6-7 ────────────────────────────────

def _fake_wind(dates, nlat=None, nlon=None):
    nlat = nlat or len(config.LAT)
    nlon = nlon or len(config.LON)
    d = np.asarray(dates, dtype="datetime64[D]")
    # value == day number, so a misalignment shows up as a wrong number, not a wrong shape
    day = d.astype("int64").astype(np.float32)
    return {"dates": d,
            "wu": np.broadcast_to(day[:, None, None], (len(d), nlat, nlon)).astype(np.float32),
            "wv": np.broadcast_to(-day[:, None, None], (len(d), nlat, nlon)).astype(np.float32)}


def test_wind_is_joined_by_date_not_by_position():
    from phase2.tscast_nio import daily_pipeline as P

    wind = _fake_wind(np.arange(np.datetime64("2025-06-01"), np.datetime64("2025-07-01")))
    # ask for a NON-contiguous subset in a different position than the wind array
    times = np.array(["2025-06-20", "2025-06-05", "2025-06-11"], dtype="datetime64[D]")
    out = P._wind_for(wind, times)
    assert out.shape == (3, len(config.LAT), len(config.LON), 2)
    want = times.astype("int64").astype(np.float32)
    assert np.allclose(out[:, 0, 0, 0], want), (
        "wind rows do not carry the day they are labelled with -- it was joined by position")
    assert np.allclose(out[:, 0, 0, 1], -want)


def test_wind_refuses_a_missing_day_rather_than_writing_nan():
    from phase2.tscast_nio import daily_pipeline as P

    wind = _fake_wind(np.arange(np.datetime64("2025-06-01"), np.datetime64("2025-06-10")))
    times = np.array(["2025-06-05", "2025-06-30"], dtype="datetime64[D]")
    with pytest.raises(ValueError, match="wind is missing"):
        P._wind_for(wind, times)


def test_wind_channels_are_appended_in_the_frozen_contract_order():
    from phase2.tscast_nio import daily_pipeline as P

    assert P.SURFACE_KEYS + P.WIND_KEYS == ["sst", "sss", "ssh", "u", "v", "wu", "wv"]
    assert len(P.WIND_UNITS) == len(P.WIND_KEYS)


def test_load_wind_refuses_a_bundle_on_a_different_grid(tmp_path):
    from phase2.tscast_nio import daily_pipeline as P

    p = tmp_path / "wrong_grid.npz"
    np.savez(p, dates=np.array(["20250601"], dtype="<U8"),
             wu=np.zeros((1, len(config.LAT), len(config.LON)), dtype=np.float32),
             wv=np.zeros((1, len(config.LAT), len(config.LON)), dtype=np.float32),
             lat=config.LAT + 0.125, lon=config.LON)     # the +0.125 offset of trap #5
    with pytest.raises(ValueError, match="different lat grid"):
        P.load_wind(str(p))


def test_load_wind_returns_none_when_absent(tmp_path):
    from phase2.tscast_nio import daily_pipeline as P

    assert P.load_wind(str(tmp_path / "nope.npz")) is None
