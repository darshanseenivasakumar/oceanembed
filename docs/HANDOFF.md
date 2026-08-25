# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```

## 2026-08-25 — Unit B (Darshan) — Day 2 data pipeline (synthetic-verified)
- CURRENT PHASE: Day 2 (data pipeline) — logic DONE & VERIFIED on synthetic data; real CMEMS download pending creds.
- BRANCH: main
- WHAT WORKS [VERIFIED by execution]: `python scripts/prepare_dataset.py` runs synthetic GLORYS → preprocess →
  build_samples and writes real-shaped artifacts: X_train (143514,11) z-scored (mean0 std1), y_train real °C,
  X_test/y_test, meta_train/test [lat,lon,date,month,cell_id], norm_stats.json (11-len feat/targ mean/std),
  land_mask (100,240) bool. Sanity: temp 26.2°C surface → 8.7°C @500m. preprocess regrids to 100×240×11.
- BUG FOUND & FIXED [VERIFIED]: DEPTHS[0]=0 m is above GLORYS' shallowest level (~0.49 m) → linear depth-interp
  returned NaN at surface and dropped ALL rows. Fixed with depth-axis extrapolation in preprocess.run(). This
  would have hit REAL GLORYS too — caught because we tested.
- WHAT IS BROKEN / UNVERIFIED: `download_glorys.py` + `download_argo.py` NOT run here (need `pip install
  copernicusmarine argopy` + CMEMS account). GLORYS dataset_id is [INFERRED] — confirm via `copernicusmarine describe`.
- FILES ADDED: data/{download_glorys,download_argo,preprocess}.py, features/build_samples.py,
  scripts/{make_synthetic_glorys,prepare_dataset}.py.
- NEXT TASK (B): install copernicusmarine+argopy, run real download, INSPECT one file, record lat/lon/depth/units
  in DATA_CONTRACT [VERIFIED], then `python scripts/prepare_dataset.py --real`.
- NOTE for A & C: run `python scripts/prepare_dataset.py` once to get full-size artifacts to develop against
  (or use the committed `artifacts/sample_*` fixtures for quick wiring).
- BLOCKERS: none for A/C. B blocked on CMEMS credentials for REAL data only.

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
