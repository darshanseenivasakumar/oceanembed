"""F8 Validation Lab -- tests.

The point of F8 is honesty, so most of these assert that the module cannot MISREPRESENT the
artifacts: that skill uses the convention the stored figure was computed with, that the model's
GLORYS-fed score is never presented as the reanalysis, and that the counter-intuitive 1000 m
result is surfaced rather than smoothed over.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.validation import lab

pytestmark = pytest.mark.filterwarnings("ignore")


def _need(path, why):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} absent -- {why}")


@pytest.fixture(scope="module")
def depth_stats():
    _need(lab.ARGO_ERROR, "ships in the data bundle")
    return lab.per_depth()


@pytest.fixture(scope="module")
def gap():
    _need(lab.REANALYSIS_GAP, "run scripts/phase2/glorys_vs_argo.py")
    return lab.reanalysis_gap()


# ---------------------------------------------------------------------------------------------
# the skill convention
# ---------------------------------------------------------------------------------------------
def test_skill_convention_reproduces_the_stored_headline(depth_stats):
    """skill = 1 - rmse/rmse_clim, NOT 1 - (rmse/rmse_clim)^2.

    Mixing the two would change every number on the panel while still looking plausible, so the
    convention is pinned against the figure Phase 1 already published.
    """
    o = depth_stats["overall"]
    recomputed = 1.0 - o["satellite"]["rmse"] / o["climatology"]["rmse"]
    assert recomputed == pytest.approx(o["satellite"]["skill_vs_clim"], abs=1e-4)

    variance_form = 1.0 - (o["satellite"]["rmse"] / o["climatology"]["rmse"]) ** 2
    assert abs(variance_form - o["satellite"]["skill_vs_clim"]) > 0.1, \
        "the two conventions must be far apart, otherwise this test proves nothing"


def test_skill_is_positive_at_every_depth(depth_stats):
    sk = depth_stats["skill_vs_climatology"]
    assert np.all(sk > 0), f"negative skill at {depth_stats['depths'][sk <= 0]}"
    assert depth_stats["all_depths_positive_skill"] is True


def test_the_1000m_paradox_is_detected_not_hidden(depth_stats):
    """Weakest skill and best absolute error are the SAME depth. A panel showing only skill
    would report our best prediction as our worst result."""
    assert depth_stats["worst_skill_is_also_best_absolute"] is True
    assert depth_stats["worst_skill_depth_m"] == 1000.0
    assert depth_stats["best_absolute_depth_m"] == 1000.0
    assert depth_stats["best_absolute_rmse"] < 0.3
    # and climatology is already excellent there, which is WHY skill is low
    k = list(config.DEPTHS).index(1000)
    assert depth_stats["rmse_climatology"][k] < 0.4


# ---------------------------------------------------------------------------------------------
# the naming trap
# ---------------------------------------------------------------------------------------------
def test_model_fed_glorys_is_never_labelled_as_the_reanalysis(depth_stats):
    """`rmse_glorys` in the artifact is a MODEL score. Calling it "GLORYS" on a panel would tell
    a judge we measured the reanalysis when we had not."""
    labels = depth_stats["labels"]
    assert "NOT the reanalysis" in labels["rmse_model_glorys"]
    assert "model" in labels["rmse_model_glorys"]
    assert "rmse_glorys" not in depth_stats, "the raw ambiguous key must not leak through"


def test_reanalysis_numbers_come_from_a_different_artifact(gap, depth_stats):
    """The two must not be the same array -- if they were, something is wired wrong."""
    assert not np.allclose(gap["rmse"], depth_stats["rmse_model_glorys"], equal_nan=True)
    assert gap["n_comparisons"] > 5000


# ---------------------------------------------------------------------------------------------
# the reanalysis gap -- the new measurement
# ---------------------------------------------------------------------------------------------
def test_reanalysis_is_worst_in_the_thermocline(gap):
    """[VERIFIED by scripts/phase2/glorys_vs_argo.py] the reanalysis' own error peaks at 100 m
    and is small below 500 m. If this inverts, the measurement or the data changed."""
    assert gap["worst_depth_m"] == 100.0
    assert 0.7 < gap["worst_mae"] < 0.9
    for z in (500.0, 700.0, 1000.0):
        k = list(config.DEPTHS).index(int(z))
        assert gap["mae"][k] < 0.3, f"reanalysis MAE at {z} m should be small, got {gap['mae'][k]}"


def test_the_thermocline_bias_sign_means_what_the_panel_says(gap):
    """bias = argo - glorys. Negative at 75-125 m = floats COLDER than the reanalysis.
    A sign error here would invert the finding on the panel."""
    assert "argo - glorys" in gap["bias_convention"]
    assert "COLDER" in gap["bias_convention"]
    for z in (75, 100, 125):
        k = list(config.DEPTHS).index(z)
        assert gap["bias"][k] < -0.3, f"expected a warm reanalysis bias at {z} m"


def test_distance_tightening_is_vacuous_on_this_grid(gap):
    """Nearest-cell distance cannot exceed ~19 km on a 0.25 deg grid, so a <=25 km filter removes
    nothing. Recorded because "we tightened to 25 km and 3 days" implies both did work; only the
    time filter does."""
    assert gap["collocation_distance_km"]["max"] < 25.0
    dist_only = gap["tightening"]["distance_only"]
    assert dist_only["n_profiles"] == gap["n_profiles"], \
        "a <=25 km filter dropped profiles -- the vacuity claim needs rechecking"


# ---------------------------------------------------------------------------------------------
# inherited vs earned
# ---------------------------------------------------------------------------------------------
def test_thermocline_error_is_inherited_not_earned():
    _need(lab.ARGO_ERROR, "bundle"); _need(lab.REANALYSIS_GAP, "run glorys_vs_argo.py")
    iv = lab.inherited_vs_earned()
    for z in (100.0, 125.0, 150.0):
        assert z in iv["at_ceiling_depths"], \
            f"{z} m should be at the ceiling of the training truth, got {iv['verdict']}"


def test_the_mixed_layer_is_where_we_are_genuinely_the_weak_link():
    _need(lab.ARGO_ERROR, "bundle"); _need(lab.REANALYSIS_GAP, "run glorys_vs_argo.py")
    iv = lab.inherited_vs_earned()
    for z in (20.0, 30.0, 50.0):
        assert z in iv["model_limited_depths"], f"{z} m should be model-limited"
    k = list(config.DEPTHS).index(50)
    assert iv["headroom_c"][k] > 0.2, "the 50 m gap should be substantial, not marginal"


def test_headroom_is_the_difference_of_two_independently_measured_arrays():
    _need(lab.ARGO_ERROR, "bundle"); _need(lab.REANALYSIS_GAP, "run glorys_vs_argo.py")
    iv = lab.inherited_vs_earned()
    assert np.allclose(iv["headroom_c"], iv["rmse_ours"] - iv["rmse_reanalysis"], equal_nan=True)
    # profile counts differ slightly and that must be visible, not smoothed away
    assert iv["n_profiles_ours"] != iv["n_profiles_reanalysis"]


def test_verdict_tolerance_is_configurable_not_hardcoded():
    _need(lab.ARGO_ERROR, "bundle"); _need(lab.REANALYSIS_GAP, "run glorys_vs_argo.py")
    loose = lab.inherited_vs_earned(tolerance_c=10.0)
    assert loose["model_limited_depths"] == [], "an absurd tolerance must call everything at-ceiling"
    strict = lab.inherited_vs_earned(tolerance_c=0.0001)
    assert len(strict["model_limited_depths"]) > len(
        lab.inherited_vs_earned()["model_limited_depths"])


# ---------------------------------------------------------------------------------------------
# limitations must be present
# ---------------------------------------------------------------------------------------------
def test_known_weaknesses_are_stated_with_evidence():
    ws = lab.known_weaknesses()
    assert len(ws) >= 4
    for w in ws:
        assert w["evidence"], f"{w['what']} has no evidence pointer"
    joined = " ".join(w["what"] + w["detail"] for w in ws)
    assert "overconfident" in joined and "D-016" in " ".join(w["evidence"] for w in ws)
    assert "24 of 48" in joined
    assert "2022" in joined


def test_lightgbm_is_refused_because_no_argo_score_exists():
    """The invariant: a baseline is shown only if a REAL ARGO SCORE EXISTS for it.

    [VERIFIED] argo_error_by_depth.json carries only rmse_satellite, rmse_glorys and
    rmse_climatology. LightGBM was never scored against Argo, so it is not shown -- on every
    machine, for the same reason.
    """
    b = lab.baseline_availability()
    assert b["climatology"]["available"] is True
    assert b["lightgbm"]["available"] is False
    assert "never scored" in b["lightgbm"]["why"]
    assert not any("lgbm" in c or "lightgbm" in c
                   for c in b["lightgbm"]["argo_columns_present"])


def test_lightgbm_stays_refused_even_when_the_row_counts_match():
    """REGRESSION. The previous guard compared local X_train rows to provenance n_train.

    On this author's machine those differ, so LightGBM was refused and the test passed. On Unit
    B's machine -- the one that will run the demo -- they match exactly, `available` came back
    True, and the panel rendered "LightGBM - shown." followed by no numbers. That is the
    fabricated baseline the guard existed to prevent, reached THROUGH the guard.

    A row count proves the training DATA is right. It cannot prove the CHECKPOINT was trained on
    it -- the pickle is unstamped (D-012). So the row count must never be the gate.
    """
    b = lab.baseline_availability()
    lgbm = b["lightgbm"]
    # The two counts agree on some machines and not others -- since the provenance fix they agree
    # HERE, which is precisely the demo-machine condition that opened the old guard. So there is
    # nothing left to simulate, and nothing to assert about the counts either: making their
    # agreement a precondition just moves the vacuous pass from one machine to the other. The
    # gate must not consult them at all, so the refusal is asserted unconditionally.
    assert lgbm["available"] is False
    assert lgbm["gate"] == "a real Argo score must exist for this baseline"


def test_the_gate_would_open_if_a_real_argo_score_appeared(monkeypatch, tmp_path):
    """The refusal must be a measurement, not a hardcoded False -- otherwise scoring LightGBM
    later would silently keep it hidden."""
    import json as _json
    fake = tmp_path / "argo.json"
    fake.write_text(_json.dumps({"rmse_climatology": [1.0], "rmse_lightgbm": [0.9]}))
    monkeypatch.setattr(lab, "ARGO_ERROR", str(fake))
    b = lab.baseline_availability()
    assert b["lightgbm"]["available"] is True
    assert b["lightgbm"]["why"] == "shown"


def test_missing_artifact_raises_an_actionable_message(monkeypatch):
    monkeypatch.setattr(lab, "REANALYSIS_GAP", os.path.join(config.ARTIFACTS, "nope.json"))
    with pytest.raises(lab.MissingArtifactError, match="glorys_vs_argo"):
        lab.reanalysis_gap()


def test_summary_assembles_without_the_ui():
    _need(lab.ARGO_ERROR, "bundle"); _need(lab.REANALYSIS_GAP, "run glorys_vs_argo.py")
    s = lab.summary()
    assert set(s) == {"per_depth", "reanalysis_gap", "inherited_vs_earned",
                      "baseline_availability", "mc_dropout_calibration",
                      "known_weaknesses", "headline"}
    assert s["headline"]["skill"] == pytest.approx(0.3871, abs=1e-3)
    assert "GLORYS-holdout" in s["headline"]["do_not_quote"]
