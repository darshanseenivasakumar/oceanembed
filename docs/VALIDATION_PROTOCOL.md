# VALIDATION_PROTOCOL.md  (Owner: Unit C — Mitun+Niru)  [seeded by B]

## Splits (anti-leakage)
- **Temporal holdout:** train {2019,2020,2021}, test {2022}. Never random-split adjacent cells/days.
- **Independent Argo:** a different data source entirely — the strongest check.
- (stretch) region holdout as a stress test.

## Validation hierarchy
- **L1 Sanity:** value ranges, NaN handling, temperature decreases with depth (mostly), units correct.
- **L2 Unit/synthetic tests:** metrics on toy arrays; shape asserts.
- **L3 Baseline comparison:** every model vs **climatology** → report `skill_vs_clim` (must be > 0 to matter).
- **L4 Held-out test:** metrics on 2022.
- **L5 Independent Argo:** metrics at real Argo points/depths.
- **L6 Event/anomaly:** a known marine-heatwave window, if time permits.

## Metrics (`validation/metrics.py`)
RMSE, MAE, R², **per-depth RMSE[11]**, spatial RMSE map, `skill_vs_clim = 1 − RMSE_model/RMSE_clim`.

## Honesty rule
Report deep-level degradation openly — surface data fundamentally limits deep skill (cf. TS-Cast). Never hide it.

## Per-experiment record (→ EXPERIMENT_LOG.md)
dataset, split, model, hyperparams, seed, metrics, checkpoint, hardware, timestamp, preprocessing version, git commit.
