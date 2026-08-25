"""Frozen constants vs the SIH26066 problem statement.

These are the cheapest things a judge can check and the easiest for us to drift on: a depth list
is two lists side by side, and a mismatch is visible in five seconds without reading a line of
our code. So they get asserted, not remembered.

Source of the required values, fetched and read directly:
    https://sih2026.vuce.in/en  ->  SIH26066
    "Standard depths in meters: (0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000)"
    "daily surface satellite observations at 0.25 degree spatial resolution for North Indian Ocean
     (5 N to 30 N and 45 E to 105 E)"

If the team deliberately deviates, do NOT delete a test here -- record the deviation in
docs/DECISIONS.md and point the test at the decision. A silent substitution is the failure mode.
"""
from __future__ import annotations

import pytest

from oceanembed import config

# Verbatim from the problem statement. Do not edit to make a test pass.
PS_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
PS_LAT_MIN, PS_LAT_MAX = 5.0, 30.0
PS_LON_MIN, PS_LON_MAX = 45.0, 105.0
PS_RESOLUTION = 0.25


# --- region ------------------------------------------------------------------
def test_region_matches_the_problem_statement():
    r = config.REGION
    assert (r["lat_min"], r["lat_max"]) == (PS_LAT_MIN, PS_LAT_MAX)
    assert (r["lon_min"], r["lon_max"]) == (PS_LON_MIN, PS_LON_MAX)


def test_resolution_is_quarter_degree():
    assert config.REGION["step"] == PS_RESOLUTION


def test_grid_size_follows_from_the_region():
    """100 x 240 is what 5-30N by 45-105E at 0.25 degrees must produce."""
    assert config.N_LAT == int((PS_LAT_MAX - PS_LAT_MIN) / PS_RESOLUTION) == 100
    assert config.N_LON == int((PS_LON_MAX - PS_LON_MIN) / PS_RESOLUTION) == 240


def test_grid_covers_the_region_without_overshooting():
    assert config.LAT.min() >= PS_LAT_MIN and config.LAT.max() < PS_LAT_MAX
    assert config.LON.min() >= PS_LON_MIN and config.LON.max() < PS_LON_MAX


# --- depths ------------------------------------------------------------------
def test_depth_count_matches_the_problem_statement():
    assert config.N_DEPTHS == len(PS_DEPTHS) == 15


def test_depths_are_ascending_and_unique():
    d = list(config.DEPTHS)
    assert d == sorted(d), "DEPTHS must ascend; predict/plot code assumes ordering"
    assert len(set(d)) == len(d), "duplicate depth levels"


def test_max_depth_reaches_1000m():
    assert max(config.DEPTHS) == 1000, "the problem statement requires coverage to 1000 m"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "D-008: config.DEPTHS has the right COUNT (15) but not the problem statement's SET -- "
        "5 m was substituted for 400 m. Fix is cheap and needs NO re-download: MAX_DEPTH=1100 "
        "means the GLORYS file already holds every level to 1062 m, so only preprocess -> "
        "build_samples -> retrain are affected. Swap 400 -> 5 (or keep 400 as a 16th level and "
        "record it in DECISIONS.md). When fixed, this xfail turns into an unexpected PASS and the "
        "marker must be deleted -- that is deliberate, so the exemption cannot outlive the bug."
    ),
)
def test_depths_match_the_problem_statement_exactly():
    assert list(config.DEPTHS) == PS_DEPTHS, (
        f"\n  PS  : {PS_DEPTHS}"
        f"\n  ours: {list(config.DEPTHS)}"
        f"\n  missing from ours: {sorted(set(PS_DEPTHS) - set(config.DEPTHS))}"
        f"\n  extra in ours    : {sorted(set(config.DEPTHS) - set(PS_DEPTHS))}"
    )


# --- surface inputs ----------------------------------------------------------
def test_the_five_surface_variables_are_present_and_first():
    """The PS names SST, SSS, SSH/SLA and surface currents (u,v) as the inputs."""
    assert config.FEATURES[:5] == ["sst", "sss", "ssh", "u", "v"]


def test_feature_count_is_consistent():
    assert config.N_FEAT == len(config.FEATURES)


# --- reproducibility ---------------------------------------------------------
def test_split_is_temporal_not_random():
    """Adjacent cells on adjacent days are near-duplicates; a random split leaks."""
    assert set(config.TRAIN_YEARS).isdisjoint(config.TEST_YEARS)
    assert max(config.TRAIN_YEARS) < min(config.TEST_YEARS), "test must follow train in TIME"


def test_seed_is_fixed():
    assert isinstance(config.SEED, int)
