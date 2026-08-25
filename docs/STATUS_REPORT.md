# OceanEmbed — status report
**2026-08-25 · Unit A+C (Arjhun) · against `main` @ `81cea51`**
**`pytest tests/ -q` → 142 passed, 1 skipped** `[VERIFIED]`

---

## 1. The problem statement's actual ask is now answered

SIH26066 asks for subsurface temperature **from surface satellite observations**, validated against
**independent ARGO**. Both halves now exist, on real data.

```
879 real Argo profiles · test year · an instrument never seen in training

  climatology                RMSE 1.5725      skill    --
  model on GLORYS surface    RMSE 0.9603      skill +0.389
  model on SATELLITE surface RMSE 0.9539      skill +0.393   <- the PS's actual ask
  domain-shift cost                          -0.0063 degC (-0.7%)
```

### The one number to quote: **+0.393**

There are two skill figures and they are **not interchangeable**:

| | number | what it means |
|---|---|---|
| GLORYS holdout | +0.626 | test data from the **same source as training** — the easier question |
| **Independent Argo** | **+0.393** | **a different instrument entirely** — the honest one |

A ~24-point gap between "held-out" and "genuinely independent" is normal and expected. Quoting
+0.626 to a judge invites the question *"held out from what?"*, and the honest answer makes the
number shrink live on stage. **Lead with +0.393 and the gap becomes evidence of rigour rather than
a hole.**

Two supporting facts worth having ready:

- **Satellite inference costs essentially nothing** (−0.7%) after bias correction — which is the
  whole premise of the PS.
- **The bias correction is legitimate, and provably so.** The SSH offset was fitted on **train
  dates only** (+0.4186 m) and independently matched the test-period offset (+0.4169 m) to
  **0.002 m**. That is a stable systematic offset between reference surfaces, not fitted noise, and
  it was measured without touching the test year. `u/v` were deliberately **not** corrected
  (corr 0.70; geostrophic-only is a different quantity, and shifting its mean would hide the
  mismatch rather than fix it).

---

## 2. Completion

| Area | State |
|---|---|
| Unit A — models, training, uncertainty, priority, comparison harness | **100%** |
| Unit B — scaffold, contracts, pipeline, downloaders, seam, app, demo scenes | **~99%** |
| Unit C — climatology, metrics, anomaly, Argo validation, 4 panels, docs | **100% code** |
| Stubs, any unit | **zero** |
| Tests | **142 passed, 1 skipped** |
| L4 real GLORYS holdout | **done** ✅ |
| **L5 independent Argo validation** | **done** ✅ |
| Demo scenes, DEMO_SPEC, UI source toggle | **done** ✅ |
| Final run-through + PPT | **in progress** ⬜ |

**Engineering ~99%. Whole project ~85%.**

---

## 3. D-016 is confirmed on real data — and it is the strongest thing in the pitch

Predicted from synthetic data: MC-dropout is overconfident at depth. **Confirmed against a real
float**, 38.6 km and 2 days away from the Bay of Bengal demo scene:

```
RMSE 0.894 degC over 14 levels
+0.01 degC at 1000 m          <- excellent
-2.0  degC at 150-200 m       <- while the model claims +/- 0.26
```

**The model is roughly 8x more wrong than it says it is, at the thermocline.** Not at the surface,
not at depth — precisely where the ocean is most structured and where a user would most want to
trust it.

Leading with that admission is the right call and is already in `DEMO_SPEC.md`. It converts the
project's biggest weakness into its most credible moment: most demos claim their results, very few
arrive having measured where their own confidence is wrong.

**Still to decide:** whether the demo's reliability display ships MC-dropout or LightGBM quantiles.
On synthetic data quantiles calibrated far better (0.70→0.92 vs 1.25→0.31). Run
`calibration_ratio()` from `inference/uncertainty.py` on the real Argo matches to settle it with a
number rather than a preference. Sigma peaking at 100 m (1.167 degC) at the same depth where skill
is worst is physically consistent and supports using it — but the peak being in the right *place*
does not mean the *magnitude* is calibrated.

---

## 4. What is left

| # | Item | Owner | Notes |
|---|---|---|---|
| 1 | **Final demo run-through + PPT** | all | The only substantial item. Aug 30. |
| 2 | Decide MC-dropout vs quantiles for the reliability panel | A | `calibration_ratio()` on the real Argo matches gives the number |
| 3 | Three PDFs → upgrade matrices off `[ABSTRACT-ONLY]` | C | Meng 2021, TS-Cast 2026, FFPG-net 2025 |
| 4 | DOIs for Wang 2021 / Chen 2022 | C | Could not be located; may be ambiguous citations |

### Known limits to state plainly, not hide
- **Climatology sigma is indicative, not rigorous** — n=3 per (month, cell). Say so wherever it appears.
- **Matrices are `[ABSTRACT-ONLY]`** — nobody has read a methods section. Fine for positioning;
  never quote a method or assert what a paper did *not* do.
- **Observation-priority is not novel.** JTECH 40(11) 2023 optimises Argo deployment to minimise
  objective mapping uncertainty. Frame ours as *"a lightweight interpretable heuristic
  complementary to formal observing-system design."* INCOIS will know that literature.
- **The NIO claim is "focused and independently validated", never "first"** — DORS 2022 is global
  and already covers the region.
- **Deep skill is weak, and 150–200 m is weaker than 1000 m.** Report per-depth, never a pooled
  RMSE. TS-Cast stops at 700 dbar and states the same bound.

---

## 5. The pattern behind every bug this week

Four now, all the same shape — **correct arrays, plausible values, wrong data**:

| bug | why nothing caught it |
|---|---|
| `.gitignore` excluding `src/oceanembed/data/` | worked on the author's machine, where the untracked file existed |
| 46 m of extrapolated "500 m" values | shapes were correct, so no assert fired |
| SSS stacked `(12,1,1,100,240)` | the bounds check inspects **values**, not shape |
| MC-dropout confidence at 150–200 m | σ was *shaped* plausibly; only a real float showed it was 8x too small |

Unit B's phrasing, now the L1 rule: **plausible values are not proof of a correct array.** The
question that catches all four: *could this have been produced without real data behind it?*

That belongs in the pitch verbatim. It is the difference between a demo that asserts and one that
has been tested against reality and reports where it failed.
