"""MC-dropout uncertainty for the per-column MLP.

OWNER: Unit A (Arjhun). Contract: docs/MODEL_SPEC.md.
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def mc_dropout_predict(model, X: np.ndarray, n: int = config.MLP["mc_passes"]):
    """Run the model n times with dropout ACTIVE -> (mean(N,11), std(N,11)) in real units.

    Sanity: std should generally grow with depth. If it doesn't, investigate — do NOT fake it.
    """
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT})"
    raise NotImplementedError("Unit A: enable train-mode dropout, loop n passes, stack, mean/std over passes.")
