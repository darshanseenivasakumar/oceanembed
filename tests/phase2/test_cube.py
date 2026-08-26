"""F2a OceanCube -- tests.

The cube's reason to exist is that the sea floor becomes a REFUSAL rather than a NaN, so most of
these are bathymetry tests. `START_HERE` rule 7: could this array have been produced without real
data behind it? A cube that returns a number for 1000 m in the Persian Gulf has failed regardless
of what its shape says.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.cube import BelowSeafloorError, CubeShapeError, OceanCube

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SHAPE = (config.N_LAT, config.N_LON, config.N_DEPTHS)

#: [VERIFIED 2026-08-26] ocean, but the sea floor is at 30 m. The cell Phase 1 painted 1000 m
#: temperatures into.
GULF_LAT, GULF_LON, GULF_FLOOR_M = 26.0, 52.5, 30.0
#: Deep open water in the Bay of Bengal -- water at every level.
DEEP_LAT, DEEP_LON = 15.0, 88.0


def _synthetic_cube(all_water: bool = False) -> OceanCube:
    """A cube built from arrays, so the structural tests need no data bundle."""
    temp = np.full(SHAPE, 20.0)
    vm = np.ones(SHAPE, dtype=bool)
    land = np.zeros((config.N_LAT, config.N_LON), dtype=bool)
    if not all_water:
        land[0, 0] = True
        vm[0, 0, :] = False
        # one shelf cell with water only to 30 m (index 4)
        vm[5, 5, 5:] = False
    return OceanCube(date="2022-07-15", temperature=temp, valid_mask=vm, land_mask=land,
                     provenance={"produced_by": "test", "source": "synthetic"})


@pytest.fixture(scope="module")
def real_cube():
    if not os.path.exists(GRIDS):
        pytest.skip("grids.npz absent (gitignored) -- real-data cube tests skipped")
    return OceanCube.reconstruct("2022-07-15", source="satellite", with_uncertainty=False)


# ---------------------------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------------------------
def test_wrong_shape_is_refused_not_reshaped():
    with pytest.raises(CubeShapeError, match="expected"):
        OceanCube(date="x", temperature=np.zeros((10, 10, 10)),
                  valid_mask=np.ones(SHAPE, bool),
                  land_mask=np.zeros((config.N_LAT, config.N_LON), bool))


def test_arrays_are_handed_out_read_only():
    """The cube is a contract object shared between consumers; in-place writes must not be
    possible, or one consumer can corrupt it for the rest with nothing raising."""
    c = _synthetic_cube()
    with pytest.raises(ValueError):
        c.temperature[0, 0, 0] = 99.0


def test_depths_and_grid_come_from_config_not_from_the_cube():
    c = _synthetic_cube()
    assert list(c.coverage()["depths_m"]) == list(config.DEPTHS)
    sl = c.depth_slice(100)
    assert len(sl["lat"]) == config.N_LAT and len(sl["lon"]) == config.N_LON


# ---------------------------------------------------------------------------------------------
# bathymetry -- the reason this class exists
# ---------------------------------------------------------------------------------------------
def test_below_the_seafloor_raises_rather_than_returning_nan():
    c = _synthetic_cube()
    lat, lon = float(config.LAT[5]), float(config.LON[5])
    assert c.value_at(lat, lon, 30) == pytest.approx(20.0)      # water here
    with pytest.raises(BelowSeafloorError, match="sea floor"):
        c.value_at(lat, lon, 1000)                              # sea bed is at 30 m


def test_the_refusal_names_the_cell_and_its_actual_depth():
    """An error that says only 'invalid' sends someone hunting. It must say where and how deep."""
    c = _synthetic_cube()
    with pytest.raises(BelowSeafloorError) as e:
        c.value_at(float(config.LAT[5]), float(config.LON[5]), 500)
    msg = str(e.value)
    assert "30" in msg and "500" in msg


def test_land_is_refused_distinctly_from_deep_water():
    c = _synthetic_cube()
    with pytest.raises(BelowSeafloorError, match="is land"):
        c.value_at(float(config.LAT[0]), float(config.LON[0]), 0)


def test_profile_states_the_seafloor_instead_of_implying_it():
    c = _synthetic_cube()
    p = c.profile(float(config.LAT[5]), float(config.LON[5]))
    assert p["seafloor_depth_m"] == 30.0
    assert p["n_levels_with_water"] == 5
    assert p["below_seafloor"][5:].all() and not p["below_seafloor"][:5].any()
    assert np.isnan(p["values"][5:]).all()


def test_depth_slice_reports_coverage_so_a_map_cannot_imply_a_full_field():
    c = _synthetic_cube()
    shallow, deep = c.depth_slice(0), c.depth_slice(1000)
    assert shallow["coverage_fraction"] > deep["coverage_fraction"]
    assert deep["n_cells_with_water"] < deep["n_ocean_cells"]


def test_a_cube_cannot_be_built_without_bathymetry(monkeypatch, tmp_path):
    """An all-True fallback would let 1000 m values appear in 20 m water. It must refuse."""
    from phase2.cube import ocean_cube as oc
    monkeypatch.setattr(config, "DATA_PROCESSED", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Persian Gulf|bathymetry"):
        oc._valid_mask_or_all_true()


# ---------------------------------------------------------------------------------------------
# slicing
# ---------------------------------------------------------------------------------------------
def test_depth_snapping_is_reported_not_silent():
    """config.DEPTHS is irregular, so a request lands between levels and must be reported."""
    c = _synthetic_cube()
    sl = c.depth_slice(260)                      # between 200 and 300, nearer 300
    assert sl["depth_m"] == 300.0
    assert sl["depth_requested_m"] == 260.0
    assert sl["snapped_by_m"] == 40.0
    exact = c.depth_slice(100)
    assert exact["snapped_by_m"] == 0.0


def test_an_exact_tie_snaps_shallower_and_says_by_how_much():
    """400 m is exactly 100 m from both 300 and 500. The tie must resolve deterministically,
    and shallower is the conservative direction -- more cells have water there."""
    c = _synthetic_cube()
    sl = c.depth_slice(400)
    assert sl["depth_m"] == 300.0, "ties must resolve to the SHALLOWER level"
    assert sl["snapped_by_m"] == 100.0


def test_sections_along_lat_and_lon_have_the_right_orientation():
    c = _synthetic_cube()
    by_lat = c.section(lat=15.0)
    by_lon = c.section(lon=88.0)
    assert by_lat["values"].shape == (config.N_LON, config.N_DEPTHS)
    assert by_lon["values"].shape == (config.N_LAT, config.N_DEPTHS)
    assert by_lat["dims"] == ("lon", "depth") and by_lon["dims"] == ("lat", "depth")


def test_section_requires_exactly_one_axis():
    c = _synthetic_cube()
    for kwargs in ({}, {"lat": 15.0, "lon": 88.0}):
        with pytest.raises(ValueError, match="exactly one"):
            c.section(**kwargs)


def test_outside_the_domain_is_refused():
    c = _synthetic_cube()
    with pytest.raises(ValueError, match="outside the domain"):
        c.nearest_cell(-40.0, 88.0)


def test_missing_field_says_why_it_is_missing():
    c = _synthetic_cube()
    with pytest.raises(ValueError, match="with_uncertainty=False|no climatology"):
        c.depth_slice(100, what="uncertainty")
    with pytest.raises(ValueError, match="unknown field"):
        c.depth_slice(100, what="salinity")


# ---------------------------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------------------------
def test_every_extraction_carries_provenance():
    c = _synthetic_cube()
    for rec in (c.depth_slice(100), c.section(lat=15.0), c.profile(15.0, 88.0)):
        p = rec["provenance"]
        assert p["produced_by"] == "test"
        assert "extraction" in p
        assert p["extraction"]["kind"] in ("depth_slice", "section", "profile")


# ---------------------------------------------------------------------------------------------
# real data
# ---------------------------------------------------------------------------------------------
def test_real_cube_refuses_1000m_in_the_persian_gulf(real_cube):
    """THE regression test for this feature. [VERIFIED] 26.00N 52.50E is ocean with water only
    to 30 m. Phase 1 painted 1000 m temperatures there."""
    assert real_cube.seafloor_depth_m(GULF_LAT, GULF_LON) == GULF_FLOOR_M
    assert real_cube.value_at(GULF_LAT, GULF_LON, 30) == pytest.approx(
        real_cube.value_at(GULF_LAT, GULF_LON, 30))
    with pytest.raises(BelowSeafloorError):
        real_cube.value_at(GULF_LAT, GULF_LON, 1000)


def test_real_cube_returns_a_plausible_deep_profile(real_cube):
    p = real_cube.profile(DEEP_LAT, DEEP_LON)
    v = p["values"]
    assert p["n_levels_with_water"] == config.N_DEPTHS, "open Bay of Bengal should reach 1000 m"
    assert np.isfinite(v).all()
    assert 20.0 < v[0] < 33.0, f"surface {v[0]} is not a tropical SST"
    assert v[-1] < v[0] - 10.0, "1000 m must be far colder than the surface"
    assert np.all(np.diff(v) < 2.0), "temperature must not jump upward with depth"


def test_real_cube_coverage_matches_the_known_bathymetry(real_cube):
    """[VERIFIED] of cells both masks call ocean, 100% have water at 0 m and 75.8% at 1000 m."""
    cov = real_cube.coverage()
    assert cov["coverage_fraction"][0] == pytest.approx(1.0, abs=1e-6)
    assert cov["coverage_fraction"][-1] == pytest.approx(0.758, abs=0.015)
    assert cov["coverage_fraction"] == sorted(cov["coverage_fraction"], reverse=True), \
        "coverage cannot increase with depth"


def test_the_coastline_disagreement_is_reported_not_absorbed(real_cube):
    """[VERIFIED] the satellite and GLORYS land masks disagree on 464 cells; 179 are ocean in the
    satellite product ONLY, and those have no water at any depth in GLORYS bathymetry.

    Unit B's F1 emits the same 464 as COASTLINE_DISAGREEMENT, so this is a known, independently
    measured disagreement rather than a defect here. A cube that silently absorbed them would
    show 98.47% surface coverage with no explanation, which reads as a bug.
    """
    dis = real_cube.coastline_disagreement()
    assert dis["n_cells"] == 179, f"expected the 179 satellite-only ocean cells, got {dis['n_cells']}"
    assert dis["source_of_land_mask"] == "satellite"
    assert "glorys" in dis["source_of_bathymetry"]

    cov = real_cube.coverage()
    assert cov["coastline_disagreement_cells"] == 179
    # the raw fraction still shows the dent -- nothing is hidden, the two are only separated
    assert cov["coverage_fraction_raw"][0] == pytest.approx(0.9847, abs=0.002)


def test_a_glorys_cube_has_no_coastline_disagreement():
    """Bathymetry is derived from GLORYS, so a GLORYS-sourced cube must be self-consistent.
    If this ever fails, the two files have drifted apart."""
    if not os.path.exists(GRIDS):
        pytest.skip("grids.npz absent")
    c = OceanCube.reconstruct("2022-07-15", source="glorys", with_uncertainty=False)
    assert c.coastline_disagreement()["n_cells"] == 0
    assert c.coverage()["coverage_fraction"][0] == pytest.approx(1.0, abs=1e-6)
    assert c.coverage()["coverage_fraction_raw"][0] == pytest.approx(1.0, abs=1e-6)


def test_real_cube_records_what_produced_it(real_cube):
    p = real_cube.provenance
    assert p["wraps"] == "oceanembed.inference.predict.reconstruct_grid"
    assert p["source"] in ("satellite", "glorys")
    assert p["units"]["temperature"] == "degC"
    assert p["grid"]["depths_m"] == list(config.DEPTHS)
