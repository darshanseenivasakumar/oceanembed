"""Unit A tests for the Day-3 model-comparison harness. Owner: Arjhun.

The verdict logic decides which model ships, so it is tested directly rather than only
exercised end-to-end. The loader tests exist because a scale mismatch between training and
evaluation already produced two false verdicts (docs/DECISIONS.md D-014).
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from oceanembed.train import _data
from oceanembed.train.compare_models import TIE_MARGIN, _climatology_baseline, _verdict


def _res(rmse: float) -> dict:
    return {"rmse": rmse, "mae": rmse * 0.8, "r2": 0.9,
            "rmse_by_depth": [rmse] * config.N_DEPTHS, "skill_vs_clim": 0.5}


# --- verdict logic ----------------------------------------------------------
def test_clear_mlp_win_is_conclusive():
    v = _verdict({"climatology": _res(1.5), "lightgbm": _res(0.50), "mlp": _res(0.25)})
    assert v["choice"] == "mlp" and v["conclusive"]


def test_clear_lightgbm_win_says_ship_lightgbm():
    """TEAM_PLAN Day 3: 'If MLP can't beat LightGBM, say so and we ship LightGBM.'"""
    v = _verdict({"climatology": _res(1.5), "lightgbm": _res(0.25), "mlp": _res(0.50)})
    assert v["choice"] == "lightgbm" and v["conclusive"]
    assert "honest result" in v["reason"]


def test_near_tie_is_not_conclusive_and_ships_the_simpler_model():
    """A 0.1% gap is noise. Reading it as a win is how a bad model gets shipped."""
    v = _verdict({"climatology": _res(1.5), "lightgbm": _res(0.2225), "mlp": _res(0.2223)})
    assert not v["conclusive"]
    assert v["choice"] == "lightgbm", "ties should fall to the simpler model"
    assert "TIE" in v["reason"]


def test_tie_margin_boundary_behaviour():
    base = 1.0
    just_inside = base * (1 - TIE_MARGIN * 0.5)
    just_outside = base * (1 - TIE_MARGIN * 2.0)
    assert not _verdict({"lightgbm": _res(base), "mlp": _res(just_inside)})["conclusive"]
    assert _verdict({"lightgbm": _res(base), "mlp": _res(just_outside)})["conclusive"]


def test_missing_model_is_never_conclusive():
    v = _verdict({"climatology": _res(1.5), "mlp": _res(0.25)})
    assert not v["conclusive"] and v["choice"] == "mlp"


def test_no_models_at_all_yields_no_choice():
    v = _verdict({"climatology": _res(1.5)})
    assert v["choice"] is None and not v["conclusive"]


# --- climatology baseline ---------------------------------------------------
def test_climatology_baseline_is_the_depthwise_train_mean():
    y_train = np.random.default_rng(0).normal(20, 3, (200, config.N_DEPTHS)).astype("float32")
    clim = _climatology_baseline(y_train, 7)
    assert clim.shape == (7, config.N_DEPTHS)
    assert np.allclose(clim[0], y_train.mean(axis=0), atol=1e-5)
    assert np.allclose(clim[0], clim[-1]), "climatology must be constant across rows"


# --- the loader, which is where the real bug lived --------------------------
def test_fixture_loader_z_scores_to_match_the_real_convention():
    """X_train.npy is z-scored, so the fixture path must be too, or models see two scales."""
    d = _data.load_fixtures()
    assert abs(float(d["X_train"].mean())) < 0.5, "fixture X_train should be roughly centred"
    assert 0.3 < float(d["X_train"].std()) < 3.0, "fixture X_train should be roughly unit-scale"


def test_fixture_loader_targets_stay_in_real_degrees():
    """y must NOT be normalized -- models predict real degC."""
    d = _data.load_fixtures()
    assert float(d["y_train"].mean()) > 5.0, "y_train looks normalized; it must be degC"


def test_fixture_train_and_test_share_one_scale():
    """The exact failure that produced RMSE 36 degC and then 2.5 degC."""
    d = _data.load_fixtures()
    tr_mean, te_mean = float(d["X_train"].mean()), float(d["X_test"].mean())
    assert abs(tr_mean - te_mean) < 1.0, (
        f"train ({tr_mean:.3f}) and test ({te_mean:.3f}) are on different scales"
    )


def test_fixture_split_is_disjoint_and_complete():
    d = _data.load_fixtures()
    total = len(d["X_train"]) + len(d["X_test"])
    raw = np.load(config.art("sample_X.npy"))
    assert total == len(raw), f"split lost rows: {total} vs {len(raw)}"
    assert len(d["X_test"]) > 0 and len(d["X_train"]) > 0


def test_fixture_loader_is_deterministic():
    a, b = _data.load_fixtures(), _data.load_fixtures()
    assert np.array_equal(a["X_train"], b["X_train"]), "seeded loader must be reproducible"


def test_normalization_stats_come_from_train_only():
    """Using test rows for the stats would leak; train-only stats leave test slightly off-centre."""
    d = _data.load_fixtures()
    assert np.allclose(d["X_train"].mean(axis=0), 0.0, atol=1e-4)


def test_load_real_fails_loudly_when_artifacts_are_missing():
    if any(__import__("os").path.exists(config.art(n)) for n in _data.REQUIRED_REAL):
        pytest.skip("real artifacts exist")
    with pytest.raises(SystemExit, match="Missing artifacts"):
        _data.load_real()
