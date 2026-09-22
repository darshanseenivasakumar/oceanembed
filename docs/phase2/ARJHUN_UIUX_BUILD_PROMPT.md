# BUILD PROMPT — OceanEmbed UI/UX overhaul ("Deep Ocean Instrument")

> Paste this whole file as your first message to Claude in `D:\sih project\oceanembed`.
> Owner: Arjhun. Written 2026-09-06. Ship window: ~1 working day (deadline 7 Sep 2026).

---

## 0. Read this first

You are upgrading the **user interface** of OceanEmbed (SIH26066 — subsurface ocean temperature
reconstruction for the North Indian Ocean). The science is **done and frozen**. You are not
retraining anything, not changing any number, not touching any model.

Before you write a single line:
1. Read `CLAUDE.md` (the operating constitution — evidence tags, real-data-only rule, file ownership).
2. Read `PROJECT_OVERVIEW.md` section 3 (what exists today).
3. Read `docs/phase2/data-model.md` and `src/phase2/cube/ocean_cube.py` (the data you will draw).
4. Run `python -c "import streamlit, plotly, altair; print('ok')"` and report what is actually installed.

Then follow the engineering loop in `CLAUDE.md`: UNDERSTAND -> INSPECT -> PLAN -> smallest working
version -> TEST -> real-data smoke test -> inspect output -> DOCUMENT -> COMMIT.

---

## 1. The problem with the UI today

There are **10 separate Streamlit apps on 10 separate ports**:

| Port | File | Page |
|---|---|---|
| 8501 | `app/streamlit_app.py` | main demo (**FROZEN — DO NOT EDIT**) |
| 8502 | `app/phase2/collocation_page.py` | collocation |
| 8503 | `app/phase2/validation_page.py` | validation |
| 8504 | `app/phase2/cube_page.py` | 3-D cube |
| 8505 | `app/phase2/physics_page.py` | physics (MLD / thermocline / barrier layer) |
| 8506 | `app/phase2/events_page.py` | events (eddies, upwelling, fronts) |
| 8507 | `app/phase2/tscast_page.py` | TS-Cast v2 reconstruction |
| 8508 | `app/phase2/validate_page.py` | validation lab |
| 8509 | `app/phase2/cyclone_heat_page.py` | cyclone heat (TCHP / OHC) |
| 8510 | `app/phase2/transect_page.py` | depth-vs-distance transect |

A judge cannot be asked to open ten browser tabs. It reads as ten prototypes, not one product.
Everything works — it just does not **look** like it works.

**Goal: one application, one visual language, one unforgettable 3-D moment.**

---

## 2. Hard constraints — violating any of these fails the task

1. **`app/streamlit_app.py` and `app/panels/` are FROZEN.** Tagged `v1.0.1-demo-aug30`, they passed
   the screening gate. Do not edit, do not refactor, do not import-and-monkeypatch. Port 8501 must
   still run byte-identically after your work.
2. **Real-data-only.** Every number on screen must come from a real artifact under `artifacts/` or a
   real model run. No placeholder numbers, no lorem, no "0.85" typed by hand. Cached results are
   allowed **only** if the real model produced them, and must be visibly labelled `CACHED` vs `LIVE`.
3. **No new science.** You are not allowed to recompute a metric in the UI. Read
   `artifacts/argo_error_by_depth.json`, `artifacts/provenance.json`, etc. If a number is not in an
   artifact, it does not go on screen.
4. **Graceful degradation is a requirement, not a nicety.** Read the comment block at the top of
   `app/phase2/cube_page.py`. A page that ImportErrors on demo day is worse than a plainer chart.
   Every renderer needs a fallback ladder (section 6.6).
5. **Existing tests must still pass.** `python -m pytest tests -q` — 530+ tests. Run it before you
   start (record the number) and again at the end.
6. **New code lives in new files** under `app/ui/`. Existing `app/phase2/*_page.py` files may be
   modified only to (a) import the shared theme and (b) drop their `st.set_page_config` call when
   they become sub-pages. Nothing else.
7. **Windows.** Paths, no bash-only chaining, system Python 3.12 (there is no `.venv`).

---

## 3. Visual identity — "Deep Ocean Instrument"

The reference feel: a NASA/ESA mission console crossed with Linear's restraint. Dark, precise,
quiet, dense with real information. **Not** a startup landing page. **Not** a dashboard template.

### 3.1 Color tokens (put these in ONE file — `app/ui/theme.py` — and import everywhere)

```
# ground
abyss        #060B14   page background
deep         #0D1526   card / panel surface
shelf        #141F35   elevated surface, hover
edge         #1E2C47   1px borders

# ink
ink          #E6EDF7   primary text
ink-dim      #8B9BB4   secondary text, labels, captions
ink-faint    #56657F   axis ticks, disabled

# signal (max TWO accents visible on any one screen)
cyan         #22D3EE   primary accent: satellite / live / interactive
azure        #38BDF8   secondary accent: selection, focus ring
amber        #FB923C   attention: uncertainty, caveats
mint         #34D399   pass / verified
coral        #F87171   fail / error / high anomaly
```

### 3.2 Scientific colormaps — non-negotiable

- **Temperature** -> `cmocean.thermal` (or Plotly `Thermal`). Sequential.
- **Anomaly** -> the diverging blue-to-pale-to-purple scale **already defined** in
  `app/phase2/cube_page.py` as `BLUE_PURPLE_DIVERGING`. Import it, do not redefine it. The pale
  midpoint MUST be pinned to zero (`cmid=0`).
- **Uncertainty** -> `magma` or `viridis`. Sequential.
- **Never** `jet`, `rainbow`, or `hsv`. A rainbow colormap on ocean data tells a domain judge you
  do not read papers.
- Every colorbar carries **units** and a **fixed range across dates**, so the animation does not
  lie by rescaling every frame.

### 3.3 Typography

- UI: **Inter** (fallback `-apple-system, Segoe UI, sans-serif`).
- Numbers, coordinates, metrics, code: **JetBrains Mono** or **IBM Plex Mono**.
- **All numeric displays use tabular figures** (`font-variant-numeric: tabular-nums`). Digits that
  jitter as a date scrubs is the cheapest tell of an amateur dashboard.
- Scale: 32 / 24 / 18 / 15 / 13 / 11 px. Body 15px. Nothing below 13px — this is projected in a hall.
- Metric tiles: 32px mono, weight 500, `-0.02em` letter-spacing.

### 3.4 Space, shape, depth

- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48. Nothing off-scale.
- Radius: 10px cards, 6px controls, 999px pills.
- **No drop shadows.** Depth comes from 1px `edge` borders and a one-step background lift
  (`deep` -> `shelf`). Shadows on a dark theme look like smudges.
- No glassmorphism, no gradient text, no glow except the single 3-D isosurface (section 6.4).

---

## 4. Information architecture — one app, five acts

Build a **single Streamlit multipage app** at `app/ui/main.py` (run on port **8500**, so the frozen
8501 demo keeps working side by side). Use `st.navigation` / `st.Page` (Streamlit >= 1.36 — **verify
the installed version with Context7 before writing the nav code**; if it is older, fall back to the
`pages/` directory convention).

Structure the nav as a **narrative**, not an inventory:

```
OVERVIEW      - The Result            headline metrics, what we built, one hero visual
SEE IT        - 3-D Ocean          *  the money shot (section 6)
              - Depth Slices          map at a chosen depth, source toggle
              - Transect              depth-vs-distance cross-section
PROVE IT      - Validation vs Argo    RMSE/bias/corr per depth, 962 floats
              - Validation Lab        our error vs inherited GLORYS error
              - Collocation           how a grid cell is matched to a float
USE IT        - Cyclone Heat          TCHP, 26C isotherm depth, OHC
              - Physics               MLD, thermocline, barrier layer
              - Events                eddies, upwelling, fronts
              - Observation Priority  where to send the next float
UNDER IT      - Provenance & Audit    checksums, code commit, data bundle, poison test
```

Every existing page becomes one entry. **Nothing is deleted.** Wrap, do not rewrite.

### 4.1 Persistent chrome (present on every page)

- **Top bar**: `OCEANEMBED` wordmark, `SIH26066` chip, **date scrubber**, **source segmented
  control** `SATELLITE | GLORYS`, a `LIVE`/`CACHED` badge, a `?` shortcuts button.
- The date and source live in `st.session_state` and are **shared across all pages**. Switching page
  must not reset them. This is the single biggest UX win available and it is cheap.
- **Left rail**: the nav above, grouped by act, collapsible, current page marked with a 2px cyan
  left border (not a background fill).
- **Right inspector** (collapsible, default open on map pages): whatever cell the user last
  hovered or clicked — lat/lon, seafloor depth, the full 15-depth profile sparkline, model sigma,
  anomaly, nearest Argo float and its distance in km.

### 4.2 Source toggle must be honest

The satellite leg (**0.9078 degC**) is the deliverable. GLORYS (0.8789 / 0.8548) is a **comparator**.
When the user switches to GLORYS the UI must show an inline note: *"Reanalysis input — an upper-bound
comparator, not the problem-statement deliverable."* Do not let a judge screenshot 0.8548 thinking it
is the headline. This honesty is a scoring feature, not a disclaimer.

---

## 5. Component kit — build these once in `app/ui/components.py`

1. **`metric_tile(label, value, unit, delta=None, provenance=None)`**
   Big mono number, small unit, dim label above, optional delta chip, provenance chip below.
2. **`provenance_chip(kind)`** — a pill: `LIVE` (cyan), `CACHED` (azure), `VERIFIED` (mint),
   `INFERRED` (amber), `UNKNOWN` (dim). Ties directly to the `CLAUDE.md` evidence tags. Put one on
   **every** number that leaves the artifacts directory. Judges will notice.
3. **`section(title, subtitle)`** — a header plus a one-line *"what am I looking at"* in `ink-dim`.
   Every single chart gets one. A chart with no sentence explaining it is a chart nobody reads.
4. **`depth_scrubber()`** — a vertical control over the 15 real depths
   `[0,10,20,30,50,75,100,125,150,200,300,400,500,700,1000]`, non-linear spacing that reflects real
   depth, with the **thermocline band (100-150 m) tinted** and labelled. Import the depth list from
   `oceanembed.config` — never hardcode it (contract-first rule).
5. **`empty_state(title, why, fix)`** and **`error_state(exc)`** — a bordered card, never a raw
   traceback. `error_state` shows a friendly line, then the exception behind an expander.
6. **`skeleton(height)`** — a shimmering placeholder shown while a cube reconstructs. Ocean
   reconstruction takes seconds; a blank page for those seconds reads as "broken".
7. **`caveat(text)`** — the amber inline note used for depth exaggeration, seafloor gaps,
   uncalibrated sigma, and the GLORYS comparator warning.

Apply the theme with one `st.markdown(CSS, unsafe_allow_html=True)` call from `theme.inject()`,
called once at the top of `main.py`. Do not scatter inline styles.

---

## 6. The 3-D Ocean page — this is the one they will remember

New file: `app/ui/three_d/ocean3d.py` plus a self-contained `app/ui/three_d/ocean3d.html`,
mounted with `streamlit.components.v1.html(..., height=720, scrolling=False)`.

Use **three.js r16x from a CDN** (`https://cdn.jsdelivr.net/npm/three@0.16x.x/...`, pinned exact
version, plus `OrbitControls`). **Check the current version and the ESM import-map syntax with
Context7 before writing it** — three.js changed its module layout recently and stale syntax will
silently render nothing.

### 6.1 What the scene contains

- **The water volume** — 15 horizontal planes, one per real depth level, stacked at their true
  (exaggerated) depth. Each plane is a `PlaneGeometry` textured with that depth's temperature slice.
  Alpha-blend them (`transparent: true`, `depthWrite: false`, opacity ~0.35, sorted back-to-front).
  This reads as a genuine volume, runs at 60fps on integrated graphics, and cannot fail the way
  raymarching can.
- **The 26 degC isotherm as a real mesh** — the money shot. Extract it **server-side** in Python with
  `skimage.measure.marching_cubes` over `cube.temperature`, send vertices+faces as a compact binary
  or a plain JSON array, render as a semi-transparent cyan surface with a **subtle emissive glow**
  (the only glow in the entire product). Caption it: *"the 26 degC layer — the depth of this surface
  is what fuels a cyclone."* That one sentence plus that one surface is your whole pitch in one image.
- **Land** — extrude `artifacts/land_mask.npy` into a flat dark-grey (`#1A2333`) shell at z=0 so the
  Indian subcontinent, Arabian peninsula and Sri Lanka are unmistakable. Judges orient themselves by
  coastline, not by axis ticks.
- **Argo floats** — real float positions for the selected date as small cyan points, each with a thin
  vertical line dropping to 1000 m (its dive trace). Independent-validation floats get a mint ring.
- **Seafloor** — where `valid_mask` is False the planes must be **cut**, not filled. Caption stays:
  *"gaps are the sea floor, not missing data — 24% of cells never reach 1000 m."*

### 6.2 Getting the data across without killing the browser

100 x 240 x 15 floats as JSON is ~360k numbers and will hang. Instead:

- Encode **each depth slice as a PNG data-URI** (normalize to the fixed global min/max, write 8-bit
  greyscale or RGBA-pack for 16-bit precision) and pass 15 small images. Apply the colormap in a
  **GLSL fragment shader** on the GPU using a 1-D colormap lookup texture — so switching between
  temperature / anomaly / uncertainty is instant and re-sends nothing.
- Total payload budget: **< 4 MB**. First paint **< 2 s**. Measure both, log them, report them.

### 6.3 Controls

- **Orbit** (drag), **zoom** (wheel), **pan** (right-drag) via `OrbitControls`, damping on.
- **Idle auto-rotate at 0.15 rad/s**, stopping the instant the user touches it, resuming after 8s
  idle. A slowly turning ocean while the presenter talks is worth more than any scripted animation.
- **Depth exaggeration slider** (1x to 200x, default 60x). The current caption discipline stays:
  *always print the factor*. 1000 m across 60 degrees of longitude is a film of water; drawn to scale
  you would see nothing, and pretending otherwise is dishonest.
- **Field switch**: Temperature / Anomaly / Uncertainty (shader swap, instant).
- **Slice mode**: a draggable clipping plane that cuts the volume open along a chosen latitude —
  reuse `cube.section()`.
- **Click a column** -> `Streamlit.setComponentValue({lat, lon})` -> the right inspector shows that
  full profile. This is the interaction that turns a picture into an instrument.

### 6.4 Scene craft

- Camera: perspective, 45 degree FOV, start at a low oblique angle (~25 degrees above horizontal,
  looking NNE across the Arabian Sea) — **not** top-down. Top-down looks like a map; oblique looks
  like a volume.
- Fog (`FogExp2`, abyss color, density tuned so the far edge dissolves) for depth cueing.
- Lighting: one hemisphere light plus one soft directional key. Keep it flat and legible — this is an
  instrument, not a game.
- A thin `edge`-colored wireframe bounding box with **real tick labels** (lat degN, lon degE, depth m).
  A 3-D plot without axes is decoration, not science.
- Bloom **only** on the isotherm mesh, and keep it subtle.

### 6.5 What NOT to build

No particle oceans, no animated caustics, no rotating earth globe, no starfield, no water shader
with waves. Every one of those says "demo" and costs you credibility with a domain judge.

### 6.6 Fallback ladder (mandatory)

```
three.js WebGL          ->  the good case
  |  WebGL unavailable / CDN blocked / point count too high
Plotly 3-D Volume       ->  already working in app/phase2/cube_page.py, reuse it
  |  plotly not installed
Altair 2-D depth slice  ->  ships with Streamlit, always available
```
Each fallback must **say in one line why it fell back**. Never a silent downgrade, never a crash.
Test the ladder by actually forcing each branch, and paste the output.

---

## 7. Motion and interaction

- 150 ms `ease-out` on hover/state, 250 ms on panel open, **0 ms on data updates** (a metric must
  never animate its way to a new value — it looks like it is being invented).
- Hover on any map -> crosshair plus live readout in the inspector. No click required to explore.
- Keyboard: left/right = date, up/down = depth, `S` = toggle source, `3` = jump to 3-D, `?` = shortcut
  sheet as a modal. A presenter driving by keyboard looks fluent; hunting for a dropdown mid-pitch
  does not.
- Every long operation gets a skeleton, never a spinner over a blank page.

---

## 8. Demo-hall realities (test these, do not assume)

- Test at **1920x1080** and at **150% browser zoom** — projectors and back rows.
- Contrast >= 4.5:1 for all text. Check the dim greys; they usually fail.
- Never encode meaning by red/green alone (deuteranopia is ~8% of men, and judging panels are small).
- Assume **no internet**. The three.js CDN must have a **vendored local copy** at
  `app/ui/three_d/vendor/` and the HTML must fall back to it. A hall Wi-Fi failure must not delete
  your best feature.
- One-command launch: write `scripts/run_ui.ps1` that starts port 8500 and opens the browser.

---

## 9. Order of work — ship-partial-safe

Do them in this order. If you run out of time, whatever is done still ships as a coherent product.

| # | Block | Outcome |
|---|---|---|
| 1 | `app/ui/theme.py` + `components.py`; apply to **one** existing page | Proves the design system on real content before scaling it |
| 2 | `app/ui/main.py` shell: nav, top bar, shared date/source state, all 10 pages reachable | The "one app" win — biggest score-per-hour on this list |
| 3 | 3-D page: planes + land + orbit + depth exaggeration | The memorable image |
| 4 | 26 degC isotherm mesh + Argo floats + click-to-inspect | The pitch, in one frame |
| 5 | Right inspector panel + provenance chips everywhere | Turns a dashboard into an instrument |
| 6 | Empty/error/skeleton states, keyboard shortcuts, offline vendoring | Survives contact with demo day |
| 7 | Screenshot pass at 1080p; fix whatever looks wrong | The judges see pixels, not architecture |

**After each block**: run it, screenshot it, paste the real terminal output, commit. Do not batch
seven blocks into one commit.

---

## 10. Definition of DONE (from `CLAUDE.md`, applied here)

- [ ] `streamlit run app/ui/main.py --server.port 8500` starts clean, no traceback in the console
- [ ] All 10 pages reachable from one nav; date + source persist across page switches
- [ ] Port 8501 (frozen demo) still runs, and `git diff` shows **zero** changes to
      `app/streamlit_app.py` and `app/panels/`
- [ ] `python -m pytest tests -q` — same or higher pass count than before you started (paste both)
- [ ] 3-D page renders on real data for at least 3 different dates; all three fallback branches
      tested by forcing them, with output pasted
- [ ] Every on-screen number traced to a file in `artifacts/` and carrying a provenance chip
- [ ] Payload and first-paint numbers measured and reported (section 6.2)
- [ ] Screenshots at 1920x1080 attached for: Overview, 3-D Ocean, Validation, Cyclone Heat
- [ ] `docs/HANDOFF.md` appended; `docs/DECISIONS.md` updated with every non-obvious UI choice
- [ ] Committed in 7 or more commits matching section 9

**"It should work" is NOT done.** Every claim tagged `[VERIFIED]`, `[INFERRED]`, or `[UNKNOWN]`.

---

## 11. The anti-checklist — do not do any of these

Emoji headings, gradient text, glassmorphism, drop shadows on dark, rainbow/jet colormaps,
more than two accents on one screen, animated counters, fake or placeholder numbers, lorem ipsum,
a chart without units, a colorbar that rescales per frame, a 3-D plot without axis labels,
autoplaying sound, a "Powered by AI" badge, deleting an existing page, editing the frozen demo,
recomputing a metric in the UI, hardcoding the depth list, claiming anything works before running it.

---

## 12. The demo narrative (drives the page order)

The nav order in section 4 is a first guess. The real order should match how the pitch is delivered
on the day. Fill this in before starting block 2.

<!-- TODO(human): the 3-minute judge walkthrough, in order -->

---

*End of prompt. Start with section 0, report what you found, then give me your plan before writing code.*
