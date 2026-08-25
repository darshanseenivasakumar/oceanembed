"""Unit A model tests: forward-pass shapes, checkpoint round-trip, dropout behaviour.

OWNER: Unit A (Arjhun).

The dropout test matters beyond hygiene: Day-4 MC-dropout uncertainty requires dropout to
stay ACTIVE in train() mode. If someone "helpfully" swaps it for something inference-only,
uncertainty silently collapses to zero and we would report fake confidence.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from oceanembed import config
from oceanembed.models.mlp_profile import MLPProfile, load_mlp, predict_mlp


@pytest.fixture
def model() -> MLPProfile:
    torch.manual_seed(config.SEED)
    return MLPProfile()


def test_config_is_self_consistent():
    config.sanity_check()


def test_forward_pass_shape(model):
    x = torch.randn(7, config.N_FEAT)
    out = model(x)
    assert out.shape == (7, config.N_DEPTHS)
    assert out.dtype == torch.float32


def test_forward_rejects_wrong_feature_count(model):
    with pytest.raises(RuntimeError):
        model(torch.randn(4, config.N_FEAT + 1))


def test_predict_mlp_shape_and_dtype(model):
    out = predict_mlp(model, np.random.randn(13, config.N_FEAT).astype("float32"))
    assert out.shape == (13, config.N_DEPTHS)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()


def test_predict_mlp_rejects_bad_shape(model):
    with pytest.raises(AssertionError):
        predict_mlp(model, np.random.randn(5, config.N_FEAT + 2).astype("float32"))


def test_predict_mlp_warns_on_raw_units(model):
    """Raw SST (~28 degC) must not be mistaken for z-scored input silently."""
    raw = np.full((6, config.N_FEAT), 28.0, dtype="float32")
    with pytest.warns(RuntimeWarning, match="RAW units"):
        predict_mlp(model, raw)


def test_dropout_active_in_train_inactive_in_eval(model):
    """MC-dropout (Day 4) depends on this exact behaviour."""
    x = torch.randn(32, config.N_FEAT)

    model.eval()
    with torch.no_grad():
        a, b = model(x), model(x)
    assert torch.allclose(a, b), "eval() must be deterministic"

    model.train()
    with torch.no_grad():
        c, d = model(x), model(x)
    assert not torch.allclose(c, d), "train() must keep dropout stochastic for MC-dropout"


def test_norm_stats_roundtrip_through_checkpoint(tmp_path, model):
    """The checkpoint must carry normalization -- see docs/DECISIONS.md."""
    rng = np.random.default_rng(config.SEED)
    fm = rng.normal(size=config.N_FEAT).astype("float32")
    fs = np.abs(rng.normal(size=config.N_FEAT)).astype("float32") + 0.5
    tm = rng.normal(size=config.N_DEPTHS).astype("float32")
    ts = np.abs(rng.normal(size=config.N_DEPTHS)).astype("float32") + 0.5
    model.set_norm_stats(fm, fs, tm, ts)

    path = tmp_path / "mlp_model.pt"
    torch.save(model.state_dict(), path)
    reloaded = load_mlp(str(path))

    assert np.allclose(reloaded.targ_mean.numpy(), tm, atol=1e-6)
    assert np.allclose(reloaded.targ_std.numpy(), ts, atol=1e-6)
    assert np.allclose(reloaded.feat_mean.numpy(), fm, atol=1e-6)

    x = np.random.randn(9, config.N_FEAT).astype("float32")
    assert np.allclose(predict_mlp(model, x), predict_mlp(reloaded, x), atol=1e-5)


def test_set_norm_stats_clamps_zero_std(model):
    """A constant feature has std 0; dividing by it would produce inf."""
    model.set_norm_stats(
        np.zeros(config.N_FEAT), np.zeros(config.N_FEAT),
        np.zeros(config.N_DEPTHS), np.zeros(config.N_DEPTHS),
    )
    assert (model.feat_std > 0).all()
    assert (model.targ_std > 0).all()


def test_denormalize_inverts_zscore(model):
    tm = np.linspace(28.0, 8.0, config.N_DEPTHS).astype("float32")
    ts = np.full(config.N_DEPTHS, 2.0, dtype="float32")
    model.set_norm_stats(
        np.zeros(config.N_FEAT), np.ones(config.N_FEAT), tm, ts
    )
    z = torch.zeros(3, config.N_DEPTHS)
    assert np.allclose(model.denormalize(z).numpy(), tm, atol=1e-5)


def test_fixtures_match_the_frozen_contract():
    """Guards against a fixture regeneration silently changing shapes under us."""
    X = np.load(config.art("sample_X.npy"))
    y = np.load(config.art("sample_y.npy"))
    assert X.shape[1] == config.N_FEAT, f"sample_X has {X.shape[1]} cols"
    assert y.shape[1] == config.N_DEPTHS, f"sample_y has {y.shape[1]} cols"
    assert len(X) == len(y)
    assert X.dtype == np.float32 and y.dtype == np.float32
