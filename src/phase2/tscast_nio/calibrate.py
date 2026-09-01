"""Phase 6: post-hoc per-depth uncertainty calibration.

THE PROBLEM  [MEASURED, not assumed]
The beta-NLL head already beats MC-dropout on the RMSE/RMS(sigma) ratio (0.70-1.86 against
1.56-3.54). But that ratio is not calibration. Empirical +/-1 sigma coverage comes out 0.44-0.82
against the 0.683 a Gaussian requires -- too NARROW in the mixed layer and thermocline, too WIDE at
1000 m. A ratio near 1 pooled over depths can hide exactly that, which is why coverage is the
number this phase reports.

THE METHOD
Per-depth variance scaling: sigma_cal(d) = s(d) * sigma_raw(d). For a Gaussian, the s that
minimises negative log-likelihood has a closed form -- no optimiser, no learning rate, nothing to
tune:

    minimise  sum[ z^2 / (2 s^2) + log(s) ]   where z = (y - mu) / sigma_raw
    d/ds = 0  ->  s = sqrt( mean(z^2) )

So s(d) is the RMS of the standardised residual at that depth. s > 1 widens an overconfident
sigma; s < 1 narrows an underconfident one.

THE RULE THAT MAKES IT HONEST
s is fitted on the TRAIN-WINDOW Argo profiles and evaluated on the TEST-WINDOW ones. Fitting on the
test profiles would drive coverage to 0.683 by construction and the number would mean nothing --
it would be reporting how well a scale factor fits the data it was fitted to. The two sets are
disjoint in time by the same embargo the model itself respects.
"""
from __future__ import annotations

import numpy as np

from phase2.tscast_nio import config

# A depth needs enough profiles for a coverage fraction to mean anything. Below this the depth is
# reported with its count and NOT calibrated, rather than given a scale factor from a handful of
# floats.
MIN_N = 50


def standardised_residuals(mu, sigma, truth):
    """z = (truth - mu) / sigma, per depth. NaN where any of the three is missing."""
    mu = np.asarray(mu, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    truth = np.asarray(truth, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (truth - mu) / sigma
    z[~np.isfinite(z)] = np.nan
    return z


# Gaussian +/-1 sigma. The quantile method targets this directly.
COV1_TARGET = 0.6826895


def fit_scales(mu, sigma, truth, method: str = "coverage") -> dict:
    """Per-depth scale factors from the CALIBRATION set. Closed form, nothing to tune.

    Two methods, and they DISAGREE on real data -- which is a result, not an inconvenience:

    "variance"  s = sqrt(mean(z^2)).  NLL-optimal FOR A GAUSSIAN: it matches the second moment.
                MEASURED on the T_SEQ=31 checkpoint this drove +/-2 sigma coverage to 0.960
                (target 0.954, near perfect) but overshot +/-1 sigma to 0.774 (target 0.683).

                That gap is the residuals telling us they are HEAVY-TAILED. Rescaling a
                heavy-tailed distribution to unit variance leaves MORE mass inside +/-1 sigma than
                a Gaussian has, because the variance is carried disproportionately by the tails.
                So matching the variance necessarily overshoots central coverage.

    "coverage"  s = the 68.27th percentile of |z|.  Targets the number section 11 of the build plan
                actually asks for, and does not assume the residuals are Gaussian.

    Default is "coverage" because that is the stated goal. "variance" is kept so the two can be
    compared rather than one being quietly assumed equivalent to the other.
    """
    if method not in ("variance", "coverage"):
        raise ValueError(f"method must be 'variance' or 'coverage', got {method!r}")
    z = standardised_residuals(mu, sigma, truth)
    scales, counts = {}, {}
    for k, d in enumerate(config.DEPTHS):
        col = z[:, k]
        ok = np.isfinite(col)
        counts[int(d)] = int(ok.sum())
        if ok.sum() < MIN_N:
            scales[int(d)] = None            # not enough data to calibrate; say so, do not guess
            continue
        v = col[ok]
        scales[int(d)] = (float(np.sqrt(np.mean(v ** 2))) if method == "variance"
                          else float(np.percentile(np.abs(v), 100.0 * COV1_TARGET)))
    return {"scales": scales, "n": counts, "min_n": MIN_N, "method": method}


def apply_scales(sigma, scales: dict) -> np.ndarray:
    """sigma_cal = s(d) * sigma. Depths with no scale are left UNCHANGED, not dropped."""
    out = np.array(sigma, dtype="float64", copy=True)
    for k, d in enumerate(config.DEPTHS):
        s = scales.get(int(d))
        if s is not None:
            out[:, k] *= s
    return out


def coverage(mu, sigma, truth) -> dict:
    """Empirical +/-1 and +/-2 sigma coverage per depth. Gaussian targets 0.683 and 0.954."""
    z = np.abs(standardised_residuals(mu, sigma, truth))
    out = {}
    for k, d in enumerate(config.DEPTHS):
        col = z[:, k]
        ok = np.isfinite(col)
        if ok.sum() == 0:
            out[int(d)] = {"n": 0, "cov1": None, "cov2": None}
            continue
        c = col[ok]
        out[int(d)] = {"n": int(ok.sum()),
                       "cov1": round(float((c <= 1.0).mean()), 4),
                       "cov2": round(float((c <= 2.0).mean()), 4)}
    return out


def pit(mu, sigma, truth, bins: int = 10) -> dict:
    """PIT histogram. Under a correct Gaussian the values are UNIFORM on [0,1].

    Shape is diagnostic in a way a single coverage number is not:
      U-shaped  -> sigma too narrow (too many values in the tails)
      humped    -> sigma too wide
      sloped    -> a BIAS in the mean, which no variance scaling can fix
    """
    from math import erf, sqrt
    z = standardised_residuals(mu, sigma, truth).ravel()
    z = z[np.isfinite(z)]
    if z.size == 0:
        return {"bins": bins, "counts": [], "uniform_deviation": None, "n": 0}
    p = np.array([0.5 * (1.0 + erf(v / sqrt(2.0))) for v in z])
    counts, _ = np.histogram(p, bins=bins, range=(0.0, 1.0))
    frac = counts / counts.sum()
    return {"bins": bins,
            "counts": counts.tolist(),
            "fraction": [round(float(f), 4) for f in frac],
            # mean |observed - uniform| per bin; 0 is perfect, ~0.1+ is badly miscalibrated
            "uniform_deviation": round(float(np.abs(frac - 1.0 / bins).mean()), 4),
            "n": int(z.size)}


def summarise(cov: dict) -> dict:
    """Overall coverage across depths that have enough samples to count."""
    c1 = [v["cov1"] for v in cov.values() if v["cov1"] is not None and v["n"] >= MIN_N]
    c2 = [v["cov2"] for v in cov.values() if v["cov2"] is not None and v["n"] >= MIN_N]
    if not c1:
        return {"cov1_mean": None, "cov2_mean": None, "cov1_range": None}
    return {"cov1_mean": round(float(np.mean(c1)), 4),
            "cov2_mean": round(float(np.mean(c2)), 4),
            "cov1_range": [round(min(c1), 4), round(max(c1), 4)],
            "cov2_range": [round(min(c2), 4), round(max(c2), 4)],
            "target_cov1": 0.683, "target_cov2": 0.954,
            "n_depths_counted": len(c1)}
