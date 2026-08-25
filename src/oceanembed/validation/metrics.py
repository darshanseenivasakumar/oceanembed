"""Error metrics for reconstruction, all reported relative to the climatology baseline.

OWNER: Unit C (Mitun+Niru). Contract: docs/VALIDATION_PROTOCOL.md.
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_clim: np.ndarray | None = None) -> dict:
    """y_true,y_pred:(N,11) -> {rmse, mae, r2, rmse_by_depth[11], skill_vs_clim}.

    skill_vs_clim = 1 - RMSE_pred/RMSE_clim  (needs y_clim; None -> skill_vs_clim=None).
    """
    assert y_true.shape == y_pred.shape and y_true.shape[1] == config.N_DEPTHS, "shapes must be (N,11)"
    raise NotImplementedError("Unit C: implement RMSE/MAE/R2/per-depth + skill_vs_clim. Handle NaNs.")
