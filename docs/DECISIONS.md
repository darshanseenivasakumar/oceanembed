# DECISIONS.md — Architecture Decision Records  (Owner: Unit A — Arjhun; seeded by B)

> Format per decision: DECISION / DATE / REASON / ALTERNATIVES / WHY REJECTED / CONSEQUENCES.
> Prevents future sessions from re-litigating settled choices.

## D-001 — Training truth = GLORYS12; validation = independent Argo
DATE 2026-08-25. REASON: complete gridded surface+subsurface fields buildable in 5 days; Argo gives an honest,
independent check. ALTERNATIVES: train directly on Argo. REJECTED: Argo too sparse in NIO for a 0.25° gridded demo.
CONSEQUENCES: clean train/validation separation; must download both via copernicusmarine + argopy.

## D-002 — Lead model = per-column MLP; baselines = climatology + LightGBM
DATE 2026-08-25. REASON: CPU-friendly, robust, beginner-safe, fits 5 days; MC-dropout gives honest uncertainty.
ALTERNATIVES: CNN/ConvLSTM/U-Net/Transformer. REJECTED for MVP: GPU + time + debugging risk. CONSEQUENCES: CNN etc.
deferred to Phase 2; a later model ships only if it beats the previous on the 2022 holdout.

## D-003 — Uncertainty = MC-dropout (LightGBM quantiles as backup)
DATE 2026-08-25. REASON: simplest defensible method; no fabricated confidence. ALTERNATIVES: deep ensembles,
heteroscedastic. REJECTED for MVP: cost/complexity. CONSEQUENCES: report model-uncertainty vs data-limitation vs
validation-error separately.

## D-004 — Deadline treated as a 5-day critical path (Aug 25→30)
DATE 2026-08-25. REASON: real inter-college gate is Aug 30. CONSEQUENCES: optional products off the critical path.

## D-005 — Team = 3 units; Mitun+Niru share one account/branch; Darshan owns pipeline+integration
DATE 2026-08-25. REASON: only 3 Claude accounts; strict single-owner files prevent merge conflicts. CONSEQUENCES:
overrides the generic "Darshan=UI" split; Niru is red-teamer within Unit C.

## D-006 — Tables use parquet (pyarrow) with CSV fallback
DATE 2026-08-25. REASON: pyarrow not yet installed; scaffold must run today. CONSEQUENCES: `utils.io` auto-detects;
fixtures ship as CSV until `pip install -r requirements.txt`.

## D-012 — LightGBM baseline: one booster per depth, quantiles in a separate artifact
DATE 2026-08-25. OWNER Unit A. REASON: LightGBM is single-output and the depths have genuinely different error
scales (surface ~2 degC spread vs ~0.3 degC at 500 m), so per-depth boosters let each fit its own scale.
Trees are scale-invariant, so they train on X as supplied (z-scored or raw) and predict REAL degC directly — no
normalization round-trip and no dependency on norm_stats.json. ALTERNATIVE: one multi-output model — REJECTED,
LightGBM does not support it natively. ARTIFACTS: `lgbm_model.pkl` stays exactly what DATA_CONTRACT says, a list
of 11 boosters. The q10/q90 quantile boosters go in a SEPARATE `lgbm_quantiles.pkl` (`{"q10":[...11],
"q90":[...11]}`) rather than changing the shape of the contracted file. **Unit B: please add
`lgbm_quantiles.pkl` to DATA_CONTRACT.md — it is a new artifact and that file is yours.**
Quantile spread is converted to a sigma-equivalent by dividing by 2.5631 (= 2 x 1.2816, the Gaussian q90-q10
width) so it is directly comparable with the MC-dropout std from `inference/uncertainty.py`. Independently-fitted
quantiles can cross; that warns and clamps to zero spread rather than producing a negative standard deviation.
Hyperparameters are deliberately NOT tuned — tuning against synthetic data optimizes for the wrong target.

## D-013 — FINDING: on the current fixtures, MLP vs LightGBM is an UNINFORMATIVE comparison
DATE 2026-08-25. RAISED BY Unit A. MEASURED on a 100-row held-out slice of the fixtures:
climatology RMSE 1.466 | LightGBM 0.222 (skill +0.849) | MLP 0.221 (skill +0.849). The MLP "wins" by 0.2%,
which is noise. REASON — and this is the point: `make_fixtures.py` adds `N(0, 0.2)` to the target, so the
irreducible noise floor is 0.20 degC. Both models score ~0.22, i.e. **both have saturated the noise floor**, and
the comparison cannot discriminate between them BY CONSTRUCTION. CONSEQUENCE: do NOT conclude "the MLP has no
advantage over trees" or "ship either one" from this run. The model-selection decision (TEAM_PLAN Unit A Day 3:
"if MLP can't beat LightGBM, say so and we ship LightGBM") can only be made on REAL GLORYS data, where the signal
is not a 1-D exponential decay and there is genuine structure for a nonlinear model to exploit. Re-run the
comparison after `prepare_dataset.py --real` and record the result here.

## D-014 - Training and evaluation MUST share one data loader (`oceanembed.train._data`)
DATE 2026-08-25. OWNER Unit A. CAUSE: `train_lgbm` and `compare_models` each had their own fixture loader.
One z-scored X, the other did not. Nothing errored - the models just silently saw different scales:
- Round 1: MLP evaluated at **RMSE 36.20 degC** (trained z-scored, evaluated raw). Looked like a broken model.
- Round 2: LightGBM at **RMSE 2.51 degC, WORSE than climatology** (trained raw, evaluated z-scored).
Neither model was broken. The CALLER was, both times, in opposite directions.
LESSON: "trees are scale-invariant" means trees do not NEED scaling - NOT that you may change the scale between
fit and predict. A booster's split thresholds are learned in the units it was trained on.
DECISION: `oceanembed/train/_data.py` is the single source of truth. `load_real()` and `load_fixtures()` both
return the SAME convention as Unit B's `build_samples`: **X always z-scored, y always real degC.** Fixtures are
z-scored with TRAIN-SPLIT stats only. `train_lgbm` and `compare_models` both delegate to it, and
`tests/test_compare_models.py` asserts train and test share one scale.
CONSEQUENCES: a preparation bug is now identical everywhere, i.e. visible, instead of a silent 20x error in one
path. **This is a live instance of the D-009 ambiguity Darshan raised** - with the stats living outside the model,
"who normalizes?" is answered separately by every caller, and the failure is silent every time.

## D-015 - Verdict rule: a sub-2% RMSE gap is a TIE, and ties ship the simpler model
DATE 2026-08-25. OWNER Unit A. REASON: TEAM_PLAN Day 3 says to pick MLP or LightGBM on the evidence, but a raw
`argmin(rmse)` reads run-to-run noise as a win. `compare_models._verdict` declares a TIE when the relative RMSE
gap is under `TIE_MARGIN = 2%`, marks the result NOT conclusive, and defaults to LightGBM as the simpler, faster,
more inspectable model. CONSEQUENCE (measured on fixtures): MLP 0.2223 vs LightGBM 0.2225 - a 0.1% gap - is
correctly reported as a tie rather than an MLP win. Fixture runs are additionally never written to
EXPERIMENT_LOG.md, so a synthetic number cannot later be mistaken for a result.

## D-016 - FINDING: MC-dropout is OVERCONFIDENT. Do not ship a reliability claim on it yet
DATE 2026-08-25. RAISED BY Unit A. **RESOLVED 2026-08-26 on real data - see the UPDATE at the end
of this entry. The headline holds and is WORSE than estimated, but the DEPTH PATTERN INVERTED:
the original title said "at depth", and depth is where it is least bad. Read the update before
quoting any number from the fixture table below.** TEAM_PLAN Day 4 says "uncertainty should generally increase with depth. If it
doesn't, investigate - don't fake it." It does not increase. Investigated; the cause is mechanical, not physical.

MC-dropout perturbs a SHARED trunk (11 -> 128 -> 128) feeding all 11 depth outputs, so the raw spread is nearly
constant across depths in NORMALIZED space [VERIFIED: std/targ_std = 0.127 -> 0.162, spread 0.043]. Converting to
real degC multiplies by targ_std, which shrinks with depth - so real-units sigma shrinks purely as an artefact of
un-normalization. Darshan's Day-3 note that "deep water is naturally less variable" is correct, but it is the
CONSEQUENCE, not an independent confirmation: sigma_real = sigma_normalized x targ_std, and sigma_normalized is flat.

MEASURED CALIBRATION on fixtures (sigma / actual RMSE per depth; 1.0 == well calibrated, <1.0 == OVERCONFIDENT):

    depth      MC-dropout      quantile (LightGBM)
      0 m         1.25              0.70
    500 m         0.31              0.92
    drift         4.0x              1.8x

**MC-dropout UNDER-STATES the real error at 500 m by 3.2x** - it reports the most confidence exactly where the
model is least trustworthy. That is the worst possible failure mode for a tool pitched to INCOIS: a judge asking
"how confident are you at 500 m?" would get a confidently wrong answer.

LightGBM quantile uncertainty is better calibrated here (ratio 0.70 -> 0.92) because each depth has its OWN
booster and can express its own spread, rather than inheriting one shared trunk's noise.

EXPECT THIS TO GET WORSE ON REAL GLORYS, NOT BETTER: there, deep prediction is genuinely harder, so actual error
will GROW with depth while MC-dropout sigma keeps SHRINKING.

ACTIONS TAKEN: `calibration_ratio()` added as the honest per-depth diagnostic (use it instead of eyeballing
whether sigma rises with depth - a rising sigma can still be badly calibrated). `relative_uncertainty()` added so
the UI can show sigma as a fraction of each depth's natural variability, which IS comparable across depths.
DECISION REQUIRED: re-measure on real data; if the drift persists, either ship quantile uncertainty instead, or
state the limitation explicitly on the reliability panel. Do NOT quote MC-dropout confidence at depth until then.

### UPDATE 2026-08-26 - RE-MEASURED ON REAL DATA. Decision resolved; depth pattern inverted.
The "DECISION REQUIRED" above is now answered. Unit B's data bundle landed, so
`artifacts/argo_error_by_depth.json` (real per-depth error against 879 independent Argo profiles)
is present and the measurement could finally be made against something real instead of fixtures.

**Method.** `ratio = RMSE(prediction - argo) / RMS(MC-dropout sigma)`, aggregated per depth over
the 879 independent Argo profiles and THEN divided, with sigma evaluated at the Argo points
themselves. [VERIFIED, reproducible: `python scripts/phase2/measure_mc_calibration.py`, seeded,
writes `artifacts/mc_calibration.json`.] 0 m is not reported -- only 12 floats reach it.

    overconfidence factor = measured Argo RMSE / RMS(sigma)      (1.0 == calibrated)

      depth   factor            depth   factor            depth   factor
        5 m    1.81              75 m    2.81             500 m    1.73
       10 m    2.35             100 m    2.87             700 m    1.59
       20 m    3.54  <- WORST   125 m    2.85            1000 m    1.56   <- BEST calibrated
       30 m    3.25             150 m    2.54
       50 m    2.95             200 m    2.18
                                300 m    2.20

**CORRECTION 2026-08-26 (second pass).** An earlier version of this update quoted **1.8x-8.5x**,
worst 8.46x at 30 m. Those magnitudes were WRONG and are withdrawn. The direction and the
conclusion were right; the numbers were roughly 2x hot at the shallow end. Three compounding
causes, measured:

1. **sigma came from the wrong sample -- the dominant cause.** It was taken from
   `X_test.npy[:4000]` rather than from the Argo collocation points, so an Argo-derived RMSE was
   divided by an unrelated subset's sigma. That slice is not representative: mean `u` is -0.153
   against +0.031 for the full set, mean `sss` 34.18 against 34.68. At 20 m this alone moved sigma
   0.152 -> 0.306, a factor of 2.0.
2. **mean(sigma) instead of RMS(sigma).** Correct for a variance-scaling factor is
   `RMSE / RMS(sigma)`, since RMSE^2 = a^2 * mean(sigma^2). Worth ~10% at 20 m (3.93 -> 3.54).
3. **sigma was not masked to the depths Argo actually sampled.** Matters most at 1000 m, where
   only 536 of 879 profiles reach.

Unit B raised this and attributed it to averaging per-point ratios (`E[a/b] >> E[a]/E[b]`). That
mechanism is real and would inflate the shallow end similarly, but it is **not** what happened
here -- no per-point ratio was ever averaged. Recorded precisely because a future reader who fixes
only the mean-vs-RMS step would still be ~1.8x hot; the sampling is the part that matters.

Source makes almost no difference: satellite 3.54x at 20 m vs glorys 3.46x.

**1. The headline is CONFIRMED.** MC-dropout is overconfident at EVERY reportable depth, by
1.6x to 3.5x. The fixture estimate was a ~4x drift, so the real spread is of the same order but
the fixture table put it in the wrong place. Nothing here rehabilitates MC-dropout.

**2. The DEPTH PATTERN INVERTED, and this entry's original title was wrong.** The fixture table
said the failure was "at depth", worst at 500 m (0.31 ratio, 4.0x). On real data 500 m is 1.73x and
1000 m is 1.56x - the two BEST-calibrated depths in the column. **The worst is the MIXED LAYER at
20-50 m, averaging 3.25x.**

**3. The fixture-based prediction was falsified, and the reasoning behind it is worth keeping.**
This entry predicted: *"EXPECT THIS TO GET WORSE ON REAL GLORYS... actual error will GROW with depth
while MC-dropout sigma keeps SHRINKING."* Actual error does **not** grow with depth. It peaks at
50 m (1.365 degC) and falls to 0.220 degC at 1000 m - our best absolute RMSE anywhere in the column
(see F8, `docs/phase2/f8-validation.md`). The deep ocean is genuinely easy to predict, which the
fixtures could not show because they encoded only one signal. The MECHANISM described above -
a shared trunk giving flat sigma in normalized space, times a shrinking `targ_std` - is still
correct; what was wrong was assuming real error would move the opposite way.

**4. Independent corroboration, from a different method.** F8 compared our per-depth RMSE against
the GLORYS reanalysis' own error versus the same floats, and found 20-50 m is exactly where we are
**model-limited** rather than at the ceiling of our training truth (headroom +0.31 to +0.38 degC),
while 100-150 m is inherited error. Two unrelated routes - calibration and inherited-vs-earned -
land on the same band. The mixed layer is this model's real weakness.

**ACTION, superseding the one above.** The limitation on the reliability panel must name the
**mixed layer (20-50 m)**, not "at depth". A panel that warns about deep water and stays quiet
about 30 m would point a judge away from the actual problem. Still do not quote MC-dropout
confidence as a reliability claim anywhere.

**CAVEAT, and it matters.** The per-depth FACTORS above are a real diagnosis: both terms are
measured, and their ratio is meaningful. The CORRECTION derived from them is not validated -
`fit_from_summary` is fitted on the same aggregate it would be scored against, so its
`ratio_after` is 1.0 by construction and `is_validated` is hard-wired False. A genuine
out-of-sample ENCE still needs per-profile residuals + sigmas persisted, which is the standing
ask on `scripts/eval_satellite_vs_argo.py`.

**Reproduce:** `phase2.reliability.calibration.fit_from_summary(load_measured_error()["rmse"],
sigma_by_depth, n_obs_per_depth=...)` with `sigma_by_depth` from
`oceanembed.inference.uncertainty.mc_dropout_predict` on `artifacts/X_test.npy`.

## D-017 - BUG FIXED: mc_dropout_predict leaked train() mode to the caller
DATE 2026-08-25. OWNER Unit A. `mc_dropout_predict` called `model.train()` to enable dropout and never restored
the previous mode, so every later plain forward pass on that model object was silently stochastic. `predict_mlp`
happened to mask it by calling `.eval()` itself, so nothing failed visibly - the kind of bug that surfaces as
irreproducible numbers days later. Now saved and restored in a `finally` block, with two tests
(`test_restores_eval_mode`, `test_restores_train_mode_if_that_was_the_caller_state`).

## D-018 - RED-TEAM CRITICAL: the SYNTHETIC banner can silently switch itself off
DATE 2026-08-25. RAISED BY Unit A (Day-5 red team). `app/streamlit_app.py` decides whether to show the
"SYNTHETIC DATA MODE" warning with:

    synthetic = os.path.exists(os.path.join(config.DATA_RAW, "synthetic_glorys.nc"))

Provenance is INFERRED from a sibling file rather than recorded in the artifacts themselves, and that sibling
file is gitignored (`.gitignore:2:data/`). [VERIFIED: `git check-ignore` confirms; `build_samples.py` writes no
provenance flag of any kind.]

REACHABLE FAILURE, and it is the likely demo-day path: `artifacts/` is small and portable, `data/raw/` is large
and gitignored. Copy the artifacts to a demo laptop without `data/raw/`, and the warning SILENTLY DISAPPEARS
while the numbers stay synthetic. The app then presents simulated data as real ocean performance to judges.
This is precisely the fabrication failure the real-data-only rule exists to prevent, arriving through a side door.

FIX (Unit B owns both files): have `build_samples` write the provenance INTO the artifacts - e.g.
`{"source": "synthetic"|"real-glorys", "built": "<iso date>"}` in `norm_stats.json` or a `provenance.json` - and
have the app read THAT. Provenance must travel with the data, not be guessed from what happens to be on disk.
Same principle as D-010, where Unit A stamped `trained_on_fixtures` into the checkpoint itself: the artifact
carries its own truth, so it cannot be laundered by moving files around.
UNTIL FIXED: never demo from a machine that does not also have `data/raw/`.

## D-019 - RED-TEAM: fresh-clone verification must be part of Definition of Done
DATE 2026-08-25. RAISED BY Unit A. A genuine `git clone` of `main` was run and stepped through as a teammate
would [VERIFIED]:
  1. `import oceanembed` -> OK
  2. `python scripts/prepare_dataset.py` -> **ModuleNotFoundError: No module named 'oceanembed.data'**
  3. `python scripts/run_slice.py` -> "Run prepare_dataset.py first to build artifacts."
  4. `reconstruct()` -> FileNotFoundError
  5. `streamlit run app/streamlit_app.py` -> serves HTTP 200 and shows a clean `st.error` (no stack trace)
So the entire pipeline is dead for everyone except Darshan, whose untracked local copy of `src/oceanembed/data/`
makes it work only on his machine. This is a whole-team blocker that has been open for a day of a five-day sprint
and CANNOT be seen from the machine that created it.
DECISION: "works on my machine" is not DONE. Before declaring a pipeline stage complete, clone to a scratch
directory and run it there. It takes two minutes and is the only way to catch this class of bug.
CLEAN RESULTS from the same sweep, worth recording: no hardcoded or fabricated metrics anywhere in code or docs
[VERIFIED by grep across *.py and *.md]; the app degrades gracefully on missing artifacts (`st.error` + `st.stop`,
never a traceback); land / no-data points are rejected with a clear message.
## D-007 — Normalization stats live INSIDE the model checkpoint
DATE 2026-08-25. OWNER Unit A. REASON: `predict_mlp` must return real °C, so it needs target mean/std — but
`artifacts/norm_stats.json` is Unit B's file and does not exist yet, and Unit A must not create it. Registering
`feat_mean/feat_std/targ_mean/targ_std` as buffers on `MLPProfile` puts them in `state_dict()`, so `mlp_model.pt`
is self-describing and needs no companion file. ALTERNATIVES: (a) have A write `norm_stats.json` — REJECTED,
violates file ownership; (b) require callers to pass stats into `predict_mlp` — REJECTED, changes a frozen
signature that B and C already code against; (c) save a dict of numpy arrays next to the state_dict — REJECTED,
`torch.load` defaults to `weights_only=True` since PyTorch 2.6 and numpy arrays are not allowed under it, so it
would force the unsafe `weights_only=False`. CONSEQUENCES: `train_mlp.py` prefers B's `norm_stats.json` when it
appears and falls back to train-split stats otherwise, logging which path it took; no signature changes for B/C.

## D-008 — OPEN QUESTION for Unit B: DEPTHS is 11 levels to 500 m; the problem statement names 15 to 1000 m
DATE 2026-08-25. RAISED BY Unit A. The SIH26066 statement lists standard depths
`0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000` (15 levels). `config.DEPTHS` currently has 11, stopping at
500 m — missing 5, 125, 700 and 1000 m. This sets the MLP output width, so changing it later means a retrain and a
contract change for every unit. Cost to change now is ~zero (four more depth levels from the same GLORYS download;
output layer 11→15). NOT ACTIONED — `config.py` is Unit B's file and the constants are frozen by group decision.
DECISION REQUIRED FROM: Darshan + team. CONSEQUENCES IF DEFERRED: either a retrain later, or we ship a demo that
visibly does not match the depth list judges are scoring against.

## D-009 — `predict_mlp` takes RAW features; the model normalizes internally
DATE 2026-08-25. RAISED BY Unit B, ACCEPTED by Unit A. REASON: once D-007 put the z-score stats inside the
checkpoint, "who normalizes?" became ambiguous, and BOTH wrong answers fail silently — double-normalizing or
skipping normalization produce plausible-but-wrong temperatures rather than an error. Making the model own the
whole transform removes the choice from the caller. ALTERNATIVES: (a) keep normalized-in and warn on raw-looking
input — REJECTED, a warning is not a guarantee and `reconstruct()` can still get it wrong; (b) pass stats into
predict_mlp — REJECTED, more caller state to get wrong. CONSEQUENCES: `inference/predict.py` and the panels pass
raw arrays straight through. `mc_dropout_predict` (Day 4) inherits the same convention. `predict_mlp` still warns
if input looks ALREADY z-scored, the one remaining misuse. VERIFIED: raw `sample_X.npy` off disk with zero
caller-side normalization -> (500,11) float32, 8.42-30.82 degC, RMSE 0.214 degC.

## D-010 — Fixture-trained checkpoints are stamped and refuse to pass silently
DATE 2026-08-25. RAISED BY Unit B, ACCEPTED by Unit A. REASON: a checkpoint trained on fixtures has FIXTURE
statistics baked into its normalization buffers; if it reached the demo it would produce confident nonsense.
IMPLEMENTATION: `MLPProfile` carries a `trained_on_fixtures` buffer (float, so it survives
`torch.load(weights_only=True)`); `train_mlp.py` stamps it from the `--fixtures/--real` flag; `load_mlp()` emits a
RuntimeWarning; `model.is_fixture_model` exposes it for a hard check in the demo path. CONSEQUENCES: enforced in
code rather than relying on a doc line. `artifacts/mlp_model.pt` is currently stamped 1 and MUST be retrained once
real GLORYS data lands.

## D-011 — OPEN, for Unit B: the fixtures encode only ONE signal (SST), not the SIH physics
DATE 2026-08-25. RAISED BY Unit A (measurement), CONVERGENT with Unit B's own "noise trap" concern.
`scripts/make_fixtures.py` builds the target as `y[:,d] = (sst - 6.0) * exp(-depth/250) + 6.0 + N(0, 0.2)`.
`ssh`, `sss`, `u`, `v`, lat/lon and day-of-year are generated but NEVER used to build `y` — 10 of 11 features are
decoys. MEASURED on `sample_X/y`: r(sst, T) = 0.83-1.00 across all depths; r(ssh, T) = -0.002 to +0.041 at every
depth; r(sin_doy, sst) = -0.014. A linear fit scores +86.9% skill vs predict-the-mean, so the fixtures are
STRUCTURED, not noise — Unit A's "loss falls" and anti-collapse checks are therefore meaningful and did pass.
BUT the model is only ever exercised on a 1-D exponential decay, so nothing tests the multi-feature problem, and
Unit C's anomaly/priority panels will render an ocean where SSH does nothing. FIX (Unit B owns the file): couple
SSH to thermocline depth and add a day-of-year cycle, per Unit B's own proposal. NOT ACTIONED by Unit A —
`scripts/make_fixtures.py` is Unit B's file.

## D-012 — Static stability is enforced by PROJECTION, not by a loss term, and only where density exists
DATE 2026-09-06. RAISED BY Unit A. REASON: `stability_penalty` (TS-Cast eq. 5) is a soft constraint —
it makes violations rare and cannot make them absent, which is why no paper in this specialisation
reports a violation count. IMPLEMENTATION: `phase2.physics.stability` projects each predicted
profile onto the nearest statically stable one — isotonic regression (PAVA) on EOS-80 density,
inverted back to temperature at FIXED salinity by bisection, then RE-VERIFIED by recomputing density
from the projected temperature and counting again. Isotonic and not a sort (which permutes levels)
or a running maximum (which only pushes values up); PAVA is the unique nearest non-decreasing
sequence and is exactly the identity on an already-stable column, which is what makes it safe to
apply unconditionally. CONSEQUENCES: the guarantee is arithmetic, not a hope. MEASURED on stage-2
satellite: 805 of 13,468 adjacent pairs (5.98%) unstable in 597 of 962 Argo columns, and 12,153 of
165,648 (7.34%) in 8,298 of 11,832 basin cells -> 0 after, for +0.0002 degC of RMSE at 2.2 ms per
profile. MEASURED against a soft-penalty model trained for this comparison
(`--w-stab 1000.0`, seed 42, otherwise identical): the soft term cuts violations ~400-fold, 805 ->
2, and STILL DOES NOT REACH ZERO — which is exactly what a soft constraint cannot promise — at a
cost of +0.0220 degC RMSE and a doubled warm bias (+0.0831 -> +0.1782). The projection reaches zero
for +0.0002 degC, roughly 100x cheaper in accuracy, on a model never trained for it. They are not
alternatives: the penalty moves weights, the projection is post-hoc, and the soft-trained model
still emits 2 violations that the projection then removes. **STAGE 2 ONLY**: density needs salinity at depth, so `project_profile` RAISES on a None
salinity rather than substituting. The tempting alternative — enforce dT/dz <= 0 — would be wrong in
THIS basin, because Bay of Bengal barrier-layer temperature inversions are real and
`physics/layers.py` already measures them; a guarantee bought by deleting a physical signal is worse
than none. Two bugs found by counting rather than reading: `T_TOL=1e-6` left 395 phantom violations
(PAVA pools to an exactly flat pair and a 1e-6 degC inversion error pushes half of them marginally
negative — now 1e-11), and a level whose inversion refused kept its original temperature, silently
restoring the original violation inside the function that promises none (refused levels are NaN with
a reason now).

## D-013 — The observability field is SENSITIVITY-DERIVED and is never called an information bound
DATE 2026-09-06. RAISED BY Unit A. REASON: every paper in this field reports where its model is
inaccurate, which conflates "the model is weak here" with "the surface carries no signal about this
depth" — the first is ours to fix, the second is a ceiling on the whole approach. IMPLEMENTATION:
`phase2.reliability.observability` differentiates the frozen model, reporting degC at each depth per
+1 s.d. coherent shift of each satellite channel — per 1 s.d. of ITSELF, because seven channels in
degC, psu, m and m/s cannot otherwise be compared. CONSEQUENCES: the analysis is clean only because
the shipped decoder is `simple` and mu depends on the latent alone ([VERIFIED] output is
bit-identical with climatology zeroed or randomised); under the paper's FiLM decoder a flat Jacobian
would have meant "fell back on the climatology" instead. MEASURED: the model reads SST for the mixed
layer and sea-surface height for the thermocline (48% of the response at 100-125 m) with nothing in
the loss telling it to. **The wording is a decision.** This is NOT an information-theoretic bound —
no noise model, no likelihood, no mutual information — and a test asserts the negation appears in
the returned definition string. The threshold tau is a stated parameter, not a hidden one, and the
full sweep ships in the artifact because the floor moves from 1000 m at tau=0.05 to 200 m at
tau=0.5. The hypothesis that our errors sit below the floor was **REFUTED** at every testable depth
(ratios 0.38 / 0.78 / 0.65 / 0.74) and is reported as refuted.

## D-014 — Every novelty experiment loads through ONE context, and refuses to write if its control disagrees
DATE 2026-09-06. RAISED BY Unit A. REASON: three experiments needed the same six things — bundle,
split with embargo, the checkpoint's own normalisation, the checkpoint, the independent-Argo
collocation, and a way to run the model at chosen cells. `rescore_checkpoint.py` already did all six
correctly; writing that sequence three more times is how this project produced an 8 degC dashboard
error and a warm-surface report that was a missing variable. IMPLEMENTATION:
`phase2.reliability.harness` holds it once, and `Context.control_rmse()` re-scores with nothing
applied and compares against the metrics file beside the checkpoint. Every script exits non-zero
rather than writing its artifact if the control does not agree to 1e-4. CONSEQUENCES: the control
caught a real bug on its first run. **`built_t_seq` is not `T_SEQ`**: the first is what CNN3D's
temporal pooling stride is built from (1 -> none, 11 -> [2,2,2]), the second is the input window,
and the shipped checkpoint is T_SEQ=11 with built_t_seq=1. Both constructions accept the same
state_dict without complaint because AdaptiveAvgPool3d equalises every parameter shape, so building
at t_seq=11 produced 0.9297 against a recorded 0.9078 with NO error raised anywhere. `harness.load`
now builds from `built_t_seq` and calls the repo's own `assert_architecture_matches`. A control that
only ever passes is not a control.

## D-020 — Temperature-inversion definition, and a held-out WINTER protocol that never touches training
DATE 2026-09-14. OWNER Unit B (Darshan), on `phase2-bob-inversion`; touches Unit A training files
(listed in the PR). REASON: the Bay of Bengal's winter inversion (cold fresh surface over warmer water
under the barrier layer) is the one profile shape a "warm surface ⇒ warm below" model gets backwards,
and the project has never measured whether ours does — nor could it: `dataset.DAILY_TEST` is
2026-04-01..2026-06-23 and the only winter in the daily bundle (Dec 2025–Feb 2026) sits inside
`DAILY_TRAIN`. Two definitions are fixed here so no later number can be tuned into existence.

**1. Inversion (temperature-only, per column).** Over the levels 0–150 m (`config.DEPTHS[:10]`):
    amp = max_z [ T(z) − min_{z' < z} T(z') ]
i.e. the largest warming with depth relative to any shallower level (a cumulative-minimum scan; NaN
levels skipped; works on any depth axis, so full-resolution Argo and the 15-level grid run the same
code). **Present iff amp ≥ 0.2 °C.** Also reported: depth of the warm maximum, depth of the shallower
minimum, their difference (thickness), and a `reason` string when unresolved. 0.2 °C is chosen to
equal the house isothermal-layer criterion (de Boyer Montégut 2004, ILD threshold) and to sit clear of
Argo/GLORYS noise; the threshold used by Thadathil et al. 2002/2016 is [UNKNOWN] to us (full texts not
read), so every result is ALSO reported at 0.1 and 0.5 °C. A result that holds at only one threshold is
not a result. Argo TEMP is in-situ, GLORYS `thetao` is potential; in the top 150 m they differ by
< 0.02 °C — stated, not corrected.

**2. ILD / MLD / BLT** are `physics/layers.py` unchanged (Unit A file, de Boyer Montégut 2004
criteria). Model-side BLT is REFUSED (needs salinity; stage 2 has never run on satellite input —
E-S2-SAT-03 standing recommendation). Truth-side BLT (GLORYS, Argo) is allowed and labelled as truth.

**3. Protocol `winter_holdout_v1`** (`tscast_nio/protocols.py`): test targets 2024-12-01..2025-02-28;
evaluation bundle spans 2024-11-20..2025-03-10 (≥ T_SEQ//2 + MAX_DAYS = 10 days of lead-in/out) and
lives in ITS OWN directory (`data/processed/daily_sat/v001_winter2425/`, provenance
`role: held-out evaluation only, never training`). Seafloor mask and depth-axis rules are those of
`seafloor_masked_v2`; truth table `artifacts/argo_winter2425.parquet` on metres. Numbers under this
name are never compared with `seafloor_masked_v2` headline numbers. ALTERNATIVES REJECTED: (a) carve
part of winter 2025–26 out of training — adjacent weeks are autocorrelated and inversions persist for
weeks, so a 5-day embargo would overstate skill, and training would lose most of its only winter;
(b) merge the winter into `v001` — `GriddedPatches._window` walks ARRAY indices and clamps at the
array ends, so a Mar→Jun date gap would be silently bridged inside an 11-day window.

**4. Decision rules are pre-registered in `EXPERIMENT_LOG.md` E-INV-00** (H1, H2, the ≥ 30-profile
rule, the frozen hyper-parameter procedure). A leg is adopted only on 3 seeds, only if the winter
inversion CSI improves on every seed by more than the control's seed sd, AND the headline 3-seed mean
RMSE worsens by ≤ 0.004 °C. Anything else is NOT A RESULT.

CONSEQUENCES: the shipped checkpoint, `DAILY_TRAIN/DAILY_TEST`, the sampler index and the 0.9063 °C
headline are byte-identical before and after this feature unless a leg passes rule 4 and is promoted
through `promote_run.py` with its own ADR. Every new training flag defaults off and refuses to run
without `--tag` (the A27 guard), so an experiment cannot overwrite the deliverable.
