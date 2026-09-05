"""One depth level as clickable cells, and the click that resolves back. Owner: Unit A (Arjhun).

The failure this file exists to catch is not a crash. It is a click that returns a real profile
from the WRONG cell -- transposed indices, or a C/F-order mismatch -- which produces a beautiful,
plausible chart for a point the reader did not choose. No shape check sees it, so the index tests
below all use a NON-SQUARE grid: with n_lat == n_lon a transposition is invisible.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.derived import mapframe as MF

NLAT, NLON = 4, 7                     # deliberately not square, and not equal to each other


def grid():
    """A 4x7 toy basin: land in the first row, a seafloor hole, water elsewhere."""
    lat = np.array([5.0, 5.25, 5.5, 5.75])
    lon = np.array([45.0, 45.25, 45.5, 45.75, 46.0, 46.25, 46.5])
    v = np.arange(NLAT * NLON, dtype="float64").reshape(NLAT, NLON)
    land = np.zeros((NLAT, NLON), bool)
    land[0, :] = True                 # a whole row of land
    v[land] = np.nan                  # land carries NaN too -- that is the trap
    v[2, 3] = np.nan                  # ocean, but below the seafloor at this level
    return v, land, lat, lon


# ==================================================== classification

def test_every_cell_appears_exactly_once_land_included():
    """A click anywhere must land on a row that can explain itself. A frame containing only water
    cells would leave two thirds of this basin unclickable and silent."""
    v, land, lat, lon = grid()
    f = MF.level_frame(v, land, lat, lon)
    assert len(f["lat"]) == NLAT * NLON == 28
    assert len(set(zip(f["i"].tolist(), f["j"].tolist()))) == 28


def test_land_is_classified_as_land_even_though_its_value_is_also_nan():
    """ORDER OF THE TWO CHECKS. Asking "is the value finite" before "is it land" would label the
    entire coastline `below the seafloor`, which is a claim about bathymetry the data never made.
    """
    v, land, lat, lon = grid()
    f = MF.level_frame(v, land, lat, lon)
    kind = f["kind"].reshape(NLAT, NLON)
    assert (kind[0, :] == MF.LAND).all()
    assert not np.isfinite(v[0, :]).any(), "the fixture must have NaN on land or this proves nothing"


def test_an_ocean_cell_with_no_value_is_seafloor_not_land():
    v, land, lat, lon = grid()
    f = MF.level_frame(v, land, lat, lon)
    kind = f["kind"].reshape(NLAT, NLON)
    assert kind[2, 3] == MF.SEAFLOOR
    assert kind[2, 2] == MF.WATER


def test_the_three_kinds_are_three_distinct_strings():
    assert len(set(MF.KINDS)) == 3
    assert set(MF.KIND_NOTE) == set(MF.KINDS)
    assert MF.KIND_NOTE[MF.LAND] and MF.KIND_NOTE[MF.SEAFLOOR], "both blanks need an explanation"


def test_counts_names_every_kind_including_the_ones_with_zero_cells():
    """A missing key reads as a kind nobody counted."""
    v, land, lat, lon = grid()
    c = MF.counts(MF.level_frame(v, land, lat, lon))
    assert set(c) == set(MF.KINDS)
    assert c[MF.LAND] == NLON and c[MF.SEAFLOOR] == 1 and c[MF.WATER] == 28 - NLON - 1
    assert sum(c.values()) == 28

    all_water = MF.counts(MF.level_frame(np.ones((2, 3)), np.zeros((2, 3), bool),
                                         [0.0, 1.0], [0.0, 1.0, 2.0]))
    assert all_water == {MF.WATER: 6, MF.SEAFLOOR: 0, MF.LAND: 0}


# ==================================================== the index -> position mapping

def test_index_i_j_resolves_to_the_right_lat_lon_on_a_non_square_grid():
    """THE transposition test. With a square grid, swapping i and j changes nothing visible."""
    v, land, lat, lon = grid()
    f = MF.level_frame(v, land, lat, lon)
    for k in range(len(f["lat"])):
        i, j = int(f["i"][k]), int(f["j"][k])
        assert f["lat"][k] == lat[i], f"row {k}: lat came from the wrong index"
        assert f["lon"][k] == lon[j], f"row {k}: lon came from the wrong index"


def test_the_value_at_a_row_is_the_value_at_that_cell_of_the_original_array():
    """The other half of the same trap: right coordinates, wrong number."""
    v, land, lat, lon = grid()
    f = MF.level_frame(v, land, lat, lon, extra={"sigma": v * 10.0})
    for k in range(len(f["value"])):
        i, j = int(f["i"][k]), int(f["j"][k])
        assert np.isnan(f["value"][k]) == np.isnan(v[i, j])
        if np.isfinite(v[i, j]):
            assert f["value"][k] == v[i, j]
            assert f["sigma"][k] == v[i, j] * 10.0


def test_ravel_order_matches_the_i_j_columns_for_the_real_basin_shape():
    """The toy grid is 4x7; the real one is 100x240 and both indices are plausible array sizes.
    Run the same check at the shipped shape so an off-by-one in `repeat`/`tile` cannot hide."""
    n_lat, n_lon = base.N_LAT, base.N_LON
    v = np.arange(n_lat * n_lon, dtype="float64").reshape(n_lat, n_lon)
    f = MF.level_frame(v, np.zeros((n_lat, n_lon), bool), base.LAT, base.LON)
    assert (f["value"] == np.arange(n_lat * n_lon)).all()
    for k in (0, 1, n_lon - 1, n_lon, n_lon + 1, n_lat * n_lon - 1):
        assert f["value"][k] == v[int(f["i"][k]), int(f["j"][k])]


# ==================================================== guards

@pytest.mark.parametrize("bad", [np.zeros((3, 3)), np.zeros((4, 6))])
def test_a_mismatched_land_mask_raises_rather_than_broadcasting(bad):
    v, _, lat, lon = grid()
    with pytest.raises(ValueError):
        MF.level_frame(v, bad.astype(bool), lat, lon)


def test_a_mismatched_extra_array_raises():
    v, land, lat, lon = grid()
    with pytest.raises(ValueError, match="sigma"):
        MF.level_frame(v, land, lat, lon, extra={"sigma": np.zeros((2, 2))})


def test_values_that_do_not_match_the_coordinate_lengths_raise():
    v, land, _, lon = grid()
    with pytest.raises(ValueError):
        MF.level_frame(v, land, [0.0, 1.0], lon)


# ==================================================== depth snapping

@pytest.mark.parametrize("asked,expect", [(0, 0), (4, 5), (100, 100), (137, 125), (163, 150),
                                          (999, 1000), (5000, 1000)])
def test_nearest_level_snaps_to_a_real_sampled_depth(asked, expect):
    """A page offering 137 m must show 125 m, not 137 -- silently snapping and then labelling the
    chart with the number the user typed is a caption that does not match its own data."""
    k = MF.nearest_level(base.DEPTHS, asked)
    assert base.DEPTHS[k] == expect


# ==================================================== against the real model

def _have_model():
    return (os.path.exists(base.art("tscast_stage1.pt"))
            and os.path.isdir(os.path.join("data", "processed", "daily_sat", "v001")))


@pytest.mark.skipif(not _have_model(), reason="checkpoint or satellite bundle not on this machine")
def test_a_clicked_cell_returns_that_cells_profile_and_the_point_api_agrees():
    """The failure worth catching: a click that returns a real profile from the WRONG cell.

    Three things must agree -- the map's own array, the frame row the click resolves to, and
    `reconstruct(lat, lon, date)`, which is the path every other page uses. The cells chosen are
    deliberately asymmetric (i != j) so a transposition cannot pass.
    """
    from phase2.tscast_nio import field_cache as FC

    date = "2026-05-15"
    f = FC.field_for(date)
    temp = np.asarray(f["temperature"])
    k = MF.nearest_level(base.DEPTHS, 100)
    frame = MF.level_frame(temp[:, :, k], f["land_mask"], base.LAT, base.LON)

    water = np.argwhere((np.asarray(frame["kind"]).reshape(temp.shape[:2]) == MF.WATER))
    asym = [(i, j) for i, j in water if i != j]
    assert len(asym) > 50, "need asymmetric ocean cells or the transposition test is vacuous"

    rng = np.random.default_rng(0)
    for i, j in [asym[n] for n in rng.choice(len(asym), 4, replace=False)]:
        row = int(i) * base.N_LON + int(j)
        assert int(frame["i"][row]) == i and int(frame["j"][row]) == j
        lat, lon = float(frame["lat"][row]), float(frame["lon"][row])
        assert lat == base.LAT[i] and lon == base.LON[j]
        assert frame["value"][row] == temp[i, j, k]

        point = FC.reconstruct_point(lat, lon, date)
        got = np.asarray(point["temperature"], dtype="float64")
        want = temp[i, j, :]
        both = np.isfinite(got) & np.isfinite(want)
        assert both.sum() >= 10, f"cell ({i},{j}) came back almost empty"
        assert np.allclose(got[both], want[both], atol=1e-4), (
            f"cell ({i},{j}) at {lat}N {lon}E: the map and the point API disagree")


@pytest.mark.skipif(not _have_model(), reason="checkpoint or satellite bundle not on this machine")
def test_the_classification_accounts_for_every_cell_and_matches_the_models_ocean_count():
    """water + seafloor must equal the ocean cells `predict_field` actually reconstructs -- 11,832,
    the same number recorded in artifacts/export_timing.json. If these ever diverge the map is
    drawing a different basin from the one the model ran on."""
    from phase2.tscast_nio import field_cache as FC

    f = FC.field_for("2026-05-15")
    temp = np.asarray(f["temperature"])
    c = MF.counts(MF.level_frame(temp[:, :, 0], f["land_mask"], base.LAT, base.LON))
    assert sum(c.values()) == base.N_LAT * base.N_LON == 24000
    assert c[MF.WATER] + c[MF.SEAFLOOR] == int((~np.asarray(f["land_mask"], bool)).sum())


def test_every_field_the_map_pages_encode_is_one_the_frame_actually_produces():
    """A page that encodes a column `level_frame` does not return draws an EMPTY chart -- Vega-Lite
    resolves the missing field to null for every row and renders nothing, with no error anywhere.

    So the contract between the library and its callers is checked structurally, by reading what
    the pages ask Altair for. This is the check that would have caught the rename if `add_edges`
    had produced `x0/x1` while the pages still asked for `lon0/lon1`.
    """
    import re

    pages = ["app/phase2/clickmap_page.py", "app/phase2/uncertainty_page.py"]
    frame = MF.add_edges(MF.level_frame(
        np.zeros((base.N_LAT, base.N_LON)), np.zeros((base.N_LAT, base.N_LON), bool),
        base.LAT, base.LON, extra={"sigma": np.zeros((base.N_LAT, base.N_LON))}))

    checked = 0
    for rel in pages:
        path = os.path.join(os.path.dirname(__file__), "..", "..", rel)
        if not os.path.exists(path):
            continue                       # that feature is not on this branch
        checked += 1
        src = open(path, encoding="utf-8").read()
        # field references in Altair shorthand: "name:Q", "name:N", "name:O"
        used = set(re.findall(r'"([a-z_0-9]+):[QNOT]"', src))
        # a page may legitimately encode columns it adds itself, so only the ones the frame is
        # expected to supply are required
        supplied = {"lat", "lon", "lat0", "lat1", "lon0", "lon1", "value", "sigma", "kind", "i", "j"}
        missing = (used & supplied) - set(frame)
        assert not missing, f"{rel} encodes {sorted(missing)}, which level_frame does not produce"
    assert checked >= 1, "no map page found to check"
