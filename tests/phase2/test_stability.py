"""Hard static-stability projection. Owner: Unit A (Arjhun).

The failure this file exists to catch is a guarantee that is not one. A projection that eliminates
"most" violations, or that silently keeps the original value when it cannot invert a level, reads
exactly like a working guarantee from the outside -- the function returns, the profile looks
sensible, and the violation count is small rather than zero. Both of those bugs were in the first
version of this module and both were found by counting, not by reading.
"""
from __future__ import annotations

import numpy as np
import pytest

from phase2.physics import seawater, stability as ST

DEPTHS = ST.DEPTHS


def a_stable_profile():
    """A plausible tropical column: warm, fresh-ish at the top, cold and salty at depth."""
    t = np.array([28.6, 28.5, 28.3, 27.9, 27.0, 24.5, 21.0, 17.5, 15.5, 14.2,
                  12.5, 11.0, 9.0, 8.0, 6.5])
    s = np.array([34.6, 34.7, 34.8, 34.9, 35.0, 35.1, 35.2, 35.2, 35.2, 35.1,
                  35.0, 35.0, 34.9, 34.8, 34.7])
    return t, s


# ==================================================== PAVA is the projection it claims to be

def test_pava_agrees_with_sklearn():
    """Fifteen hand-written lines against the reference implementation. A transcription error here
    would produce a monotone sequence that is simply not the nearest one, and nothing downstream
    could tell."""
    from sklearn.isotonic import IsotonicRegression
    rng = np.random.default_rng(0)
    for _ in range(200):
        y = rng.normal(size=int(rng.integers(2, 20)))
        got = ST.isotonic_nondecreasing(y)
        want = IsotonicRegression(increasing=True).fit_transform(np.arange(y.size), y)
        assert np.allclose(got, want, atol=1e-12)


def test_pava_output_is_always_non_decreasing():
    rng = np.random.default_rng(1)
    for _ in range(200):
        y = rng.normal(size=int(rng.integers(2, 30)))
        assert np.all(np.diff(ST.isotonic_nondecreasing(y)) >= -1e-12)


def test_pava_is_the_identity_on_an_already_sorted_sequence():
    """The property that makes the operator safe to apply unconditionally: it cannot damage a
    profile that had nothing wrong with it."""
    y = np.array([1.0, 1.0, 2.0, 3.5, 3.5, 9.0])
    assert np.allclose(ST.isotonic_nondecreasing(y), y)


def test_pava_moves_values_both_ways_unlike_a_cumulative_maximum():
    """A cummax also produces a non-decreasing sequence, and is not the nearest one: it can only
    push values up, so one too-large element drags everything after it."""
    y = np.array([0.0, 10.0, 1.0, 2.0])
    got = ST.isotonic_nondecreasing(y)
    assert got[1] < 10.0, "PAVA must pull the outlier DOWN, which a cumulative maximum cannot"
    assert np.allclose(got, [0.0, 13.0 / 3, 13.0 / 3, 13.0 / 3])


def test_pava_rejects_bad_weights_and_non_finite_values():
    with pytest.raises(ValueError):
        ST.isotonic_nondecreasing([1.0, 2.0], w=[1.0, 0.0])
    with pytest.raises(ValueError):
        ST.isotonic_nondecreasing([1.0, np.nan])


# ==================================================== the violation counter

def test_violations_counts_a_planted_inversion():
    rho = np.array([1021.0, 1022.0, 1023.0, 1022.5, 1024.0] + [1025.0] * 10)
    v = ST.stability_violations(rho, DEPTHS)
    assert v["n_violating"] == 1
    assert v["worst_drho_dz"] < 0
    assert v["n_pairs"] == 14


def test_violations_ignores_masked_pairs_rather_than_passing_them():
    """A gap is not a violation and is not a pass. A pair touching a masked level must not be
    counted at all -- counting it as clean would let a NaN buy a clean bill of health."""
    rho = np.array([1021.0, 1022.0, 1021.5] + [1025.0] * 12)
    mask = np.ones(15, bool)
    assert ST.stability_violations(rho, DEPTHS, mask=mask)["n_violating"] == 1
    mask[2] = False
    v = ST.stability_violations(rho, DEPTHS, mask=mask)
    assert v["n_violating"] == 0
    assert v["n_pairs"] == 12, "both pairs touching the masked level must drop out"


def test_violations_refuses_unordered_depths():
    with pytest.raises(ValueError):
        ST.stability_violations(np.ones(15), np.array([0, 5, 3] + list(range(3, 15))))


# ==================================================== the projection itself

def test_projection_eliminates_a_planted_inversion_and_verifies_it():
    t, s = a_stable_profile()
    t[7] = 21.5                                  # a warm blob under cooler water
    r = ST.project_profile(t, s)
    assert r["violations_before"]["n_violating"] >= 1
    assert r["violations_after"]["n_violating"] == 0
    assert r["verified"] is True


def test_projection_is_the_identity_on_a_stable_profile():
    t, s = a_stable_profile()
    r = ST.project_profile(t, s)
    assert r["violations_before"]["n_violating"] == 0
    assert r["n_levels_changed"] == 0
    assert r["max_abs_dT"] == 0.0
    assert np.allclose(r["temperature"], t)


def test_projected_density_actually_equals_the_isotonic_target():
    """The round trip is the whole guarantee: rho -> PAVA -> T -> rho must come back where it was
    sent. Verified against the isotonic target, not merely against monotonicity."""
    t, s = a_stable_profile()
    t[5] = 26.0
    t[9] = 16.0
    r = ST.project_profile(t, s)
    ok = np.isfinite(r["density_out"]) & np.isfinite(r["density_isotonic"])
    assert ok.sum() >= 14
    assert np.allclose(r["density_out"][ok], r["density_isotonic"][ok], atol=1e-8)


def test_tightening_the_root_find_tolerance_is_load_bearing(monkeypatch):
    """FALSIFICATION. T_TOL was 1e-6 and it left 395 phantom violations on real stage-2 output,
    because a pooled block has EXACTLY equal density and a 1e-6 degC inversion error pushes half of
    those flat pairs marginally negative. Loosening it here must bring the failure back; if this
    test ever passes with a loose tolerance, the constant has stopped mattering and the comment
    explaining it is out of date."""
    rng = np.random.default_rng(3)
    t, s = a_stable_profile()
    bad = 0
    for _ in range(40):
        tt = t + rng.normal(0, 0.8, t.size)
        monkeypatch.setattr(ST, "T_TOL", 1e-3)
        r = ST.project_profile(tt, s)
        bad += r["violations_after"]["n_violating"]
    assert bad > 0, "a loose tolerance must reintroduce violations, or T_TOL is not load-bearing"


def test_a_level_that_cannot_be_inverted_is_refused_not_silently_left_violating():
    """The second bug this module had. Keeping the original temperature when the inversion refuses
    restores the ORIGINAL density -- and therefore the original violation -- inside a function
    whose entire promise is that there are none. The level must come back NaN, with a reason."""
    # Near-fresh, cold water: below the density maximum drho/dT is positive, so the mapping
    # rho -> T is not one-to-one and no root may be returned.
    t = np.array([2.0, 1.0, 3.0] + [5.0] * 12)
    s = np.array([0.05, 0.05, 0.05] + [35.0] * 12)
    r = ST.project_profile(t, s)
    assert r["refusals"], "the fresh-water regime must be refused, not inverted"
    assert r["violations_after"]["n_violating"] == 0, (
        "a refused level must become a gap, never a silently surviving violation")
    assert np.isnan(r["temperature"][np.isnan(r["density_isotonic"])]).all()


def test_stage_one_is_refused_because_stability_needs_salinity():
    """The compliance boundary, in code. A temperature-only static-stability check is not a weaker
    version of this -- enforcing monotone cooling would delete Bay of Bengal barrier-layer
    inversions, which are real and which this project measures elsewhere."""
    t, _ = a_stable_profile()
    with pytest.raises(ValueError, match="salinity"):
        ST.project_profile(t, None)


def test_projection_never_changes_salinity():
    t, s = a_stable_profile()
    t[6] = 22.0
    r = ST.project_profile(t, s)
    assert np.allclose(r["salinity"], s), "the operator moves temperature at FIXED salinity"


# ==================================================== the stacked version

def test_project_many_matches_the_scalar_path_profile_by_profile():
    """One implementation, not two. A vectorised copy that disagreed would only tell us the copy
    was wrong -- the drift this project has been bitten by repeatedly."""
    rng = np.random.default_rng(7)
    t, s = a_stable_profile()
    T = np.stack([t + rng.normal(0, 1.0, 15) for _ in range(12)])
    S = np.stack([s] * 12)
    many = ST.project_many(T, S)
    for i in range(T.shape[0]):
        one = ST.project_profile(T[i], S[i])
        assert np.allclose(many["temperature"][i], one["temperature"], equal_nan=True)
    assert many["violations_after"]["n_violating"] == 0
    assert many["verified"] is True


def test_project_many_reports_counts_that_reconcile():
    rng = np.random.default_rng(9)
    t, s = a_stable_profile()
    T = np.stack([t + rng.normal(0, 1.2, 15) for _ in range(30)])
    S = np.stack([s] * 30)
    r = ST.project_many(T, S)
    assert r["n_profiles"] == 30
    assert 0 <= r["n_profiles_changed"] <= 30
    assert r["n_profiles_verified"] == 30
    assert r["violations_before"]["n_violating"] > r["violations_after"]["n_violating"]


def test_the_eos_used_here_is_the_projects_own():
    """Not a second transcription of EOS-80. If this ever imports its own coefficients, the
    fifteen published check values in test_physics.py stop covering this module."""
    assert ST.seawater is seawater
