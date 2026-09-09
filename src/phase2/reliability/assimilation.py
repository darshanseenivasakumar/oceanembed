"""Latent-space assimilation: correct the state, not the pixel. Owner: Unit A (Arjhun).

THE IDEA
--------
Every paper in this specialisation treats Argo as the scoring rubric. None of them feed it back.
When a float surfaces, its profile is used to grade the model and then discarded.

This module uses it. With the network FROZEN, it asks: what latent vector would have made the
decoder produce the profile the float actually measured? That is a small optimisation over 128
numbers with the weights held fixed -- seconds, no retraining, no gradient ever reaching a weight.

    h*  =  argmin_h  || decode(h) - y_observed ||^2  +  lambda || h - h0 ||^2

The correction is then dh = h* - h0, and it is pushed to every other cell whose latent state is
CLOSE IN LATENT SPACE, by cosine similarity -- not to cells that are close in kilometres. Two
patches of ocean with similar surface expressions get corrected alike even if they are a thousand
kilometres apart; two adjacent cells on opposite sides of a front do not.

The naive version of this -- patch the output near the float -- is trivial and a reviewer would
see through it in a sentence. Correcting the latent is inference-time data assimilation on a
frozen network, and it does not exist in this specialisation.

THE CONTROL THAT DECIDES WHETHER ANY OF IT IS REAL
---------------------------------------------------
The shipped model carries a **+0.1003 degC warm bias**. So ANY correction fitted to a real float
will, on average, cool the prediction -- and cooling the prediction improves the score EVERYWHERE,
whether or not the propagation means anything. An experiment that only measured "error went down
at similar cells" would report a global bias correction as latent assimilation, and it would be
completely wrong. This project has already made that exact class of mistake once, in the
cloud-dropout sweep, where a 15% masking improvement was error cancellation rather than robustness.

So every run measures the same correction applied to three populations:

    similar     cosine similarity >= tau to the donor float's latent
    dissimilar  the BOTTOM decile of similarity -- states the correction should not describe
    shuffled    the same corrections, randomly reassigned to recipients

**The result is the GAP between `similar` and the other two.** If all three improve equally, this
is a bias correction wearing a costume, and the module says so rather than reporting the first
number alone. `summarise()` returns `verdict` for exactly this reason.

EVALUATION IS LEAVE-ONE-OUT, ALWAYS
------------------------------------
A float's own profile is never used to score the correction fitted to it. Fitting a latent to a
profile and then reporting the error against that same profile measures the optimiser, not the
method -- it will be near zero by construction, which is why `fit_latent` reports it separately and
labels it `in_sample`.
"""
from __future__ import annotations

import numpy as np
import torch

from phase2.tscast_nio import config as c2

#: Cosine similarity above which a cell is treated as the same water mass as the donor. 0.9 is a
#: choice, not a measurement; it is a parameter everywhere and is written into every artifact.
TAU = 0.90

#: Ridge weight anchoring h* to h0. Without it the optimiser is free to find a latent far outside
#: the distribution the decoder was trained on, which fits one profile beautifully and generalises
#: to nothing. Reported in every result so it can be swept.
LAMBDA = 1.0

STEPS = 300
LR = 0.05


def decode(model, h, clim=None, month=None):
    """(mu, logvar) from a latent, with the weights frozen. Both z-scored.

    Dispatches on the decoder the checkpoint actually carries and RAISES on the FiLM path rather
    than guessing. FiLM's decoder consumes the climatology as its input, so a latent correction
    there means something different from a latent correction on the shipped head, and silently
    treating the two as interchangeable would produce a number nobody could interpret.
    """
    if getattr(model, "decoder", None) is not None:
        raise NotImplementedError(
            "latent assimilation is implemented for the shipped decoder='simple' head only. The "
            "FiLM decoder takes the climatology as its input, so a latent correction there is not "
            "the same operation and must be designed, not assumed. This checkpoint carries "
            f"decoder={model.decoder_name!r}.")
    out = model.simple_head(h)
    blocks = out.split(c2.N_DEPTHS, dim=-1)
    return blocks[0], blocks[1]


def fit_latent(model, h0, y_obs_z, mask, lam: float = LAMBDA, steps: int = STEPS,
               lr: float = LR) -> dict:
    """Find the latent whose decoded profile best matches one observed profile.

    Args:
        h0:      (1, latent) the encoder's own output for that cell -- the starting point.
        y_obs_z: (1, 15) the float's profile, z-scored with the SAME statistics the model was
                 fitted under. Passing physical degC here would silently optimise against a target
                 twenty times too large.
        mask:    (1, 15) bool, True where the float actually sampled. Levels a float never reached
                 contribute nothing; filling them with zeros would fit the latent to the mean.

    Returns h_star, the correction, and the in-sample error before and after -- labelled
    `in_sample` because it is not evidence of anything on its own.
    """
    was_training = model.training
    model.eval()
    for p in model.parameters():                      # belt and braces: no weight may move
        p.requires_grad_(False)

    h = h0.detach().clone().requires_grad_(True)
    opt = torch.optim.Adam([h], lr=lr)
    m = mask.float()
    n = m.sum().clamp(min=1.0)

    def _loss(hh):
        mu, _lv = decode(model, hh)
        fit = (((mu - y_obs_z) ** 2) * m).sum() / n
        return fit + lam * ((hh - h0) ** 2).sum(), fit

    with torch.no_grad():
        _, fit0 = _loss(h0)
    history = []
    for _ in range(steps):
        opt.zero_grad()
        total, fit = _loss(h)
        total.backward()
        opt.step()
        history.append(float(fit.detach()))

    with torch.no_grad():
        _, fit1 = _loss(h)

    if was_training:
        model.train()
    return {
        "h_star": h.detach(),
        "delta": (h.detach() - h0.detach()),
        "in_sample_mse_before": float(fit0),
        "in_sample_mse_after": float(fit1),
        "history": history,
        "lambda": float(lam),
        "steps": int(steps),
        "lr": float(lr),
    }


def cosine(a, b) -> np.ndarray:
    """Row-wise cosine similarity of (N, D) against (M, D) -> (N, M)."""
    A = np.asarray(a, dtype="float64")
    B = np.asarray(b, dtype="float64")
    A = A / np.clip(np.linalg.norm(A, axis=-1, keepdims=True), 1e-12, None)
    B = B / np.clip(np.linalg.norm(B, axis=-1, keepdims=True), 1e-12, None)
    return A @ B.T


def propagate(h_recipients, delta, similarity, tau: float = TAU, weighted: bool = True):
    """Apply one donor's correction to recipient latents, scaled by how alike they are.

    Recipients below `tau` receive nothing at all -- the correction describes a water mass, and a
    state that is not that water mass should not be touched. Above tau the weight ramps linearly
    from 0 at tau to 1 at perfect similarity, so a cell that only just clears the threshold is not
    given the full correction.
    """
    s = np.asarray(similarity, dtype="float64")
    w = np.where(s >= tau, (s - tau) / max(1e-9, 1.0 - tau) if weighted else 1.0, 0.0)
    return np.asarray(h_recipients, dtype="float64") + w[:, None] * np.asarray(delta, "float64")


def summarise(mae_before, mae_similar, mae_dissimilar, mae_shuffled, n) -> dict:
    """Turn four error numbers into a verdict, so a page cannot render the first one alone.

    The claim is only supported if the improvement at SIMILAR states materially exceeds the
    improvement at dissimilar and shuffled ones. Otherwise the honest reading is that a global
    bias correction has been measured, and the verdict says that in words.
    """
    def gain(after):
        return float(mae_before - after)

    g_sim, g_dis, g_shuf = gain(mae_similar), gain(mae_dissimilar), gain(mae_shuffled)
    margin = g_sim - max(g_dis, g_shuf)
    if g_sim <= 0:
        verdict = "NO IMPROVEMENT: the correction does not help at similar states either"
    elif margin <= 0:
        verdict = ("BIAS CORRECTION, NOT ASSIMILATION: dissimilar or shuffled recipients improve "
                   "as much as similar ones, so the gain is not coming from latent similarity")
    elif margin < 0.25 * g_sim:
        verdict = ("WEAK: similar states improve more, but most of the gain is also available to "
                   "unrelated states, so it is mostly a bias correction")
    else:
        verdict = ("SUPPORTED: the gain at similar states substantially exceeds the gain at "
                   "dissimilar and shuffled states")
    return {
        "mae_before": float(mae_before),
        "mae_similar": float(mae_similar),
        "mae_dissimilar": float(mae_dissimilar),
        "mae_shuffled": float(mae_shuffled),
        "gain_similar": g_sim,
        "gain_dissimilar": g_dis,
        "gain_shuffled": g_shuf,
        "margin": float(margin),
        "n_pairs": int(n),
        "verdict": verdict,
        "supported": bool(g_sim > 0 and margin >= 0.25 * g_sim),
    }
