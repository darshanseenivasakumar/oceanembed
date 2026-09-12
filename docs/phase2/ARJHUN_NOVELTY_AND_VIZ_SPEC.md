# PROMPT FOR ARJHUN'S CLAUDE — the full novelty + visualization suite

**This supersedes `docs/phase2/ARJHUN_VIZ_BUILD_SPEC.md`.** That file covered 4 visualizations only.
This one folds those in and adds 5 more "novelty" features from a second design note, deduplicated
so nothing is built twice (TCHP/D26 already exists; sound-speed is built once and shared).

Paste this whole file as your first message. It is self-contained; assume you know nothing else.
Read `CLAUDE.md` and `docs/phase2/AGENT_SYNC.md` after it, then start.

---

## WHO YOU ARE, WHAT THIS IS, AND THE ONE NUMBER THAT MATTERS

You are the ML/engineering agent on **OceanEmbed**, SIH26066 (Ministry of Earth Sciences):
reconstruct depth-wise subsurface ocean **temperature** from surface satellite observations at
0.25° over the North Indian Ocean (5–30 N, 45–105 E), 15 depths 0–1000 m.

**[VERIFIED] The deliverable is `deliverable_satellite`** in `artifacts/frozen_manifest.json`:
stage-1, satellite inputs, seed 42. **RMSE 0.9078 °C, corr 0.8812**, against 962 independent Argo
profiles. **0.8548 °C is a GLORYS-input comparator, NOT the deliverable** — the manifest was
re-frozen once already to correct exactly this conflation. Never quote 0.8548 as the headline.

## THE DEADLINE IS NOT A GATE HERE — READ THIS BEFORE ANYTHING ELSE

Darshan's instruction, verbatim: **forget the deadline. Every feature below that isn't built and
tested lives on its own branch and never touches anything shared until it is.** This changes how
you should think about scope: there is no cutting, no "stretch vs priority" triage in this document.
Build what you can, in whatever order makes sense to you, and each piece proves itself independently
before it goes anywhere near `phase2-tscast-nio` or `main`.

## THE BRANCH-BASE CORRECTION — get this right or you build on stale code

**[VERIFIED, checked live this session] `main` in a fresh checkout of this repo is a STALE Phase-1
snapshot** — `docs/PROJECT_RECORD.md` (compiled 2026-09-05 on the `phase2-tscast-nio` branch)
records `origin/main` as 186 commits behind `phase2-tscast-nio`. `src/phase2/` happens to exist on
`main` too in some checkouts, which makes this easy to miss — but it is pre-freeze code, missing
nine feature subsystems (collocation, 3-D cube, calibrated uncertainty, physics/OHC, event
detection, validation lab, wind input, cyclone heat, Argo overlay) that only exist on
`phase2-tscast-nio`.

**Every branch below forks from `phase2-tscast-nio`, never from `main`.**

```
git fetch origin
git checkout phase2-tscast-nio && git pull
git checkout -b <feature-branch-name>
```

Branch names use a **HYPHEN**: `phase2-viz-transect`. Git refuses `phase2/anything` while a branch
named `phase2` exists — hard failure, not style.

## THE GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

Read-only, no exceptions: `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, the baseline
`tests/`. **Import from them. Never edit them.**

## OWNERSHIP

You own: `src/phase2/` (`physics/`, `derived/`, `cube/`, `validation/`, `train/`), and **new files
you add** to `app/phase2/` and `tests/phase2/`.

**Off limits (Darshan's F1, read+import only):** `src/phase2/data/collocation.py`,
`app/phase2/collocation_page.py`. Post an ASK in AGENT_SYNC if either needs a fix.

---

## THE CROSS-CUTTING REQUIREMENT — every page ends in a "Formula & How to Read This" footer

Darshan wants every feature explained **on the page itself**: what it shows, the exact formula, and
how to read it — for a judge or scientist who opens the page cold. **This is not a new UI pattern —
generalize one that already exists.** `app/phase2/validation_page.py` already ends in
`st.expander` blocks under *"5 · What this model is not good at"* (`PROJECT_RECORD.md` §4.4,
confirmed by reading the file this session). Every page below — new AND the 9 existing ones — gets
the same shape at the bottom. Write one shared helper, e.g. in a new small module
`src/phase2/viz_explainer.py`:

```python
def render_explainer(title: str, formula: str, plain: str, how_to_read: str,
                     caveats: list[str] | None = None) -> None:
    """Standard end-of-page block. `formula` is a raw LaTeX string for st.latex.
    Call this LAST on every phase2 page, new or existing."""
    st.divider()
    st.subheader(f"About this panel — {title}")
    if formula:
        st.latex(formula)
    st.markdown(plain)
    st.markdown(f"**How to read it:** {how_to_read}")
    if caveats:
        with st.expander("Caveats and limitations"):
            for c in caveats:
                st.markdown(f"- {c}")
```

Every feature section below gives you the exact `formula` / `plain` / `how_to_read` text to pass in.
Use it close to verbatim — it has been written carefully so a non-specialist judge can follow it.

---

## WHAT ALREADY EXISTS — the reuse table (do not rebuild any of this)

The linchpin, feeds almost everything below:
```python
from phase2.tscast_nio.field import predict_field
from phase2.tscast_nio.inference import TSCastPredictor
field = predict_field(TSCastPredictor(), "2026-05-15")
# field["temperature"] (100,240,15) °C, field["sigma"] (100,240,15) CALIBRATED,
# field["valid_mask"], field["land_mask"], field["provenance"]
```
Never re-read `data/processed/grids.npz` for the model field — that's training-era GLORYS, not the
shipped reconstruction.

| You need | Reuse | Where |
|---|---|---|
| Depth-vs-distance section | `sample_transect(track, field)` → `{temperature,sigma (n,15), lat,lon,distance_km,depths}` | `src/phase2/derived/transect.py` |
| Track between 2 points, isotherm-generic contour line | `track_points(...)`, `isotherm_line(section, threshold_c)` — **feed it a σθ section instead of T and it draws isopycnals for free** | same |
| NaN-strict sampling, no grid-snap staircase | `bilinear_at(field_2d,lat,lon,lat_grid,lon_grid)` | same |
| Density / σθ (EOS-80) | `density(S,θ)`, `sigma_theta(S,θ)` | `src/phase2/physics/seawater.py` |
| MLD / ILD / barrier / thermocline | `mixed_layer_depth`, `thermocline`, … | `src/phase2/physics/layers.py` |
| **TCHP / OHC / D26 — already built, reuse as-is** | `heat_content_field(field) → {tchp, ohc_0_zref, d26}`, `integrated_uncertainty(...)` | `src/phase2/derived/heat_content.py`, rendered at `app/phase2/cyclone_heat_page.py` (port 8509) |
| Model vs nearby Argo | `overlay(lat,lon,date) → {model, floats, per_depth}`, `two_sigma_band` | `src/phase2/validation/argo_overlay.py` |
| Per-depth RMSE/bias/corr scoring | the functions behind `metrics.py` / `eval_argo.py` — reuse for the OMNI/RAMA time-axis validation too | `src/phase2/tscast_nio/metrics.py` |
| GLORYS reference T + companion salinity | `CollocationEngine(...).collocate(lat,lon,dt)` → `sources["glorys"].temperature_profile`, `sources["subsurface"].salinity_profile` | `src/phase2/data/collocation.py` (import only) |
| 3-D slicing / Plotly volume | `OceanCube.reconstruct(date)`, `.depth_slice`, `.section`, `.profile`; `cube/volume.py` | `src/phase2/cube/` |
| Eddy detection (Okubo-Weiss, from u,v) | `okubo_weiss(u,v)`, `detect_eddies(u,v,...)` | `src/phase2/events/eddy.py` |
| Existing observation-priority v1 (prior art, framed "not novel") | `products/observation_priority.py` | `src/oceanembed/` (Phase-1, read-only — import, don't edit) |
| Arabian Sea / Bay of Bengal partition | `grid_masks()`, `classify_points()` | `src/phase2/basins.py` |
| Page template + port registry | every `app/phase2/*.py` file; ports enforced by `tests/phase2/test_launch_ports.py` | — |

## WHAT DOES NOT EXIST — net-new, build and TEST it, never assume it works

- **Sound-speed function.** Nowhere in the repo. You write it once (Mackenzie 1981, formula below),
  it's shared by the transect and acoustics branches.
- **Full-map isopycnal contouring.** Section-level is free (`isotherm_line` on a σθ section); a
  2-D map contour is new if a panel needs it.
- **EKE / geostrophic-current-from-SSH.** Surface currents exist only as model *input* (u,v). If you
  compute EKE from those directly, label it as derived from model input, not an independent
  observation.
- **Cyclone track data.** Not in the repo. Needs an IBTrACS CSV or one hardcoded case study.
- **OMNI/RAMA buoy data.** Not in the repo. `docs/INCOIS_PROBE.md` already probed the INCOIS LAS
  server for gridded Argo and found the catalogue reachable but the data-materialization backend
  down — OMNI/RAMA may live in a different category of that same catalogue and deserves its own
  probe before assuming it's equally blocked.
- **Cloud-mask / sensor-dropout stress test.** No masking code anywhere.
- **Gradient-preserving / static-stability loss terms.** [VERIFIED — grepped `train_stage1.py`/
  `train_stage2.py` this session] Only `gaussian_nll` (β-NLL, eq. 3/4) and `density_nll` (eq. 5,
  stage 2 only, a *consistency* loss between predicted density and EOS-80 of predicted T,S) exist.
  Neither is a vertical-gradient loss or a monotonicity/stability penalty. Both are new.
- MC-dropout σ (`src/oceanembed/inference/uncertainty.py`) is uncalibrated and overconfident at
  depth (D-016). **Any uncertainty visualization must use the calibrated Phase-2 `predict_field`
  sigma, never MC-dropout.**

---

## THE 9 FEATURES

Each is its own branch, forked from `phase2-tscast-nio`, independently tested, never merged until
Darshan says so.

### 1 · `phase2-viz-clickmap` — port 8511 — interactive click-any-pixel → profile

**Goal:** the flagship demo tool. *"Give me a lat/lon and I'll show you the predicted thermocline
right now."*

**Build:** Altair `mark_rect` depth-slice map (temperature at a chosen depth from `predict_field`),
with `st.altair_chart(chart, on_select="rerun")` selection. A clicked cell populates a side panel
with that cell's vertical temperature profile + calibrated ±2σ band (`two_sigma_band`). Optional
current-vector overlay from input u,v, explicitly labeled "model input, not a derived diagnostic."
Degrade to lat/lon `number_input` if selection events misbehave (the pattern `cyclone_heat_page.py`
already uses for its point-inspector).

Fetch current Altair/Streamlit selection-API docs via Context7 before coding.

**Footer:** `formula=""` (no formula, it's a UI feature). `plain`: "This map shows the model's
predicted temperature at one depth, everywhere in the basin — not just where an Argo float happens
to be. Click any point to see the full vertical profile the model predicts there, with its
uncertainty band." `how_to_read`: "A tight ±2σ band means the model is confident; a wide one means
trust it less — cross-check with the uncertainty map (feature 3)."

**Acceptance check:** a click at a known ocean point returns a finite 15-depth profile; a click on
land shows an explicit "no ocean here" message, never a blank chart.

---

### 2 · `phase2-viz-transect` — port 8510 — vertical cross-sections, upgraded

**Note on the port:** 8510 is already claimed by Darshan's pending transect commit (`4a1dc9b`,
currently on `origin/main`, not yet merged into `phase2-tscast-nio`). Pull that commit in first —
`transect.py` and `transect_page.py` already exist and work (section heatmap + 20/26 °C isotherms);
you are extending them, not starting fresh.

**Build, in this order (each independently shippable):**

1. **Model vs GLORYS vs Argo section** — the physics-proof panel, and the safest (temperature-only,
   no salinity needed). Draw model T and GLORYS T sections side by side along the same track;
   scatter nearby Argo floats as dots colored by model−float error. Reuse `argo_overlay` and the
   collocation GLORYS profiles.
2. **Sliding slice** — a slider that sweeps the transect line east–west, holding its shape. Pure UI
   over `track_points` + `sample_transect`.
3. **Isopycnal overlay** — σθ along the track from **companion salinity** (GLORYS, via collocation —
   see the honesty rule below), drawn via `isotherm_line(sigma_theta_section, threshold=...)`.
4. **Sound-speed contours** — the new Mackenzie function (below), computed on the same companion
   salinity + predicted temperature.

**THE COMPANION-SALINITY HONESTY RULE:** the deliverable predicts temperature only. Isopycnals and
sound speed both need salinity, which does not exist in this model's output. Compute both from
**GLORYS salinity** (via `CollocationEngine`), and **label it in the UI**: *"Density and sound speed
use GLORYS salinity as a companion field — the satellite deliverable predicts temperature only."*
This is not a footnote to bury; it is what makes the panel defensible.

**Footer for isopycnals:** `formula = r"\sigma_\theta = \rho(S,\theta) - 1000"`. `plain`: "Lines of
constant density (isopycnals) show where water of the same weight sits. Where they bunch together
and slope steeply, two different water masses are meeting — that's a front." `how_to_read`: "Flat,
widely-spaced lines = well-mixed water. Steep, closely-packed lines = a sharp boundary."

**Footer for sound speed:** `formula = r"c(T,S,z) \approx 1448.96 + 4.591T - 0.05304T^2 + 2.374\times10^{-4}T^3 + 1.340(S-35) + 1.630\times10^{-2}z + 1.675\times10^{-7}z^2 - 1.025\times10^{-2}T(S-35) - 7.139\times10^{-13}Tz^3"`
(Mackenzie 1981, 9-term). `plain`: "Sound travels faster in warmer, saltier, and deeper (higher-
pressure) water. This converts the temperature and salinity at each depth into how fast sound moves
there, in metres per second." `how_to_read`: "Contour lines bunched together mean sound speed is
changing fast with depth — that's where sound waves bend (refract)."
`caveats=["Uses GLORYS companion salinity, not the satellite deliverable's own output."]`

**Acceptance check:** `c(35, 25, 1000) ≈ 1550.744 m/s` to <0.05 m/s — the Mackenzie canonical check
value. If your function doesn't reproduce it, it's wrong; don't ship it.

---

### 3 · `phase2-viz-uncertainty` — port 8512 — uncertainty as transparency

**Build:** one `mark_rect` map at a chosen depth: temperature → color (`turbo`), **calibrated**
sigma → opacity. `predict_field` already returns the 2-D sigma, so this is mostly an Altair
`opacity` encoding plus a legend explaining the double encoding.

**Footer:** `formula = r"\alpha \propto 1/\sigma_{\beta\text{-NLL}}(x,y)"`. `plain`: "Color shows the
predicted temperature. Transparency shows how confident the model is — vivid means confident, faded
means uncertain (often in dynamic eddies or under heavy cloud cover)." `how_to_read`: "Don't trust a
faded region's exact number; it's a hint about *where* the model is guessing, not a value to quote."
`caveats=["Uses the calibrated Phase-2 sigma. Never substitute the Phase-1 MC-dropout spread — it was measured overconfident by 1.6-3.5x (D-016)."]`

**Acceptance check:** sigma range at the rendered depth is finite and within the calibration
artifact's known range (see `artifacts/uncertainty_calibration.json` scale factors, ~0.89–1.46).

---

### 4 · `phase2-viz-tchp3d` — port 8513 — 3-D TCHP + real cyclone case studies

**This absorbs BOTH Strategy 4 (3-D volumetric tracker) and half of novelty vector 2 (event case
studies) — build them together, they need the same track data.**

**What's already done, reuse verbatim:** TCHP/OHC/D26 math (`heat_content_field`), the 2-D
dashboard (`cyclone_heat_page.py`, port 8509). **Do not recompute or re-derive any of this.**

**What's new:**
1. **Cyclone track data.** Resolve this FIRST — it's a hard dependency for everything else in this
   feature. Options: an IBTrACS CSV (public, has track + intensity for named storms), or one
   hardcoded case study (Cyclone Biparjoy or Mocha — pick one with a track that crosses your data
   window, 2025-06-01 to 2026-06-23). If neither is available, say so in AGENT_SYNC before building
   further — don't fabricate a track.
2. **Before/during/after case study view.** TCHP maps at 3 dates bracketing the storm's peak
   intensification, side by side, showing the subsurface heat reservoir depleting as the storm
   passes over it.
3. **3-D volumetric render.** Plotly `go.Volume` (reuse `cube/volume.py` — **mind the `.tolist()`
   trap**: Plotly ≥6 serializes numpy as base64 that Streamlit's bundled plotly.js can't decode,
   giving an empty box). Show TCHP-anomaly as a semi-transparent volume, the cyclone track overlaid,
   Argo floats scattered and colored by RMSE. Depth exaggeration so it isn't flat. Degrade to the
   existing 2-D TCHP map if the 3-D render fails or is slow, exactly like `cube_page.py` does.

**Footer:** `formula = r"\text{TCHP} = \rho c_p \int_0^{D_{26}} (T(z) - 26)\, dz"`. `plain`: "This is
the heat energy stored in water warm enough to fuel a cyclone's rapid intensification — literally
the fuel reservoir under the storm." `how_to_read`: "Bright/dense regions are where a storm passing
overhead could intensify fast. Watch the volume shrink as the case-study track crosses it — that's
the storm using up the fuel."
`caveats=["TCHP integrates temperature only, from the satellite deliverable; D26 uses the same field."]`

**Acceptance check:** the before/during/after TCHP maps show a measurable decrease along the track
(if they don't, say so honestly rather than picking a different storm to make the story work).

---

### 5 · `phase2-novelty-physics-loss` — no new port, extends `physics_page.py` (8505)

**Goal:** penalize the model for producing an unphysical, over-smoothed, or unstable profile — not
just for being wrong on average.

**Build:** two new loss terms added to `train_stage1.py`/`train_stage2.py`, each behind its own
`--w-` flag (following the existing `--w-density` pattern from stage 2, which lets eq. 5 be
ablated) so the effect is measurable, not just added:

- **Gradient-preserving loss:** penalize error in the *vertical derivative* of temperature, not
  just the value.
  `formula = r"L_{grad} = \text{mean}\left[\left(\frac{\partial \hat T}{\partial z} - \frac{\partial T}{\partial z}\right)^2\right]"`,
  computed as finite differences between adjacent `config.DEPTHS` levels on both predicted and true
  profiles. `plain`: "Getting the average temperature right isn't enough — a model can hit the right
  numbers while smearing a sharp thermocline into a gentle slope. This term punishes exactly that."
- **Static stability penalty:** penalize a predicted profile where density *decreases* with depth
  (physically impossible in a resting water column — it would immediately overturn).
  `formula = r"L_{stab} = \text{mean}\left[\text{ReLU}\left(-\frac{\partial \hat\rho}{\partial z}\right)\right]"`,
  using `seawater.density_torch` (already differentiable, already used by the eq. 5 density loss) on
  the predicted profile. `plain`: "In a stable ocean, water gets denser as you go down. If the model
  predicts a spot where lighter water sits below heavier water, that's not a subtle error — it's
  physically impossible, and this term says so directly."

**CRITICAL: this produces NEW checkpoints. It never touches `tscast_stage1.pt`, the frozen
deliverable.** Train with `--w-grad 0 --w-stab 0` to exactly reproduce the current model as a
sanity check, then sweep both weights up from zero the same way `--w-density` was ablated for eq. 5.
**Given the project's own history (`--w-density` ON cost accuracy, 0.8593 vs 0.8548 — see
`PROJECT_RECORD.md §6.1`), do not assume these terms help. Measure it, on at least 3 seeds before
believing a sign, exactly like every other effect in this project.**

Add a small "physical consistency" section to `physics_page.py`: for the current frozen model vs.
your new gradient/stability-trained variant, show % of profiles with a static-instability violation,
and mean gradient error at the thermocline (75–125 m).

**Acceptance check:** `--w-grad 0 --w-stab 0` reproduces the frozen model's RMSE to within float
noise (<0.001 °C) — proves the new loss terms are truly additive, not silently changing anything
else.

---

### 6 · `phase2-novelty-buoy-validation` — port 8514 — OMNI/RAMA time-axis validation

**Goal:** Argo floats drift and sample every 5–10 days; INCOIS's own moored buoys (OMNI network,
co-maintained RAMA array) sample fixed locations every few hours. Validating against them proves the
model tracks *time*, not just *space* — something Argo genuinely cannot check.

**Step 1, before writing any validation code: probe for the data.** `docs/INCOIS_PROBE.md` already
established the INCOIS LAS catalogue (`las.incois.gov.in`) is reachable and lists 13 categories, the
first being *ARGO DATA PRODUCTS*. **Check the other 12 categories for OMNI/RAMA** using the same
probe pattern as `scripts/phase2/probe_incois_las.py` (`getCategories.do`, `getDatasets.do`) before
assuming it's blocked the same way Argo's data layer was — it may be a different backend. **Fallback
if INCOIS's own portal is unreachable:** NOAA PMEL hosts public RAMA mooring data (Global Tropical
Moored Buoy Array project) — a legitimate, public, alternate source, the same kind of documented
deviation the team already used for Argo (argopy instead of INCOIS LAS). Document whichever source
you end up using, and why, the same way `docs/INCOIS_PROBE.md` does.

**Build:** once you have a buoy time series (T, and S if available) at a handful of fixed
coordinates:
1. Extract the model's predicted time series at those exact coordinates across your full data window
   (2025-06-01 to 2026-06-23) via repeated `predict_field` calls or `OceanCube.profile(lat,lon)`.
2. Score with the existing RMSE/bias/correlation functions (`metrics.py`) — same math as Argo
   validation, applied along a **time axis at one point** instead of across scattered points.
3. **Intra-seasonal tracking check:** band-pass filter both series to the ~30–90 day band
   (Butterworth filter, `scipy.signal`) and correlate — this is the MJO/intra-seasonal-oscillation
   band. This is new signal-processing code; there's no existing function to reuse for the filter
   itself, only for the RMSE/correlation once filtered.

**Footer:** `formula = ""` (methodology, not a single equation). `plain`: "Argo floats drift and only
revisit a spot every 5-10 days, so they can't say whether the model tracks *changes over time* at
one location. INCOIS's own moored buoys sit still and sample every few hours — this compares the
model's daily prediction at that fixed spot against what the buoy actually measured, day by day."
`how_to_read`: "A high correlation on the filtered (30-90 day) signal means the model is catching
slow seasonal swings, like monsoon-driven cooling, not just the daily average temperature."

**Acceptance check:** the buoy data source is real (never synthesized) and its provenance (URL,
fetch date, station coordinates) is recorded in the output artifact, the same way every other data
source in this project stamps its provenance.

---

### 7 · `phase2-novelty-acoustics` — port 8515 — sound speed profiles, SLD, SOFAR axis

**Reuses the Mackenzie sound-speed function from feature 2** — build it once, in
`src/phase2/physics/seawater.py` (alongside `density`, `sigma_theta` — same module, same EOS-80
one-atmosphere convention), and import it from both branches. If you build feature 2 first, this
branch just imports; if this branch comes first, feature 2 imports from here instead. Coordinate via
AGENT_SYNC so it's written exactly once.

**Build (this is the naval-acoustics / operational diagnostic, distinct from feature 2's transect
contours — this is a dedicated page with full-map products):**
- **Sound-speed profile (SSP)** at any clicked point (reuse the click-map pattern from feature 1).
- **Sonic Layer Depth (SLD):** the depth of the local sound-speed maximum in the near-surface layer
  — analogous to MLD but for acoustics.
- **SOFAR channel axis:** the depth of the sound-speed *minimum* below the SLD — the "waveguide"
  where sound travels thousands of km with minimal loss (this is what lets whale calls and naval
  sonar signals propagate so far).
- A full-basin map of SLD at one date, so an operator can see where the surface duct is deep
  (favorable for near-surface sonar) vs shallow.

**Footer for SSP:** same Mackenzie formula as feature 2.

**Footer for SLD/SOFAR:** `formula = ""`. `plain`: "Sound speed usually falls with temperature near
the surface, then rises again with pressure at depth — this creates a speed *minimum*. Above that
minimum, sound gets trapped near the surface (the Sonic Layer); the minimum itself is the SOFAR
channel axis, a natural sound conduit that spans ocean basins." `how_to_read`: "A deep SLD means
sound stays trapped near the surface longer — relevant for surface-ship sonar performance and
detecting near-surface targets."
`caveats=["Uses GLORYS companion salinity, same honesty rule as feature 2."]`

**Acceptance check:** same Mackenzie 1550.744 m/s check value as feature 2; SLD/SOFAR depths must be
monotonically consistent (SOFAR axis depth ≥ SLD on every valid profile — assert this in a test).

---

### 8 · `phase2-novelty-cloud-dropout` — port 8516 — monsoon cloud-cover stress test

**Goal:** IR satellite SST cannot see through monsoon cloud cover. Quantify how badly the model
degrades when SST is missing, and whether SSH + wind carry enough signal to compensate.

**RESOLVE THIS FIRST, before writing the stress-test harness — it's an open engineering question,
not an assumption:** does `TSCastNIO`'s CNN encoder tolerate NaN/missing input at all? Check
`models/tscast.py` and `dataset.py`. If the encoder was never built to handle missing pixels,
"masking" at inference means **filling with climatology, not true NaN** — feeding real NaN into a
conv net that never saw NaN in training will likely just break, not degrade gracefully. Write down
which case you're in before proceeding.

**Build, cheap version first (no retraining, safe, reuses an existing harness pattern):**
1. Take a real satellite SST field. Randomly mask 30/50/70% of ocean pixels (climatology-fill or
   true NaN, per the finding above).
2. Run inference, score against the same Argo floats used for the real headline.
3. Plot RMSE degradation vs. mask percentage — a graceful-degradation curve.

This mirrors `scripts/phase2/run_sat_ablations.py`'s 3-seed-per-leg pattern (masking percentage
takes the place of "which channel is dropped").

**Stretch, if you want the more rigorous version:** train a mask-augmented variant (SST randomly
masked during training too, so the model learns to lean on SSH/wind when SST is missing) and compare
its degradation curve against the un-augmented model's. This is a new training leg — same rule as
feature 5: new checkpoint, never touches the frozen deliverable, 3 seeds before believing a sign.

**Footer:** `formula = ""`. `plain`: "During the monsoon, thick cloud cover blinds infrared satellite
sensors, so the model sometimes has to work with incomplete surface data. This test artificially
blanks out part of the SST input and measures how much the prediction degrades — a preview of how
the model would perform during a real cloudy month." `how_to_read`: "A shallow slope (RMSE barely
rising as more SST goes missing) means the model leans on other channels (SSH, wind) and degrades
gracefully. A steep slope means SST is doing most of the work and the model would struggle in heavy
monsoon cloud."

**Acceptance check:** the 0%-masked case reproduces the real headline RMSE (0.9078 °C) — that's your
control, proving the harness itself isn't introducing error before you even start masking.

---

### 9 · `phase2-novelty-eke-priority` — port 8517 — uncertainty × EKE observation-priority v2

**Read `docs/NOVELTY_MATRIX.md` before building this.** The project's own literature review already
concluded that "anomaly × uncertainty × sparsity" observation-priority is **not a novel idea** —
it's a simplified heuristic version of a published, formally-optimized research area (JTECH 2023,
Gumbel-Softmax sensor placement). **Keep that framing.** This feature is a refinement of an existing
honest heuristic, not a new capability claim. Never say "the AI tells INCOIS where to deploy floats"
— the required phrasing, already established: *"regions where additional observations may provide
high scientific value."*

**Build:** replace v1's sparsity factor with **EKE** (eddy kinetic energy), computed from the
u,v model-input currents:
`formula = r"EKE = \tfrac{1}{2}(u'^2 + v'^2)"`, where `u', v'` are the eddy/anomaly component of
velocity (deviation from a time-mean or low-pass-filtered current — reuse the finite-difference
primitives in `events/_metric.py` if useful, and `events/eddy.py`'s Okubo-Weiss machinery already
works with the same u,v arrays). Then:
`formula = r"\text{Priority}(x,y) = \sigma_{\beta\text{-NLL}}(x,y) \times EKE(x,y)"`.

**Footer:** `plain`: "This combines two things: how uncertain the model is at a point, and how
dynamically active the ocean is there (EKE — high in eddies and jets, low in calm water). Multiplying
them flags places that are BOTH turbulent AND poorly predicted — exactly where a physical
observation would teach the model the most." `how_to_read`: "High priority doesn't mean 'the ocean
is doing something important here' — it means 'we genuinely don't know what's happening here, and it
looks dynamic enough to matter.'"
`caveats=["This is a heuristic, not a formally optimized observing-system design — see docs/NOVELTY_MATRIX.md.", "EKE here is computed from model INPUT currents (u,v), not an independent observation."]`

**Acceptance check:** restrict ranking to cells passing `valid_mask` (v1 had a bug ranking the
Persian Gulf at ~20 m depth as top priority — don't repeat it).

---

## WORKFLOW PER FEATURE — follow every step, every branch

1. `git fetch origin`, checkout `phase2-tscast-nio`, pull, branch from there with a hyphenated name.
2. Research first. **Context7** for current library docs (Altair selection API, Streamlit
   `on_select`, Plotly volume, scipy.signal for the Butterworth filter) before coding.
3. Build the smallest working version.
4. Write real tests under `tests/phase2/`. **Do NOT create `tests/phase2/__init__.py`** — it shadows
   the `src/phase2` package and breaks imports under pytest. Delete it if it appears.
5. Run the FULL suite: `PYTHONPATH=src python -m pytest -q`. Everything must pass, not just yours.
6. Real-data smoke test, inspect the actual numbers — passing tests are not correct science.
7. Add a feature-specific check to `scripts/phase2/accept.py`.
8. Register the new port in `.claude/launch.json` and `docs/HANDOFF.md`'s port table.
9. Commit only after tests pass (`git commit -F -` with a heredoc — backticks in `-m` get
   command-substituted by bash and silently delete text). **Push the feature branch only. Never
   push, merge, or rebase `main` or `phase2-tscast-nio`.**
10. Append to `docs/phase2/AGENT_SYNC.md`, tagged `[ARJHUN]`, with evidence tags, the branch name,
    and the one command Darshan runs to test it.

## TRAPS THAT HAVE ALREADY COST THIS PROJECT HOURS

- `tests/phase2/__init__.py` breaks imports under pytest. Never create it.
- Branch `phase2/x` fails while branch `phase2` exists. Use `phase2-x`.
- `st.cache_data` silently drops any argument whose name starts with `_`.
- Altair v6 refuses frames >5000 rows: call `alt.data_transformers.disable_max_rows()`.
- Plotly ≥6 + Streamlit: pass `.tolist()`, not numpy, into `go.Volume`/`go.Scatter3d`.
- On Windows, Streamlit runs as `python.exe` — `ps | grep streamlit` finds nothing. Use
  `netstat -ano | grep :PORT` then `taskkill //PID <pid> //F`.
- Never let a bare expression sit in Streamlit code — magic renders its return value.
- Sample tracks via `bilinear_at`, never repeated `reconstruct()` (grid-snap staircase). Land /
  seafloor is always a **gap**, never a smoothed blend.
- This project's own history: an unweighted physics loss term was ADDED once (eq. 5 density
  constraint) and MEASURED to cost accuracy (0.8593 vs 0.8548). Do not assume a physics term helps.
  Ablate it with a flag, measure on 3 seeds, believe only what survives a reseed (see
  `PROJECT_RECORD.md §12.6` for a worked example of a claim that did NOT survive a reseed).

## HONESTY RULES

Tag every claim **[VERIFIED]**, **[INFERRED]**, or **[UNKNOWN]**. Never claim code works unless you
executed it. Never fabricate a metric, a cyclone track, or a buoy reading. Keep 0.9078 (deliverable)
and 0.8548 (comparator) distinct always. If anything in this spec looks wrong to you, say so before
building — being challenged by the other agent is the point.

## FIRST REPLY — do not write code yet

Reply with:
1. Which feature you start with, and why.
2. Anything in this spec you think is wrong — especially the companion-salinity approach, the
   Mackenzie sound-speed formula, and the gradient/stability loss design.
3. Whether you already know a public source for cyclone tracks (feature 4) or OMNI/RAMA data
   (feature 6) — if not, flag both as needing a probe before that feature can really start.
