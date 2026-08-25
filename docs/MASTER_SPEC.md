# MASTER_SPEC.md  (Owner: Unit B — Darshan)

## Problem (SIH26066, Ministry of Earth Sciences)
Reconstruct depth-wise subsurface ocean **temperature** from **daily surface** ocean/satellite observations at **0.25°**
over the **North Indian Ocean (5–30°N, 45–105°E)**. Motivation: heat content, stratification, marine heatwaves,
cyclones, fisheries, data assimilation.

## Scope
- **MUST (Aug 30 demo):** real data → preprocessing → real model inference → multi-depth temperature → NIO map →
  vertical profile → baseline comparison → quantitative validation (incl. independent Argo) → stated limitations →
  stable Streamlit UI → reproducible.
- **SHOULD (Aug 30 if time):** uncertainty band, anomaly map, observation-priority map (behind toggles; never on the
  critical path).
- **WON'T yet (Phase 2, post-win):** CNN/ConvLSTM, physics-guided loss, real satellite L4 inputs, depth to 2000 m,
  deep ensembles, the learned "ocean embedding".

## Honest positioning
Reconstruction with DL is already published (Meng 2021, TS-Cast 2026, FFPG-net 2025, DORS 2022 — see
`docs/LITERATURE_MATRIX.md`). We claim **system-level** contribution: a North-Indian-Ocean-focused, validated tool that
adds an uncertainty→anomaly→**observation-priority** decision layer. We never claim we invented AI subsurface reconstruction.

## Pipeline (critical path)
DATA (GLORYS+Argo) → PREPROCESS → BUILD SAMPLES → BASELINE (climatology, LightGBM) → MODEL (per-column MLP) →
VALIDATION (2022 holdout + Argo) → UI (Streamlit) → DEMO. Optional products branch off, never block the path.

## Deadline
Aug 30 inter-college gate. 5-day sprint (Aug 25→29 build, Aug 30 demo). If won → Phase 2.
