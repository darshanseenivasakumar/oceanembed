"""Unit A model tests: forward-pass shapes, checkpoint round-trip, dropout behaviour.

OWNER: Unit A (Arjhun).

Self-contained BY DESIGN: nothing here depends on artifacts/ existing. A fresh clone cannot
run scripts/prepare_dataset.py today (see docs/HANDOFF.md), so tests that needed real
artifacts would just be skipped everywhere and prove nothing.

The dropout test matters beyond hygiene: Day-4 MC-dropout requires dropout to stay ACTIVE in
train() mode. If it is ever swapped for something inference-only, uncertainty silently collapses
to zero and we would report fabricated confidence.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from oceanembed import config
from oceanembed.models import mlp_profile as mp
from oceanembed.models.mlp_profile import MLPProfile, load_mlp, predict_mlp


@pytest.fixture
def model() -> MLPProfile:
    torch.manual_seed(config.SEED)
    return MLPProfile()


@pytest.fixture
def norm_stats(tmp_path, monkeypatch):
    """Provide norm_stats.json without touching Unit B's real artifact."""
    tm = np.linspace(28.0, 9.0, config.N_DEPTHS).astype("float32")
    ts = np.full(config.N_DEPTHS, 2.0, dtype="float32")
    path = tmp_path / "norm_stats.json"
    path.write_text(json.dumps({
        "feat_mean": np.zeros(config.N_FEAT).tolist(),
        "feat_std": np.ones(config.N_FEAT).tolist(),
        "targ_mean": tm.tolist(),
        "targ_std": ts.tolist(),
    }), encoding="utf-8")
    monkeypatch.setattr(mp, "_targ_stats", lambda: (tm, ts))
    return tm, ts


# --- config -----------------------------------------------------------------
def test_config_is_self_consistent():
    config.sanity_check()


# --- forward pass -----------------------------------------------------------
def test_forward_pass_shape(model):
    out = model(torch.randn(7, config.N_FEAT))
    assert out.shape == (7, config.N_DEPTHS)
    assert out.dtype == torch.float32


def test_forward_rejects_wrong_feature_count(model):
    with pytest.raises(RuntimeError):
        model(torch.randn(4, config.N_FEAT + 1))


def test_architecture_matches_the_contract(model):
    """11 -> 128 -> 128 -> 11 with dropout, per docs/MODEL_SPEC.md and config.MLP."""
    linears = [m for m in model.net if isinstance(m, torch.nn.Linear)]
    dropouts = [m for m in model.net if isinstance(m, torch.nn.Dropout)]
    widths = [linears[0].in_features] + [lin.out_features for lin in linears]
    assert widths == [config.N_FEAT, *config.MLP["hidden"], config.N_DEPTHS], widths
    assert dropouts and all(d.p == config.MLP["dropout"] for d in dropouts)


# --- dropout / MC-dropout precondition --------------------------------------
def test_dropout_active_in_train_inactive_in_eval(model):
    x = torch.randn(64, config.N_FEAT)

    model.eval()
    with torch.no_grad():
        a, b = model(x), model(x)
    assert torch.allclose(a, b), "eval() must be deterministic"

    model.train()
    with torch.no_grad():
        c, d = model(x), model(x)
    assert not torch.allclose(c, d), "train() must stay stochastic or MC-dropout returns zero uncertainty"


# --- predict_mlp ------------------------------------------------------------
def test_predict_mlp_shape_and_dtype(model, norm_stats):
    out = predict_mlp(model, np.random.randn(13, config.N_FEAT).astype("float32"))
    assert out.shape == (13, config.N_DEPTHS)
    assert out.dtype == np.float32 and np.isfinite(out).all()


def test_predict_mlp_rejects_bad_shape(model, norm_stats):
    with pytest.raises(AssertionError):
        predict_mlp(model, np.random.randn(5, config.N_FEAT + 2).astype("float32"))


def test_predict_mlp_returns_real_degrees_not_normalized(model, norm_stats):
    """The contract is 'z-scored in, REAL degC out'. Normalized output would sit near 0."""
    out = predict_mlp(model, np.zeros((8, config.N_FEAT), dtype="float32"))
    tm, _ = norm_stats
    assert out.mean() > 5.0, f"output mean {out.mean():.2f} looks normalized, not degC"
    # An untrained net outputs ~0 in normalized space, so predictions ~= targ_mean.
    assert np.allclose(out.mean(axis=0), tm, atol=3.0)


def test_predict_mlp_leaves_model_in_eval(model, norm_stats):
    """predict_mlp calls model.eval(); MC-dropout must re-enable train() itself."""
    model.train()
    predict_mlp(model, np.random.randn(4, config.N_FEAT).astype("float32"))
    assert not model.training


# --- checkpoint -------------------------------------------------------------
def test_checkpoint_save_load_round_trip(tmp_path, model, norm_stats):
    path = tmp_path / "mlp_model.pt"
    torch.save(model.state_dict(), path)
    reloaded = load_mlp(str(path))

    x = np.random.randn(9, config.N_FEAT).astype("float32")
    assert np.allclose(predict_mlp(model, x), predict_mlp(reloaded, x), atol=1e-5)


def test_loaded_checkpoint_is_in_eval_mode(tmp_path, model):
    path = tmp_path / "mlp_model.pt"
    torch.save(model.state_dict(), path)
    assert not load_mlp(str(path)).training, "load_mlp must return an eval-mode model"


# --- documented dependency --------------------------------------------------
def test_predict_mlp_requires_norm_stats(model, monkeypatch):
    """Documents a real coupling: predict_mlp is unusable until Unit B ships norm_stats.json.

    On a fresh clone that file does not exist, so this raises FileNotFoundError. Recorded as a
    test rather than a surprise -- see docs/HANDOFF.md.
    """
    def _boom():
        raise FileNotFoundError("norm_stats.json")
    monkeypatch.setattr(mp, "_targ_stats", _boom)
    with pytest.raises(FileNotFoundError):
        predict_mlp(model, np.zeros((2, config.N_FEAT), dtype="float32"))
