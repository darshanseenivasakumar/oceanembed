# PHASE2_STATUS.md

Status vocabulary: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `TESTED` · `VALIDATED` · `DEMO READY`

> ## WHICH NUMBER IS THE HEADLINE — read before quoting any of the three
>
> As of 2026-09-02 there are three validated results, and **the most accurate one is NOT the
> deliverable.** The PS asks for temperature "using only surface satellite observations".
>
> | result | Argo RMSE | skill | INPUT SOURCE |
> |---|---|---|---|
> | **stage 1 satellite — SHIPPED** | **0.9063** | **+0.2379** (+0.1480 where the climatology is real) | **satellite** ✅ the PS deliverable — `seafloor_masked_v2`, n 12,727 |
> | stage 1 GLORYS — comparator | 0.8826 | +0.2578 | reanalysis ❌ — `seafloor_masked_v2`, seed 42 |
> | stage 2 GLORYS — best accuracy | 0.8548 | +0.3027 | reanalysis ❌ — `unmasked_v1`, n 12,829, NOT directly comparable |
>
> **Quoting 0.8548 as "our result" would present a reanalysis-fed model as satisfying a
> satellite-input requirement.** It is a legitimate number and a legitimate comparator; it is not
> the deliverable. Row 14's "CURRENT HEADLINE" label predates the satellite model and should be
> read as "best accuracy on the GLORYS-input path".
>
> The honest framing for a jury (re-measured 2026-09-07 under `seafloor_masked_v2`, 3 seeds each,
> identical points, rmse_climatology 1.1892 and n=12,727 in both legs): *satellite minus
> reanalysis-fed reads +0.0237 / +0.0231 / −0.0040 °C — mean +0.0143 — and the sign does NOT hold,
> so by our own three-seed rule the cost is not an established effect; the satellite model retains
> ~95% of the comparator's skill (three-seed mean).* Under `seafloor_masked_v1` the same three
> seeds read +0.0263 / +0.0267 / −0.0028; the earlier "+0.0289, retains 92%" was one seed under
> `unmasked_v1`.
>
> **SCORING PROTOCOL CHANGE 2026-09-07 — `seafloor_masked_v1`.** Every number in this file dated
> before 2026-09-07 was scored under `unmasked_v1`: the model's raw output compared against Argo at
> every depth the float sampled, including the 93 of 12,829 comparisons below the training target's
> own seafloor, where `output.build_record` returns None. The scorer now declines those and counts
> them (`eval_argo.apply_seafloor_mask`). On the deliverable: RMSE 0.9078 → **0.9006**, skill
> +0.2595 → **+0.2400**, n 12,829 → 12,736. Separately, `metrics.per_depth(baseline_ok=...)` now
> reports skill on the 895 profiles whose cell has a REAL climatology: **+0.1494**. The other 67 sit
> on a basin-mean fill (`build_samples` drops any-NaN columns, so shelf cells contribute no rows and
> `climatology.build_climatology` fills them), where "skill" read +0.55 against a baseline that does
> not exist. Historical rows below are left as written and are `unmasked_v1`.
>
> **TRUTH-TABLE CHANGE 2026-09-07 — `seafloor_masked_v2` (audit #8).** Argo reports PRESSURE in
> decibars; `config.DEPTHS` is metres. `download_argo._profiles_to_rows` interpolated one onto the
> other directly, sampling every float ~1% too shallow — 0.6 m at 100 m, 8.2 m at 1000 m — which
> in a thermocline is a tenth of a degree charged to the model. The table was regenerated with the
> UNESCO 1983 conversion (`phase2.data.argo_depth`); the re-fetch itself changed nothing (surface
> levels agree to 0.005 °C on the 4,330 shared profiles), so the deltas are the axis alone: the
> truth moved **colder** by 0.05–0.06 °C at 100–150 m, and 89 comparisons at 1000 m existed only
> because a float reaching 1000 dbar had been read as reaching 1000 m. On the deliverable: RMSE
> 0.9006 → **0.9063**, bias +0.1066 → **+0.1400** (a third of the warm bias had been hidden),
> skill +0.2400 → **+0.2379**, n 12,736 → 12,727, 962 → 963 profiles. Every v1 record is kept
> on disk under its own name; the old table is `argo_daily_period_pres_as_depth_v1.parquet`.
>
> Stage 2 has not yet been run on satellite input. Until it is, there is no satellite T+S+density
> number and none may be implied.


> ## ⚠ SUPERSEDED RESULTS — read before quoting any number below
>
> **Every trained artifact produced before commit `1d3c135` (2026-09-02) came from a leaky
> sampler.** `dataset._window()` clamped the input window to the array ends instead of to the
> train/test split, so **5 of 304 train days (2026-03-27..31, 1.64%) read test-period surface
> fields.** The split assert was correct; the input window was not, which is why every test
> passed while it happened.
>
> Affected and **INVALID — do not quote**: `tscast_stage1_withUV_s42` (0.8612 / 0.8611),
> `tscast_stage1_noUV_s42` (0.9024), `tscast_stage1_metrics_tseq31` (0.9267), and the wind
> comparison derived from the first two.
>
> **The numbers are preserved verbatim as historical record and are not edited.** A matched
> re-run under the embargo is the replacement; until it lands, this project has no quotable
> headline.
>
> **UPDATE 2026-09-02, after merging `a5cdd3a`:** two embargo fixes were written independently.
> Darshan's DROPS the 5 boundary training targets; mine CLAMPED their input window. **His is the
> better protocol and is now canonical** -- clamping silently shortened the context for boundary
> samples while still counting them as full ones, and it embargoed the TEST side too, which models
> an operational setting nobody runs. **So `0.8645`, from my clamped re-run, is ALSO superseded:
> right conclusion, wrong protocol.** The numbers to quote are **stage 1 0.8793** and **stage 2
> 0.8548**, both measured under the canonical embargo.


**A feature is never marked VALIDATED because unit tests pass.** TESTED means the code does what the
code intends. VALIDATED means the *science* was checked against an independent source or a
documented physical expectation.

| # | Feature | Owner | Branch | Status | Backend | Frontend | Tests | Sci. validation | Known limitation |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Repository audit | Darshan | phase2 | **IMPLEMENTED** | n/a | n/a | n/a | n/a | — |
| 1 | Collocation engine | Darshan | phase2-collocation | **VALIDATED** | ☑ | ☑ | ☑ 29 | ☑ | satellite covers 24 of 48 dates; monthly grids force a 7-day median Argo offset |
| 2 | OceanCube 3-D | **Arjhun** (from Darshan) | `phase2-ocean-cube` | **TESTED** | ☑ | ☑ | ☑ 38 | ☑ | **F2a + F2b both built.** Sea floor is a REFUSAL not a NaN (Persian Gulf 26N 52.5E reads 30 m and raises at 1000 m). 3-D volume/isosurface on port 8504, depth emitted negative, degrades to a 2-D altair slice when plotly is absent — the volume layer imports no renderer at all |
| 3 | Spatial CNN | Arjhun | phase2/spatial-ai | NOT STARTED | ☐ | ☐ | ☐ | ☐ | only 48 timesteps to train on |
| 4 | Calibrated uncertainty + OOD | Arjhun | `phase2-reliability` | **TESTED** | ☑ | ☐ | ☑ 40 | ☐ | **NOT validated — needs real `X_train.npy`.** The OOD detector flags 99.18% of the real test set because the local X_train is the stale synthetic one (ssh mean 0.0017 vs 0.4421). The detector is CORRECT; the artifact is wrong. D-016 re-measured on real data: overconfident 1.6x-3.5x, worst in the mixed layer, not at depth |
| 5 | Physics (thermocline/MLD/OHC) | Arjhun | `phase2-physics` | **VALIDATED** | ☑ | ☐ | ☑ 31 | ☑ | **Re-run on the real bundle by BOTH units independently.** All four checks pass here: BoB salinity +4.78 psu with depth, thermocline below MLD in 87.8% of 526k cell-dates, barrier layer BoB 9.5 m vs Arabian 7.1 m (8/12 months), constant-density error max 0.293% (9× the synthetic 0.028%). Two numbers differ from Unit B's — see AGENT_SYNC, box definitions |
| 6 | Event detection | Arjhun | `phase2-events` | **TESTED** | ☑ | ☐ | ☑ 24 | ◐ | **Eddies + upwelling scientifically validated; FRONTS ARE NOT.** Great Whirl reproduced (85 km Jan → 243 km Aug at 7.5N 53E); Somali/Oman upwelling SW-monsoon dominated with a working BoB control. Fronts have no independent reference checked. Monthly → detection only, never tracking |
| 7 | Subsurface heatwave | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **monthly sampling -> persistence uncomputable** |
| 8 | Validation Lab | **Arjhun** (from Darshan) | `phase2-validation` | **TESTED** | ☑ | ☑ | ☑ 16 | ☑ | **Measured the reanalysis itself vs Argo — new, nothing had done it.** Thermocline error is LARGELY INHERITED (Phase-1: 100-150 m within 0.023 C of GLORYS' own error); mixed layer 20-50 m is genuinely ours (+0.31 to +0.38 C). **Both figures are PHASE-1 and must not be restated about the v2 deliverable** -- re-measured there (audit 2026-09-07) the thermocline gap is 0.178 C at 100 m and the mixed-layer gap +0.23 to +0.38 C. LightGBM baseline REFUSED because **no Argo score exists for it** — Unit B caught that my earlier row-count gate passed on his machine and rendered an empty 'shown' box |
| 9 | Ocean Sentinel | Arjhun | phase2/sentinel | NOT STARTED | ☐ | ☐ | ☐ | ☐ | thresholds must be configurable |
| 10 | Observation Priority v2 | Darshan | phase2/observation-priority | NOT STARTED | ☐ | ☐ | ☐ | ☐ | v1 heuristic already exists; not novel (JTECH 2023) |
| 11 | **Wind input (PS req 8)** | Darshan | `phase2-tscast-nio` | **VALIDATED** | ☑ | n/a | ☑ 22 | ☑ | **0% → done.** 388 daily-mean fields from the only gap-filled global L4 covering 2025-26 (hourly, averaged by us; no P1D/P1M variant exists). Grid is offset 0.0625 deg from ours so it is block-averaged BY COORDINATE, never by position. Validated against the Findlater Jet: JJA 9.57 vs DJF 5.60 m/s over the western Arabian Sea, measured across seasons |
| 12 | **TS-Cast-NIO v2 stage 1** | Darshan (from Arjhun) | `phase2-tscast-nio` | **VALIDATED** | ☑ | ☑ | ☑ 36 | ☑ | ⚠ **SUPERSEDED 2026-09-01 — see row 14 and `EXPERIMENT_LOG :: v2-embargoed`.** As measured pre-embargo: ~~RMSE 0.8612 °C / skill +0.2975, wind −0.0149 °C and −41% warm bias~~. Those numbers were correct for commit `6e6ba9a` and are kept as the historical record; the leakage embargo (`a5cdd3a`) changed them. Post-embargo the same matched pair reads **7ch 0.8793 vs 5ch 0.8682 — wind COSTS +0.0111 °C** while still removing 14.6% of the warm bias. Skill still positive at all 15 depths. Stage 1 only — salinity and the eq. 5 density loss are stage 2. Mixed layer (20–50 m) remains model-limited; thermocline error is LARGELY inherited from the reanalysis -- 0.178 C of the 100 m error is the model's own, measured on the shipped v2 run (audit 2026-09-07), not the 0.023 C Phase-1 figure |
| 13 | **v2 UI — explain every output** | Darshan | `phase2-tscast-nio` | **TESTED** | ☑ | ☑ | ☑ 15 | ◐ | Port 8504, four tabs, frozen demo untouched. Every rendered number is asserted equal to the metrics artifact to 4 dp by `accept.py check_v2_ui`. Marked TESTED not VALIDATED: it renders validated science correctly, which is not the same as validating anything itself |
| 14 | **Stage 2 — salinity + density (best accuracy; a GLORYS-fed COMPARATOR, not the deliverable — see row 16)** | Darshan | `phase2-tscast-nio` | **VALIDATED** | ☑ | ☑ | ☑ 26 | ☑ | **T RMSE 0.8548 °C / skill +0.3027 / bias +0.1055 on the same 962 independent Argo (n=12,829, `unmasked_v1` scoring)**, plus salinity 0.2450 psu and density 0.2841 kg m⁻³. Beats stage-1 7ch on every accuracy metric, so this is the shipped headline as of 2026-09-01. The paper's eq. 5 density loss is OFF: with it ON the same run reads 0.8593 / +0.2990 / bias +0.1598, i.e. it costs accuracy — reported as a negative result, not hidden. Byte identity in `artifacts/frozen_manifest.json` |
| 15 | **Phase 1 — provenance audit + freeze** | Darshan | `fix/provenance-audit` | **VALIDATED** | ☑ | n/a | ☑ 4 | ☑ | Three findings. (1) The Aug-26 synthetic-`X_train` alarm is STALE — verified four ways (row counts match provenance exactly; ssh mean 0.4463 not 0.0017; `norm_stats` derived from it; LightGBM ssh splits span 0.0–0.659). (2) The planned row-count gate was NOT built — it is the guard this repo already removed for cause (D-012). (3) **The wind result reverses post-embargo** and was independently re-scored from disk at a 0.00e+00 gap before being written down. `freeze_headline.py` proven to fail on a tampered file |
| 16 | **Stage 1 SATELLITE-INPUT (the PS deliverable)** | Arjhun | `phase2-tscast-nio` | **VALIDATED** | ☑ | ☑ | ☑ 44 | ☑ | **⚠ the epoch behind this number was chosen on the test period itself (`selection_protocol: test_period_v0`); a leak-free protocol costs +0.0725 °C over 3 seeds, sign holding 3/3 — see PROJECT_RECORD §16.6.** T RMSE 0.9063 °C / skill +0.2379 (+0.1480 on the 896 profiles with a real climatology) / bias +0.1400 on 963 independent Argo (n=12,727, `seafloor_masked_v2`; the same checkpoint read 0.9006 / +0.2400 / n=12,736 under `seafloor_masked_v1` — pressure read as depth — and 0.9078 / +0.2595 / n=12,829 under `unmasked_v1`)** — the first result whose INPUTS are satellite observations (OSTIA SST, DUACS altimetry, SMOS-blended SSS, GLOBCURRENT total currents, observational wind). GLORYS remains the target, which the PS names. Bundle `daily_sat/v001`, 388 days, 0 dropped, passed 44 provenance + data-lineage checks and a negative test that caught GLORYS injected into all five satellite channels. Config identical to the GLORYS-input leg; only the input source differs. **n=1 — multi-seed is A10.**


## F5 — detail (Arjhun, `phase2-physics`)

Full write-up: `docs/phase2/f5-physics.md`.

**Unblocked by Unit B.** The audit called OHC blocked on missing subsurface salinity; he showed the
cause was wrong — GLORYS always carried `so` at 36 levels, Phase 1 just took index 0. So density is
real rho(S, theta) and the constant-density caveat is gone rather than documented.

**Built.** `src/phase2/physics/seawater.py` (one-atmosphere EOS-80), `layers.py` (MLD, ILD, barrier
layer, thermocline), `ohc.py`. 31 tests pass.

**EOS coefficients verified before building on them** — 15 hand-entered constants are how a
plausible-but-wrong number enters a pipeline. All four published UNESCO check values agree to
< 1e-3 kg/m3, including the classic rho(35, 25) = 1023.343.

**The scientific point, and it is the strongest thing in F5.** MLD uses the DENSITY criterion
(de Boyer Montegut et al. 2004, 0.03 kg/m3 from 10 m), not temperature. The two disagree wherever
salinity sets the stratification, and their difference IS the barrier layer. Unit B measured
minimum salinity **6.43 psu at 22.50N, 91.25E** (Meghna/Ganges). So a temperature-only MLD would be
systematically TOO DEEP in exactly the region our priority map ranks first (17.75-19.25N,
85.75-93.75E) and in exactly the process our impact story rests on — cyclone intensification, which
barrier layers are a recognised control on. A test measures that error at >= 50 m on a realistic
plume profile.

**NOW VALIDATED (2026-08-26).** Unit B's 133 MB bundle landed and all three verifier levels pass.
The four checks were run **twice, independently** — by Unit B on his machine and by me here — and
all four pass. `test_salinity_generally_increases_with_depth_in_the_bay_of_bengal`, which FAILED
against the synthetic stand-in, now PASSES. My numbers:

| check | synthetic | real (mine) | real (Unit B) |
|---|---|---|---|
| BoB salinity 0 → 500 m | +0.02 psu | **+4.78** | +2.80 |
| thermocline below MLD | 11.6% | **87.8%** of 526k cell-dates | 84.7% |
| barrier layer BoB vs Arabian | ~0 m | **9.5 vs 7.1 m, BoB thicker 8/12 months** | 8.3 vs 4.6 m, 10/12 |
| constant-density error (max) | 0.028% | **0.2931%** | 0.2542% |

The two units' numbers differ in the last two rows because we used **different box definitions**,
not because either run is wrong — the qualitative conclusion is identical and it is the conclusion
that is claimed. Unit B's seasonality warning is confirmed: BoB barrier layer peaks in March
(19.6 m) and through the monsoon, and the Arabian Sea wins in Dec/Jan/Feb/Apr. **A single-date
check inverts this signal.** Measure across months.

One grid-run number looked like a failure and was not — worth recording because the checking is the
point. "Thermocline below MLD in only 11.6% of cells" is a property of the SYNTHETIC data:
`make_synthetic_glorys.py` builds temperature as `exp(-z/250)` from the surface, so there is no
mixed layer and the steepest gradient sits at the top by construction. Verified by printing one
profile rather than assuming either way. Salinity spans 0.28 psu across the column, so no barrier
layer exists to find and the constant-density error is correspondingly tiny (0.028%). All three
should change qualitatively on real GLORYS — that is the validation.

**Unit B's sanity test caught the synthetic data, exactly as designed.** With my locally
regenerated `subsurface.npz` in place, `test_salinity_generally_increases_with_depth_in_the_bay_of_bengal` FAILS: 34.60 psu at the surface vs 34.58 at depth at 18N/88E — noise, where the
real Bay of Bengal has a fresh cap over saltier water. His test rejected data with the right
shape, dtype, units and plausible magnitudes but no ocean structure. That is the Phase-1
failure mode, caught by a scientific test rather than a shape test. It fails only locally
(the file is gitignored and his test skips when absent). **No code was changed in response —
adjusting a sanity test to accommodate synthetic data would be exactly backwards.**

### >>> ASK DARSHAN (3): ANSWERED by the data bundle, 2026-08-26.
Real `subsurface.npz` landed and verified. Ask (1) `argo_error_by_depth.json` also answered.
Ask (2) — per-profile residuals + sigma, for F4's *held-out* path — remains the only one open.

## F6 — detail (Arjhun, `phase2-events`)

Full write-up: `docs/phase2/f6-events.md`. Built entirely on the real bundle, so unlike F4 and F5
it never ran on a synthetic stand-in.

**Built.** `src/phase2/events/` — `_metric.py` (spherical derivatives), `eddy.py` (Okubo-Weiss),
`fronts.py` (SST gradient), `upwelling.py` (signature + Ekman pumping + wind loader),
`_realdata.py` (structural real-data gate). 24 tests; 64 in `tests/phase2/`; 206 repo-wide.

**The eddy detector reproduces the Great Whirl.** The largest anticyclone in 4-12N / 48-58E grows
from ~85 km in Jan-Feb to **243 km in August**, holds station at ~7.5N 53E, and collapses to 77 km
in December. Right season, right place, right scale. **[VERIFIED]** that the
feature is in the data; **[INFERRED]** that it is the Great Whirl — that rests on the standard
description, and no paper was re-read. Check a citation before it reaches a slide.

**Upwelling has the right seasonality AND a working control.** Somali 8.3x and Oman ∞ (SW monsoon
over NE), while the Bay of Bengal control goes the *other* way — which is what makes it a test
rather than a detector that fires wherever the ocean is cold.

**A finding against my own spec.** The spec's default "cold" reference — the zonal mean at that
latitude — is **backwards at Somali**: ratio 0.88x, because a coastal upwelling box is colder than
its latitude band all year, so the criterion is a geographic fact rather than an event. Against the
monthly climatology it reads 1.68x, the right direction. Added
`climatological_sst_reference(month)`; the default is kept (climatology is gitignored) but now
labels itself `FALLBACK` in the returned payload. `cold` is the weak term either way — the
seasonality is carried by `shoaled_thermocline` (0% for eight months, 15-25% Jun-Aug), and the
result says so via `limiting_term`.

**FRONTS ARE NOT VALIDATED.** The detector runs and the strongest July gradient (11.4 degC/100 km
at 11.4N 51.5E) sits in the Somali upwelling front region, which is encouraging and is not
evidence. No front climatology or published census was checked. Also: a percentile threshold
*always* returns the sharpest gradients present, so it can never report "no fronts" — `threshold`
and `mean_gradient` are returned so a flat field is visible as one.

### >>> ASK DARSHAN (5): the wind grid is offset +0.125 deg from `config.LAT`/`config.LON`
Cell centres vs cell edges. Identical `(100,240)` shape, identical spacing, plausible values, every
value ~14 km southwest of where a naive assignment puts it. Nothing but a coordinate comparison
catches it. F6 regrids on load and a test asserts both halves. Flagging because F10 priority or any
panel overlaying wind will hit the same thing, and it is invisible.

### >>> ASK DARSHAN (6): the bundle leaves synthetic artifacts beside real ones
`artifacts/provenance.json` reads `n_train = 323028`, but the local `X_train.npy` is the old
synthetic file with **143514** rows, and `lgbm_model.pkl` / `lgbm_quantiles.pkl` are still
synthetic-trained. Excluding them was deliberate and reasonable (they are regenerable) — but the
result is a directory where provenance describes data that is not all present. Anything loading
`X_train` or the LightGBM baseline gets synthetic input while provenance says `real-glorys`.
Suggest the verifier fail when a file's row count contradicts `provenance.json`.

### Scaffold bug reproduced independently
`tests/phase2/__init__.py` had to be deleted again on this branch — it came back with
`origin/phase2` and broke `phase2.physics` imports exactly as it broke `phase2.reliability`. That is
two independent reproductions. It will hit your next branch too.

## F1 validation evidence

Marked VALIDATED on 2026-08-26. What justifies it, so nobody has to take the tick on trust:

- **Physical expectations** checked by `python scripts/phase2/accept.py` on real data: an exact grid
  hit reports 0.00 km offset; the profile returns 15 levels and cools 27.5 -> 9.0 C with depth;
  inland 15N 75E is REJECTED and says why (`LAND_IN_GLORYS`).
- **Against an independent source**: the same collocation logic drove
  `scripts/phase2/glorys_vs_argo.py` across 2,455 real Argo profiles, reproducing the known
  physical structure of the basin (reanalysis error peaking at the thermocline, near-zero in the
  deep ocean) rather than noise. Argo is never used in training.
- **UI matches the engine** to four decimals (SST 27.4946/26.9589, SSS 36.8145/36.1656, Argo
  53 km / +5 d / 14 levels), so the page is not recomputing or reformatting anything.

Not claimed: F1 has not been validated for satellite-driven queries on the 24 dates lacking
satellite coverage, and the 7-day median Argo offset is a limit of monthly grids, not a bug.


## F4 — detail (Arjhun, `phase2-reliability`)

Full write-up: `docs/phase2/f4-reliability.md`.

**Built.** `src/phase2/reliability/calibration.py` (variance/std scaling, Levi et al. 2022; ENCE)
and `ood.py` (Mahalanobis, Lee et al. 2018). 40 tests pass; full suite **182 passed, 10 skipped**.
Baseline diff vs `origin/phase2` is **empty** — `src/oceanembed/`, `app/`, `scripts/`,
`pyproject.toml`, baseline `tests/test_*.py` all untouched. `main` never checked out.

**Scientifically tested** — not shape tests:
- recovers a known 4x overconfidence factor to within 10%
- resolves depth-VARYING miscalibration (a single global factor would over-correct the surface)
- **ENCE improves out of sample**, on rows the factors were not fitted on
- reproduces the D-016 thermocline case: sigma 0.30 -> corrected lands on the measured 1.22 degC
- leaves already-calibrated uncertainty alone (alpha ~ 1)
- OOD flags a state that is inside every marginal range but violates the SST/SSH correlation —
  the property a per-feature z-score cannot have, and the whole reason for Mahalanobis
- OOD false-positive rate matches the chosen percentile (~1% at p99, measured 0.93% on held-out)

**NOT VALIDATED, and why.** `artifacts/argo_error_by_depth.json` is gitignored and lives only on
the machine that ran the real Argo evaluation. Every number F4 can currently produce comes from
synthetic artifacts (`provenance.json -> "synthetic"`). The method is exercised; the science is not.

### Two asks for Unit B
1. **Whitelist the error file.** ~15 numbers, and it is a *result* rather than raw data — results
   are the evidence. One line: `!/artifacts/argo_error_by_depth.json`.
2. **Persist per-sample residuals**, to unlock the rigorous path. The JSON stores *aggregate*
   per-depth RMSE, which supports only moment-matching — and moment-matching **cannot be held
   out**, so its factors are fitted on exactly the numbers they would be scored against.
   `is_validated` returns False for that path by design. Adding
   `[lat, lon, date, depth_idx, residual, sigma]` per matched profile to
   `scripts/eval_satellite_vs_argo.py` would let F4 report a genuine out-of-sample ENCE.
   Unit-B script, so: requested, not changed.

### Two scaffold notes
- **`tests/phase2/__init__.py` deleted.** It made pytest import tests as `phase2.test_*`, shadowing
  `src/phase2` so that `phase2.reliability` was unimportable. Latent until now only because
  `test_subsurface.py` imports just `oceanembed` and skips. Baseline `tests/` has no `__init__.py`
  anywhere; `main` has no `tests/phase2` at all, so this cannot reach it.
- **Branch naming.** `git checkout -b phase2/reliability` is impossible: `phase2` already exists as
  a branch and a git ref cannot be both a branch and a directory. Using **`phase2-reliability`**.
  `phase2/collocation` will hit the same wall.

### Held per instruction
F5 OHC, F6 upwelling, F7 persistence not started — audit section 4 gaps (no subsurface salinity,
no wind, monthly sampling) are still open pending Unit B's decision.

## Baseline protection
`main` @ `v1.0-demo-aug30` is frozen. 142 tests pass. No Phase-2 change may touch it.

## Blockers
1. §4 of the audit — download subsurface salinity + wind (~3 h), or formally de-scope F5 OHC-density,
   F6 upwelling attribution and F7 persistence.
2. Confirm the two-agent ownership split.
