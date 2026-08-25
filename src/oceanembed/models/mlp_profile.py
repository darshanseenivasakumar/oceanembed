"""Per-column MLP: surface features (11) -> temperature at 11 depths.

OWNER: Unit A (Arjhun). Contract: docs/MODEL_SPEC.md. Produces artifacts/mlp_model.pt.

Normalization lives INSIDE the model as registered buffers, so a checkpoint is
self-describing: `state_dict()` carries feat/targ mean+std alongside the weights, and
`torch.load(..., weights_only=True)` (the PyTorch >=2.6 default) can read it because
buffers are plain tensors. See docs/DECISIONS.md.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from oceanembed import config


class MLPProfile(nn.Module):
    """11 -> 128 -> 128 -> 11, dropout=config.MLP['dropout'].

    Dropout stays ON in train() mode; Day-4 MC-dropout relies on that, so
    tests/test_model.py asserts it explicitly.
    """

    def __init__(
        self,
        n_feat: int = config.N_FEAT,
        n_depth: int = config.N_DEPTHS,
        hidden: tuple[int, ...] | None = None,
        dropout: float | None = None,
    ) -> None:
        super().__init__()
        hidden = tuple(config.MLP["hidden"]) if hidden is None else tuple(hidden)
        dropout = float(config.MLP["dropout"]) if dropout is None else float(dropout)

        self.n_feat = int(n_feat)
        self.n_depth = int(n_depth)
        self.hidden = hidden
        self.dropout_p = dropout

        layers: list[nn.Module] = []
        prev = self.n_feat
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)]
            prev = h
        layers.append(nn.Linear(prev, self.n_depth))
        self.net = nn.Sequential(*layers)

        # Identity normalization until set_norm_stats() is called.
        self.register_buffer("feat_mean", torch.zeros(self.n_feat))
        self.register_buffer("feat_std", torch.ones(self.n_feat))
        self.register_buffer("targ_mean", torch.zeros(self.n_depth))
        self.register_buffer("targ_std", torch.ones(self.n_depth))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(N, n_feat) z-scored -> (N, n_depth) z-scored."""
        return self.net(x)

    def set_norm_stats(self, feat_mean, feat_std, targ_mean, targ_std) -> None:
        """Store the z-score stats used at training time. Guards against zero std."""
        def _t(a, n):
            v = torch.as_tensor(np.asarray(a, dtype="float32")).flatten()
            assert v.numel() == n, f"expected {n} values, got {v.numel()}"
            return v

        self.feat_mean.copy_(_t(feat_mean, self.n_feat))
        self.feat_std.copy_(torch.clamp(_t(feat_std, self.n_feat), min=1e-6))
        self.targ_mean.copy_(_t(targ_mean, self.n_depth))
        self.targ_std.copy_(torch.clamp(_t(targ_std, self.n_depth), min=1e-6))

    def denormalize(self, y_z: torch.Tensor) -> torch.Tensor:
        """z-scored target -> real units (degC)."""
        return y_z * self.targ_std + self.targ_mean


def load_mlp(path: str) -> MLPProfile:
    """Load artifacts/mlp_model.pt into a fresh MLPProfile.

    weights_only=True is the PyTorch >=2.6 default and is safe here because the checkpoint
    contains only tensors (weights + the four normalization buffers).
    """
    state = torch.load(path, map_location="cpu", weights_only=True)
    model = MLPProfile()
    model.load_state_dict(state)
    model.eval()
    return model


def predict_mlp(model: MLPProfile, X: np.ndarray) -> np.ndarray:
    """X:(N,11) z-scored -> (N,11) temperature in REAL units (degC).

    Per docs/MODEL_SPEC.md the CALLER supplies z-scored X (using norm_stats.json).
    We warn loudly if X looks like raw units, because that failure is silent otherwise.
    """
    X = np.asarray(X, dtype="float32")
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, (
        f"X must be (N,{config.N_FEAT}), got {X.shape}"
    )

    # Cheap guard: z-scored data sits near mean 0 / std 1. Raw SST (~28) blows past this.
    if np.abs(X.mean()) > 3.0 or X.std() > 5.0:
        import warnings

        warnings.warn(
            f"predict_mlp received X with mean={X.mean():.2f} std={X.std():.2f} -- that looks "
            "like RAW units, but the contract expects z-scored input. Predictions will be wrong.",
            RuntimeWarning,
            stacklevel=2,
        )

    was_training = model.training
    model.eval()
    with torch.no_grad():
        y = model.denormalize(model(torch.from_numpy(X)))
    if was_training:
        model.train()

    out = y.cpu().numpy().astype("float32")
    assert out.shape == (X.shape[0], config.N_DEPTHS), f"bad output shape {out.shape}"
    return out
