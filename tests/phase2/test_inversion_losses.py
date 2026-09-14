"""New training losses for the inversion ladder (E-INV-00 legs L2, L3).

torch-only, no data, no model build. Verifies the depth-capped gradient loss and the sign hinge
against hand-computed values on tiny tensors.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from phase2.tscast_nio.models import tscast as M
from oceanembed import config

DEPTHS = torch.tensor(np.asarray(config.DEPTHS, dtype="float64"), dtype=torch.float32)
# per-depth normalisation stats (arbitrary but distinct, to prove de-normalisation happens)
Y_MEAN = torch.linspace(28.0, 4.0, config.N_DEPTHS)
Y_STD = torch.linspace(1.0, 0.2, config.N_DEPTHS)


def _z(t_degc):
    return (t_degc - Y_MEAN) / Y_STD


def test_gradient_loss_uncapped_matches_the_existing_behaviour():
    truth = torch.linspace(29.0, 5.0, config.N_DEPTHS)
    pred = truth.clone()
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    loss = M.gradient_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS)
    assert float(loss) == pytest.approx(0.0, abs=1e-6)


def test_gradient_cap_ignores_deep_level_pairs():
    # A perfect top, a deliberately wrong gradient only in the deep pairs (below 100 m).
    truth = torch.linspace(29.0, 5.0, config.N_DEPTHS)
    pred = truth.clone()
    pred[-1] = pred[-1] + 10.0                      # wreck only the 700->1000 m pair
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    full = M.gradient_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS)
    capped = M.gradient_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS,
                             max_depth_m=100.0)
    assert float(full) > 0.0
    assert float(capped) == pytest.approx(0.0, abs=1e-6)   # the broken pair is below the cap


def test_sign_loss_is_zero_when_the_prediction_has_the_right_sign_everywhere():
    truth = torch.tensor([26.0, 26.0, 26.0, 26.4, 26.8, 27.2, 26.0, 24.0, 22.0, 20.0,
                          18.0, 14.0, 10.0, 7.0, 4.0])            # inversion 10->50 m
    pred = truth.clone()
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    loss = M.sign_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS)
    assert float(loss) == pytest.approx(0.0, abs=1e-6)


def test_sign_loss_penalises_predicting_cooling_where_truth_warms_downward():
    truth = torch.tensor([26.0, 26.0, 26.0, 26.4, 26.8, 27.2, 26.0, 24.0, 22.0, 20.0,
                          18.0, 14.0, 10.0, 7.0, 4.0])
    pred = torch.linspace(29.0, 5.0, config.N_DEPTHS)            # monotone cooling: misses the inversion
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    loss = M.sign_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS)
    assert float(loss) > 0.0


def test_sign_loss_ignores_flat_truth_gradients_below_the_min_step():
    # truth almost flat in the top 100 m (no real gradient to get the sign of); pred wiggles
    truth = torch.full((config.N_DEPTHS,), 26.0)
    truth[10:] = torch.linspace(25.5, 4.0, config.N_DEPTHS - 10)
    pred = truth.clone(); pred[1] += 0.05; pred[2] -= 0.05        # sub-min_step noise up top
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    loss = M.sign_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS,
                       min_step=0.2)
    assert float(loss) == pytest.approx(0.0, abs=1e-6)


def test_sign_loss_only_looks_above_the_depth_cap():
    truth = torch.linspace(29.0, 5.0, config.N_DEPTHS)
    truth[12] = truth[11] + 2.0                                   # a deep inversion at 500 m
    pred = torch.linspace(29.0, 5.0, config.N_DEPTHS)             # monotone: wrong sign at 500 m
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    loss = M.sign_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS,
                       max_depth_m=100.0)
    assert float(loss) == pytest.approx(0.0, abs=1e-6)            # the deep inversion is below the cap


def test_sign_loss_skips_level_pairs_that_cross_the_seafloor():
    truth = torch.tensor([26.0, 26.0, 26.0, 26.4, 26.8, 27.2, 26.0, 24.0, 22.0, 20.0,
                          18.0, 14.0, 10.0, 7.0, 4.0])
    pred = torch.linspace(29.0, 5.0, config.N_DEPTHS)
    mask = torch.ones(config.N_DEPTHS, dtype=torch.bool)
    mask[3:] = False                                              # only 0,5,10 m valid: no inversion pair survives
    loss = M.sign_loss(_z(pred)[None], _z(truth)[None], mask[None], Y_MEAN, Y_STD, DEPTHS)
    assert float(loss) == pytest.approx(0.0, abs=1e-6)


def test_sign_loss_is_batched_and_averages_over_qualifying_pairs():
    truth = torch.stack([torch.tensor([26.0, 26.0, 26.0, 26.4, 26.8, 27.2, 26.0, 24.0, 22.0, 20.0,
                                       18.0, 14.0, 10.0, 7.0, 4.0]),
                         torch.linspace(29.0, 5.0, config.N_DEPTHS)])
    pred = torch.linspace(29.0, 5.0, config.N_DEPTHS)[None].repeat(2, 1)
    mask = torch.ones(2, config.N_DEPTHS, dtype=torch.bool)
    loss = M.sign_loss(_z(pred), _z(truth), mask, Y_MEAN, Y_STD, DEPTHS)
    assert float(loss) > 0.0                                      # first column contributes, second is fine
