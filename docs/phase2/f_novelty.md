# Three novelty features — hard guarantees, observability, latent assimilation

Owner: Unit A (Arjhun). Added 2026-09-06.

Three things this specialisation does not do, built on the **frozen** shipped checkpoint. None of
them retrains anything, and every one carries the control that decides whether its own headline is
real.

| # | feature | module | script | artifact | UI |
|---|---|---|---|---|---|
| 1 | Hard static-stability projection | `src/phase2/physics/stability.py` | `scripts/phase2/run_stability_projection.py` | `artifacts/stability_projection.json` | `app/ui/features/stability.py` |
| 2 | Observability field | `src/phase2/reliability/observability.py` | `scripts/phase2/run_observability.py` | `artifacts/observability.json` + `observability_field.npz` | `app/ui/features/observability.py` |
| 3 | Latent-space assimilation | `src/phase2/reliability/assimilation.py` | `scripts/phase2/run_latent_assimilation.py` | `artifacts/latent_assimilation.json` | `app/ui/features/assimilate.py` |

All three load through **one** shared context, `src/phase2/reliability/harness.py`, which is
factored from `rescore_checkpoint.py`'s proven path rather than rewritten three times.

Tests: `tests/phase2/test_stability.py` (18), `test_observability.py` (16),
`test_assimilation.py` (17), `test_novelty_harness.py` (8) — **59**, all offline.

---

## The control found a real bug before any experiment ran

`Context.control_rmse()` re-scores the loaded checkpoint with nothing applied and compares against
the metrics file beside it. The first run **disagreed**: `0.9297` against a recorded `0.9078`, on
exactly the right 962 profiles and 12,829 comparisons.

The cause: **the model's `t_seq` is not the data's `t_seq`.** `built_t_seq` is the value the
encoder was *constructed* with, and it sets the temporal pooling stride in `CNN3D` — `t_seq=1`
means no temporal pooling, `t_seq=11` means `[2,2,2]`. The shipped checkpoint records `T_SEQ=11`
(an eleven-day input window) and `built_t_seq=1`.

Both constructions accept the same `state_dict` without complaint, because `AdaptiveAvgPool3d`
makes every parameter shape identical either way. Building at `t_seq=11` produced a **plausible
wrong number with no error raised anywhere**. `harness.load` now builds from `built_t_seq` and
calls `assert_architecture_matches`, which the repo already had for exactly this.

**[VERIFIED]** after the fix: `0.9077608087441584` against `0.9077608087441584` recorded.

---

## 1 — Static stability as a guarantee, not a penalty

### The claim

Every profile the system emits is statically stable — density non-decreasing with depth — **by
construction**, and the zero is re-verified rather than asserted.

### Why it is not already done

`models/tscast.stability_penalty` is the standard move: `mean ReLU(-drho/dz)` added to the loss.
That is TS-Cast's eq. 5 and it is what the field does. A soft penalty makes violations *rare*; it
cannot make them *absent*, which is why **no paper in this specialisation reports a violation
count**. We report ours.

### How it works

```
rho    = EOS-80 density from predicted (S, T)
rho*   = the L2-nearest non-decreasing sequence      <- isotonic regression (PAVA)
T*     = the temperature with density rho* at UNCHANGED salinity   <- bisection
verify = recompute density from (S, T*) and count violations again
```

Isotonic regression, not a sort (which permutes levels — the 500 m value can land at 100 m) and
not a running maximum (which only pushes values up, dragging everything beneath). PAVA gives the
unique *nearest* non-decreasing sequence, moves values both ways, and **is exactly the identity on
an already-stable column** — which is what makes it safe to apply unconditionally.

### The measured result **[VERIFIED 2026-09-06]**

Stage-2 satellite checkpoint (`tscast_stage2_sat_s2.pt`), control reproduces `0.8854083481` exactly.

| | before | after | |
|---|---|---|---|
| unstable adjacent pairs, 962 Argo columns | **805** of 13,468 (**5.98 %**) | **0** | verified |
| columns containing a violation | **597** of 962 (62 %) | 0 | |
| worst gradient | −1.895e−02 kg m⁻³ m⁻¹ | 0.000 | |
| whole basin, 2026-06-22, 11,832 cells | **12,153** of 165,648 (**7.34 %**) in 8,298 cells | **0** | 32.7 s |
| RMSE vs independent Argo | 0.8854 | 0.8856 | **+0.0002 °C** |

Cost: **2.2 ms per profile**, closed form, no iteration count to tune.

### Soft penalty vs hard projection, measured on one test set **[VERIFIED 2026-09-06]**

`tscast_stage2_sat_s2_stab.pt`, trained with `--w-stab 1000.0`, seed 42, everything else identical
to the baseline. Its own control reproduces its recorded RMSE (0.907392).

| | unstable pairs before | after | RMSE vs Argo | bias |
|---|---|---|---|---|
| baseline, eq. 5 density NLL only | **805** of 13,468 (5.977 %) in 597 profiles | 0 | 0.8854 → 0.8856 | +0.0831 → +0.0818 |
| **soft stability penalty**, w=1000 | **2** of 13,468 (0.015 %) in 2 profiles | 0 | 0.9074 | +0.1782 |

**This is the claim, and now it is measured rather than argued.** The soft penalty reduces
violations **~400-fold** — and does **not** reach zero, which is exactly what a soft constraint
cannot promise. It also costs **+0.0220 °C** of RMSE against independent Argo and more than doubles
the warm bias (+0.0831 → +0.1782).

The projection reaches zero for **+0.0002 °C**, roughly **100× cheaper in accuracy** than the soft
penalty, and it applies to a model that was never trained for it. The two are not alternatives: the
soft penalty changes the weights, the projection is a post-hoc operator, and a soft-trained model
still emits two violations that the projection then removes.

### Two bugs found by counting rather than reading

1. **`T_TOL = 1e-6` broke the guarantee.** PAVA pools violating levels to a block mean, so a
   pooled pair has *exactly* equal density. Round-tripping that through an inversion accurate to
   1e-6 °C perturbs density by ~3e-7 kg m⁻³, which over a 5 m gap is ~6e-8 kg m⁻³ m⁻¹ — and half
   of those land negative. **395 of 401 "surviving violations" were this artifact**, median
   magnitude 1.3e-8. Now `1e-11`.
2. **A refused level silently restored its own violation.** Where `drho/dT` is not strictly
   negative (the freshwater regime — this basin reaches 1.64 psu), the inversion must refuse. The
   first version kept the original temperature there, which restored the original density and
   therefore the original violation, **inside a function whose whole promise is that there are
   none**. Refused levels now come back `NaN` with a reason. 12 of 962 profiles.

A third, in the tests: `tol=T_TOL` as a **default argument** is bound at import, so monkeypatching
`ST.T_TOL` did nothing and the "tolerance is load-bearing" test was asserting nothing. It reads the
module constant at call time now.

### The boundary, which is part of the feature

Density needs salinity at depth. **The shipped deliverable is stage 1, temperature only, so static
stability is not a well-posed question about it** and `project_profile` raises rather than
substituting. The tempting shortcut — enforce `dT/dz <= 0` — would be *wrong in this basin
specifically*: Bay of Bengal barrier-layer temperature inversions are real and this project
measures them in `physics/layers.py`. A "guarantee" bought by deleting a physical signal is worse
than no guarantee.

### The soft comparator

`train_stage2.py --w-stab` was added (default `0.0`, so every existing stage-2 objective is
byte-identical). It carries the same overwrite guard `--w-grad` has in stage 1: `--w-stab` with
`--tag s2`/`sat_s2` **raises**, because it would otherwise overwrite the baseline the experiment
compares against.

Weight chosen by measurement, not guess: on a real 2,048-sample batch the term is `2.77e-4` against
a base loss of `-0.5425`, so `w=100` is 5.1 % of the objective and `w=1000` is 51 %.

---

## 2 — The observability field

### The claim

A per-cell, per-day, per-channel map of **what the satellite is actually informing**, obtained by
differentiating the frozen model.

### Why it is not already done

Every paper reports where its model is inaccurate. That conflates *the model is weak here* with
*the surface carries no signal about this depth*. The first is ours to fix; the second is a ceiling
on the entire approach. TS-Cast gestures at it in prose; nobody computes it as a field.

### What is measured

```
J[d,c] = sigma_T(d) * sum over (day,row,col) of  d mu_z[d] / d x_z[c,day,row,col]
```

**Degrees Celsius at depth `d` per one-standard-deviation coherent shift of channel `c`.** Each
channel is per 1 s.d. of *itself*, which is the only way seven channels in °C, psu, m and m/s are
comparable — summing raw sensitivities across those units is dimensionally meaningless.

This is clean *because* the shipped decoder is `simple`: `mu` comes from the encoder latent alone.
**[VERIFIED]** running the model with climatology zeroed and with climatology randomised gives
bit-identical output. Had the paper's climatology-prior decoder shipped, a flat Jacobian would have
meant "it fell back on the average" — a much weaker statement.

### The headline result **[VERIFIED, 962 profiles, 6.3 s]**

| depth | sst | sss | ssh | u | v | wu | wv | L2 | ÷ variability | leads |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | **1.460** | 0.353 | 0.299 | 0.122 | 0.128 | 0.111 | 0.105 | 1.602 | 0.90 | sst 57 % |
| 30 | **1.199** | 0.833 | 0.892 | 0.171 | 0.200 | 0.229 | 0.170 | 2.035 | 1.17 | sst 32 % |
| 100 | 0.574 | 1.239 | **2.834** | 0.352 | 0.356 | 0.235 | 0.324 | 3.344 | 1.47 | ssh 48 % |
| 125 | 0.613 | 1.145 | **2.964** | 0.487 | 0.358 | 0.224 | 0.378 | 3.461 | **1.64** | ssh 48 % |
| 1000 | 0.276 | 0.200 | 0.221 | 0.112 | 0.103 | 0.071 | 0.089 | 0.527 | 0.49 | sst 26 % |

**The model learned the physically correct channel handover with nobody telling it to.**
Sea-surface temperature dominates the top 30 m; sea-surface height takes over from 50 m and peaks
at the thermocline. SSH is the depth-integrated signal of thermocline displacement — that is the
right thing to read, and it appears nowhere in the loss function.

Relative leverage falls **3.3×** from 1.64 at 125 m to 0.49 at 1000 m.

Per basin: Arabian Sea median information depth 1000 m, peak sensitivity 125 m (n=679); Bay of
Bengal 500 m and 100 m (n=283).

### The negative result, reported as one

The hypothesis was that our errors would sit **below** the information floor — that deep error is
the surface having nothing left to say. **It is refuted, and in the opposite direction.**

Depth-controlled (profiles above vs below *their own* floor, at the *same* depth):

| depth | MAE above floor | n | MAE below floor | n | ratio |
|---|---|---|---|---|---|
| 300 m | 0.5178 | 793 | 0.1981 | 61 | **0.38** |
| 500 m | 0.2914 | 659 | 0.2271 | 174 | **0.78** |
| 700 m | 0.2741 | 553 | 0.1785 | 274 | **0.65** |
| 1000 m | 0.2708 | 449 | 0.1991 | 354 | **0.74** |

Low sensitivity marks **quiescent water close to climatology that is easy to predict**, not water
the model cannot see into. The pooled ratio (0.32×) is **confounded by depth** — sensitivity and
the ocean's own variability both fall with depth — and is labelled as such in the artifact.

### Wording, deliberately

**Sensitivity-derived information depth. NOT an information-theoretic bound.** No noise model, no
likelihood, no mutual information. A test asserts the string "NOT an information-theoretic bound"
is present. The floor is also strongly τ-dependent: median 1000 m at τ=0.05, 200 m at τ=0.5. The
whole sweep ships in the artifact.

---

## 3 — Latent-space assimilation

### The claim

When a real float surfaces, the model's **internal state** is corrected with the network frozen,
and the correction propagates to water in a similar state — not to the float's own pixel, and not
by distance.

### Why it is not already done

The literature treats Argo as the scoring rubric and never feeds it back. The naive version —
patching the output near the float — is trivial. Correcting the 128-number latent is
inference-time data assimilation on a frozen network.

### The control that decides whether it is real

The shipped model runs **+0.1003 °C warm**, so *any* correction fitted to a real float tends to
cool the prediction, and cooling improves the score everywhere. An experiment measuring only
"error fell at similar cells" would report a global bias correction as assimilation — the same
class of mistake the cloud-dropout sweep nearly made. So the identical correction is applied to
three populations: **latent-similar**, the **least-similar decile**, and **random** recipients.
Evaluation is always leave-one-out; the donor's own profile never scores its own correction.

### The measured result **[VERIFIED, 120 donors, 962 profiles]**

| λ | in-sample fit | \|Δh\|/\|h\| | similar | near <200 km | far ≥500 km | dissimilar | shuffled |
|---|---|---|---|---|---|---|---|
| 1.0 | 5.8 % | 0.008 | +0.0018 | +0.0042 | +0.0010 | −0.0017 | +0.0014 |
| 0.1 | 37.7 % | 0.059 | +0.0108 | +0.0264 | +0.0057 | −0.0237 | +0.0009 |
| **0.03** | **66.7 %** | **0.130** | **+0.0150** | **+0.0422** | **+0.0065** | **−0.0745** | **−0.0241** |
| 0.01 | 86.2 % | 0.212 | +0.0130 | +0.0476 | +0.0029 | −0.1445 | −0.0670 |
| 0.003 | 96.2 % | 0.301 | +0.0075 | +0.0444 | −0.0026 | −0.2071 | −0.1129 |
| 0.001 | 99.2 % | 0.365 | +0.0033 | +0.0396 | −0.0061 | −0.2386 | −0.1388 |

At λ=0.03: MAE **0.5441 → 0.5291** at similar states (**+0.0150 °C**, ≈2.8 %), while random
recipients get **0.0241 °C worse** and the least-similar decile **0.0745 °C worse**. If this were
the warm bias being cancelled, all three would improve together. They do not.

**The correction travels by water mass**: still **+0.0065 °C** at recipients ≥500 km from the
donor, over 136,250 comparisons. Most of the benefit is nonetheless local (+0.0422 under 200 km),
and that is stated rather than buried.

### The selection rule had to be fixed

The first headline picked λ by the largest **margin** over the controls and chose λ=0.001 — where
similar states gain only +0.0033 °C but the controls are driven 0.2386 °C worse. **A rule that
rewards wrecking its own control will always report success.** Selection is now the largest gain
*at similar states*, among λ where **neither control improved**; the controls are a gate, not a
score.

### Limits

* Recipients are other Argo cells, not the whole basin — the gain is measured only where a float
  exists to score it.
* Pushing the latent further out of distribution destroys the long-range effect while the local
  one survives (far gain goes negative at λ ≤ 0.003).
* Single-observation correction: no time evolution, no error covariance, no cycling. Operational
  assimilation has all three.

---

## Reproducing

```bash
PYTHONPATH=src python scripts/phase2/run_stability_projection.py
PYTHONPATH=src python scripts/phase2/run_observability.py
PYTHONPATH=src python scripts/phase2/run_latent_assimilation.py
```

Each **refuses to write its artifact** if the control does not reproduce the checkpoint's own
recorded RMSE.

The soft-penalty comparator:

```bash
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage2 \
    --daily-dir data/processed/daily_sat/v001 --t-seq 11 --epochs 25 \
    --train-samples 60000 --test-samples 12000 --patience 5 --seed 42 \
    --w-stab 1000.0 --tag sat_s2_stab
PYTHONPATH=src python scripts/phase2/run_stability_projection.py --compare-tag sat_s2_stab
```
