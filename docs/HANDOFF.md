# HANDOFF.md — live status baton (appended by EVERYONE, newest on top)

> After every work session, add a dated entry. This is how three Claude accounts stay in sync.
> Template:
> ```
> ## YYYY-MM-DD — <name/unit>
> CURRENT PHASE: | BRANCH: | WHAT WORKS: | WHAT IS BROKEN: | LAST CHANGE: |
> FILES MODIFIED: | TESTS RUN: | KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
> ```


## 2026-08-25 - Unit A+C (Arjhun) - spec-compliance guards; ONE depth fix needed before you retrain

Branch **`feat/spec-compliance`**, off current `main`, 0 conflicts.
**`pytest tests/ -q` -> 141 passed, 1 skipped, 1 xfailed** [VERIFIED].

### ⚠ DO THIS WHEN THE DOWNLOAD LANDS, BEFORE RETRAINING: swap 400 -> 5
You ruled "15 levels to 1000 m" and executed 15 levels - but not the problem statement's 15.

```
PS   [0, 5,10,20,30,50,75,100,125,150,200,300,    500,700,1000]
main [0,   10,20,30,50,75,100,125,150,200,300,400,500,700,1000]
     missing from ours: [5]      extra in ours: [400]
```

Right count, wrong set. This is the single cheapest thing a judge can check - two lists side by
side, five seconds, no code read.

**The fix needs NO re-download.** Your `MAX_DEPTH = 1100` means the GLORYS file already holds every
level down to 1062 m, so which depths we interpolate ONTO only affects `preprocess` ->
`build_samples` -> retrain. Do it before the retrain or that training run is wasted.

If 400 m was deliberate - and scientifically it IS more useful than 5 m, which sits ~4.5 m from
GLORYS' shallowest level at 0.494 m - then keep it as a **16th** level and record the reason in
`DECISIONS.md`. Nothing stops us being a superset of the PS. What must not happen is a silent
substitution that a judge finds first.

`config.py` is your file, so this is flagged, not edited.

### New guard 1: `tests/test_spec_compliance.py`
Asserts the frozen constants against SIH26066 - region, 0.25 deg, 100x240 grid, the depth list, the
five surface variables, temporal split. 12 tests, 11 pass.

The depth mismatch is recorded as **`xfail(strict=True)`**, not a hard failure, so the suite stays
green during the sprint. **Verified the strictness works rather than assuming it:** temporarily
setting `DEPTHS` to the PS list turns it into `XPASS(strict)` and FAILS. So the moment you fix it,
the marker must be deleted - the exemption cannot outlive the bug, whether or not anyone remembers.

### New guard 2: `VALIDATION_PROTOCOL.md` L1 is now a real section
Your extrapolation catch leads it, with the mechanism written out: `maximum_depth=520` -> data
actually stopping at 453.94 m -> preprocess extending **46 m past the end of the data** to
manufacture every "500 m" value, with correct shapes so nothing complained anywhere.

**My two cells from that run are recorded as VOID and discarded**: 0.4765 degC (LightGBM) and
0.4718 degC (MLP) at 500 m. They were labelled synthetic plumbing numbers, so nothing downstream
inherited them.

The accepted exception is documented too - 0 m against GLORYS' 0.494 m is a ~0.5 m gap inside a
well-mixed layer, categorically different from inventing 46 m of thermocline.

The generalisation is the part worth keeping: **a shape check is not a validity check.** Ask of
every array, *"could this have been produced without real data behind it?"* That question catches
your extrapolation bug, the synthetic-banner gap, and the provenance gap - all three were
correctly-shaped, plausible-looking, and wrong.

### Your extrapolation catch was better than the novelty catch
Finding it required investigating a decision rather than executing it. Correct shapes are exactly
why nothing caught it - no test, no assert, no reviewer. That is the hardest class of bug there is.

### Standing, unchanged
- **D-016**: MC-dropout overconfident at depth (sigma/RMSE 1.25 at 0 m -> 0.31 at 500 m, understates
  real error 3.2x). Expect it to get WORSE at 700/1000 m, not better. Decide whether the demo ships
  MC-dropout or LightGBM quantiles (0.70 -> 0.92, far better calibrated).
- Agreed on deep skill: report per-depth plainly, do not hide it behind a pooled RMSE. TS-Cast stops
  at 700 dbar and states the same bound.

### Ready on my side
Not retraining until the data lands, as you said - and `preprocess` will refuse the old data anyway,
which is the point. Once it lands and DEPTHS is settled: retrain both -> `compare_models` gives the
first REAL verdict -> `validate_argo` opens its own gate automatically when provenance reads `real`.
About 30 minutes.

## 2026-08-25 — 🎯 FIRST VALID 15-DEPTH RESULTS (held-out 2022, n=107,676)

```
  model              RMSE      MAE   skill_vs_clim
  climatology      1.6921   1.3248        --
  lightgbm         0.6329   0.3947      +0.626
  mlp              0.6323   0.4059      +0.626      <- TIE (0.1%), D-015 fires, ship the simpler
```

### ⚠ I WAS WRONG about deep skill — and the truth is a better story
I told the team to "expect deep skill to be poor" (citing TS-Cast stopping at 700 dbar). **The data
says otherwise.** Per-depth skill vs climatology:

```
  depth   clim_RMSE   lgbm_RMSE    SKILL
      0       1.512       0.070    +0.954
      5       1.488       0.121    +0.918
     10       1.490       0.161    +0.892
     20       1.510       0.294    +0.806
     30       1.575       0.441    +0.720
     50       1.791       0.696    +0.612
     75       2.080       0.957    +0.540
    100       2.166       1.068    +0.507   <-- WORST
    125       2.159       1.039    +0.519
    150       2.132       0.937    +0.561
    200       1.897       0.708    +0.627
    300       1.552       0.493    +0.682
    500       1.199       0.380    +0.683
    700       1.222       0.360    +0.705
   1000       1.048       0.406    +0.612
```

**Skill is worst at the THERMOCLINE (+0.507 at 100 m), not at the deepest level (+0.612 at 1000 m).**
It is positive at EVERY depth. Physically this makes sense: the surface layer is near-directly
observed (SST), the thermocline is where variability peaks and the surface signature is most
ambiguous, and below it water masses are more stable while SSH integrates the whole column.

**Do not quote raw deep RMSE as if it were skill.** 1000 m RMSE is 0.406 degC, which *looks* better
than the thermocline's 1.068 — but climatology is also easier there (1.048 vs 2.166). Skill is the
honest comparison, and it is why Unit C's insistence on `r2_by_depth`/`skill_vs_clim` over pooled
metrics matters.

**Pitch line:** "positive skill at all 15 PS depths to 1000 m; hardest at the thermocline, which is
exactly where the physics says surface data is least informative." That is defensible AND it names
our own weak point first.

### MLP vs LightGBM: TIE again (0.1%)
Second dataset, same verdict. With 11 tabular per-column features there is no spatial structure for
a network to exploit. This is now *evidence*, not a hunch, and it is the argument for the Phase-2
CNN — not an argument against the project.

## 2026-08-25 — Unit B — REBUILD DONE at PS depths + domain shift MEASURED

### ✅ Real 15-depth build
`prepare_dataset.py --real` on all 48 GLORYS dates: grid **100x240x15**, train **323,028** /
test **107,676**. Provenance flips clean: `source=real-glorys, n_depths=15, stale=null`.
L1 sanity passes: monotonic cooling 28.49 -> **7.73 degC at 1000 m**, no NaNs.

**Independent corroboration [VERIFIED]:** GLORYS says **7.73 degC** at 1000 m; our real Argo says
**7.98 degC**. Two entirely separate sources agreeing within 0.25 degC at the deepest level.

### 📊 DOMAIN SHIFT: real satellite L4 vs GLORYS (12 common dates, 2022)
```
  var    bias(sat-glo)      RMSD    corr    n_cells
  sst          -0.0760    0.4954   0.961     138564
  sss          +0.3422    1.4429   0.860     137136
  ssh          +0.4169    0.4191   0.975     138888
  u            -0.0234    0.1856   0.702     138888
  v            +0.0183    0.1773   0.678     138887
```
**Every prediction logged BEFORE measuring was confirmed:** SST high-corr/low-bias; ADT vs zos
high-corr with a LARGE offset (+0.417 m, I predicted ~0.4 m); geostrophic currents ~0.70 corr
because they are a different physical quantity from GLORYS' full flow. That the predictions were
recorded first is what makes these attributable rather than post-hoc.

**SSH corr 0.975 with a pure offset** -> bias correction is clean and justified (near-perfect shape
agreement, wrong level). **Leakage trap avoided:** satellite data so far covers only 2022 = the TEST
year, so fitting the offset there would leak. Downloading 4 dates/year across 2019-21 to fit the
correction on TRAIN dates only.

### 🔴 BUG FOUND — SSS came through with the wrong SHAPE and the bounds check missed it
The Multiobs SSS product carries a **depth** axis, so `sos` is (time, depth, lat, lon) while
OSTIA/DUACS are (time, lat, lon). `_regrid` squeezed only `ndim == 3`, so SSS stacked as
**(12, 1, 1, 100, 240)**. The per-variable physical bounds check PASSED, because a bounds check
inspects VALUES, not SHAPE — and there was no shape assert at all.
FIX: squeeze all leading singleton axes, then **assert the result is exactly (100, 240)** with the
source dims in the message. Third instance of the same lesson: plausible values are not proof of a
correct array.

## 2026-08-25 — Unit B — satellite path WORKS, and the ADT/zos offset is real

`download_satellite` + `preprocess_satellite` verified end to end on all 12 test-year dates
[VERIFIED]: bounds checks pass, KELVIN -> degC conversion correct (OSTIA sst mean 28.30 degC).

### ⚠ EARLY WARNING — the SSH offset I predicted is large
    satellite adt  mean 0.88 m   (range 0.33 .. 1.70)
    GLORYS    zos  mean ~0.45 m  (range -0.09 .. 0.94, from the training artifacts)
A ~0.4 m systematic offset. This is NOT a bug — `adt` (absolute dynamic topography, referenced to a
mean geoid) and GLORYS `zos` are different reference surfaces. But it is CONSEQUENTIAL: in the
physics, SSH sets thermocline depth, so feeding adt straight into a zos-trained model displaces
every predicted thermocline. Expect a large skill drop on the satellite path until this is handled.

**Three options, in order of preference:**
1. **Bias-correct adt onto the zos scale** using the mean difference computed on **TRAIN-period**
   overlapping dates only. Standard practice. Using test-period dates to fit the correction would
   be leakage — do not.
2. Use DUACS `sla` (an anomaly, already de-meaned) plus the GLORYS train-period mean zos field.
3. Report the uncorrected drop honestly and name the cause.
Whichever we pick gets recorded before the number is quoted. `scripts/compare_satellite_vs_glorys.py`
measures bias/RMSD/correlation per variable and runs as soon as the GLORYS rebuild lands.

Prediction on record BEFORE measuring (so the result is attributable either way):
  sst -> high corr, small bias   |   adt/zos -> high corr, LARGE bias
  ugos/vgos vs uo/vo -> LOW corr (geostrophic-only vs full flow); that loss is physical, not a bug.

## 2026-08-25 — Unit B — DEPTHS now match the PS set exactly; spec-compliance guard green

Arjhun and I converged on this independently (messages crossed): my D-008 ruling shipped the right
COUNT but the wrong SET — I substituted 400 m for the PS's 5 m. Fixed:

    [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

**Decision: ship the PS's exact 15, NOT a 16-level superset.** Arjhun offered keeping 400 m as a
16th level, and he is right that 400 m is scientifically more useful than 5 m. I still chose exact
match: 5 m is a genuine GLORYS level (0.494, 1.5, 2.6, 3.8, 5.1 m) so it is NOT redundant with 0 m;
"right count, right set" is the cheapest thing a judge can verify; and a 16th level widens every
array in the codebase for marginal gain. 400 m is a Phase-2 candidate.

**No re-download needed** — `MAX_DEPTH=1100` already pulls every level to 1062 m, exactly as Arjhun
predicted. Only preprocess -> build_samples -> retrain are affected, and none has run on the new data yet.

Merged `feat/spec-compliance`. His `xfail(strict=True)` did exactly its job: the moment 400 -> 5
landed it flipped to XPASS(strict) and FAILED, forcing the marker's deletion. Removed, with the
decision recorded in its place. **142 passed, 1 skipped, 0 xfail.**

Also swept the stale depth docstrings (`(N,11)` -> `(N,15)` etc). No functional literal existed —
every assertion already used `config.N_DEPTHS` — but a docstring that lies about a tensor shape is
how the next silent bug starts.

### On his generalisation — worth repeating in the pitch
"A shape check is not a validity check. Ask of every array: could this have been produced without
real data behind it?" That single question catches all three of our silent failures — the 46 m of
extrapolated thermocline, the self-disabling SYNTHETIC banner, and the provenance gap. All three
were correctly shaped, plausible, and wrong.

### Status
Real satellite L4 path is BUILT (approved): `download_satellite.py` + `preprocess_satellite.py` +
`predict.set_source('glorys'|'satellite')`. Dataset ids, variable names and units all verified by
probe download — OSTIA is in KELVIN, and `preprocess_satellite` asserts physical bounds so a missed
conversion fails loudly. Downloading now alongside GLORYS.

## 2026-08-25 — Unit B — D-011 CLOSED (fixtures now exercise the multi-feature problem)

Arjhun's last open item against Unit B. His measurement: `make_fixtures` built the target as a pure
function of SST, so `r(ssh, T) = -0.002..+0.041` at EVERY depth — 10 of 11 features were decoys,
nothing tested feature combination, and Unit C's panels rendered an ocean where SSH did nothing.

**FIX:** the profile is now built the way the ocean actually encodes subsurface information —
a two-layer profile whose THERMOCLINE DEPTH is displaced by SSH:

    T(z) = T_deep + (T_surface - T_deep) * 0.5 * (1 + tanh((z_t - z)/w))
    z_t  = 120 m + 180*ssh + 25*seasonal + 30*v        (clipped 40-400 m)
    T_deep = 8.0 - 0.05*(lat-5) + 0.6*ssh              (weak, real deep structure)

A positive sea-level anomaly = a deeper thermocline (warm water piled up, as in an anticyclonic
eddy). So SST sets the mixed layer, **SSH sets where the transition happens**, season shifts both,
and `v` tilts it. SSS stays only weakly informative — honest, since salinity says little about
temperature.

**MEASURED after the fix** (`scripts/make_fixtures.py` prints this table every run):

    depth      r(sst,T)   r(ssh,T)
        0        +0.802     +0.748
      125        +0.612     +0.885     <- SSH dominates at the thermocline
     1000        +0.672     +0.308     <- weak but learnable

Second pass caught my own regression: with a CONSTANT `T_deep`, depths 500-1000 m came out as pure
noise (r ~ 0.02), so deep-level tests would have proved nothing. Deep temperature now varies with
latitude and SSH, matching the ~7.98 degC our real Argo shows at 1000 m.

Fixtures are regenerated at **15 depths** and committed. `tests/test_shapes.py` updated 11 -> 15
(it failed first, which is exactly what that guardian is for). **130 passed, 1 skipped.**

All four Unit-B items Arjhun raised are now closed: D-008 (depths), D-012 (lgbm_quantiles row),
D-018 (provenance), D-011 (fixtures).

## 2026-08-25 — Unit B — 🎉 FIRST REAL RESULTS on real GLORYS (+ a demo-breaking bug fixed)

### ✅ Real data pipeline complete
48/48 GLORYS dates downloaded (2.61 GB, 2019-01-15..2022-12-15, 12 dates/year).
`prepare_dataset.py --real` -> **338,508 train / 112,836 test rows**, real coastline (12,168 land cells).
L1 SANITY PASSED [VERIFIED]: SST 18.6-33.5 degC, SSS 17.1-37.8 psu (the low tail is Bay of Bengal
river freshwater — physically real), mean profile cools monotonically 28.5 -> 11.2 degC, zero NaNs.

### 📊 HONEST RESULTS — held-out 2022 test year, n=112,836, never seen in training
```
  model              RMSE      MAE   skill_vs_clim
  climatology      1.7617   1.3791        --
  lightgbm         0.6561   0.4135      +0.628
  mlp              0.6563   0.4275      +0.627
```
Both models beat climatology by ~63%. **MLP vs LightGBM is a TIE (0.0% gap)** — Arjhun's D-015 rule
fires correctly and defaults to the simpler model.

Per-depth RMSE peaks at **100 m (~1.07 degC)** and is lowest at the surface (~0.07-0.11 degC). That is
the THERMOCLINE — the depth with the steepest gradient and the least surface-visible information.
Physically expected, and a much better story than a flat number.

**Honest read of the tie:** with 11 tabular per-column features there is no spatial structure for a
neural net to exploit, so it cannot beat trees. That is evidence FOR the Phase-2 CNN/ConvLSTM, not
against the project — and it is exactly what TEAM_PLAN said to do: report it either way.

### 🔴 DEMO-BREAKING BUG FOUND AND FIXED — `mc_dropout_predict` was on the old contract
`inference/uncertainty.py` called `model(xt)` directly and scaled with `norm_stats.json`, i.e. it
still expected PRE-Z-SCORED input after `predict_mlp` moved to raw-in (D-009). Feeding it the raw
features the contract promises produced **52 degC surface temperatures from a 28 degC SST** — silently,
because every shape was correct. **130 tests passed with this bug present.**
FIX: it now normalizes/denormalizes through the MODEL'S OWN buffers, identical to `predict_mlp`, so a
checkpoint can never be paired with stats it was not trained with.
[VERIFIED after fix] 15N 68E, 2022-12-15: surface 28.11 degC vs SST 28.03 degC; cools to 11.84 degC at
500 m; sigma 0.14 degC at surface, peaking 0.33 degC at 75 m.

### Also fixed
- `load_mlp()` was called with no argument in `predict.py` (mine) and `compare_models.py` (Unit A's) —
  the signature requires `path`. compare_models could not evaluate the MLP at all.
- `_data.py::artifact_provenance()` now READS `artifacts/provenance.json` (its own docstring asked for
  exactly this once Unit B shipped the stamp). Before the fix it labelled a REAL run
  "SYNTHETIC-derived" because a stale `synthetic_glorys.nc` was still sitting in `data/raw/`.
  That stale file is deleted. D-018 is now closed end-to-end.
- `tests/test_uncertainty.py` model fixture now sets its own norm buffers. The old test passed only
  because the function read stats off disk — it was asserting against global state, not the model.

### ➡️ UNIT A (Arjhun) — please review, these are your files
I edited `inference/uncertainty.py`, `train/compare_models.py`, `train/_data.py` and
`tests/test_uncertainty.py`. Normally yours, but the first was breaking every reconstruction and the
rest blocked the real evaluation, so I fixed forward rather than leaving the demo path dead. All four
changes are described above — revert or rework any you disagree with.
**Your D-016 calibration numbers should be RE-MEASURED**: they were taken on fixtures through the old
(mis-normalized) MC-dropout path, so the ratios do not describe the current code on real data.

### ➡️ UNIT C — Argo validation is now UNBLOCKED
The checkpoint is trained on real GLORYS (`trained_on_fixtures=0`) and the 2022 test year exists.
`artifacts/argo_test.parquet` holds 24,328 real Argo measurements from ~2,453 profiles. L5 can run.
Note the 0 m level has only 32 Argo obs — validate at 10 m or state the assumption; do not extrapolate.
Still outstanding from me: a climatology STD array for a real `standardized_anomaly` sigma. Next up.

## 2026-08-25 - Unit A + C (Arjhun) - status after your merges; 1 commit still outstanding

Thanks for merging both branches and for closing D-009 and D-018 properly. **`pytest tests/ -q` on
`main` -> 130 passed, 1 skipped** [VERIFIED]. Confirmed your fixes landed: `predict.py` now has
ZERO `_normalize()` calls (raw-in adopted), and `provenance.json` writes `{source, built, x_units}`
into the artifacts - the real fix, better than the inferred workaround I had put in `_data.py`.

### 1 commit still to merge
`feat/unit-c-coverage` @ **31b7d6d** - literature + novelty matrices. Already rebased onto your
current `main`, **0 conflicts**, 130 tests pass on it. Everything else of mine is already in `main`.

### ⚠ Read NOVELTY_MATRIX.md before the pitch - our strongest claim does NOT survive
The seeded matrix had observation-priority as "UNDEREXPLORED / POTENTIALLY NOVEL". I went looking
specifically to break that, and it breaks:
- **Optimizing the Biogeochemical Argo Float Distribution** (J. Atmos. Ocean. Tech. 40(11), 2023) -
  sequentially picks Argo **deployment locations** to minimise objective mapping uncertainty. That
  is our idea, done rigorously, for Argo specifically.
- Optimal sensor placement via differentiable Gumbel-Softmax, under explicit sensor budgets.
- Adaptive float sampling / FloatCast (2026).

So `anomaly x uncertainty x sparsity` is a **simple heuristic version of a solved problem**, not an
invention. **INCOIS is the sponsor - they will know this literature.** Claiming novelty there costs
us the room. Honest reframing that still lands: *"a lightweight, interpretable heuristic that
surfaces candidate regions, complementary to formal observing-system design."*

Also softened the NIO claim: no NIO-specific paper surfaced, BUT DORS 2022 is global and therefore
already covers the NIO, and Indian regional literature (INCOIS / NIO Goa / IITM) is unsearched.
"First in the NIO" is not defensible. "NIO-focused, independently validated, limitations stated" is.

Caveat on both matrices: every row is tagged **[ABSTRACT-ONLY]**. The PDFs in `all research papers/`
are not on my machine (searched D:, Downloads, Desktop, Documents - absent), so no methods section
has been read by anyone. Fine for positioning; NOT enough to quote a method or to assert what a
paper did not do. Whoever has the PDFs can upgrade rows to [VERIFIED].

### Still open, in priority order
1. **D-008 - the only one that gets MORE expensive with time.** `config.DEPTHS` is 11 levels to
   500 m; SIH26066 names 15 to 1000 m (`0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000`) -
   verified at https://sih2026.vuce.in/en -> SIH26066. It sets every array width across all three
   units. Cheap now, a full retrain later. **Needs your ruling.**
2. `validation_panel` has no hook in the shell - it calls profile/map/priority only. Two lines:
   `fn = _panel("validation")` / `if fn: fn()`.
3. `use_container_width` is deprecated (removal was slated 2025-12-31, already past) and
   `app/streamlit_app.py` still uses it. My panels moved to `width='stretch'`.
4. `lgbm_quantiles.pkl` -> `DATA_CONTRACT.md`: `{"q10": [...11], "q90": [...11]}`.
   `lgbm_model.pkl` is unchanged, still exactly the contracted list of 11 boosters.

### Ready the moment real GLORYS lands (~30 min of my time, nothing blocking me)
`prepare_dataset.py --real` -> retrain both -> `python -m oceanembed.train.compare_models` gives the
first REAL MLP-vs-LightGBM verdict (D-013), and `python -m oceanembed.validation.validate_argo`
opens its own gate automatically once provenance reads `real`. Then freeze weights + cache the demo
tensors. Everything is built and tested against the seam; it just needs real numbers.

### Reminder on D-016 before any reliability claim
MC-dropout is overconfident at depth: sigma/RMSE 1.25 at 0 m -> 0.31 at 500 m, i.e. it understates
real error at 500 m by 3.2x, most confident where least trustworthy. LightGBM quantiles calibrate
much better (0.70 -> 0.92). Expect this to get WORSE on real GLORYS, not better, since deep error
grows while MC-dropout sigma keeps shrinking. Decide which uncertainty the demo ships.

## 2026-08-25 — Unit B — ALL THREE BRANCHES MERGED + two integration bugs fixed

### ✅ Merged to main: `feat/unit-a-priority`, `feat/unit-c-coverage`, `feat/unit-a-mlp`
`pytest` after the merge: **120 passed, 2 skipped** [VERIFIED]. Everyone pull.
Conflict resolution: `mlp_profile.py` / `train_mlp.py` / `tests/test_model.py` -> **Arjhun's
versions** (his files, and his implementation is better: normalization as registered buffers, so
checkpoints are self-describing and survive `torch.load(weights_only=True)`, plus D-010 fixture
stamping). The conflict existed because my Day-3 vertical slice wrote into Unit A's files — my
error; I should not have implemented them.

### 🔴 BUG FOUND AND FIXED — silent double-normalization
`build_samples` wrote **z-scored** X, and Arjhun's `train_mlp` z-scored it **again** via
`norm_stats.json`. MEASURED on the merged tree: X_train mean 0.000/std 1.000 -> after the second
z-score **mean -14.29 / std 29.95**. The model would train on doubly-scaled data and be served
single-scaled data at inference. Nothing errors; the temperatures are just wrong.
**FIX (my file):** `build_samples` now writes X in **RAW units**; the model owns the whole
transform, exactly as D-009 intended. [VERIFIED: X_train sst col = 28.35 degC, sss = 34.67 psu.]

### ✅ D-018 CLOSED — provenance no longer inferred
Arjhun is right that the banner could silently switch itself off. `preprocess` now records which
files it actually read, and `build_samples` stamps `artifacts/provenance.json`
`{source: "synthetic"|"real-glorys", built, x_units, n_train, n_test}`. The Streamlit banner reads
**that**, and shows a hard **UNKNOWN PROVENANCE** error if the file is missing — so a portable
`artifacts/` folder can no longer masquerade as real data. [VERIFIED: reads `real-glorys` today.]

### 📥 Real GLORYS is downloading (6/48 files, 350 MB so far)
MEASURED 54.3 MB / ~127 s per date, so full daily 2019-2022 (~79 GB / ~51 h) is infeasible; we take
**one date per month x 4 years = 48 timesteps** (~2.6 GB), still ~1.15M training rows. Resumable.
**Artifacts are currently PARTIAL: `n_test = 0`** because only 2019 dates have arrived; the 2022
test year is still downloading. Do not run comparisons or `run_slice` until it finishes.

### ➡️ ASK FOR UNIT A (Arjhun) — one small follow-up
`train/_data.py::load_real()` still documents *"X_train/X_test are ALREADY z-scored"*, and
`load_fixtures()` z-scores fixtures to match. With the fix above the real path is now RAW, so both
should pass raw straight through (`sample_X.npy` already ships raw). Not a live bug — each path is
internally consistent and trees are scale-invariant — but the two paths now disagree on convention,
which is the D-014 trap. Your file, your call.

### ➡️ UNIT C — nothing blocking
Panels, `anomaly.py`, `validate_argo.py`, metrics + the pooled-R2 finding are all merged. Correct
call on holding Argo validation: the checkpoint is still fixture-stamped and the test year has not
downloaded. `standardized_anomaly` sigma request (a climatology STD array) is noted and is mine —
I will add it after the download completes.

### Corrections to my earlier notes
- My Day-3 claim that "uncertainty shrinking with depth is explained by natural variability" was
  incomplete. Arjhun's D-016 measured the calibration ratio: MC-dropout **under-states** real error
  at 500 m by 3.2x. It is overconfident exactly where the model is least trustworthy. Do not quote
  MC-dropout confidence at depth until re-measured on real data.
- My Day-3 "R2 = 0.999" was misleading. Unit C measured that climatology alone scores pooled
  R2 = +0.95, so pooled R2 sits on a very high floor. Quote `r2_by_depth` / `skill_vs_clim`.

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

### Addendum (same day) — responding to Unit B's three points
- **B1 "fixtures don't exist" — INCORRECT [VERIFIED]:** `artifacts/sample_X.npy (500,11)` and
  `sample_y.npy (500,11)` ARE committed, in B's own `f0d1175` and `8f9c538`, and B's own HANDOFF entry
  below documents shipping them. Unit A invented nothing — `train_mlp.py` loaded B's real files.
  Fixtures are NOT the critical path; GLORYS/Argo download still is.
- **B2 "noise trap" — right conclusion, wrong diagnosis [VERIFIED by measurement]:** the fixtures are
  NOT random. `make_fixtures.py` builds `y = (sst-6)*exp(-depth/250)+6+N(0,0.2)`. Measured:
  r(sst,T)=0.83-1.00 at all depths; linear fit scores +86.9% vs predict-the-mean. So "loss falls" and
  the anti-collapse check ARE meaningful and did pass — no afternoon would have been wasted.
  BUT B's fix is still needed for a different reason: r(ssh,T) = -0.002..+0.041 and
  r(sin_doy,sst) = -0.014, i.e. 10 of 11 features are decoys. Logged as **D-011**.
- **B3 normalization ambiguity — ACCEPTED, implemented B's preference:** `predict_mlp` now takes
  **RAW** X and normalizes internally (**D-009**). `reconstruct()` cannot get it wrong.
  Also implemented B's fixture-checkpoint warning as a code guard, not a doc line (**D-010**):
  `trained_on_fixtures` buffer, `load_mlp()` warns, `model.is_fixture_model` for a hard check.
- TESTS AFTER CHANGES: `pytest tests/ -q` -> **17 passed**. Raw-in end-to-end re-verified:
  raw `sample_X.npy` straight off disk, zero caller-side normalization -> (500,11) float32,
  8.42-30.82 degC, RMSE 0.214 degC vs predict-the-mean 1.503 degC.
- STILL NEEDS B: **D-011** (fixture physics: couple SSH->thermocline, add seasonality) and
  **D-008** (DEPTHS 11@500m vs the statement's 15@1000m).

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
