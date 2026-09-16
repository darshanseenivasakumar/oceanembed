# Feature request: What-If Calculator (separate section)

Hand this file to Claude and start in **plan mode**. Read `CLAUDE.md` first, then this file, before
proposing a plan.

## Goal

Add a **What-If Calculator**: a section of the app, kept completely separate from the existing
panels (reconstruction, profile, map, priority, validation). It lets a user take a real query
result and manually override the numbers that feed the formulas/model, then instantly see how the
outputs change — "what if SST were 10.2 instead of 10.0?" — without touching real data or
retraining anything.

This is a **backend + wiring** task. Do not spend design effort on visual UI/UX polish — that part
is owned by Arjhun. Plan mode should focus on: what to compute, what to expose, how to keep it
correct and separate. A minimal Streamlit page is enough to prove it works end to end.

## Why "separate"

This must NOT be bolted onto `app/streamlit_app.py`'s existing flow or mixed into `app/panels/`.
It should be its own page/section (e.g. a new Streamlit page under a `pages/`-style entry, or a
clearly separate tab/route — your call in plan mode, driven by how this Streamlit version supports
multi-page apps). Someone should be able to use the real app without ever noticing the calculator
exists, and vice versa.

## What "calculate whatever formulas we used" means concretely

This repo already has several **real, explicit formulas** with tunable parameters — not the neural
network itself, which isn't meaningfully "slidable." Reuse these functions as-is; do not
reimplement their math:

- `src/oceanembed/products/anomaly.py`
  - `anomaly(pred_grid, climatology, month)`
  - `standardized_anomaly(pred_grid, climatology, month)`
  - `flag_extremes(pred_grid, climatology, month, k=DEFAULT_K)` — `k` (default 2.0) is a real
    user-adjustable parameter.
- `src/oceanembed/products/observation_priority.py`
  - `observation_priority(anomaly_grid, uncertainty_grid, sparsity_grid, weights=DEFAULT_WEIGHTS, robust=True)`
    — `weights` (default `(1.0, 1.0, 1.0)` for anomaly/uncertainty/sparsity) and `robust` are
    real user-adjustable parameters.
- `src/oceanembed/inference/predict.py`
  - `_features_at(i_lat, i_lon, t_idx)` builds the raw model input vector:
    `[sst, sss, ssh, u, v, sin(lat), cos(lat), sin(lon), cos(lon), sin(doy), cos(doy)]`.
  - `reconstruct(lat, lon, date)` shows how a point is looked up and fed through
    `mc_dropout_predict(model, Xraw)` to get `profile_mean`/`profile_std`.

The five **surface inputs** (`sst`, `sss`, `ssh`, `u`, `v`) are the "x = 10 vs x = 10.2" variables
the user most wants to play with, because they directly drive the model's output profile. The
`k`, `weights`, and `robust` values are the second kind: they drive the downstream formulas, not
the model.

## Required behavior

1. User picks a real baseline point the same way the main app does (lat, lon, date) — reuse
   existing lookups (`grids`, `_nearest_time_index`, etc.), don't duplicate that logic.
2. Show the baseline's real `sst, sss, ssh, u, v` values (read from the real grid, not invented).
3. Let the user override any subset of those five values, plus `k`, `weights` (3 numbers), and
   `robust` (bool).
4. Recompute:
   - The model profile using the overridden surface inputs (call `mc_dropout_predict` with the
     edited raw feature vector — same 11-element layout as `_features_at`, only the first 5
     entries change).
   - `anomaly` / `standardized_anomaly` / `flag_extremes` with the overridden `k` where relevant.
   - `observation_priority` with the overridden `weights`/`robust`, if that panel's inputs are in
     scope for this baseline point.
5. Display both the **baseline (real)** result and the **what-if (edited)** result side by side, or
   as a clear delta. Label the what-if numbers as **hypothetical / not measured**, since they come
   from user-edited inputs, not real observations — this matters per `CLAUDE.md`'s real-data-only
   rule (that rule is about not faking real results; it does not forbid an explicitly-labeled
   what-if sandbox).

## Design goal: extensible, not just these three formulas

The task says "all the variables used by the other features" — treat the three formulas above as
the first entries in a small **formula registry**, not as hardcoded special cases. Something like:
a list/dict of `{id, label, function, inputs: [{name, default, min, max}], outputs}` that the
calculator iterates over generically. This way, when Unit A or Unit C adds a new tunable formula
later, they register it once and the calculator UI (whatever Arjhun builds) can pick it up without
structural changes. Keep this registry as data, not a UI framework — plan mode should decide the
simplest structure that satisfies this, not over-engineer it.

## Constraints

- Do not modify `anomaly.py`, `observation_priority.py`, or the model/training code. Only import
  and call them with different arguments.
- Do not touch `app/panels/*` (Unit C's files) or retrain/modify the model (Unit A's files) —
  new code should live in new files.
- No new heavy dependencies.
- Follow `CLAUDE.md`'s engineering loop: understand → inspect → plan → implement smallest working
  version → test → real-data smoke test → document → commit.
- After planning, use the `writing-plans` skill (or this session's equivalent) to produce an
  implementation plan before writing code, per this repo's usual workflow.

## Out of scope

- Visual design, styling, layout polish (Arjhun's part).
- Editing training data, retraining, or changing model architecture.
- Any formula not already implemented somewhere in the repo — this feature exposes existing math,
  it doesn't invent new science.
