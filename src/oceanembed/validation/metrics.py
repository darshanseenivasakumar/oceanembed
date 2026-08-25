"""Error metrics for reconstruction, reported relative to the climatology baseline.

OWNER: Unit C (Mitun+Niru). Implemented as the Day-3 vertical slice; refine as needed.
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_clim: np.ndarray | None = None) -> dict:
    """y_true,y_pred:(N,11) -> {rmse, mae, r2, rmse_by_depth[11], skill_vs_clim}. NaN-safe.

    skill_vs_clim = 1 - RMSE_pred / RMSE_clim  (needs y_clim; None -> None). >0 means better than climatology.
    """
    assert y_true.shape == y_pred.shape and y_true.shape[1] == config.N_DEPTHS, "shapes must be (N,11)"
    err = y_pred - y_true
    rmse = float(np.sqrt(np.nanmean(err ** 2)))
    mae = float(np.nanmean(np.abs(err)))
    ss_res = np.nansum(err ** 2)
    ss_tot = np.nansum((y_true - np.nanmean(y_true)) ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    rmse_by_depth = np.sqrt(np.nanmean(err ** 2, axis=0)).astype(float).tolist()

    skill = None
    if y_clim is not None:
        rmse_clim = float(np.sqrt(np.nanmean((y_clim - y_true) ** 2)))
        skill = float(1.0 - rmse / rmse_clim) if rmse_clim > 0 else None
    return dict(rmse=rmse, mae=mae, r2=r2, rmse_by_depth=rmse_by_depth, skill_vs_clim=skill)
