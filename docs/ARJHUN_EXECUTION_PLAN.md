# ARJHUN — EXECUTION PLAN (SIH26066)

Implementation source of truth for Arjhun's machine. Written 2026-09-01 after a forensic audit of
**this disk only**. Companion: `DARSHAN_REVIEW_AND_TASKS.md`.

**Status: MODE A complete. Awaiting `APPROVED — ENTER EXECUTION MODE`.**

---

## 1. PROBLEM UNDERSTANDING

SIH26066 asks for an **operational chain**, not a model:

```
satellite surface obs -> QC -> daily 0.25 deg harmonisation -> embedding
   -> DL reconstruction -> depth-wise subsurface T -> independent Argo validation
   -> basin x depth x uncertainty -> daily operational product -> dashboard
```

Domain 5-30 N, 45-105 E. Daily. 0.25 deg. 15 frozen depths
`[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]` (`config.DEPTHS`, do not change).

**Our error was optimising the middle and treating the ends as packaging.** The thing we call a
satellite embedding is embedding GLORYS reanalysis.

## 2. VERIFIED REPOSITORY STATE

Branch `phase2-tscast-nio` @ `6c83006`. `main` untouched @ `4995444`. 461 tests collected, 300
passing, 18 skipped.

| | verified |
|---|---|
| Daily bundle provenance | `GLORYS12V1 daily` — **5 of 7 channels are reanalysis**; only `wu,wv` are observations |
| `inference.py:220` | `"input_source": "glorys"` — a hardcoded literal |
| Raw satellite | **1,164/1,164 files complete** (sst/ssh/sss x 388 days, 1.1 GB) — **and nothing reads them except the downloader** |
| Raw wind | 388 days, complete, 3.4 GB |
| Argo | T: 4,331 profiles (962 in test window, median offset 0 d). **T+S table ABSENT** |
| Leakage fix `a5cdd3a` | **absent locally and on every remote** |
| Stage-2 artifacts | **none exist** |
| Valid stage-1 checkpoint | **none** — `tscast_stage1.pt` quarantined in `_stale_pre401e67b/` |

## 3. MISSING COMPONENTS

1. Satellite-input bundle (raw exists, no preprocessing)
2. Satellite-only model
3. Anti-GLORYS-fallback guard on the tscast path
4. Operational/NRT loop; `LAST_GLORYS` is a string literal ~10 weeks stale
5. Run-time degraded-mode surfacing (sampler NaN->0 mask never reaches the output)
6. Basin masks and basin x depth metrics — **entirely absent**
7. Anomaly RMSE; currents ablation; matched sat-vs-GLORYS comparison

## 4. DEPENDENCY GRAPH

```
P1 leakage-safe window  <-- blocks everything
    +-- P1b canonical artifact name (unblocks dashboard + check_v2_ui)
    +-- P1c mark leaky artifacts SUPERSEDED
    +-- P2 satellite bundle -> P3 validation -> P4 provenance + guard
            +-- P5 satellite-only baseline
                    +-- P6 Argo validation (S/rho need Darshan's T+S table)
                    +-- P7 matched sat-vs-GLORYS
                    +-- P8 ablations (multi-seed)
                    +-- P9 uncertainty  +-- P10 basin x depth
                            +-- P11 anomaly/OHC -> P12 operational -> P13 dashboard -> P14 freeze
```

## 5. PHASES, TESTS, ACCEPTANCE

### P1 — leakage-safe window **(FIRST)**
`_window()` clamps only to array ends. `GriddedPatches` must know its split and clamp within it.
- **Test:** zero train windows contain a test index. **Today this fails with exactly 5 crossings**
  (2026-03-27…31) — so the test is proven to catch the real bug before the fix lands.
- **Accept:** 0 crossings; one re-run leg moves the number off 0.8611.

### P1b — canonical artifact name
`accept.py:511-512` returns `True` with a `[skip]` when the unsuffixed metrics file is absent.
- **Accept:** `check_v2_ui` **enforces** rather than skips; dashboard renders.

### P1c — mark superseded
`PHASE2_STATUS.md:23`, `EXPERIMENT_LOG.md:44`, and the leaky artifacts.
- **Rule:** annotate, **never edit the numbers**.

### P2 — satellite bundle -> `data/processed/daily_sat/v001/`
Never overwrite `data/processed/daily/`. Per channel: Kelvin->degC (`analysed_sst`), regrid
0.05/0.125 -> 0.25 deg, **GLORYS land mask** (satellite SST contains inland water — a Tibetan lake
at 3.81 degC, 28.52 N 90.28 E, sits inside our box), documented missing-data policy, full provenance.
- **Test:** unit conversion; land mask excludes inland water; no silent imputation; per-channel
  provenance present.
- **Accept:** verifier passes on all 388 days; missing dates reported, not filled.

### P3 — bundle validation
Extend `verify_daily_bundle.py` to the processed npz and its provenance.
- **Accept:** ranges, dates, grid, coverage, provenance completeness all pass.

### P4 — provenance + anti-GLORYS guard
`input_source` read from the bundle, not a literal. Add `checkpoint_sha256` + `code_commit` to the
record (required by `tscast_output_schema.md:117-129`, currently absent).
- **Test (negative first):** inject GLORYS fields into a satellite bundle -> **guard must FAIL**;
  restore -> **guard must PASS**. Provenance-based, not filename-based.
- **Accept:** the negative test demonstrably catches the wrong source.

### P5 — satellite-only baseline
`T_SEQ=11` (won the ablation by 0.0567 degC), `cnn3d`, simple decoder, beta-NLL 0.5. GLORYS remains
the **target** (contract §5C), never the input.
- **Accept:** provenance says satellite end-to-end; Argo RMSE reported with n.

### P6 — independent Argo validation
RMSE/MAE/bias/correlation/skill, per depth, **with n**. S and rho only once Darshan's T+S table
lands — until then they stay null and labelled, which the code already does correctly.

### P7 — matched sat-vs-GLORYS
Identical split, target, depths, architecture, seed policy, evaluation population.
- **Accept:** `rmse_climatology` identical to 4 dp across legs — that is what proves same-points.

### P8 — ablations, multi-seed
SSS / currents / wind, on / off, matched. **3 seeds minimum**: wind's own effect flipped sign
(-0.0149 -> +0.0111) under a retrain, and everything here lives at +/-0.02 degC.
- **Accept:** sign holds across seeds, **or** is reported as not holding. A negative result is a
  result.

### P9 — uncertainty
Currently improved, not calibrated (+/-1 sigma 0.608 -> 0.720 vs 0.683; heavy-tailed residuals).
Recalibrate on the satellite model; label the limitation if it persists.

### P10 — basin x depth · P11 — anomaly/OHC on validated profiles · P12 — operational (measure
latency; "daily operational", never "real-time" without a number) · P13 — dashboard · P14 — freeze.

## 6. ARTIFACT + PROVENANCE CONTRACT

Every experiment: `config/ logs/ metrics/ plots/ predictions/ manifests/ checkpoint/ README.md`,
recording WHAT / WHY / DATA / MODEL / SPLIT / SEED / TRAINING / RESULT / LIMITATION / VALIDATION.
Statuses: `PLANNED RUNNING FAILED COMPLETE SUPERSEDED INVALID UNVERIFIED`. **Never overwrite a
prior record.**

## 7. RESOURCES (measured)

16 cores · 15.3 GB RAM · **no GPU** (`torch 2.13.0+cpu`) · **57 GB free (88% used)**.
Per-epoch @100k: `T_SEQ=1` 1.8 min · `T_SEQ=11` **8.4 min** · `T_SEQ=31` 24.9 min.
P2 ~30 min + 0.7 GB · P5 ~40 min · P7 ~40 min · P8 ~4 h. **Phases 2-8 ~6-8 h CPU.**
**Disk is the binding constraint** — `daily_sat/` must be derived-only; a second raw bundle will not fit.

## 8. ROLLBACK / SAFETY

Branch per phase; checkpoint commit at each boundary. Never `reset --hard`, `clean -fd`, force
push, or overwrite canonical data. Leaky artifacts are **marked**, not deleted.

## 9. INVALID ARTIFACTS (do not quote)

`tscast_stage1_withUV_s42.*` (0.8611) · `tscast_stage1_noUV_s42.*` (0.9024) ·
`tscast_stage1_metrics_tseq31.json` (0.9267) — all produced by the leaky sampler. The Phase-5 run
that wrote the first two was **killed mid-flight**; only seed 42 completed, and it is invalid.

## 10. COMPLETION GATE

A component is done only with: implementation + test + real-data check + scientific sanity check +
documentation + reproducible artifact. Not because a file exists or training finished.

## 11. KNOWN RISKS

R1 superseded headline presented as validated · R2 "wind helps" unretracted here · R3 n=1
everywhere · R4 the embedding is not satellite · R5 uncertainty uncalibrated · R6 fronts
unvalidated (honestly labelled) · U3 `accept.py` green while its UI check skips · U4 no operational
product consumes the v2 model (OHC/events run on raw GLORYS; anomaly on the Phase-1 MLP).

## 12. HANDOFF POINTS

After P1 (fix verified) · P4 (guard demonstrated) · P5 (first satellite number) · P7 (the
comparison) · P8 (ablations) · P14 (freeze). Each with evidence, not claims.
