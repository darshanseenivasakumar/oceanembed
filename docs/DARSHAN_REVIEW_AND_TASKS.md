# DARSHAN — REVIEW & TASKS

Written by Arjhun's machine, 2026-09-01, from a **forensic audit of this disk only**. Nothing here
is carried from chat history. Read time ~5 minutes. Detail lives in `ARJHUN_EXECUTION_PLAN.md`.

---

## 0. UPDATE 2026-09-01 — THE OFFICIAL PS HAS NOW BEEN READ [VERIFIED]

The PDF has no text layer (outlined vector glyphs; every extractor returns 0 chars). Rendered it
with PyMuPDF at 170 dpi and read it. **It is 3 pages, not 12.**

**Your transcription in `V2_MASTER_PROMPT_ARJHUN.md:78-96` was faithful — all 17 rows confirmed.**
Three things it understated, and one that changes the build:

1. **"estimate the three-dimensional ocean temperature using ONLY surface satellite observations."**
   Stronger than we were treating it. GLORYS into the encoder is a direct compliance failure.
2. **GLORYS as the training TARGET is explicitly endorsed** by the PS. That question is closed —
   your §5C framing was right, and it is now on the record from the source.
3. **"Gridded ARGO - INCOIS Live Access Server (LAS)"** is named outright as the in-situ dataset.
   Your task D2 below is a genuine PS MUST, not a nice-to-have. Our argopy floats are a different
   product class: `argo_test.parquet` has 2,445 unique latitudes for 2,455 profiles - float
   positions, not a grid.
4. **Theme is Disaster Management** - worth knowing for how we frame the demo.

### THE CORRECTION - currents, and it lands on your question 2

The PS names its input products. Four of five match what we hold. Currents do not:

| PS names | we planned |
|---|---|
| **`OSCAR_L4_OC_FINAL_V2.0`** - a TOTAL surface current | DUACS `ugos/vgos` - **geostrophic only** |

**This answers the ugos-vs-uo question you and I were going to argue to a jury.** The PS wants the
total current, because that is the correct counterpart to GLORYS `uo/vo`. It was never a framing
problem; it was the wrong product.

OSCAR needs a NASA Earthdata login we do not have, so I probed CMEMS live and found a better route:

```
cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m   (MULTIOBS_GLO_PHY_MYNRT_015_003, COPERNICUS-GLOBCURRENT)
coverage : 2022-05-01 -> 2026-08-31    our window sits fully inside
grid     : NATIVE 0.25 deg             no regridding needed
vars     : uo, vo = "absolute surface geostrophic + depth Ekman velocity"
```

Same physical quantity, native resolution, variable names and semantics matching GLORYS, on
credentials that already work. The delayed-mode twin stops 2026-03-31 and cannot reach our window -
the same conclusion `8555a86` reached for SST/SSH. **I am treating this as a documented deviation
from the PS's named product, recorded in provenance and stated to the jury - not quietly swapped.
Your sign-off on that wording is task D5.**

### SCHEDULE - and one rule that outranks it

Target is **2026-09-10**. Arjhun's directive, binding on both machines:

> **These dates are planning targets, not scientific acceptance criteria. Never skip validation,
> tests, or independent verification to meet a date.**

If a phase cannot pass its acceptance test honestly, the date slips and the verification does not.
On Sep 10 we demo what is actually validated and say plainly what is not.

## 1. THE ONE THING THAT MATTERS

**Your leakage fix `a5cdd3a` is not on this machine, and it is not on origin.**

```
git cat-file -t a5cdd3a                            -> unknown revision
git branch -r --contains a5cdd3a                   -> not in any remote branch
git log --oneline HEAD..origin/phase2-tscast-nio   -> empty
```

Consequence: **every number on this machine was produced by the leaky sampler.** Nothing here is
quotable, including the 0.8611 my currents ablation reproduced today before I killed it.

I re-derived the leak independently rather than trusting the report: with `T_SEQ=11`, **5 of 304
train days** (2026-03-27…31) have input windows reaching into the test block = **1.64%**, against
your 996/60,000 = **1.66%**. We agree. The diagnosis is precise: the **split** is correctly asserted
(`dataset.py:229-241`), it is the **T_SEQ window** that crosses it — which is why every existing
test passes.

---

## 2. THREE CLAIMS IN YOUR BRIEF THIS DISK CONTRADICTS

Not disputing your machine — flagging that they did not transfer, so neither of us assumes they did.

| your brief says | this disk |
|---|---|
| "canonical Arabian Sea / Bay of Bengal masks", "basin × depth metrics" | **ABSENT.** No `basins.py`. `metrics.py::per_depth` has no basin dimension. No basin field in the output schema. |
| "currents-related infrastructure/ablation work" | The `--drop-channels` flag is mine from today. **No currents ablation result exists.** |
| Stage 2, density OFF, **0.8548** | **No stage-2 artifact of any kind exists here** — no checkpoint, no metrics. |
| corrected 0.8548 / 0.8682 / 0.8793 | **Not present.** Only greps that hit are coincidental bytes inside binary `lgbm_*.pkl` weights. |

Also: **"Bay of Bengal is harder than the Arabian Sea" is not a model result on this disk.** No
per-basin model error has ever been computed. What exists is a *depth* story (surface-hard /
deep-easy), correctly stated as mechanism, not causation.

---

## 3. TWO THINGS THAT ARE ACTIVELY MISLEADING RIGHT NOW

1. **`PHASE2_STATUS.md:23` marks v2 stage 1 `VALIDATED — RMSE 0.8612`** — the superseded leaky
   number. `EXPERIMENT_LOG.md:44` still shows "wind −0.0149 helps". Nothing anywhere says
   superseded (`grep -i "supersed\|invalid\|leak"` → empty).
2. **`accept.py` reports green while its most important UI check is skipped.** Training writes
   *tagged* files (`tscast_stage1_withUV_s42_metrics.json`); the dashboard, `output.py` and
   `check_v2_ui` all expect the *unsuffixed* `tscast_stage1_metrics.json`, which is quarantined in
   `_stale_pre401e67b/`. `accept.py:511-512` **returns `True` with a `[skip]`** when it is absent.
   So the "every number equals its artifact" guarantee is **dormant, not enforced**, and the
   dashboard renders only its error banner (verified live).

---

## 4. YOUR TASKS — in order, nothing else blocks like #1

1. **Send the leakage fix.** Patch, branch, or the file. Until it lands, no experiment I run is
   valid. *This is the only true blocker.*
2. **Decide the canonical artifact name** so the producer/consumer split above is resolved once —
   tagged or unsuffixed. Your call; it touches your dashboard.
3. **Run `scripts/phase2/fetch_argo_ts_daily_period.py`** (exists, never run). Without
   `argo_daily_period_ts.parquet`, stage-2 salinity and density are **not scored at all** — the
   code correctly refuses and reports nulls, so eq. 5 currently proves nothing.
4. **Basin masks**, if you want the basin×depth analysis — with the Persian Gulf and Gulf of
   Thailand excluded. Note `PHASE2_STATUS.md:63-67` already warns our two units got different
   physics numbers from *different box definitions*; a canonical mask fixes that too.
5. **The provenance/synthetic mismatch** (`X_train.npy`, `lgbm_*.pkl` synthetic while
   `provenance.json` says real). Flagged in your build plan, untouched here.
6. **PROBE INCOIS LAS FOR REAL** (`las.incois.gov.in`, OPeNDAP, `certifi` SSL). Now confirmed a PS
   MUST (§0.3), and no probe script, log or cached response exists anywhere on this disk. Deliver
   the dataset path / resolution / years, **or a documented negative** — either is a result. It is
   network-bound, not token-bound, so it is cheap on a Pro budget.
7. **Sign off the currents-substitution wording** (§0). One paragraph: why CMEMS GLOBCURRENT
   `uo/vo` stands in for the PS's PO.DAAC OSCAR, for the provenance record and the jury.

---

## 5. WHAT I AM DOING — do not duplicate

Satellite bundle build · anti-GLORYS guard test · satellite-only model · matched sat-vs-GLORYS
comparison · ablations (multi-seed) · uncertainty recalibration · operational loop.

I own the heavy compute. **Correction to the audit: this box DOES have a GPU** — an RTX 4050
(6.4 GB VRAM). It read as "no GPU" only because `torch+cpu` was installed. Now on
`torch 2.13.0+cu126` (exact version match, no downgrade); 442 tests pass after the swap.

**Measured, real model, T_SEQ=11:** CPU 11.58 min/epoch → **CUDA 2.65 min/epoch (4.4x)**. Phases
2–8 drop from ~6–8 h to **~2 h**. It is 4.4x rather than your ~9x because at 548k params our
bottleneck is now the CPU-side patch sampler, not the GPU.

---

## 6. DO NOT SPEND TOKENS ON

- Re-running anything I can run here (training, ablations, processing, bundle builds).
- Re-auditing the repo — this document and `ARJHUN_EXECUTION_PLAN.md` are that audit.
- Cyclone prediction, MHW forecasting, transformers, more EOS-loss engineering (measured no-gain
  6/6), dashboard polish before the science is valid.

---

## 7. WHAT I NEED YOUR SCIENTIFIC JUDGEMENT ON

1. **Is a satellite-input / GLORYS-target model the right framing?** I believe yes (§5C of your
   contract), but it is the central scientific decision and it should be yours, on the record.
2. ~~`ugos`/`vgos` vs `uo`/`vo` framing~~ — **ANSWERED BY THE PS, see §0.** It wanted a total
   current all along. Replaced by: **sign off the CMEMS GLOBCURRENT substitution wording** (task D5).
3. **Uncertainty is improved, not calibrated** (±1σ 0.608 → 0.720 vs 0.683 target; heavy-tailed
   residuals). Do we ship it labelled as a limitation, per your §11?

---

## 8. HONEST COMPLIANCE

**~55–60%.** 11 of 17 PS rows genuinely done. The gap is one specific thing — the input end of the
chain — plus the operational layer. It is a finish, not a rebuild. But the headline currently on
record is invalid, and that must be corrected before anything is shown.
