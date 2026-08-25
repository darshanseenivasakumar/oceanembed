"""Anomaly = reconstruction - climatology, z-scored per depth.

OWNER: Unit C (Mitun+Niru). Baseline period = TRAIN years climatology (see DECISIONS.md).
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def anomaly(pred_grid: np.ndarray, climatology: np.ndarray, month: int) -> np.ndarray:
    """pred_grid:(100,240,11), climatology:(12,100,240,11), month:1..12 -> anomaly (100,240,11).

    Optionally z-score per depth (threshold k*sigma; document k). Do NOT hardcode arbitrary thresholds.
    """
    assert pred_grid.shape == (config.N_LAT, config.N_LON, config.N_DEPTHS), "pred_grid must be (100,240,11)"
    assert 1 <= month <= 12, "month must be 1..12"
    raise NotImplementedError("Unit C: subtract climatology[month-1]; optional per-depth z-score.")
