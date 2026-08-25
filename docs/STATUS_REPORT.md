# OceanEmbed — status report
**2026-08-25 · from Unit A+C (Arjhun) · against `main` @ `462a8fb`**
**`pytest tests/ -q` → 142 passed, 1 skipped** `[VERIFIED]`

---

## 1. The headline: we have real numbers

D-013 finally has an answer, on real GLORYS, on a temporal holdout.

```
dataset : real GLORYS artifacts (provenance.json, built 2026-08-25T16:04:47)
split   : train[2019,2020,2021]  test[2022]  — by TIME
n_test  : 112,836

  model          RMSE      MAE       R2    skill_vs_clim
  climatology  1.7617   1.3791   0.9281        --
  lightgbm     0.6561   0.4135   0.9900     +0.6275
  mlp          0.6563   0.4275   0.9900     +0.6275

VERDICT: LIGHTGBM (NOT conclusive) — TIE, 0.0% apart, inside the 2% noise margin
```

**Read this correctly.** `skill_vs_clim = +0.63` is the real headline: both models cut climatology's
error by ~63% on a year they never saw. `R² = 0.99` is **not** a headline — climatology alone scores
0.9281 on the same pooled metric, because pooled R² is dominated by the surface-to-deep gradient
(`VALIDATION_PROTOCOL.md`). Quote `skill_vs_clim`.

**And the tie is a result, not a shrug.** TEAM_PLAN said: *"if MLP can't beat LightGBM, say so and
we ship LightGBM."* On real data it can't — 0.0% apart. So we ship LightGBM: simpler, faster,
inspectable. That is an honest outcome arrived at by a command, not by whoever was talking.

**Independent sanity check already passed:** the rebuild gives 28.49 °C → 7.73 °C at 1000 m, and
real Argo independently says **7.98 °C** at 1000 m. Different data source, 0.25 °C apart.

---

## 2. Completion

| Area | State |
|---|---|
| **Unit A** — models, training, uncertainty, priority, comparison harness | **100%** |
| **Unit B** — scaffold, contracts, pipeline, downloaders, seam, app | **~98%** |
| **Unit C** — climatology, metrics, anomaly, Argo validation, 4 panels, docs | **100% code** |
| Stubs remaining, any unit | **zero** |
| Tests | **142 passed, 1 skipped** |
| Real GLORYS holdout result (L4) | **done** ✅ |
| Independent Argo validation (L5) | **not yet run** ⬜ |
| Demo / PPT for Aug 30 | **~10%** ⬜ |

**Engineering ≈ 98%. Whole project ≈ 75%.** The gap is L5 plus the pitch.

---

## 3. What still has to be done

### 3.1 Run independent Argo validation — L5, the strongest check we have  🔴
`validate_argo` has been gated shut this whole time because provenance read `synthetic`. It now
reads `real-glorys`, so **the gate opens on its own**:

```bash
python -m oceanembed.validation.validate_argo
```

Refuses if the model is not real-trained; reports **n per depth** because 0 m holds only ~32 Argo
observations against ~2,400 elsewhere, and an RMSE from 32 points beside one from 2,400 reads as
equally solid unless `n` is on the same row. Expect deep skill to be poor — say so plainly.

*(I cannot run this: my machine has no real artifacts, only the stale synthetic set.)*

### 3.2 Finish the SSH bias correction, fitted on TRAIN years only  🔴
Domain shift is measured and the SSH offset is `+0.417 m` with `corr 0.975` — near-perfect shape,
pure reference-surface offset (ADT vs zos). Correcting it is justified. **Fitting it on 2022 would
leak**, since 2022 is the test year. Train-year satellite dates are the right call.

### 3.3 Decide D-016: which uncertainty ships  🟠
On synthetic data MC-dropout was overconfident at depth — σ/RMSE **1.25 at 0 m → 0.31 at 500 m**,
understating real error 3.2×. LightGBM quantiles calibrated far better (0.70 → 0.92). **Re-measure
on real data now that it exists**, and expect it to be worse, not better: deep error grows while
MC-dropout σ keeps shrinking, and we now go to 1000 m rather than 500 m.

The demo currently shows MC-dropout as "reliability". If the drift persists, either ship quantiles
or state the limitation on the panel. `calibration_ratio()` in `inference/uncertainty.py` produces
the number.

### 3.4 Demo and pitch — the only thing nobody has started  🟠
Aug 30. Needs: run-through, PPT, and the honest framing already agreed —
- lead with `skill_vs_clim +0.63`, never pooled R²
- observation-priority is **"a lightweight interpretable heuristic complementary to formal
  observing-system design"**, never a novelty claim (JTECH 40(11) 2023 does it rigorously, and
  INCOIS will know that literature)
- NIO claim is *"focused and independently validated"*, never *"first"* — DORS 2022 is global and
  already covers the NIO
- show the deep-layer weakness rather than hiding it; TS-Cast stops at 700 dbar and states the same
  bound

### 3.5 Literature: upgrade rows from `[ABSTRACT-ONLY]`  🟡
`LITERATURE_MATRIX.md` and `NOVELTY_MATRIX.md` are built from published abstracts — the PDFs are on
Mitun's/Niru's machines, not the build machine. **No methods section has been read by anyone.**
Fine for positioning; not enough to quote a method or to assert what a paper did *not* do. Three
PDFs would close it: Meng 2021, TS-Cast 2026, FFPG-net 2025.

Also unresolved: **Wang 2021 and Chen 2022** from the TEAM_PLAN list could not be located — DOIs
needed from whoever named them.

---

## 4. The pattern worth carrying into the demo

Three bugs this week, all the same shape — **correct arrays, plausible values, wrong data**:

| bug | why nothing caught it |
|---|---|
| `.gitignore` excluding `src/oceanembed/data/` | worked on the author's machine, where the untracked file existed |
| 46 m of extrapolated "500 m" values | shapes were correct, so no assert fired |
| SSS stacked `(12,1,1,100,240)` | the physical bounds check inspects **values**, not shape |

Unit B's own phrasing on the third: *"plausible values are not proof of a correct array."* That is
the L1 rule now (`VALIDATION_PROTOCOL.md`). The question that catches all three is: **could this
array have been produced without real data behind it?**

Worth saying out loud in the pitch. Most demos claim their results; fewer arrive with their own
failure modes documented and fixed.

---

## 5. Immediate next actions

| # | Action | Owner | Blocking? |
|---|---|---|---|
| 1 | `python -m oceanembed.validation.validate_argo` | B (has the artifacts) | **yes — L5 is the credibility shot** |
| 2 | SSH bias correction on train-year dates | B | yes for satellite-mode results |
| 3 | Re-measure D-016 calibration on real data | A | no |
| 4 | Demo run-through + PPT | all | **yes — Aug 30** |
| 5 | Share 3 PDFs → upgrade matrices to `[VERIFIED]` | C | no |

Nothing is blocked on me. Send me the real artifacts (or the `validate_argo` output) and I will take
items 3 and the technical half of 4.
