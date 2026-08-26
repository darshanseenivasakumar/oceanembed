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


def test_lightgbm_baseline_is_refused_when_its_provenance_cannot_be_verified():
    """The spec asked for LightGBM beside climatology. It cannot be shown honestly here.

    [VERIFIED] the local checkpoint is a bare list of boosters with no provenance stamp, it was
    excluded from the data bundle as regenerable, and the local X_train.npy row count contradicts
    provenance.json. Showing its score would be a fabricated baseline. The module must REFUSE,
    and say why, rather than quietly omitting the column.
    """
    b = lab.baseline_availability()
    assert b["climatology"]["available"] is True
    assert b["lightgbm"]["available"] is False
    assert "NOT SHOWN" in b["lightgbm"]["why"]
    assert b["lightgbm"]["local_x_train_rows"] != b["lightgbm"]["provenance_n_train"]
    assert b["lightgbm"]["how_to_unblock"]


# ---------------------------------------------------------------------------------------------
# reliability: the D-016 correction
# ---------------------------------------------------------------------------------------------
def test_mc_dropout_is_overconfident_at_every_depth():
    cal = lab.mc_dropout_calibration(n_rows=2000)
    if not cal["available"]:
        pytest.skip(cal["why"])
    assert cal["overconfident_everywhere"] is True
    assert cal["worst_factor"] > 5.0, "the worst case should be severe, not marginal"
    assert cal["best_factor"] > 1.0, "even the best depth is still overconfident"


def test_the_mixed_layer_is_worse_than_depth_correcting_d016():
    """D-016 concluded 'overconfident at depth' from FIXTURES. On real data that inverts.

    This is the assertion that keeps the panel pointing at the right band. If it ever fails,
    either the model changed or D-016's original framing was right after all -- and a human
    must look, rather than the panel quietly reverting to the old warning.
    """
    cal = lab.mc_dropout_calibration(n_rows=2000)
    if not cal["available"]:
        pytest.skip(cal["why"])
    assert cal["worse_in_mixed_layer_than_at_depth"] is True, (
        f"mixed layer {cal['mixed_layer_range']} vs deep {cal['deep_range']}"
    )
    assert 20.0 <= cal["worst_depth_m"] <= 50.0, \
        f"worst calibration should be in the mixed layer, got {cal['worst_depth_m']} m"
    assert cal["best_depth_m"] >= 500.0, \
        f"best calibration should be deep, got {cal['best_depth_m']} m"


def test_a_thin_sample_depth_cannot_set_the_headline():
    """Depth 0 rests on 12 Argo profiles. It must not be reported as the worst depth."""
    cal = lab.mc_dropout_calibration(n_rows=2000)
    if not cal["available"]:
        pytest.skip(cal["why"])
    assert cal["n_obs"][0] < lab.MIN_OBS_FOR_HEADLINE
    assert cal["worst_depth_m"] != 0.0 and cal["best_depth_m"] != 0.0


def test_the_stated_weakness_names_the_mixed_layer_not_the_thermocline():
    """The panel text itself, not just the numbers behind it."""
    w = [x for x in lab.known_weaknesses() if "MC-dropout" in x["what"]]
    assert len(w) == 1
    text = w[0]["what"] + " " + w[0]["detail"]
    assert "MIXED LAYER" in w[0]["what"]
    assert "20-50 m" in text
    assert "1.8x to 8.5x" in text
    assert "UPDATE 2026-08-26" in w[0]["evidence"], "must point at the corrected D-016"


def test_calibration_degrades_gracefully_when_the_model_is_missing(monkeypatch):
    """A missing checkpoint must yield available=False with a reason, never a traceback."""
    monkeypatch.setattr(lab, "ARGO_ERROR", os.path.join(config.ARTIFACTS, "nope.json"))
    cal = lab.mc_dropout_calibration(n_rows=50)
    assert cal["available"] is False and cal["why"]


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
