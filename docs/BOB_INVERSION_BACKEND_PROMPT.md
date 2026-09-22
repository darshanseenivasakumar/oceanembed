# Feature request: finish the Bay of Bengal winter-inversion study (Phases 2–4) + a UI-ready results contract

Hand this file to Claude and start in **plan mode**, on branch `phase2-bob-inversion`. Read, in
order: `CLAUDE.md`, `docs/phase2/f_inversion.md`, `docs/DECISIONS.md` D-020, `docs/EXPERIMENT_LOG.md`
E-INV-00, then this file. Do not skip those — every threshold, date window, and pass/fail rule this
feature uses is pre-registered there, and re-deriving them here would risk contradicting the
frozen definitions.

## What this feature is (one paragraph, for orientation)

The northern Bay of Bengal gets a fresh, light "lid" of river runoff (Ganges/Brahmaputra) that
stops winter cooling from mixing downward — so the surface goes colder than the water 20–150 m
below it, backwards from the "warm surface ⇒ warm below" assumption every SST-driven depth model
makes, including this one. This feature (1) already measured that the phenomenon is real in the
truth data, (2) needs to measure whether the shipped model gets it wrong on a winter it never
trained on, and (3) tries a small set of pre-registered, cheap training changes to see if any fixes
it without hurting the headline 0.9063 °C number.

## Current state — verified by inspection just before writing this, do not re-trust blindly

**Committed, on `phase2-bob-inversion`:**
- Phase 0 (literature, `D-020`, `E-INV-00` pre-registration) — done.
- Phase 1: `src/phase2/derived/inversion.py` (`inversion_amplitude`, `inversion_field`, `present()`,
  `region_labels()`), `src/phase2/derived/inversion_skill.py` (`contingency`, `amplitude_stats`,
  `depth_stats`, `three_seed_summary`, `adopt()`), `src/phase2/tscast_nio/time_encoding.py`
  (`doy_encoding`). 38 tests. Real-data smoke test on GLORYS matches Thadathil et al. 2016 (north
  Bay ~90% winter days inverted here vs ~80% in the paper). This is the E-INV-00 truth-side sanity
  gate — PASSED.
- Fix-ladder leg **L1** (`--doy`, day-of-year channels) — wired into `train_stage1.py`.
- Fix-ladder legs **L2** (`--w-grad-shallow`) and **L3** (`--w-sign`) — wired ("the sign hinge and
  shallow-gradient terms, wired and smoke-run" per commit history).
- `winter_holdout_v1` protocol constants in `src/phase2/tscast_nio/protocols.py`
  (`WINTER_TEST_START/END` = 2024-12-01..2025-02-28, `WINTER_BUNDLE_START/END` =
  2024-11-20..2025-03-10).

**Uncommitted, sitting in the working tree right now — commit this first, as its own step, before
building anything new:**
- Fix-ladder leg **L4** (`--w-inv-sample α`, sample reweighting) and **L5** (`--aux-inversion`,
  auxiliary BCE presence head) — fully wired in `train_stage1.py` and `models/tscast.py`
  (`inversion_target`, `bce_inversion_loss`, `TSCastNIO(aux_inversion=...)`).
- `tests/phase2/test_inversion_losses.py` gained 6 new tests for L4/L5. **Verified: 13/13 pass**
  (`python -m pytest tests/phase2/test_inversion_losses.py -q`).
- Also uncommitted: `.claude/launch.json`, `scripts/phase2/measure_cloud_robustness.py` — unrelated
  to this feature, leave them alone, don't fold them into this commit.

**Not started — confirmed missing by directory/file search:**
- `data/processed/daily_sat/v001` (the satellite-input training bundle) **does not exist on this
  machine at all.** `data/raw/satellite/` and `data/raw/satellite_daily/` DO exist — check whether
  they already cover a wide enough date range that `src/phase2/tscast_nio/sat_daily_pipeline.py`
  can build `daily_sat/v001` from what's already downloaded, before assuming a fresh download is
  needed. This blocks not just the ladder but the winter-holdout CONTROL run too.
- No winter 2024–25 data anywhere under `data/`. Needs a new download (GLORYS + the satellite L4
  products, matching `download_daily_2025_2026.py`'s pattern and CMEMS credentials — already saved
  at `~/.copernicusmarine-credentials`, confirmed present) for `WINTER_BUNDLE_START..END`.
- No Argo winter truth table (`artifacts/argo_winter2425.parquet` — name from D-020 §3). Needs
  fetching Argo profiles for the winter window and running them through the same UNESCO-1983
  depth-axis conversion as `phase2.data.argo_depth` (D-018/audit #8 — do NOT reuse the old
  pressure-as-depth path).
- These scripts named in `docs/phase2/f_inversion.md`'s Units table do not exist yet:
  `scripts/phase2/download_winter_holdout.py`, `build_winter_bundles.py`, `run_inversion_study.py`,
  `run_inversion_ladder.py`.
- The frozen-hyperparameter dry run (W for L3, α for L4) required by E-INV-00 before any 3-seed
  run has not happened — no value is recorded in `EXPERIMENT_LOG.md` E-INV-00 yet.
- Leg **L6** (union of adopted legs) has no code — it can't, until L1–L5 results say which legs
  adopted.

## What to build, in this order (do not skip ahead — each step gates the next)

### Step 1 — commit the L4/L5 WIP
Smallest possible commit: the 4 files listed above under "uncommitted", nothing else. Message
should read like the existing history (`git log --oneline` on this branch for tone). Run the full
`tests/phase2/` suite first, not just the new file, in case L4/L5 touched something shared.

### Step 2 — Phase 2: get the satellite bundle onto this machine
1. Inspect `data/raw/satellite/` and `data/raw/satellite_daily/` — date coverage, which products
   (`sat_daily_pipeline.py` names them). If they already span the deliverable's training window,
   just run the existing pipeline to produce `data/processed/daily_sat/v001`. Confirm with
   `scripts/phase2/verify_sat_bundle.py` before trusting it.
2. Only if genuinely missing data, extend `download_daily_2025_2026.py`'s pattern for whatever
   satellite window is short. Do not touch GLORYS download logic — that data already exists.

### Step 3 — Phase 2: the winter holdout bundle
1. Write `download_winter_holdout.py` (model it directly on `download_daily_2025_2026.py`): GLORYS +
   the 3 satellite L4 products (bias-corrected the same way the shipped satellite model expects —
   check `oceanembed.data.download_satellite`'s bias-correction step, D-018/D-020 note it uses
   TRAIN-period dates only, so confirm the winter window doesn't silently reuse a train-period
   correction it shouldn't) for `WINTER_BUNDLE_START..WINTER_BUNDLE_END`.
2. Write `build_winter_bundles.py`: produces the evaluation-only bundle at
   `data/processed/daily_sat/v001_winter2425/` (satellite input) **and** a GLORYS-input twin (for
   the attribution check in E-INV-00's "Attribution" clause), both stamped
   `role: held-out evaluation only, never training` in provenance, both using `seafloor_masked_v2`'s
   mask and depth-axis rules (`WINTER_HOLDOUT_PROTOCOL` already encodes this — read it before
   writing this script, don't reinvent the mask/axis choice).
3. Build `artifacts/argo_winter2425.parquet` the same way `argo_daily_period.parquet` was built
   (metres via UNESCO-1983), for the winter window. Print and record the count of truth-present
   profiles per region (north Bay, south Bay, Arabian Sea) — E-INV-00's "sample-size rule" needs
   this BEFORE any scoring: if north Bay has < 30 truth-present profiles, GLORYS-dense scoring on
   the 30 sampled days is used instead, not Argo.

### Step 4 — Phase 3: H1 (does the problem exist)
1. Train (or reuse, if a byte-identical checkpoint already exists) the CONTROL: same recipe as
   `sat_7ch` in `run_sat_ablations.py`'s `BASE_ARGS`, 3 seeds (42, 43, 44).
2. Write `run_inversion_study.py`: scores each control checkpoint on `winter_holdout_v1` using
   `derived/inversion.py` + `derived/inversion_skill.py` (`contingency`, `amplitude_stats`,
   `three_seed_summary`), computing POD and amplitude bias in the northern Bay (≥15°N inside
   `basins.BAY_OF_BENGAL`). Also run the GLORYS-input checkpoint on the GLORYS-input winter bundle
   for the attribution comparison.
3. Apply E-INV-00's H1 rule exactly: POD < 0.5 and/or amplitude bias ≤ −50% ⇒ H1 confirmed, proceed
   to legs. POD ≥ 0.8 and |bias| < 25% ⇒ H1 rejected — **stop here, report "verified + mapped", do
   not fabricate a fix-ladder result for a problem that didn't reproduce.**
4. Write the verdict into `EXPERIMENT_LOG.md` under E-INV-00 (append, don't create a new entry) and
   into `docs/phase2/f_inversion.md`'s status table (Phase 3 row).

### Step 5 — Phase 4: frozen hyperparameters, then H2 (only if H1 confirmed)
1. **Before touching the 3-seed runs**: run the 1-seed, 2-epoch dry run for W (L3) and α (L4) per
   the exact procedure in E-INV-00 ("Frozen hyper-parameters" paragraph). Append the chosen numbers
   to that E-INV-00 entry immediately, with the numbers that justified them (loss-fraction at
   epoch 1 for W, loss-mass share for α). **Do not revisit these after seeing winter scores** — if
   you're tempted to, that's the sign to stop and flag it to the user instead of adjusting quietly.
2. Write `run_inversion_ladder.py`: orchestrates `train_stage1.py` for legs L1–L5 (L6 later, see
   below), 3 seeds each, tags `inv_<leg>_s<seed>` (the `--tag` guard already in `train_stage1.py`
   enforces this can't silently overwrite the deliverable). Resumable — skip a leg/seed whose
   checkpoint+metrics already exist, matching `run_sat_ablations.py`'s pattern.
3. Score each leg on `winter_holdout_v1` (CSI, from `inversion_skill.contingency`) and on
   `seafloor_masked_v2` (the existing headline protocol, RMSE only — reuse existing eval, don't
   write a new one). Apply `inversion_skill.adopt()` — it already encodes E-INV-00's exact adopt
   rule (beats control on every seed, 3-seed mean gain > control's CSI sd, RMSE cost ≤ +0.004°C).
4. If ≥2 legs adopt, build **L6** = union of their flags, run it 3 seeds too, score the same way.
5. Any leg (including L6) that passes `adopt()` goes through `promote_run.py` with its own ADR —
   do not promote by hand-editing the shipped checkpoint path.
6. Record every leg's verdict — adopted AND rejected — in `EXPERIMENT_LOG.md` E-INV-00 and
   `docs/phase2/f_inversion.md`. A rejected leg is still a result; don't omit it.

### Step 6 — a stable, UI-ready results contract (do this regardless of H1/H2 outcome)
Whatever the verdict, the frontend (Arjhun, separate prompt, separate session) needs one clean,
already-computed thing to render — not raw arrays it has to interpret. Add a small module, e.g.
`src/phase2/derived/inversion_report.py`, exposing something like:

    from phase2.derived.inversion_report import summary
    s = summary()   # reads whatever artifacts this feature wrote; no recomputation, no training

`summary()` should return (shape driven by whatever actually got produced, so don't guess numbers
here — read them off the real artifacts):
- the truth-side finding (north/south/Arabian frequency + amplitude, with the literature comparison
  numbers already computed in Phase 1's smoke test, saved to an artifact instead of only living in
  `HANDOFF.md` prose),
- the H1 verdict (confirmed/rejected, POD, amplitude bias, which is the headline for this feature),
- the H2 verdict if H1 was confirmed (adopted leg(s) if any, their CSI gain and RMSE cost; "no leg
  adopted" is a valid, reportable value — do not hide it),
- every caveat already listed in `docs/phase2/f_inversion.md`'s "What this feature refuses to do"
  section, verbatim, so the UI can display them next to the numbers rather than a frontend author
  having to go find and rephrase them.

This mirrors how the What-If Calculator feature exposed `oceanembed.whatif.baseline/apply/
list_formulas` as the one contract the UI needed — same idea: backend computes and freezes the
result, frontend only renders it.

## Hard constraints (repeating the pre-registered rules so they aren't silently drifted from)

- Never compare a `winter_holdout_v1` number against the 0.9063°C `seafloor_masked_v2` headline —
  different period, different bundle, D-020 §3 is explicit that these must never be conflated.
- A leg is **NOT A RESULT** below 3 seeds. Don't report a 1-seed number as if it were one, even
  informally in a doc.
- `W` and `α` are frozen before any 3-seed run and never revisited after seeing winter scores.
- Every experimental `train_stage1.py` flag already refuses to run without `--tag` — keep using it;
  don't add a bypass.
- Model-side barrier layer thickness is refused (needs salinity; stage 2 has never run on satellite
  input) — don't attempt to compute or display one.
- Don't cite an inversion threshold from a paper nobody on this project has read; 0.2°C is the
  house ILD criterion, not a claimed match to Thadathil's threshold (which is `[UNKNOWN]` per D-020
  until someone reads the full text).
- `train_stage1.py` and `models/tscast.py` are Unit A files; D-020's header already records that
  this branch touches them additively with Darshan's approval — list every touched file in the
  eventual PR description, per that note.
- Follow `CLAUDE.md`'s engineering loop for every step above: understand → inspect → plan →
  implement smallest version → test → real-data smoke test → update `docs/HANDOFF.md` → commit.
  Don't batch steps 2–5 into one giant commit.
- Tag every claim `[VERIFIED]` / `[INFERRED]` / `[UNKNOWN]` per `CLAUDE.md`'s 15 rules — especially
  for anything about data coverage, GPU run time, or whether H1/H2 will confirm, before it's
  actually measured.

## Out of scope for this prompt

- The actual frontend (`app/ui/features/inversion.py`) — Arjhun's, and needs its own prompt written
  once Step 6's contract exists and the H1/H2 verdict is known (the UI's shape depends on the
  verdict — e.g. whether there's an adopted-fix comparison to show at all).
- Retraining or modifying the shipped `seafloor_masked_v2` deliverable checkpoint directly.
- Any depth/threshold decision not already made in D-020 — if a new one seems necessary, stop and
  raise it rather than deciding it inline.
