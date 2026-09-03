"""Tests for F1 — the multi-source collocation engine.

Contract tests AND scientific sanity tests. Phase 1's recurring bug was "correct arrays,
plausible values, wrong data" — five separate times, and shape tests caught none of them.
So several tests below assert PHYSICS and CROSS-SOURCE CONSISTENCY, not just structure.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import pytest

from oceanembed import config
from phase2.data.collocation import (
    CollocationEngine, _haversine_km, TEMPORAL_HIGH_D, TEMPORAL_MED_D, SPATIAL_MAX_KM,
)

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(config.DATA_PROCESSED, "grids.npz")),
    reason="run scripts/prepare_dataset.py --real first",
)

OCEAN = (15.0, 65.0)      # open Arabian Sea, deep
LAND = (15.0, 75.0)       # inland India


@pytest.fixture(scope="module")
def engine():
    return CollocationEngine()


@pytest.fixture(scope="module")
def date(engine):
    g = engine._npz("grids.npz")
    return str(pd.Timestamp(g["times"][-1]).date())


# ── contract ────────────────────────────────────────────────────────────────
def test_record_has_the_full_contract(engine, date):
    r = engine.collocate(*OCEAN, date)
    for k in ("requested", "matched", "offsets", "sources", "quality", "flags", "provenance"):
        assert hasattr(r, k), k
    for k in ("spatial_km", "temporal_days", "spatial_method"):
        assert k in r.offsets
    for k in ("grid_i", "grid_j", "time_index", "cell_id"):
        assert k in r.matched
    assert set(r.sources) >= {"glorys", "satellite", "subsurface", "argo"}


def test_provenance_records_where_numbers_came_from(engine, date):
    p = engine.collocate(*OCEAN, date).provenance
    assert p["grid"] == f"{config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}"
    assert p["depths_m"] == list(config.DEPTHS)
    assert "grids.npz" in p["files"]
    assert p["tolerance_days"] == engine.tolerance_days


def test_requested_values_are_preserved_verbatim(engine, date):
    """The engine must never quietly rewrite what the caller asked for."""
    r = engine.collocate(15.13, 65.07, date)
    assert r.requested["latitude"] == 15.13
    assert r.requested["longitude"] == 65.07
    assert r.matched["latitude"] != 15.13      # matched is the grid cell, kept separate


def test_profiles_have_one_value_per_depth(engine, date):
    r = engine.collocate(*OCEAN, date)
    assert len(r.sources["glorys"]["temperature_profile"]) == config.N_DEPTHS
    assert len(r.sources["subsurface"]["salinity_profile"]) == config.N_DEPTHS


# ── absence must be None, never zero ────────────────────────────────────────
def test_missing_data_is_none_not_zero(engine, date):
    """A NaN must surface as None. Returning 0.0 would be a silent fabrication —
    0 degC is a physically meaningful temperature."""
    r = engine.collocate(*OCEAN, date)
    prof = r.sources["glorys"]["temperature_profile"]
    assert all(v is None or isinstance(v, float) for v in prof)
    assert not any(v == 0.0 for v in prof if v is not None), "0.0 in an Arabian Sea profile is suspicious"


def test_land_is_rejected_and_flagged(engine, date):
    r = engine.collocate(*LAND, date)
    assert "LAND_IN_GLORYS" in r.flags, "the flag must name WHOSE land mask fired"
    assert r.quality == "REJECT"


def test_coastline_disagreement_is_reported(engine, date):
    """GLORYS masks the shallow head of the Persian Gulf; the satellite product resolves it.
    That disagreement is a finding, not noise — F9 Sentinel consumes it."""
    r = engine.collocate(29.5, 48.25, date)
    assert "LAND_IN_GLORYS" in r.flags
    assert any(f.startswith("COASTLINE_DISAGREEMENT") for f in r.flags), r.flags
    sat = r.sources.get("satellite")
    if sat is not None and sat.get("sss") is not None:
        assert sat["sss"] > 38.0, "the Persian Gulf is hypersaline; a low value would be suspect"


def test_outside_domain_is_flagged(engine, date):
    r = engine.collocate(0.0, 65.0, date)      # south of the domain
    assert "OUTSIDE_DOMAIN" in r.flags
    assert r.quality == "REJECT"


# ── offsets are measured, not asserted ──────────────────────────────────────
def test_exact_grid_point_has_zero_spatial_offset(engine, date):
    r = engine.collocate(float(config.LAT[40]), float(config.LON[80]), date)
    assert r.offsets["spatial_km"] < 0.01


def test_spatial_offset_never_exceeds_half_a_cell(engine, date):
    """Nearest-neighbour on a 0.25 deg grid: no query can land further than the half-diagonal."""
    rng = np.random.default_rng(0)
    for _ in range(40):
        la = float(rng.uniform(6, 29)); lo = float(rng.uniform(46, 104))
        r = engine.collocate(la, lo, date)
        assert r.offsets["spatial_km"] <= SPATIAL_MAX_KM, (la, lo, r.offsets)


def test_haversine_matches_a_known_distance():
    """One degree of latitude is ~111 km. Guards against a flat-earth approximation slipping in."""
    d = _haversine_km(15.0, 65.0, 16.0, 65.0)
    assert 110.0 < d < 112.0
    # a degree of LONGITUDE shrinks with latitude — the whole reason we use haversine
    assert _haversine_km(25.0, 65.0, 25.0, 66.0) < _haversine_km(5.0, 65.0, 5.0, 66.0)


def test_quality_follows_the_measured_temporal_offset(engine):
    g = engine._npz("grids.npz")
    exact = pd.Timestamp(g["times"][-1])
    assert engine.collocate(*OCEAN, exact).quality == "HIGH"
    assert engine.collocate(*OCEAN, exact + pd.Timedelta(days=int(TEMPORAL_MED_D))).quality in ("MEDIUM", "LOW")
    far = engine.collocate(*OCEAN, exact + pd.Timedelta(days=60))
    assert far.quality == "REJECT" and "TEMPORAL_OFFSET_EXCEEDS_TOLERANCE" in far.flags


# ── scientific sanity — the tests that would have caught Phase 1's bugs ─────
def test_glorys_surface_salinity_equals_subsurface_top_level(engine, date):
    """Two independent extraction paths read the same GLORYS variable. If they disagree, one of
    them has a depth-indexing or interpolation bug."""
    r = engine.collocate(*OCEAN, date)
    a = r.sources["glorys"]["sss"]
    b = r.sources["subsurface"]["salinity_profile"][0]
    assert a is not None and b is not None
    assert abs(a - b) < 0.01, f"glorys sss={a} but subsurface salinity[0]={b}"


def test_temperature_profile_cools_with_depth(engine, date):
    """Tropical ocean: surface is warmest. A profile that warms downward is broken."""
    prof = [v for v in engine.collocate(*OCEAN, date).sources["glorys"]["temperature_profile"]
            if v is not None]
    assert len(prof) >= 10
    assert prof[0] > prof[-1] + 5.0, "surface should be well warmer than 1000 m"


def test_values_are_in_physical_range(engine, date):
    r = engine.collocate(*OCEAN, date)
    g = r.sources["glorys"]
    assert -2.0 < g["sst"] < 40.0
    assert 0.0 <= g["sss"] < 42.0          # floor is 0: rivers make the Bay of Bengal near-fresh
    assert abs(g["u"]) < 5.0 and abs(g["v"]) < 5.0


def test_satellite_and_glorys_are_kept_separate(engine, date):
    """They are different products and SHOULD disagree slightly. If they were ever identical it
    would mean one had been substituted for the other."""
    r = engine.collocate(*OCEAN, date)
    sat, gl = r.sources.get("satellite"), r.sources["glorys"]
    if sat is None:
        pytest.skip("no satellite on this date")
    assert sat["sst"] != gl["sst"], "satellite and GLORYS SST identical — sources may be crossed"
    assert abs(sat["sst"] - gl["sst"]) < 5.0, "disagreement too large to be a product difference"


def test_argo_is_labelled_independent_and_carries_its_own_offsets(engine, date):
    found = None
    for lat in np.arange(8.0, 22.0, 1.0):
        for lon in np.arange(60.0, 92.0, 2.0):
            r = engine.collocate(float(lat), float(lon), date)
            if r.sources["argo"] is not None:
                found = r.sources["argo"]
                break
        if found:
            break
    if found is None:
        pytest.skip("no Argo profile within tolerance anywhere on this date")
    assert "INDEPENDENT" in found["note"]
    assert found["spatial_offset_km"] >= 0
    assert found["n_levels"] > 0
    assert len(found["temperature_profile"]) == config.N_DEPTHS


def test_argo_match_respects_both_space_and_time(engine, date):
    """A match must be near in BOTH dimensions — never nearest in one while far in the other."""
    for lat in np.arange(8.0, 22.0, 1.0):
        for lon in np.arange(60.0, 92.0, 2.0):
            a = engine.collocate(float(lat), float(lon), date).sources["argo"]
            if a is not None:
                assert abs(a["temporal_offset_days"]) <= engine.tolerance_days
                assert a["spatial_offset_km"] <= 160.0     # the 1 deg bounding box
                return
    pytest.skip("no Argo match found")


def test_repeated_queries_are_identical(engine, date):
    """Collocation is pure indexing — it must be deterministic."""
    a = engine.collocate(*OCEAN, date).to_dict()
    b = engine.collocate(*OCEAN, date).to_dict()
    assert a == b


def test_rejects_an_invalid_spatial_method():
    with pytest.raises(ValueError):
        CollocationEngine(spatial_method="magic")


# ---------------------------------------------------------------------------------------------
# the daily era, and telling an empty Argo match from an empty Argo TABLE  (added 2026-09-03)
# ---------------------------------------------------------------------------------------------
def test_phase1_remains_the_default_and_its_argo_table_is_unchanged():
    """Every published F1 number was measured on this pairing. Adding an era must not move it."""
    e = CollocationEngine()
    assert e.era == "phase1"
    assert e.argo_table == "argo_test"


def test_argo_table_follows_the_era_but_an_explicit_table_still_wins():
    assert CollocationEngine(era="daily").argo_table == "argo_daily_period"
    assert CollocationEngine(era="daily", argo_table="argo_test").argo_table == "argo_test"
    with pytest.raises(ValueError):
        CollocationEngine(era="2026")


def test_argo_coverage_reports_what_the_table_holds_rather_than_asserting_it():
    """The page used to explain every empty match as ocean sparsity. It can now read the span."""
    p1 = CollocationEngine(era="phase1").argo_coverage()
    assert p1 is not None and p1["years"] == [2022], p1

    # THE BUG, AS A TEST: 2019-2021 dates were offered against a 2022-only table, so an empty
    # match there said nothing about the ocean -- yet the UI blamed float sparsity.
    e = CollocationEngine(era="phase1")
    assert not e.argo_table_covers("2019-07-15")
    assert not e.argo_table_covers("2021-07-15")
    assert e.argo_table_covers("2022-07-15")


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(config.DATA_PROCESSED, "daily_sat", "v001")),
    reason="daily bundles not on this machine")
def test_daily_era_collocates_real_2026_data_with_a_2026_argo_table():
    e = CollocationEngine(era="daily")
    cov = e.argo_coverage()
    assert 2026 in cov["years"] and e.argo_table_covers("2026-06-18")

    r = e.collocate(15.0, 65.0, "2026-06-18")
    assert r.matched["datetime"] == "2026-06-18", "daily record must hit the exact day"
    assert r.offsets["temporal_days"] == 0
    gl = r.sources["glorys"]
    assert 20.0 < gl["sst"] < 35.0 and 30.0 < gl["sss"] < 40.0
    assert sum(v is not None for v in gl["temperature_profile"]) == config.N_DEPTHS

    # satellite here is daily_sat/v001 -- real observations, and NOT the same numbers as GLORYS
    sat = r.sources["satellite"]
    assert sat is not None and sat["sst"] is not None
    assert sat["sst"] != gl["sst"], "satellite and reanalysis SST must not be identical"

    # the bundles carry no subsurface currents; that must be flagged, not silently None
    assert "SUBSURFACE_CURRENTS_UNAVAILABLE" in r.flags
    assert all(v is None for v in r.sources["subsurface"]["u_profile"])
    assert any(v is not None for v in r.sources["subsurface"]["salinity_profile"])
    assert r.provenance["era"] == "daily"
    assert r.provenance["argo_table"] == "argo_daily_period"


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(config.DATA_PROCESSED, "daily_sat", "v001")),
    reason="daily bundles not on this machine")
def test_daily_era_matches_a_float_that_is_actually_there():
    """An era switch that returned None for everything would look like working code."""
    import pandas as _pd
    df = _pd.read_parquet(config.art("argo_daily_period.parquet"))
    row = df.iloc[len(df) // 2]
    e = CollocationEngine(era="daily")
    r = e.collocate(float(row["lat"]), float(row["lon"]), _pd.Timestamp(row["date"]))
    a = r.sources["argo"]
    assert a is not None, "a float taken FROM the table must match against that table"
    assert a["spatial_offset_km"] < 30.0 and abs(a["temporal_offset_days"]) <= 10
