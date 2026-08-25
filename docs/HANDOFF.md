# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```

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
