"""MC-dropout uncertainty for the per-column MLP.

OWNER: Unit A (Arjhun). Keeps dropout ACTIVE at inference and runs n stochastic passes.
"""
from __future__ import annotations
import numpy as np
import torch
from oceanembed import config
from oceanembed.utils import io


def mc_dropout_predict(model, X: np.ndarray, n: int = config.MLP["mc_passes"]):
    """Run model n times with dropout ON -> (mean(N,11), std(N,11)) in REAL units.

    Sanity: std generally grows with depth (surface data constrains deep temperature less). Do NOT fake it.
    """
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT})"
    s = io.load_json(config.art("norm_stats.json"))
    tm, ts = np.asarray(s["targ_mean"], "float32"), np.asarray(s["targ_std"], "float32")

    model.train()  # enable dropout
    xt = torch.as_tensor(X, dtype=torch.float32)
    preds = np.empty((n, X.shape[0], config.N_DEPTHS), dtype="float32")
    with torch.no_grad():
        for i in range(n):
            preds[i] = model(xt).cpu().numpy() * ts + tm
    return preds.mean(0), preds.std(0)
