"""Observation-priority map: where an extra in-situ measurement may add most scientific value.

OWNER: Unit A (Arjhun). Frame honestly (see docs/NOVELTY_MATRIX.md): "regions where additional observations
may provide high scientific value" — NEVER "the AI tells MoES where to deploy Argo."

Method and weighting are documented in docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import warnings

import numpy as np

from oceanembed import config

# Default weights for (anomaly, uncertainty, sparsity). Equal weighting is the honest default:
# we have no evidence yet that one factor should dominate. See docs/ARCHITECTURE.md.
DEFAULT_WEIGHTS = (1.0, 1.0, 1.0)


def _norm01(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype="float32")
    lo, hi = np.nanmin(a), np.nanmax(a)
    return np.zeros_like(a) if hi <= lo else (a - lo) / (hi - lo)


def _norm_factor(a: np.ndarray, name: str, robust: bool) -> tuple[np.ndarray, bool]:
    """Scale one factor to [0,1], NaN-preserving, with a guard for degenerate inputs.

    A CONSTANT grid carries no information about *where* to observe. Min-max scaling maps it to
    all-zeros, which would silently zero the entire product -- the map renders blank and looks
    like a bug rather than a missing input. We return all-ONES instead, i.e. the factor is
    NEUTRAL. This is not hypothetical: `predict.py::_argo_sparsity()` returns a uniform grid
    whenever `argo_test` is absent, which is the state of the repo today.
    """
    a = np.asarray(a, dtype="float32")

    if np.all(np.isnan(a)):
        warnings.warn(f"{name}_grid is entirely NaN; treating it as neutral.", RuntimeWarning, stacklevel=3)
        return np.ones_like(a), True

    if robust:
        lo, hi = np.nanpercentile(a, 1.0), np.nanpercentile(a, 99.0)
    else:
        lo, hi = np.nanmin(a), np.nanmax(a)

    if not np.isfinite(hi - lo) or hi <= lo:
        warnings.warn(
            f"{name}_grid is constant (no spatial variation), so it cannot rank locations. "
            "Treating it as NEUTRAL (all ones) rather than zeroing the whole priority map.",
            RuntimeWarning,
            stacklevel=3,
        )
        return np.ones_like(a), True

    return np.clip((a - lo) / (hi - lo), 0.0, 1.0), False


def observation_priority(
    anomaly_grid: np.ndarray,
    uncertainty_grid: np.ndarray,
    sparsity_grid: np.ndarray,
    *,
    weights: tuple[float, float, float] = DEFAULT_WEIGHTS,
    robust: bool = True,
) -> np.ndarray:
    """All inputs (100,240) -> priority (100,240) in [0,1]; NaN preserved on land.

    priority = weighted GEOMETRIC MEAN of norm(|anomaly|), norm(uncertainty), norm(sparsity).

    Why a geometric mean rather than the raw product: with equal weights the two rank locations
    IDENTICALLY (the cube root is monotonic), but the product of three [0,1] numbers collapses
    toward zero, so a colour map of it is almost entirely dark. The geometric mean keeps the same
    ordering while spreading values across [0,1], which is what the panel needs to be readable.

    Multiplicative (not additive) is deliberate: a location is only interesting if it is
    ALL THREE of anomalous, uncertain, and unobserved. A sum would let one large factor carry a
    location that is uninteresting on the other two.
    """
    grids = {
        "anomaly": anomaly_grid,
        "uncertainty": uncertainty_grid,
        "sparsity": sparsity_grid,
    }
    for name, g in grids.items():
        g = np.asarray(g)
        assert g.shape == (config.N_LAT, config.N_LON), (
            f"{name}_grid must be ({config.N_LAT},{config.N_LON}), got {g.shape}"
        )

    w = np.asarray(weights, dtype="float64")
    assert w.shape == (3,), f"weights must be 3 values, got {weights}"
    assert np.all(w >= 0) and w.sum() > 0, f"weights must be non-negative and not all zero, got {weights}"

    # |anomaly|: a cold anomaly is as interesting as a warm one.
    a, a_neutral = _norm_factor(np.abs(np.asarray(anomaly_grid, dtype="float32")), "anomaly", robust)
    u, u_neutral = _norm_factor(uncertainty_grid, "uncertainty", robust)
    s, s_neutral = _norm_factor(sparsity_grid, "sparsity", robust)

    # If EVERY factor is degenerate we have no basis to rank anywhere. Returning all-ones
    # would paint the whole basin as maximum priority, which is worse than showing nothing.
    if a_neutral and u_neutral and s_neutral:
        warnings.warn(
            "all three factors are degenerate -- priority is unevaluable, returning NaN. "
            "The UI hides the panel rather than displaying a uniform map.",
            RuntimeWarning,
            stacklevel=2,
        )
        return np.full((config.N_LAT, config.N_LON), np.nan, dtype="float32")

    # Weighted geometric mean, computed in log space for numerical stability.
    # eps keeps log finite where a factor is exactly 0; the result there is still ~0.
    eps = 1e-12
    stack = np.stack([a, u, s])
    logs = np.log(np.clip(stack, eps, None))
    priority = np.exp(np.tensordot(w, logs, axes=(0, 0)) / w.sum()).astype("float32")

    # Land (NaN in any input) must stay NaN, not become a priority of 0 -- the UI masks NaN,
    # and a zero would read as "we evaluated this cell and it scored lowest".
    priority[np.isnan(stack).any(axis=0)] = np.nan

    finite = priority[np.isfinite(priority)]
    if finite.size:
        assert finite.min() >= -1e-6 and finite.max() <= 1 + 1e-6, (
            f"priority escaped [0,1]: {finite.min():.4f}..{finite.max():.4f}"
        )
    return priority
