"""Per-column MLP: surface features (11) -> temperature at 11 depths.

OWNER: Unit A (Arjhun). Contract: docs/MODEL_SPEC.md. Produces artifacts/mlp_model.pt.

Normalization lives INSIDE the model as registered buffers, so a checkpoint is
self-describing: `state_dict()` carries feat/targ mean+std alongside the weights, and
`torch.load(..., weights_only=True)` (the PyTorch >=2.6 default) can read it because
buffers are plain tensors. See docs/DECISIONS.md.
"""
from __future__ import annotations

import warnings

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

        # Provenance: 1.0 => trained on synthetic fixtures, MUST NOT reach the demo.
        # A float buffer (not a bool attr) so it survives the checkpoint round-trip
        # under torch.load(weights_only=True). See docs/DECISIONS.md D-010.
        self.register_buffer("trained_on_fixtures", torch.zeros(1))

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

    def normalize(self, x_raw: torch.Tensor) -> torch.Tensor:
        """raw features -> z-scored, using the stats baked into this checkpoint."""
        return (x_raw - self.feat_mean) / self.feat_std

    def denormalize(self, y_z: torch.Tensor) -> torch.Tensor:
        """z-scored target -> real units (degC)."""
        return y_z * self.targ_std + self.targ_mean

    @property
    def is_fixture_model(self) -> bool:
        return bool(self.trained_on_fixtures.item() >= 0.5)


def load_mlp(path: str) -> MLPProfile:
    """Load artifacts/mlp_model.pt into a fresh MLPProfile.

    weights_only=True is the PyTorch >=2.6 default and is safe here because the checkpoint
    contains only tensors (weights + normalization + provenance buffers).
    """
    state = torch.load(path, map_location="cpu", weights_only=True)
    model = MLPProfile()
    model.load_state_dict(state)
    model.eval()

    if model.is_fixture_model:
        warnings.warn(
            f"{path} was trained on SYNTHETIC FIXTURES: its normalization stats and weights encode "
            "fixture statistics, not the ocean. It must be retrained once real GLORYS data lands "
            "and must never back the demo. See docs/DECISIONS.md D-010.",
            RuntimeWarning,
            stacklevel=2,
        )
    return model


def predict_mlp(model: MLPProfile, X: np.ndarray) -> np.ndarray:
    """X:(N,11) in RAW units -> (N,11) temperature in REAL units (degC).

    RAW IN, REAL OUT. The model carries its own normalization stats, so it z-scores the
    input itself. Callers (inference/predict.py, the panels) pass raw features straight
    through and cannot double-normalize or skip normalization. See docs/DECISIONS.md D-009.
    """
    X = np.asarray(X, dtype="float32")
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, (
        f"X must be (N,{config.N_FEAT}), got {X.shape}"
    )

    # Guard the one way this can still go wrong: a caller who pre-z-scored. If the model
    # expects meaningfully non-zero feature means but X arrives centred on 0 with unit
    # spread, it was almost certainly normalized already -> we would double-normalize.
    if float(model.feat_mean.abs().max()) > 1.0:
        if abs(float(X.mean())) < 0.5 and 0.3 < float(X.std()) < 3.0:
            warnings.warn(
                f"predict_mlp got X with mean={X.mean():.2f} std={X.std():.2f}, which looks "
                "ALREADY z-scored. This function expects RAW units and normalizes internally; "
                "passing normalized input double-normalizes and yields wrong temperatures.",
                RuntimeWarning,
                stacklevel=2,
            )

    was_training = model.training
    model.eval()
    with torch.no_grad():
        y = model.denormalize(model(model.normalize(torch.from_numpy(X))))
    if was_training:
        model.train()

    out = y.cpu().numpy().astype("float32")
    assert out.shape == (X.shape[0], config.N_DEPTHS), f"bad output shape {out.shape}"
    return out
