"""TS-Cast-NIO stage-1 model tests.

The one that matters most is test_nll_is_minimised_at_the_true_variance. It is the whole reason
this model exists: MC-dropout was measured 1.6-3.5x overconfident, and the fix is only a fix if
the loss actually drives sigma to the real error.
"""
import warnings

import numpy as np
import pytest
import torch

warnings.filterwarnings("ignore", message=".*enable_nested_tensor.*")

from phase2.tscast_nio import config
from phase2.tscast_nio.models import (TSCastNIO, depth_interp_matrix, gaussian_nll)

C, P, DEP = 5, config.P, config.N_DEPTHS


def _model(**kw):
    kw.setdefault("t_seq", 1)
    kw.setdefault("p", P)
    kw.setdefault("latent", 64)
    return TSCastNIO("cnn3d", C, **kw)


def _inputs(b=3):
    return (torch.randn(b, C, 1, P, P), torch.randn(b, 3, 1, P, P),
            torch.randn(b, 12, DEP), torch.randint(0, 12, (b,)))


# ---------------------------------------------------------------- the loss

def test_nll_matches_equation_3_by_hand():
    y = torch.tensor([[2.0]])
    mu = torch.tensor([[0.0]])
    logvar = torch.tensor([[np.log(4.0)]])
    mask = torch.ones(1, 1, dtype=torch.bool)
    # 0.5 * exp(-log 4) * (2-0)^2 + 0.5 * log 4 = 0.5*0.25*4 + 0.5*1.3863 = 0.5 + 0.6931
    assert float(gaussian_nll(mu, logvar, y, mask)) == pytest.approx(1.1931, abs=1e-3)


def test_nll_is_minimised_at_the_true_variance():
    """The point of the whole model. If the loss did not bottom out at the real error, the
    predicted sigma would be decorative and we would have replaced one miscalibrated uncertainty
    with another."""
    err = 1.7
    y = torch.full((512, 1), err)
    mu = torch.zeros(512, 1)
    mask = torch.ones(512, 1, dtype=torch.bool)
    grid = np.linspace(np.log(err ** 2) - 3, np.log(err ** 2) + 3, 121)
    losses = [float(gaussian_nll(mu, torch.full((512, 1), float(lv)), y, mask)) for lv in grid]
    best = grid[int(np.argmin(losses))]
    assert best == pytest.approx(np.log(err ** 2), abs=0.06), (
        f"NLL minimised at logvar={best:.3f}, true log(err^2)={np.log(err**2):.3f}")


def test_nll_punishes_inflating_the_variance_to_escape_the_penalty():
    """The +0.5*logvar term. Without it a network trivially predicts huge sigma and pays nothing."""
    y, mu = torch.zeros(64, 1), torch.zeros(64, 1)
    mask = torch.ones(64, 1, dtype=torch.bool)
    small = float(gaussian_nll(mu, torch.full((64, 1), -2.0), y, mask))
    huge = float(gaussian_nll(mu, torch.full((64, 1), 6.0), y, mask))
    assert huge > small, "inflating the variance was not penalised"


def test_masked_levels_contribute_nothing():
    """~24% of cells are below the sea floor. A masked level must contribute nothing, not zero."""
    y = torch.zeros(1, 4)
    mu = torch.tensor([[0.0, 0.0, 1000.0, 0.0]])       # a wild value at a masked level
    logvar = torch.zeros(1, 4)
    m_all = torch.tensor([[True, True, False, True]])
    m_ref = torch.tensor([[True, True, True, True]])
    bad = gaussian_nll(mu, logvar, y, m_ref)
    good = gaussian_nll(mu, logvar, y, m_all)
    assert float(good) < float(bad) / 100, "a masked level leaked into the loss"


# ------------------------------------------------------- depth resampling

def test_interp_matrix_rows_sum_to_one():
    M = depth_interp_matrix(config.DEPTHS, np.linspace(0, 1000, config.INTERNAL_LEVELS))
    assert np.allclose(M.sum(axis=1), 1.0), "interpolation weights must be a partition of unity"


def test_interp_matrix_is_identity_when_grids_match():
    M = depth_interp_matrix(config.DEPTHS, config.DEPTHS)
    assert np.allclose(M, np.eye(config.N_DEPTHS))


def test_15_to_64_to_15_round_trip_preserves_a_realistic_profile():
    """If the internal grid mangled the profile, every depth would be biased before the network
    even ran."""
    d = np.array(config.DEPTHS, dtype="float64")
    prof = 28.0 - 24.0 * (1 - np.exp(-d / 250.0))          # warm surface, cold deep
    internal = np.linspace(0, 1000, config.INTERNAL_LEVELS)
    up = depth_interp_matrix(config.DEPTHS, internal)
    down = depth_interp_matrix(internal, config.DEPTHS)
    back = down @ (up @ prof)
    assert np.max(np.abs(back - prof)) < 0.15, f"round trip error {np.max(np.abs(back - prof)):.3f}"


# ------------------------------------------------------------- the model

def test_output_is_the_15_contract_depths():
    m = _model()
    mu, logvar = m(*_inputs())
    assert mu.shape == (3, DEP) and logvar.shape == (3, DEP)


def test_film_starts_near_identity_so_training_begins_at_the_prior():
    """FiLM must start ~identity so an untrained model sits on the climatology rather than on
    noise -- but NOT at exact zero, which would cut the gradient to the encoder entirely. See
    test_gradients_reach_the_encoder for the other half of that trade."""
    m = _model()
    film = m.decoder.down_films[0]
    h = torch.randn(2, 64)
    x = torch.randn(2, film.c, 8)
    out = film(x, h)
    rel = float(((out - x).abs().max() / x.abs().max()).detach())
    assert rel < 0.05, f"FiLM started {rel:.3f} away from identity; training will not begin at the prior"


def test_film_actually_conditions_on_the_satellite_latent():
    """After a weight nudge, a different latent must change the profile -- otherwise the encoder
    is decorative and the model is just a climatology lookup."""
    m = _model()
    torch.nn.init.normal_(m.decoder.down_films[0].out.weight, std=0.1)
    x = torch.randn(2, m.decoder.down_films[0].c, 8)
    a = m.decoder.down_films[0](x, torch.zeros(2, 64))
    b = m.decoder.down_films[0](x, torch.ones(2, 64) * 3)
    assert not torch.allclose(a, b), "FiLM ignored the latent"


def test_residual_mode_anchors_the_output_on_the_requested_month():
    """residual=True means the model ADJUSTS the average. Changing which month is requested must
    therefore move the output, because a different month is a different prior."""
    m = _model(residual=True).eval()
    x, g, clim, _ = _inputs(b=1)
    clim = torch.randn(1, 12, DEP) * 5.0
    with torch.no_grad():
        a = m(x, g, clim, torch.tensor([0]))[0]
        b = m(x, g, clim, torch.tensor([6]))[0]
    assert not torch.allclose(a, b), "the month index did not select a prior"
    assert torch.allclose(a - clim[:, 0, :], b - clim[:, 6, :], atol=1e-5), \
        "the correction should be month-independent; only the prior it is added to changes"


def test_non_residual_mode_ignores_the_month_prior():
    m = _model(residual=False).eval()
    x, g, clim, _ = _inputs(b=1)
    with torch.no_grad():
        a = m(x, g, clim, torch.tensor([0]))[0]
        b = m(x, g, clim, torch.tensor([6]))[0]
    assert torch.allclose(a, b), "non-residual output must not depend on the month index"


def test_logvar_is_clamped_so_sigma_cannot_explode_or_collapse():
    m = _model()
    x, g, clim, mo = _inputs()
    _, logvar = m(x, g, clim * 1e4, mo)
    from phase2.tscast_nio.models.tscast import LOGVAR_MAX, LOGVAR_MIN
    lo, hi = float(logvar.detach().min()), float(logvar.detach().max())
    assert lo >= LOGVAR_MIN and hi <= LOGVAR_MAX


def test_model_survives_the_t_seq_flip():
    m = TSCastNIO("cnn3d", C, t_seq=31, p=P, latent=64)
    mu, _ = m(torch.randn(2, C, 31, P, P), torch.randn(2, 3, 1, P, P),
              torch.randn(2, 12, DEP), torch.randint(0, 12, (2,)))
    assert mu.shape == (2, DEP)


def test_gradients_reach_the_encoder():
    """If they did not, the satellite embedding would be untrained decoration."""
    m = _model()
    mu, logvar = m(*_inputs())
    gaussian_nll(mu, logvar, torch.randn(3, DEP), torch.ones(3, DEP, dtype=torch.bool)).backward()
    grads = [p.grad for p in m.encoder.parameters() if p.grad is not None]
    assert grads and any(float(g.abs().sum()) > 0 for g in grads), "no gradient reached the encoder"


def test_beta_nll_at_zero_is_exactly_the_papers_equation_3():
    y, mu, lv = torch.tensor([[2.0]]), torch.tensor([[0.0]]), torch.tensor([[np.log(4.0)]])
    mask = torch.ones(1, 1, dtype=torch.bool)
    assert float(gaussian_nll(mu, lv, y, mask, beta=0.0)) == pytest.approx(1.1931, abs=1e-3)


def test_beta_nll_at_one_gives_exactly_the_mse_gradient_for_the_mean():
    """The defining property. beta=1 cancels the 1/sigma^2 weighting on the squared-error term, so
    the mean trains as if under MSE while the variance head still learns."""
    y = torch.tensor([[2.0]])
    lv = torch.full((1, 1), 1.5)
    mask = torch.ones(1, 1, dtype=torch.bool)

    mu = torch.zeros(1, 1, requires_grad=True)
    gaussian_nll(mu, lv, y, mask, beta=1.0).backward()
    g_beta = mu.grad.clone()

    mu2 = torch.zeros(1, 1, requires_grad=True)
    (0.5 * (y - mu2) ** 2).mean().backward()
    assert torch.allclose(g_beta, mu2.grad)


def test_beta_weight_is_detached_so_it_cannot_become_a_second_route_to_game_sigma():
    """If the sigma^(2beta) weight carried gradient, the model could still shrink sigma to cut the
    loss -- reintroducing the exact failure beta-NLL exists to prevent."""
    y = torch.tensor([[2.0]])
    mask = torch.ones(1, 1, dtype=torch.bool)
    lv = torch.zeros(1, 1, requires_grad=True)
    gaussian_nll(torch.zeros(1, 1), lv, y, mask, beta=1.0).backward()
    g_with = lv.grad.clone()

    # the same loss with the weight treated as a plain constant must give the identical gradient
    lv2 = torch.zeros(1, 1, requires_grad=True)
    w = float(torch.exp(torch.zeros(1, 1)) ** 1.0)
    per = 0.5 * torch.exp(-lv2) * (y - 0.0) ** 2 + 0.5 * lv2
    (per * w).mean().backward()
    assert torch.allclose(g_with, lv2.grad), "the beta weight is leaking gradient into logvar"


def test_higher_beta_removes_the_reward_for_collapsing_sigma_on_well_fit_points():
    """Encodes the measured failure precisely.

    The variance collapse only pays off where the model ALREADY fits well: with a large residual,
    shrinking sigma makes NLL worse, not better. So this uses a near-zero residual -- a training
    point the network has learned -- which is where the loss can be driven down without bound by
    sigma alone. beta must remove almost all of that reward.
    """
    y, mu = torch.tensor([[0.01]]), torch.tensor([[0.0]])
    mask = torch.ones(1, 1, dtype=torch.bool)
    wide, collapsed = torch.zeros(1, 1), torch.full((1, 1), -6.0)

    reward_0 = (float(gaussian_nll(mu, wide, y, mask, beta=0.0))
                - float(gaussian_nll(mu, collapsed, y, mask, beta=0.0)))
    reward_1 = (float(gaussian_nll(mu, wide, y, mask, beta=1.0))
                - float(gaussian_nll(mu, collapsed, y, mask, beta=1.0)))

    assert reward_0 > 2.0, "beta=0 should hand out a large free loss reduction - the pathology"
    assert reward_1 < 0.05, "beta=1 must remove essentially all of it"
    assert reward_0 > 100 * reward_1


def test_a_large_residual_does_not_reward_shrinking_sigma_even_at_beta_zero():
    """The other half of the mechanism, and the reason the collapse is a TRAIN-set failure that a
    held-out score exposes: where the model is wrong, plain NLL already punishes a narrow sigma."""
    y, mu = torch.tensor([[1.0]]), torch.tensor([[0.0]])
    mask = torch.ones(1, 1, dtype=torch.bool)
    wide = float(gaussian_nll(mu, torch.zeros(1, 1), y, mask, beta=0.0))
    collapsed = float(gaussian_nll(mu, torch.full((1, 1), -6.0), y, mask, beta=0.0))
    assert collapsed > wide
