"""Hard static-stability projection: a guarantee, not a penalty. Owner: Unit A (Arjhun).

WHAT THIS IS
------------
`models.tscast.stability_penalty` adds ReLU(-drho/dz) to the training loss. That is the standard
move -- it is TS-Cast's eq. 5 and it is what every paper in this specialisation does. A soft
penalty makes violations RARE. It cannot make them ABSENT, and no soft-constrained model can
report a violation count of zero without getting lucky.

This module does the other thing. It takes a profile the network has already emitted and returns
the NEAREST profile that is statically stable, by construction:

    rho      = EOS-80 density from predicted (S, T)
    rho*     = the L2-nearest non-decreasing-in-depth sequence   <- isotonic regression (PAVA)
    T*       = the temperature that, at the SAME salinity, has density rho*

After that, `stability_violations(rho*, DEPTHS)["n_violating"] == 0` is arithmetic, not a hope.

THE HONEST BOUNDARY, AND IT IS NOT SMALL
----------------------------------------
Density needs salinity. The SHIPPED deliverable is stage 1, which predicts temperature alone, so
**static stability is not a well-posed question about the shipped product** and this module refuses
to answer it there (`project_profile` raises on a None salinity rather than substituting one).

The tempting shortcut is to enforce dT/dz <= 0 instead -- monotone cooling downward -- and call it
stability. That would be WRONG IN THIS BASIN SPECIFICALLY. Temperature inversions under the Bay of
Bengal barrier layer are real, documented, and are a feature this project already measures
(`physics.layers.barrier_layer`). A monotone-temperature projection would delete them and report a
"guarantee" purchased by destroying a physical signal. So: stage 2 or nothing, and the refusal is
the same one `physics_page` already makes about MLD.

WHY ISOTONIC REGRESSION AND NOT A CLIP OR A SORT
------------------------------------------------
Three candidates enforce non-decreasing density, and only one is the nearest such profile:

  * sorting the column    -- non-decreasing, but it PERMUTES levels: the 500 m value can end up
                             at 100 m. It is a different profile, not a corrected one.
  * cumulative maximum    -- non-decreasing, but it only ever pushes values UP, so a single
                             too-dense level drags every level below it with it.
  * isotonic (PAVA)       -- the L2 projection onto the monotone cone. It is the unique nearest
                             non-decreasing sequence, it moves values both ways, and it changes
                             NOTHING where the profile was already stable.

The last property is what makes this safe to apply unconditionally: on an already-stable column
the operator is the identity, so it cannot degrade a profile that had nothing wrong with it.

TWO GUARDS THAT ARE LOAD-BEARING
--------------------------------
1. **Inverting density back to temperature assumes drho/dT < 0**, and that is not true everywhere
   in the ocean: fresh water has its density maximum near 4 degC, so below that, cooling makes
   water LIGHTER. This basin's surface salinity reaches 1.64 psu in the Ganges-Meghna plume
   (measured, `sound_speed_in_range`), so the assumption cannot be waved through. `_invert_one`
   checks the sign of drho/dT across the bracket and returns NaN with a reason rather than a
   confident wrong root.
2. **The guarantee is re-verified, not asserted.** `project_profile` recomputes density from the
   projected (S, T*) and counts violations again. If the round trip does not come back clean the
   result carries `verified: False` and the caller is expected to refuse it. A guarantee that is
   only proved on paper is a penalty with better marketing.
"""
from __future__ import annotations

import numpy as np

from phase2.physics import seawater
from phase2.tscast_nio import config as _c

#: Depth axis these functions default to, in metres, shallow -> deep.
DEPTHS = np.asarray(_c.DEPTHS, dtype="float64")

#: Bracket for the temperature root-find, degC. Wider than any water in this basin (the measured
#: range is roughly 4 to 35 degC) so a real profile is never at the edge, and narrow enough that
#: bisection converges in ~40 iterations to well below float32 noise.
T_BRACKET = (-3.0, 40.0)

#: Root-find tolerance in degC.
#:
#: THIS WAS 1e-6 AND IT BROKE THE GUARANTEE. Isotonic regression pools violating levels to a
#: block mean, so a pooled pair has EXACTLY equal density and a gradient of exactly zero. Round-
#: tripping that through a temperature inversion accurate to only 1e-6 degC perturbs density by
#: |drho/dT| * 1e-6 ~ 3e-7 kg m-3, which over a 5 m gap is ~6e-8 kg m-3 m-1 -- and half of those
#: perturbations land on the negative side of an exactly-flat pair. Measured on the real stage-2
#: prediction: 395 of 401 "surviving violations" were this artifact, at a median magnitude of
#: 1.3e-8. The physics was right and the arithmetic was not.
#:
#: 1e-11 costs about sixteen more bisection steps (43 degC bracket, 43/2^42 ~ 1e-11) and puts the
#: round-trip density error at ~3e-12 kg m-3, which is three orders below DRHO_DZ_EPS.
T_TOL = 1e-11

#: A density gradient more negative than this counts as a violation. Exactly 0.0 would make
#: floating-point equality a physical claim; this is one part in a million of a kg m-3 per metre,
#: which is far below any real stratification and far above float64 round-off.
DRHO_DZ_EPS = -1e-9

#: EOS-80's S**1.5 term is NaN below zero and one NaN poisons a whole column. The same floor
#: `density_nll` and `stability_penalty` already use, for the same reason.
S_FLOOR = 0.0


def isotonic_nondecreasing(y, w=None):
    """Pool-Adjacent-Violators. Returns the L2-nearest non-decreasing sequence to `y`.

    This is the whole novelty in fifteen lines: minimise sum_i w_i (y*_i - y_i)^2 subject to
    y*_1 <= y*_2 <= ... <= y*_n. PAVA solves it exactly in O(n), not approximately.

    Written here rather than imported from scikit-learn because `requirements.txt` belongs to
    Unit B and this is fifteen lines -- but `tests/phase2/test_stability.py` pins it against
    `sklearn.isotonic.IsotonicRegression` on random data, so a transcription error cannot hide.

    Args:
        y: 1-D sequence, ordered shallow -> deep.
        w: optional positive weights. Default: uniform, i.e. nearest in plain density L2. Weighting
           by layer thickness would instead give "nearest in a depth-integrated sense" -- a
           different and also defensible choice, exposed rather than decided silently.
    """
    y = np.asarray(y, dtype="float64")
    if y.ndim != 1:
        raise ValueError(f"isotonic_nondecreasing expects 1-D, got shape {y.shape}")
    n = y.size
    if n == 0:
        return y.copy()
    w = np.ones(n) if w is None else np.asarray(w, dtype="float64")
    if w.shape != y.shape:
        raise ValueError(f"weights {w.shape} do not match values {y.shape}")
    if np.any(w <= 0):
        raise ValueError("isotonic weights must be strictly positive")
    if not np.all(np.isfinite(y)):
        raise ValueError("isotonic_nondecreasing needs finite values; mask first")

    # Each block holds (weighted mean, total weight, length). Merge backwards while the previous
    # block's mean exceeds this one's -- that is the "adjacent violator" being pooled.
    means, weights, counts = [], [], []
    for i in range(n):
        m, ww, cc = y[i], w[i], 1
        while means and means[-1] > m:
            pm, pw, pc = means.pop(), weights.pop(), counts.pop()
            m = (pm * pw + m * ww) / (pw + ww)
            ww += pw
            cc += pc
        means.append(m)
        weights.append(ww)
        counts.append(cc)
    return np.repeat(np.asarray(means), np.asarray(counts))


def stability_violations(rho, depths=None, mask=None) -> dict:
    """Count where density DECREASES downward. This is the number nobody in this field reports.

    Args:
        rho:    (..., n_levels) potential density, shallow -> deep.
        depths: matching depth axis in metres. Defaults to the project's 15 standard depths.
        mask:   (..., n_levels) bool, True where the level is real water. Pairs touching a masked
                level are not counted at all -- a gap is not a violation and is not a pass either.

    Returns a dict with the count, the fraction, the worst gradient, and the total density
    inversion (the summed magnitude of the negative gradients, kg m-3 m-1). The last one matters:
    a hundred violations of 1e-8 and one of 0.5 are very different failures and a bare count
    conflates them.
    """
    rho = np.asarray(rho, dtype="float64")
    depths = DEPTHS if depths is None else np.asarray(depths, dtype="float64")
    if rho.shape[-1] != depths.size:
        raise ValueError(f"rho has {rho.shape[-1]} levels, depths has {depths.size}")

    dz = np.diff(depths)
    if np.any(dz <= 0):
        raise ValueError("depths must be strictly increasing, shallow -> deep")

    drho = np.diff(rho, axis=-1) / dz
    pair_ok = np.isfinite(drho)
    if mask is not None:
        mask = np.asarray(mask, bool)
        pair_ok &= mask[..., 1:] & mask[..., :-1]

    bad = pair_ok & (drho < DRHO_DZ_EPS)
    n_pairs = int(pair_ok.sum())
    n_bad = int(bad.sum())
    worst = float(np.min(np.where(bad, drho, np.inf))) if n_bad else 0.0
    return {
        "n_pairs": n_pairs,
        "n_violating": n_bad,
        "fraction": (n_bad / n_pairs) if n_pairs else float("nan"),
        "worst_drho_dz": worst,
        "total_inversion": float(np.sum(np.where(bad, -drho, 0.0))),
        "n_profiles_with_violation": int(np.any(bad, axis=-1).sum()) if rho.ndim > 1 else int(n_bad > 0),
    }


def _drho_dT(s, t, h=1e-4):
    """Central difference of EOS-80 density with respect to temperature."""
    return (seawater.density(s, t + h) - seawater.density(s, t - h)) / (2.0 * h)


def _invert_one(rho_target, s, lo=T_BRACKET[0], hi=T_BRACKET[1], tol=None):
    """Temperature with density `rho_target` at salinity `s`. Returns (t, reason_or_None).

    Bisection rather than Newton: EOS-80 is a fifth-order polynomial in t and Newton can leave the
    physical bracket on a bad step, which would return a mathematically valid root that is not
    seawater. Bisection cannot.

    THE MONOTONICITY GUARD IS NOT DECORATION. rho is monotone DECREASING in t only above the
    temperature of maximum density, which for fresh water is near 4 degC. This basin's surface
    salinity reaches 1.64 psu in the Ganges-Meghna plume, so the fresh-water case is reachable and
    the sign is checked rather than assumed.
    """
    # Read at CALL time, not bound as a default at import time. `tol=T_TOL` in the signature meant
    # the module constant was frozen the moment this file was imported: changing ST.T_TOL had no
    # effect whatsoever, so the test asserting the tolerance is load-bearing was asserting nothing
    # and passed for the wrong reason. A constant that cannot be changed by changing it is not a
    # parameter, it is a literal with a misleading name.
    tol = T_TOL if tol is None else float(tol)
    if not np.isfinite(rho_target) or not np.isfinite(s):
        return np.nan, "non-finite input"
    s = max(float(s), S_FLOOR)

    f_lo = seawater.density(s, lo) - rho_target     # heaviest end of the bracket
    f_hi = seawater.density(s, hi) - rho_target     # lightest end
    if not (np.isfinite(f_lo) and np.isfinite(f_hi)):
        return np.nan, "EOS-80 non-finite at bracket"

    # Both derivative ends must be negative, or the mapping rho -> t is not one-to-one here and
    # any root we return would be one of two.
    if _drho_dT(s, lo) >= 0 or _drho_dT(s, hi) >= 0:
        return np.nan, "drho/dT not strictly negative across bracket (fresh-water regime)"
    if f_lo * f_hi > 0:
        return np.nan, "target density outside the temperature bracket"

    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = seawater.density(s, mid) - rho_target
        if hi - lo < tol:
            return mid, None
        if (f_lo < 0) == (f_mid < 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return 0.5 * (lo + hi), None


def project_profile(temperature, salinity, depths=None, mask=None, weights=None) -> dict:
    """Project ONE (T, S) profile onto the nearest statically stable one, at fixed salinity.

    Returns a dict carrying the projected temperature, the density before and after, the violation
    counts before and after, the temperature change applied, and `verified` -- which is the result
    of RE-COUNTING violations on the round-tripped density rather than trusting the algebra.

    Raises on a None salinity. Stage 1 predicts temperature alone; a temperature-only static
    stability check is not a weaker version of this, it is a different and wrong claim (see the
    module docstring on Bay of Bengal temperature inversions).
    """
    if salinity is None:
        raise ValueError(
            "static stability needs salinity at depth, and stage 1 predicts temperature alone. "
            "This is the same boundary physics_page draws for MLD: refused, not approximated. "
            "Use a stage-2 prediction, or GLORYS salinity in an explicitly-labelled comparison.")

    depths = DEPTHS if depths is None else np.asarray(depths, dtype="float64")
    t = np.asarray(temperature, dtype="float64").copy()
    s = np.asarray(salinity, dtype="float64")
    if t.shape != s.shape or t.shape[-1] != depths.size:
        raise ValueError(f"T {t.shape} / S {s.shape} must match and end in {depths.size} levels")

    valid = np.isfinite(t) & np.isfinite(s)
    if mask is not None:
        valid &= np.asarray(mask, bool)

    rho = np.full(t.shape, np.nan)
    rho[valid] = seawater.density(np.maximum(s[valid], S_FLOOR), t[valid])
    before = stability_violations(rho, depths, mask=valid)

    t_star = t.copy()
    rho_star = rho.copy()
    reasons: list[str] = []

    idx = np.flatnonzero(valid)
    if idx.size >= 2:
        w = None if weights is None else np.asarray(weights, dtype="float64")[idx]
        rho_fit = isotonic_nondecreasing(rho[idx], w)
        rho_star[idx] = rho_fit
        for k, lev in enumerate(idx):
            if rho_fit[k] == rho[lev]:
                continue                                  # PAVA left this level alone
            t_new, why = _invert_one(rho_fit[k], s[lev])
            if why is not None:
                # REFUSE THE LEVEL. The first version kept the original temperature here, which
                # silently restored the ORIGINAL density -- and therefore the original violation.
                # Measured on real stage-2 output that left 5 genuine violations standing inside a
                # function whose whole promise is that there are none. A guarantee with a quiet
                # exception is not a guarantee; a gap that names its reason is honest.
                reasons.append(f"level {int(lev)}: {why}")
                t_star[lev] = np.nan
                rho_star[lev] = np.nan
                continue
            t_star[lev] = t_new

    # THE VERIFICATION. Recompute density from what we are actually returning.
    rho_round = np.full(t.shape, np.nan)
    v2 = valid & np.isfinite(t_star)
    rho_round[v2] = seawater.density(np.maximum(s[v2], S_FLOOR), t_star[v2])
    after = stability_violations(rho_round, depths, mask=v2)

    dt = np.where(valid, t_star - t, np.nan)
    return {
        "temperature": t_star,
        "temperature_in": t,
        "salinity": s,
        "density_in": rho,
        "density_isotonic": rho_star,
        "density_out": rho_round,
        "violations_before": before,
        "violations_after": after,
        "verified": after["n_violating"] == 0,
        "n_levels_changed": int(np.sum(np.abs(dt) > T_TOL)),
        "max_abs_dT": float(np.nanmax(np.abs(dt))) if np.any(np.isfinite(dt)) else 0.0,
        "mean_abs_dT": float(np.nanmean(np.abs(dt))) if np.any(np.isfinite(dt)) else 0.0,
        "refusals": reasons,
    }


def project_many(temperature, salinity, depths=None, mask=None) -> dict:
    """`project_profile` over a stack of profiles, shape (N, n_levels).

    Loops rather than vectorising: the root-find is per level and per profile, PAVA is inherently
    sequential, and at the scale this runs (thousands of profiles, milliseconds each) a clever
    vectorisation would buy nothing and would be a second implementation to keep in step with the
    scalar one -- the drift this project has already been bitten by five times.
    """
    T = np.atleast_2d(np.asarray(temperature, dtype="float64"))
    S = np.atleast_2d(np.asarray(salinity, dtype="float64"))
    depths = DEPTHS if depths is None else np.asarray(depths, dtype="float64")
    M = None if mask is None else np.atleast_2d(np.asarray(mask, bool))

    out_t = np.full(T.shape, np.nan)
    n_changed = np.zeros(T.shape[0], dtype=int)
    refusals: list[str] = []
    verified = np.ones(T.shape[0], dtype=bool)

    for i in range(T.shape[0]):
        r = project_profile(T[i], S[i], depths, None if M is None else M[i])
        out_t[i] = r["temperature"]
        n_changed[i] = r["n_levels_changed"]
        verified[i] = r["verified"]
        refusals.extend(f"profile {i}: {x}" for x in r["refusals"])

    valid = np.isfinite(T) & np.isfinite(S)
    if M is not None:
        valid &= M
    rho_in = np.full(T.shape, np.nan)
    rho_in[valid] = seawater.density(np.maximum(S[valid], S_FLOOR), T[valid])
    rho_out = np.full(T.shape, np.nan)
    v2 = valid & np.isfinite(out_t)
    rho_out[v2] = seawater.density(np.maximum(S[v2], S_FLOOR), out_t[v2])

    return {
        "temperature": out_t,
        "violations_before": stability_violations(rho_in, depths, mask=valid),
        "violations_after": stability_violations(rho_out, depths, mask=v2),
        "verified": bool(verified.all()),
        "n_profiles_verified": int(verified.sum()),
        "n_profiles": int(T.shape[0]),
        "n_levels_changed": int(n_changed.sum()),
        "n_profiles_changed": int((n_changed > 0).sum()),
        "refusals": refusals,
    }
