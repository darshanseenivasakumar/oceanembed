"""Where an extra observation would teach the model most. Owner: Unit A (Arjhun).

WHAT THIS IS, AND WHAT IT IS NOT -- read `docs/NOVELTY_MATRIX.md` before changing the wording
------------------------------------------------------------------------------------------------
This project's own literature review already concluded that "anomaly x uncertainty x sparsity"
observation-priority is **NOT a novel idea**. It is a simplified heuristic version of a published,
formally-optimised research area: optimising BGC-Argo distribution to minimise objective-mapping
uncertainty (JTECH 2023), optimal sensor placement via differentiable Gumbel-Softmax, adaptive
float sampling (FloatCast 2026). NOVELTY_MATRIX marks it "ALREADY DONE" and settles on the only
claim that is both true and defensible:

    a lightweight, interpretable heuristic that surfaces candidate regions,
    complementary to formal observing-system design

So this module is a REFINEMENT of an existing honest heuristic, not a new capability. It must never
be described as telling INCOIS or MoES where to deploy floats. The sanctioned phrasing is
"regions where additional observations may provide high scientific value".

WHAT CHANGES FROM v1
--------------------
v1 (`oceanembed.products.observation_priority`) multiplies anomaly, uncertainty and SPARSITY --
distance to the nearest float. Sparsity has a defect nobody can fix inside it: the places floats
are most absent are the places floats cannot GO. v1 duly ranked the Persian Gulf, 20 m deep, at the
top, and the fix had to be bolted on at the caller (`inference/predict.py:302-311`).

v2 replaces sparsity with EDDY KINETIC ENERGY. "Nobody has measured here" becomes "the ocean is
doing something here that a static picture will get wrong", which is a statement about the water
rather than about the observing network, and it cannot be maximised by a place no instrument can
reach.

    EKE = 1/2 (u'^2 + v'^2),   u' = u - <u>,  <.> a time mean

THE HONESTY LABEL THAT HAS TO TRAVEL WITH IT
u and v here are the model's INPUT channels -- COPERNICUS-GLOBCURRENT surface currents. They are
not something this model derived, and a page must say so. An EKE map is a fact about the current
product, and only the sigma factor is the model's own contribution.

TWO CHOICES THAT ARE NOT OBVIOUS
--------------------------------
THE MEAN IS OVER A WINDOW, NOT THE WHOLE RECORD. The North Indian Ocean reverses seasonally: the
Somali Current runs the other way between monsoons. Subtracting a full-record mean would leave the
entire monsoon reversal inside u', and the resulting "EKE" would be dominated by the seasonal cycle
rather than by eddies -- large everywhere the current reverses, which is most of the basin. A
centred window of ~30 days removes the seasonal mean flow and leaves the mesoscale.

THE FACTORS ARE NORMALISED BEFORE MULTIPLYING. sigma is in degC (order 1) and EKE in m^2/s^2 (order
0.01). A raw product is dominated by whichever has the wider dynamic range and would rank on EKE
alone. Each factor is scaled to [0,1] with 1st/99th-percentile clipping and combined as a geometric
mean -- deliberately the same method `observation_priority` uses, so v1 and v2 rank on the same
footing and a comparison between them means something. `test_priority_v2.py` pins that equivalence.
"""
from __future__ import annotations

import warnings

import numpy as np

from oceanembed import config as base

#: Days either side of the target date used to form the mean flow. See the module docstring for
#: why this is a window and not the whole record.
DEFAULT_WINDOW_DAYS = 30

#: The phrasing NOVELTY_MATRIX settled on. Kept here so a page cannot quietly invent a stronger one.
CLAIM = ("regions where additional observations may provide high scientific value")
NOT_A_CLAIM = ("This does not tell anyone where to deploy a float. It is an interpretable "
               "heuristic that surfaces candidate regions, complementary to -- not a substitute "
               "for -- formal observing-system design.")


def _norm01_robust(a, name: str) -> tuple[np.ndarray, bool]:
    """Scale to [0,1], NaN-preserving, 1st-99th percentile clipping.

    Mirrors `oceanembed.products.observation_priority._norm_factor` deliberately, including its
    treatment of a degenerate factor: a CONSTANT grid carries no information about where to
    observe, and min-max would map it to all-zeros and silently blank the whole product. All-ones
    -- i.e. neutral -- is returned instead, with a warning, so a missing input reads as missing
    rather than as "nowhere is interesting".
    """
    a = np.asarray(a, dtype="float64")
    if np.all(np.isnan(a)):
        warnings.warn(f"{name} is entirely NaN; treating it as neutral.", RuntimeWarning,
                      stacklevel=3)
        return np.ones_like(a), True
    lo, hi = np.nanpercentile(a, 1.0), np.nanpercentile(a, 99.0)
    if not np.isfinite(hi - lo) or hi <= lo:
        warnings.warn(f"{name} has no spatial variation, so it cannot rank locations. Treating it "
                      f"as NEUTRAL (all ones) rather than zeroing the whole map.",
                      RuntimeWarning, stacklevel=3)
        return np.ones_like(a), True
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0), False


def eddy_kinetic_energy(u, v, *, t_index: int | None = None,
                        window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """EKE = 1/2(u'^2 + v'^2) in m^2/s^2, from a (n_times, n_lat, n_lon) current record.

    u, v          : surface current components, m/s. These are MODEL INPUT channels, not anything
                    this model derived -- see the module docstring.
    t_index       : the day to evaluate. None returns the window-mean EKE over the whole record.
    window_days   : half-width of the centred window used to form the mean flow.

    Returns {"eke", "u_prime", "v_prime", "window", "n_steps_used", "mean_speed"}. `mean_speed`
    is |<u>| -- the mean flow itself -- so a caller can show that the high-EKE regions are NOT
    simply the fast ones.
    """
    u = np.asarray(u, dtype="float64")
    v = np.asarray(v, dtype="float64")
    if u.shape != v.shape:
        raise ValueError(f"u {u.shape} against v {v.shape}")
    if u.ndim != 3:
        raise ValueError(f"u is {u.shape}, expected (n_times, n_lat, n_lon)")

    n = u.shape[0]
    if t_index is None:
        lo, hi = 0, n
    else:
        lo = max(0, int(t_index) - int(window_days))
        hi = min(n, int(t_index) + int(window_days) + 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # all-NaN land columns
        u_bar = np.nanmean(u[lo:hi], axis=0)
        v_bar = np.nanmean(v[lo:hi], axis=0)
        up, vp = u[lo:hi] - u_bar, v[lo:hi] - v_bar
        eke = np.nanmean(0.5 * (up ** 2 + vp ** 2), axis=0)
    return {"eke": eke, "u_prime": up, "v_prime": vp, "window": (lo, hi),
            "n_steps_used": hi - lo, "mean_speed": np.hypot(u_bar, v_bar)}


def priority(sigma_2d, eke_2d, *, valid_mask=None, weights=(1.0, 1.0)) -> dict:
    """Priority = geometric mean of norm(sigma) and norm(EKE), on cells a float could occupy.

    sigma_2d   : the model's CALIBRATED per-cell uncertainty, degC. Depth-collapsed by the caller.
    eke_2d     : eddy kinetic energy, m^2/s^2, from `eddy_kinetic_energy`.
    valid_mask : (n_lat, n_lon, n_depths) from `predict_field`. Cells without water at the DEEPEST
                 level are excluded, because that is the guard v1 needed and did not have.

    THE GUARD IS THE POINT, AND IT IS APPLIED HERE RATHER THAN AT THE CALLER.
    v1 ranked the Persian Gulf -- about 20 m of water -- at the top, because a place no float can
    enter is by definition a place with no floats. The fix lives at v1's single call site
    (`inference/predict.py:302-311`), which means every NEW caller reintroduces the bug. Here it is
    a parameter of the product itself, and omitting it is a deliberate act that says so in the
    returned provenance rather than a silent default.
    """
    s = np.asarray(sigma_2d, dtype="float64")
    e = np.asarray(eke_2d, dtype="float64")
    if s.shape != e.shape:
        raise ValueError(f"sigma {s.shape} against eke {e.shape}")
    w = np.asarray(weights, dtype="float64")
    if w.shape != (2,) or np.any(w < 0) or w.sum() <= 0:
        raise ValueError(f"weights={weights}: expected two non-negative values, not all zero")

    n_before = int(np.isfinite(s).sum())
    guarded = False
    if valid_mask is not None:
        vm = np.asarray(valid_mask, dtype=bool)
        if vm.ndim != 3 or vm.shape[:2] != s.shape:
            raise ValueError(f"valid_mask is {vm.shape}, expected {s.shape + (-1,)}")
        deep_enough = vm[..., -1]
        s = np.where(deep_enough, s, np.nan)
        e = np.where(deep_enough, e, np.nan)
        guarded = True

    ns, s_neutral = _norm01_robust(s, "sigma")
    ne, e_neutral = _norm01_robust(e, "eke")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        # Geometric mean in log space, exactly as v1 does it: with a raw product the two factors
        # that rank a location are not weighted equally by the eye, and the map's dynamic range
        # collapses toward zero wherever either factor is small.
        logs = w[0] * np.log(np.clip(ns, 1e-6, None)) + w[1] * np.log(np.clip(ne, 1e-6, None))
        p = np.exp(logs / w.sum())
    p = np.where(np.isfinite(s) & np.isfinite(e), p, np.nan)

    return {
        "priority": p, "sigma_norm": ns, "eke_norm": ne,
        "guarded_by_valid_mask": guarded,
        "n_cells_ranked": int(np.isfinite(p).sum()),
        "n_cells_excluded_as_too_shallow": n_before - int(np.isfinite(p).sum()) if guarded else 0,
        "sigma_is_neutral": s_neutral, "eke_is_neutral": e_neutral,
        "weights": [float(x) for x in w],
        "claim": CLAIM, "not_a_claim": NOT_A_CLAIM,
    }


def top_cells(result: dict, k: int = 20, *, lat=None, lon=None) -> list[dict]:
    """The k highest-priority cells, most valuable first. [] when nothing is rankable.

    Returns [] rather than raising or padding: on a date where the guard excludes everything, "no
    candidate region" is the honest answer and a list of k arbitrary cells would not be.
    """
    p = np.asarray(result["priority"], dtype="float64")
    lat = np.asarray(base.LAT if lat is None else lat, dtype="float64")
    lon = np.asarray(base.LON if lon is None else lon, dtype="float64")
    finite = np.argwhere(np.isfinite(p))
    if finite.size == 0:
        return []
    vals = p[finite[:, 0], finite[:, 1]]
    order = np.argsort(-vals)[:int(k)]
    out = []
    for n in order:
        i, j = int(finite[n, 0]), int(finite[n, 1])
        out.append({"rank": len(out) + 1, "lat": float(lat[i]), "lon": float(lon[j]),
                    "i": i, "j": j, "priority": float(p[i, j]),
                    "sigma_norm": float(result["sigma_norm"][i, j]),
                    "eke_norm": float(result["eke_norm"][i, j])})
    return out
