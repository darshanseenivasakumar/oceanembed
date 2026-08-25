"""Per-column MLP: surface features (11) -> temperature at 11 depths.

OWNER: Unit A (Arjhun). B seeded this stub; do not let other units edit it.
Contract: docs/MODEL_SPEC.md. Produces artifacts/mlp_model.pt.
"""
from __future__ import annotations
import numpy as np
from oceanembed import config

# import torch inside functions so the repo imports fine before torch is installed.


class MLPProfile:  # replace with (torch.nn.Module) when implementing
    """11 -> 128 -> 128 -> 11, dropout=config.MLP['dropout']. Keep dropout ON for MC-dropout."""

    def __init__(self, n_feat: int = config.N_FEAT, n_depth: int = config.N_DEPTHS):
        raise NotImplementedError("Unit A: build the torch MLP here (see docs/MODEL_SPEC.md).")


def load_mlp(path: str) -> "MLPProfile":
    raise NotImplementedError("Unit A: load state_dict from artifacts/mlp_model.pt.")


def predict_mlp(model: "MLPProfile", X: np.ndarray) -> np.ndarray:
    """X:(N,11) z-scored -> (N,11) temperature in REAL units (un-normalize with norm_stats.json)."""
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT})"
    raise NotImplementedError("Unit A: forward pass + un-normalize.")
