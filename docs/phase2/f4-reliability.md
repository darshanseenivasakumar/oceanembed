# F4 — Calibrated uncertainty + OOD detection

**Owner:** Unit A (Arjhun) · **Branch:** `phase2-reliability` · **Status:** IMPLEMENTED + TESTED,
**not VALIDATED** (see §5).

---

## 1. The problem

`docs/DECISIONS.md` D-016, measured in Phase 1 and still open:

> MC-dropout reports **σ ≈ 0.30 °C** at 75 m while the error against real Argo floats is
> **1.22 °C** — a ~4× underestimate, at the depth where the model is weakest.

Overconfidence is the dangerous direction. The Phase-1 response was to stop showing the spread and
show measured error instead — correct, but it leaves the model with no usable uncertainty. F4 makes
the spread itself trustworthy, and adds the failure mode calibration cannot cover.

**Two different questions, two different tools:**

| question | tool | fails when |
|---|---|---|
| "how wrong are we, typically?" | `calibration.py` | the input resembles training |
| "is this input even like training?" | `ood.py` | it isn't |

Calibration is fitted on data resembling training, so it says nothing about a state unlike anything
in 2019–2021. That is the OOD detector's job, and no amount of recalibration substitutes for it.

---

## 2. Method — variance (std) scaling

Post-hoc rescaling of predicted standard deviations by a factor fitted on held-out data. The mean
prediction is untouched and the predictive distribution stays Gaussian, so nothing downstream
changes shape.

Minimising the Gaussian NLL with respect to a scalar `a` has a closed form:

```
a² = (1/n) · Σᵢ ( residualᵢ² / σᵢ² )
```

Fitted **per depth**, because the miscalibration is depth-dependent by nature — worst at the
thermocline, mild at the surface. A single global factor would over-correct the surface while
under-correcting 75–150 m.

**Metric — ENCE** (Expected Normalized Calibration Error):

```
ENCE  = (1/N_bin) · Σⱼ |RMVⱼ − RMSEⱼ| / RMVⱼ
RMVⱼ  = √( mean(σᵢ²) for i ∈ binⱼ )
RMSEⱼ = √( mean(residualᵢ²) for i ∈ binⱼ )
```

Samples sorted by σ into equally-sized bins. Scale-free, so 0 m and 1000 m are directly comparable
despite error magnitudes differing by an order of magnitude.

### Citations
- Levi, Gispan, Giladi & Fetaya, *Evaluating and Calibrating Uncertainty Prediction in Regression
  Tasks* (2022) — std-scaling and ENCE.
- Kuleshov, Fenner & Ermon, *Accurate Uncertainties for Deep Learning Using Calibrated Regression*,
  ICML 2018, PMLR v80 — the earlier isotonic-regression approach.
  https://proceedings.mlr.press/v80/kuleshov18a/kuleshov18a.pdf
- Lee, Lee, Lee & Shin, *A Simple Unified Framework for Detecting Out-of-Distribution Samples and
  Adversarial Attacks*, NeurIPS 2018 — Mahalanobis distance as an OOD score.
  https://arxiv.org/abs/1807.03888

`[ABSTRACT-ONLY]` for Levi et al.: the formulae were taken from a secondary source that states them
explicitly, not from the paper's own PDF. The ENCE formula above is reproduced verbatim from that
source. Upgrade to `[VERIFIED]` on reading the original.

---

## 3. OOD — Mahalanobis distance

```
d(x)² = (x − μ)ᵀ Σ⁻¹ (x − μ)
```

fitted on training surface features.

**Why not per-feature z-scores.** The surface variables are strongly correlated — SST and SSH
co-vary through thermal expansion, so warm water stands higher. A state can sit inside *every*
marginal range while being jointly impossible: warm SST with a depressed sea surface. Mahalanobis
sees that; independent z-scores cannot. `tests/phase2/test_ood.py::test_violating_the_sst_ssh_correlation_is_flagged`
tests exactly this, and asserts each value is marginally unremarkable first, so the test cannot
pass for the wrong reason.

**Threshold is an empirical percentile of training distances**, not a χ² quantile. χ² assumes
multivariate normality, and `FEATURES` includes bounded cyclic encodings (sin/cos of lat, lon,
day-of-year) which are emphatically not Gaussian. An empirical percentile is distribution-free:
*"further from training than 99% of training itself"*. The ~1% false-positive rate is therefore a
deliberate choice, and is asserted in the tests.

**`physical_only=True` is the default.** The six cyclic encodings are deterministic functions of
position and date, so any in-domain query is inside their range by construction and they dilute the
score. The default restricts to `sst, sss, ssh, u, v`. The full 11-D form is retained for *"is this
query unusual in any respect"*, including an out-of-season date.

---

## 4. API

```python
from phase2.reliability import calibration as cal, ood

# RIGOROUS: per-sample residuals + sigmas, real fit/eval split, ENCE reported
res = cal.fit_from_samples(residuals, sigmas)      # (N,15) each
res.is_validated        # True  — evaluated on rows it was not fitted on
calibrated = res.apply(sigma)
print(res.summary())

# WEAK: per-depth aggregates only (what argo_error_by_depth.json stores)
res = cal.fit_from_summary(rmse_by_depth, sigma_by_depth)
res.is_validated        # False — always

det = ood.fit_from_artifacts(percentile=99.0)
det.is_ood(X)           # (N,) bool
det.report(X)           # dict for a UI banner
```

---

## 5. 🔴 Why this is NOT marked VALIDATED

**`artifacts/argo_error_by_depth.json` is not on this machine.** It is gitignored (`/artifacts/*`)
and exists only where `scripts/eval_satellite_vs_argo.py` was run — Darshan's laptop. Every number
this module could currently produce comes from synthetic artifacts
(`artifacts/provenance.json → "synthetic"`).

So: the **method** is tested — the estimator recovers a known 4× overconfidence, resolves
depth-varying miscalibration, and improves ENCE out of sample. The **science** is unverified,
because it has never touched real error.

### Two things needed to close this

**(a) The error file.** It is ~15 numbers. It is a *result*, not raw data, and results are the
evidence — it arguably belongs in git alongside `EXPERIMENT_LOG.md`. One whitelist line:

```
!/artifacts/argo_error_by_depth.json
```

**(b) Per-sample residuals, to use the rigorous path.** `argo_error_by_depth.json` stores
*aggregate per-depth RMSE*. That supports only moment-matching (`a_d = RMSE_d / RMV_d`), which
**cannot be held out** — there is no per-sample identity to split on, so the factors are fitted on
exactly the numbers they would be scored against. `ratio_after` comes back 1.0 by construction and
proves nothing; `is_validated` returns `False` and the note says so.

To reach `fit_from_samples`, `eval_satellite_vs_argo.py` would additionally persist, per matched
profile: `[lat, lon, date, depth_idx, residual, sigma]`. That is a Unit-B change to a Unit-B script,
so it is **requested, not made**.

This is the same discipline Unit B applied to the SSH bias offset: fit on train dates, verify
against the test period, and only then believe it.

---

## 6. Known limitations

- **Gaussian assumption.** Std-scaling keeps the distribution Gaussian. If the real error is
  heavy-tailed, a scaled σ still under-covers the tails. Isotonic recalibration (Kuleshov) is
  distribution-free and is the upgrade path if quantile coverage matters.
- **OOD flags the input, never the output.** An in-distribution input is not thereby correct. The
  `report()` note states this and a test asserts the wording survives.
- **Sparse depths.** 0 m routinely has ~32 Argo observations against ~2,400 elsewhere. Factors are
  fitted there but flagged in `unreliable_depths`; do not quote them.
- **Fitted on 2019–2021.** A genuinely novel ocean state — a record marine heatwave — should be
  flagged OOD. That is correct behaviour, not a failure, but it means the tool says "no evidence"
  exactly when the science is most interesting.

---

## 7. Note for Unit B — a latent scaffold bug, fixed

`tests/phase2/__init__.py` made pytest import test modules as `phase2.test_*`, which **shadowed
`src/phase2`** and made `phase2.reliability` unimportable. It was latent because
`test_subsurface.py` imports only `oceanembed` and currently skips; it would have hit you the
moment a Phase-2 test imported `phase2.data`.

Deleted. The baseline `tests/` has no `__init__.py` anywhere, so this matches existing convention.
`main` has no `tests/phase2` directory at all, so the change cannot reach it.

**Also:** `git checkout -b phase2/reliability` is impossible — `phase2` already exists as a branch,
and a git ref cannot be both a branch and a directory. This work is on **`phase2-reliability`**.
You will hit the same wall on `phase2/collocation`; worth settling the convention now.
