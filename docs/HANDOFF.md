# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```





## 2026-08-25 - Unit A (Arjhun) - Day 3 PREPPED (blocked on real data), + a real bug found

- BRANCH: `feat/unit-a-priority`. **`pytest tests/ -q` -> 50 passed.**
- **Day 3 cannot complete**: it is "train for real; beat the baseline", and there is no real data because
  `prepare_dataset.py` still fails (`.gitignore` excludes `src/oceanembed/data/`). Checked `origin/main` - no fix
  pushed yet. So I built everything that does NOT depend on real data.
- NEW `oceanembed/train/compare_models.py` - the three-way verdict harness. `scripts/run_slice.py` compares MLP
  vs climatology only and has no LightGBM arm, so the Day-3 decision ("if MLP can't beat LightGBM, say so and we
  ship LightGBM") had nothing producing it. One command now does:
  `python -m oceanembed.train.compare_models`. Degrades gracefully when a model is missing; refuses to write
  fixture runs to EXPERIMENT_LOG.md.
- NEW `oceanembed/train/_data.py` - one loader shared by training AND evaluation (see D-014).

### BUG FOUND AND FIXED - a live instance of Darshan's D-009 concern
`train_lgbm` and `compare_models` each had their own fixture loader; one z-scored X, the other did not. Nothing
errored. The models silently saw different scales:
- MLP evaluated at **RMSE 36.20 degC** (trained z-scored, evaluated raw)
- then LightGBM at **RMSE 2.51 degC, worse than climatology** (trained raw, evaluated z-scored)
Neither model was broken - the caller was, twice, in opposite directions. Fixed by making both delegate to
`train/_data.py`; tests assert train and test share one scale. **Darshan: this is exactly the silent failure you
predicted. With the stats living outside the model, every caller answers "who normalizes?" separately and gets it
wrong quietly. Strongest argument yet for resolving D-009.**
I also corrected a misleading comment I had written in `lgbm_baseline.py`: trees do not NEED scaling, but that is
not the same as being safe under a change of scale between fit and predict.

### Harness verified on fixtures [VERIFIED by execution]
climatology 1.4664 | LightGBM 0.2225 (+0.848) | MLP 0.2223 (+0.848)
VERDICT: LIGHTGBM (**NOT conclusive**) - 0.1% gap, under the 2% noise margin, ships the simpler model.
That is the correct answer: D-013 predicted both models saturate the 0.20 degC noise floor, and they do.
NOT written to EXPERIMENT_LOG.md - fixture runs are not experiments.

- FILES MODIFIED: `src/oceanembed/train/compare_models.py` (new), `src/oceanembed/train/_data.py` (new),
  `src/oceanembed/train/train_lgbm.py`, `src/oceanembed/models/lgbm_baseline.py` (comment fix),
  `tests/test_compare_models.py` (new), `docs/DECISIONS.md` (D-014, D-015), `docs/HANDOFF.md`.
- NEXT (A), the moment the `.gitignore` fix lands - about 10 minutes of work:
  `python scripts/prepare_dataset.py` -> `train_lgbm` -> `train_mlp` ->
  `python -m oceanembed.train.compare_models` -> real verdict auto-logged to EXPERIMENT_LOG.md.
- OPEN FOR B (all still blocking or unanswered): `.gitignore` blocker | **D-008** depths (VERIFIED 15 levels to
  1000 m at https://sih2026.vuce.in/en -> SIH26066; ours is 11 to 500 m) | **D-009** raw-in vs z-scored-in |
  add `lgbm_quantiles.pkl` to DATA_CONTRACT.md.

## 2026-08-25 — Unit A (Arjhun) — Day 2 COMPLETE (baselines + full training loop + tests)

- BRANCH: `feat/unit-a-priority` (off current main 3f85e52). **`pytest tests/ -q` -> 36 passed.**
- Day 2 item 1 (LightGBM baseline + quantile uncertainty): DONE — see the entry below.
- Day 2 item 2 (MLP loop: seed, early stopping, save checkpoint): **already done in B's
  `train_mlp.py`** [VERIFIED by reading it: `_seed()`, patience + best-state restore, saves
  `mlp_model.pt`]. Not duplicated.
- Day 2 item 3 (`tests/test_model.py`): DONE — was still an 8-line stub on `main`. 12 tests:
  architecture matches `config.MLP` (11->128->128->11, dropout 0.2), forward shapes, dropout
  ACTIVE in train() / inactive in eval() (the MC-dropout precondition), predict_mlp shape/dtype,
  real-degC-not-normalized output, eval-state hygiene, checkpoint round-trip.
  **Self-contained by design** — nothing depends on `artifacts/` existing, because a fresh clone
  cannot run `prepare_dataset.py` today, so artifact-dependent tests would skip everywhere and
  prove nothing.

### Findings
- **[VERIFIED] `predict_mlp` hard-fails without `artifacts/norm_stats.json`** — raw
  `FileNotFoundError` from `_targ_stats()`. On a fresh clone that file does not exist, so the
  whole predict path is unusable. Combined with the `.gitignore` blocker (no pipeline -> no
  norm_stats.json) the demo path is dead on a clean clone. Recorded as a test
  (`test_predict_mlp_requires_norm_stats`) rather than left as a surprise. **B: consider a
  clearer error, or having `mlp_model.pt` carry its own stats (that is D-007 on
  `feat/unit-a-mlp`).**
- **[VERIFIED] MY MISTAKE, now fixed:** a fixture-trained `mlp_model.pt` from `feat/unit-a-mlp`
  was left in gitignored `artifacts/` and survived the branch switch. It has norm buffers that
  B's `MLPProfile` does not define, so `load_mlp()` failed with "Unexpected key(s) in
  state_dict". Not a bug in B's code — my stale artifact. Deleted. Anyone switching between
  these branches must clear `artifacts/*.pt` first.

### D-009 — NOT actioned, and deliberately so
`predict.py` calls `_normalize()` before `predict_mlp` [VERIFIED: `Xn = _normalize(...)` at
predict.py:105 and :145], so the live integration is **z-scored-in**. Porting the raw-in version
from `feat/unit-a-mlp` would DOUBLE-NORMALIZE and silently corrupt every temperature in the demo
— precisely the failure Darshan flagged. Resolving it properly means deleting `_normalize()` from
`predict.py`, which is B's file. **So D-009 needs Darshan's decision, not a unilateral change.**
This branch keeps B's z-scored-in contract throughout.

- NEXT (A): blocked on real data for the honest MLP-vs-LightGBM verdict (D-013). Once B's
  `.gitignore` fix lands: `prepare_dataset.py` -> `train_lgbm` + `train_mlp` on real X_train ->
  re-run the comparison -> log to EXPERIMENT_LOG.md -> Day 4 (MC-dropout tuning already exists in
  B's `uncertainty.py`; `observation_priority()` is done).
- OPEN FOR B: `.gitignore` blocker | **D-008** depths (VERIFIED 15 levels to 1000 m at
  https://sih2026.vuce.in/en -> SIH26066; ours is 11 to 500 m) | **D-009** above |
  add `lgbm_quantiles.pkl` to DATA_CONTRACT.md.

## 2026-08-25 — Unit A (Arjhun) — LightGBM baseline DONE

- BRANCH: `feat/unit-a-priority` (continues from observation_priority).
- WHAT WORKS [VERIFIED by execution]:
  - `python -m oceanembed.train.train_lgbm --fixtures` -> 11 boosters in 6.6 s, saves
    `artifacts/lgbm_model.pkl` + `lgbm_quantiles.pkl`. Val RMSE 0.216 degC, skill vs climatology +0.839.
  - `pytest tests/test_lgbm_baseline.py -q` -> **10 passed** (booster count, shapes, real-degC output,
    save/load round-trip, beats-climatology, quantile non-negativity, quantile-crossing warning).
  - `train()` mirrors `train_mlp.train()` so `run_slice.py` can call either interchangeably.
- **D-013 — READ THIS BEFORE COMPARING MODELS.** Head-to-head on a 100-row held-out fixture slice:
  climatology 1.466 | LightGBM 0.222 (+0.849) | MLP 0.221 (+0.849). The MLP "wins" by 0.2% = noise.
  `make_fixtures.py` adds N(0, 0.2), so the noise floor is 0.20 degC and **both models have saturated it**.
  The comparison is uninformative BY CONSTRUCTION. Do not conclude "MLP has no advantage" from it —
  the model-selection call can only be made on real GLORYS.
- NEW ARTIFACT (**Unit B: please add to DATA_CONTRACT.md, that file is yours**):
  `lgbm_quantiles.pkl` = `{"q10": [...11 boosters], "q90": [...11]}`. `lgbm_model.pkl` is unchanged and
  still exactly the contracted list of 11 boosters. Quantile spread -> sigma-equivalent via /2.5631.
- FILES MODIFIED: `src/oceanembed/models/lgbm_baseline.py`, `src/oceanembed/train/train_lgbm.py`,
  `tests/test_lgbm_baseline.py` (new), `docs/DECISIONS.md` (D-012, D-013), `docs/HANDOFF.md`.
- STILL BLOCKED ON B: the `.gitignore` bug (`data/` swallows `src/oceanembed/data/`) means I cannot run
  `prepare_dataset.py`, so nothing here has touched real data. Everything above is fixtures.
- NEXT (A): once the .gitignore fix lands -> `train_lgbm` on real data, re-run the MLP-vs-LightGBM
  comparison for a REAL verdict, then rebase the useful parts of `feat/unit-a-mlp`.

## 2026-08-25 — Unit A (Arjhun) — observation_priority() implemented + BLOCKING repo bug

### ⚠ BLOCKER FOR EVERYONE — `src/oceanembed/data/` is not in the repo (Unit B to fix)
`.gitignore` line 2 is `data/`, which has no leading slash, so it matches **any** directory named
`data` at any depth — including `src/oceanembed/data/`. Unit B's preprocessing module was therefore
never committed. [VERIFIED]:
```
$ git check-ignore -v src/oceanembed/data/preprocess.py
.gitignore:2:data/      src/oceanembed/data/preprocess.py

$ python scripts/prepare_dataset.py
ModuleNotFoundError: No module named 'oceanembed.data'

$ python scripts/run_slice.py
Run `python scripts/prepare_dataset.py` first to build artifacts.
```
Consequence: **anyone who clones cannot build artifacts or run the slice.** Units A and C are both
blocked on real-data work. It only runs on Darshan's machine, where the file exists untracked.
FIX (Unit B owns `.gitignore`): anchor the rule to the repo root — `/data/` instead of `data/` —
then `git add -f src/oceanembed/data/` and commit. One line.

### observation_priority() — DONE
- BRANCH: `feat/unit-a-priority`, branched off current `main` (3f85e52) so it merges clean.
- WHAT WORKS [VERIFIED by execution]:
  - `pytest tests/test_observation_priority.py -q` -> **11 passed**.
  - Verified against the REAL seam (`predict.py:165-176`, real `_argo_sparsity()`, today's no-Argo
    state): `priority (100,240) float32`, ocean 0.0000-1.0000, mean 0.5654, 856 distinct values,
    land all-NaN, ocean all finite. `reconstruct_grid` no longer returns `priority=None`, so the
    Streamlit panel lights up automatically via B's auto-detection.
- DESIGN (full rationale in `docs/ARCHITECTURE.md`): weighted geometric mean of normalized
  |anomaly| x uncertainty x sparsity, default weights (1,1,1), 1st-99th percentile normalization.
  Multiplicative because a site must be anomalous AND uncertain AND unobserved. Geometric mean
  rather than raw product because the ranking is identical (asserted in a test) but the product
  collapses toward 0 and renders a near-black map.
- **The bug this design prevents**: `_argo_sparsity()` returns a UNIFORM grid when `argo_test` is
  absent — the repo's state today. Min-max scaling a constant grid gives all-zeros, which would
  silently zero the whole priority map: a blank panel that looks like a bug, not a missing input.
  Constant/all-NaN factors are therefore treated as NEUTRAL and warn; if all three are degenerate
  the result is all-NaN so the UI hides the panel instead of painting the basin as max priority.
- FILES MODIFIED: `src/oceanembed/products/observation_priority.py`,
  `tests/test_observation_priority.py` (new), `docs/ARCHITECTURE.md`, `docs/HANDOFF.md`.
- NEXT (A): LightGBM baseline + quantile uncertainty (`models/lgbm_baseline.py`,
  `train/train_lgbm.py` — both still stubs). Then rebase the useful parts of `feat/unit-a-mlp`
  (weights_only=True safety, norm-stats-in-checkpoint, fixture-provenance guard D-010, 17 tests).
- STILL OPEN FOR B: the `.gitignore` blocker above; **D-008** depths (now VERIFIED from the official
  page https://sih2026.vuce.in/en -> SIH26066: 15 levels to 1000 m, ours is 11 to 500 m);
  **D-009** raw-in vs z-scored-in for `predict_mlp` (your committed version is z-scored-in, but you
  asked for raw-in).
- WITHDRAWN by A: **D-011** (fixture physics) is now moot — the pipeline trains on synthetic GLORYS
  via `build_samples`, not on `sample_X.npy`. Don't spend time on it.

## 2026-08-25 — Unit B — Day 4: reconstruct() seam + Streamlit demo (CLICKABLE)
- WHAT WORKS [VERIFIED by execution]:
  - `inference/predict.py`: `reconstruct(lat,lon,date)` → profile_mean/std, reliability, climatology, anomaly,
    surface vars, land handling. `reconstruct_grid(date)` → temp/uncertainty/anomaly/priority (100,240,11) in ~3.6 s.
  - `app/streamlit_app.py`: launches headless, serves **HTTP 200**, clean log. streamlit 1.62.0 installed.
  - Land/no-data points correctly rejected; ocean profile 25.5 °C → 8.65 °C @500 m (physically sensible).
- ⚠️ STILL SYNTHETIC DATA — the app shows a loud SYNTHETIC banner until real GLORYS is downloaded. Do not demo as real.
- **NO-COLLISION DESIGN (important for A & C):**
  - The shell auto-detects `app/panels/<x>_panel.py::render()`. Until Unit C writes them it draws minimal fallbacks.
    **Unit C's panels slot in with zero edits to `streamlit_app.py`.** [VERIFIED: detection returns fallback today.]
  - `reconstruct_grid` returns `priority=None` until **Unit A** implements `observation_priority()`; the UI then
    shows the panel automatically. [VERIFIED: currently None, no crash.]
  - `anomaly` uses Unit C's `products/anomaly.py` when implemented, else the plain definition.
  - I did NOT touch `app/panels/*`, `products/anomaly.py`, or `products/observation_priority.py` — still A's and C's.
- ALSO FIXED: `utils.io.save_table` now deletes the other-format twin so a stale .csv can never shadow a fresh
  .parquet (pyarrow got installed, so tables are parquet now).
- NEXT (B): real CMEMS download → `prepare_dataset.py --real` → rerun slice + app for REAL numbers; DEMO_SPEC scenes.

## 2026-08-25 — Day 3 vertical slice COMPLETE (climatology + MLP + metrics + uncertainty)
- CURRENT PHASE: Day 3 — end-to-end slice runs. BRANCH: main.
- WHAT WORKS [VERIFIED by execution] — `python scripts/run_slice.py`:
  climatology baseline → MLP training (early stop) → honest 2022-test evaluation → per-depth skill →
  MC-dropout uncertainty → auto-append to docs/EXPERIMENT_LOG.md.
- IMPLEMENTED: `validation/metrics.py` (compute_metrics), `climatology.py` (build/predict),
  `models/mlp_profile.py` (torch MLP 11→128→128→11, dropout 0.2), `train/train_mlp.py` (seeded, early stop),
  `inference/uncertainty.py` (MC-dropout, 30 passes). torch 2.9.1+cpu and sklearn confirmed installed.
- ⚠️ NUMBERS ARE ON **SYNTHETIC** DATA — ILLUSTRATIVE ONLY, NOT REAL PERFORMANCE. The synthetic field is a smooth
  function of lat+season, so it is trivially learnable (R²≈0.999). **Never quote these to judges.** Real GLORYS
  numbers will be much less flattering — that is expected and fine.
- SCIENTIFICALLY ENCOURAGING [VERIFIED]: per-depth skill vs climatology DECREASES with depth
  (+0.812 @0 m → +0.145 @500 m), the physically expected pattern (surface data constrains deep temperature less).
- FINDING (uncertainty): absolute MC-dropout std SHRINKS with depth (0.214→0.029 °C). This is NOT necessarily a bug —
  deep water is naturally less variable (natural std 1.341→0.236 °C). The slice therefore reports the
  **std/natural-variability ratio** (~0.15, near-constant here) and per-depth skill as the honest diagnostics.
  RE-CHECK on real data before making any uncertainty claim.
- NEXT (A/Arjhun): LightGBM baseline + quantile uncertainty; tune MLP on REAL data; observation_priority().
- NEXT (C/Mitun+Niru): anomaly.py, validate_argo.py, UI panels; fill LITERATURE_MATRIX from the PDFs.
- NEXT (B/Darshan): real CMEMS download → `prepare_dataset.py --real` → rerun slice for REAL metrics; then
  predict.py seam + Streamlit wiring.

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
