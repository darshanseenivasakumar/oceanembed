# PROMPT FOR ARJHUN'S CLAUDE — the Subsurface Marine Heatwave (MHW) Detector

Paste this whole file as your first message. It is self-contained; assume you know nothing else.
Read `CLAUDE.md` and `docs/phase2/AGENT_SYNC.md` after it, then start.

---

## WHO YOU ARE, WHAT THIS IS, AND THE ONE NUMBER THAT MATTERS

You are the ML/engineering agent on **OceanEmbed**, SIH26066 (Ministry of Earth Sciences):
reconstruct depth-wise subsurface ocean **temperature** from surface satellite observations at
0.25° over the North Indian Ocean (5–30 N, 45–105 E), 15 depths 0–1000 m.

**[VERIFIED] The deliverable is `deliverable_satellite`** in `artifacts/frozen_manifest.json`:
stage-1, satellite inputs, seed 42. **RMSE 0.9078 °C** against 962 independent Argo profiles.
**0.8548 °C is a GLORYS-input comparator, NOT the deliverable.** Never quote 0.8548 as the headline.

## WHAT YOU ARE BUILDING, AND WHY IT IS NOT A NEW PROJECT

A **subsurface marine-heatwave (MHW) detector.** A marine heatwave (Hobday et al. 2016) is water
that stays **hotter than the 90th percentile of what's normal for that day of year, for at least 5
consecutive days.** The scientific point: **subsurface heatwaves frequently have no surface
signature at all** — roughly one-third of events are trapped below the surface where satellites
can't see them (Sun et al.; Fragkopoulou et al.). A satellite SST map looks calm while a heatwave
rages at 150 m and kills a fishery. The 2018-19 Bering Sea event starved ~10 billion snow crabs
before surface sensors noticed.

**This is a DERIVED PRODUCT on the model you already have, not a new model.** OceanEmbed already
reconstructs the 3-D temperature field from satellite inputs — that is the hard part, and it's done.
The detector sits on top of it. Most of what it needs already exists in the repo (below); the only
genuinely new pieces are the heatwave *baseline* and the *detection logic*.

**This reopens a feature the team shelved.** `PHASE2_ARCHITECTURE_AUDIT.md:156` names a planned
`src/phase2/events/heatwave.py` that was never built, and F7 (subsurface heatwave) was declared
"BLOCKED / permanently closed" (`PHASE2_STATUS.md:67`) because the Phase-1 event data was **monthly**
— you cannot detect a "5 consecutive day" event in monthly data. With the 388 consecutive **daily**
days now on disk plus the multi-year baseline this spec adds, **F7 is unblocked.** Say so.

## THREE DECISIONS ALREADY MADE WITH DARSHAN — do not relitigate

1. **Region: North Indian Ocean.** The paste that inspired this recommends the California Current as
   a pilot. **We are NOT pivoting** — that would throw away the entire validated model, all the data,
   and the SIH deliverable. NIO, using the existing model.
2. **Baseline: download a multi-year daily baseline** (details below). One year cannot define a
   heatwave — Darshan and I worked through why: with one year, "June 1st" has exactly one temperature,
   so nothing can be "unusually" warm relative to a distribution that doesn't exist. The multi-year
   download is mandatory, not optional.
3. **Scope: the PHYSICAL detector only.** Subsurface MHW cube + Benthic Decoupling Index + eddy-driver
   attribution. The ecological / fisheries-alert / vessel-routing layer from the paste is **explicitly
   out** — it needs biological threshold data and species models we don't have, and would be the
   biggest overclaim risk in the whole project. Frame it as future work; do not build it.

## THE GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

Read-only, import-only: `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, baseline `tests/`.

## THE BRANCH-BASE RULE — build on the right code

**[VERIFIED this session] `main` in a fresh checkout is a STALE Phase-1 snapshot** (`PROJECT_RECORD.md`
records origin/main as 186 commits behind). The authoritative line is **`phase2-tscast-nio`**.

```
git fetch origin
git checkout phase2-tscast-nio && git pull
git checkout -b phase2-mhw-detector
```

Branch name uses a HYPHEN. Everything for this feature lives on `phase2-mhw-detector` and merges
nowhere until Darshan says so.

---

## STEP 0 — THE DATA TO DOWNLOAD (do this first; nothing works without it)

**[VERIFIED — this is the crux gap] There is NO percentile climatology anywhere in the repo.** An
Explore pass confirmed: `climatology.npy` is a MONTHLY mean over 2019-2021 only; `clim_daily.npz` is
that same monthly mean re-bundled (its own builder docstring says "388 DAYS IS NOT A CLIMATOLOGY");
`climatology_std.npy` is a monthly interannual σ with n=3 and is read by nothing. No `p90`, no
day-of-year climatology, no Hobday threshold exists. This is why the download is mandatory.

**Download (reuse the existing pipeline — same product the daily bundle already uses):**
- Product: **`cmems_mod_glo_phy_my_0.083deg_P1D-m`** (GLORYS12V1 daily reanalysis).
- Variables: **`thetao`** (temperature) and **`so`** (salinity — needed for the mixed-layer depth in
  the Benthic Decoupling Index).
- Region: **5–30 N, 45–105 E** (import `config.REGION`, never hardcode).
- Depths: the 15 standard `config.DEPTHS` levels, to 1000 m.
- Period: **1993-01-01 → 2020-12-31 is ideal** (28 years, the GLORYS12 span). **10 years (2011-2020)
  is the practical minimum** — fewer years makes the 90th percentile noisier; state which you used.
- Size: ~0.5 GB processed/year (the existing 388-day bundle is 509 MB) → ~5 GB for 10 yr, ~15 GB for
  28 yr processed; raw NetCDF is larger. Use the **resumable** downloader
  `src/oceanembed/data/download_glorys.py` and regrid with the SAME operator the daily pipeline uses
  (`src/phase2/tscast_nio/daily_pipeline.py` / `preprocess_satellite.py`) so the baseline lands on the
  **model's exact 0.25° grid**. A threshold built on a different grid is invalid — this is not
  optional consistency, it's correctness.

Store it as its own bundle (e.g. `data/processed/mhw_baseline/`), gitignored like all data, with the
period + product stamped into an embedded `provenance` JSON exactly like the existing bundles do.

---

## WHAT ALREADY EXISTS — reuse, do not rebuild (all [VERIFIED] this session)

```python
from phase2.tscast_nio.field import predict_field
from phase2.tscast_nio.inference import TSCastPredictor
field = predict_field(TSCastPredictor(), "2026-05-15")   # temperature (100,240,15) + calibrated sigma
```

| Need | Reuse | Where |
|---|---|---|
| Model temperature for the detection year (2025-26) | `predict_field(...)` | `phase2/tscast_nio/field.py` |
| GLORYS truth for 2025-26 (to validate against) | `temp` key in `data/processed/daily/{2025,2026}.npz` (388 consecutive days) | on disk |
| Mixed-layer depth (density criterion) | `mixed_layer_depth(salinity, theta)` | `src/phase2/physics/layers.py` |
| Seafloor depth | `seafloor_depth_m(lat,lon)` on `OceanCube` | `src/phase2/cube/ocean_cube.py` |
| Eddy detection (driver attribution) | `detect_eddies(u, v)` — 2-D single snapshot | `src/phase2/events/eddy.py` |
| Arabian Sea / Bay of Bengal split | `grid_masks()`, `classify_points()` | `src/phase2/basins.py` |
| 3-D rendering | `OceanCube.reconstruct(date)`, `cube/volume.py` (`.tolist()` trap!) | `src/phase2/cube/` |
| Page template + explainer-footer pattern | any `app/phase2/*.py`; the `st.expander` blocks at the end of `validation_page.py` | — |

**Do NOT reuse `products/anomaly.py` for the MHW baseline** — it subtracts a monthly 2019-21 mean and
its σ is spatial, not climatological. The new day-of-year percentile artifact replaces it here.

## WHAT'S NET-NEW — build and TEST each; never assume it works

1. The multi-year baseline download + processing (Step 0).
2. The **day-of-year climatology + 90th-percentile threshold** builder.
3. The **MHW detection engine** — `src/phase2/events/heatwave.py` (the shelved file, finally built).
4. The **detector Streamlit page** — new, port **8518**.
5. The **model-vs-GLORYS MHW validation**.

---

## THE HOBDAY ALGORITHM — the heart of this feature

### A · Climatology + threshold (the new baseline artifact)

For each grid cell, each depth, each **day-of-year (1–366)**:
- Pool all temperatures from that day-of-year within an **11-day window centered on it** (±5 days),
  across **every baseline year** (so ~11 × N_years samples per point).
- **Climatology** = the mean of that pool. **Threshold** = the **90th percentile** of that pool.
- Then **smooth both along day-of-year with a 31-day moving average** (Hobday's step — removes
  sampling noise so the threshold is a smooth seasonal curve).
- Handle day-of-year 366 / leap years (wrap the window across the year boundary; don't drop Dec/Jan).

Output two `(366, 100, 240, 15)` float arrays → save as the new baseline artifact with provenance
(period, product, window, smoothing). This is the single most important new file.

**Footer text for this:**
`formula = r"T(x,y,z,t) > T_{90}(x,y,z,\text{doy}(t)) \;\text{for}\; \geq 5\;\text{consecutive days}"`
`plain`: "A marine heatwave isn't just 'warm water' — it's water hotter than the top 10% of what's
normal for THIS time of year at THIS depth, and it has to stay that hot for at least 5 days in a row."
`how_to_read`: "The threshold line is the seasonal 'unusually hot' bar. When the actual temperature
pokes above it and stays there, that stretch is a heatwave."

### B · Detection engine (`src/phase2/events/heatwave.py`)

Given a daily temperature time series at a cell/depth and the threshold curve:
- An event = temperature **> threshold for ≥5 consecutive days**.
- **Gap rule:** two events separated by a gap of **≤2 days** join into one event (Hobday).
- Per event, compute: **duration** (days), **mean & max intensity** (temperature minus *climatology*,
  °C, not minus threshold), **cumulative intensity** (°C·days), and **category** — Moderate / Strong
  / Severe / Extreme, by how many multiples of (threshold − climatology) the peak exceeds (Hobday
  2018). Return a list of event dicts, same shape-of-thinking as `detect_eddies`.

Write this as **pure functions on arrays** (no I/O, no Streamlit) so it's unit-testable, exactly like
`transect.py` and `eddy.py` are. Test against a hand-built synthetic series where you know the answer
(e.g. a 7-day spike with a 1-day dip in the middle should be ONE event of duration 7, not two).

### C · The scientific contribution + validation (the honest framing)

The threshold is built from GLORYS. Run detection on **both**:
- the **model reconstruction** (2025-26, satellite-driven — via `predict_field`), and
- the **GLORYS truth** (2025-26, the `temp` array already on disk).

Then **compare them per depth: hit / miss / false-alarm rate for MHW events.** The contribution is
answering *"can a satellite-only model catch subsurface heatwaves — including ones with no surface
signature?"* — NOT "we invented MHW detection." Zhang et al. (2024) already did global satellite
subsurface MHW detection; keep the honesty of `docs/NOVELTY_MATRIX.md`. Our angle is: a NIO-focused,
independently-framed detector on our own validated reconstruction, with its hit/miss rate measured.

**The demo money-shot:** find a real event in the 2025-26 window that is a heatwave at 100–200 m but
NOT at 0 m — a hidden subsurface heatwave the model caught that a surface SST map would miss. That
single case, shown on the 3-D cube, is the most compelling thing in this feature. If you can't find
one, say so honestly rather than manufacturing it.

### D · The Benthic Decoupling Index (the shelf story)

`BDI = MLD / seafloor_depth` (after Amaya et al.). When the mixed layer doesn't reach the seafloor
(BDI < 1), bottom water is cut off from the surface, so a bottom heatwave can rage while the surface
looks normal. Reuse `mixed_layer_depth` + `seafloor_depth_m`.

**State the caveat plainly, don't bury it:** `seafloor_depth_m` **saturates at 1000 m**, 24% of cells
shallower than 1000 m are masked, and the continental shelf (<200 m) — exactly where BDI matters most
— is where the model is **weakest** (Argo can't train on the shelf; the model's own worst region).
So BDI is most meaningful on the shelf and least reliable there. That tension IS the honest finding;
present it, don't hide it.

**Footer text:** `formula = r"\text{BDI} = h_{MLD} / H_{seafloor}"`. `plain`: "This measures whether
the surface 'mixed layer' reaches all the way down to the seabed. When it doesn't (index below 1),
the bottom water is sealed off from the surface — so it can heat up completely unseen from above."
`how_to_read`: "Low index = decoupled seabed = a bottom heatwave could be hiding there. Highest value
where it's most useful (shallow shelf), but that's also where the model is least sure — read it with
that in mind."

---

## THE EXPLAINER-FOOTER CONVENTION (Darshan's cross-cutting requirement)

Every page ends in a plain-language "what/formula/how-to-read" block. Generalize the pattern already
at the bottom of `validation_page.py` into one shared helper (e.g. `src/phase2/viz_explainer.py`):

```python
def render_explainer(title, formula, plain, how_to_read, caveats=None):
    st.divider(); st.subheader(f"About this panel — {title}")
    if formula: st.latex(formula)
    st.markdown(plain); st.markdown(f"**How to read it:** {how_to_read}")
    if caveats:
        with st.expander("Caveats and limitations"):
            for c in caveats: st.markdown(f"- {c}")
```

Call it last on the MHW page, with the Hobday and BDI text above.

## WORKFLOW — follow every step

1. `git fetch`, checkout `phase2-tscast-nio`, pull, branch `phase2-mhw-detector`.
2. Context7 for current docs (copernicusmarine for the download, scipy for percentile/smoothing,
   streamlit/plotly) before coding.
3. Build smallest working version: baseline builder → detection engine → page, in that order.
4. Tests under `tests/phase2/`. **No `tests/phase2/__init__.py`** (breaks pytest imports).
5. `PYTHONPATH=src python -m pytest -q` — everything passes, not just yours.
6. Real-data smoke test, inspect the actual events. A detector that finds 0 events, or finds a
   heatwave in every cell every day, is wrong — sanity-check the count against the literature
   (heatwaves are episodic, not constant).
7. Add a feature check to `scripts/phase2/accept.py` (assert the threshold artifact has the right
   shape and that a known synthetic series yields the known event).
8. Register port 8518 in `.claude/launch.json` and `docs/HANDOFF.md`.
9. Commit after tests pass (`git commit -F -` heredoc — backticks in `-m` get eaten by bash). Push
   the feature branch ONLY.
10. Log to `docs/phase2/AGENT_SYNC.md` tagged `[ARJHUN]` with the branch, the one test command, and
    what Darshan should see.

## TRAPS THAT HAVE COST THIS TEAM HOURS

- `tests/phase2/__init__.py` breaks pytest imports. Never create it.
- Branch `phase2/x` fails while branch `phase2` exists. Use `phase2-x`.
- `st.cache_data` silently drops `_`-prefixed args. Use a sha256 cache-buster.
- Altair >5000 rows: `alt.data_transformers.disable_max_rows()`.
- Plotly ≥6 + Streamlit: pass `.tolist()`, not numpy, into `go.Volume`/`go.Scatter3d` (empty box otherwise).
- Windows Streamlit runs as `python.exe`: `netstat -ano | grep :8518` then `taskkill //PID <pid> //F`.
- Never let a bare expression sit in Streamlit code (magic renders it).
- **The baseline period (1993-2020) and the detection period (2025-26) are disjoint — that's
  CORRECT for MHW (you detect against a historical normal). Do NOT "fix" it by using the same years
  for both; that would define away every heatwave.**

## HONESTY RULES

Tag every claim [VERIFIED] / [INFERRED] / [UNKNOWN]. Never fabricate a heatwave event, a metric, or a
citation. Keep 0.9078 (deliverable) and 0.8548 (comparator) distinct. If a subsurface-only event
can't be found in the data, say so — don't manufacture the money-shot. If anything here looks wrong,
say so before building.

## FIRST REPLY — do not write code yet

Reply with:
1. Confirm you'll start with Step 0 (the download) and which baseline period you'll pull (recommend
   the full 1993-2020; say if you'll start with 10 years to move faster).
2. Anything in this spec you think is wrong — especially the Hobday window/smoothing parameters and
   the model-vs-GLORYS validation design.
3. Your read on whether the "hidden subsurface heatwave" money-shot is likely to exist in the 388-day
   window, or whether that window is too short to expect a clean 5-day subsurface-only event.
