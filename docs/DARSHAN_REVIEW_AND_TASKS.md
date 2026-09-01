# DARSHAN — REVIEW & TASKS

Written by Arjhun's machine, 2026-09-01, from a **forensic audit of this disk only**. Nothing here
is carried from chat history. Read time ~5 minutes. Detail lives in `ARJHUN_EXECUTION_PLAN.md`.

---

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

---

## 5. WHAT I AM DOING — do not duplicate

Satellite bundle build · anti-GLORYS guard test · satellite-only model · matched sat-vs-GLORYS
comparison · ablations (multi-seed) · uncertainty recalibration · operational loop.

I own the heavy compute. **Measured on this box:** 16 cores, 15.3 GB RAM, **no GPU**, 57 GB free.
`T_SEQ=11` costs 8.4 min/epoch @100k. Phases 2–8 ≈ **6–8 h CPU**. A GPU is not required at
`T_SEQ=11`.

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
2. **`ugos`/`vgos` are geostrophic currents**; GLORYS `uo`/`vo` include ageostrophic (Ekman) flow.
   That is a genuine difference in physical quantity, not a units problem. A satellite-driven score
   is *expected* to differ. How do we frame that to a jury — as a limitation, or as the measurement?
3. **Uncertainty is improved, not calibrated** (±1σ 0.608 → 0.720 vs 0.683 target; heavy-tailed
   residuals). Do we ship it labelled as a limitation, per your §11?

---

## 8. HONEST COMPLIANCE

**~55–60%.** 11 of 17 PS rows genuinely done. The gap is one specific thing — the input end of the
chain — plus the operational layer. It is a finish, not a rebuild. But the headline currently on
record is invalid, and that must be corrected before anything is shown.
