"""Argo pressure is decibars; config.DEPTHS is metres (audit finding #8).

The first block pins the conversion to UNESCO's own check value so the constants cannot drift.
The second shows the bug is MEASURABLE on a realistic thermocline, and the third runs the real
`_profiles_to_rows` on a synthetic argopy-shaped dataset and checks it now samples at the depth
it labels -- with a control proving the pre-fix behaviour is different.
"""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from oceanembed import config
from oceanembed.data import download_argo
from phase2.data.argo_depth import depth_from_pressure, pressure_read_as_depth_error_m


# ------------------------------------------------------------------ the formula


def test_unesco_1983_check_value():
    """Fofonoff & Millard (1983), Technical Paper 44: 10000 dbar at 30 N is 9712.653 m."""
    assert depth_from_pressure(10000.0, 30.0) == pytest.approx(9712.653, abs=1e-3)


def test_zero_pressure_is_the_surface_and_depth_is_monotone():
    p = np.linspace(0, 2000, 401)
    for lat in (0.0, 15.0, 45.0, 89.0):
        z = depth_from_pressure(p, lat)
        assert z[0] == 0.0
        assert np.all(np.diff(z) > 0)
        assert np.all(z[1:] < p[1:]), "a decibar is always slightly MORE than a metre of water"


def test_negative_pressure_is_refused_not_extrapolated():
    assert np.isnan(depth_from_pressure(-5.0, 10.0))


def test_the_error_on_the_shipped_grid_at_the_basin_middle():
    """Pinned so the size of the bug is written down where it can be quoted."""
    err = pressure_read_as_depth_error_m(config.DEPTHS, 15.0)
    by_level = dict(zip(config.DEPTHS, np.round(err, 2)))
    assert by_level[0] == 0.0
    assert by_level[100] == pytest.approx(0.61, abs=0.01)
    assert by_level[200] == pytest.approx(1.27, abs=0.01)
    assert by_level[500] == pytest.approx(3.52, abs=0.01)
    assert by_level[1000] == pytest.approx(8.23, abs=0.01)
    assert np.all(err >= 0), "pressure read as depth always samples the float too shallow"


# ------------------------------------------------------------------ it is measurable


def test_interpolating_on_pressure_misreads_a_thermocline():
    """A 0.1 degC/m gradient -- ordinary for this basin at 100-200 m -- turned into a tenth of a
    degree charged to the model at 100 m, and more below. The size of that misread is the whole
    reason this is a finding and not a nit."""
    lat = 15.0
    p = np.arange(0.0, 1201.0, 2.0)                    # dbar, a 2-dbar float
    z = depth_from_pressure(p, lat)
    t = 30.0 - 0.1 * z                                  # linear in DEPTH, so truth is known
    on_pressure = np.interp(config.DEPTHS, p, t)        # the bug
    on_depth = np.interp(config.DEPTHS, z, t)           # the fix
    truth = 30.0 - 0.1 * np.asarray(config.DEPTHS, float)
    assert np.allclose(on_depth, truth, atol=1e-6)
    misread = on_pressure - truth
    assert misread[config.DEPTHS.index(100)] == pytest.approx(0.061, abs=0.003)
    assert misread[config.DEPTHS.index(1000)] == pytest.approx(0.823, abs=0.01)
    assert np.all(misread[1:] > 0), "reading too shallow always reads too WARM in a thermocline"


# ------------------------------------------------------------------ the real code path


def _argopy_like(p_dbar, temp, lat, lon, when="2025-08-01", platform=1, cycle=1):
    """The N_POINTS long table argopy's DataFetcher returns, with good QC everywhere."""
    n = len(p_dbar)
    return xr.Dataset(
        {"PRES": ("N_POINTS", np.asarray(p_dbar, float)),
         "TEMP": ("N_POINTS", np.asarray(temp, float)),
         "LATITUDE": ("N_POINTS", np.full(n, lat)),
         "LONGITUDE": ("N_POINTS", np.full(n, lon)),
         "TIME": ("N_POINTS", np.full(n, np.datetime64(when))),
         "PLATFORM_NUMBER": ("N_POINTS", np.full(n, platform)),
         "CYCLE_NUMBER": ("N_POINTS", np.full(n, cycle)),
         "TEMP_QC": ("N_POINTS", np.ones(n, int)),
         "PRES_QC": ("N_POINTS", np.ones(n, int)),
         "POSITION_QC": ("N_POINTS", np.ones(n, int))},
        coords={"N_POINTS": np.arange(n)})


def test_profiles_to_rows_samples_at_the_depth_it_labels():
    lat = 15.0
    p = np.arange(0.0, 1201.0, 2.0)
    z = depth_from_pressure(p, lat)
    t = 30.0 - 0.1 * z
    rows = download_argo._profiles_to_rows(_argopy_like(p, t, lat, 70.0))
    got = {di: v for (_, _, _, di, v) in rows}
    for di, d in enumerate(config.DEPTHS):
        assert got[di] == pytest.approx(30.0 - 0.1 * d, abs=1e-4), f"level {d} m is mis-sampled"


def test_a_float_that_stops_short_of_1000_m_in_depth_gets_no_1000_m_value():
    """1003 dbar is only ~995 m. The old code interpolated a 1000 m value there because it read
    the pressure as 1003 metres. Now the level is refused, as it should be."""
    lat = 15.0
    p = np.arange(0.0, 1004.0, 2.0)                    # tops out at 1002 dbar ~ 994 m
    rows = download_argo._profiles_to_rows(_argopy_like(p, 30.0 - 0.01 * p, lat, 70.0))
    levels = {di for (_, _, _, di, _) in rows}
    assert config.DEPTHS.index(1000) not in levels
    assert config.DEPTHS.index(700) in levels


def test_the_pre_fix_behaviour_is_actually_different():
    """The control: the same synthetic profile interpolated the OLD way disagrees with what
    `_profiles_to_rows` now returns. Without this, the tests above could pass against code that
    silently still read pressure as depth."""
    lat = 15.0
    p = np.arange(0.0, 1201.0, 2.0)
    z = depth_from_pressure(p, lat)
    t = 30.0 - 0.1 * z
    old = np.interp(config.DEPTHS, p, t)
    new = {di: v for (_, _, _, di, v) in
           download_argo._profiles_to_rows(_argopy_like(p, t, lat, 70.0))}
    diff = [abs(old[di] - new[di]) for di in new]
    assert max(diff) > 0.5, "the fix changed nothing; is pressure still being read as depth?"


def test_salinity_is_converted_on_the_same_axis():
    lat = 15.0
    p = np.arange(0.0, 1201.0, 2.0)
    z = depth_from_pressure(p, lat)
    ds = _argopy_like(p, 30.0 - 0.1 * z, lat, 70.0)
    ds["PSAL"] = ("N_POINTS", 35.0 + 0.001 * z)
    ds["PSAL_QC"] = ("N_POINTS", np.ones(len(p), int))
    rows = download_argo._profiles_to_rows(ds, with_salinity=True)
    got = {di: s for (_, _, _, di, _, s) in rows}
    for di, d in enumerate(config.DEPTHS):
        assert got[di] == pytest.approx(35.0 + 0.001 * d, abs=1e-5)
