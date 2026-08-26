"""F2b volume layer -- tests.

The renderer is not tested here (a browser is not a unit test). What IS tested is everything that
would make the picture WRONG rather than merely absent: the depth sign, the coordinate pairing,
the sea-floor masking, and that the 2-D fallback stays reachable with no renderer installed.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.cube import OceanCube, volume

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SHAPE = (config.N_LAT, config.N_LON, config.N_DEPTHS)


def _cube() -> OceanCube:
    """A cube with a known shelf, so masking is checkable without the data bundle."""
    temp = np.zeros(SHAPE)
    # temperature = depth index, so a value identifies its own level unambiguously
    temp[:] = np.arange(config.N_DEPTHS, dtype="float64")
    vm = np.ones(SHAPE, dtype=bool)
    land = np.zeros((config.N_LAT, config.N_LON), dtype=bool)
    land[0, 0] = True
    vm[0, 0, :] = False
    vm[6, 6, 5:] = False                      # a shelf cell: water only to index 4
    return OceanCube(date="2022-07-15", temperature=temp, valid_mask=vm, land_mask=land,
                     provenance={"produced_by": "test", "source": "synthetic"})


# ---------------------------------------------------------------------------------------------
# the two things that make ocean data awkward in 3-D
# ---------------------------------------------------------------------------------------------
def test_depth_is_emitted_negative_so_the_ocean_is_not_upside_down():
    """Plotly's z increases upward. Emitting +depth would put the sea floor ABOVE the surface."""
    v = volume.to_volume_arrays(_cube(), stride=5)
    assert v["z"].max() == pytest.approx(0.0), "the surface must sit at z = 0"
    assert v["z"].min() == pytest.approx(-float(config.DEPTHS[-1]))
    assert (v["z"] <= 0).all(), "no part of the ocean may be above the surface"


def test_aspect_ratio_keeps_the_basin_wide_rather_than_a_needle():
    a = volume.aspect_ratio()
    lat = np.asarray(config.LAT); lon = np.asarray(config.LON)
    assert a["y"] == pytest.approx((lat[-1] - lat[0]) / (lon[-1] - lon[0]), rel=1e-6)
    assert a["x"] > a["y"] > a["z"], "longitude widest, then latitude, depth shallowest"


def test_vertical_exaggeration_scales_only_the_depth_axis():
    base, stretched = volume.aspect_ratio(1.0), volume.aspect_ratio(3.0)
    assert stretched["z"] == pytest.approx(3.0 * base["z"])
    assert stretched["x"] == base["x"] and stretched["y"] == base["y"]


# ---------------------------------------------------------------------------------------------
# coordinates must pair with their values
# ---------------------------------------------------------------------------------------------
def test_every_value_lands_on_its_own_coordinate():
    """The fixture sets temperature == depth index, so a mismatch between the flattened value
    array and the flattened depth array is detectable rather than invisible.

    This is the meshgrid indexing='ij' guarantee. With the default 'xy' the lat and lon axes
    swap and every point moves, while the shapes stay valid -- correct array, wrong data.
    """
    v = volume.to_volume_arrays(_cube(), stride=7)
    ok = np.isfinite(v["value"])
    depth_from_z = -v["z"][ok]
    expected = np.asarray(config.DEPTHS, dtype="float64")[v["value"][ok].astype(int)]
    assert np.allclose(depth_from_z, expected), "values are not paired with their own depths"


def test_coordinates_stay_inside_the_domain():
    v = volume.to_volume_arrays(_cube(), stride=4)
    assert v["x"].min() >= float(config.LON[0]) and v["x"].max() <= float(config.LON[-1])
    assert v["y"].min() >= float(config.LAT[0]) and v["y"].max() <= float(config.LAT[-1])


# ---------------------------------------------------------------------------------------------
# the sea floor
# ---------------------------------------------------------------------------------------------
def test_below_the_seafloor_is_nan_and_counted():
    """Gaps in the render must be the sea floor, and the count must be reportable so a caption
    can say so instead of leaving a reader to assume data is missing."""
    v = volume.to_volume_arrays(_cube(), stride=1)
    assert v["n_below_seafloor"] > 0
    assert v["n_with_water"] + v["n_below_seafloor"] == v["n_points"]

    # the land cell contributes 15 empty points, the shelf cell 10
    assert v["n_below_seafloor"] >= config.N_DEPTHS + (config.N_DEPTHS - 5)


def test_land_contributes_no_finite_value():
    v = volume.to_volume_arrays(_cube(), stride=1)
    on_land = (v["x"] == float(config.LON[0])) & (v["y"] == float(config.LAT[0]))
    assert on_land.any()
    assert not np.isfinite(v["value"][on_land]).any()


# ---------------------------------------------------------------------------------------------
# size, so a browser is not handed 360,000 points
# ---------------------------------------------------------------------------------------------
def test_stride_reduces_the_point_count_but_never_the_depth_levels():
    fine, coarse = volume.to_volume_arrays(_cube(), stride=1), volume.to_volume_arrays(_cube(), stride=4)
    assert coarse["n_points"] < fine["n_points"] / 10
    assert fine["shape"][2] == coarse["shape"][2] == config.N_DEPTHS, \
        "depth must never be strided -- 15 levels is already coarse and the thermocline is the point"


def test_the_full_grid_is_flagged_over_budget():
    """stride=1 is 360,000 points. The page must be told, not left to freeze the browser."""
    v = volume.to_volume_arrays(_cube(), stride=1)
    assert v["n_points"] == config.N_LAT * config.N_LON * config.N_DEPTHS
    assert v["over_budget"] is True
    assert volume.to_volume_arrays(_cube(), stride=volume.DEFAULT_STRIDE)["over_budget"] is False


def test_stride_must_be_positive():
    with pytest.raises(ValueError, match="stride"):
        volume.to_volume_arrays(_cube(), stride=0)


# ---------------------------------------------------------------------------------------------
# isosurface levels
# ---------------------------------------------------------------------------------------------
def test_isosurface_levels_use_percentiles_not_extremes():
    """One extreme cell must not push every shell into a corner of the range."""
    c = _cube()
    v = volume.to_volume_arrays(c, stride=3)
    levels = volume.isosurface_levels(v, n=4)
    assert len(levels) == 4 and levels == sorted(levels)
    lo, hi = v["value_range"]
    assert levels[0] > lo - 1e-9 and levels[-1] < hi + 1e-9


def test_isosurface_levels_on_an_empty_field_return_nothing_rather_than_raising():
    c = _cube()
    empty = OceanCube(date=c.date, temperature=np.full(SHAPE, np.nan),
                      valid_mask=np.zeros(SHAPE, bool), land_mask=c.land_mask,
                      provenance={"produced_by": "test"})
    v = volume.to_volume_arrays(empty, stride=5)
    assert volume.isosurface_levels(v) == []


# ---------------------------------------------------------------------------------------------
# graceful degradation -- the actual F2b requirement
# ---------------------------------------------------------------------------------------------
def test_the_volume_layer_imports_no_plotting_library():
    """`phase2.cube.volume` must be usable with no renderer installed, or the fallback path
    cannot be trusted to exist when plotly is the thing that is missing."""
    import inspect
    src = inspect.getsource(volume)
    for banned in ("import plotly", "import matplotlib", "import altair", "import streamlit"):
        assert banned not in src, f"volume.py must not {banned}"


def test_the_two_dimensional_fallback_needs_only_the_cube():
    """The fallback renders a depth_slice. If that ever needed the 3-D path, a plotly failure
    would take the whole page down -- which is the situation F2b exists to avoid."""
    sl = _cube().depth_slice(100)
    assert sl["values"].shape == (config.N_LAT, config.N_LON)
    assert np.isfinite(sl["coverage_fraction"])


def test_uncertainty_and_anomaly_are_refused_when_absent_rather_than_drawn_as_zero():
    with pytest.raises(ValueError, match="with_uncertainty=False|no climatology"):
        volume.to_volume_arrays(_cube(), what="uncertainty")


@pytest.mark.skipif(not os.path.exists(GRIDS), reason="grids.npz absent (gitignored)")
def test_a_real_volume_is_mostly_sea_floor_and_land():
    """[VERIFIED] on the real grid roughly half the domain is land and a quarter of the ocean
    does not reach 1000 m, so a majority of sampled points legitimately hold no water."""
    cube = OceanCube.reconstruct("2022-07-15", source="satellite", with_uncertainty=False)
    v = volume.to_volume_arrays(cube)
    assert v["n_with_water"] > 5000, "a real basin must render substantial water"
    assert v["n_below_seafloor"] > v["n_with_water"], "land + shelf should dominate the box"
    lo, hi = v["value_range"]
    assert 0.0 < lo < 15.0 and 20.0 < hi < 36.0, f"implausible temperature range {lo}..{hi}"
