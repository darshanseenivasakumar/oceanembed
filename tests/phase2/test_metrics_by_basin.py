"""per_depth_by_basin must slice the SAME metrics by the canonical basins -- nothing more.

The risks these tests guard against, in order of how quietly they would fail:

  1. The overall block silently differing from plain per_depth (a basin split should not change
     the whole-domain number).
  2. Profiles going missing between the basins and the total, so per-basin counts do not add up.
  3. The function inventing its own geography instead of deferring to phase2.basins.
  4. A misaligned lat/lon scoring profiles under the wrong basin with no error raised.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2 import basins
from phase2.tscast_nio import metrics

N_D = config.N_DEPTHS


def _synthetic(n_arabian=120, n_bengal=80, n_unassigned=0, seed=0):
    """Profiles at known longitudes so their basin is not in doubt: 65E Arabian, 88E Bay of
    Bengal, 79E (south of Sri Lanka) unassigned. All at 15N."""
    rng = np.random.default_rng(seed)
    lon = np.concatenate([np.full(n_arabian, 65.0), np.full(n_bengal, 88.0),
                          np.full(n_unassigned, 79.0)])
    lat = np.full(lon.shape, 15.0)
    truth = rng.normal(20.0, 2.0, size=(lon.size, N_D))
    pred = truth + rng.normal(0.0, 0.3, size=truth.shape)
    clim = truth + rng.normal(0.0, 1.0, size=truth.shape)
    return pred, truth, lat, lon, clim


# ------------------------------------------------------------------ overall

def test_overall_block_is_identical_to_plain_per_depth():
    pred, truth, lat, lon, clim = _synthetic()
    plain = metrics.per_depth(pred, truth, clim=clim, reference="argo")
    split = metrics.per_depth_by_basin(pred, truth, lat, lon, clim=clim, reference="argo")["overall"]
    np.testing.assert_allclose(split["rmse"], plain["rmse"], equal_nan=True)
    np.testing.assert_allclose(split["skill_rmse_ratio"], plain["skill_rmse_ratio"], equal_nan=True)
    assert split["n"] == plain["n"]
    assert split["overall"]["rmse"] == pytest.approx(plain["overall"]["rmse"], abs=1e-12)


# ------------------------------------------------------------- reconciliation

def test_profile_counts_reconcile_with_the_total():
    pred, truth, lat, lon, clim = _synthetic(n_arabian=120, n_bengal=80, n_unassigned=15)
    pf = metrics.per_depth_by_basin(pred, truth, lat, lon, clim=clim)["profiles"]
    assert pf["arabian_sea"] == 120
    assert pf["bay_of_bengal"] == 80
    assert pf["unassigned"] == 15
    assert pf["arabian_sea"] + pf["bay_of_bengal"] + pf["unassigned"] == pf["total"] == 215


def test_per_depth_n_adds_up_across_basins_when_none_unassigned():
    """With no unassigned profiles, the overall count at each depth must equal the sum of the two
    basins' counts at that depth. If a profile were double-counted or dropped, this breaks."""
    pred, truth, lat, lon, clim = _synthetic(n_arabian=120, n_bengal=80, n_unassigned=0)
    r = metrics.per_depth_by_basin(pred, truth, lat, lon, clim=clim)
    overall_n = r["overall"]["n"]
    a_n = r["by_basin"]["arabian_sea"]["n"]
    b_n = r["by_basin"]["bay_of_bengal"]["n"]
    for d in range(N_D):
        assert overall_n[d] == a_n[d] + b_n[d], f"depth index {d} does not reconcile"


def test_it_defers_to_the_canonical_basin_definition():
    """The counts must match phase2.basins.classify_points on the same points -- the function must
    not draw its own boxes."""
    pred, truth, lat, lon, clim = _synthetic(n_arabian=50, n_bengal=90, n_unassigned=7)
    pf = metrics.per_depth_by_basin(pred, truth, lat, lon)["profiles"]
    labels = basins.classify_points(lat, lon)
    assert pf["arabian_sea"] == int((labels == basins.ARABIAN_SEA).sum())
    assert pf["bay_of_bengal"] == int((labels == basins.BAY_OF_BENGAL).sum())
    assert pf["unassigned"] == int((labels == basins.UNASSIGNED).sum())


# -------------------------------------------------------------------- guards

def test_a_three_dimensional_field_is_rejected():
    """Basin membership is per profile, so the leading axis must be the profile axis. A gridded
    (time, cell, depth) block would be assigned nonsensically; refuse it rather than guess."""
    grid = np.zeros((4, 5, N_D))
    with pytest.raises(ValueError, match="profile axis"):
        metrics.per_depth_by_basin(grid, grid, np.zeros(4), np.zeros(4))


def test_misaligned_latlon_is_rejected():
    pred = np.zeros((10, N_D))
    with pytest.raises(ValueError, match="profile count"):
        metrics.per_depth_by_basin(pred, pred, np.zeros(9), np.zeros(10))


def test_an_empty_basin_is_reported_not_dropped():
    """Everything in the Arabian Sea -> the Bay of Bengal block must still exist, with n 0 and a
    note, so a reader sees 'zero profiles here' rather than a missing key."""
    pred, truth, lat, lon, clim = _synthetic(n_arabian=60, n_bengal=0, n_unassigned=0)
    r = metrics.per_depth_by_basin(pred, truth, lat, lon, clim=clim)
    assert r["by_basin"]["bay_of_bengal"]["n_profiles"] == 0
    assert "note" in r["by_basin"]["bay_of_bengal"]
    assert r["by_basin"]["arabian_sea"]["n_profiles"] == 60


# ---------------------------------------------------------------- real data

def test_on_the_real_argo_set_every_profile_lands_and_counts_reconcile():
    """The path the evaluation actually uses. pred = truth (a perfect reconstruction) is enough to
    exercise classification and reconciliation; the metric VALUES are checked elsewhere."""
    import pandas as pd
    from oceanembed.validation import validate_argo as VA
    p = config.art("argo_daily_period.parquet")
    if not os.path.exists(p):
        pytest.skip("argo_daily_period.parquet absent - artifacts are gitignored")
    keys, truth = VA.pivot_profiles(pd.read_parquet(p))
    lat, lon = keys["lat"].values, keys["lon"].values
    r = metrics.per_depth_by_basin(truth, truth, lat, lon)
    pf = r["profiles"]
    assert pf["arabian_sea"] + pf["bay_of_bengal"] + pf["unassigned"] == pf["total"] == len(lat)
    assert pf["arabian_sea"] > 100 and pf["bay_of_bengal"] > 100
    # perfect reconstruction -> zero RMSE in each basin, at every depth that has samples
    for name in ("arabian_sea", "bay_of_bengal"):
        for d, rm in enumerate(r["by_basin"][name]["rmse"]):
            if r["by_basin"][name]["n"][d] > 0:
                assert rm == pytest.approx(0.0, abs=1e-9), f"{name} depth {d}"


# ------------------------------------------------------- bounds on the record

def test_the_record_carries_the_bounds_as_numbers_not_only_prose():
    """D4. `basin_definition` names the module, which is not enough: a reader of a metrics file a
    year from now cannot recover WHICH partition a per-basin number was computed over from a
    sentence. The actual limits must travel with the numbers they qualify."""
    pred, truth, lat, lon, clim = _synthetic()
    rec = metrics.per_depth_by_basin(pred, truth, lat, lon)
    b = rec["basin_bounds"]
    assert b[basins.ARABIAN_SEA]["lon_max"] == 78.0
    assert b[basins.ARABIAN_SEA]["excludes_persian_gulf"] == {"lat_min": 23.5, "lon_max": 56.5}
    assert b[basins.BAY_OF_BENGAL]["lon_min"] == 80.0
    assert b[basins.BAY_OF_BENGAL]["lon_max"] == 100.0
    assert basins.UNASSIGNED in b, "the record must say that unassigned water exists"


def test_the_recorded_bounds_are_the_ones_actually_in_force():
    """A declared limit that the classifier does not honour is worse than none -- it is a number
    on the record that reads as verified. Probe each boundary from both sides."""
    b = basins.BOUNDS
    as_max = b[basins.ARABIAN_SEA]["lon_max"]
    bob_min = b[basins.BAY_OF_BENGAL]["lon_min"]
    bob_max = b[basins.BAY_OF_BENGAL]["lon_max"]
    pg = b[basins.ARABIAN_SEA]["excludes_persian_gulf"]

    at = lambda la, lo: basins.classify_points([la], [lo])[0]  # noqa: E731

    assert at(15.0, as_max - 0.5) == basins.ARABIAN_SEA
    assert at(15.0, as_max + 0.5) != basins.ARABIAN_SEA      # the 78-80 E strip
    assert at(15.0, bob_min + 0.5) == basins.BAY_OF_BENGAL
    assert at(15.0, bob_min - 0.5) != basins.BAY_OF_BENGAL
    assert at(8.0, bob_max - 0.5) == basins.BAY_OF_BENGAL
    assert at(8.0, bob_max + 0.5) != basins.BAY_OF_BENGAL    # Malacca side

    # Inside the declared Persian Gulf box -> not Arabian Sea. Outside it, past Hormuz, the
    # Gulf of Oman IS Arabian Sea: that is why the limit is 56.5 and not 57.0.
    assert at(pg["lat_min"] + 0.5, pg["lon_max"] - 0.5) != basins.ARABIAN_SEA
    assert at(25.2, 56.9) == basins.ARABIAN_SEA
