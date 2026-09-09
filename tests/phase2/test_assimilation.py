"""Latent-space assimilation. Owner: Unit A (Arjhun).

Offline: a real TSCastNIO with random weights, no bundle and no checkpoint.

The failure this file exists to catch is the one the experiment is designed around. The shipped
model runs +0.1003 degC warm, so ANY correction fitted to a real float tends to cool the
prediction, and cooling improves the score everywhere. An experiment that only measured "error
fell at similar cells" would report a global bias correction as latent assimilation. The verdict
logic below is what stops that, so the verdict logic is tested harder than the optimiser is.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from phase2.reliability import assimilation as A
from phase2.tscast_nio import config as c2
from phase2.tscast_nio.models.tscast import TSCastNIO


def a_model(stage=1, decoder="simple", seed=0):
    torch.manual_seed(seed)
    m = TSCastNIO("cnn3d", 7, t_seq=1, p=c2.P, latent=c2.LATENT_DIM,
                  decoder=decoder, stage=stage)
    m.eval()
    return m


# ==================================================== decode is the model's own path

def test_decode_returns_mu_and_logvar_of_the_right_shape():
    m = a_model()
    h = torch.randn(4, c2.LATENT_DIM)
    mu, lv = A.decode(m, h)
    assert mu.shape == (4, c2.N_DEPTHS)
    assert lv.shape == (4, c2.N_DEPTHS)


def test_decode_matches_the_full_forward_pass_from_the_same_latent():
    """The load-bearing equivalence. If decode() is not the path the network actually takes, every
    correction measured through it describes a different model from the one being shipped."""
    m = a_model(seed=3)
    x = torch.randn(2, 7, 3, c2.P, c2.P)
    g = torch.randn(2, 3, 1, c2.P, c2.P)
    cp = torch.zeros(2, 12, c2.N_DEPTHS)
    mo = torch.zeros(2, dtype=torch.long)
    with torch.no_grad():
        want, _ = m(x, g, cp, mo)
        got, _ = A.decode(m, m.encoder(x, g))
    assert torch.allclose(got, want, atol=1e-6)


def test_decode_refuses_the_film_decoder_rather_than_guessing():
    """FiLM takes the climatology as its INPUT, so a latent correction there is a different
    operation. Silently treating the two as interchangeable would produce a number nobody could
    interpret."""
    m = a_model(decoder="film")
    with pytest.raises(NotImplementedError, match="simple"):
        A.decode(m, torch.randn(2, c2.LATENT_DIM))


# ==================================================== fitting the latent

def _fit_case(lam=0.01, steps=150, seed=5):
    m = a_model(seed=seed)
    torch.manual_seed(seed)
    h0 = torch.randn(1, c2.LATENT_DIM)
    y = torch.randn(1, c2.N_DEPTHS)
    mask = torch.ones(1, c2.N_DEPTHS, dtype=torch.bool)
    return m, A.fit_latent(m, h0, y, mask, lam=lam, steps=steps)


def test_fitting_reduces_the_in_sample_error():
    _m, r = _fit_case()
    assert r["in_sample_mse_after"] < r["in_sample_mse_before"]


def test_fitting_never_moves_a_single_weight():
    """The whole premise is a FROZEN network. If a weight moves this is fine-tuning, and the claim
    'no retraining' is false."""
    m = a_model(seed=11)
    before = {k: v.detach().clone() for k, v in m.state_dict().items()}
    torch.manual_seed(11)
    A.fit_latent(m, torch.randn(1, c2.LATENT_DIM), torch.randn(1, c2.N_DEPTHS),
                 torch.ones(1, c2.N_DEPTHS, dtype=torch.bool), lam=0.01, steps=50)
    for k, v in m.state_dict().items():
        assert torch.equal(v, before[k]), f"{k} moved during a frozen-network fit"


def test_a_stronger_ridge_moves_the_latent_less():
    """lambda is the only thing holding the fitted latent near the distribution the decoder was
    trained on. If this ordering ever breaks, the sweep in the experiment script is meaningless."""
    norms = []
    for lam in (10.0, 1.0, 0.1, 0.01):
        _m, r = _fit_case(lam=lam, steps=120)
        norms.append(float(r["delta"].norm()))
    assert norms == sorted(norms), f"|delta| must grow as lambda falls, got {norms}"


def test_masked_levels_do_not_pull_the_fit():
    """A float that never reached 1000 m must not be treated as having measured the mean there."""
    m = a_model(seed=7)
    torch.manual_seed(7)
    h0 = torch.randn(1, c2.LATENT_DIM)
    y = torch.zeros(1, c2.N_DEPTHS)
    y[0, -3:] = 50.0                                   # absurd values, all masked out
    mask = torch.ones(1, c2.N_DEPTHS, dtype=torch.bool)
    mask[0, -3:] = False
    with_junk = A.fit_latent(m, h0, y, mask, lam=0.01, steps=80)["h_star"]
    y2 = y.clone()
    y2[0, -3:] = -99.0                                 # different junk, same mask
    without = A.fit_latent(m, h0, y2, mask, lam=0.01, steps=80)["h_star"]
    assert torch.allclose(with_junk, without, atol=1e-6)


# ==================================================== similarity and propagation

def test_cosine_is_one_on_the_diagonal_and_symmetric():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(6, 12))
    S = A.cosine(X, X)
    assert np.allclose(np.diag(S), 1.0)
    assert np.allclose(S, S.T)


def test_cosine_ignores_magnitude():
    a = np.array([[1.0, 2.0, 3.0]])
    assert A.cosine(a, 7.5 * a)[0, 0] == pytest.approx(1.0)


def test_propagation_gives_nothing_below_the_threshold():
    """A state that is not this water mass must not be touched at all -- not touched a little."""
    h = np.zeros((3, 4))
    d = np.ones(4)
    out = A.propagate(h, d, np.array([0.95, 0.5, -0.2]), tau=0.9)
    assert np.allclose(out[1], 0.0)
    assert np.allclose(out[2], 0.0)
    assert np.all(out[0] > 0)


def test_propagation_weight_ramps_from_the_threshold_to_full_at_perfect_similarity():
    h = np.zeros((2, 3))
    d = np.ones(3)
    out = A.propagate(h, d, np.array([1.0, 0.95]), tau=0.9)
    assert np.allclose(out[0], 1.0), "identical states take the whole correction"
    assert np.allclose(out[1], 0.5), "halfway to the threshold takes half"


def test_unweighted_propagation_applies_the_full_correction():
    """The control populations get the identical correction, unweighted -- otherwise 'similar'
    would be compared against a SMALLER perturbation and would win for the wrong reason."""
    out = A.propagate(np.zeros((2, 3)), np.ones(3), np.array([0.1, 0.2]),
                      tau=-1.0, weighted=False)
    assert np.allclose(out, 1.0)


# ==================================================== the verdict, which is the real product

def test_a_pure_bias_correction_is_named_as_one():
    """Every population improving by the same amount is exactly what a global bias fix looks like.
    Reporting the first number alone would call it assimilation."""
    got = A.summarise(mae_before=0.50, mae_similar=0.45,
                      mae_dissimilar=0.45, mae_shuffled=0.45, n=100)
    assert got["supported"] is False
    assert "BIAS CORRECTION" in got["verdict"]


def test_a_state_specific_gain_is_supported():
    got = A.summarise(mae_before=0.50, mae_similar=0.40,
                      mae_dissimilar=0.55, mae_shuffled=0.52, n=100)
    assert got["supported"] is True
    assert got["verdict"].startswith("SUPPORTED")


def test_no_gain_at_similar_states_is_not_dressed_up():
    got = A.summarise(mae_before=0.50, mae_similar=0.51,
                      mae_dissimilar=0.60, mae_shuffled=0.58, n=100)
    assert got["supported"] is False
    assert "NO IMPROVEMENT" in got["verdict"]


def test_a_gain_mostly_available_to_unrelated_states_is_called_weak():
    got = A.summarise(mae_before=0.50, mae_similar=0.40,
                      mae_dissimilar=0.41, mae_shuffled=0.42, n=100)
    assert got["supported"] is False
    assert "WEAK" in got["verdict"]


def test_the_margin_is_measured_against_the_BEST_control_not_the_worst():
    """Taking the worse control would let a badly-behaved dissimilar group manufacture a margin --
    which is exactly how the experiment script's first headline picked the wrong lambda."""
    got = A.summarise(mae_before=0.50, mae_similar=0.40,
                      mae_dissimilar=0.90, mae_shuffled=0.41, n=100)
    assert got["margin"] == pytest.approx(0.10 - 0.09)
