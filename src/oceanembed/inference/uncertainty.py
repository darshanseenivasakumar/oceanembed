"""MC-dropout uncertainty for the per-column MLP.

OWNER: Unit A (Arjhun). Keeps dropout ACTIVE at inference and runs n stochastic passes.

READ THIS BEFORE QUOTING ANY UNCERTAINTY NUMBER
-----------------------------------------------
TEAM_PLAN Day 4 says: "uncertainty should generally increase with depth. If it doesn't,
investigate -- don't fake it." It does not. Investigated, and the reason is mechanical:

MC-dropout perturbs a SHARED trunk (11 -> 128 -> 128) that feeds all 11 depth outputs, so the
raw output spread is nearly constant across depths in NORMALIZED space [VERIFIED: ratio
std/targ_std = 0.127 -> 0.162, spread 0.043]. Converting to real degC multiplies by targ_std,
which shrinks with depth -- so real-units sigma shrinks with depth purely as an artefact of
un-normalization, not because the model is more confident down there.

Measured calibration on fixtures (sigma / actual RMSE; well-calibrated == 1.0 at every depth):

    depth      MC-dropout      quantile (LightGBM)
      0 m         1.25              0.70
    500 m         0.31              0.92
    drift         4.0x              1.8x

**MC-dropout UNDER-STATES the real error at 500 m by 3.2x.** It reports the most confidence
exactly where the model is least trustworthy. `models/lgbm_baseline.quantile_uncertainty` is
better calibrated here because each depth has its OWN booster and can express its own spread.

Expect this to get WORSE on real GLORYS, not better: there, deep prediction is genuinely harder
so actual error will GROW with depth while MC-dropout sigma keeps SHRINKING. Re-check before any
reliability claim reaches the demo or a judge. See docs/DECISIONS.md D-016.
"""
from __future__ import annotations

import numpy as np
import torch

from oceanembed import config
from oceanembed.utils import io


def mc_dropout_predict(model, X: np.ndarray, n: int = config.MLP["mc_passes"]):
    """Run model n times with dropout ON -> (mean(N,11), std(N,11)) in REAL units.

    This is EPISTEMIC (model) uncertainty only -- the spread of what this one network believes.
    It does not include observation noise or the error from training on GLORYS rather than the
    real ocean, so it is a LOWER BOUND on total predictive uncertainty. Never present it as a
    confidence interval on the true temperature.

    The model's train/eval mode is restored before returning; leaving it in train() made every
    later plain forward pass silently stochastic.
    """
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT})"
    assert n >= 2, f"need at least 2 passes to have a spread, got {n}"

    s = io.load_json(config.art("norm_stats.json"))
    tm = np.asarray(s["targ_mean"], "float32")
    ts = np.asarray(s["targ_std"], "float32")

    was_training = model.training
    model.train()  # enable dropout
    try:
        xt = torch.as_tensor(X, dtype=torch.float32)
        preds = np.empty((n, X.shape[0], config.N_DEPTHS), dtype="float32")
        with torch.no_grad():
            for i in range(n):
                preds[i] = model(xt).cpu().numpy() * ts + tm
    finally:
        model.train(was_training)  # restore -- do not leak train mode to later callers

    return preds.mean(0), preds.std(0)


def calibration_ratio(sigma: np.ndarray, y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """Per-depth sigma / actual RMSE -> (11,). The honest diagnostic for any uncertainty method.

    1.0  = well calibrated
    <1.0 = OVERCONFIDENT (claims more certainty than it has)  <-- the dangerous direction
    >1.0 = underconfident

    Use this instead of eyeballing whether sigma "increases with depth". A sigma that rises with
    depth can still be badly calibrated, and one that falls can be fine -- what matters is
    whether it tracks the error actually made.
    """
    sigma = np.asarray(sigma, dtype="float32")
    y_true = np.asarray(y_true, dtype="float32")
    y_pred = np.asarray(y_pred, dtype="float32")
    assert sigma.shape == y_true.shape == y_pred.shape, "sigma, y_true, y_pred must all be (N,11)"

    rmse = np.sqrt(np.nanmean((y_pred - y_true) ** 2, axis=0))
    return (np.nanmean(sigma, axis=0) / np.maximum(rmse, 1e-9)).astype("float32")


def relative_uncertainty(sigma: np.ndarray) -> np.ndarray:
    """sigma as a fraction of each depth's natural variability -> (N,11).

    Real-units sigma is not comparable across depths: 0.05 degC at 500 m (natural spread
    ~0.34 degC) means something very different from 0.05 degC at the surface (spread ~2.06 degC).
    Dividing by targ_std makes depths comparable, which is what the UI should display.
    """
    ts = np.asarray(io.load_json(config.art("norm_stats.json"))["targ_std"], "float32")
    return (np.asarray(sigma, dtype="float32") / np.maximum(ts, 1e-9)).astype("float32")
