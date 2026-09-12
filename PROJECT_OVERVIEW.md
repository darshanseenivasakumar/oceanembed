# OceanEmbed — Project Overview

**Problem:** SIH26066 · **Sponsor:** Ministry of Earth Sciences (INCOIS) · **Event:** Smart India Hackathon 2026
**Repo:** `D:\sih project\oceanembed` · **Team:** Arjhun (models/training/physics) + Darshan (data/app/validation)
**Status as of 2026-09-04:** Phase 1 demo frozen and passed the screening gate. Phase 2 in progress, final deadline **7 Sep 2026**.

---

## 1. The Problem Statement

### 1.1 What SIH26066 asks for
Satellites can only see the ocean's **surface** — temperature, height, colour, roughness. They cannot see
**underneath**. But almost everything that matters about the ocean happens below the surface:

- **Cyclones** draw their fuel from warm water stored well below the surface (ocean heat content). A storm can
  pass over water that *looks* warm on satellite images but is actually shallow and cold underneath, or vice
  versa — surface temperature alone is a poor predictor of how much a cyclone can intensify.
- **Marine heatwaves** and long-term ocean warming are stored in the subsurface layers, not just the top few
  metres.
- **Monsoon dynamics**, fish habitats, and naval/defence applications all depend on the vertical structure of
  temperature and salinity, not just what is visible from space.

The only way to measure the subsurface directly today is **Argo floats** — autonomous robots that drift and dive,
periodically surfacing to transmit a temperature/salinity profile. But there are only **~2,455 Argo profiles**
scattered across the **~15 million km²** North Indian Ocean in a given year — far too sparse to give a complete,
gridded, daily picture.

**The ask:** use a machine learning model to *reconstruct* the full 3-D subsurface temperature field (and
supporting products) purely from what satellites *can* see at the surface, for the region that matters most to
India.

### 1.2 Exact technical requirements
- **Output variable:** subsurface ocean **temperature**, secondarily **salinity** and **density**
- **Depths:** 15 standard levels, 0–1000 m — `[0, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 400, 500, 700, 1000]`
- **Domain:** North Indian Ocean, **5–30°N, 45–105°E** (covers the Arabian Sea and Bay of Bengal)
- **Resolution:** 0.25° grid (100 × 240 cells), **daily**
- **Inputs allowed:** surface satellite observations only — SST, SSS, SSH (altimetry), surface currents, wind
- **Required supporting products:** predictive uncertainty, temperature anomaly, and an **observation-priority
  layer** — a map of where deploying a new Argo float would be most scientifically valuable
- **Required validation:** against **independent** Argo float data never used in training
- **Required honesty:** RMSE, correlation, and bias must be reported per depth, not hidden behind one pooled number

### 1.3 Why this is a hard problem, specifically
- Surface data cannot fully "see" the subsurface — there is a real, physical ceiling on how accurate any
  surface-only model can be, especially at the thermocline (the depth band where temperature drops fastest) and
  in the deep ocean.
- There is no direct "satellite-input, ground-truth-output" dataset to train on — real satellite coverage of the
  full subsurface doesn't exist. Something has to stand in as the training target.
- The North Indian Ocean has strong regional quirks (the Bay of Bengal's river-freshened surface layer, the
  Somali/Arabian Sea upwelling driven by the monsoon) that a generic global model would not capture well.

---

## 2. Our Approach

### 2.1 The core idea
We train a deep learning model to map a short **time-window of surface satellite fields** (not just one day —
an 11-day sequence) over a **local spatial patch** (roughly ±2°, about the size of one ocean eddy) around each
point, into a full 15-depth temperature (and salinity) profile at that point.

Because no real "satellite-in, deep-ocean-out" ground truth exists, we solve the training-data problem in two
steps:

1. **Train against GLORYS12V1**, a physics-based ocean reanalysis (a supercomputer ocean model that assimilates
   real satellite and in-situ data) as the training *target*. This gives complete, gridded, daily
   temperature/salinity fields everywhere — something no satellite or float network can provide on its own.
2. **Validate against real, independent Argo float profiles** that the model never saw during training. This is
   the honest test: it tells us how the model performs against reality, not just against the reanalysis it was
   trained on.

We also deliberately ran the model on **two different kinds of input** to be fully honest about what the PS is
actually asking for:

| Input leg | What feeds the model | Role |
|---|---|---|
| **Satellite-fed** (real OSTIA SST, DUACS altimetry, SMOS-blended SSS, GLOBCURRENT currents, observational wind) | Real observational products | **This is the actual PS deliverable** — the PS asks for satellite-only input |
| Reanalysis-fed (GLORYS surface fields as input) | Model-generated fields, not satellite | An upper-bound **comparator only** — shows what's possible if surface inputs were perfect, never presented as "our result" |

### 2.2 Model architecture — adapted from the "TS-Cast" 2026 paper
We based our model on **TS-Cast** (*Ocean Science*, 2026), the closest published method to what SIH26066 asks
for, and adapted it to our region and data:

1. **Encoder** — reads the 11-day, 17×17-cell surface patch (7 channels: SST, SSS, SSH, current-u, current-v,
   wind-u, wind-v) plus a geographic position encoding, and compresses it into a single feature vector.
   We ran a **fair "bake-off"** between four candidate encoders — sharing the exact same output head so the
   *only* thing that differed was the encoder — before picking a winner:
   - `MLPControl` — no spatial context at all (the control, to prove spatial context is worth having)
   - **`CNN3D`** — 3-D convolutions with residual blocks (the paper's own design) — **this is the one we shipped**
   - `CNN+Attention` — a CNN stem followed by self-attention
   - `ViT` — a vision transformer
2. **Climatology-residual decoding** — instead of predicting the raw temperature, the model predicts a
   *deviation* from the normal seasonal average (climatology) at that location. This is an easier target for the
   network to learn and keeps predictions physically grounded.
3. **Uncertainty head** — the model also predicts its own confidence (a variance) at every depth, trained with a
   **β-NLL loss** rather than a plain likelihood loss, because plain likelihood loss was measured collapsing the
   uncertainty estimate to near-zero early in training (a known failure mode we hit and fixed).
4. **Two stages:**
   - **Stage 1** predicts temperature only.
   - **Stage 2** adds a salinity output, then **computes** density from the model's own predicted temperature and
     salinity using the real seawater equation of state (never predicts density directly) — matching how the
     reference paper does it.

### 2.3 The decision-support layer
Beyond raw reconstruction, we built an **observation-priority map**: a heuristic combining (a) how anomalous a
region is, (b) how uncertain the model is there, and (c) how far it is from the nearest real Argo float — combined
as a weighted geometric mean into a single 0–1 "worth observing" score. We are explicit that this is **not a
novel idea** — proper "optimal sensor placement" research already exists and is more rigorous — so we frame it
honestly as a lightweight, interpretable heuristic, not a scientific breakthrough.

### 2.4 How we worked
- A written, evidence-tagged discipline: every claim in project docs is marked **[VERIFIED]** (we actually ran
  it), **[INFERRED]** (a reasonable guess), or **[UNKNOWN]** — never stated as fact without one of these.
- A running **decision log** (`docs/DECISIONS.md`) recording every non-obvious engineering choice, including
  ones that turned out wrong, so mistakes aren't silently repeated.
- Strict single-owner file boundaries between the two of us, so we could work in parallel without merge conflicts.
- A **real-data-only rule**: no fabricated metrics, no synthetic numbers presented as results, and any
  synthetic/demo data must be visibly labelled in the app.

---

## 3. What We Have Built (as of 2026-09-04)

### 3.1 Phase 1 — the screening-gate demo (FROZEN, PASSED)
Tagged `v1.0.1-demo-aug30`, 142 tests passing, frozen on `main` and untouched since.
- Full pipeline: GLORYS + Argo download → preprocessing/regridding → per-column **MLP** model (a simple
  11-input → 128 → 128 → 11-output neural network, one prediction per grid column) plus **LightGBM** and
  **climatology** baselines
- MC-dropout uncertainty estimation
- Observation-priority v1
- A working Streamlit demo UI
- **Result:** this passed the Aug 30 inter-college screening gate.

### 3.2 Phase 2 — the current build (in progress, deadline 7 Sep 2026)

**The validated headline result** (frozen, reproducible, checked against a checksum of the exact code+data
combination that produced it):

| | RMSE | bias | correlation | skill vs climatology | validated against |
|---|---|---|---|---|---|
| **Satellite-input, Stage 1 — THE PS DELIVERABLE** | **0.9078 °C** | +0.1003 °C | 0.8812 | +0.2595 | 962 independent Argo floats, 12,829 depth comparisons |
| GLORYS-input, Stage 1 (comparator, not the deliverable) | 0.8789 °C | — | — | +0.2831 | same Argo set |
| GLORYS-input, Stage 2 T+S+density (best-accuracy comparator, not the deliverable) | 0.8548 °C | +0.1055 | — | +0.3027 | same Argo set |

The gap between the satellite-fed and reanalysis-fed legs (+0.0289 °C) is itself a meaningful result: it shows
real satellite observations retain about 92% of the skill of a "perfect surface input" comparator.

**What else has been built and scientifically checked:**

- **Real data pipeline**: GLORYS12V1 (reanalysis) plus real satellite products — OSTIA SST, DUACS altimetry,
  SMOS-blended sea-surface salinity, GLOBCURRENT surface currents, and an observational wind product — downloaded,
  regridded, and pipelined into a 388-day daily bundle. Nothing synthetic in the shipped model.
- **Collocation engine** — matches model grid output to the exact time/place of a real Argo measurement. VALIDATED.
- **Physics module** — proper mixed-layer depth, thermocline, barrier-layer, and ocean-heat-content calculations
  using the real seawater equation of state (EOS-80), checked against four published reference values to better
  than 0.001 kg/m³. VALIDATED: reproduces known Bay-of-Bengal "barrier layer" behaviour (a freshwater cap that
  traps heat above the thermocline — directly relevant to cyclone intensification).
- **Event detection** — an eddy detector that reproduces the seasonal growth of the **Great Whirl** (a known
  Arabian Sea eddy, ~85 km in January growing to ~243 km in August, in the right place); an upwelling detector
  validated against the Findlater Jet wind pattern. Front detection is built but not yet independently validated.
- **"Validation Lab"** — we measured the reanalysis's *own* error against Argo, not just our model's error. This
  lets us tell the difference between error we **inherited** from imperfect training data (mainly at the
  thermocline, 100–150 m) versus error that is **genuinely ours** (the 20–50 m mixed layer).
- **Basin-split analysis** — separate scoring for the Arabian Sea vs the Bay of Bengal.
- **Uncertainty calibration measurement** — how trustworthy the model's stated confidence actually is, measured
  against real errors (see §6, flaw #4).
- **3-D ocean cube visualisation**, a cyclone heat-content panel (Tropical Cyclone Heat Potential + isotherm depth
  + ocean heat content), a live Argo-overlay panel, and a depth-vs-distance transect (cross-section) tool.
- **7 separate Streamlit dashboards**, each on its own fixed port, covering the main demo, collocation, physics,
  events, validation, the 3-D cube, and the v2 TS-Cast reconstruction UI.
- **530+ automated tests** passing across the Phase 2 codebase, plus a provenance/audit system that
  cryptographically hashes every model checkpoint and traces it back to the exact code commit and data bundle
  that produced it — including a deliberate "poison test" that injects reanalysis data into the satellite input
  channels to prove the leak-detector actually catches contamination.

---

## 4. Future Scope

Things we know are still open, in rough priority order:

1. **Basin-split the satellite-fed model specifically** — currently the Arabian-Sea-vs-Bay-of-Bengal breakdown
   only exists for the reanalysis-fed comparator, not the actual deliverable.
2. **Multi-seed runs** — every headline number today comes from a single training run (one random seed). We need
   several seeds to know if these numbers are stable or lucky.
3. **Explain the Arabian Sea satellite-input penalty** — real satellite input costs an extra +0.0341 °C
   specifically in the Arabian Sea, reproducibly, and we've tested and ruled out four possible causes without
   finding the real one.
4. **Run Stage 2 (salinity + density) on satellite input** — it currently only exists on the reanalysis-fed leg.
5. **Improve uncertainty calibration** further, especially in the mixed layer where it's worst.
6. **Currents ablation** — test whether including ocean current data (u/v) actually earns its keep versus a
   simpler input set.
7. **INCOIS LAS integration** — the sponsor's own live gridded-Argo data service has been unreachable throughout
   development; we fell back to the public `argopy` archive. Needs re-testing before claiming integration works.
8. **Near-real-time latency measurement** for a genuinely operational pipeline (right now everything runs on
   historical archived data).
9. **Ocean Sentinel** (configurable threshold-based alerting) — not started.
10. **Merge remaining feature branches cleanly into `main`** — some Phase 2 features (cyclone-heat, argo-overlay,
    transect) were built and verified on separate branches and still need final integration decisions.

**Deliberately deferred, not forgotten:**
- A transformer-based (ViT) encoder for production use — tested in the bake-off, not clearly better with the
  amount of data available.
- Marine/subsurface heatwave detection — blocked because it needs day-to-day persistence tracking that our
  current data cadence can't reliably support, and there's no agreed scientific definition yet.
- A second-generation observation-priority model — deliberately not pursued, since rigorous published methods
  already exist for this and we'd rather be honest about that than reinvent a weaker version.

---

## 5. Technology Stack & Training Process

### 5.1 Tech stack

| Layer | Tools |
|---|---|
| Language | Python 3.12 |
| Deep learning | **PyTorch** (CUDA-accelerated — trained on an RTX 3050 GPU) |
| Classical ML baseline | **LightGBM** (gradient-boosted trees) |
| Data handling | NumPy, pandas, xarray, pyarrow/parquet (CSV fallback) |
| Ocean data access | `copernicusmarine` (CMEMS/GLORYS + satellite L4 products), `argopy` (Argo floats) |
| App / UI | Streamlit, Altair, Plotly (3-D volumetric rendering) |
| Testing | pytest (530+ tests) |
| Version control | git, with a written decision log and single-owner file split |

### 5.2 Datasets used

| Dataset | Role | Details |
|---|---|---|
| **GLORYS12V1** (CMEMS reanalysis) | Training **target** (truth) for all depths; also used as the input for the GLORYS-fed comparator leg | ~1/12° native, regridded to 0.25°, daily |
| **OSTIA** | Real satellite input — sea surface temperature | L4, daily |
| **DUACS altimetry** | Real satellite input — sea surface height / derived currents | L4, daily |
| **SMOS-blended** | Real satellite input — sea surface salinity | L4, daily |
| **GLOBCURRENT** | Real satellite input — total surface currents | daily |
| Observational wind product | Real satellite/observational input — surface wind u/v | daily-mean, block-averaged onto our grid |
| **Argo floats** (via `argopy`) | **Independent validation only — never used in training** | 962 independent profiles / 12,829 depth comparisons in the current frozen Phase 2 run |

### 5.3 How the model was trained
1. **Windowing:** each training sample is an 11-day sequence of a 17×17-cell (~±2°) patch around a target grid
   cell, across 7 surface channels, plus a 3-value geographic position encoding.
2. **Target:** the model predicts a *residual* on top of a monthly climatology (computed strictly from training
   years, to avoid the model ever "peeking" at the test period).
3. **Split:** time-based, never random — a fixed training window and a held-out test window, with an "embargo"
   that **drops** (not shortens) any training day whose input window would otherwise overlap the test period.
   (We actually caught and fixed a real leakage bug here mid-project — see §6.)
4. **Loss:** β-NLL (β=0.5) — a variant of Gaussian negative-log-likelihood chosen because the plain version
   was measured collapsing the model's predicted uncertainty to near-zero early in training.
5. **Optimizer:** AdamW, with early stopping on held-out loss (training stops once the held-out score stops
   improving for a set number of epochs).
6. **Checkpoint selection:** we save the **best held-out epoch**, not simply the last one — this task overfits
   within a handful of epochs.
7. **Stage 2:** the same architecture gets a second output head for salinity; density is then **computed** (not
   predicted) from the model's own temperature and salinity outputs, using the real seawater equation of state.
8. **Every run is seeded and logged** — checkpoint, data bundle, code commit, and metrics are all recorded
   together so a result can be reproduced or audited later, not just trusted on faith.

---

## 6. Known Flaws & Honest Limitations

We deliberately keep a public record of what's wrong or unproven, rather than hiding it. In order of how much it
matters:

1. **This is not a novel method.** AI reconstruction of subsurface ocean temperature from satellite data is
   already published research (Meng 2021, TS-Cast 2026, FFPG-net 2025, DORS 2022, NeSPReSO 2025). Our honest
   claim is a **system-level** contribution — a North-Indian-Ocean-focused, independently validated tool with an
   uncertainty → anomaly → observation-priority decision layer — not a new reconstruction technique.
2. **The observation-priority idea is also not novel.** Rigorous published methods for optimal sensor/float
   placement already exist and are more sophisticated than our heuristic (no cost model, no float-drift physics).
3. **The mixed layer (20–50 m) is a genuine model weakness**, not something inherited from the training data —
   we're 0.3–0.4 °C worse than the reanalysis there, confirmed three independent ways (accuracy, skill, and
   uncertainty calibration).
4. **Uncertainty is mildly overconfident.** After finding and fixing a bug that initially made this look far
   worse than reality, the corrected measurement shows the model's ±2σ confidence band covers about 91% of real
   errors versus a 95.4% nominal target — worst at 50 m. We show the *measured* coverage on screen, and never
   label it "95% confidence."
5. **An unexplained penalty in the Arabian Sea.** Feeding real satellite data (instead of reanalysis) costs an
   extra +0.0341 °C there specifically, reproducibly across runs — and we don't know why. Four candidate causes
   were tested and none held up.
6. **Every headline number is from a single training run (seed).** We have no multi-seed statistical confidence
   intervals yet, so we can't yet say how much of any number is "real" versus run-to-run noise.
7. **Stage 2 (salinity + density) has never been run on satellite input** — it's validated only on the
   reanalysis-fed comparator leg, so there is currently no real satellite-driven salinity/density number.
8. **Limited validation windows.** Argo validation covers 2022 for Phase 1 and a 2025–26 window for Phase 2 —
   not a multi-year record, so seasonal/interannual generalisation isn't fully tested yet.
9. **Front detection is unvalidated.** The detector runs and produces plausible-looking output, but no
   independent reference or climatology has been checked against it (unlike eddies and upwelling, which are).
10. **Marine/subsurface heatwave detection is permanently blocked** for this project — the data cadence available
    can't support the multi-day persistence tracking the feature needs.
11. **The LightGBM baseline is never shown against real Argo scores** — the artifact that exists was never
    properly scored, and showing it anyway would be a fabricated comparison, so the app states the omission
    rather than hiding it.
12. **INCOIS's own gridded-Argo data service (LAS) has been unreachable throughout development.** We validated
    against the public `argopy` archive instead — a documented substitution, not a silent one.
13. **A real data-leakage bug was found and fixed mid-project** — an earlier version of the training-window logic
    let a handful of boundary training days read test-period data. All numbers produced before the fix were
    retired rather than quietly kept.
14. **The reference paper's density-loss term was tested and found to hurt accuracy on our data** — reported as
    a negative result and left switched off, rather than silently dropped.
15. **Deep-ocean skill (below ~500 m) is fundamentally limited by the physics of the problem itself** — the deep
    ocean simply varies very little and our error there mostly reflects imperfections already present in the
    reanalysis we trained against, not something better modelling from surface data alone can fix.
16. **Not everything built is merged into the main branch yet.** Some Phase 2 features were developed and
    verified on separate branches and still need final integration.

---

*This document reflects the project state as of 2026-09-04. Numbers and statuses will change as Phase 2
continues toward the 7 Sep 2026 deadline — treat this as a snapshot, not a living source of truth. The living
source of truth is `docs/PHASE2_STATUS.md` and `docs/HANDOFF.md` in the repo.*
