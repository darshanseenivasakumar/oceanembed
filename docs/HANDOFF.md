# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```

## 2026-08-25 — Unit A (Arjhun) — MLP implemented, trains on fixtures
- CURRENT PHASE: Day 1 (MODEL_SPEC + MLPProfile on fixtures) — DONE.
- BRANCH: feat/unit-a-mlp
- WHAT WORKS [VERIFIED by execution]:
  - `pytest tests/test_model.py -v` -> **11 passed** (shapes, checkpoint round-trip, dropout on/off,
    zero-std clamp, raw-units warning, fixture-contract guard).
  - `python -m oceanembed.train.train_mlp --fixtures` -> val loss 0.896 -> 0.064 (z-scored MSE), 0.8 s CPU.
  - Reload via `load_mlp` -> `predict_mlp` -> (500,11) float32, 8.42-30.82 degC.
  - ANTI-COLLAPSE CHECK: model RMSE 0.214 degC vs predict-the-mean 1.503 degC (+85.8% skill); per-depth
    spread tracks truth; profile cools monotonically 27.45 -> 8.91 degC. Not collapsed.
  - These are SYNTHETIC FIXTURES — plumbing evidence only, NOT a result.
- WHAT IS BROKEN: nothing known in Unit A code.
- LAST CHANGE: implemented MLPProfile/load_mlp/predict_mlp, train_mlp.py, tests; filled MODEL_SPEC.md.
- FILES MODIFIED: `src/oceanembed/models/mlp_profile.py`, `src/oceanembed/train/train_mlp.py`,
  `tests/test_model.py`, `docs/MODEL_SPEC.md`, `docs/DECISIONS.md` (D-007, D-008), `docs/HANDOFF.md`.
- TESTS RUN: `pytest tests/test_model.py -v` — 11 passed (output pasted above).
- KNOWN ISSUES / DECISIONS:
  - **D-007**: norm stats now live as buffers INSIDE `mlp_model.pt`, so no companion file is needed.
    `train_mlp` auto-prefers `artifacts/norm_stats.json` the moment B ships it. No signature change for B/C.
  - **CONTRACT MISMATCH [UNKNOWN] — needs Darshan**: MODEL_SPEC says X is z-scored, but `sample_X.npy` is RAW
    (verified range -1.000..36.994) and `norm_stats.json` is absent. Will real `X_train.npy` ship z-scored, or
    raw + norm_stats.json? `predict_mlp` raises a RuntimeWarning on raw-looking input meanwhile.
  - **D-008 — needs a team decision**: `config.DEPTHS` = 11 levels to 500 m, but SIH26066 names 15 to 1000 m
    (missing 5/125/700/1000). This sets my output width; changing later = retrain. Cheap to fix now.
  - `docs/EXPERIMENT_LOG.md` deliberately NOT touched — it is Unit C's file and is for REAL runs from Day 3.
    Fixture numbers there would read as results.
- NEXT TASK (A): Day 2 — `models/lgbm_baseline.py` + `train/train_lgbm.py` (11 boosters, quantile option),
  finish early stopping/seed hygiene. NOTE: `lightgbm` not yet installed locally.
- BLOCKERS: none for Day 2. Day 3 needs B's real `X_train/y_train/X_test/y_test.npy` + `norm_stats.json`.

## 2026-08-25 — Unit B (Darshan) — scaffold seeded
- CURRENT PHASE: Day 1 (scaffold + contracts + fixtures) — DONE for the core.
- BRANCH: main
- WHAT WORKS [VERIFIED by execution]: `python src/oceanembed/config.py` OK; `python scripts/make_fixtures.py`
  writes `artifacts/sample_X.npy (500,11)`, `sample_y.npy (500,11)`, `sample_meta.csv` (lat,lon,date,month,cell_id);
  guardian checks pass (config sanity, fixture shapes, grid round-trip).
- WHAT IS BROKEN: nothing known. `pytest` + `pyarrow` + `pyyaml` not installed locally yet (tests verified inline).
- LAST CHANGE: created repo skeleton, config.py, utils (grids, io), fixtures, tests, docs, module stubs.
- FILES MODIFIED: whole initial scaffold (see git log).
- TESTS RUN: config.sanity_check + fixture shape asserts + grid roundtrip — all PASS (inline, pytest pending install).
- KNOWN ISSUES: tables fall back to CSV until `pip install -r requirements.txt` (pyarrow) — by design.
- NEXT TASK (B): GLORYS + Argo download, preprocess, build_samples → real `X/y/meta/norm_stats/land_mask/argo` files.
- NEXT TASK (A): implement `models/mlp_profile.py` + training on fixtures (stubs + signatures ready).
- NEXT TASK (C): implement `validation/metrics.py` + `climatology.py` on fixtures; seed LITERATURE/NOVELTY matrices.
- BLOCKERS: none. A and C can start immediately against `artifacts/sample_*`.
