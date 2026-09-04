

## E-CAL-02  2026-09-02  — E-CAL-01 was measured through the wrong bundle; refitted

**Status: E-CAL-01 IS RETRACTED. The "4-5x too narrow thermocline" finding was an artifact.**

`calibrate_uncertainty.py:64` called `D.load_daily()` with no argument, defaulting to
`data/processed/daily` -- the GLORYS bundle -- while the shipped model trains on
`data/processed/daily_sat/v001`. The identical defect `inference.py` had. So every per-depth sigma
scale in E-CAL-01 was fitted on the errors a satellite-trained model makes when fed reanalysis,
which are not the errors it makes.

| | E-CAL-01 (GLORYS-fed, WRONG) | refitted (satellite-fed) |
|---|---|---|
| ±1σ coverage after | 0.6053 | **0.6387** (target 0.683) |
| ±2σ coverage after | 0.9650 | **0.9119** (target 0.954) |
| scale at 50 m | 3.24 | **1.19** |
| scale at 75 m | 5.13 | **1.28** |
| scale at 100 m | 5.41 | **1.46** |
| scale at 150 m | 4.78 | **1.15** |
| scale at 300 m | 4.13 | **1.01** |

**The uncertainty head was never 4-5x miscalibrated. The diagnostic was.** Real scales span
0.89-1.46. I reported that miscalibration as "a result about the model, not a
tuning detail" and it was neither -- it was a bug in the measuring instrument.

### What is true now

Both bands run SLIGHTLY NARROW, not wildly so: ±2σ covers 91.2% where a Gaussian of that width
gives 95.4%, and ±1σ covers 63.9% against 68.3%. So the model remains mildly overconfident and
the ±2σ band must NOT be labelled "95%" -- the nominal is not the measured figure.

Note the direction reversed as well: under the wrong bundle ±2σ OVER-covered (0.965 > 0.954); it
now UNDER-covers (0.912 < 0.954). Every conclusion drawn from E-CAL-01 pointed the wrong way.

### UI corrected in the same commit

`tscast_page.py` and `ui_tables.py` carried the retracted figures in a caption, a docstring, a
chart title, a tooltip and a column label -- "±2σ (95%)" and "5.4x at 100 m". All now read the
measured values. The band label is "±2σ", never "95%".

**Superseded artifact kept:** `uncertainty_calibration_INVALID_glorys_fed.json`.

## E-S2-SAT-01 — stage 2 (salinity + density) on satellite input, 2026-09-05

**Question.** Stage 2 had never been run on satellite input — the fourth open item carried into the
A16 freeze, and the reason `physics_page` refuses MLD, the barrier layer and real-density OHC on
the v2 source. Does the two-head model train on the satellite bundle, and can its salinity be
scored against something independent?

**Prerequisite that was missing.** `artifacts/argo_daily_period_ts.parquet` did not exist; the only
Argo table for the daily window is temperature-only. Without it `train_stage2.py` degrades loudly:
`metrics_salinity`, `calibration_salinity` and `density` all null — "nothing in it measures eq. 5,
which is the only reason stage 2 exists". So the fetch had to come first.

`scripts/phase2/fetch_argo_ts_daily_period.py` (written earlier, never run until now):
- **59,066 rows / ~4,334 profiles** in 2025-06-01..2026-06-23, **salinity present on 100.0%**
- `argo_test.parquet` and `argo_daily_period.parquet` **untouched**, as its guards require
- **temperature identical where the two tables overlap** — max |difference| **0.000000 °C** across
  59,039 of 59,040 distinct rows. This is the check that matters: stage-2 salinity sits on the same
  profiles as the stage-1 headline, so the two runs are comparable.

**Run.** `--daily-dir data/processed/daily_sat/v001 --t-seq 11 --epochs 25 --train-samples 60000
--test-samples 12000 --patience 5 --tag sat_s2`, seed 42, cnn3d, β-NLL 0.5, w_density 1.0,
protocol `embargoed_v2`. `--daily-dir` was passed EXPLICITLY: `load_daily(None)` defaults to the
GLORYS bundle, so omitting it would have trained stage 2 on reanalysis and called it satellite.

**Result** — scored on 962 independent Argo profiles, n = 12,829, the same population as stage 1:

| | value |
|---|---|
| temperature RMSE | **0.8854 °C** (skill +0.2777) |
| salinity RMSE | **0.2571 psu**, corr 0.945–0.978 by depth |
| density (eq. 5) RMSE | **0.2900 kg m⁻³**, bias −0.0353, predicted σ 0.2329, ratio 1.245 |
| stage-1 baseline it compared against | 0.9078, n 12,829, sha `53848bb5…` (the satellite deliverable) |

Salinity RMSE by depth falls monotonically with depth apart from the surface: 0.368 psu at 5 m to
0.054 psu at 1000 m — the fresh, variable surface layer is the hard part, which is the expected
shape for this basin.

**What this does NOT establish.** Stage-2 temperature is 0.0224 below stage 1's. That is the same
±0.02 scale at which the channel ablations required **3 seeds** before a sign was believed, and
this is **one seed**. It is NOT evidence that stage 2 improves temperature. Stage 2 is **not
promoted and not frozen**; stage 1 remains the deliverable.

The paper reports ~0.1 psu south / 0.2 psu north in ITS basin. Quoted for scale only — a different
ocean, never as a comparison.

**Defect found while verifying.** The stage-2 metrics artifact recorded `data: "daily"` — a
CADENCE, not a path — and carried neither `input_source` nor `daily_dir`, though the checkpoint
carried both. That is the exact ambiguity `bundle_for_checkpoint` blames for the 8 °C dashboard
error, and the metrics JSON is what `freeze.py`, `frozen_manifest.json` and every dashboard read.
Stage 1 has recorded both all along. `train_stage2.py` fixed; this run's artifact backfilled from
its own checkpoint and labelled `bundle_fields_backfilled` rather than presented as recorded at
training time.

## E-S2-SAT-02 — the 3-seed check, and the retraction of E-S2-SAT-01's temperature reading

**Question.** E-S2-SAT-01 measured stage-2 temperature at 0.8854 against stage 1's 0.9078 on the
same 962 profiles — 0.0224 better — and refused to call it an improvement on one seed. Does it hold?

**No. It does not.** Seeds 43 and 44 added, matched on every axis (`stage2_seed_check.py` asserts
input_source, daily_dir, T_SEQ, both periods, argo_profiles, argo_table, w_density, beta_nll, n and
the stage-1 baseline are identical across legs — all ok):

| seed | stage-2 T RMSE | vs stage-1 0.9078 |
|---|---|---|
| 42 | 0.8854 | **+0.0224** better |
| 43 | 0.9095 | −0.0018 worse |
| 44 | 0.9158 | −0.0080 worse |

mean **+0.0042**, spread **0.0304**, sd 0.0160. **The sign does not hold.** Seed 42 was the lucky
leg, and its 0.0224 sits well inside the seed spread. This is the third time this project has seen
an effect at ±0.02 °C fail to survive a reseed — wind's ablation flipped −0.0149 → +0.0111, the SSH
contrast was 1 of 3, and now this. The rule earns its keep again.

**RETRACTION.** E-S2-SAT-01 recorded "0.0224 below stage 1's" with the caveat that one seed was not
enough. The caveat was right and the number is now superseded: **stage 2 does not improve
temperature on satellite input.** The entry stands as written — historical, not edited — and this
is its correction.

**Salinity and density are new claims with no stage-1 counterpart, so the question is stability:**

| | s42 | s43 | s44 | mean | spread |
|---|---|---|---|---|---|
| salinity RMSE (psu) | 0.2571 | 0.2777 | 0.2737 | **0.2695** | 0.0207 |
| density RMSE (kg m⁻³) | 0.2900 | 0.3050 | 0.3166 | **0.3039** | 0.0266 |
| density calibration ratio | 1.245 | 1.281 | 1.491 | 1.339 | **0.246** |

Salinity is reasonably stable — 0.0207 psu spread on a 0.2695 mean, ~8%. Density RMSE likewise
(~9%). **The density calibration RATIO is not**: 0.246 spread on a 1.339 mean, ~18%, and that ratio
is the uncertainty-quality indicator. No stage-2 uncertainty claim should be quoted from one run.

**Consequence for `physics_page`.** Salinity being stable and independently validated is what MLD
by density and the barrier layer would need, and that part is now supported. But stage 2 is not
promoted, not frozen, and does not beat stage 1 on temperature — so wiring those panels to it would
put the page's headline barrier-layer claim behind an unpromoted model. That is a decision, not a
detail, and it is not taken here.

**Code change this required.** `train_stage2.py` hardcoded `base.SEED` in five places, so a seed
sweep was impossible without editing the file. It now takes `--seed` and threads one value through
sample draw, weight init and data order, exactly as `train_stage1.py` does — including stage 1's
"seed AFTER build: init consumes the RNG" ordering.
