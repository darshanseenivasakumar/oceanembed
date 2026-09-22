# PROMPT FOR ARJHUN'S CLAUDE — the visualization suite (V-series)

Paste this whole file as your first message. It is self-contained; assume you know nothing else.
Read `CLAUDE.md` and `docs/phase2/AGENT_SYNC.md` after it, then start.

---

## WHO YOU ARE AND WHAT THIS IS

You are the ML/engineering agent on **OceanEmbed**, Smart India Hackathon 2026, problem statement
**SIH26066** (Ministry of Earth Sciences): reconstruct depth-wise subsurface ocean **temperature**
from surface satellite observations at 0.25° over the North Indian Ocean (5–30 N, 45–105 E), 15
depths 0–1000 m.

Repo: `D:\sih project\oceanembed`. Team: Arjhun (you), Darshan, Mitun, Niru. Two Claude agents:
yours and Darshan's.

**The deliverable, stated honestly (memorise this distinction — a judge will probe it):**
- **[VERIFIED]** The shipped product is `deliverable_satellite` in `artifacts/frozen_manifest.json`:
  stage-1, **satellite inputs** (OSTIA SST, DUACS altimetry, SMOS-blended SSS, GLOBCURRENT currents,
  observational wind), seed 42, 7 channels, T_SEQ 11. Headline **RMSE 0.9078 °C, corr 0.8812**.
- **The 0.8548 °C number is a GLORYS-input comparator, NOT the deliverable.** Never quote 0.8548 as
  the headline. The manifest was re-frozen on 2026-09-03 specifically to correct that conflation.
- `checkpoint_present: false` for the deliverable on some machines — scores are verified from the
  metrics JSON, not re-run. If you cannot load `tscast_stage1_sat_7ch_s42.pt`, say so; do not fake it.

**Why we are building visualizations at all.** For INCOIS and ocean scientists, a plot is a
diagnostic, not decoration. A "model vs GLORYS vs Argo" slice through the thermocline *proves the
model captured physics*; a point-wise RMSE number does not. Everything below is chosen to make the
existing, already-validated model **legible and trustworthy** — not to add model capability.

## THE GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

Read-only, no exceptions: `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, and the baseline
`tests/`. **Import from them. Never edit them.** If you need different behaviour, write an adapter
under `src/phase2/`.

Branch names use a **HYPHEN**: `phase2-viz-transect`. Git refuses `phase2/anything` while a branch
named `phase2` exists — it fails with `cannot lock ref`. Hard failure, not style.

## OWNERSHIP — what you may touch

You own (per `CLAUDE.md` + the earlier handover): `src/phase2/` (`physics/`, `derived/`, `cube/`,
`validation/`), and **new files you add** to `app/phase2/` and `tests/phase2/`.

**Off limits (Darshan's F1, read+import only):** `src/phase2/data/collocation.py`,
`app/phase2/collocation_page.py`. If either needs a fix, post an ASK in AGENT_SYNC; do not edit them.

---

## THE ONE HONESTY RULE THAT SHAPES TWO OF THESE FEATURES — READ BEFORE PLANNING

**The deliverable satellite model predicts TEMPERATURE ONLY. It has no salinity output.**

Two things you are asked to draw — **isopycnals** (lines of constant density) and **sound-speed
contours** — are *functions of salinity*. Density is ρ(S, θ); sound speed is c(S, T, depth). You
physically cannot derive either from the temperature field alone.

Darshan's decision (confirmed): compute them from a **clearly-labelled companion salinity field** —
either GLORYS `so` (via the collocation engine / `subsurface.npz`) or the stage-2 T+S checkpoint —
and **label it in the UI as NOT from the satellite model.** A caption such as *"Density &amp; sound
speed use GLORYS salinity as a companion field; the satellite deliverable predicts temperature only"*
must be visible on any panel that shows an isopycnal or a sound-speed contour.

This is not a footnote to bury. Showing the seam is what makes the panel defensible. A judge who
spots an un-labelled salinity dependency will assume the whole model is oversold. Turn the weakness
into a visible integrity signal.

---

## WHAT ALREADY EXISTS — reuse, do not rebuild

The linchpin. One call gives you temperature **and calibrated** sigma for the whole basin:

```
from phase2.tscast_nio.field import predict_field
from phase2.tscast_nio.inference import TSCastPredictor
field = predict_field(TSCastPredictor(), "2026-05-15")
#   field["temperature"] (100,240,15) °C,  NaN on land/below seafloor
#   field["sigma"]       (100,240,15) °C,  CALIBRATED per-cell σ
#   field["valid_mask"], field["land_mask"], field["provenance"]
```

Never re-read `data/processed/grids.npz` to get the model field — that is monthly GLORYS, not the
shipped reconstruction. Get the field from `predict_field`.

| You need | Reuse | Where |
|---|---|---|
| Depth-vs-distance section | `sample_transect(track, field)` → `{temperature,sigma (n,15), lat,lon,distance_km,depths}` | `src/phase2/derived/transect.py` |
| Even-spaced track between 2 points | `track_points(lat0,lon0,lat1,lon1,n=50)` | same |
| NaN-strict sampling (no grid-snap staircase, land=gap) | `bilinear_at(field_2d,lat,lon,lat_grid,lon_grid)` | same |
| **Isotherm / isopycnal line on a section** | `isotherm_line(section, threshold_c=26.0)` — **threshold-generic**: pass a σθ section + a density value and it draws an isopycnal with zero new contour code | same |
| Density / σθ | `density(S,θ)`, `sigma_theta(S,θ)` (EOS-80) | `src/phase2/physics/seawater.py` |
| MLD / ILD / barrier / thermocline | `mixed_layer_depth`, `thermocline`, … | `src/phase2/physics/layers.py` |
| TCHP / OHC / D26 as 2-D maps | `heat_content_field(field) → {tchp, ohc_0_zref, d26}` | `src/phase2/derived/heat_content.py` |
| Model vs nearby Argo floats | `overlay(lat,lon,date) → {model, floats, per_depth}`, `two_sigma_band` | `src/phase2/validation/argo_overlay.py` |
| GLORYS reference T + companion salinity | `CollocationEngine(...).collocate(lat,lon,dt)` → `sources["glorys"].temperature_profile`, `sources["subsurface"].salinity_profile` | `src/phase2/data/collocation.py` (import only) |
| 3-D slicing / Plotly volume | `OceanCube.reconstruct(date)`, `.depth_slice`, `.section`, `.profile`; `cube/volume.py` | `src/phase2/cube/` |

The template page to copy: **`app/phase2/transect_page.py`** (port 8510) — Altair `mark_rect` section
+ isotherm `mark_line` overlays, user draws endpoints. Every Phase-2 page follows its shape:
module docstring with the exact `streamlit run … --server.port N` line, `sys.path.insert(...src)`,
`from oceanembed import config`, a `@st.cache_data build(...)` calling `predict_field`, a
`_v2_version()` sha256 cache-buster, `main()` guarded by `if __name__ == "__main__"`.

## WHAT DOES NOT EXIST — net-new, build and TEST it, never assume

- **[VERIFIED] Sound-speed function: does not exist anywhere in `src`.** You will write it in
  `src/phase2/physics/` (you own physics). Use the **Mackenzie (1981) nine-term** equation. Pin it
  with a canonical acceptance test: **c(S=35 PSU, T=25 °C, D=1000 m) ≈ 1550.744 m/s** (Mackenzie's
  own check value). If your function does not reproduce that to <0.05 m/s, it is wrong — do not ship
  it. Needs salinity → companion-salinity label applies.
- **[VERIFIED] Full-map isopycnal contour helper: does not exist.** On a *section* it is free
  (`isotherm_line` on a σθ section). A 2-D map contour would be new — only build it if a panel needs
  it.
- **[VERIFIED] EKE / geostrophic-current-from-SSH: does not exist.** Surface currents exist only as
  model *input* (u, v). If you overlay current vectors, label them "model input (u,v)", never a
  derived diagnostic. Do not invent an EKE field.
- **[VERIFIED] Cyclone track data: not in the repo.** V4 needs a track source — an IBTrACS CSV, or
  one hardcoded case study (e.g. Cyclone Mocha or Biparjoy). Resolve this with Darshan before
  building V4; do not fabricate a track.
- **MC-dropout σ** (`src/oceanembed/inference/uncertainty.py`) is uncalibrated and overconfident at
  depth (decision D-016, ~3× too small at the thermocline). **V3 must use the calibrated Phase-2
  `predict_field` sigma, never MC-dropout.**

---

## YOUR TASK: FOUR FEATURES, IN THIS ORDER

Build **one at a time**. Branch, build, test, push, report. Darshan tests each before you start the
next. V1 and V2 are the priority; V3 is cheap; V4 is stretch — do it only if V1–V3 land cleanly.

### V1 — Transect upgrade (Strategy 2). Branch `phase2-viz-transect`.

Extend `src/phase2/derived/transect.py` and `app/phase2/transect_page.py` (port 8510). The section
heatmap + 20/26 °C isotherms already work. Add, in this sub-order (each is independently shippable):

1. **Model vs GLORYS vs Argo section** — the physics-proof panel, and the safest (temperature-only,
   no salinity). Draw the model T section beside the GLORYS T section along the same track, and
   scatter nearby Argo float temperatures as dots colored by model−float error. Reuse `argo_overlay`
   and the collocation GLORYS profiles. This is the single most credible panel in the whole suite —
   build it first.
2. **Sliding slice** — a slider that sweeps the transect line (e.g. hold latitude span, slide the
   whole line east–west). Pure UI over `track_points` + `sample_transect`. Show the thermocline
   tilt change; a clean "watch the thermocline upwarp near the coast" is a strong live-demo moment.
3. **Isopycnal overlay** — compute σθ along the track from companion salinity, draw isopycnals via
   `isotherm_line(sigma_theta_section, threshold=…)`. **Companion-salinity label required.**
4. **Sound-speed contours** — new Mackenzie function; contour c on the section. **Label required.**
   This is the naval-acoustics hook (sonic layer depth, SOFAR channel), but it is last for a reason:
   it depends on both the new function and companion salinity.

Acceptance check (add to `scripts/phase2/accept.py`): the GLORYS/Argo panel produces finite,
in-range temperatures along a known track; the sound-speed function passes the 1550.744 m/s check.

### V2 — Click-any-pixel → profile (Strategy 1). Branch `phase2-viz-clickmap`. NEW page, port 8511.

The flagship demo tool: *"give me a lat/lon and I'll show you the predicted thermocline right now."*

- An Altair `mark_rect` depth-slice map (temperature at a chosen depth from `predict_field`), with
  `st.altair_chart(chart, on_select="rerun")` selection. A clicked cell populates a side panel with
  that cell's vertical temperature profile + calibrated ±2σ band (`two_sigma_band`), and the
  companion salinity profile if the salinity panel is enabled (labelled).
- Optional: surface current vectors from input u,v as a quiver-style overlay, labelled "model input".
- Degrade gracefully: if selection events are unavailable, fall back to lat/lon `number_input`
  (the pattern `cyclone_heat_page.py` already uses).

Fetch current Altair/Streamlit selection-API docs via Context7 before coding — the `on_select` API
is recent and your training data may be stale.

### V3 — Uncertainty-as-transparency (Strategy 3). Branch `phase2-viz-uncertainty`. NEW page, port 8512.

One `mark_rect` map at a chosen depth: temperature → color (e.g. `turbo`), **calibrated sigma →
opacity**. Confident cells are vivid; uncertain cells (dynamic eddies, sparse-data zones) fade out.
`predict_field` already returns the 2-D sigma, so this is mostly an Altair `opacity` encoding plus a
legend that explains the double encoding. Frame it as the "where to trust the AI / where a float
would add most" view — but do **not** re-run the observation-priority claim as novel (it is not; see
`docs/NOVELTY_MATRIX.md`). This is a *presentation* of calibrated uncertainty, honestly labelled.

### V4 — 3-D volumetric TCHP + cyclone track (Strategy 4, STRETCH). Branch `phase2-viz-tchp3d`. Port 8513.

Only if V1–V3 are done, tested and pushed. Plotly `go.Volume` (reuse `cube/volume.py`; **mind the
`.tolist()` trap** — Plotly ≥6 serialises numpy as base64 that Streamlit's bundled plotly.js can't
decode, giving an empty box). Show the TCHP field from `heat_content_field` as a semi-transparent
subsurface "fuel" volume, overlay a real cyclone track (resolve the data source first), and scatter
Argo floats colored by RMSE. Depth exaggeration so it isn't flat. Degrade to a 2-D TCHP map if the
3-D render fails, exactly as `cube_page.py` does.

---

## WORKFLOW PER FEATURE — follow every step

1. `git status`, confirm the branch, confirm `main` untouched. Branch with a hyphen.
2. Research first. **Context7** for current library docs (Altair selection API, Streamlit
   `on_select`, Plotly volume, xarray) before coding — training data may be stale.
3. Build the smallest working version.
4. Write real tests under `tests/phase2/`. **Do NOT create `tests/phase2/__init__.py`** — it shadows
   the `src/phase2` package and breaks imports under pytest. Delete it if it appears.
5. Run the FULL suite: `PYTHONPATH=src python -m pytest -q`. Everything must pass, not just yours.
6. Real-data smoke test and **inspect the actual numbers** — passing tests are not correct science.
   We once had 130 tests green while the model returned 52 °C from a 28 °C input.
7. Add a feature-specific check to `scripts/phase2/accept.py` asserting real science (a value in
   range, the 1550.744 m/s sound-speed check), not just that the module imported.
8. Register the new port in `.claude/launch.json` and the port table in `docs/HANDOFF.md`.
9. Commit only after tests pass (use `git commit -F -` with a heredoc — backticks in `-m` get
   command-substituted by bash and silently delete text). Push the feature branch. Never push main.
10. Append to `docs/phase2/AGENT_SYNC.md` at the top of the LOG, tagged `[ARJHUN]`, with evidence
    tags, the branch name, the one command Darshan runs, and what he should see on screen.

## HOW DARSHAN TESTS — make it one command

```
python scripts/phase2/accept.py
```

It verifies the branch is safe, runs the full suite and the data verifier, then runs your
feature-specific check for whatever branch is current. Every feature adds its own check function.

## TRAPS THAT HAVE ALREADY COST US HOURS

- `tests/phase2/__init__.py` breaks imports under pytest. Never create it.
- Branch `phase2/x` fails while branch `phase2` exists. Use `phase2-x`.
- `st.cache_data` silently drops any argument whose name starts with `_`. Naming a cache arg `_lat`
  pins the first result forever — it looks like a science bug. Use `_v2_version()` sha256 busting.
- Altair v6 refuses frames >5000 rows: call `alt.data_transformers.disable_max_rows()` (the full NIO
  grid is ~11.8k cells after meshgrid).
- Plotly ≥6 + Streamlit: pass `.tolist()`, not numpy, into `go.Volume`/`go.Scatter3d`.
- On Windows, Streamlit runs as `python.exe`, so `ps | grep streamlit` finds nothing. Use
  `netstat -ano | grep :PORT` then `taskkill //PID <pid> //F`.
- Never let a bare expression sit in Streamlit code — magic renders its return value (a stray `None`
  badge once appeared in the UI this way).
- Sample tracks via `bilinear_at`, never repeated `reconstruct()` — the latter snaps to grid centres
  and draws a staircase. Land / seafloor is always a **gap**, never a smoothed blend.

## HONESTY RULES

Tag every claim **[VERIFIED]** (you ran it and saw output), **[INFERRED]** (reasonable, untested),
or **[UNKNOWN]** (say so). Never claim code works unless you executed it. Never fabricate a metric,
an uncertainty, a citation, or a cyclone track. Keep 0.9078 (deliverable) and 0.8548 (comparator)
distinct at all times. If Darshan's spec here looks wrong to you, say so before building — being
challenged by the other agent is the point.

## FIRST REPLY — do not write code yet

Reply with:
1. Which feature you start (V1, and within it the GLORYS/Argo panel) and why.
2. Your read on the **Sep-7 2026** time budget — can V1 + V2 land without hurting demo prep? Say no
   if no; landing V1 and V2 cleanly beats four half-finished pages.
3. Anything in this spec you think is wrong — especially the companion-salinity approach and the
   sound-speed choice.
