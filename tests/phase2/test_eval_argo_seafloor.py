"""The scorer must not score what the product refuses to serve, nor a baseline that does not exist.

TWO DEFECTS THIS FILE EXISTS FOR (audit 2026-09-06, findings #10 and the climatology fill)

1. Below the training target's seafloor. `output.build_record` masks every depth where the GLORYS
   bundle has no water -- "a reconstruction that filled it with a number would be inventing water" --
   yet every scorer compared the model's raw mu against Argo at exactly those depths. Measured on the
   shipped run: 93 of 12,829 comparisons (RMSE 1.614 there, bias -0.759) plus one profile on a
   GLORYS land cell. The metric and the product disagreed about what a valid prediction is.

2. A climatology that is not one. `build_samples.py` drops any cell whose column has a NaN, so a
   cell shallower than 1000 m contributes no rows and `climatology.build_climatology` fills it with
   the basin-mean profile -- at EVERY depth, not just the dry ones. Skill against that fill is not
   skill against climatology. Measured: +0.149 where a real per-cell climatology exists (895
   profiles), +0.551 at the 67 shelf profiles scored against the fill, +0.260 blended.

The helpers under test make both refusals explicit and countable, so a scored number always
travels with how many comparisons it declined to make and why.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.tscast_nio import eval_argo as EA, metrics as M

D15 = base.N_DEPTHS


def _toy():
    """A 4x4 grid: cell (0,0) is land, cell (1,1) has water to 100 m only (index 7), the rest are
    full-depth. Four profiles: one on each kind of cell, plus a second full-depth one."""
    land = np.zeros((4, 4), bool); land[0, 0] = True
    valid = np.ones((4, 4, D15), bool)
    valid[0, 0, :] = False                 # land: no water anywhere
    valid[1, 1, 8:] = False                # shelf: dry below index 7 (100 m)
    la = np.array([0, 1, 2, 3]); lo = np.array([0, 1, 2, 3])
    truth = np.full((4, D15), 20.0)
    truth[2, 14] = np.nan                  # a full-depth profile the float itself did not reach
    return land, valid, la, lo, truth


def test_water_mask_is_false_exactly_where_the_target_has_no_water():
    land, valid, la, lo, _ = _toy()
    w = EA.seafloor_mask(la, lo, valid, land)
    assert w.shape == (4, D15)
    assert not w[0].any(), "a land cell has no water at any depth"
    assert w[1, :8].all() and not w[1, 8:].any(), "the shelf cell is wet to 100 m and dry below"
    assert w[2].all() and w[3].all()


def test_applying_the_mask_removes_only_the_refused_comparisons_and_counts_them():
    land, valid, la, lo, truth = _toy()
    masked, ref = EA.apply_seafloor_mask(truth, la, lo, valid, land)
    # land profile: all 15 gone; shelf profile: 7 gone (indices 8..14); full-depth ones untouched
    assert np.isnan(masked[0]).all()
    assert np.isfinite(masked[1, :8]).all() and np.isnan(masked[1, 8:]).all()
    assert np.array_equal(np.isfinite(masked[2]), np.isfinite(truth[2]))
    assert np.isfinite(masked[3]).all()
    assert ref["n_refused_below_seafloor"] == 15 + 7
    assert ref["n_profiles_on_land"] == 1
    assert ref["per_depth_refused"][7] == 1 and ref["per_depth_refused"][8] == 2
    assert ref["scoring_protocol"] == EA.SCORING_PROTOCOL == "seafloor_masked_v2"
    assert ref["truth_axis"] == EA.TRUTH_AXIS == "depth_m_unesco1983"
    # a level the float never reached is NOT a refusal -- it was never a comparison
    assert sum(ref["per_depth_refused"]) == 22


def test_the_mask_never_invents_a_comparison():
    """Masking can only remove finite values; it must never turn a NaN into a number."""
    land, valid, la, lo, truth = _toy()
    masked, _ = EA.apply_seafloor_mask(truth, la, lo, valid, land)
    assert np.all(np.isfinite(masked) <= np.isfinite(truth))


def test_baseline_exists_only_where_the_cell_has_a_real_climatology():
    """build_samples drops any-NaN columns, so a cell without water to the deepest level has no
    rows and gets the basin-mean fill. A real climatology exists only for full-depth cells."""
    land, valid, la, lo, _ = _toy()
    ok = EA.baseline_exists_mask(la, lo, valid, land)
    assert ok.tolist() == [False, False, True, True]


def test_per_depth_reports_skill_against_the_real_baseline_separately():
    """The blended skill stays (it is what every earlier artifact recorded); the real-baseline skill
    is ADDED with its own n, never silently substituted."""
    rng = np.random.default_rng(0)
    truth = rng.normal(20, 2, (40, D15))
    pred = truth + rng.normal(0, 0.5, truth.shape)
    clim = truth + rng.normal(0, 1.0, truth.shape)
    clim[:10] = truth[:10] + rng.normal(0, 5.0, (10, D15))       # a terrible "baseline" at 10 rows
    ok = np.ones(40, bool); ok[:10] = False
    m = M.per_depth(pred, truth, clim=clim, baseline_ok=ok)
    o = m["overall"]
    assert o["n_real_baseline"] == 30 * D15
    assert o["skill_rmse_ratio_real_baseline"] < o["skill_rmse_ratio"], (
        "excluding the rows where the baseline is garbage must LOWER the skill, because those rows "
        "were flattering it")
    assert "real_baseline" in o["skill_note"].lower() or "real baseline" in o["skill_note"].lower()
    # without the flag the fields are absent, so old artifacts and new ones cannot be confused
    m0 = M.per_depth(pred, truth, clim=clim)
    assert "skill_rmse_ratio_real_baseline" not in m0["overall"]


def test_per_depth_refuses_a_baseline_mask_of_the_wrong_length():
    truth = np.zeros((5, D15)); pred = np.zeros((5, D15)); clim = np.zeros((5, D15))
    with pytest.raises(ValueError, match="baseline_ok"):
        M.per_depth(pred, truth, clim=clim, baseline_ok=np.ones(4, bool))


# -- on the real bundle and the real table ------------------------------------------------

_BUNDLE = os.path.join("data", "processed", "daily_sat", "v001")
_TABLE = base.art("argo_daily_period.parquet")
needs_data = pytest.mark.skipif(not (os.path.isdir(_BUNDLE) and os.path.exists(_TABLE)),
                                reason="satellite bundle or daily Argo table absent")


@needs_data
def test_the_shipped_collocation_refuses_92_comparisons_and_one_land_profile():
    """Pinned so the number the deck and notes quote cannot drift from the code that produced it.
    Measured 2026-09-07 on the shipped bundle against the depth-axis Argo table
    (seafloor_masked_v2): 963 profiles, 92 below-seafloor comparisons, 1 land profile,
    12,819 -> 12,727 comparisons. Under the pressure-as-depth table (v1) it was 962 / 93 /
    12,829 -> 12,736: one float that reached 1000 dbar no longer reaches 1000 m, and one
    profile that used to interpolate to nothing now carries a level."""
    from phase2.tscast_nio import dataset as D

    d = D.load_daily(_BUNDLE)
    _tr, te = D.daily_split_indices(d["times"])
    keys, truth, keep, t_idx, la, lo, ref = EA.collocate(d, te, verbose=False)
    assert int(keep.sum()) == 963
    assert ref["n_refused_below_seafloor"] == 92
    assert ref["n_profiles_on_land"] == 1
    assert int(np.isfinite(truth[keep]).sum()) == 12819 - 92
    assert ref["per_depth_refused"][-1] == 21, "the deepest level carried the most refusals"
    ok = EA.baseline_exists_mask(la[keep], lo[keep], d["valid_mask"], d["land_mask"])
    assert int(ok.sum()) == 896, "896 of the 963 profiles sit in cells with a real climatology"
