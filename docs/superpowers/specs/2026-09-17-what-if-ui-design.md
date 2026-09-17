# What-If Calculator — port-8500 UI (Unit A)

**Date:** 2026-09-17 · **Owner:** Unit A (Arjhun) · **Backend:** Unit B (Darshan), `src/oceanembed/whatif/`

The backend (`baseline()`, `apply()`, `list_formulas()`) is built, committed, and its 24 tests pass.
This spec covers only the Streamlit view that wires it into the one-page instrument on port 8500.

## Goal

Let a user override the inputs to the real model/formulas and see **baseline vs what-if vs delta**,
live, inside the existing instrument — without re-implementing any science (the backend calls the
real model/anomaly/priority code) and without ever presenting an edited number as a measured one.

## Placement

- One new file: `app/ui/features/whatif.py`, exposing `render(ctx) -> None` like every other feature.
- Two registration edits (Unit A's own files): `app/ui/features/__init__.py` `MODULES`, and
  `app/ui/words.py` `FEATURES` (+ any `EXPLAIN` ids the page uses).
- Band: **STRESS IT** — it probes the model with inputs that never happened, the same spirit as
  Cloud cover and Profile shape. Rail goes 15 → 16 features.
- No new port, no `launch.json` entry, no edits to other units' files. Backend is imported only.

## Layout — three tabs, driven by the registry

The page loops `whatif.list_formulas()` and renders one tab per `FormulaSpec`, building each tab's
widgets from `spec.inputs` (`.kind` → slider/toggle, `.default`/`.min`/`.max`/`.unit` → widget
args). A 4th formula added to the registry later appears with **zero** UI changes.

1. **Subsurface profile** (`scope="point"`, the flagship). Pick a point on the shared clickable
   basin map (`maps.clickable`). Five sliders (SST/SSS/SSH/u/v), each pre-filled with the *real*
   baseline value at that point. An explicit **Run what-if** button triggers `apply(...)` (the
   MC-dropout call is ~26 s here, so recomputing on every slider tick would freeze the page).
   Output: baseline and what-if temperature profiles on one depth axis, plus a `tiles()` row of the
   deltas at surface / 100 m / 500 m.

2. **Anomaly extremes** (`scope="grid"`). One slider `k`. Render `grid_is_extreme` as a basin map
   and a tile for the extreme-cell count, baseline vs what-if.

3. **Observation priority** (`scope="grid"`). Three weight sliders + robust toggle → re-render the
   priority basin map and point/basin tiles live (this handler is cheap — no button needed).

## Honesty guardrails (repo real-data rule)

- Every `apply()` result carries `hypothetical: True`; the page shows a persistent `ux.caveat(...)`:
  *"These numbers come from inputs you edited, not from measured observations."*
- The baseline is always drawn beside the what-if, so the reader sees measured vs edited.
- Handlers return `available: False` on land / missing artifact; the page renders the same refusal
  style the other panels use, and **never** invents a number. If the backend package is absent the
  feature shows the reproduce command, exactly like `assimilate.py`.

## Data flow

`ctx` (date, source) → map `ctx.source` (`"Satellite"`/`"GLORYS"`) to the backend's lowercase
`"satellite"`/`"glorys"` → `whatif.baseline(lat, lon, date, source)` once per point →
each tab calls `whatif.apply(formula_id, overrides, ctx_backend)`. Heavy model work runs only on the
profile tab, only when the point is set and Run is pressed.

## Testing

Backend's 24 tests already pass and are the science guarantee. For the view: a real smoke test on
port 8500 — pick a point, move a slider, press Run, confirm the what-if profile diverges from the
baseline and the delta is non-zero; confirm land refuses; confirm the two grid tabs re-render. A
Streamlit view is not meaningfully unit-testable, so the smoke test is the definition of done here.

## Out of scope

No changes to the backend, no new formulas, no persistence of what-if scenarios, no export. Adding a
tunable formula later is a backend one-liner (`FormulaSpec` in `registry.py`); the UI picks it up.
