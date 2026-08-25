"""F4 OOD-detection tests. Owner: Unit A (Arjhun).

The scientific tests here check that the detector flags states that are PHYSICALLY unusual for
the North Indian Ocean, and — the part a per-feature z-score cannot do — states that sit inside
every marginal range while violating the joint correlation structure. That second property is
the entire justification for using Mahalanobis distance, so it is tested directly.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from phase2.reliability import ood

F = config.N_FEAT
RNG = np.random.default_rng(config.SEED)


def training_like(n=5000, seed=0):
    """Surface states resembling the tropical North Indian Ocean, with realistic correlation.

    SST and SSH co-vary through thermal expansion — warm water stands higher. That correlation
    is what makes 'warm but low' jointly impossible while marginally unremarkable.
    """
    rng = np.random.default_rng(seed)
    X = np.zeros((n, F), dtype="float64")
    sst = rng.normal(28.0, 1.2, n)
    X[:, config.FEATURES.index("sst")] = sst
    X[:, config.FEATURES.index("sss")] = rng.normal(35.0, 0.6, n)
    # SSH tied to SST: +0.06 m per degC, plus independent noise.
    X[:, config.FEATURES.index("ssh")] = 0.06 * (sst - 28.0) + rng.normal(0.0, 0.03, n)
    X[:, config.FEATURES.index("u")] = rng.normal(0.0, 0.25, n)
    X[:, config.FEATURES.index("v")] = rng.normal(0.0, 0.25, n)
    for name in config.FEATURES[5:]:                     # cyclic encodings, bounded [-1, 1]
        X[:, config.FEATURES.index(name)] = rng.uniform(-1, 1, n)
    return X


def one(**overrides):
    """A single in-distribution row, with named features overridden."""
    x = training_like(1, seed=99)[0].copy()
    x[config.FEATURES.index("sst")] = 28.0
    x[config.FEATURES.index("ssh")] = 0.0
    for k, v in overrides.items():
        x[config.FEATURES.index(k)] = v
    return x[None, :]


# ============================================================ SCIENTIFIC
def test_a_physically_impossible_temperature_is_flagged():
    """5 degC surface water does not occur in the tropical North Indian Ocean."""
    det = ood.fit(training_like())
    assert det.is_ood(one(sst=5.0))[0], "polar-cold SST should be out of distribution"


def test_a_typical_state_is_not_flagged():
    det = ood.fit(training_like())
    assert not det.is_ood(one(sst=28.3, ssh=0.02))[0], "an ordinary tropical state must pass"


def test_violating_the_sst_ssh_correlation_is_flagged():
    """THE reason for Mahalanobis over independent z-scores.

    SST 30.4 degC and SSH -0.09 m are each inside their own marginal range, but warm water
    standing LOW is jointly implausible. A per-feature z-score sees two ordinary numbers;
    Mahalanobis sees the broken relationship.
    """
    X = training_like()
    det = ood.fit(X)

    sst_i, ssh_i = config.FEATURES.index("sst"), config.FEATURES.index("ssh")
    warm_low = one(sst=30.4, ssh=-0.09)

    # Confirm the premise: each value really is marginally unremarkable.
    for i, v in ((sst_i, 30.4), (ssh_i, -0.09)):
        z = abs(v - X[:, i].mean()) / X[:, i].std()
        assert z < 3.0, f"feature {config.FEATURES[i]} is a marginal outlier (z={z:.2f})"

    assert det.is_ood(warm_low)[0], (
        "a jointly impossible warm-but-low state slipped through — the covariance is not "
        "being used"
    )


def test_false_positive_rate_matches_the_chosen_percentile():
    """A 99th-percentile threshold should flag ~1% of in-distribution data. That rate is a
    deliberate choice, so it must actually hold."""
    X = training_like(20000, seed=1)
    det = ood.fit(X, percentile=99.0)
    frac = det.is_ood(X).mean()
    assert 0.005 < frac < 0.02, f"expected ~1% false positives, got {frac:.3%}"


def test_a_stricter_percentile_flags_less():
    X = training_like(8000, seed=2)
    assert ood.fit(X, percentile=99.9).is_ood(X).mean() < ood.fit(X, percentile=95.0).is_ood(X).mean()


def test_distance_grows_monotonically_with_departure():
    """A score that does not increase as a state gets weirder is not measuring anything."""
    det = ood.fit(training_like())
    d = [det.score(one(sst=s))[0] for s in (28.0, 26.0, 22.0, 15.0, 5.0)]
    assert all(b > a for a, b in zip(d, d[1:])), f"non-monotonic distances: {d}"


def test_physical_only_is_more_sensitive_than_the_full_feature_set():
    """The six cyclic encodings dilute the score, which is why physical_only is the default."""
    X = training_like(8000, seed=3)
    weird = one(sst=20.0)
    d_phys = ood.fit(X, physical_only=True)
    d_full = ood.fit(X, physical_only=False)
    z_phys = d_phys.score(weird)[0] / d_phys.threshold
    z_full = d_full.score(weird)[0] / d_full.threshold
    assert z_phys > z_full, f"physical-only should be more sensitive ({z_phys:.2f} vs {z_full:.2f})"


# ============================================================ HONESTY
def test_report_states_what_the_flag_does_not_mean():
    det = ood.fit(training_like(2000, seed=4))
    note = det.report(one(sst=10.0))["note"].lower()
    assert "does not mean the prediction is wrong" in note
    assert "not thereby correct" in note


# ============================================================ UNIT
def test_fit_uses_only_the_physical_features_by_default():
    det = ood.fit(training_like(2000, seed=5))
    assert det.feature_names == ood.PHYSICAL_FEATURES
    assert len(det.feature_idx) == 5


def test_score_accepts_full_width_or_selected_width():
    X = training_like(2000, seed=6)
    det = ood.fit(X)
    full = det.score(X[:10])                              # (N, 11)
    subset = det.score(X[:10][:, det.feature_idx])        # (N, 5)
    assert np.allclose(full, subset)


def test_score_rejects_a_wrong_feature_count():
    det = ood.fit(training_like(2000, seed=7))
    with pytest.raises(AssertionError):
        det.score(np.zeros((3, 8)))


def test_report_shapes_and_keys():
    det = ood.fit(training_like(2000, seed=8))
    r = det.report(training_like(50, seed=9))
    assert r["n"] == 50 and 0.0 <= r["frac_ood"] <= 1.0
    assert set(["threshold", "percentile", "distance_median", "features"]) <= set(r)


def test_singular_covariance_does_not_crash():
    """sin^2 + cos^2 = 1 makes the cyclic block exactly collinear; pinv + ridge must survive."""
    X = training_like(2000, seed=10)
    X[:, config.FEATURES.index("v")] = X[:, config.FEATURES.index("u")]   # perfectly collinear
    det = ood.fit(X, physical_only=True)
    assert np.isfinite(det.score(X[:20])).all()


def test_rejects_a_wrong_training_width():
    with pytest.raises(AssertionError):
        ood.fit(np.zeros((100, F - 2)))


def test_rejects_an_out_of_range_percentile():
    with pytest.raises(AssertionError):
        ood.fit(training_like(500, seed=11), percentile=100.0)


def test_rows_with_nan_features_are_dropped_not_imputed():
    X = training_like(2000, seed=12)
    X[:50, config.FEATURES.index("sst")] = np.nan
    det = ood.fit(X)
    assert det.n_train == 1950, "NaN rows must be excluded from the fit, never filled in"
