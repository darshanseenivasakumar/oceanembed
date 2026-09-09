"""Where the surface stops carrying information about depth. Owner: Unit A (Arjhun).

THE QUESTION NOBODY IN THIS SPECIALISATION SEPARATES
----------------------------------------------------
Every paper reports where its model is inaccurate. That number conflates two completely different
things:

    (a) the model is weak here            -- our problem, and fixable
    (b) the surface carries no signal
        about this depth, here, today     -- a property of the ocean, and a hard ceiling on the
                                             ENTIRE approach, ours and everyone else's

TS-Cast gestures at (b) in prose -- surface data bounds deep and high-frequency skill -- but as a
sentence, not a computed field. This module computes it, per cell and per day.

WHAT IS ACTUALLY MEASURED, IN ONE LINE
--------------------------------------
The Jacobian of the frozen model's output with respect to its satellite input:

    J[d, c] = y_std[d] * sum over (day, row, col) of  d mu_z[d] / d x_z[c, day, row, col]

which reads: **degrees Celsius of change at depth d, per one-standard-deviation coherent shift of
satellite channel c across the whole input patch.** Every channel is expressed per 1 s.d. of
ITSELF, which is what makes seven channels in different units (degC, psu, metres, m/s) comparable
at all -- summing raw sensitivities across those units would be dimensionally meaningless.

Where J collapses toward zero at depth, the network's output at that depth is insensitive to what
the satellite saw. It is not using the surface, because the surface is not telling it anything.

WHAT THIS IS AND IS NOT -- THE WORDING IS DELIBERATE
-----------------------------------------------------
This is a **sensitivity-derived information depth**. It is NOT an information-theoretic bound, and
this module never uses that phrase. A Fisher-information or mutual-information argument would need
a noise model for each satellite product and a likelihood over the state, and neither exists here.

What it IS: a measured property of THIS trained model. A different architecture could in principle
extract signal where this one has gone flat. So the honest claim is "our reconstruction stops
responding to the surface below this depth", not "no reconstruction could".

THE SHIPPED DECODER MAKES THIS CLEAN, AND THAT IS NOT LUCK
-----------------------------------------------------------
The shipped checkpoint uses `decoder="simple"`: mu comes from the encoder latent alone. The
climatology-prior path (FiLM) is built but was measured to cost accuracy and is not shipped, and
`forward` returns before touching `clim` on the simple path -- verified by running the model with
climatology set to zero and to noise and getting bit-identical output. So dmu/dx is the WHOLE
dependence of the prediction on its inputs. Had the residual-climatology decoder been shipped, a
flat Jacobian would have meant "it fell back on the climatology", which is a different and much
weaker statement.
"""
from __future__ import annotations

import numpy as np
import torch

from phase2.tscast_nio import config as c2

DEPTHS = np.asarray(c2.DEPTHS, dtype="float64")

#: Relative-sensitivity threshold defining "still informed by the surface". A level is counted as
#: informed while its aggregate sensitivity is at least this fraction of the profile's own maximum.
#: 0.10 is a choice, not a measurement -- it is a parameter everywhere it is used, it is written
#: into every artifact this module produces, and `information_depth` returns the whole curve so a
#: reader can pick their own.
TAU = 0.10


def jacobian(ctx, index=None, batch_size: int = 64, depths_idx=None) -> dict:
    """Per-sample dT/d(surface), for every depth and every channel.

    Returns
        coherent  (N, 15, C)  degC at depth d per +1 s.d. coherent shift of channel c
        absolute  (N, 15, C)  sum |dmu/dx| -- an upper bound; a channel can matter locally while
                              its coherent response cancels to nearly zero
        l2        (N, 15, C)  the gradient's Euclidean norm over the patch
    All three are kept because they answer different questions and one of them alone would let a
    cancelling channel read as an unused one.

    Fifteen backward passes per batch -- one per depth. `batch_size` is small by default because
    each pass holds a (B, C, T, P, P) gradient: at B=64, C=7, T=11, P=17 that is ~14 MB per depth.
    """
    index = ctx.argo_idx if index is None else np.asarray(index)
    depths_idx = range(c2.N_DEPTHS) if depths_idx is None else list(depths_idx)
    y_std = np.asarray(ctx.y_std, dtype="float64")

    coh, ab, l2 = [], [], []
    ctx.model.eval()
    for batch in ctx.loader(index, batch_size):
        x, g, cp, mo = ctx._unpack(batch)
        x = x.detach().requires_grad_(True)
        mu = ctx.model(x, g, cp, mo)[0]                       # (B, 15), z-scored

        b_coh = np.zeros((x.shape[0], len(depths_idx), x.shape[1]))
        b_abs = np.zeros_like(b_coh)
        b_l2 = np.zeros_like(b_coh)
        for k, d in enumerate(depths_idx):
            # Gradients do not mix across the batch: sample n's output depends only on sample n's
            # input, so summing over the batch and differentiating once recovers all B rows.
            (gr,) = torch.autograd.grad(mu[:, d].sum(), x, retain_graph=(k < len(depths_idx) - 1))
            gr = gr.detach()
            b_coh[:, k, :] = gr.sum(dim=(2, 3, 4)).cpu().numpy() * y_std[d]
            b_abs[:, k, :] = gr.abs().sum(dim=(2, 3, 4)).cpu().numpy() * y_std[d]
            b_l2[:, k, :] = gr.pow(2).sum(dim=(2, 3, 4)).sqrt().cpu().numpy() * y_std[d]
        coh.append(b_coh)
        ab.append(b_abs)
        l2.append(b_l2)

    return {
        "coherent": np.concatenate(coh),
        "absolute": np.concatenate(ab),
        "l2": np.concatenate(l2),
        "channels": ctx.channels,
        "depths": DEPTHS.tolist(),
        "units": "degC at depth per 1 s.d. coherent shift of the named channel",
    }


def aggregate(J, how: str = "l2") -> np.ndarray:
    """(N, 15, C) -> (N, 15): one sensitivity per depth, across channels.

    'l2'  -- the norm of the seven-channel response vector. The default: it asks how big the
             response is to ANY unit perturbation of the surface, which is the observability
             question, and it cannot be gamed by one channel cancelling another.
    'sum' -- the response to all seven shifting together by +1 s.d. Physically meaningful, but it
             can read as zero where two channels genuinely oppose, so it is offered and not chosen.
    'max' -- the single most informative channel at that depth.
    """
    A = np.abs(np.asarray(J, dtype="float64"))
    if how == "l2":
        return np.sqrt((A ** 2).sum(axis=-1))
    if how == "sum":
        return A.sum(axis=-1)
    if how == "max":
        return A.max(axis=-1)
    raise ValueError(f"how must be 'l2', 'sum' or 'max', got {how!r}")


def information_depth(sens, depths=None, tau: float = TAU) -> dict:
    """The deepest level whose sensitivity is at least `tau` of the profile's own maximum.

    Returns the depth in metres, the level index, and the full relative-sensitivity curve, so the
    threshold is a reader's choice rather than a hidden one.

    THE DEEPEST INFORMED LEVEL, NOT THE FIRST CROSSING. Sensitivity need not fall monotonically --
    a subsurface feature can be more strongly constrained than the level above it. Taking the
    deepest level that clears the threshold is the generous reading, and it is generous in the
    direction that makes our own claim WEAKER: it reports more of the column as informed, so any
    statement of the form "below here the surface tells us nothing" is conservative.
    """
    S = np.atleast_2d(np.asarray(sens, dtype="float64"))
    depths = DEPTHS if depths is None else np.asarray(depths, dtype="float64")
    if S.shape[-1] != depths.size:
        raise ValueError(f"sensitivity has {S.shape[-1]} levels, depths has {depths.size}")
    if not 0.0 < tau <= 1.0:
        raise ValueError(f"tau must be in (0, 1], got {tau}")

    peak = np.nanmax(S, axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = np.where(peak > 0, S / peak, np.nan)

    informed = np.isfinite(rel) & (rel >= tau)
    # argmax on the reversed axis finds the LAST True; a profile with none is flagged, not
    # silently given level 0 -- which would read as "informed at the surface only" rather than
    # "this profile has no usable sensitivity anywhere".
    any_informed = informed.any(axis=-1)
    last = depths.size - 1 - np.argmax(informed[:, ::-1], axis=-1)
    idx = np.where(any_informed, last, -1)
    dep = np.where(any_informed, depths[np.clip(idx, 0, None)], np.nan)

    return {
        "depth_m": dep,
        "level_index": idx,
        "relative": rel,
        "sensitivity": S,
        "tau": float(tau),
        "n_without_signal": int((~any_informed).sum()),
        "definition": ("deepest standard level whose across-channel sensitivity is >= tau of that "
                       "profile's own maximum; sensitivity-derived, NOT an information-theoretic "
                       "bound"),
    }


def residual_vs_information(error, info_depth, depths=None) -> dict:
    """Do our errors sit where the surface had stopped informing us?

    This is the join that turns a diagnostic into a claim. For each profile and depth we know the
    model's absolute error against an independent float, and whether that depth was above or below
    that profile's information depth. If the error below the floor is materially larger, then the
    deep error is not a training failure -- it is the reconstruction operating where its input has
    no leverage.

    Returns mean absolute error above and below the floor, per depth and overall, with counts.
    A depth resting on very few comparisons must not set a headline, so `n` travels with every
    number.
    """
    E = np.abs(np.asarray(error, dtype="float64"))
    depths = DEPTHS if depths is None else np.asarray(depths, dtype="float64")
    d_info = np.asarray(info_depth, dtype="float64")[:, None]
    below = depths[None, :] > d_info
    ok = np.isfinite(E) & np.isfinite(d_info)

    def _m(sel):
        s = sel & ok
        return (float(np.nanmean(E[s])) if s.any() else float("nan"), int(s.sum()))

    above_mae, above_n = _m(~below)
    below_mae, below_n = _m(below)
    per_depth = []
    for k in range(depths.size):
        a, an = _m((~below) & (np.arange(depths.size)[None, :] == k))
        b, bn = _m(below & (np.arange(depths.size)[None, :] == k))
        per_depth.append({"depth": float(depths[k]), "mae_above": a, "n_above": an,
                          "mae_below": b, "n_below": bn})

    # THE POOLED RATIO IS CONFOUNDED BY DEPTH AND MUST NOT BE THE HEADLINE.
    #
    # Sensitivity falls with depth and so does the ocean's own variability, so "below the floor"
    # is mostly "deep", and deep water is easier to predict for reasons that have nothing to do
    # with observability. The only fair test compares the two groups AT THE SAME DEPTH, which is
    # what `per_depth` holds. `verdict` is computed from those rows and from nothing else.
    testable = [r for r in per_depth if r["n_above"] > 30 and r["n_below"] > 30
                and np.isfinite(r["mae_above"]) and np.isfinite(r["mae_below"])]
    ratios = [r["mae_below"] / r["mae_above"] for r in testable if r["mae_above"] > 0]
    if not ratios:
        verdict = "UNTESTABLE: no depth has enough profiles on both sides of the floor"
        supported = None
    elif all(r > 1.0 for r in ratios):
        verdict = ("SUPPORTED: at every testable depth, profiles below their information floor "
                   "carry larger errors than profiles above it")
        supported = True
    elif all(r < 1.0 for r in ratios):
        verdict = ("REFUTED, AND IN THE OPPOSITE DIRECTION: at every testable depth, profiles "
                   "below their information floor carry SMALLER errors. Low sensitivity marks "
                   "quiescent water that is close to climatology and easy to predict, not water "
                   "the model cannot see into.")
        supported = False
    else:
        verdict = "MIXED: the sign of the effect is not consistent across depths"
        supported = False

    return {
        "mae_above_floor": above_mae, "n_above_floor": above_n,
        "mae_below_floor": below_mae, "n_below_floor": below_n,
        "pooled_ratio": ((below_mae / above_mae)
                         if above_mae and np.isfinite(above_mae) else float("nan")),
        "pooled_ratio_is_confounded_by_depth": True,
        "per_depth": per_depth,
        "depth_controlled_ratios": ratios,
        "n_testable_depths": len(testable),
        "verdict": verdict,
        "supported": supported,
    }
