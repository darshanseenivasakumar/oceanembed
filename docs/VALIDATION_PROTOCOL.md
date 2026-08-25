# VALIDATION_PROTOCOL.md  (Owner: Unit C — Mitun+Niru)

## Splits (anti-leakage)
- **Temporal holdout:** train {2019,2020,2021}, test {2022}. Never random-split adjacent cells/days.
- **Independent Argo:** a different data source entirely — the strongest check.
- (stretch) region holdout as a stress test.

**Why never random-split:** adjacent grid cells on adjacent days are almost the same water. A random
split puts near-duplicates on both sides, so the model scores well by near-memorisation. The number
looks excellent and means nothing. Any split change is a team decision.

## Validation hierarchy
Each level has a pass criterion. A level that has not been *run* is not passed.

| | Level | Pass criterion | Status |
|---|---|---|---|
| **L1** | Sanity | value ranges sane, NaN/land handled, temperature falls with depth, units correct | `[UNVERIFIED — needs real data]` |
| **L2** | Unit / synthetic tests | `pytest tests/` green; shape asserts at every boundary | **`[VERIFIED]` 16 passed** |
| **L3** | Baseline comparison | `skill_vs_clim > 0` on the test set — **mandatory**, a model that cannot beat climatology has no result | `[UNVERIFIED — needs real data]` |
| **L4** | Held-out test | metrics on 2022, never touched during training | `[UNVERIFIED — needs real data]` |
| **L5** | Independent Argo | metrics at real Argo points/depths | `[UNVERIFIED — argo_test not built]` |
| **L6** | Event / anomaly | a known marine-heatwave window, if time permits | not started |

## Metrics (`validation/metrics.py`)
RMSE, MAE, **per-depth RMSE[11]**, **per-depth R²[11]**, pooled R², `skill_vs_clim = 1 − RMSE_model/RMSE_clim`.

### ⚠ Do not quote pooled R² — it is inflated  `[VERIFIED by measurement]`
Pooled R² divides by the variance of *all* values at *all* depths, which is dominated by the vertical
gradient (~28 °C at the surface to ~9 °C at 500 m). Knowing only that water gets colder with depth
already explains most of it, so pooled R² starts from a very high floor:

| predictor | pooled R² | per-depth R² |
|---|---|---|
| climatology (the mean profile) | **+0.9538** | **0.0000** |
| one global mean everywhere | +0.0000 | −78.59 |

Climatology scoring **+0.95** is the tell. So a headline of "R² = 0.999" sounds near-perfect while the
real skill is only the gap above ~0.95 — and a judge reads the absolute number.

**Report `r2_by_depth` and `skill_vs_clim`.** `r2_by_depth` measures each depth against that depth's own
mean, so climatology scores exactly 0.0 and anything positive is genuine skill. Pooled `r2` is retained
in the dict only so existing callers keep working.

## Honesty rules
1. Report deep-level degradation openly — surface data fundamentally limits deep skill (cf. TS-Cast).
   Saying "we are weaker below 300 m and here is the number" is a strength, not a weakness.
2. **Never quote a number the code did not produce.** Every figure traces to a logged run.
3. Uncertainty is not confidence. See `docs/DECISIONS.md` D-016: MC-dropout is currently
   **overconfident at depth** (σ/RMSE 1.25 at 0 m → 0.31 at 500 m), so it must not back a reliability
   claim until re-measured on real data.
4. Label synthetic results as synthetic, everywhere, every time.

## Per-experiment record (→ EXPERIMENT_LOG.md)
dataset, split, model, hyperparams, seed, metrics, checkpoint, hardware, timestamp, preprocessing
version, git commit.

## Red-team checklist (Niru, before the demo)
Data leakage · unit/coordinate errors · temporal leakage · overfitting · weak baselines · misleading
charts · fake confidence · unsupported novelty claims · **does it work on a fresh clone?**
Findings go in `docs/HANDOFF.md`. The reviewer's job is to find problems, not to praise.
