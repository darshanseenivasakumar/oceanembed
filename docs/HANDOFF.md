# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```

## 2026-08-25 — Unit B — REAL Argo data + critical .gitignore fix

### 🔴 CRITICAL BUG FIXED — repo was incomplete for everyone
`.gitignore` had a bare `data/` pattern, which matches ANY directory named `data` at any depth — so
**`src/oceanembed/data/` (download_glorys, download_argo, preprocess) was NEVER committed**. A fresh clone
would die with ImportError. Patterns are now root-anchored (`/data/`, `/artifacts/*`, `/all research papers/`).
[VERIFIED] fresh `git clone` now imports every module including `data/`.
**Everyone: `git pull` — you were missing the data module.**

### ✅ REAL Argo data downloaded (no credentials needed — Argo is public)
`artifacts/argo_test.parquet`: **24,328 measurements / ~2,453 real profiles**, NIO, all 12 months of 2022.
100% inside our region; 29.0 °C @0 m → 12.2 °C @500 m; QC flags {1,2} only; no extrapolation.
(This file is gitignored — regenerate with `python -m oceanembed.data.download_argo`, ~5 min.)

### ✅ GLORYS dataset id VERIFIED (no login needed for the catalog)
`cmems_mod_glo_phy_my_0.083deg_P1D-m` — confirmed via `copernicusmarine.describe`. The **download** still
needs a free CMEMS account.

### ⚠️ DO NOT run Argo validation yet — it would be meaningless
The current `mlp_model.pt` is trained on **SYNTHETIC** GLORYS. Comparing a synthetic-trained model against
**real** Argo profiles produces garbage numbers that would look like a real result. Sequence must be:
real GLORYS download → retrain → *then* Argo validation. Unit C: build `validate_argo.py` against the
committed fixtures/structure, but do not publish metrics until the model is trained on real data.

### Environment notes (saves everyone hours)
- `erddapy<3` pinned — argopy 1.4.0 imports a symbol removed in erddapy 3.x.
- Windows SSL: `download_argo._fix_ssl()` sets `SSL_CERT_FILE` from `certifi` (ERDDAP fails otherwise).
- Verified working combo: pandas 2.3.3, xarray 2025.9.0, numpy 2.3.5, torch 2.9.1+cpu, streamlit 1.62.0.
- Regression-checked: pipeline + seam still pass after those dependency downgrades.

### NEXT
- **B (Darshan):** `copernicusmarine login` → download real GLORYS → `prepare_dataset.py --real` → retrain → real metrics.
- **A (Arjhun):** `observation_priority()` — the seam already calls it and shows the panel automatically once it exists.
- **C (Mitun+Niru):** panels (`render(recon_output, argo_df)`), `anomaly.py`, `validate_argo.py` (hold metrics until real data).






## 2026-08-25 - Unit A (Arjhun) - Day 5: RED TEAM (integration support is blocked)

- BRANCH: `feat/unit-a-priority`. **`pytest tests/ -q` -> 63 passed.**
- Day 5 is "help wire `predict.py`; freeze final weights; generate cached demo tensors; be available for red-team
  fixes." `predict.py` is Unit B's file, and freezing weights / caching demo tensors both need REAL data, which
  still does not exist. So I did the red-team half properly.

### Fresh-clone audit [VERIFIED by actually cloning main to a scratch dir]
  1. `import oceanembed`                     -> OK
  2. `python scripts/prepare_dataset.py`     -> **ModuleNotFoundError: No module named 'oceanembed.data'**
  3. `python scripts/run_slice.py`           -> "Run prepare_dataset.py first"
  4. `reconstruct(15.0, 88.0, '2022-06-15')` -> FileNotFoundError
  5. `streamlit run app/streamlit_app.py`    -> HTTP 200, clean `st.error`, no traceback
**The pipeline is dead for everyone but Darshan.** His untracked local `src/oceanembed/data/` makes it work on
his machine only - which is exactly why he cannot see it. Open for a full day of a five-day sprint (D-019).

### ⚠ D-018 - CRITICAL: the SYNTHETIC banner can silently switch itself off
`app/streamlit_app.py`:
    synthetic = os.path.exists(os.path.join(config.DATA_RAW, "synthetic_glorys.nc"))
The warning depends on a **gitignored** file existing on disk, and the artifacts carry NO provenance flag
[VERIFIED: `git check-ignore` confirms `data/` is ignored; `build_samples.py` writes no such flag].
**Demo-day failure path:** `artifacts/` is small and portable, `data/raw/` is large and gitignored. Copy the
artifacts to a demo laptop without `data/raw/` and the SYNTHETIC warning silently vanishes while the numbers stay
simulated - presenting synthetic data to judges as real ocean performance.
FIX (Unit B owns both files): write provenance INTO the artifacts (`{"source": "synthetic"|"real-glorys"}` in
`norm_stats.json` or a `provenance.json`) and have the app read that. Same principle as D-010, where the
checkpoint carries its own `trained_on_fixtures` stamp. **Until fixed: never demo from a machine without
`data/raw/`.**

### Clean results - worth recording, not just the problems
- **No hardcoded or fabricated metrics anywhere** in code or docs [VERIFIED by grep across *.py and *.md].
  The real-data-only rule is holding.
- App degrades gracefully on missing artifacts: `st.error` + `st.stop()`, never a traceback.
- Land / no-data points rejected with a clear message.
- Darshan's no-collision seam design works exactly as advertised: `observation_priority()` dropped in with zero
  edits to `predict.py` or `streamlit_app.py`.

- FILES MODIFIED: `docs/DECISIONS.md` (D-018, D-019), `docs/HANDOFF.md`. No code changes - every remaining Day-5
  task needs either Unit B's files or real data.
- OPEN FOR B, in priority order: **`.gitignore` blocker** (D-019, blocks everyone) | **D-018** synthetic-banner
  provenance (fabrication risk on demo day) | **D-016** MC-dropout overconfident at depth - decide whether the
  demo ships MC-dropout or quantile uncertainty | **D-008** depths 11@500m vs the statement's 15@1000m |
  **D-009** raw-in vs z-scored-in | add `lgbm_quantiles.pkl` to DATA_CONTRACT.md.

## 2026-08-25 - Unit A (Arjhun) - Day 4 COMPLETE (uncertainty investigated + bug fixed)

- BRANCH: `feat/unit-a-priority`. **`pytest tests/ -q` -> 63 passed.**
- Day 4 item 2 (`observation_priority()`): DONE earlier - see the entry below.
- Day 4 item 1 (`inference/uncertainty.py`): the sanity check the assignment asks for FAILS, and I
  investigated rather than papering over it. **This is the most important finding so far - read D-016.**

### D-016 - MC-dropout is OVERCONFIDENT at depth [VERIFIED by measurement]
The assignment says sigma should rise with depth. It falls (0.26 -> 0.055 degC). The cause is mechanical:
dropout perturbs a SHARED trunk feeding all 11 outputs, so spread is flat in NORMALIZED space
(std/targ_std = 0.127 -> 0.162, spread 0.043); multiplying by targ_std - which shrinks with depth - makes
real-units sigma shrink. **Darshan: your Day-3 explanation ("deep water is naturally less variable") is right,
but it is the CONSEQUENCE of the un-normalization, not independent confirmation that the uncertainty is sound.**

Calibration measured (sigma / actual RMSE; 1.0 = calibrated, <1.0 = OVERCONFIDENT):

        depth    MC-dropout    quantile
          0 m       1.25         0.70
        500 m       0.31         0.92
        drift       4.0x         1.8x

**MC-dropout under-states real error at 500 m by 3.2x** - most confident exactly where least trustworthy.
LightGBM quantiles are better calibrated because each depth has its own booster.
Expect this to WORSEN on real GLORYS: deep error will grow while MC-dropout sigma keeps shrinking.
**Do not quote MC-dropout confidence at depth in the demo or to a judge until re-measured on real data.**

### D-017 - BUG FIXED: mc_dropout_predict leaked train() mode
It called `model.train()` and never restored the previous mode, so every later plain forward pass on that model
was silently stochastic. `predict_mlp` masked it by calling `.eval()` itself, so nothing failed visibly - the kind
of bug that later shows up as irreproducible numbers. Fixed with save/restore in a `finally`, plus two tests.
[VERIFIED: model.training was True after the call before the fix, False after.]

### Added (Unit A files)
- `calibration_ratio(sigma, y_true, y_pred)` -> (11,) - the honest per-depth diagnostic. Use it instead of
  eyeballing whether sigma rises with depth; a rising sigma can still be badly calibrated.
- `relative_uncertainty(sigma)` -> sigma as a fraction of each depth's natural variability, so depths are
  comparable. 0.05 degC at 500 m (natural spread 0.34) is NOT the same confidence as 0.05 degC at the surface
  (natural spread 2.06). **Unit C: this is what the reliability panel should display, not raw degC.**
- `tests/test_uncertainty.py` - 13 tests including strictly-positive spread (zero spread = dropout off =
  fabricated certainty), mode restoration, and overconfidence detection.

- FILES MODIFIED: `src/oceanembed/inference/uncertainty.py`, `tests/test_uncertainty.py` (new),
  `docs/DECISIONS.md` (D-016, D-017), `docs/HANDOFF.md`.
- NEXT (A): Day 5 integration support. Still blocked from any REAL number by the `.gitignore` issue.
- OPEN FOR B (unchanged): `.gitignore` blocker | **D-008** depths (15 to 1000 m per the official page) |
  **D-009** raw-in vs z-scored-in | add `lgbm_quantiles.pkl` to DATA_CONTRACT.md | **D-016** decide whether the
  demo ships MC-dropout or quantile uncertainty.

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
