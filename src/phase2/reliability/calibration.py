"""F4 — post-hoc recalibration of the model's uncertainty. Owner: Unit A (Arjhun).

THE PROBLEM THIS FIXES (D-016, measured in Phase 1, still open)
---------------------------------------------------------------
MC-dropout reports sigma ~0.30 degC at 75 m while the error against real Argo floats is
1.22 degC — a ~4x underestimate, at the depth where the model is weakest. Overconfidence is
the dangerous direction: a judge who checks one value against a float finds us confidently
wrong. The baseline's response was to stop showing the spread and show measured error instead.
This module goes further and makes the spread itself trustworthy.

METHOD — variance (std) scaling
-------------------------------
Post-hoc rescaling of predicted standard deviations by a factor fitted on held-out data. It
leaves the mean prediction untouched and keeps the predictive distribution Gaussian, so nothing
downstream changes shape.

  Levi, Gispan, Giladi & Fetaya, "Evaluating and Calibrating Uncertainty Prediction in
  Regression Tasks" (2022) — std-scaling, and the ENCE metric used here.
  Kuleshov, Fenner & Ermon, "Accurate Uncertainties for Deep Learning Using Calibrated
  Regression", ICML 2018 (PMLR v80) — the earlier isotonic-regression recalibration.
  https://proceedings.mlr.press/v80/kuleshov18a/kuleshov18a.pdf

Minimising the Gaussian negative log-likelihood w.r.t. a single scalar a gives a closed form:

    a^2 = (1/n) * sum_i ( residual_i^2 / sigma_i^2 )            [needs PER-SAMPLE data]

We fit one factor PER DEPTH, because the miscalibration is depth-dependent by nature: it is
worst at the thermocline and mild at the surface, so a single global factor would over-correct
the surface while under-correcting 75-150 m.

ENCE (Levi et al.), the calibration metric reported here:

    ENCE = (1/N_bin) * sum_j | RMV_j - RMSE_j | / RMV_j
    RMV_j  = sqrt( mean( sigma_i^2 ) for i in bin j )
    RMSE_j = sqrt( mean( residual_i^2 ) for i in bin j )

with samples sorted by sigma into equally-sized bins. 0 is perfect; it is scale-free, so it can
be compared across depths whose error magnitudes differ by an order of magnitude.

TWO ENTRY POINTS, AND THE DIFFERENCE MATTERS
--------------------------------------------
`fit_from_samples`  — per-sample residuals and sigmas. Supports a real fit/evaluate split and
                      ENCE. **This is the rigorous path.**
`fit_from_summary`  — only per-depth aggregate RMSE (what artifacts/argo_error_by_depth.json
                      stores). Moment-matching only: a_d = RMSE_d / RMV_d. **It cannot be held
                      out**, because a summary carries no per-sample identity to split on, so
                      the resulting factors are DESCRIPTIVE, not validated. Marked as such in
                      the returned record and refused by `CalibrationResult.is_validated`.

Fitting and evaluating on the same profiles would make any calibration look perfect. That is the
same discipline Unit B used for the SSH bias offset: fit on train dates, verify against the test
period, and only then believe it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from oceanembed import config

# Below this many matched observations a per-depth factor is fitted but flagged unreliable.
# Argo rarely samples at exactly 0 m, so the shallowest level routinely has tens of points
# against ~2,400 elsewhere (Phase-1 finding, docs/DATA_CONTRACT.md).
MIN_OBS_PER_DEPTH = 100

# Guard against a degenerate fit: a depth whose sigma is ~0 would give an unbounded factor.
_EPS = 1e-9


@dataclass
class CalibrationResult:
    """Per-depth scaling factors plus the evidence for whether they can be believed."""

    alphas: np.ndarray                      # (15,) multiply sigma by this
    depths: list = field(default_factory=lambda: list(config.DEPTHS))
    method: str = "std-scaling (Levi et al. 2022)"
    fitted_on: str = ""
    evaluated_on: str = ""
    n_per_depth: list | None = None
    ence_before: float | None = None
    ence_after: float | None = None
    ratio_before: np.ndarray | None = None  # sigma / actual RMSE, per depth
    ratio_after: np.ndarray | None = None
    held_out: bool = False
    unreliable_depths: list = field(default_factory=list)
    note: str = ""

    @property
    def is_validated(self) -> bool:
        """True only if factors were evaluated on data they were NOT fitted on.

        A summary-only fit is descriptive. Never let it be reported as validated —
        PHASE2_STATUS.md separates TESTED from VALIDATED for exactly this reason.
        """
        return bool(self.held_out and self.ence_after is not None)

    def apply(self, sigma: np.ndarray) -> np.ndarray:
        """sigma (..., 15) -> calibrated sigma. Mean predictions are untouched."""
        sigma = np.asarray(sigma, dtype="float32")
        assert sigma.shape[-1] == len(self.alphas), (
            f"last axis must be {len(self.alphas)} depths, got {sigma.shape}"
        )
        return (sigma * self.alphas.astype("float32")).astype("float32")

    def summary(self) -> str:
        lines = [f"Calibration — {self.method}",
                 f"  fitted on   : {self.fitted_on}",
                 f"  evaluated on: {self.evaluated_on or 'NOT EVALUATED'}",
                 f"  held out    : {self.held_out}   validated: {self.is_validated}"]
        if self.ence_before is not None:
            lines.append(f"  ENCE  {self.ence_before:.4f} -> {self.ence_after:.4f}"
                         if self.ence_after is not None else
                         f"  ENCE  {self.ence_before:.4f}")
        lines.append(f"  {'depth':>7}{'alpha':>9}{'ratio_before':>14}{'ratio_after':>13}{'n':>8}")
        for k, d in enumerate(self.depths):
            rb = "  -" if self.ratio_before is None else f"{self.ratio_before[k]:14.3f}"
            ra = "  -" if self.ratio_after is None else f"{self.ratio_after[k]:13.3f}"
            n = "" if self.n_per_depth is None else f"{self.n_per_depth[k]:8d}"
            flag = "  <- too few obs" if d in self.unreliable_depths else ""
            lines.append(f"  {d:>7}{self.alphas[k]:9.3f}{rb}{ra}{n}{flag}")
        if self.note:
            lines += ["", "  " + self.note]
        return "\n".join(lines)


# --------------------------------------------------------------------------- metrics
def ence(residuals: np.ndarray, sigmas: np.ndarray, n_bins: int = 10) -> float:
    """Expected Normalized Calibration Error (Levi et al. 2022) for ONE depth.

    Samples are sorted by sigma into equally-sized bins; each bin compares its root-mean-variance
    against its RMSE. Scale-free, so 0 m and 1000 m are directly comparable.

    Returns NaN if there are too few finite samples to bin meaningfully.
    """
    r = np.asarray(residuals, dtype="float64").ravel()
    s = np.asarray(sigmas, dtype="float64").ravel()
    assert r.shape == s.shape, f"residuals {r.shape} and sigmas {s.shape} must match"

    ok = np.isfinite(r) & np.isfinite(s) & (s > _EPS)
    r, s = r[ok], s[ok]
    if len(r) < max(2 * n_bins, 10):
        return float("nan")

    order = np.argsort(s)
    r, s = r[order], s[order]

    total = 0.0
    counted = 0
    for b in np.array_split(np.arange(len(r)), n_bins):
        if len(b) == 0:
            continue
        rmv = np.sqrt(np.mean(s[b] ** 2))
        rmse = np.sqrt(np.mean(r[b] ** 2))
        if rmv > _EPS:
            total += abs(rmv - rmse) / rmv
            counted += 1
    return float(total / counted) if counted else float("nan")


def ence_by_depth(residuals: np.ndarray, sigmas: np.ndarray, n_bins: int = 10) -> np.ndarray:
    """(N, 15) -> (15,) ENCE per depth."""
    residuals = np.asarray(residuals, dtype="float64")
    sigmas = np.asarray(sigmas, dtype="float64")
    assert residuals.shape == sigmas.shape and residuals.ndim == 2
    return np.array([ence(residuals[:, k], sigmas[:, k], n_bins)
                     for k in range(residuals.shape[1])], dtype="float32")


def _ratio_by_depth(residuals: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
    """sigma / actual RMSE, per depth. <1 = overconfident.

    Same quantity as the baseline's uncertainty.calibration_ratio, but that function takes
    (y_true, y_pred); here we already hold residuals, so we avoid inventing a fake y_true just
    to satisfy a signature.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        rmse = np.sqrt(np.nanmean(residuals ** 2, axis=0))
        return (np.nanmean(sigmas, axis=0) / np.maximum(rmse, _EPS)).astype("float32")


# --------------------------------------------------------------------------- fitting
def _alpha_from_samples(residuals: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
    """Closed-form NLL-optimal std-scaling factor per depth: a^2 = mean(res^2 / sigma^2)."""
    r = np.asarray(residuals, dtype="float64")
    s = np.asarray(sigmas, dtype="float64")
    out = np.ones(r.shape[1], dtype="float32")
    for k in range(r.shape[1]):
        ok = np.isfinite(r[:, k]) & np.isfinite(s[:, k]) & (s[:, k] > _EPS)
        if ok.sum() == 0:
            continue  # leave at 1.0 = no change, rather than inventing a factor
        out[k] = float(np.sqrt(np.mean((r[ok, k] / s[ok, k]) ** 2)))
    return out


def fit_from_samples(residuals: np.ndarray, sigmas: np.ndarray, *,
                     fit_frac: float = 0.5, seed: int = config.SEED,
                     n_bins: int = 10, label: str = "per-sample") -> CalibrationResult:
    """RIGOROUS PATH. Fit std-scaling on one split, evaluate on the other.

    residuals : (N, 15) prediction - truth, real degC
    sigmas    : (N, 15) the model's UNCALIBRATED spread

    Rows are split, so a profile used to fit never appears in the evaluation. Reported ENCE and
    calibration ratios are therefore honest out-of-sample numbers.
    """
    residuals = np.asarray(residuals, dtype="float64")
    sigmas = np.asarray(sigmas, dtype="float64")
    assert residuals.shape == sigmas.shape, "residuals and sigmas must have the same shape"
    assert residuals.ndim == 2 and residuals.shape[1] == config.N_DEPTHS, (
        f"expected (N, {config.N_DEPTHS}), got {residuals.shape}"
    )
    assert 0.0 < fit_frac < 1.0, "fit_frac must leave data for evaluation"
    assert len(residuals) >= 4, "need at least 4 rows to split"

    idx = np.random.default_rng(seed).permutation(len(residuals))
    n_fit = max(1, int(len(idx) * fit_frac))
    fit_i, eval_i = idx[:n_fit], idx[n_fit:]

    alphas = _alpha_from_samples(residuals[fit_i], sigmas[fit_i])

    ev_r, ev_s = residuals[eval_i], sigmas[eval_i]
    n_per_depth = [int(v) for v in (np.isfinite(ev_r) & np.isfinite(ev_s)).sum(axis=0)]

    ratio_before = _ratio_by_depth(ev_r, ev_s)
    ratio_after = _ratio_by_depth(ev_r, ev_s * alphas)
    ence_before = float(np.nanmean(ence_by_depth(ev_r, ev_s, n_bins)))
    ence_after = float(np.nanmean(ence_by_depth(ev_r, ev_s * alphas, n_bins)))

    return CalibrationResult(
        alphas=alphas,
        fitted_on=f"{len(fit_i)} rows ({label})",
        evaluated_on=f"{len(eval_i)} held-out rows ({label})",
        n_per_depth=n_per_depth,
        ence_before=ence_before, ence_after=ence_after,
        ratio_before=ratio_before, ratio_after=ratio_after,
        held_out=True,
        unreliable_depths=[int(config.DEPTHS[k]) for k, n in enumerate(n_per_depth)
                           if n < MIN_OBS_PER_DEPTH],
    )


def fit_from_summary(rmse_by_depth, sigma_by_depth, *,
                     n_obs_per_depth=None, source: str = "summary") -> CalibrationResult:
    """WEAK PATH. Moment-matching from per-depth aggregates: a_d = RMSE_d / RMV_d.

    This is what artifacts/argo_error_by_depth.json makes possible, because it stores aggregate
    per-depth RMSE rather than per-sample residuals.

    **The result is DESCRIPTIVE, never validated.** A summary has no per-sample identity, so there
    is nothing to hold out: the factors are fitted on exactly the numbers they would be scored
    against, which would make any calibration look perfect. `is_validated` returns False, and
    ENCE is left as None because it requires per-sample binning.

    To upgrade this to the rigorous path, persist per-profile residuals and sigmas alongside the
    aggregate — see docs/phase2/f4-reliability.md.
    """
    rmse = np.asarray(rmse_by_depth, dtype="float64")
    rmv = np.asarray(sigma_by_depth, dtype="float64")
    assert rmse.shape == rmv.shape == (config.N_DEPTHS,), (
        f"expected ({config.N_DEPTHS},) arrays, got {rmse.shape} and {rmv.shape}"
    )

    alphas = np.ones(config.N_DEPTHS, dtype="float32")
    ok = np.isfinite(rmse) & np.isfinite(rmv) & (rmv > _EPS)
    alphas[ok] = (rmse[ok] / rmv[ok]).astype("float32")

    with np.errstate(invalid="ignore", divide="ignore"):
        ratio_before = (rmv / np.maximum(rmse, _EPS)).astype("float32")

    n_list = None if n_obs_per_depth is None else [int(v) for v in n_obs_per_depth]
    unreliable = ([] if n_list is None
                  else [int(config.DEPTHS[k]) for k, n in enumerate(n_list)
                        if n < MIN_OBS_PER_DEPTH])

    return CalibrationResult(
        alphas=alphas,
        method="moment-matching from per-depth aggregates (NOT held out)",
        fitted_on=source,
        evaluated_on="",
        n_per_depth=n_list,
        ratio_before=ratio_before,
        ratio_after=np.ones(config.N_DEPTHS, dtype="float32"),  # 1.0 BY CONSTRUCTION, not evidence
        held_out=False,
        unreliable_depths=unreliable,
        note=("DESCRIPTIVE ONLY. Fitted on the same aggregate it would be scored against, so "
              "ratio_after is 1.0 by construction and proves nothing. Not validated. Persist "
              "per-profile residuals + sigmas to use fit_from_samples instead."),
    )


# --------------------------------------------------------------------------- IO
def load_measured_error(path: str | None = None, source: str = "satellite") -> dict:
    """Read artifacts/argo_error_by_depth.json (written by scripts/eval_satellite_vs_argo.py).

    Returns {"rmse": (15,), "n_obs": (15,), "n_profiles": int, "meta": dict}.
    Raises with an actionable message if absent — this file is gitignored and lives only where
    the real Argo evaluation was run.
    """
    path = path or config.art("argo_error_by_depth.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found.\n"
            "It is written by `python scripts/eval_satellite_vs_argo.py` and is gitignored "
            "(/artifacts/*), so it exists only on the machine that ran the real Argo evaluation.\n"
            "F4 cannot report REAL calibration numbers without it."
        )

    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)

    key = f"rmse_{source}"
    assert key in d, f"{path} has no '{key}'; keys are {sorted(d)}"
    assert list(d.get("depths", [])) == list(config.DEPTHS), (
        "depth axis in the error file does not match config.DEPTHS — refusing to align by "
        "position, which would silently pair the wrong depths"
    )

    rmse = np.array([np.nan if v is None else float(v) for v in d[key]], dtype="float64")
    n_obs = np.asarray(d.get("n_obs_per_depth", [0] * config.N_DEPTHS), dtype="int64")
    return {"rmse": rmse, "n_obs": n_obs, "n_profiles": int(d.get("n_profiles", 0)), "meta": d}
