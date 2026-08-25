"""F4 — out-of-distribution detection on the surface inputs. Owner: Unit A (Arjhun).

WHAT THIS ANSWERS, AND WHAT IT DOES NOT
---------------------------------------
Answers: *"is this surface state unlike anything the model was trained on?"*
Does NOT answer: *"is this prediction wrong?"*

The distinction is the whole point. Calibrated uncertainty (calibration.py) says how wrong we
usually are on data that RESEMBLES training. It says nothing about a February 2026 Arabian Sea
state that looks like no month in 2019-2021. For that the honest answer is "outside the range we
have evidence for", not a confidently narrow error bar. Phase 1's D-016 was overconfidence
INSIDE the training distribution; this is the outside-the-distribution failure, and no amount of
recalibration fixes it.

METHOD — Mahalanobis distance in the 11-D feature space
--------------------------------------------------------
    d(x)^2 = (x - mu)^T * Sigma^-1 * (x - mu)

fitted on the training features. Chosen over a per-feature z-score because the surface variables
are strongly correlated (SST and SSH co-vary through thermal expansion), so a state can sit
inside every marginal range while being jointly impossible — warm SST with a deeply depressed sea
surface, say. Mahalanobis sees that; independent z-scores cannot.

  Lee, Lee, Lee & Shin, "A Simple Unified Framework for Detecting Out-of-Distribution Samples
  and Adversarial Attacks", NeurIPS 2018 — Mahalanobis distance as an OOD score.
  https://arxiv.org/abs/1807.03888

The threshold is an EMPIRICAL PERCENTILE of the training distances, not a chi-squared quantile.
Chi-squared assumes multivariate normality; our features include bounded cyclic encodings
(sin/cos of latitude, longitude and day-of-year) which are emphatically not Gaussian. Using the
training distances themselves makes the threshold distribution-free: "further from training than
99% of the training data itself".

KNOWN LIMITATION — the cyclic encodings
----------------------------------------
FEATURES includes sin/cos of lat, lon and day-of-year. Those are deterministic functions of
position and date, so a query at a location or season inside the domain is by construction inside
their range, and they contribute little discriminative power. The signal comes from the five
physical variables (sst, sss, ssh, u, v). `fit(..., physical_only=True)` restricts to those, and
is the recommended default for "is this ocean state unusual"; the full 11-D form is kept for
"is this query unusual in any respect at all", including an out-of-season date.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from oceanembed import config

# Features that describe the OCEAN rather than the query coordinates.
PHYSICAL_FEATURES = ["sst", "sss", "ssh", "u", "v"]

# Ridge added to the covariance diagonal before inversion. The cyclic encodings are exactly
# collinear in places (sin^2 + cos^2 = 1), so the raw covariance can be near-singular.
_RIDGE = 1e-6


@dataclass
class OODDetector:
    """Mahalanobis OOD detector fitted on training surface features."""

    mean: np.ndarray
    inv_cov: np.ndarray
    feature_idx: np.ndarray
    feature_names: list
    threshold: float
    percentile: float
    n_train: int
    train_distances: np.ndarray | None = None

    def score(self, X: np.ndarray) -> np.ndarray:
        """(N, 11) or (N, k) raw features -> (N,) Mahalanobis distance. Larger = more unusual."""
        X = np.asarray(X, dtype="float64")
        assert X.ndim == 2, f"expected (N, features), got {X.shape}"
        if X.shape[1] == config.N_FEAT:
            X = X[:, self.feature_idx]
        assert X.shape[1] == len(self.feature_idx), (
            f"expected {config.N_FEAT} or {len(self.feature_idx)} columns, got {X.shape[1]}"
        )
        delta = X - self.mean
        # einsum keeps this O(N*k^2) without forming an (N, N) intermediate.
        return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", delta, self.inv_cov, delta), 0.0))

    def is_ood(self, X: np.ndarray) -> np.ndarray:
        """(N,) bool — True where the input is further from training than the threshold."""
        return self.score(X) > self.threshold

    def report(self, X: np.ndarray) -> dict:
        """Scores plus the fraction flagged, for a UI banner or a log line."""
        d = self.score(X)
        flagged = d > self.threshold
        return {
            "n": int(len(d)),
            "n_ood": int(flagged.sum()),
            "frac_ood": float(flagged.mean()) if len(d) else 0.0,
            "threshold": float(self.threshold),
            "percentile": float(self.percentile),
            "distance_median": float(np.median(d)) if len(d) else float("nan"),
            "distance_max": float(d.max()) if len(d) else float("nan"),
            "features": list(self.feature_names),
            "note": ("Flags inputs UNLIKE TRAINING DATA. It does not mean the prediction is "
                     "wrong, and an in-distribution input is not thereby correct."),
        }


def fit(X_train: np.ndarray, *, percentile: float = 99.0,
        physical_only: bool = True, keep_train_distances: bool = False) -> OODDetector:
    """Fit the detector on RAW training features (the convention build_samples writes).

    percentile     : threshold as a percentile of the TRAINING distances. 99 means "further from
                     training than 99% of training itself", so ~1% of in-distribution data is
                     expected to trip it — a false-positive rate chosen on purpose, not an
                     accident.
    physical_only  : restrict to sst/sss/ssh/u/v. See the module docstring on why the cyclic
                     encodings dilute the score.
    """
    X_train = np.asarray(X_train, dtype="float64")
    assert X_train.ndim == 2 and X_train.shape[1] == config.N_FEAT, (
        f"expected (N, {config.N_FEAT}) raw features, got {X_train.shape}"
    )
    assert 0.0 < percentile < 100.0, "percentile must be inside (0, 100)"

    names = PHYSICAL_FEATURES if physical_only else list(config.FEATURES)
    idx = np.array([config.FEATURES.index(n) for n in names], dtype="int64")
    Xf = X_train[:, idx]

    ok = np.isfinite(Xf).all(axis=1)
    Xf = Xf[ok]
    assert len(Xf) > len(idx), (
        f"need more finite rows ({len(Xf)}) than features ({len(idx)}) to estimate a covariance"
    )

    mean = Xf.mean(axis=0)
    cov = np.cov(Xf, rowvar=False)
    cov = np.atleast_2d(cov) + _RIDGE * np.eye(len(idx))
    inv_cov = np.linalg.pinv(cov)   # pinv, not inv: survives a near-singular covariance

    delta = Xf - mean
    train_d = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", delta, inv_cov, delta), 0.0))

    return OODDetector(
        mean=mean,
        inv_cov=inv_cov,
        feature_idx=idx,
        feature_names=names,
        threshold=float(np.percentile(train_d, percentile)),
        percentile=float(percentile),
        n_train=int(len(Xf)),
        train_distances=train_d if keep_train_distances else None,
    )


def fit_from_artifacts(percentile: float = 99.0, physical_only: bool = True) -> OODDetector:
    """Convenience: fit on artifacts/X_train.npy.

    Note the provenance caveat — if the artifacts are synthetic, the fitted distribution
    describes synthetic data and the detector is exercised, not validated. Check
    artifacts/provenance.json before quoting anything from it.
    """
    from oceanembed.utils import io

    X = io.load_npy(config.art("X_train.npy")).astype("float64")
    return fit(X, percentile=percentile, physical_only=physical_only)
