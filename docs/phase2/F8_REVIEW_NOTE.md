# F8 Validation Lab — review note

**From:** Darshan · **26 Aug 2026** · **Branch tested:** `phase2-ocean-cube` @ `970ce59`
**Concerns:** `app/phase2/validation_page.py` and `src/phase2/validation/lab.py` (Arjhun's F8 work)

Ran the page locally on port 8503. **Section 2 is the best thing built on this project so far.**
Three defects below, none of which affect the Aug-30 demo — `main` is untouched and F8 is not being
shown on the 30th.

---

## 1. LightGBM renders "shown." with nothing under it

Section 3 prints the literal line **"LightGBM — shown."** followed by no numbers.

The guard in `lab.baseline_availability()` tests whether local `X_train` row count equals
`provenance.json`'s `n_train`. On Arjhun's machine those differed (143,514 vs 323,028) so LightGBM
was refused and his test passed. **On this machine they match exactly — 323,028 == 323,028 — so the
guard opens.** But there is no LightGBM score against Argo anywhere: `argo_error_by_depth.json`
contains only `rmse_satellite`, `rmse_glorys`, `rmse_climatology`.

So on the machine with the full real dataset, the panel asserts a baseline it cannot show. That is
the fabricated baseline the guard was written to prevent, reached through it rather than around it.

**The conclusion is right, the check is wrong.** Row count proves the *training data* is right; it
cannot prove the *checkpoint* was trained on it, since the pickle carries no provenance stamp. The
invariant that holds on every machine:

> Show LightGBM only if a real Argo score exists for it.

None exists, so it is never shown — for the right reason, everywhere.

Same fix for `tests/phase2/test_validation.py::test_lightgbm_baseline_is_refused_...`, which asserts
a property of one filesystem rather than of the code. It is why the suite reports 1 failed here.

## 2. Section 4 is empty and points at a file that does not exist

The page says:

> Calibration could not be measured here: `artifacts/mc_calibration.json` is absent.
> Generate it: `python scripts/phase2/measure_mc_calibration.py`

That script exists **only on `phase2-collocation`**. Checked every branch:

| branch | has the script |
|---|---|
| phase2-collocation | yes |
| phase2-ocean-cube | **no** |
| phase2-validation | **no** |
| phase2-reliability | **no** |
| main | **no** |

So anyone following the page's own instruction hits "file not found", and Section 4 — *"how much
should you trust the model's own error bars?"* — stays blank. That is one of the most important
sections on the page.

Fix: cherry-pick the script onto the branch, or change the message to point at something that exists.

## 3. The Section 1 charts are unreadable

Numerically correct, visually noise. The depth axis is **linear**, but our depth levels are not
evenly spaced:

`0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000`

**10 of the 15 points fall between 0 and 150 m** — 67% of the data compressed into the top **15%**
of the chart, while the bottom 85% of vertical space carries 5 points. The skill line consequently
reads as a vertical scribble, and a judge sees noise rather than a result.

Fix: a log depth axis, or ordinal (evenly spaced) depth labels. Standard for ocean profiles that
sample densely near the surface.

---

## What should not be touched

**Section 2 — inherited vs earned — is the pitch, already visualised.** The red / grey / green
split and the closing line:

> *"Our honest weak spot is the mixed layer, 20–50 m … In the thermocline (100–150 m) we are within
> 0.05 °C of it: that error is inherited, not earned."*

**Section 5 — "what this model is not good at"** — is the right instinct and the reason a judge will
trust the rest of the page.

## How to reproduce

```
git checkout phase2-ocean-cube
python scripts/phase2/glorys_vs_argo.py
python -m streamlit run app/phase2/validation_page.py --server.port 8503
```

The middle line is required — that artifact is gitignored and does not arrive with the branch.
