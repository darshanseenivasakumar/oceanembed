# F8 — Validation Lab

**Owner:** Unit A (Arjhun), transferred from Unit B 2026-08-26 · **Branch:** `phase2-validation`
**Status:** TESTED · **Accept:** `python scripts/phase2/accept.py`

The feature that makes the existing demo more convincing without changing it. It shows, honestly,
where the model is good and where it is not — and answers a question nothing else in this project
could: **how much of our remaining error is ours, and how much is inherited from the reanalysis we
trained on?**

---

## 1. What was built

| file | role |
|---|---|
| `scripts/phase2/glorys_vs_argo.py` | **new measurement** — GLORYS reanalysis vs independent Argo |
| `src/phase2/validation/lab.py` | all the science; the UI defines no metrics of its own |
| `app/phase2/validation_page.py` | Streamlit page, port 8503, separate from the frozen demo |
| `scripts/phase2/accept.py` | **new** — the one command Darshan runs, with checks for F5/F6/F8 |

16 tests in `tests/phase2/test_validation.py`; **222 pass repo-wide**. Baseline untouched.

---

## 2. The new measurement: how good is our training truth?

Everything in this repo previously measured *our model* against something. Nothing had measured
**GLORYS itself** — and GLORYS is what we trained on. A model cannot be more accurate than the
truth it was fit to, so this sets the ceiling.

`scripts/phase2/glorys_vs_argo.py` is model-free: it compares `grids.npz["temp"]` directly against
Argo floats at the same ≤5-day tolerance the Phase-1 evaluation used.

**[VERIFIED] 888 profiles matched of 2455 · 11,761 depth comparisons**

| depth | MAE | RMSE | bias (argo − glorys) |
|---|---|---|---|
| 20 m | 0.518 | 0.890 | −0.110 |
| 50 m | 0.640 | 0.988 | −0.351 |
| **100 m** | **0.785** | 1.139 | **−0.489** |
| 125 m | 0.768 | 1.059 | −0.413 |
| 500 m | 0.219 | 0.319 | +0.019 |
| 1000 m | 0.209 | 0.287 | +0.106 |

The reanalysis is worst in the thermocline and carries a **systematic warm bias of ~0.5 °C at
75–125 m** — the floats are consistently colder. Overall MAE 0.522 °C, RMSE 0.828 °C.

### Is it collocation mismatch rather than real error? No.

| tightening | n | 100 m MAE | Δ |
|---|---|---|---|
| baseline (≤5 days) | 888 | 0.785 | — |
| ≤3 days | 548 | 0.761 | **−0.023** |
| ≤25 km | 888 | 0.785 | **+0.000** |

**Correction to how this was previously framed.** "Tightening to ≤25 km and ≤3 days removes only
0.02 °C" is true, but the ≤25 km half does *nothing* — nearest-cell distance on a 0.25° grid maxes
at **18.7 km**, so every match is already inside 25 km and no profile is dropped. All of the 0.023
comes from the time filter. A test pins this so the claim cannot drift back.

**One caveat that must travel with these numbers.** `temp` is GLORYS *after* interpolation onto our
grid and our 15 depth levels. That interpolation is part of the error our model inherited, so it
belongs in the number — but it makes this an **upper bound** on the native product's own error.
This is not a verdict on GLORYS.

---

## 3. The headline result: inherited vs earned

Subtracting the reanalysis's own RMSE from ours, per depth:

```
depth   ours   reanalysis  headroom   verdict
    0  0.389    0.360       +0.029   at-ceiling
   10  0.735    0.655       +0.080   model-limited
   20  1.202    0.890       +0.312   model-limited
   30  1.323    0.995       +0.328   model-limited
   50  1.365    0.988       +0.377   model-limited
   75  1.246    1.068       +0.178   model-limited
  100  1.162    1.139       +0.023   at-ceiling
  125  1.079    1.059       +0.020   at-ceiling
  150  0.959    0.951       +0.008   at-ceiling
  200  0.853    0.774       +0.079   model-limited
  300  0.761    0.622       +0.139   model-limited
  500  0.350    0.319       +0.031   at-ceiling
  700  0.300    0.324       -0.024   at-ceiling
 1000  0.220    0.287       -0.067   beats-reanalysis
```

**The thermocline error is inherited, not earned.** At 100–150 m we are within 0.023 °C of the
reanalysis's own error against the same floats. We have hit the ceiling of our training truth
there; no amount of model work moves it without a better truth.

**Our genuine weak spot is the mixed layer, 20–50 m** — 0.31–0.38 °C worse than the reanalysis.
That gap is ours to close, and the panel says so in those words.

**At 1000 m we beat the reanalysis** (−0.067 °C).

The ±0.05 °C tolerance separating the verdicts is a presentation convention, exposed as
`inherited_vs_earned(tolerance_c=...)` and covered by a test that an absurd tolerance collapses
every verdict — so it cannot be quietly tuned to flatter a result.

---

## 4. The 1000 m paradox, explained rather than hidden

Skill is **lowest at 1000 m (+0.225)** — and that is also where our **absolute error is best in the
whole column (0.220 °C)**. The deep ocean barely varies, so climatology is already excellent there
(0.284 °C) and there is almost nothing left to beat.

Low skill, excellent prediction. **A skill-only chart reports our best result as our worst**, so the
page always shows absolute RMSE beside skill, and `per_depth()` returns
`worst_skill_is_also_best_absolute` as a computed flag rather than the page hardcoding the
observation. Skill is positive at all 15 depths, from +0.225 (1000 m) to +0.501 (500 m).

**Convention:** `skill = 1 − RMSE/RMSE_climatology`. [VERIFIED] this reproduces the published
overall figure exactly: 1 − 0.9638/1.5725 = 0.3871. It is *not* the variance form
`1 − (RMSE/RMSE_clim)²`, which would give ~0.62 and silently change every number. A test pins it.

---

## 5. The naming trap this module exists to prevent

`artifacts/argo_error_by_depth.json` has a key called **`rmse_glorys`**. That is **our model fed
GLORYS surface inputs** — a model score. It is **not** the GLORYS reanalysis. Labelling it "GLORYS"
on a panel would tell a judge we had measured the reanalysis when we had not.

`lab.py` renames on the way in and never lets the ambiguous key through:

```
model_satellite  our model, real satellite inputs   <- the PS deliverable
model_glorys     our model, GLORYS inputs           <- was `rmse_glorys`
reanalysis       GLORYS itself vs Argo              <- glorys_vs_argo.json
```

A test asserts the raw key does not leak and that the two arrays are not equal.

---

## 6. What is deliberately NOT shown

**The LightGBM baseline.** The spec asked for it beside climatology. It cannot be shown honestly on
this machine, so `baseline_availability()` **refuses it and says why on the panel** rather than
omitting the column silently:

- `argo_error_by_depth.json` has no LightGBM column — it was never scored against Argo.
- `lgbm_model.pkl` was deliberately excluded from the data bundle as regenerable, so the local file
  predates the real data.
- Local `X_train.npy` has **143514** rows while `provenance.json` records **n_train = 323028**.
- The checkpoint is a bare list of boosters (D-012) with **no provenance stamp**, so its training
  source cannot be read back from the file.

Quoting it would report a synthetic-trained model as a baseline, or claim provenance we cannot
verify. To unblock: `python scripts/prepare_dataset.py --real && python -m oceanembed.train.train_lgbm`,
then score it against Argo.

---

## 7. Known weaknesses stated on the panel

Each with an evidence pointer, because a result without its limits is not a result:
MC-dropout ~4× overconfident at the thermocline (D-016) · satellite covers 24 of 48 dates ·
Argo validation is 2022 only · 24% of ocean cells are shallower than 1000 m.

---

## 8. Charting: altair, not plotly

The page first used plotly and **ImportError'd on load** — plotly is in `requirements.txt` but is
not installed in this environment. `app/panels/_viz.py` had already recorded the reason:

> plotly are in requirements.txt but are NOT guaranteed to be installed on a teammate's or a
> demo machine, and a panel that ImportErrors on demo day is worse than a plainer chart.

Rewritten in altair, which ships with Streamlit. The frozen demo does **not** import plotly, so it
was never at risk — checked, because four days from the gate that was worth confirming rather than
assuming.

**Streamlit traps avoided:** no cached function takes an underscore-prefixed argument (that
silently excludes it from the cache key and pins the first result forever — [VERIFIED] against
current Streamlit docs); no bare expression sits at statement level.

---

## 9. Reproduce

```bash
python scripts/phase2/glorys_vs_argo.py            # writes artifacts/glorys_vs_argo.json
python scripts/phase2/accept.py                    # safety + full suite + data + science
streamlit run app/phase2/validation_page.py --server.port 8503
```

Requires the data bundle (gitignored). Tests skip — never fake — when artifacts are absent.
