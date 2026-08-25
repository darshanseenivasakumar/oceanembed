"""Climatology baseline: monthly mean temperature per cell/depth over the TRAIN years.

OWNER: Unit C (Mitun+Niru). Produces artifacts/climatology.npy (12,100,240,11).
This is the mandatory baseline every model is scored against, and the anomaly reference.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from oceanembed import config


def build_climatology(y_train: np.ndarray, meta_train: pd.DataFrame) -> np.ndarray:
    """y_train:(N,11) + meta_train[month,cell_id,...] -> (12,100,240,11). Save to artifacts/climatology.npy."""
    assert y_train.shape[1] == config.N_DEPTHS, "y_train must be (N,11)"
    raise NotImplementedError("Unit C: group by (month, cell) -> mean profile; scatter into the (12,100,240,11) grid.")


def climatology_predict(meta: pd.DataFrame) -> np.ndarray:
    """For each row (month, cell) look up the climatology -> baseline (N,11)."""
    raise NotImplementedError("Unit C: index artifacts/climatology.npy by month + cell_id.")
