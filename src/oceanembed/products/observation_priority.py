"""Observation-priority map: where an extra in-situ measurement may add most scientific value.

OWNER: Unit A (Arjhun). Frame honestly (see docs/NOVELTY_MATRIX.md): "regions where additional observations
may provide high scientific value" — NEVER "the AI tells MoES where to deploy Argo."
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def _norm01(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype="float32")
    lo, hi = np.nanmin(a), np.nanmax(a)
    return np.zeros_like(a) if hi <= lo else (a - lo) / (hi - lo)


def observation_priority(anomaly_grid: np.ndarray,
                         uncertainty_grid: np.ndarray,
                         sparsity_grid: np.ndarray) -> np.ndarray:
    """All inputs (100,240) -> priority (100,240) in [0,1].

    priority = norm(|anomaly|) * norm(uncertainty) * norm(sparsity).  (weights documented in ARCHITECTURE.md)
    sparsity = distance to nearest recent Argo (Unit A computes/receives it).
    """
    for name, g in [("anomaly", anomaly_grid), ("uncertainty", uncertainty_grid), ("sparsity", sparsity_grid)]:
        assert g.shape == (config.N_LAT, config.N_LON), f"{name}_grid must be (100,240)"
    raise NotImplementedError("Unit A: combine the three normalized grids; document the weighting.")
