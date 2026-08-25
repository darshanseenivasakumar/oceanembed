"""Per-column MLP: surface features (11) -> temperature at 11 depths.

OWNER: Unit A (Arjhun). Trained on z-scored X and z-scored y; predict_mlp returns REAL units.
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
from oceanembed import config
from oceanembed.utils import io


class MLPProfile(nn.Module):
    def __init__(self, n_feat: int = config.N_FEAT, n_depth: int = config.N_DEPTHS,
                 hidden=config.MLP["hidden"], dropout: float = config.MLP["dropout"]):
        super().__init__()
        layers, d = [], n_feat
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU(), nn.Dropout(dropout)]
            d = h
        layers += [nn.Linear(d, n_depth)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def _targ_stats():
    s = io.load_json(config.art("norm_stats.json"))
    return np.asarray(s["targ_mean"], "float32"), np.asarray(s["targ_std"], "float32")


def load_mlp(path: str = None) -> MLPProfile:
    path = path or config.art("mlp_model.pt")
    model = MLPProfile()
    model.load_state_dict(torch.load(path, map_location="cpu"))
    model.eval()
    return model


def predict_mlp(model: MLPProfile, X: np.ndarray) -> np.ndarray:
    """X:(N,11) z-scored -> (N,11) temperature in REAL units (deg C)."""
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT})"
    tm, ts = _targ_stats()
    model.eval()
    with torch.no_grad():
        out = model(torch.as_tensor(X, dtype=torch.float32)).cpu().numpy()
    return (out * ts + tm).astype("float32")
