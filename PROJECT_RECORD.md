# PROJECT_RECORD.md — OceanEmbed / SIH26066
## Complete build, data, training and validation record

**Compiled:** 2026-09-05, ~21:00 IST
**Compiled at commit:** `139cb7e` on branch `phase2-novelty-cloud-dropout`; working tree **dirty** —
a second agent session was actively adding files while this was written (see §17).
**Remote:** `https://github.com/darshanseenivasakumar/oceanembed.git`
**Supersedes:** the compilation at `189713f` (2026-09-05 00:48). All of its content is carried
forward; seventeen commits, one new experiment and four new dashboards have been added since.

**Method.** Every number below was read out of a file on this disk or produced by a command run
during compilation. Nothing is transcribed from memory. Where a claim could not be checked here it
is tagged **[UNKNOWN]** or **[INFERRED]**, per `CLAUDE.md`.

**Evidence tags.** **[VERIFIED]** = executed / inspected here. **[INFERRED]** = reasonable but
untested. **[UNKNOWN]** = not checked.

---

## Table of contents

| § | |
|---|---|
| [1](#s1) | The problem statement, and what is actually shipped |
| [2](#s2) | Timeline and repository statistics |
| [3](#s3) | Branch and merge topology |
| [4](#s4) | Technology stack — every library, and why |
| [5](#s5) | Full subsystem inventory — what was built |
| [6](#s6) | Data: every dataset downloaded, processed and trained on |
| [7](#s7) | Every model trained — complete checkpoint inventory |
| [8](#s8) | Results — the headline, per depth, and every comparator |
| [9](#s9) | Ablations and controlled experiments |
| [10](#s10) | The cloud-dropout experiment — the newest result |
| [11](#s11) | Uncertainty: what is calibrated and what is not |
| [12](#s12) | The dashboard suite — fifteen surfaces, one port each |
| [13](#s13) | The freeze, provenance and byte-identity machinery |
| [14](#s14) | PS requirements audit — 16 PASS / 0 FAIL / 1 BLOCKED |
| [15](#s15) | Corrections, retractions and withdrawn claims |
| [16](#s16) | **Flaws, limitations and open items** |
| [17](#s17) | Current state of the working tree |
| [18](#s18) | How to reproduce every number here |
| [19](#s19) | Method: how this project is run |
| [20](#s20) | Appendix — document map, decisions, literature |

---

<a name="s1"></a>
## 1. The problem statement, and what is actually shipped

### 1.1 The problem (SIH26066, Ministry of Earth Sciences / INCOIS)

Reconstruct **depth-wise subsurface ocean temperature** from **daily surface satellite
observations** at **0.25°** over the **North Indian Ocean (5–30 °N, 45–105 °E)**, at 15 standard
depths from the surface to 1000 m, evaluated by RMSE, correlation and bias, with the GLORYS
reanalysis as the training target and gridded Argo as independent validation.

Frozen constants live in `src/oceanembed/config.py` and are imported everywhere, never retyped
**[VERIFIED — read from the file]**:

```
REGION    lat 5.0-30.0 N, lon 45.0-105.0 E, step 0.25 deg  ->  grid 100 x 240 = 24,000 cells
DEPTHS    [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]   (15 levels, m)
SEED      42
FEATURES  (v1) sst, sss, ssh, u, v, sin/cos lat, sin/cos lon, sin/cos doy   -- 11, in THIS order
CHANNELS  (v2) sst, sss, ssh, u, v, wu, wv                                  --  7
SPLIT     (v1) train 2019-2021, test 2022
          (v2) train 2025-06-01..2026-03-26, test 2026-04-01..2026-06-23, embargoed_v2
```

`config.sanity_check()` asserts the grid is 100 × 240, the depths are 15, the features are 11 and
the surface-feature order has not changed. It runs at import time in the tests.

### 1.2 What is shipped — and why it is not the most accurate number

**The deliverable is a satellite-input model.** This is the single most important fact in the
project, and it is enforced in code rather than in prose:

| | Argo RMSE | skill (1 − RMSE/RMSE_clim) | input source | status |
|---|---|---|---|---|
| **stage 1, satellite inputs** | **0.9078 °C** | **+0.2595** | OSTIA / DUACS / SMOS-blend / GLOBCURRENT / CMEMS-wind | **SHIPPED — the PS deliverable** |
| stage 1, GLORYS inputs | 0.8789 °C | +0.2831 | reanalysis | comparator only |
| stage 2, GLORYS inputs (T+S+ρ) | 0.8548 °C | +0.3027 | reanalysis | comparator only, **best accuracy** |
| stage 2, satellite inputs | 0.8854 / 0.9095 / 0.9158 (s42/43/44) | — | satellite | **not promoted, not frozen** |

The most accurate number in the project (**0.8548**) is **not** the deliverable, because its inputs
are reanalysis and the PS asks for satellite observations. Quoting it as "our result" would present
a reanalysis-fed model as satisfying a satellite-input requirement. `scripts/phase2/freeze.py`
asserts `input_source == "satellite"` on the shipped artifact so this cannot silently regress.
**[VERIFIED — live run 2026-09-05: `ok  input_source is 'satellite' -- the PS deliverable`]**

**The framing that is defensible to a jury:**

> Real satellite observations cost **+0.019 °C** (3-seed mean) against a reanalysis-fed comparator
> and retain **~92 %** of its skill. That difference is itself a measured result, computed on
> identical points — `rmse_climatology = 1.2259` and `n = 12,829` in both legs.

---

<a name="s2"></a>
## 2. Timeline and repository statistics

### 2.1 Two phases, two model generations

| phase | dates | model | data cadence | outcome |
|---|---|---|---|---|
| **Phase 1 (v1)** | 2026-08-25 → 08-26 | per-column MLP (11 → 128 → 128 → 15) + LightGBM baseline + climatology | GLORYS **monthly**, 48 steps 2019–2022 | demo shipped; Argo RMSE 0.9638 / skill +0.387 on 879 profiles |
| **Phase 2 (v2)** | 2026-08-26 → 09-05 | **TS-Cast-NIO** — 3-D CNN satellite encoder → climatology-prior decoder → T + log-variance heads | **daily**, 388 steps 2025-06-01 → 2026-06-23 | frozen 2026-09-02; Argo RMSE 0.9078 on 962 profiles, satellite inputs |

Phase 2 additionally built fifteen feature subsystems, each with a dashboard or a scored artifact:
collocation, 3-D cube, calibrated uncertainty + OOD, physics/OHC, event detection, validation lab,
wind input, cyclone heat, Argo overlay, transect, NetCDF export + HTTP API, click-map, uncertainty
map, acoustics, and cloud dropout.

### 2.2 Repository statistics **[VERIFIED — measured at `139cb7e`]**

```
commits reachable from HEAD ....... 273
commits by author ................. Arjhun 151 | darshanseenivasakumar 79 | "OceanEmbed Team" 43
lines added / deleted ............. +62,097 / -6,097

COMMITTED at 139cb7e (git ls-files)      WORKING TREE at 21:12 (incl. uncommitted)
  src/      13,117 lines / 88 files        src/      13,259 / 89   (+ dropout.py, 142)
  tests/    10,098 lines / 55 files        tests/    10,305 / 56   (+ test_dropout.py, 207)
  scripts/   6,791 lines / 42 files        scripts/   7,044 / 43   (+ run_cloud_dropout.py, 253)
  app/       5,329 lines / 20 files        app/       5,555 / 21   (+ dropout_page.py, 226)
  ---------------------------------        ---------------------------------
  total     35,335 lines / 205 files       total     36,163 / 209
```

The two columns differ by exactly the four uncommitted cloud-dropout files (§17), which is itself a
check that nothing else is drifting.

Commits per day:

```
08-25  61      08-29  13      09-02  46
08-26  48      08-30  19      09-03  21
08-27   2      08-31   8      09-04  14
08-28  12      09-01  13      09-05  16
```

Twelve calendar days, 273 commits — a mean of 22.75 per day, with two clear sprint peaks: 08-25
(the Phase-1 build) and 09-02 (the leakage embargo plus the satellite freeze).

### 2.3 Team structure

Three units on three separate Claude accounts, with **strict file ownership** so parallel work
never collides (`CLAUDE.md`, `TEAM_PLAN/`):

| unit | person | owns |
|---|---|---|
| **A** | Arjhun | `models/`, `train/`, `inference/uncertainty.py`, `products/observation_priority.py`, `docs/{ARCHITECTURE,MODEL_SPEC,DECISIONS}.md`, and in Phase 2 `src/phase2/{physics,events,reliability,derived,validation,export,api}` |
| **B** | Darshan | scaffold, `config.py`, `config/`, `utils/`, `data/`, `features/`, `inference/predict.py`, `app/streamlit_app.py`, `docs/{MASTER_SPEC,DATA_CONTRACT,DEMO_SPEC}.md`, `CLAUDE.md` |
| **C** | Mitun + Niru | `climatology.py`, `validation/`, `products/anomaly.py`, `app/panels/`, `docs/{VALIDATION_PROTOCOL,LITERATURE_MATRIX,NOVELTY_MATRIX,EXPERIMENT_LOG}.md` |

Cross-machine coordination happens in `docs/phase2/AGENT_SYNC.md` (**214 KB**, ~46 numbered
exchanges — A1–A23 from Arjhun, D1–D11 from Darshan) and `docs/HANDOFF.md` (33 KB), appended by
everyone. Data moves between machines by zip, never through git, with SHA-256 for every file
recorded in `PHASE2_DATA_MANIFEST.json` (62 files).

---

<a name="s3"></a>
## 3. Branch and merge topology

### 3.1 Branches **[VERIFIED]**

Remote branches that still exist:

```
origin/main                    <- integration
origin/phase2-tscast-nio       <- the v2 model line
origin/phase2-reliability
origin/phase2-viz-foundation   <- the shared foundation for the 9-feature suite
origin/phase2-viz-transect
origin/phase2-viz-uncertainty
origin/phase2-novelty-acoustics
origin/feat/argo-overlay
origin/feat/cyclone-heat
```

Local branches (many track branches deleted on the remote after merge):

```
phase2-novelty-cloud-dropout  <- HEAD, 139cb7e
main, backup-arjhun-pre-merge, docs/status-report,
feat/{argo-overlay, cyclone-heat, spec-compliance, unit-a-mlp, unit-a-priority, unit-c-coverage},
phase2, phase2-collocation, phase2-events, phase2-novelty-acoustics, phase2-ocean-cube,
phase2-physics, phase2-reliability, phase2-tscast-nio, phase2-validation,
phase2-viz-foundation, phase2-viz-transect, phase2-viz-uncertainty
```

Branch names use a **hyphen**, never a slash after `phase2`: `phase2` exists as a branch and a git
ref cannot be both a branch and a directory, so `phase2/feature` is impossible. This was learned by
hitting it.

### 3.2 Divergence right now **[VERIFIED]**

`git rev-list --left-right --count origin/main...HEAD` → **`0   26`**

**HEAD is 26 commits ahead of `origin/main` and 0 behind.** Everything Darshan has pushed is merged
in; twenty-six of Arjhun's commits are not pushed. That is the largest unpushed backlog in the
project's history and is the highest-risk operational item in §16.

### 3.3 The seventeen commits since the previous compilation (`189713f`) **[VERIFIED]**

```
4a1dc9b  Feature: transect tool -- depth-vs-distance cross-sections (Prompt 6)     [Darshan]
3696622  AGENT_SYNC: answer A17, report the transect push, confirm clean trial merge
283a182  Stage 2 does NOT improve temperature -- seed 42 was the lucky leg
6d3a826  physics_page wired to stage 2 -- and the wiring measured why not to trust two of it
2f245f3  AGENT_SYNC A18: stage 2 trained, does not beat stage 1, two physics fields unusable
4c43fd1  Merge origin/main: Darshan's transect tool (Prompt 6) + his A17 answer
6bb088f  Prompt 6 verified. A missing D26 was being reported as a cold surface
d3bd22f  AGENT_SYNC A19: Prompt 6 verified, and the missing-value pattern named
f4742d9  START_HERE rule 8: an absence is not a value
d9ff4aa  Prompt 7: export a reconstruction to NetCDF, and serve it            (+1,605 lines)
dd8ec6d  Foundation for the 9-feature suite: sound speed, honest depth-finders, one field cache
9747688  Probe the two external sources before building on either: one is real, one is unreachable
46ff74b  F1: click any of the 24,000 cells, get that cell's profile (port 8512)
7af3e71  predict_field's device argument moved the batch but not the weights, so it never worked
fd6952f  F3: uncertainty as transparency, and the spec's acceptance check replaced (port 8513)
d915f93  F7: sound speed, the sonic layer, and a SOFAR axis this grid cannot see (port 8514)
139cb7e  F2: transect upgrades -- and three bugs in the page they were built on
```

Test count over that span: **611 → 628 → 681 → 745 → 768 → 782 → 800 → 820**.

> **A naming collision worth knowing about.** There are **two** independent F-numbering schemes in
> this repo. The Phase-2 architecture audit numbers F1–F10 (F1 collocation, F2 OceanCube, F3
> spatial CNN, F4 uncertainty+OOD, F5 physics, F6 events, F7 subsurface heatwave, F8 validation
> lab, F9 sentinel, F10 priority v2). The later "9-feature visualisation/novelty spec" re-uses
> F1–F9 for entirely different things (F1 click map, F2 transect upgrades, F3 uncertainty map,
> F4 cyclone case study, F6 moored buoys, F7 acoustics…). **A bare "F5" is ambiguous in this
> repository.** §12 uses the visualisation numbering; `PHASE2_STATUS.md` uses the audit numbering.
---

<a name="s4"></a>
## 4. Technology stack — every library, and why

**Language / runtime:** Python 3.12.3 on Windows 11 (`AMD64`, Ryzen-class), plus an NVIDIA GeForce
RTX 4050 Laptop GPU. Packaged with `setuptools` via `pyproject.toml` (`oceanembed 0.1.0`,
`requires-python >= 3.10`, src-layout, pytest `pythonpath = ["src"]`).

**[VERIFIED — `requirements.txt`, `pyproject.toml`, `artifacts/export_timing.json`]**

| layer | library | role | notes recorded in the repo |
|---|---|---|---|
| numerics | `numpy` | every array | — |
| tables | `pandas`, `pyarrow` | Argo tables, metrics frames | parquet with a **CSV fallback** if pyarrow is absent (D-006) |
| gridded I/O | `xarray`, `netCDF4` | reading CMEMS products, writing the export | NetCDF has no bool → masks are written as `int8` flags |
| science | `scipy` | interpolation, filters | — |
| ocean data | `copernicusmarine` | GLORYS12V1 + satellite L4 download | needs a free CMEMS account |
| ocean data | `argopy` | independent Argo float profiles | **`erddapy<3` pinned** — argopy 1.4.0 imports a private symbol removed in erddapy 3.x |
| TLS | `certifi` | Windows SSL fix | `download_argo` sets `SSL_CERT_FILE` from it |
| ML | `torch` 2.13.0+cu126 | the MLP (v1) and TS-Cast-NIO (v2) | CUDA **is available** and the inference path deliberately does **not** use it by default (§16) |
| ML | `lightgbm` | per-depth baseline + quantile uncertainty | one booster per depth; quantiles in a separate artifact (D-012) |
| ML | `scikit-learn` | metrics, scaling utilities | — |
| UI | `streamlit` 1.62.0 | fourteen dashboards | pins `starlette<2,>=0.46.0` — the reason FastAPI had to be gated |
| charts | `altair` / Vega-Lite | almost all 2-D charts | chosen after plotly was found not installed on one machine |
| charts | `plotly` | the 3-D volume only | the cube degrades to a 2-D altair slice when plotly is absent |
| charts | `matplotlib` | offline figures | — |
| API | `fastapi` + `uvicorn` | the HTTP export service | taken **only** for the `/docs` page; `service.py` imports no web framework so a starlette fallback costs ~40 lines |
| test | `pytest` | 820 tests | — |

**The dependency decision worth recording.** FastAPI was installed only after a dry-run resolution
report was read, and the install order was `fastapi → streamlit → copernicusmarine`, in that order,
because the risk was to **Streamlit**, not the data pipeline: `copernicusmarine` has no starlette
dependency, and Streamlit pins starlette. **Verified afterwards: starlette stayed at 1.6.0 and all
ten then-existing pages still loaded.** **[VERIFIED]**

**Not used, with reasons on the record:** GNN (*"a uniform 0.25° lat/lon lattice has no irregular
graph structure; message passing there reduces to convolution with extra machinery and no graph to
exploit"*); ConvLSTM (only 48 monthly timesteps existed when the choice was made); any pretrained
foundation model (nothing in scope).

---

<a name="s5"></a>
## 5. Full subsystem inventory — what was built

### 5.1 `src/oceanembed/` — the Phase-1 core (still live, still imported)

| file | lines | what it does |
|---|---|---|
| `config.py` | 74 | the single source of truth: REGION, LAT/LON, DEPTHS, FEATURES, split, SEED, paths, `sanity_check()` |
| `climatology.py` | 51 | monthly climatology + interannual σ from the train years only |
| `data/download_glorys.py` | 100 | resumable, date-subsampled CMEMS GLORYS downloader |
| `data/download_satellite.py` | 98 | satellite L4 downloader (OSTIA / DUACS / Multiobs) |
| `data/download_argo.py` | 167 | argopy fetch → interpolate each profile onto `DEPTHS` |
| `data/preprocess.py` | 129 | memory-safe regrid to 0.25° + land mask + provenance stamp |
| `data/preprocess_satellite.py` | 158 | the same operator applied to satellite L4 |
| `features/build_samples.py` | 106 | `(N, 11)` feature matrix in `FEATURES` order, **raw units** |
| `models/mlp_profile.py` | 148 | `MLPProfile` 11→128→128→15, dropout 0.2; **normalisation buffers ride inside the checkpoint** (D-007); fixture-provenance stamp (D-010) |
| `models/lgbm_baseline.py` | 154 | one LightGBM booster per depth + separate quantile boosters (D-012) |
| `train/train_mlp.py` | 190 | MLP trainer, best-held-out-epoch checkpointing |
| `train/train_lgbm.py` | 126 | baseline trainer |
| `train/_data.py` | 121 | **one loader shared by training and evaluation** (D-014) |
| `train/compare_models.py` | 206 | head-to-head with the 2 %-gap tie rule (D-015) |
| `inference/predict.py` | 330 | `reconstruct()` / `reconstruct_grid()` — the frozen seam the UI consumes |
| `inference/uncertainty.py` | 105 | MC-dropout mean/σ, seeded; train-mode leak fixed (D-017) |
| `products/anomaly.py` | 117 | anomaly in °C and in σ, kept as two separate functions |
| `products/observation_priority.py` | 127 | weighted **geometric mean** of anomaly × uncertainty × Argo-sparsity; degenerate factors treated as neutral; land stays NaN |
| `validation/metrics.py` | 78 | RMSE / correlation / bias per depth |
| `validation/validate_argo.py` | 212 | independent-Argo scoring with two honesty gates |
| `utils/{io,grids}.py` | 110 | parquet-with-CSV-fallback tables, grid helpers |

### 5.2 `src/phase2/` — the Phase-2 modules

| module | lines | what it does |
|---|---|---|
| `basins.py` | 172 | **one canonical** Arabian Sea / Bay of Bengal partition, so per-basin numbers cannot drift |
| `data/collocation.py` | 472 | multi-source collocation: model / GLORYS / satellite / Argo at one point, two eras; `argo_coverage()` so an empty match is reported as a table gap, never as an empty ocean |
| `data/extract_subsurface.py` | 124 | salinity and u,v at all 36 GLORYS levels (Phase 1 had taken index 0 only) |
| `data/download_wind{,_daily}.py` | 382 | monthly wind + stress, and the hourly→daily-mean L4 pipeline |
| `data/download_satellite_daily.py` | 153 | the daily satellite L4 fetch |
| `physics/seawater.py` | ~210 | one-atmosphere EOS-80 **plus Mackenzie 1981 sound speed**; all 15 EOS constants checked against 4 published UNESCO values to < 1e-3 kg m⁻³, including ρ(35, 25) = 1023.343 |
| `physics/layers.py` | 166 | MLD by the **density** criterion (de Boyer Montégut 2004, 0.03 kg m⁻³ from 10 m), ILD, **barrier layer**, thermocline |
| `physics/ohc.py` | 141 | ocean heat content with real ρ(S,θ), plus a constant-density variant that names its own error |
| `events/eddy.py` | 169 | Okubo–Weiss eddy detection |
| `events/fronts.py` | 117 | SST-gradient fronts |
| `events/upwelling.py` | 282 | upwelling signature + Ekman pumping, with a climatological SST reference |
| `events/_metric.py` / `_realdata.py` | 248 | spherical derivatives; structural real-data gate |
| `cube/ocean_cube.py` + `volume.py` | 502 | the reconstructed 3-D volume; sea floor enforced as a **refusal**; plotly volume with a 2-D altair fallback |
| `validation/lab.py` | 379 | Validation Lab — measures **the reanalysis itself** against Argo, so inherited error is separated from model error |
| `validation/argo_overlay.py` | 213 | model profile ± 2σ against one independent float |
| `validation/dropout.py` | 142 | **new, uncommitted** — sensor-dropout masking in physical units (§10) |
| `derived/heat_content.py` | 289 | TCHP / OHC / D26 for cyclone potential |
| `derived/transect.py` | ~300 | depth-vs-distance sections, bilinear sampler, `contour_line`, `slide` |
| `derived/profile_features.py` | 268 | depth-finders that return **(value, reason)** — six reasons, so a bare NaN never conflates land, too-few-levels, never-attained, crossed-the-other-way and grid-edge |
| `derived/mapframe.py` | 128 | one depth level as clickable cells, classified land / below-seafloor / water **once**, in the library |
| `derived/acoustics.py` | 192 | sonic layer depth, SOFAR axis, sound-speed envelope |
| `export/netcdf.py` | 184 | `field_to_xarray` / `write_netcdf` / `to_bytes` / `export_field` |
| `api/service.py` | 152 | every API decision; **imports no web framework** |
| `api/app.py` | 80 | a thin FastAPI adapter over `service.py` |
| `viz_explainer.py` | 162 | the shared page footer, **validated rather than trusted**: a formula with no symbol note raises, a placeholder raises, a caveat with no evidence raises |

### 5.3 `src/phase2/tscast_nio/` — the v2 model

Reimplemented from the published description of **TS-Cast** (Chae, Donohue & Park, *Ocean Science*
22, 2161–2177, 2026). Their code was never released; nothing is copied.

| file | lines | what it does |
|---|---|---|
| `models/tscast.py` | 433 | `TSCastNIO`: encoder → decoder → temperature + log-variance heads; `FiLM` (paper eq. 2); `ClimatologyUNet`; `gaussian_nll` (eq. 3) with β-NLL; `density_nll` (eq. 5); `depth_interp_matrix` for the fixed 15↔64 resampling; `assert_architecture_matches` |
| `encoders.py` | 170 | the **four bake-off candidates** — `MLPControl` (centre cell only), `CNN3D` (the paper's), `CNNAttention`, `ViT` — with a **shared identical `ProfileHead`** so the encoder is the only variable |
| `dataset.py` | 375 | `GriddedPatches` — P = 17 patches (±2.0°), T_SEQ-day windows, the split embargo |
| `train/train_stage1.py` | 573 | stage-1 trainer: T + log-var, β-NLL, best-held-out-epoch, per-depth Argo scoring, full metrics JSON |
| `train/train_stage2.py` | 495 | stage-2 trainer: + salinity head + the eq. 5 density constraint; refuses to run without an Argo table carrying salinity; takes `--seed` |
| `inference.py` | 286 | the predictor; the checkpoint declares its own bundle so the predictor stops guessing |
| `field.py` | ~225 | grid-wide `predict_field`, `v2_cache_version`, `_promoted_from`, device handling |
| `field_cache.py` | 173 | **one predictor, one lock, one cache key** across every page |
| `metrics.py` | 300 | per-depth RMSE / correlation / bias / **two** skill definitions, both returned because they are not interchangeable |
| `calibrate.py` | 153 | post-hoc per-depth variance scaling |
| `eval_argo.py` | 88 | independent-Argo scoring |
| `output.py` | 253 | the frozen output schema; `_calibration_applies_to` matches **stage first** |
| `provenance.py` | 159 | assembles the ten-key provenance block once and **asserts** the schema contract holds |
| `daily_pipeline.py` / `sat_daily_pipeline.py` | 632 | build the daily GLORYS and daily satellite bundles |
| `ui_tables.py` | 202 | the tables the dashboard renders, asserted equal to the metrics artifact |

**Architecture, and where it deliberately departs from the paper** **[VERIFIED by reading the
source and `config.py`]**:

* **Encoder** — bake-off winner `cnn3d` → a 128-dim latent (the PS's "compact satellite embedding").
* **Decoder** — the paper's idea is a 1-D U-Net whose *input is the monthly climatology*, not the
  satellite data: the network **adjusts a physically-grounded average** rather than guessing a
  profile from scratch. FiLM (γ·x + β) injects the satellite latent at every encode/decode step.
* **15 depths, not the paper's 128.** Four stride-2 downsamples need far more than 15 levels, so the
  U-Net runs on an internal **64-level** grid with a fixed linear-interpolation matrix mapping
  15 → 64 in and 64 → 15 out. The frozen output contract is untouched.
* **Widths cut for our data.** At the paper's widths the model is **7,118,474 parameters** (519 k
  encoder, 6.6 M decoder, of which **3.0 M is FiLM alone**) against **543,383** for the encoder+head
  the bake-off actually validated. That is **13.1× the capacity on 100 k samples**, and it overfits
  by epoch 3 regardless of the loss — β-NLL removed the variance collapse (train NLL −1.0610 →
  −0.2025) and the best epoch stayed at 3. So `LATENT_DIM = 128`, `UNET_CHANNELS = (32,64,128)`;
  the paper's `(64,128,256,512)` is kept in the config for the record.
* **The FiLM decoder is built but NOT shipped.** `decoder="simple"` — the bake-off head — is the
  only decoder ever scored against Argo, and stage 2 refuses to run on anything else with an
  explicit error: *"FiLM was MEASURED to cost accuracy."*
* **Residual output** (`residual=True`): the network predicts a *correction* to the current month's
  climatology. The paper does not state this; it is our reading of "adjust the average", kept behind
  a flag so the claim stays testable.
* **σ does not depend on the satellite input.** The log-variance head reads only the climatology
  embedding — the paper's design, stated rather than quietly "fixed".
* **There is deliberately no `TRAIN` dict in the config.** One used to sit there reading
  `epochs=250, lr=1e-5, batch_size=512` — values nothing in the codebase read and no run ever used
  (the real defaults are 25 / 1e-3 / 256, in argparse). *"A frozen constant that no code imports and
  no experiment used is worse than an absent one: it reads as the contract while the CLI quietly
  decides."*

### 5.4 `scripts/` — 42 committed scripts, 6,791 lines (43 / 7,044 including the uncommitted one)

The load-bearing ones:

| script | lines | what it guarantees |
|---|---|---|
| `phase2/accept.py` | ~830 | the acceptance gate — including a stage-2 gate that **cannot pass by importing**, and a `viz foundation` check of 8 falsification assertions |
| `phase2/freeze.py` | 194 | re-verifies the freeze rather than trusting the manifest; **18 checks** |
| `phase2/freeze_headline.py` | 324 | byte-identity manifest builder; proven to fail on a tampered file |
| `phase2/audit_ps.py` | 184 | opens an artifact per PS clause — *"a requirements matrix written by hand records what someone believed on the day they wrote it"* |
| `phase2/verify_sat_bundle.py` | 221 | 44 provenance + lineage checks, incl. a **negative test that catches GLORYS injected into all five satellite channels** |
| `phase2/verify_daily_bundle.py` | 282 | refuses, does not warn |
| `phase2/run_sat_ablations.py` | 194 | the 3-seed channel-ablation harness — **requires three seeds before a sign is believed** |
| `phase2/run_cloud_dropout.py` | 253 | **new, uncommitted** — the cloud-dropout harness (§10) |
| `phase2/score_by_basin.py` | 177 | per-basin scoring off one canonical partition |
| `phase2/calibrate_uncertainty.py` | 197 | per-depth σ scaling, fitted on train-window Argo, reported on test-window Argo |
| `phase2/rescore_checkpoint.py` | 182 | re-scores a `.pt` from disk instead of trusting its sibling JSON |
| `phase2/promote_run.py` | 160 | promotion writes `promoted_from` + sha256 |
| `phase2/export_field.py` | 73 | reconstruct → NetCDF; **refuses an out-of-bundle date** rather than snapping |
| `phase2/measure_export_timing.py` | 123 | replaced an `[INFERRED]` cost claim with a measurement |
| `phase2/probe_incois_las.py` | 122 | reproduces the INCOIS probe; exits non-zero while the data layer is down |
| `phase2/probe_ibtracs.py` | 146 | cyclone best-track probe (§6.8) |
| `phase2/probe_buoys.py` | 203 | moored-buoy reachability probe (§6.8) |
| `phase2/stage2_seed_check.py` | 116 | the 3-seed stage-2 matcher (§15.6) |
| `phase2/fetch_argo_ts_daily_period.py` | 111 | the T+S Argo fetch, with guards that refuse to touch the two existing tables |

### 5.5 `tests/` — 55 committed files, 10,098 lines (56 / 10,305 including the uncommitted one)

**Run live during compilation of this document** (`.venv/Scripts/python.exe -m pytest -q`, exit
code 0) **[VERIFIED — 2026-09-05]**:

```
820 passed, 9 skipped, 274 warnings in 934.04s (0:15:34)
```

That matches the count in the HEAD commit message exactly. The 274 warnings are all third-party
deprecations (numpy timedelta units, xarray/netCDF4 shape assignment, a LightGBM sliced-data
notice) — **none originates in project code**. The run does *not* include the 15 new dropout tests,
which were written after collection started.

The suite grew with the work and every step is traceable in `docs/HANDOFF.md` and the commit
messages: `530 → 547 → 554 → 557 → 561 → 566 → 571 → … → 611 → 613 → 628 → 681 → 745 → 768 → 782 →
800 → 820`.

Largest test files: `test_tscast_stage2.py` (543), `test_events.py` (443), `test_collocation.py`
(287), `test_wind_daily.py` (286), `test_physics_v2.py` (276), `test_panels.py` (263),
`test_cube.py` (256), `test_profile_features.py` (253), `test_tscast_model.py` (252),
`test_field_cache.py` (246), `test_validation.py` (238), `test_transect_upgrades.py` (237),
`test_acoustics.py` (232), `test_tscast_dataset.py` (217), `test_volume.py` (216),
`test_mapframe.py` (203), `test_viz_explainer.py` (193), `test_uncertainty_map.py` (189).
---

<a name="s6"></a>
## 6. Data: every dataset downloaded, processed and trained on

### 6.1 On-disk footprint **[VERIFIED — measured 2026-09-05]**

```
data/raw          28   GB          data/processed    3.0 GB          artifacts   222 MB
------------------------------     ------------------------------
glorys_daily      23   GB          daily             497 MB   <- GLORYS comparator input
wind_daily         3.4 GB          daily_sat         463 MB   <- THE DELIVERABLE'S INPUT
satellite_nrt      1.1 GB          daily_hybrid_sst  466 MB
satellite_daily  279   MB          daily_hybrid_ssh  462 MB
currents_nrt      82   MB          daily_hybrid_sss  462 MB
wind              22   MB          daily_hybrid_glocur 461 MB
ibtracs            9.8 MB          subsurface.npz     74 MB
synthetic_glorys   9.3 MB          wind_daily.npz     57 MB
rama               0   B  (empty - the blocked buoy fetch, see 6.8)
                                   grids.npz          31 MB
                                   satellite_grids.npz 4.3 MB
```

`data/` and `artifacts/` are **gitignored** — nothing here travels through git. The `.gitignore`
anchors `/data/` with a leading slash on purpose: *a bare `data/` would also match
`src/oceanembed/data/`, our source module, and silently drop it from the repo* (this actually
happened once and is one of the five bugs rule 7 caught). Two exceptions are whitelisted: the tiny
fixtures, and `frozen_manifest.json`, because *"it is the only thing that lets another machine prove
its checkpoints are the ones that were scored."*

Transfer between the two machines is by zip, documented in `README_UNZIP_ME_FIRST.txt`, with the
SHA-256 of every file recorded in `PHASE2_DATA_MANIFEST.json` (62 files, 16-hex checksums).

### 6.2 The satellite daily bundle — `data/processed/daily_sat/v001` (THE deliverable's input)

**388 consecutive days, 2025-06-01 → 2026-06-23, 0 gaps, 0 days dropped.** **[VERIFIED]** —
`freeze.py` counts them from the files and `audit_ps.py` re-counts them independently.

Array layout, read from the npz:

```
times         (214,)              datetime64[D]     # the 2025 file; 2026 holds the other 174
surface       (214,100,240,7)     float32           # the 7 INPUT channels
temp          (214,100,240,15)    float32           # the GLORYS TARGET
salinity      (214,100,240,15)    float32           # GLORYS, target-side
land_mask     (100,240)           bool
valid_mask    (100,240,15)        bool
channels      ['sst','sss','ssh','u','v','wu','wv']
units         ['degC','psu','m','m s-1','m s-1','m s-1','m s-1']
missing_days  ()                  empty
provenance    6,060-character JSON blob embedded INSIDE the file
```

**Every input channel with its real product** (read from the embedded provenance) **[VERIFIED]**:

| ch | product | provider | class | native | processing |
|---|---|---|---|---|---|
| `sst` | `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` (OSTIA: AVHRR, VIIRS, AMSR2, SEVIRI) | UKMO | SATELLITE_DERIVED | 0.05°, K | K→°C, bilinear to 0.25°, GLORYS land mask |
| `sss` | `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` (SMOS **blended with in-situ**, Buongiorno Nardelli 2016) | CNR | SATELLITE **+ INSITU_BLEND** | 0.125° | bilinear to 0.25° |
| `ssh` | `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` (DUACS multi-mission altimetry) | CLS/CNES | SATELLITE_DERIVED | 0.125°, m | bilinear; `adt` vs GLORYS `zos` offset **deliberately not corrected** |
| `u`,`v` | `cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m` (GLOBCURRENT total = geostrophic + Ekman) | CLS/CNES | SATELLITE_DERIVED | 0.25°, **offset half a cell** | bilinear half-cell shift |
| `wu`,`wv` | `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | CMEMS | SATELLITE_DERIVED | 0.125°, hourly | hourly → daily mean, block-averaged **by coordinate, never by position** |

**Target:** `GLORYS12V1 daily` (`cmems_mod_glo_phy_my_0.083deg_P1D-m`). `temp`, `salinity`,
`land_mask` and `valid_mask` are copied from the GLORYS bundle **unchanged**. Satellite is the
INPUT; GLORYS is the TARGET; the provenance says so explicitly so they cannot be conflated.

**Four limitations recorded in the bundle itself, not in a doc that could drift:**

1. **A documented PS deviation.** Currents come from CMEMS GLOBCURRENT rather than the PS's PO.DAAC
   `OSCAR_L4_OC_FINAL_V2.0` — no NASA Earthdata login was available. Same quantity, same 0.25°
   daily grid. Recorded in the bundle, in `FREEZE_MANIFEST.json`, and checked by `freeze.py`.
2. **Edge policy.** The first row (lat 5.0) and first column (lon 45.0) are NaN in every satellite
   channel — each native grid starts inboard of our domain edge (sst 45.025, ssh/sss 45.0625,
   currents 45.125). NaN is deliberate: extrapolating an unobserved coastline would fabricate data.
   Cost ≈ **1.4 %** of cells.
3. **The SSS sensor limit — the most consequential one.** Measured on 5 days against GLORYS: the
   satellite SSS product **floors at 30.78 psu where GLORYS reaches 9.72**, and Unit B independently
   measured **6.43 psu at 22.50 N 91.25 E** (the Meghna/Ganges plume). *The satellite input is blind
   to the single most distinctive feature of the Bay of Bengal.* This is a sensor limit, not a
   modelling gap.
4. **Land-mask source.** Taken from GLORYS, because satellite SST contains inland water — a Tibetan
   lake at 3.81 °C sits inside our lat/lon box.

**Missing-data policy:** a day is included only if *every* satellite channel exists for it, plus a
GLORYS target and wind. **No imputation anywhere.**

### 6.3 The GLORYS daily bundle — `data/processed/daily` (comparator)

Same 388 days, same shapes, same target. The five surface channels are GLORYS reanalysis instead of
satellite; `wu`/`wv` are identical in both bundles because wind was always observational.
`salinity` is **byte-identical between the two bundles** — both carry the same GLORYS12V1
target-side field. **[VERIFIED]** This matters: it is why a "v2 satellite" MLD computed from that
salinity would put a reanalysis field inside a number labelled satellite, and why `physics_page`
refuses it.

### 6.4 The four hybrid bundles — `data/processed/daily_hybrid_{sst,sss,ssh,glocur}/v001`

Purpose-built for the channel-isolation experiment (§9.4): each is the satellite bundle with
**exactly one** channel (or channel pair) swapped back to GLORYS, so the Arabian Sea penalty can be
attributed to a specific input. Four bundles × 3 seeds = **12 additional training runs**, ~1.85 GB
of purpose-built data for one negative result.

### 6.5 The Phase-1 monthly bundle (still used by several panels)

| file | size | contents |
|---|---|---|
| `data/processed/grids.npz` | 31 MB | 48 monthly steps 2019-01-15 → 2022-12-15; temperature `(48,100,240,15)` + surface + masks |
| `data/processed/subsurface.npz` | 74 MB | salinity and u,v at all 36 GLORYS levels → real ρ(S,θ) for OHC |
| `data/processed/satellite_grids.npz` | 4.3 MB | OSTIA / DUACS / Multiobs, 24 of the 48 dates |
| `data/raw/wind/` | 22 MB | 48 monthly wind + wind-stress files, 2019-01 → 2022-12 |

`artifacts/provenance.json`: `source = real-glorys`, built 2026-08-25T17:56:42, 15 depths,
**n_train 323,028 / n_test 107,676**, x_units raw.

### 6.6 Argo — independent validation, never used in training

Five parquet tables, all built with argopy:

| table | rows / profiles | window | variables | used by |
|---|---|---|---|---|
| `argo_test.parquet` | 32,836 rows / 2,455 profiles | **2022 only** | T | Phase-1 validation, collocation `phase1` era |
| `argo_2025.parquet` + `argo_2026.parquet` | — | 2025 / 2026 | T | source for the daily-period table |
| `argo_daily_period.parquet` | — | 2025-06-01 → 2026-06-23 | T | **the 962 profiles / 12,829 depth comparisons behind every v2 number** |
| `argo_ts_2025` + `argo_ts_2026` → **`argo_daily_period_ts.parquet`** | **59,066 rows / ~4,334 profiles** | 2025-06-01 → 2026-06-23 | **T and S**, salinity on 100.0 % | stage 2 (built 2026-09-04) |

The T+S table was fetched on 2026-09-04 with three guards, all of which passed **[VERIFIED,
recorded in `docs/EXPERIMENT_LOG.md`]**:

* the two pre-existing tables were left **untouched**;
* salinity present on **100.0 %** of profiles;
* **temperature identical where the tables overlap — max |difference| 0.000000 °C across 59,039
  rows.** That last check is what makes stage-2 salinity comparable to the stage-1 headline: it
  sits on the same profiles.

Collocation tolerance for scoring: **≤ 5 days** offset. The Phase-1 reanalysis-vs-Argo study
(`glorys_vs_argo.json`) reports collocation distance max 18.7 km / mean 10.5 km / p95 16.5 km.

### 6.7 Climatology

`artifacts/climatology.npy` and `climatology_std.npy`, `(12,100,240,15)` = [month, lat, lon, depth],
17 MB each, built from **2019–2021 only** (the train years — deliberately not the daily split, so it
cannot leak). `clim_daily.npz` (5.6 MB) is the daily-bundle prior. The climatology is both the
decoder's physical prior and the skill denominator: `rmse_climatology = 1.2259 °C` on the exact
points every v2 skill number uses.

### 6.8 Two external sources probed before any code was written against them

`docs/phase2/EXTERNAL_DATA_PROBE.md`, `scripts/phase2/probe_ibtracs.py`, `probe_buoys.py`.
Probed 2026-09-05. *"A case study must come from an archive, never from a storm someone
remembered."*

**Cyclone tracks — UNBLOCKED [VERIFIED].** IBTrACS v04r01 (NOAA NCEI), `last3years` CSV, 10.3 MB,
fetched to `data/raw/ibtracs/`. **15 North Indian systems** have track points inside
2025-06-01 … 2026-06-23; four reach tropical-storm strength with ≥ 10 points inside the grid box:

| SID | name | dates | pts | in box | max wind | extent |
|---|---|---|---|---|---|---|
| 2025275N22068 | **SHAKHTI** | 2025-10-01 → 10-07 | 47 | 47 | **74 kt** | 18.9–22.1 N, 60.1–68.3 E |
| 2025298N11089 | MONTHA | 2025-10-25 → 10-29 | 39 | 39 | 50 kt | 10.8–19.6 N, 80.7–89.0 E |
| 2025331N06083 | DITWAH | 2025-11-26 → 12-02 | 49 | 49 | 40 kt | 5.9–13.0 N, 80.2–82.6 E |
| 2025274N16087 | (unnamed) | 2025-10-01 → 10-03 | 17 | 17 | 35 kt | 15.9–21.2 N, 83.6–86.5 E |

**The correction this probe existed to catch:** the build spec proposed *"Biparjoy or Mocha"*. Both
are **2023** storms and neither appears anywhere in our window — hardcoding either would have drawn
a track over a field from a different year. Also recorded: recent IBTrACS seasons are
**provisional** (`TRACK_TYPE` kept per storm), and **a blank `WMO_WIND` is missing, not zero** —
KAJIKI and BUALOI read 0 kt only because both wind columns are empty.

**Moored buoys — BLOCKED here, but the data is confirmed to exist [VERIFIED].** Same shape as the
INCOIS probe: catalogue healthy, data layer not.

```
ok    1.1-1.7 s   data.pmel.noaa.gov ERDDAP /info, /tabledap/*.das, /files listing
ok    1.7 s       osmc.noaa.gov /info for the same dataset
FAIL 43.5-43.8 s  every request returning actual DATA, on BOTH hosts
FAIL              /files download 302s to http://coastwatch.pfeg.noaa.gov -- timeout over HTTP,
                  SSL UNEXPECTED_EOF over HTTPS; upgrading the redirect to TLS does not help
```

`pmelTaoDyT` (TAO/TRITON, RAMA, PIRATA daily temperature) covers **1977-11-03 → 2026-07-03**, which
*contains* our window, and **five moorings sit inside the box** (8 N 67 E, 8 N 90 E, 12 N 90 E,
15 N 65 E, 15 N 90 E; 4.3 MB total). Whether the cause is a NOAA outage or this network is
**[UNKNOWN]** — it reproduces across three hosts, which argues against one server being down.

**The question that decides the feature is still unanswered:** whether those five moorings carry
finite temperature on days inside our window. RAMA has had long servicing gaps in the northern
Indian Ocean and a 1977–2026 span says nothing about 2025–26. `buoy_probe.json` records this as
`coverage_days_in_window: null` **with a note** rather than omitting the field — *"an unmeasured
quantity absent from an artifact reads as one nobody thought of."*

The probe also **refuses to blame INCOIS** for a `CERTIFICATE_VERIFY_FAILED` raised by this
machine's own trust store, and points at the maintained INCOIS probe instead.

### 6.9 Synthetic data — where it was used, and why it was abandoned

`scripts/make_synthetic_glorys.py` (67 lines) built a stand-in so Units A and C were not blocked on
the CMEMS download. It built temperature as `exp(-z/250)` from the surface, which means **there is
no mixed layer at all** and the steepest gradient sits at the top by construction.

Unit B's sanity test `test_salinity_generally_increases_with_depth_in_the_bay_of_bengal` **failed
against the synthetic stand-in and passes on real data**. That test rejected data with the right
shape, dtype, units and plausible magnitudes but no ocean structure. **No code was changed in
response** — adjusting a scientific sanity test to accommodate synthetic data would be exactly
backwards. All physics validation was subsequently re-run on the real bundle, by both units
independently:

| check | synthetic | real (Unit A) | real (Unit B) |
|---|---|---|---|
| BoB salinity 0 → 500 m | +0.02 psu | **+4.78** | +2.80 |
| thermocline below MLD | 11.6 % | **87.8 %** of 526 k cell-dates | 84.7 % |
| barrier layer BoB vs Arabian | ~0 m | **9.5 vs 7.1 m, BoB thicker 8/12 months** | 8.3 vs 4.6 m, 10/12 |
| constant-density error (max) | 0.028 % | **0.293 %** | 0.254 % |

The last two rows differ between units because of **different box definitions**, not because either
run is wrong; the qualitative conclusion is identical and it is the conclusion that is claimed.
Unit B's seasonality warning is confirmed: the BoB barrier layer peaks in March (19.6 m) and through
the monsoon while the Arabian Sea wins Dec/Jan/Feb/Apr — **a single-date check inverts this signal.**
---

<a name="s7"></a>
## 7. Every model trained — complete checkpoint inventory

**36 trained TS-Cast-NIO checkpoints** live in `artifacts/`, plus the Phase-1 MLP and LightGBM
baselines. The table below was generated by opening each run's own metrics JSON. **[VERIFIED]**

### 7.1 Phase-2 TS-Cast-NIO runs

| tag | seed | stage | input source | bundle | Argo RMSE | skill | bias |
|---|---|---|---|---|---|---|---|
| **`sat_7ch_s42`** ← **SHIPPED** | 42 | 1 | **satellite** | `daily_sat/v001` | **0.9078** | **+0.2595** | +0.1003 |
| `abl_full_s42` (same config) | 42 | 1 | satellite | `daily_sat/v001` | 0.9078 | +0.2595 | +0.1003 |
| `abl_full_s43` | 43 | 1 | satellite | `daily_sat/v001` | 0.9047 | +0.2620 | +0.0992 |
| `abl_full_s44` | 44 | 1 | satellite | `daily_sat/v001` | 0.9084 | +0.2590 | +0.0742 |
| `abl_noSSS_s42/43/44` | 42–44 | 1 | satellite − sss | `daily_sat/v001` | 0.9125 / 0.9423 / 0.9398 | +0.2557 / +0.2313 / +0.2334 | — |
| `abl_noCUR_s42/43/44` | 42–44 | 1 | satellite − u,v | `daily_sat/v001` | 0.9005 / 0.9127 / 0.9381 | +0.2654 / +0.2555 / +0.2347 | — |
| `abl_noWIND_s42/43/44` | 42–44 | 1 | satellite − wu,wv | `daily_sat/v001` | 0.8904 / 0.9115 / 0.9312 | +0.2737 / +0.2564 / +0.2404 | — |
| `canon_7ch_s42/43/44` | 42–44 | 1 | **glorys** | `daily` | 0.8789 / 0.8772 / 0.9079 | +0.2831 / +0.2845 / +0.2594 | — |
| `hybsst_s42/43/44` | 42–44 | 1 | satellite + GLORYS **sst** | `daily_hybrid_sst` | 0.8541 / 0.8819 / 0.9437 | — | — |
| `hybsss_s42/43/44` | 42–44 | 1 | satellite + GLORYS **sss** | `daily_hybrid_sss` | 0.8915 / 0.8817 / 0.9289 | — | — |
| `hybssh_s42/43/44` | 42–44 | 1 | satellite + GLORYS **ssh** | `daily_hybrid_ssh` | 0.8854 / 0.9060 / 0.9589 | — | — |
| `hyb_s42/43/44` | 42–44 | 1 | satellite + GLORYS **currents** | `daily_hybrid_glocur` | 0.8857 / 0.8982 / 0.9349 | — | — |
| `embargo_withUV_s42` | 42 | 1 | glorys | `daily` | 0.8645 | +0.2948 | +0.1105 |
| `sat_s2` (stage 2) | 42 | **2** | satellite | `daily_sat/v001` | 0.8854 | +0.2777 | +0.0831 |
| `sat_s2_s43` | 43 | 2 | satellite | `daily_sat/v001` | 0.9095 | +0.2580 | +0.1278 |
| `sat_s2_s44` | 44 | 2 | satellite | `daily_sat/v001` | 0.9158 | +0.2529 | +0.2119 |
| `withUV_s42` ⚠ | 42 | 1 | glorys | `daily` | 0.8611 | +0.2975 | **INVALID — pre-embargo, leaky** |
| `noUV_s42` ⚠ | 42 | 1 | glorys | `daily` | 0.9024 | +0.2638 | **INVALID — pre-embargo, leaky** |
| `tseq31` ⚠ | 42 | 1 | glorys | `daily` | 0.9267 | +0.2441 | **INVALID — pre-embargo, leaky** |

Also frozen elsewhere (checksums carried forward from Darshan's machine and **explicitly labelled
as not re-verified here**): `tscast_stage2_s2_nodensity` **0.8548 / +0.3027** and
`tscast_stage2_s2` (eq. 5 density loss **ON**) **0.8593 / +0.2990**.

**That pair is a reported negative result:** turning the paper's eq. 5 density constraint ON costs
accuracy (0.8593 vs 0.8548) and worsens the warm bias (+0.1598 vs +0.1055). It is published as a
negative result rather than hidden.

### 7.2 The shipped run's exact configuration **[VERIFIED — read from `tscast_stage1_metrics.json`]**

```
tag                sat_7ch_s42          ->  promoted to artifacts/tscast_stage1.pt
encoder            cnn3d                    decoder      simple   (NOT the FiLM decoder)
loss               beta-NLL, beta = 0.5     latent       128      unet_channels (32,64,128)
T_SEQ              11 (data window)         built_t_seq  1        P (patch)  17  (+/-2.0 deg)
seed               42                       residual     True
channels           sst, sss, ssh, u, v, wu, wv           input_source  satellite
daily_dir          data/processed/daily_sat/v001

train period       2025-06-01 .. 2026-03-26
test  period       2026-04-01 .. 2026-06-23
protocol           embargoed_v2             n_targets_embargoed  5
train_samples      60,000                   test_samples  12,000
epochs_requested   25    epochs_run 9       best_epoch 4          patience 5
lr                 1e-3  weight_decay 0.01  batch_size 256
device             cuda                     train_seconds 550.7
params             encoder 507,848  +  decoder 40,734   =  548,582
code_commit        a67feea
argo               962 profiles, n = 12,829 depth comparisons, max 5 days offset
sha256             53848bb52533752d15a4e25f6e0fb038297bd32671606b290dd0260e991441ae
bytes              2,214,831
```

**The model is small.** 548,582 parameters, 2.2 MB on disk, 550 seconds of training on one laptop
GPU. That is a deliberate outcome of the capacity measurement in §5.3, not a shortcut.

### 7.3 Phase-1 (v1) models

| artifact | size | what |
|---|---|---|
| `mlp_model.pt` | 84 KB | `MLPProfile` 11→128→128→15, dropout 0.2, normalisation buffers inside the checkpoint |
| `lgbm_model.pkl` | 21.8 MB | 15 LightGBM boosters, one per depth |
| `lgbm_quantiles.pkl` | 44.3 MB | q10/q90 boosters (D-012) |

Phase-1 headline (`artifacts/argo_error_by_depth.json`, 879 independent Argo profiles):

```
satellite-driven   RMSE 0.9638   MAE 0.6225   skill vs climatology  0.3871
GLORYS-driven      RMSE 0.9736   MAE 0.6234   skill vs climatology  0.3809
climatology        RMSE 1.5725
```

### 7.4 The encoder bake-off **[VERIFIED — `architecture_feasibility.json`]**

Ranked on **held-out independent-Argo RMSE**, not on the train/test gap. The brief asked for the
smallest gap; that was rejected in writing because *"a model too weak to fit anything has a
near-zero gap, so the blind MLP control could win and we would wrongly conclude no embedding is
needed."* The gap is reported as a stability diagnostic instead.

| candidate | params | train loss | held-out loss | gap | **Argo RMSE** | corr | bias | train s |
|---|---|---|---|---|---|---|---|---|
| **`cnn3d`** ← winner | 543,383 | 0.0818 | 0.1434 | 0.0616 | **0.9891** | 0.9038 | +0.105 | 3,264 |
| `cnn_attention` | 457,039 | 0.0823 | 0.1348 | 0.0524 | 1.0198 | 0.8981 | +0.138 | — |
| `mlp_control` (centre cell only) | 369,807 | 0.1015 | 0.1252 | 0.0237 | 1.0566 | 0.899 | +0.262 | 85 |
| `vit` | — | — | — | — | — | — | — | — |

Conditions: monthly archive, T_SEQ = 1 (the daily bundle had not landed), 5 channels, P = 17,
40,000 train samples, 12,000 held-out GLORYS, 897 Argo profiles, 15 epochs, seed 42, AdamW,
lr 1e-3, all candidates within ~1.5× on parameter count.

**Note the shape of this result.** `mlp_control` — which sees only the centre cell, i.e. exactly the
information the Phase-1 per-column model had — has the *smallest* generalisation gap and the *worst*
Argo error. That is the entire justification for a spatial encoder, and it is why the ranking metric
had to be independent-Argo RMSE.

---

<a name="s8"></a>
## 8. Results — the headline, per depth, and every comparator

### 8.1 The shipped result

```
Model      TS-Cast-NIO stage 1, satellite inputs, seed 42
Reference  962 INDEPENDENT Argo profiles (never used in training), n = 12,829 depth comparisons

  RMSE            0.9078 degC
  bias            +0.1003 degC      (convention: model - truth; positive = model runs warm)
  correlation     0.8812            (mean of the 15 per-depth values)
  skill           +0.2595           (1 - RMSE/RMSE_clim; RMSE_clim = 1.2259)
  Murphy skill    +0.4517           (1 - MSE/MSE_clim)
```

Both skill definitions are stored, with a note in the artifact: *"On the same real Argo predictions
they read 0.39 and 0.63. Never quote one beside the other."*

### 8.2 Per depth, the shipped model **[VERIFIED]**

| depth (m) | RMSE °C | bias °C | corr | RMSE clim | skill | n |
|---|---|---|---|---|---|---|
| 0 | 0.4027 | −0.0095 | 0.787 | 0.7500 | +0.4631 | 21 |
| 5 | 0.4676 | −0.0956 | 0.939 | 1.0035 | +0.5341 | 959 |
| 10 | 0.5235 | −0.0419 | 0.922 | 0.9944 | +0.4735 | 960 |
| 20 | 0.7805 | +0.1863 | 0.870 | 1.1287 | +0.3085 | 959 |
| 30 | 0.9732 | +0.4150 | 0.871 | 1.3080 | +0.2560 | 959 |
| **50** | **1.1870** | **+0.6572** | 0.874 | 1.2950 | **+0.0834** | 958 |
| 75 | 1.0845 | +0.3455 | 0.844 | 1.3198 | +0.1783 | 958 |
| **100** | **1.2178** | +0.2554 | 0.776 | 1.5501 | +0.2144 | 958 |
| 125 | 1.2009 | +0.0962 | 0.822 | 1.6282 | +0.2624 | 958 |
| 150 | 1.0628 | −0.0113 | 0.873 | 1.5300 | +0.3053 | 950 |
| **200** | 1.0302 | −0.1241 | 0.921 | 1.5917 | **+0.3528** | 872 |
| 300 | 0.9856 | −0.1717 | 0.899 | 1.2678 | +0.2226 | 854 |
| 500 | 0.5845 | −0.0283 | 0.915 | 0.6425 | +0.0902 | 833 |
| 700 | 0.4063 | −0.0872 | 0.946 | 0.4319 | +0.0594 | 827 |
| **1000** | 0.3053 | −0.1163 | 0.959 | 0.2928 | **−0.0426** | 803 |

**Read the shape, not just the mean.** Error is small at the surface, **bulges through the
thermocline** (peak 1.22 °C at 100 m — where a surface field constrains depth least), and collapses
below 500 m. The widest gain over climatology is **+0.56 °C at 200 m**.

**The model does NOT beat climatology everywhere.** At 1000 m climatology wins by 0.012 °C
(0.293 vs 0.305) — **14 of 15 depths, not 15**. The dashboard chart labels that crossover outright
("climatology wins by 0.012 °C here"), and a test asserts the label appears on the real data and
does *not* appear when a model really does win everywhere. **[VERIFIED]**

**The bias has structure too.** It is negative at the surface, peaks at **+0.657 °C at 50 m**, and
turns negative again below 150 m. The overall +0.1003 is a small average of a large, depth-organised
error — which is exactly why the cloud-dropout experiment in §10 could cancel it.

### 8.3 Reanalysis error — the ceiling on any model fit to it

`artifacts/glorys_vs_argo.json` measures **GLORYS itself** against independent Argo, with no model
involved. 2,455 profiles total → 888 matched (1,558 dropped as too far in time, 9 on land),
n = 11,761 comparisons, ≤ 5 days, distances max 18.7 / mean 10.5 / p95 16.5 km.

```
GLORYS-vs-Argo RMSE by depth (all matches):
  0.360  0.573  0.655  0.890  0.995  0.988  1.068  1.139  1.059  0.951  0.774  0.622  0.319  0.324  0.287
```

Under a tightened match (≤ 3 days AND ≤ 25 km, 548 profiles) the numbers barely move, which
separates real reanalysis error from collocation mismatch.

**Consequence, measured in the Validation Lab:** the thermocline error (100–150 m) is largely
**inherited** — the Phase-1 model sat within **0.023 °C** of GLORYS' own error there. The **mixed
layer (20–50 m) is genuinely ours**: +0.31 to +0.38 °C worse than the reanalysis. Nothing else in
the project had ever measured the training truth's own accuracy. **[VERIFIED]**

**CORRECTED 2026-09-07 — those two figures are Phase-1 and were being restated about the shipped
v2 model, where they do not hold.** Re-measured on the shipped checkpoint against the same 962
profiles, with GLORYS scored at the identical cells and days: the reanalysis reads 1.042 °C at
100 m against our 1.218, so **0.178 °C of the thermocline error is ours**, not 0.023 — still mostly
inherited, but not at the ceiling. The mixed-layer gap on v2 is **+0.23 to +0.38 °C** (20 m +0.227,
30 m +0.275, 50 m +0.382). The direction of the diagnostic survives; the magnitudes do not.
**[VERIFIED — audit re-score, 2026-09-06]**

This is the single most useful diagnostic the project produced. It says where effort would pay: a
better mixed-layer treatment is available to us; a better thermocline is not, without a better
training target.
---

<a name="s9"></a>
## 9. Ablations and controlled experiments

**The governing rule, learned the hard way:** an effect at the ±0.02 °C scale is not believed until
its **sign holds across 3 seeds**. This project has now watched **three** separate effects fail that
test (§15).

### 9.1 T_SEQ — how many days of surface context (`artifacts/tseq_ablation.json`)

| T_SEQ | Argo RMSE | bias | corr | skill | best epoch |
|---|---|---|---|---|---|
| 1 | 0.9096 | +0.170 | 0.894 | +0.258 | 7 |
| **11** ← chosen | **0.8529** | +0.036 | 0.889 | **+0.304** | 2 |
| 31 (the paper's ±15 days) | 0.9267 | +0.252 | 0.882 | +0.244 | 4 |

**The paper's 31-day window is the worst of the three at our data scale — worse than no window at
all — and carries the largest warm bias.** TS-Cast used ±15 days on 1/8° NW-Pacific data with
~155 k in-situ profiles; at our sample budget ±5 days wins. This is reported as a **measured
disagreement with the paper**, not a reimplementation failure.

Selection rule, stated in the artifact: lowest independent-Argo RMSE; the 0.0567 margin over
T_SEQ = 1 exceeds the 0.02 tie-break, so the shorter-window preference did not apply.

Two caveats carried in the artifact rather than dropped: all three legs **predate the embargo fix**
and are leaky (0 / 5 / 15 of 304 train days respectively — the longer windows were the more
flattered, and 31 still lost), and `AGENT_SYNC` never records legs 1 and 11's `--epochs`/`--patience`,
so the sweep may not be perfectly matched. Both are tagged **[INFERRED, needs re-measuring]**.

`config.T_SEQ` had read **31** while every real run passed `--t-seq 11` on the command line, so
anything reading the default silently built a 31-day model no experiment supports. Fixed, with the
measurement written into the constant's comment.

### 9.2 Channel ablation on the satellite bundle, 3 seeds per leg (`sat_ablation.json`)

| leg | dropped | RMSE mean | sd | Δ vs full | per-seed Δ | **sign holds?** |
|---|---|---|---|---|---|---|
| full (7 ch) | — | 0.9070 | 0.0020 | — | — | — |
| **noSSS** | `sss` | 0.9315 | 0.0165 | **+0.0245** | +0.0047 / +0.0375 / +0.0314 | **YES** |
| noCUR | `u`,`v` | 0.9171 | 0.0192 | +0.0101 | −0.0072 / +0.0080 / +0.0297 | **NO** |
| noWIND | `wu`,`wv` | 0.9110 | 0.0204 | +0.0041 | −0.0174 / +0.0068 / +0.0228 | **NO** |

**Only SSS survives.** Dropping salinity costs 0.0245 °C and the sign holds in all three seeds.
Currents and wind are **not measurable at this data scale** — their per-seed deltas straddle zero.

Note the seed spread of the *full* leg is 0.0020 while the ablated legs run 0.016–0.020: removing a
channel makes training less stable, which is itself informative.

### 9.3 Wind — built, validated, and it does not help

Wind went from 0 % to done: **388 daily-mean fields** from the only gap-filled global L4 covering
2025-26 (hourly, averaged by us — no P1D or P1M variant exists). Its grid is **offset 0.0625° from
ours**, so it is block-averaged **by coordinate, never by position**; a test asserts both halves.

**Scientifically validated against the Findlater Jet:** JJA **9.57 m/s** vs DJF **5.60 m/s** over
the western Arabian Sea, measured across seasons rather than on one date. The monsoon is visible in
the data. **[VERIFIED]**

Its effect on accuracy reversed under the embargo and again under reseeding: pre-embargo −0.0149 °C,
post-embargo **+0.0111 °C** (a cost) while still removing 14.6 % of the warm bias, and in the 3-seed
satellite ablation the sign does not hold at all. **The channel is in because the PS requires it and
because it is physically motivated, not because it was measured to help.**

### 9.4 The Arabian Sea satellite penalty — reproducible, and its cause is UNKNOWN

This is the most rigorously investigated open question in the project.

**The effect** (`basin_3seed.json`, 3 seeds, satellite minus GLORYS RMSE — positive = satellite
worse):

| | seed 42 | seed 43 | seed 44 | mean | sign holds |
|---|---|---|---|---|---|
| overall | +0.0289 | +0.0276 | +0.0005 | **+0.0190** | YES |
| **Arabian Sea** | +0.0424 | +0.0528 | +0.0071 | **+0.0341** | **YES** |
| Bay of Bengal | −0.0037 | −0.0376 | −0.0168 | **−0.0194** | YES (satellite is *better*) |

**The pre-registered hypothesis was falsified.** The satellite SSS product floors at 30.78 psu and is
blind to the Bay of Bengal freshwater plume, so the prediction — written down *before* the run — was
that the **Bay of Bengal** would score worse on satellite. It scores **better**. The Arabian Sea,
which has no such sensor limit, is the half that pays. The superseded prediction is marked
SUPERSEDED **in the artifact itself**, not quietly deleted.

**Four mechanisms were proposed and tested; none is supported** (`channel_isolation.json`,
`hybrid_currents_basin.json`, `currents_basin.json` — 12 additional 3-seed training runs on four
purpose-built hybrid bundles):

| swap one channel back to GLORYS | overall Δ mean | Arabian Δ mean | sign holds |
|---|---|---|---|
| baseline: nothing swapped | +0.0190 | +0.0341 | YES |
| GLORYS `sst` | +0.0053 | +0.0109 | **NO** |
| GLORYS `sss` | +0.0128 | +0.0205 | YES (overall), NO in BoB |
| GLORYS `ssh` | +0.0288 | +0.0418 | YES (overall), NO in BoB |
| GLORYS `u,v` | +0.0183 | +0.0245 | YES (overall), NO in BoB |

**No single input explains the penalty.** Swapping any one channel back to reanalysis leaves the
Arabian Sea penalty essentially intact. The honest conclusion, stated as the headline rather than
buried: *the effect is reproducible across seeds and its cause is unknown after four tested
hypotheses.*

### 9.5 The stage-2 satellite comparison (3 seeds)

See §15.6 — a retraction, and the third effect at ±0.02 °C to fail a reseed.

### 9.6 Physics ablation: the paper's eq. 5 density loss

Turning the density constraint **ON** costs accuracy: 0.8593 vs 0.8548 RMSE, with a worse warm bias
(+0.1598 vs +0.1055). Reported as a **negative result about the paper's own physics term**, on the
GLORYS-input leg where both runs exist. **[VERIFIED — `frozen_manifest.json`, scores read from each
run's own metrics JSON]**

---

<a name="s10"></a>
## 10. The cloud-dropout experiment — the newest result

**Status: run, artifact written, code UNCOMMITTED as of this compilation (2026-09-05 21:10 IST).**
`src/phase2/validation/dropout.py` (142 lines) + `scripts/phase2/run_cloud_dropout.py` (253 lines) →
`artifacts/cloud_dropout.json` (written 2026-09-05 20:52, 30.9 s of compute), plus
`app/phase2/dropout_page.py` (226 lines, port 8515) and `tests/phase2/test_dropout.py`
(207 lines, **15 tests**) — the last two appeared *during* this compilation, written by a
concurrent session. None of it is committed. **[VERIFIED — files read at 21:09]**

The 15 tests are worth listing, because they are the shape of the experiment's own falsification:
masking writes NaN into the raw array **not zero**; only the named channel loses data; the input
array is not mutated; the fraction is a fraction of **ocean**, not of the grid; land is never
reported as masked; both fractions are reported because they differ; an impossible fraction raises;
an unknown channel raises **rather than defaulting to the first**; a different mask seed gives a
different mask but the same count; cloud is drawn independently per time step; **the encoder cannot
tell a gap from average water**; the control reproduces the checkpoint's own recorded RMSE; masking
the whole SST channel materially degrades the model; the curve is monotone beyond its minimum; and
**the improvement at light masking is real and is explained as a bias cancellation.**

### 10.1 The question

During the monsoon, thick cloud blinds infrared SST retrieval for days at a time over large parts of
this basin. The shipped model takes SST as its first channel and its bundle's
`missing_data_policy` is *"No imputation anywhere"*. So the question is not whether the model
degrades under cloud — it is **how fast**, and whether SSH and wind carry enough signal to soften it.

### 10.2 The design, and the one mistake that would have made it meaningless

* **Masking happens in PHYSICAL units, on the raw bundle array, before `GriddedPatches` z-scores
  it.** Masking *after* normalisation, or masking to 0, would be worthless: in z-space **0.0 IS the
  channel mean**, so a "masked" pixel would arrive at the encoder as a perfectly plausible
  average-temperature pixel, RMSE would barely move, and the result would read *"the model is robust
  to 60 % cloud cover."* It would be robust to nothing — the mask would never have reached it.
* **Only SST is masked.** SSS is microwave (SMOS) and SSH is altimetry; neither is stopped by cloud,
  and pretending otherwise would overstate the scenario. `channel_index()` **raises** rather than
  defaulting to channel 0, so a change in bundle channel order cannot silently blind the model to
  something else and label the result "cloud cover".
* **The training normalisation is recovered from the pristine array.** The checkpoint was fitted
  under one set of channel statistics; recomputing them from a masked array would change the input
  scaling as well as its content, and the experiment would measure two things at once. Only the TEST
  dataset is masked — which is also what cloud actually does: it arrives at inference time, long
  after the weights were fitted.
* **The control is the whole experiment.** At fraction 0.0 the harness must reproduce the
  checkpoint's own recorded RMSE. It does, **exactly**: `recorded_rmse` and `control_rmse` are both
  `0.9077608087441584`, `control_agrees: true`, tolerance 1e-3. **The run refuses to write its
  artifact if the control disagrees.**
* **Three mask realisations per fraction** (seeds 0, 1, 2), because a single random mask is one draw
  and the spread across draws is the noise floor a degradation has to beat.

### 10.3 The result **[VERIFIED — read from `artifacts/cloud_dropout.json`]**

962 Argo profiles, n = 12,829, the shipped checkpoint unmodified.

| SST blanked | RMSE (mean of 3 draws) | spread | Δ vs control | bias | corr | skill |
|---|---|---|---|---|---|---|
| 0 % (control) | 0.9078 | — | — | **+0.1003** | 0.8812 | +0.2595 |
| 5 % | 0.9006 | 0.0004 | −0.0072 | +0.0739 | 0.8820 | +0.2654 |
| 10 % | 0.8957 | 0.0010 | −0.0120 | +0.0472 | 0.8828 | +0.2693 |
| **15 %** | **0.8950** | **0.0002** | **−0.0127** | +0.0206 | 0.8834 | **+0.2699** |
| 20 % | 0.8973 | 0.0005 | −0.0104 | −0.0052 | 0.8829 | +0.2680 |
| 30 % | 0.9118 | 0.0011 | +0.0040 | −0.0590 | 0.8825 | +0.2562 |
| 50 % | 0.9857 | 0.0024 | +0.0779 | −0.1632 | 0.8733 | +0.1959 |
| 70 % | 1.1087 | 0.0005 | +0.2010 | −0.2668 | 0.8455 | +0.0956 |
| 90 % | 1.2914 | 0.0011 | +0.3837 | −0.3930 | 0.7675 | **−0.0535** |
| 100 % | 1.4114 | 0.0000 | +0.5036 | −0.4708 | 0.6968 | **−0.1513** |

### 10.4 The reading — and the reading that would have been wrong

**The curve is not monotone. Blanking 15 % of ocean SST makes the score BETTER**, by 0.0127 °C,
with a spread across mask draws of 0.0002 — **60× the noise**, so it is not a fluke.

It would be easy, and completely wrong, to report that as *"the model tolerates cloud cover."*

It is **two errors partially cancelling.** The shipped model carries a **+0.1003 °C warm bias**. A
blanked pixel reaches the encoder as the channel mean, which pulls the prediction cooler. The RMSE
minimum at 15 % sits essentially where **the bias crosses zero, at 19.0 %**. The artifact's own
`analysis` block says so in those words, and the page built on it repeats the caution above the
chart.

**So the honest reading is a finding about the DELIVERABLE, not about robustness:**

> The shipped model runs warm, and a bias correction is worth about **0.013 °C** — recoverable for
> free, without retraining. Past the minimum the curve is monotone and the degradation is real:
> **+0.50 °C at 100 % blanking**, with skill-vs-climatology going **negative at 90 %**.

### 10.5 The caveat the artifact carries in its own body

> *The encoder has no missing-data channel.* `dataset.__getitem__` z-scores the patch and replaces
> every non-finite value with `0.0`, which **is** the channel mean — so a blanked pixel reaches the
> model as average water and it cannot tell the two apart. This measures degradation under that
> behaviour, not under a model designed to handle gaps.

This is a real architectural finding, located precisely: `dataset.py:156` computes a `finite` array
and **line 157 immediately discards it**, despite the module docstring promising it is kept *"so a
model can learn to distrust those cells."* `masking_is_indistinguishable_from_mean_fill()` asserts
that equivalence so the claim cannot rot.

**Stated plainly: the model is not degrading gracefully under missing data — it is being told
nothing, and treating every gap as climatologically average water.** Giving the encoder a
missing-data mask channel is the obvious next experiment and has not been run. **[UNKNOWN]**

---

<a name="s11"></a>
## 11. Uncertainty: what is calibrated and what is not

### 11.1 The current, shipped calibration (`artifacts/uncertainty_calibration.json`)

Post-hoc **per-depth variance scaling**. Scales are **fitted on train-window Argo (3,423 profiles)**
and coverage is **reported on test-window Argo (908 profiles)** — the two are disjoint in time.
Fitted against the **shipped checkpoint** (`is_shipped_model: true`), which `freeze.py` asserts.

Two methods were fitted and both are stored; the `coverage` method is used:

| | ±1σ coverage (target 0.683) | ±2σ coverage (target 0.954) | PIT deviation |
|---|---|---|---|
| variance-matching | 0.7119 (range 0.529–0.915) | 0.9355 (range 0.841–0.991) | 0.0091 |
| **coverage (used)** | **0.6387** (range 0.461–0.724) | **0.9119** (range 0.801–0.955) | 0.0101 |

Per-depth scale factors actually applied (coverage method):

```
0 m 1.149 | 5 m 1.108 | 10 m 1.103 | 20 m 1.169 | 30 m 1.141 | 50 m 1.188 | 75 m 1.279
100 m 1.458 | 125 m 1.290 | 150 m 1.153 | 200 m 1.056 | 300 m 1.008 | 500 m 0.940
700 m 0.910 | 1000 m 0.886
```

### 11.2 What is claimed, exactly

**The band is `±2σ`. It is never labelled "95 %".** Coverage is reported as a **range (80.1 %–95.5 %
by depth, mean 91.2 %)**, never as the mean alone, because the mean hides an 80 % depth at 50 m.
No ±1σ band and no confidence percentage appear anywhere in the UI, because neither is defensible.
`freeze.py` checks this claim wording as one of its 18 checks. **[VERIFIED — live run]**

**Honest summary: the uncertainty is *improved*, not *calibrated*.** The model remains mildly
overconfident.

### 11.3 Two independent signals point at the same depth

Measured on 2026-06-23 and pinned by tests in the uncertainty dashboard (§12):

* the model is **least certain at 100 m** — median σ **1.197 °C**; most certain at 500 m (0.265);
* the **largest calibration scale factor is ALSO at 100 m** — ×1.4583.

Two independent signals on the same depth: the raw model is least certain at the thermocline **and**
was most overconfident there. Both are stated on the page.

### 11.4 The Phase-1 MC-dropout finding (D-016), kept for the record

`artifacts/mc_calibration.json`, 879 Argo profiles, ratio = RMSE / RMS(σ) aggregated per depth
*then* divided (averaging per-point ratios inflates the shallow end ~2×; the artifact says so):

```
overconfident at EVERY depth      worst  3.54x at 20 m      best  1.56x at 1000 m
mixed layer (20-50 m) mean 3.25   deep (>=500 m) mean 1.63
```

The original D-016 write-up said the problem was "at depth". **It is the opposite** — the mixed
layer is where the spread is worst. The title and the reliability panel were both corrected.
---

<a name="s12"></a>
## 12. The dashboard suite — fifteen surfaces, one port each

The port map is **enforced by a test** (`tests/phase2/test_launch_ports.py`): no two configs share a
port, no two docstrings claim one, `.claude/launch.json` agrees with every docstring, and every
runnable page has an entry. A negative test re-injects the old 8504 collision and watches 2 of 10
checks fail. `_app_pages()` originally substring-matched `"set_page_config"`, so a helper that
*documented* not having one was collected as a runnable page — it is parsed with **`ast`** now.
**[VERIFIED]**

| port | app | lines | what it is |
|---|---|---|---|
| 8501 | `app/streamlit_app.py` | 256 | the Phase-1 demo shell (frozen, read-only) |
| 8502 | `collocation_page.py` | 307 | multi-source point inspector |
| 8503 | `validation_page.py` | 292 | Validation Lab |
| 8504 | `cube_page.py` | 299 | 3-D OceanCube |
| 8505 | `physics_page.py` | 444+ | MLD / barrier layer / thermocline / OHC, three sources |
| 8506 | `events_page.py` | 339 | eddies / fronts / upwelling |
| 8507 | `tscast_page.py` | 727+ | the v2 model dashboard |
| 8508 | `validate_page.py` | 255 | live Argo overlay |
| 8509 | `cyclone_heat_page.py` | 209 | TCHP / OHC / D26 |
| 8510 | `transect_page.py` | ~500 | depth-vs-distance cross-sections (F2) |
| **8511** | `phase2.api.app:app` (uvicorn) | 232 | **the HTTP export API** |
| 8512 | `clickmap_page.py` | ~430 | click any of 24,000 cells → that cell's profile (F1) |
| 8513 | `uncertainty_page.py` | 351 | uncertainty as transparency (F3) |
| 8514 | `acoustics_page.py` | 380 | sound speed / sonic layer / SOFAR (F7) |
| 8515 | `dropout_page.py` | 226 | cloud dropout — **uncommitted at compile time** |
| — | `app/panels/` | 508 | four Phase-1 panels (map, profile, priority, validation) |

### 12.1 The NetCDF export and HTTP API (port 8511) — `d9ff4aa`

Before this commit there was **no way to get a reconstruction out of the system**: verified by
grepping — zero hits for `fastapi`, `flask`, `st.download_button` or `BytesIO` anywhere.

**A contract nobody was checking.** `tscast_output_schema.md` §5 is marked `Status: CONTRACT` and
requires ten provenance keys. **Neither producer satisfied it and nothing tested it** — the point
path omitted `checkpoint_sha256` and `code_commit`; the field path omitted those plus `P`,
`input_date` and `clim_train_years`. `provenance.py` now assembles the block once and **asserts**
the contract; `test_provenance.py` parametrises over the keys *and* source-text-guards the doc so
code and contract cannot drift apart silently.

**Three format decisions, each an application of rule 8** (an absence is not a value):

* **`_FillValue` set explicitly** on every float variable. Left to a reader's default, a land cell
  becomes a **0 °C measurement**.
* **A stage-1 file OMITS the salinity variables** rather than writing an all-NaN grid — the latter
  asserts *"this file has salinity, missing everywhere"*, a different and false claim.
* **Masks are `int8` flags** with `flag_values`/`flag_meanings`. NetCDF has no bool, and a silent
  float cast is how a mask stops being a mask.

`export_field.py` **refuses an out-of-bundle date** rather than snapping, and the refusal names the
valid range. Exit 1, verified.

**Two things in the API that must not be "simplified":** handlers are `def`, **never** `async def`
(an async handler calling `predict_field` blocks the event loop for 32 s — guarded by an **AST**
check, because a text grep matches the warning in the docstring as readily as a violation); and
every predictor call is **inside a lock**, because `predict_field` borrows `ds.index` while
`reconstruct` overwrites it and never restores it, so two concurrent requests would return
plausible wrong answers rather than raising.

**Verified live [VERIFIED]:** `/health` and `/coverage` 200 with real bundle dates; `/profile`
**1.1 s**, 15 depths, no `NaN` token in the body; `/field.nc` **3.29 MB in 34.3 s**, reopening as
valid NetCDF carrying `input_source=satellite` and the checkpoint sha; `/docs` renders all four
routes; an out-of-bundle date returns **422 naming the valid range** on both endpoints.

### 12.2 A measurement that replaced an `[INFERRED]` claim

`field.py` said *"seconds on the GPU, under a minute on CPU"* — an estimate standing where a reader
takes a cost figure. `artifacts/export_timing.json` **[VERIFIED]**:

```
predict_field       32.09 s median of 4 (30.98-32.92), 11,832 ocean cells, batch 512
predictor load       7.20 s, paid once
build + write        0.49 s + 0.25 s   ->  3.29 MB file
total warm          32.84 s     total cold  39.90 s
host   Windows 11, Python 3.12.3, torch 2.13.0+cu126, RTX 4050 Laptop GPU, cuda_available: true
device_used  cpu
```

**And the estimate was wrong in a way that mattered: CUDA is available and the inference path never
used it.** `TSCastPredictor` loads with `map_location="cpu"` and never moves the model, so every
dashboard reconstruction is a CPU reconstruction.

### 12.3 The device bug that had never worked — `7af3e71`

Found by a user turning on the GPU toggle the click map had just added:

```
Could not reconstruct 2026-06-23: Input type (torch.cuda.FloatTensor) and
weight type (torch.FloatTensor) should be the same
```

`predict_field` sent `x`, `g`, `cp` and `mo` to `device` **and left the model wherever it loaded** —
always CPU. So `device="cuda"` fed CUDA inputs to CPU weights and raised. **The parameter had been
broken for as long as it had existed; nothing had ever passed it.** The "4.1× speedup" figure in
`field.py`'s own header had been measured by moving the model *by hand*, which is exactly why the
argument's own failure went unnoticed.

Measured after the fix, same date, same predictor **[VERIFIED]**:

```
CPU    37.57 s          CUDA   8.86 s        4.24x
max |CPU - CUDA| temperature   6.866e-04 degC over 153,291 cells
max |CPU - CUDA| sigma         2.427e-04 degC
model returned to cpu afterwards: yes      same NaN pattern: yes
```

6.9e-4 °C is float32 noise against a 0.9078 °C headline. The model is moved **back** in the
`finally` block, beside `ds.index` and for the same reason: the predictor is a process-wide
singleton shared by every page, and leaving it on the GPU would silently change the device of every
later reconstruction — **including the NetCDF export, which is deliberately kept on CPU so a
downloaded file cannot differ in its last digits from the page beside it.**

### 12.4 The shared foundation — `dd8ec6d`

Three of the nine planned features wanted the same code, and writing it three times is how
`v2_cache_version` came to be pasted into three pages before being factored out. So it is one small
tested branch the feature branches fork from:

* **`seawater.sound_speed`** — Mackenzie 1981, coefficients pinned to the published value the way
  EOS-80 already is. Argument order is `(salinity, theta, depth_m)`, matching every other function
  in the module — **not** the printed `c(T,S,D)`. Both orders are pinned by a test.
* **`sound_speed_in_range()`** is a separate mask because a sixth of the surface is outside
  Mackenzie's envelope: measured, salinity runs **1.64–39.98 psu** (7.64 % of surface cells below
  S = 30 — the Ganges/Meghna plume) and θ reaches **35.34 °C** (10.35 % above T = 30).
* **`derived/profile_features.py`** — depth-finders that return **(value, reason)**. Six reasons,
  because a bare NaN conflates land, too-few-levels, never-attained, crossed-the-other-way and
  grid-edge. *Rule 8 turned into a type signature.*
* **`derived/mapframe.py`** — one depth level as clickable cells, classified once. **The order of
  the two checks is load-bearing:** asking "is the value finite" before "is it land" labels the
  entire coastline "below the seafloor", which is a claim about bathymetry the data never made.
* **`field_cache.py` + `app/phase2/_fields.py`** — one predictor, one lock, one cache key. Four
  pages held the predictor in `st.cache_resource` — a cross-session singleton shared by every
  browser tab — **with no lock**, so two tabs corrupted each other and returned a plausible wrong
  answer rather than raising. Tested with real threads.
* **`viz_explainer.py`** — the shared page footer, **validated rather than trusted**: a formula with
  no symbol note raises, a placeholder raises, a caveat with no evidence raises.

### 12.5 F1 — the click map (8512), and four bugs only rendering could find

*"An Argo float answers 'what is it like at 500 m' only where a float happens to be, every 5–10
days; this answers it everywhere, every day, and lets a reader test that themselves rather than take
it on trust."*

1. `mark_rect` on a continuous scale with no `x2`/`y2` has no idea how wide a cell is, so Vega-Lite
   picked a default band and the basin drew as a handful of enormous blocks.
2. `use_container_width` gave a **1.6 aspect against the basin's true 2.29** — at the mean latitude
   a degree of longitude is cos(17.5°) = 0.954 of a degree of latitude — so the Bay of Bengal was
   the wrong shape.
3. `mark_area` with `x`/`x2` forces a zero baseline, which stretched the profile axis to 0–35 °C and
   squeezed a real ±2σ band of 0.83 °C into **2 % of the plot**: an uncertainty band drawn so thin
   it reads as certainty.
4. Vega-Lite's default is `invalid: "filter"` — a datum whose encoded field is null is **dropped**.
   So land was never drawn, a click on India selected nothing, and the panel went on saying "click
   any cell": **silence exactly where the page promises an explanation.**

**None of those is visible from a test. All four were found by opening the page.**

**Verified in the browser on real data [VERIFIED]:** ocean 17.50 N 57.50 E → 15/15 levels, 28.27 °C
surface → 9.11 °C at 1000 m, ±2σ 0.83–3.63 °C, calibrated; land 21.75 N 47.50 E → *"That cell is
land"*, no phantom profile.

**The classification cross-checks three ways.** At 100 m: 9,763 water + 2,069 seafloor + 12,168 land
= **24,000 = the grid exactly**. At 1000 m: 8,973 + 2,859 + 12,168, land unchanged, water strictly
fewer. water + seafloor = **11,832 at both depths** — the same ocean-cell count
`export_timing.json` records — and 8,973 is independently the number of cells with water at all 15
levels, measured while writing the sound-speed function.

### 12.6 F3 — uncertainty as transparency (8513)

Colour is temperature, opacity is confidence, as specified. **Three departures, each measured:**

* **A second view mode, because the double encoding contaminates its own channel.** Opacity over a
  dark ground pulls every hue toward the background, so a low-confidence **warm** cell reads as a
  cool one — *the fade corrupts the temperature it is drawn on top of.* "Uncertainty alone" drops
  the hue and shows σ on an inferno scale. It is also the better picture: the bright band sits on the
  Somali Current and the southern Arabian Sea eddy field, dark in the quiet Bay of Bengal interior —
  **the model is least sure where the ocean is most active.**
* **The opacity domain is per-view, and its two end values are printed in °C.** σ at 5 m and σ at
  1000 m differ enough that one fixed range would render whole depths uniformly vivid or uniformly
  faded — which makes cross-view comparison invalid unless the reader knows, so the numbers are in
  the caption rather than implied by the colours.
* **The calibration panel does not flatter itself:** ±2σ covers 91.2 % against a nominal 95.4 %,
  −4.2 points, on 908 held-out profiles. *A page about uncertainty that overstated its own
  uncertainty would be self-refuting.*

**The spec's acceptance check was comparing two different quantities.** Verbatim: *"sigma range at
the rendered depth is finite and within the calibration artifact's known range (~0.89–1.46)"*. Those
are dimensionless **scale factors** that multiply σ; σ is in °C. It would have passed or failed for
the wrong reason. Replaced with a much stronger check: reconstruct the field twice, once with
calibration switched off, and assert **depth by depth** that calibrated/raw equals the published
factor to `rtol=1e-5` — plus that calibration moves σ and **not** temperature, since a scale applied
to the wrong array would leave a still-plausible ocean nothing downstream could catch.

### 12.7 F7 — acoustics (8514), and a page that found a bug in itself by being clicked

Sound speed is the operational reason to want subsurface temperature: it decides how far a sonar
hears and where its signal bends.

**The bug.** The first draft reported *"8.25 N, 78.00 E — axis resolved"*. That is the **Palk
Strait**: three finite levels, about ten metres of water. It had found a five-metre dip in a
ten-metre column and called it a SOFAR channel.

Measured across the basin on real GLORYS T/S: of **848 cells reporting "axis resolved", 336 — 40 %
— sat in water shallower than 300 m**, reporting axis depths of 5, 10, 20, 30 m. The 471 cells with
a full column reported 200, 300, 500 and 700 m only. `sofar_axis` now requires a full water column
(`SOFAR_MIN_COLUMN_M = 1000.0`). The categories then partition exactly: 8,502 below-grid + 471
resolved = **8,973 full-depth cells**, + 2,859 too shallow = **11,832 ocean**. A test asserts that
arithmetic; another asserts the guard is **load-bearing**, by relaxing `min_column_m` to 0 and
watching the artifact come straight back. **None of that was visible from a test. It was visible
from clicking one cell.**

**What the spec asked for that cannot honestly ship.** A basin map of SOFAR axis depth. On the
compliant stage-2 source, 2026-06-23: **12,168 no water column / 8,973 axis below 1000 m / 2,859 too
shallow / ZERO resolved.** The tropical Indian Ocean axis sits near 1500–2000 m, **below our deepest
level**. So the page ships a map of *where the axis is resolvable*, and on this date says "nowhere"
in words rather than drawing 24,000 cells of grid edge.

**Why an acoustics page is defensible from a temperature model — measured, not argued.** At
2026-06-23's mean conditions the deliverable's 0.9078 °C temperature error moves sound speed
**+2.31 m/s**; stage 2's 0.2695 psu salinity error moves it **+0.30 m/s**. **Temperature is 89 % of
the budget.** Computed live, so it moves with conditions — and the direction is not the intuitive
one: Mackenzie's quadratic term is negative, so **dc/dT falls as water warms** (4.08 m/s per °C at
5 °C against 2.11 at 29 °C). Cold deep water is *more* temperature-dominated, 10.5× against 6.7×.

**A colour bug worth recording:** the first "unresolved" colour, `#6b5a7a`, sat on the deep end of
the reversed viridis ramp and **read as DEEP DUCT**. A resolved absence must be off the value ramp
entirely. And an envelope caption divided by all 24,000 cells, reporting 24 % where the real figure
is **48 %** — two thirds of the grid is land, and land has no salinity to be out of range.

### 12.8 F2 — transect upgrades (8510), and three bugs in the page they were built on

* **The page's cache key was never passed.** `build_section` took a `version` argument and `main`
  never supplied it, so its `st.cache_data` never invalidated when the checkpoint changed — **the
  exact mechanism behind the 8 °C dashboard error of 2026-09-02.** The seam existed; nothing went
  through it.
* **The date was a free text box.** `_time()` is an argmin with no bound, so `1850-01-01` returned
  bundle index 0 and a complete, plausible section with **no warning**. It is a picker over the
  model's real calendar now.
* **The legend understated the model's own uncertainty.** It read *"Model spread (°C, 1σ — NOT
  calibrated)"*; `predict_field` applies the per-depth calibration whenever `_calibration_applies_to`
  passes, which for the shipped stage-1 model it does. *Every other honesty bug in this project has
  been a page claiming **more** than it had; this one claimed less.*

**What the upgrade added,** measured on the default track:

```
model - GLORYS   bias +0.011, RMSE 0.560 degC over 747 section points
vs 3 Argo        pooled RMSE 0.795 degC, offsets 2-60 km
```

GLORYS is the training target, so 0.560 is **agreement with what the model was fitted to**. The
caption says that, so the smaller number cannot stand as the better one. Every float carries its
`offset_km` and `temporal_offset_days` into the tooltip: a float 60 km and 4 days away is a weaker
check than one 2 km and same-day, and hiding that overstates the validation.

**A sliding slice — which had a bug of its own in the first draft.** Clipping each endpoint against
the grid independently lets one end stop at the boundary while the other keeps going, so the track
silently **shrinks** instead of sliding: *a control that promises to hold a line's shape and quietly
deforms it.* `transect.slide` clips the **shift** instead, bounded by whichever end reaches the edge
first, so the span is preserved by construction.

**Isopycnal and sound-speed contours.** On a real 8 N 68 E → 20 N 88 E stage-2 section the
24 kg m⁻³ isopycnal is resolved at **26 of 60** points by `contour_line` and at **0 of 60** by
`isotherm_line` — the foundation branch paying for itself, now pinned by a test. Asking
`sample_transect` for a key the field does not carry **raises** rather than returning an all-NaN
section, because an all-NaN density overlay is indistinguishable from "no isopycnals here".

### 12.9 physics_page wired to stage 2 — and the wiring measured why not to trust two of it

A third source, *"v2 stage-2 (unpromoted)"*: all four structure fields from temperature **and**
salinity the model predicted, no reanalysis in them. The first time MLD-by-density, the barrier
layer and a real-density OHC exist on this project **from satellite input alone**.

**Two guards fired on their own**, which is the point of having them: `predict_field` reports
`checkpoint: "unpromoted"` (the sha does not match what promotion recorded) and
`sigma_is_calibrated: False` — *"calibration was fitted on a stage-1 model, this record is stage 2"*.

**The measurement — stage 2 vs GLORYS, 2026-06-18, per ocean cell [VERIFIED]:**

| field | bias (s2 − glorys) | RMSE | median s2 | median glorys |
|---|---|---|---|---|
| **MLD (density, m)** | **−14.12** | **21.34** | 20.0 | 50.0 |
| **Barrier layer (m)** | **+8.88** | **19.00** | 20.0 | 0.0 |
| ILD (temperature, m) | −5.85 | 16.44 | 50.0 | 50.0 |
| Thermocline depth (m) | −1.80 | 24.12 | 87.5 | 87.5 |
| OHC 0–300 m (GJ/m²) | **−0.024** | **0.664** | 25.0 | 25.1 |

**OHC survives; MLD and the barrier layer do not.** The cause is upstream and measurable: surface
salinity carries **+0.19 psu of bias** (RMSE 0.59 at 0 m). The MLD criterion is a **0.03 kg m⁻³**
threshold from 10 m, and ~0.19 psu is roughly 0.15 kg m⁻³ — **five times the threshold** — so the
criterion trips at the wrong depth systematically. An integral is far less sensitive than a
threshold crossing, which is why OHC is unaffected.

**Consequence.** The page's published seasonal claim is BoB 9.5 m vs Arabian 7.1 m — a **2.4 m**
signal. The stage-2 barrier layer's bias alone is **+8.9 m**, nearly four times it. So that section
is **not** computed from stage 2, and the page computes the comparison **live and prints the bias
table plus a warning above the maps**, on the date the reader selected. **Standing recommendation:
do not use the stage-2 MLD or barrier layer for any claim; its OHC is defensible.**
---

<a name="s13"></a>
## 13. The freeze, provenance and byte-identity machinery

### 13.1 `artifacts/FREEZE_MANIFEST.json` — the A16 freeze

```
frozen_at   2026-09-02T20:12:52
git         ffd95e6e84e1988fde65e9546ea9c392418010d5 on phase2-tscast-nio, tree clean
model       promoted from sat_7ch_s42 -> artifacts/tscast_stage1.pt
            sha256 53848bb52533752d15a4e25f6e0fb038297bd32671606b290dd0260e991441ae
            built at code commit a67feea
data        data/processed/daily_sat/v001, 388 days
            2025.npz sha256 6e3e53ee2334...   2026.npz sha256 7fdefe1f444e...
split       train 2025-06-01..2026-03-26 | test 2026-04-01..2026-06-23 | embargoed_v2 | 5 embargoed
checks      18 passed, 0 failed
```

### 13.2 `artifacts/frozen_manifest.json` — byte identity across two machines

Four claims, each with a role, a checksum and its scores read from that run's own metrics JSON —
**never retyped**:

| key | role | RMSE | checkpoint present here? |
|---|---|---|---|
| `deliverable_satellite` | **THE PS DELIVERABLE** | 0.9078 | yes, sha verified |
| `glorys_comparator_stage2` | GLORYS T+S+ρ, best accuracy, **not** the deliverable | 0.8548 | no — frozen on the other machine, checksum carried forward and **labelled as not re-verified** |
| `glorys_comparator_stage2_densityON` | the eq. 5 physics-ablation control | 0.8593 | no — same |
| `glorys_comparator_stage1_embargoed` | leak-corrected GLORYS stage 1 | 0.8645 | yes, sha verified |

The manifest was rewritten on 2026-09-04 because **a freeze that spans two machines must accumulate,
not overwrite**: running the original `freeze_headline.py` as written would have nulled the two
checksums verified on the other machine. A claim whose `checkpoint_present` is false carries an
explicit note saying its bytes must be frozen where the file lives.

It also carries its own history: `"supersedes": "the 2026-09-01 manifest … that named the GLORYS
stage-2 run 0.8548 as HEADLINE. That predates the satellite-input build and the deeper _window()
embargo fix; 0.8548 is a comparator, not the deliverable."`

Two checkpoints are kept **read-only** in `artifacts/frozen/`:
`tscast_stage1_sat_7ch_s42.pt` and `tscast_stage1_embargo_withUV_s42.pt` (mode `-r--r--r--`).

### 13.3 What guards exist, and what each one caught

| guard | what it prevents | evidence it works |
|---|---|---|
| `freeze.py --check` (18 checks) | checkpoint / bundle / `dataset.py` / `inference.py` / split moving without a re-freeze | run during compilation: **17 ok, 1 fail** (dirty tree — §17) |
| `audit_ps.py` (17 rows) | a hand-written requirements matrix drifting from reality | **16 PASS / 0 FAIL / 1 BLOCKED**, §14 |
| `verify_sat_bundle.py` (44 checks) | a reanalysis field entering a "satellite" bundle | includes a **negative test that catches GLORYS injected into all five satellite channels** |
| `test_launch_ports.py` | two apps claiming one port | negative test: re-injecting the 8504 collision fails 2 of 10 checks |
| `field._promoted_from` | crediting any loaded checkpoint with a promotion | returns the name only when the loaded file's **sha256 is the one promotion recorded**; regression test uses an impostor checkpoint |
| `_calibration_applies_to` | stage-1 σ scales silently rescaling a stage-2 model | **stage is matched first** now — the axis it originally did not look at |
| `MLPProfile.trained_on_fixtures` | a fixture-trained checkpoint backing a demo | `load_mlp()` raises on load |
| `accept.py check_v2_ui` | the dashboard showing a number the model did not produce | every rendered number asserted equal to the metrics artifact to 4 dp |
| `accept.py` viz-foundation check | a plausible-but-wrong primitive | **8 falsification assertions**, incl. that swapping `sound_speed`'s first two arguments moves it 10.74 m/s, and the Palk Strait SOFAR guard |
| `argo_coverage()` | an empty Argo match described as an empty ocean | §15.5 |
| structural Altair test | a page encoding a column the frame does not return | such a page draws an **empty chart with no error anywhere**; the test reads what each page asks Altair for |
| AST guard on the API | an `async def` handler blocking the event loop for 32 s | a text grep would match the docstring warning as readily as a violation |
| bundle-embedded `provenance` JSON | a doc drifting from the data it describes | provenance travels **inside the npz** |

---

<a name="s14"></a>
## 14. PS requirements audit — 16 PASS / 0 FAIL / 1 BLOCKED

Run live during compilation: `PYTHONPATH=src python scripts/phase2/audit_ps.py`. Every row opens an
artifact and checks it. **[VERIFIED — live output, 2026-09-05]**

| # | requirement | verdict | evidence the script produced |
|---|---|---|---|
| 1 | preprocessing + harmonisation, multi-source | **ok** | 7 channels harmonised from 5 distinct products into `daily_sat/v001` |
| 2 | spatial resolution 0.25° | **ok** | step 0.25, grid 100×240, 5.0–30.0 N / 45.0–105.0 E |
| 3 | temporal resolution daily | **ok** | 388 daily steps 2025-06-01..2026-06-23, **0 gaps** |
| 4 | input: SST | **ok** | `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2`, SATELLITE_DERIVED |
| 5 | input: SSS | **ok** | `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D`, SATELLITE + INSITU_BLEND |
| 6 | input: SSH / SLA | **ok** | `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs`, SATELLITE_DERIVED |
| 7 | input: surface currents U,V | **ok** | `cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m`, SATELLITE_DERIVED |
| 8 | input: surface winds U,V | **ok** | `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H`, SATELLITE_DERIVED |
| 9 | compact satellite embedding via DL | **ok** | cnn3d → 128-dim latent, chosen over 4 candidates, `input_source=satellite` |
| 10 | reconstruction: surface → profile | **ok** | one forward pass returns 15 depths per (lat, lon, date) |
| 11 | 15 standard depths, exactly | **ok** | `config.DEPTHS == the PS list: True` |
| 12 | evaluate: RMSE | **ok** | RMSE at 15/15 depths, overall 0.9078 |
| 13 | evaluate: correlation | **ok** | correlation at 15/15 depths, overall 0.8812 |
| 14 | evaluate: bias | **ok** | bias at 15/15 depths, overall +0.1003 |
| 15 | training target: GLORYS reanalysis | **ok** | GLORYS12V1 daily `cmems_mod_glo_phy_my_0.083deg_P1D-m` |
| 16 | independent validation: **INCOIS LAS gridded Argo** | **BLOCKED** | 962 independent argopy profiles used; deviation documented in `docs/INCOIS_PROBE.md` |
| 17 | PoC over Bay of Bengal / Arabian Sea | **ok** | per-basin skill over 3 seeds: Arabian +0.0341, BoB −0.0194 |

> **BLOCKED is a real answer, not a softer word for FAIL.** It means the requirement is understood,
> our side of the work is done, and an external dependency is unavailable. It must be stated to a
> jury as exactly that, never quietly counted either way.

### 14.1 Why req 16 is blocked — the INCOIS probe (`docs/INCOIS_PROBE.md`)

Probed 2026-09-02. **The catalogue is reachable and carries exactly the right product; the data
layer is dead.**

* **Works:** `getCategories.do` 200 (13 categories, the first is *ARGO DATA PRODUCTS*),
  `getDatasets.do` 200 (**17,007,907 bytes**, 52 datasets), THREDDS catalogue 200 in 0.19 s.
* **Two gridded Argo products found**, both 1° × 1°, 10-day, 24 depth levels, running to 2026-07-30:
  Kessler–McCreary (`argo_10d.nc`) and **Variational Analysis** (`argo_10dv.nc`, which carries
  `SAL`).
* **Fails:** every OPeNDAP route hangs at 0 bytes (240 s / 75 s / 75 s), the advertised `ftds_url`
  404s, and `ProductServer.do` accepts a valid request then returns *"An error occurred in the
  service that was creating your product."* The `.jnl` files are 44-byte Ferret journal stubs.
  **The Ferret / F-TDS materialisation backend is down — not the host, not the network, not us.**

The metadata alone settled three open questions: **14 of our 15 depths are exact INCOIS levels**
(only 0 m is absent — INCOIS starts at 5 m), spatial overlap is **~98 %** (only the 29.5–30 °N strip
falls outside), and **VAM carries salinity**, which would score the currently-unscored stage-2 S and
ρ. Two mismatches are pre-documented for when it returns: our field must be **aggregated** to their
1° boxes (never interpolate a 1° analysis onto 0.25°), and our daily output must be **averaged into
their 10-day windows** before any RMSE.

**No downloader was written.** *"A downloader that has never once retrieved a byte is not evidence
of anything."*

---

<a name="s15"></a>
## 15. Corrections, retractions and withdrawn claims

This section is deliberately long. Several numbers in this project were believed and wrong, and
every one looked right. The corrections are part of the record, not an embarrassment to be trimmed.

### 15.1 The leakage embargo — every pre-2026-09-02 artifact is INVALID

`dataset._window()` clamped the input window to the **array ends** instead of to the **train/test
split**, so **5 of 304 train days (2026-03-27..31, 1.64 %) read test-period surface fields.** The
split assertion was correct; the input window was not — which is exactly why every test passed while
it happened.

**Invalid, never to be quoted:** `tscast_stage1_withUV_s42` (0.8612 / 0.8611),
`tscast_stage1_noUV_s42` (0.9024), `tscast_stage1_metrics_tseq31` (0.9267), and the wind comparison
derived from the first two. The numbers are **preserved verbatim as historical record and are not
edited**; `artifacts/INVALID_PRE_EMBARGO.md` names them.

Two embargo fixes were written independently on two machines. **Darshan's — which DROPS the 5
boundary training targets — is canonical**, because Arjhun's clamping silently shortened the context
for boundary samples while still counting them as full ones, and embargoed the test side too, which
models an operational setting nobody runs. So **0.8645, from the clamped re-run, is also superseded:
right conclusion, wrong protocol.**

### 15.2 E-CAL-01 retracted — the diagnostic was broken, not the model

`calibrate_uncertainty.py:64` called `D.load_daily()` with **no argument**, defaulting to
`data/processed/daily` (GLORYS), while the shipped model trains on `daily_sat/v001`. Every per-depth
σ scale in E-CAL-01 was therefore fitted on the errors a satellite-trained model makes **when fed
reanalysis**, which are not the errors it makes.

| | E-CAL-01 (GLORYS-fed, WRONG) | refitted (satellite-fed) |
|---|---|---|
| ±1σ coverage | 0.6053 | **0.6387** |
| ±2σ coverage | 0.9650 (**over**-covers) | **0.9119** (**under**-covers) |
| scale at 50 m | 3.24 | **1.19** |
| scale at 75 m | 5.13 | **1.28** |
| scale at 100 m | 5.41 | **1.46** |
| scale at 150 m | 4.78 | **1.15** |
| scale at 300 m | 4.13 | **1.01** |

**The uncertainty head was never 4–5× miscalibrated. The diagnostic was.** Real scales span
0.89–1.46. Even the *direction* reversed, so every conclusion drawn from E-CAL-01 pointed the wrong
way. The UI carried the retracted figures in a caption, a docstring, a chart title, a tooltip and a
column label; all five were corrected in the same commit. The superseded artifact is kept as
`uncertainty_calibration_INVALID_glorys_fed.json`.

### 15.3 The 8 °C dashboard error — same defect, different file

`inference.py` had the identical `load_daily()` defect: it fed **GLORYS to a satellite model**, and
the dashboard read **8.01 °C at 100 m**. Two further faults compounded it: the Streamlit cache keyed
on *arguments* rather than on imported module source, so **the code was fixed and the screen was
not** (the predictor cache is versioned now); and the metrics JSON recorded `data: "daily"` — a
*cadence*, not a path. Both `input_source` and `daily_dir` are now recorded in the checkpoint **and**
the metrics JSON, and the checkpoint is the authority.

### 15.4 The SSH claim — 1 of 3 seeds, presented as 3 of 3

A positive SSH result was written up as reproducible. It was **1 of 3 seeds**. Retracted in commit
`bcd9a1b`. Darshan caught it in review before it reached a slide.

### 15.5 An empty Argo match explained as an empty ocean

`argo_test.parquet` holds **2022 only** (32,836 rows, zero in 2019/2020/2021), while the collocation
page offered all 48 grid dates. On **36 of 48 dates (75 %)** the page said:

> *"No Argo profile within tolerance. 2,455 floats across ~15 million km² is genuinely sparse — that
> gap is the problem this project exists to fill."*

That asserts a fact about the ocean from an absence in a file. Measured at 15 °N 65 °E, open Arabian
Sea, same point and tolerance: **no match 2019 / 2020 / 2021, match in 2022 — the only variable was
the year.** Fixed by adding `argo_coverage()` / `argo_table_covers()` so the page branches on
evidence: outside the table's span it now says *"this says nothing about the ocean."*

### 15.6 Stage 2 on satellite input — a retraction of a number written down 90 minutes earlier

`scripts/phase2/stage2_seed_check.py` confirms all legs share `input_source`, `daily_dir`, `T_SEQ`,
both periods, `argo_profiles`, `argo_table`, `w_density`, `beta_nll`, `n` and the stage-1 baseline.
**[VERIFIED — live output]**

```
TEMPERATURE -- the only quantity with a stage-1 number to beat
  seed 42:  stage2 0.8854   stage1 0.9078   better by +0.0224
  seed 43:  stage2 0.9095   stage1 0.9078   better by -0.0018
  seed 44:  stage2 0.9158   stage1 0.9078   better by -0.0080

  mean improvement +0.0042 degC, spread 0.0304, sd 0.0160
  sign holds across all 3 seeds: NO  -- the effect does not survive a reseed
```

**Seed 42 was the lucky leg.** Its +0.0224 sits well inside the seed spread. **Stage 2 does not
improve temperature on satellite input**, and stage 1 remains the deliverable. E-S2-SAT-01 stands
unedited as the historical record; E-S2-SAT-02 is its correction.

Salinity and density are *new* claims with no stage-1 counterpart, so the question is stability:

| | s42 | s43 | s44 | mean | spread |
|---|---|---|---|---|---|
| salinity RMSE (psu) | 0.2571 | 0.2777 | 0.2737 | **0.2695** | 0.0207 (~8 %) |
| density RMSE (kg m⁻³) | 0.2900 | 0.3050 | 0.3166 | **0.3039** | 0.0266 (~9 %) |
| density calibration ratio | 1.245 | 1.281 | 1.491 | 1.339 | **0.246 (~18 %)** |

Salinity and density RMSE are reasonably stable. **The density calibration *ratio* is not** — and
that ratio is the uncertainty-quality indicator, so no stage-2 uncertainty claim may be quoted from
a single run. Salinity RMSE falls monotonically with depth apart from the surface — **0.368 psu at
5 m to 0.054 psu at 1000 m**, correlation 0.945–0.978 — the expected shape for this basin.

**A shared-code bug this exposed and fixed first:** `output._calibration_applies_to` matched on
T_SEQ and channels only, and a stage-2 checkpoint carries the **same** T_SEQ 11 and the **same**
seven channels as stage 1 — so stage-1 scales would have rescaled stage-2 σ and looked normal doing
it. *Exactly the failure that function exists to prevent, along an axis it did not look at.*

### 15.7 A missing D26 reported as a cold surface — rule 8's fifth instance

A NaN D26 (depth of the 26 °C isotherm) has **three** causes — land or below-seafloor, a column that
never cools to 26 °C, and a surface already below 26 °C — and both the script and the page called
all of them *"below 26 °C at the surface"*.

On the default May track it was wrong for **every one of the 22 NaN points**: **17 were LAND** (the
great circle crosses India) and 5 were warm-to-bottom columns. **ZERO had a cold surface**, in a
section reading 30.16–31.29 °C throughout. The page's default view said *"14 of 60 points never
reach 26 °C at the surface"* when all 14 were warm-to-bottom — **the opposite meaning.**

**On a cyclone chart "cold surface" is exactly the signal a reader is hunting for**, so mislabelling
land as that is the dangerous direction to be wrong in. Both now count the causes separately:
*"D26 62.1..97.9 m (22 points without a D26: 17 no valid water (land or dry cell), 5 never cool to
26 °C)"*. A regression test asserts the old wording cannot come back.

### 15.8 The pattern behind five bugs — and the rule that came out of it

| where | the absence | what it was reported as |
|---|---|---|
| `inference.py` | which bundle a checkpoint used | hardcoded `input_source: "glorys"` |
| `field.py` | `promoted_from` lives in the metrics, not the `.pt` | `"unpromoted"` — **about the SHIPPED model** |
| `eddy.summarise` | the caller never said which currents | hardcoded `"GLORYS reanalysis"` |
| `collocation_page` | the Argo table holds no rows for that year | *"floats are genuinely sparse"* — a claim about the ocean |
| `transect` (script + page) | land, or a column that never cools | *"below 26 °C at the surface"* |

**None was caught by a test.** The wrong answer is well-formed, plausible and correctly typed in
every case, so a shape check cannot see it. Four were found only by rendering the thing and reading
it against data already on hand.

**They share a direction, and that is the part worth remembering: the invented meaning is always the
interesting one.** GLORYS rather than unknown; sparse ocean rather than empty table; cold surface
rather than land. That is not chance — *a default gets reached for precisely because it reads like a
result, so the fabricated answer is by construction the one most likely to end up on a slide.*

This became **START_HERE rule 8**: *an absence is not a value.* A function that can mean "I don't
know" either returns `None`/NaN, or returns **the reason alongside the value**.

### 15.9 Smaller corrections, each caught by a check rather than by reading

* **A hardcoded provenance string that was accidentally true.** `eddy.summarise()` hardcoded
  `"source": "GLORYS reanalysis surface currents, not observations"`. True while the only caller read
  GLORYS grids; **false the instant the page could read satellite currents** — fed GLOBCURRENT, it
  still reported GLORYS.
* **`checkpoint: "unpromoted"` on a promoted model.** `promote_run.py` writes `promoted_from` into
  the *metrics* artifact, never into the checkpoint, so the `or "unpromoted"` fallback fired every
  time.
* **A 1,052-day date error, computed but never displayed.** `cube_page` offered GLORYS' 48
  2019-2022 dates under *every* source including "v2 satellite", and `predict_field` silently
  snapped each to the nearest of 388 real satellite days. The sidebar's own default (2022-07-15)
  rendered 2025-06-01 — **+1052 days away** — with `provenance.days_from_requested` computed and
  never read.
* **A chart that drew itself as a zigzag.** `mark_line(point=True)` with `x=RMSE`, `y=depth`:
  **Altair sorts a line by its X encoding unless given `order`**, and RMSE is not monotonic in
  depth, so the line crossed itself repeatedly. Nothing errored; the numbers were right; the picture
  said "unstable model". `validation_page` carried the identical defect in both panels, and so did
  the Argo overlay.
* **Invisible annotation text.** Streamlit themes axis text but **not** free `mark_text`, which
  defaults to black — rgb(0,0,0) on rgb(14,17,23), **1.11:1 contrast**. Found by measuring the
  rendered DOM, not by looking. Now `#787878` (4.30:1 light, 4.28:1 dark). The chart palette
  `#2a78d6` / `#d95926` was **computed with a validator, not chosen**: the previous grey `#999999`
  failed the chroma floor at 2.78:1, and a first fix `#eb6834` passed on white and failed the dark
  band.
* **numpy read `"20250601"` as the year 20250601** — caught by the author's own guard.
* **A cell-lookup convention bug shifted 75.5 % of Argo collocations.** Fixed, and the baseline
  re-measured afterwards.
* **`mc_dropout_predict` leaked `train()` mode to the caller** (D-017).
* **A row-count precondition became the vacuous pass it guarded against** (`test_validation`).
* **One Argo float came back twice on every cycle**, making the diagnostic look like corruption.
* **Two guards located `layer_fields_v2` by the string `"def layer_fields_v2"`** — which is a
  **prefix** of the newer `layer_fields_v2_stage2` defined above it, so both silently moved onto the
  stage-2 function, which uses salinity by design. Locators tightened to `"def layer_fields_v2("`.
* **The 1.8×–8.5× calibration magnitudes were withdrawn** — they were ~2× hot. Unit B was right; the
  corrected *direction* was kept, the magnitudes were not.
* **Altair's 5,000-row cap** silently truncated the TCHP map; lifted so it renders at full grid.
* **Streamlit does not reload deep imports:** editing `src/phase2/**` needs a server restart, and
  the symptom is an `AttributeError` for a function that plainly exists on disk. Recorded in
  AGENT_SYNC A23 so the next person does not lose an hour to it.
---

<a name="s16"></a>
## 16. Flaws, limitations and open items

This is the section to read before quoting anything. It is organised by how fixable each item is.

### 16.1 Scientific flaws in the shipped model

| # | flaw | magnitude | is it ours? |
|---|---|---|---|
| 1 | **The model runs warm.** Bias +0.1003 °C overall, peaking at **+0.657 °C at 50 m** | the cloud-dropout curve shows a bias correction is worth ~0.013 °C of RMSE, free | **mostly inherited** — the GLORYS target is +0.1078 °C warm against the same floats and the model is −0.007 against its own target. The **+0.447 °C** added at 50 m is ours |
| 2 | **The thermocline is the hardest depth.** RMSE peaks at **1.22 °C at 100 m**, correlation drops to 0.776 | the widest band in the profile | **mostly inherited** — GLORYS itself scores 1.042 °C there — but **0.178 °C is ours**. The 0.023 °C figure is Phase-1 and does not hold for v2 |
| 3 | **The mixed layer (20–50 m) is genuinely worse than the reanalysis** by +0.23 to +0.38 °C on v2 (+0.31 to +0.38 in Phase 1) | the one place effort would clearly pay | **ours** |
| 4 | **Climatology beats the model at 1000 m** by 0.012 °C — 14 of 15 depths, not 15 | small, and labelled on the chart | **ours**, and stated |
| 5 | **The Arabian Sea satellite penalty**: +0.0341 °C, sign holding 3/3 seeds | reproducible | **cause UNKNOWN** after four tested hypotheses |
| 6 | **Uncertainty is improved, not calibrated.** ±2σ covers **80.1 % at 50 m** against a 95.4 % nominal | mildly overconfident everywhere | **ours** |
| 7 | **The encoder has no missing-data channel.** A gap and average water arrive as the same number | see §10 | **ours**, architectural, unfixed |
| 8 | **Stage 2 does not improve temperature on satellite input** (3 seeds, sign does not hold) and is **not promoted, not frozen** | mean +0.0042 inside a 0.0304 spread | measured |
| 9 | **Stage-2 MLD is −14.12 m biased and its barrier layer +8.88 m**, from +0.19 psu of surface salinity bias against a 0.03 kg m⁻³ threshold | ~4× the 2.4 m signal the published claim rests on | **ours**; needs a better salinity head, not a UI change |
| 10 | **The density calibration ratio is unstable across seeds** (1.245 / 1.281 / 1.491, ~18 % spread) | that ratio is the uncertainty-quality indicator | no stage-2 uncertainty claim from one run |

### 16.2 Data limits that do not move

* **Sub-mesoscale structure is unresolvable at 0.25° (~25 km).** A real limit of the grid.
* **The satellite SSS product is blind to the Bay of Bengal freshwater plume** — it floors at
  **30.78 psu** where the real signal reaches **6.43**. A *sensor* limit, not a modelling gap.
* **Nothing predicts salinity at depth from satellite inputs.** The 7 channels carry a *surface* SSS
  only. This is why `physics_page` **refuses** MLD-by-density, the barrier layer and real-density
  OHC in v2 mode, showing an explicit *"refused, not approximated"* box instead of silently
  substituting GLORYS salinity. It is a **compliance boundary**, not an absence — the GLORYS
  salinity is sitting right there in the bundle, and a test asserts that `layer_fields_v2` neither
  reads it nor returns it.
* **The SOFAR axis is below our deepest level.** 94.75 % of full-depth cells have their sound-speed
  minimum at 1000 m; the tropical Indian Ocean axis sits near 1500–2000 m. A basin-wide axis-depth
  map would be a grid artifact 95 % of the time, so it is refused.
* **The wind-stress product runs 2019-01..2022-12 only** and cannot reach the 2025-26 window, so the
  upwelling panel produces a **signature, not an attribution** (`wind_attributed: False`).
* **Seasonal climatologies stay on the Phase-1 2019-2022 monthly record**, and say so. A four-year
  seasonal signal cannot be recomputed on a 388-day bundle without silently changing published
  magnitudes.
* **The bundle is 74 days stale** and cannot be extended without work: `sat_daily_pipeline.build_year`
  requires a GLORYS target and drops days lacking one — GLORYS `my` ends 2026-06-23, so every live
  day would be dropped and the bundle would come out **empty**. `build_year` is year-granular and
  overwrites the whole year npz; `download_wind_daily.download_months` clips to module constants;
  `build_daily_wind` has no incremental path; `inference.forecast` compares against a hardcoded
  `LAST_GLORYS` so **the guard inverts** once the bundle extends; `verify_sat_bundle` hard-fails
  without a matching GLORYS year. SSS lag (~6 d) also binds.

### 16.3 Not validated

* **Fronts are NOT validated.** The detector runs and July's strongest gradient (11.4 °C/100 km at
  11.4 N 51.5 E) sits in the Somali upwelling front region — encouraging, and not evidence. No front
  climatology or published census was checked. A percentile threshold *always* returns the sharpest
  gradients present, so it can never report "no fronts"; `threshold` and `mean_gradient` are returned
  so a flat field is visible as one.
* **The Great Whirl identification is [INFERRED].** That a ~243 km August anticyclone holds station
  at 7.5 N 53 E is **[VERIFIED]** in the data. That it *is* the Great Whirl rests on the standard
  description; no paper was re-read.
* **The Phase-1 OOD detector is not validated** — it flags **99.18 %** of the real test set because
  the local `X_train.npy` is the stale synthetic one (ssh mean 0.0017 vs 0.4421). **The detector is
  correct; the artifact is wrong.**
* **The whole literature matrix is `[ABSTRACT-ONLY]`.** No methods section of any cited paper has
  been read on this machine. That is enough to position the work; it is **not** enough to quote a
  hyperparameter, claim a paper did *not* do something, or assert a numerical comparison.
* **Indian-language and regional literature (INCOIS, NIO Goa, IITM) has not been searched** — and
  the sponsor knows it best.

### 16.4 Unresolved discrepancy

**The Validation Lab headline (RMSE 0.9638 / 879 profiles) still disagrees with the freeze manifest
(0.9078 / 962).** Flagged 2026-09-03, never traced. **[UNKNOWN]** — the likely reading is that the
Lab reports the *Phase-1* satellite-driven number from `argo_error_by_depth.json` while the manifest
reports the *v2* model, but that has not been confirmed and is recorded as open.

### 16.5 Novelty — the honest position

From `docs/NOVELTY_MATRIX.md`, which corrected its own seed:

* AI reconstruction of subsurface temperature from surface data — **NOT NOVEL** (Meng 2021; DORS
  2022; FFPG-net 2025; TS-Cast 2026; NeSPReSO 2025).
* Uncertainty-aware reconstruction — **already done, and better than ours**: TS-Cast predicts
  depth-dependent log error variances for T, S *and* density, parametric and calibrated.
* Physics-guided reconstruction — already done (FFPG-net EOF modes; TS-Cast EOS).
* **Observation-priority / where-to-measure-next — ALREADY DONE.** The seed matrix called this
  "potentially novel"; a targeted search found it is an established area with dedicated methods
  (optimising BGC Argo deployment to minimise objective-mapping uncertainty, JTECH 40(11) 2023;
  optimal sensor placement via differentiable Gumbel-Softmax; FloatCast 2026). **Ours is a simple
  heuristic — `anomaly × uncertainty × sparsity` — with no cost model, no float drift physics, no
  budget constraint, and a σ term measured as overconfident.**
* *"First to reconstruct subsurface temperature in the NIO"* — **not defensible.** Global methods
  (DORS 2022) already include the North Indian Ocean.

**The claim that survives:**

> A North-Indian-Ocean-focused, independently-validated reconstruction **system** — surface →
> subsurface temperature with uncertainty, anomaly and an observation-priority layer — built and
> verified end to end. We are **not** proposing a new reconstruction method, and we do **not** claim
> novelty for uncertainty-guided observation targeting; both are established fields whose state of
> the art exceeds our MVP.

The observation-priority layer is framed as *"regions where additional observations may provide high
scientific value"* — **never** *"the AI tells MoES where to deploy Argo floats."* That framing is
marked non-negotiable in `docs/ARCHITECTURE.md`.

### 16.6 Engineering and process risks — live right now

1. **HEAD is 26 commits ahead of `origin/main` and none of it is pushed.** All of §12's work — the
   API, the export, the four new dashboards, the device fix — exists on one laptop.
2. **`artifacts/` and `data/` are gitignored (222 MB + 31 GB).** Every checkpoint and every bundle
   lives outside version control, transferred by zip. The `frozen_manifest.json` checksums are the
   only thing that lets the other machine prove its files are the ones that were scored.
3. **The cloud-dropout work is uncommitted** — module, script, page, tests and artifact.
4. **Two `frozen_manifest` claims (0.8548, 0.8593) have never been re-verified on this disk.** They
   are labelled as such, but they are the two most flattering numbers in the project.
5. **`accept.py` carries one known pre-existing failure** comparing two *legacy Phase-1* artifacts
   with different profile-retention rules. The RMSE agreement it also checks passes at 0.0213 °C,
   and neither artifact underwrites the shipped model.
6. **Inference is on CPU by default** (32 s per whole-field reconstruction) although a measured
   4.2× CUDA speedup exists. Deliberate — switching days before a demo would make an exported file
   differ in its last digits from the page beside it — but it is a latent performance ceiling.
7. **Five copy-pasted `_commit()` helpers** remain, deliberately untouched as working pipeline code.
8. **`predict_field` mutates `predictor.ds.index`** and restores it in a `finally`; `reconstruct`
   overwrites it and **never restores it**. The lock papers over this. The correct fix reopens the
   field-equals-point guarantee and was deferred.
9. **Fifteen Streamlit ports and one uvicorn port** is a lot of surface for a demo. Nothing
   aggregates them into a single app.

### 16.7 Never started, or blocked

| item | state |
|---|---|
| Spatial CNN on the monthly archive (audit F3) | **never started** — only 48 timesteps |
| Subsurface marine heatwave (audit F7) | **unbuilt, no longer impossible** — was blocked at monthly cadence; 388 consecutive days now exist |
| Eddy **tracking** (as opposed to detection) | **unbuilt** — same reason |
| Ocean Sentinel (audit F9) | **never started** |
| Observation Priority v2 (audit F10) | **never started**; v1 heuristic exists and is not novel |
| Cyclone case study (viz F4) | **unblocked and specified** — SHAKHTI (74 kt, 47/47 points in box) with MONTHA as the BoB counterpart; **no code written** |
| Moored-buoy validation (viz F6) | **blocked** — source identified, coverage confirmed to span our window, five files named; needs a machine that can reach `coastwatch.pfeg.noaa.gov` |
| INCOIS LAS gridded Argo (PS req 16) | **blocked** — their Ferret/F-TDS backend is down; re-probe before any public claim |

---

<a name="s17"></a>
## 17. Current state of the working tree

`git status --short` at 2026-09-05 21:09 IST **[VERIFIED]**:

```
 M .claude/launch.json                    <- port 8515 for the dropout page
 M docs/phase2/AGENT_SYNC.md              <- the next sync entry, in progress
 M src/phase2/viz_explainer.py
 M tests/phase2/test_viz_explainer.py
?? app/phase2/dropout_page.py             <- 226 lines, port 8515
?? scripts/phase2/run_cloud_dropout.py    <- 253 lines
?? src/phase2/validation/dropout.py       <- 142 lines
?? tests/phase2/test_dropout.py           <- 207 lines, 15 tests
?? PROJECT_RECORD.md                      <- this file
?? README_UNZIP_ME_FIRST.txt              <- data-transfer instructions
?? OceanEmbed_SIH26066.pptx               <- 62 KB pitch deck
?? OceanEmbed_SIH26066.BACKUP-...pptx     <- 330 KB prior version
```

**The tree moved while this document was being written.** `dropout_page.py`,
`tests/phase2/test_dropout.py` and the AGENT_SYNC edit all appeared between 20:48 and 21:09, from a
concurrent session. Everything above is a snapshot at 21:09, not a stable state.

Because the tree is dirty, `freeze.py --check` reports **NOT FROZEN — 1 check failed (working tree
clean)**. **All 17 other checks pass.** **[VERIFIED — live run]** Committing restores the freeze.

Artifacts that postdate HEAD and are untracked (as all of `artifacts/` is): `cloud_dropout.json`,
`buoy_probe.json`, `ibtracs_probe.json`, `export_timing.json`, `tscast_stage2_sat_s2_s43.pt` /
`_s44.pt` and their metrics, `argo_daily_period_ts.parquet`, `argo_ts_{2025,2026}.parquet`.

---

<a name="s18"></a>
## 18. How to reproduce every number here

All commands assume the repo root and the project venv. Set `PYTHONPATH=src`.

Verify the shipped model is what it claims to be (18 checks):

```bash
PYTHONPATH=src python scripts/phase2/freeze.py --check
```

Audit all 17 PS requirements against artifacts on disk:

```bash
PYTHONPATH=src python scripts/phase2/audit_ps.py
```

Verify the satellite bundle is genuinely satellite (44 checks incl. the GLORYS-injection negative test):

```bash
PYTHONPATH=src python scripts/phase2/verify_sat_bundle.py
```

Re-score a checkpoint from disk instead of trusting its sibling JSON:

```bash
PYTHONPATH=src python scripts/phase2/rescore_checkpoint.py --checkpoint artifacts/tscast_stage1.pt
```

Re-run the stage-2 3-seed comparison (reads each run's own metrics JSON, transcribes nothing):

```bash
PYTHONPATH=src python scripts/phase2/stage2_seed_check.py
```

Re-run the cloud-dropout experiment (~31 s; refuses to write if the control disagrees):

```bash
PYTHONPATH=src python scripts/phase2/run_cloud_dropout.py --tag sat_7ch_s42 --daily-dir data/processed/daily_sat/v001
```

Retrain the deliverable — `--daily-dir` is **not optional**; omitting it silently trains on GLORYS:

```bash
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 --daily-dir data/processed/daily_sat/v001 --t-seq 11 --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5 --encoder cnn3d --decoder simple --tag sat_7ch_s42
```

Retrain stage 2 with an explicit seed (requires the T+S Argo table):

```bash
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage2 --daily-dir data/processed/daily_sat/v001 --t-seq 11 --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5 --seed 42 --tag sat_s2
```

Run the 3-seed channel ablation harness:

```bash
PYTHONPATH=src python scripts/phase2/run_sat_ablations.py
```

Re-probe the two blocked external sources:

```bash
PYTHONPATH=src python scripts/phase2/probe_incois_las.py
```

Export one day to NetCDF:

```bash
PYTHONPATH=src python scripts/phase2/export_field.py --date 2026-06-23 --out field.nc
```

Serve the API (port 8511, 127.0.0.1 only):

```bash
PYTHONPATH=src python -m uvicorn phase2.api.app:app --host 127.0.0.1 --port 8511 --workers 1
```

Launch any dashboard (ports in `.claude/launch.json`; the v2 model dashboard is 8507):

```bash
PYTHONPATH=src python -m streamlit run app/phase2/tscast_page.py --server.port 8507
```

Full test suite:

```bash
python -m pytest -q
```
---

<a name="s19"></a>
## 19. Method: how this project is run

This is not decoration — it is the reason the numbers above can be trusted, and it is the part of
the work that is genuinely unusual.

### 19.1 The evidence tags

Every claim carries **[VERIFIED]** (executed / inspected), **[INFERRED]** (reasonable, untested) or
**[UNKNOWN]** (not checked). Only VERIFIED claims are facts. This is enforced socially, in
`CLAUDE.md`, and it is visible throughout the docs.

### 19.2 The 15 "never assume" rules (`CLAUDE.md`)

Never claim (1) code works unless executed, (2) a dataset has a variable unless inspected, (3) a
model improves unless the comparison ran. Never fabricate (4) metrics, (5) uncertainty, (6)
citations, (7) novelty without a literature check. (8) Never invent missing requirements. Never
assume (9) tensor dims, (10) units, (11) coordinate order, (12) temporal alignment, (13)
missing-value handling, (14) a valid train/test split. (15) If uncertain, say it is unverified.

### 19.3 The eight START_HERE rules

1. `main` is untouchable.
2. `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/` and the baseline tests are **read-only**.
   Need different behaviour? An adapter in `src/phase2/`.
3. Stay in your own area; cross-area change → post an ASK in `AGENT_SYNC.md` first.
4. **Never mark VALIDATED because tests pass.** TESTED = the code does what it intends. VALIDATED =
   the science was checked against something independent.
5. **Never adjust a scientific test to accommodate synthetic data.** This nearly happened and was
   refused.
6. **Verify constants against published values before building on them.** The 15 EOS-80 coefficients
   were checked against four UNESCO values *before* any physics used them; Mackenzie's were pinned
   the same way.
7. **A shape check is not a validity check.** Ask of every array: *could this have been produced
   without real data behind it?*
8. **An absence is not a value.** (§15.8)

**Rule 7 has caught five bugs:** `.gitignore` excluding `src/oceanembed/data/`; 46 m of extrapolated
"500 m" values; SSS stacked `(12,1,1,100,240)` past a bounds check that inspects values not shape;
MC-dropout claiming ±0.26 °C where the real error was 2.0 °C; the model painting 1000 m temperatures
in the ~90 m Persian Gulf. **All five: correct arrays, plausible values, wrong data.**

**Rule 8 has caught five of its own, and rule 7 could not see any of them** (§15.8).

### 19.4 The definition of DONE

Code exists **+** tests pass **+** ran on real/fixture data **+** output inspected **+** reproducible
(seed + config saved) **+** docs updated **+** committed. For ML also: training done, validation
done, metrics + checkpoint + seed + config logged to `docs/EXPERIMENT_LOG.md`. *"It should work" is
NOT done.*

### 19.5 The three-seed rule

An effect at the ±0.02 °C scale is not believed until its sign holds across three seeds. **Three
separate effects have failed that test:** wind's ablation flipped −0.0149 → +0.0111; the SSH
contrast was 1 of 3 presented as 3 of 3; stage-2 temperature was +0.0224 on seed 42 and negative on
43 and 44.

### 19.6 Contract-first

Shapes, filenames and signatures are frozen in `docs/DATA_CONTRACT.md` and `docs/MODEL_SPEC.md`, and
constants live in `src/oceanembed/config.py`. Import them — never hardcode. To change a contract:
edit the contract file first, tell the team, then code.

### 19.7 Real-data-only

No fabricated metrics, uncertainty or citations. Cached demo results are allowed **only if the real
model generated them**, and the UI must label them CACHED vs LIVE.

### 19.8 What actually found the bugs

Worth tallying, because it is the most transferable lesson in the project:

| how a bug was found | count (approx., from the commit record) |
|---|---|
| **rendering the page and reading it against data already on hand** | the largest single category — 4 of rule 8's 5, all 4 of the click map's, the Palk Strait SOFAR bug, the zigzag chart, the invisible annotation |
| a purpose-built **negative test** (inject the bug, watch the guard fire) | the GLORYS-injection check, the port collision, the impostor checkpoint, the relaxed SOFAR guard |
| running a **matched 3-seed comparison** | the wind reversal, the SSH retraction, the stage-2 retraction |
| **measuring** something that had been estimated | the export timing, the CUDA speedup, the sound-speed budget |
| an ordinary unit test | comparatively few of the *interesting* ones |

*A shape check cannot see a fabricated label. Only looking can.*

---

<a name="s20"></a>
## 20. Appendix

### 20.1 Where the authoritative record lives

| document | size | what it is |
|---|---|---|
| `CLAUDE.md` | 3.5 KB | the operating constitution: evidence tags, the 15 never-assume rules, file ownership, contract-first, real-data-only |
| `PHASE2_STATUS.md` | 19.5 KB | the feature-by-feature status table (17 rows) with the "WHICH NUMBER IS THE HEADLINE" warning at the top |
| `docs/HANDOFF.md` | 33 KB | the freeze record plus every verification pass, appended by everyone |
| `docs/EXPERIMENT_LOG.md` | 11.8 KB | E-CAL-02, E-S2-SAT-01/02/03 — experiments *with* their retractions |
| `docs/DECISIONS.md` | 23.7 KB | 19 ADRs, D-001 … D-019 |
| `docs/phase2/AGENT_SYNC.md` | 214 KB | the two-machine wire: A1–A23, D1–D11 |
| `docs/phase2/START_HERE.md` | 9.8 KB | orientation for a fresh session; the 8 rules |
| `docs/phase2/DARSHAN_BUILD_SPEC.md` | 276 KB | the 3,570-line implementation spec, *"built by reading the code, not remembering it"* |
| `docs/phase2/EXTERNAL_DATA_PROBE.md` | 7.4 KB | cyclone tracks (unblocked) and moored buoys (blocked) |
| `docs/INCOIS_PROBE.md` | 5.7 KB | the PS req 16 blocker, with every probe reproduced |
| `docs/DATA_CONTRACT.md` | 10 KB | frozen shapes, filenames, units, conventions |
| `docs/MODEL_SPEC.md` | 4.7 KB | frozen tensor contract and public signatures |
| `docs/ARCHITECTURE.md` | 4 KB | the module seam diagram and the observation-priority method |
| `docs/{LITERATURE,NOVELTY}_MATRIX.md` | 14 KB | prior work, checked at abstract level |
| `docs/phase2/tscast_output_schema.md` | 7.8 KB | the output contract, §5 of which is now asserted in code |
| `PHASE2_ARCHITECTURE_AUDIT.md` | 10.5 KB | the Phase-2 opening audit (F1–F10) |
| `PHASE2_DATA_MANIFEST.json` | 7 KB | 62 files with SHA-256, for the cross-machine transfer |
| `TEAM_PLAN/` | — | `SHARED_BRIEF.md` + one file per unit |

### 20.2 Decision index (`docs/DECISIONS.md`)

```
D-001  training truth = GLORYS12; validation = independent Argo
D-002  lead model = per-column MLP; baselines = climatology + LightGBM
D-003  uncertainty = MC-dropout (LightGBM quantiles as backup)
D-004  deadline treated as a 5-day critical path
D-005  team = 3 units; Mitun+Niru share one account
D-006  tables use parquet (pyarrow) with CSV fallback
D-007  normalisation stats live INSIDE the model checkpoint
D-008  DEPTHS -> 15 levels to 1000 m + stop silent deep extrapolation
D-009  predict_mlp takes RAW features; the model normalises internally
D-010  fixture-trained checkpoints are stamped and refuse to pass silently
D-011  the fixtures encode only ONE signal (SST) -- CLOSED, multi-feature physics added
D-012  LightGBM: one booster per depth, quantiles in a separate artifact
D-013  FINDING: on the current fixtures, MLP vs LightGBM is an UNINFORMATIVE comparison
D-014  training and evaluation MUST share one data loader
D-015  a sub-2% RMSE gap is a TIE, and ties ship the simpler model
D-016  FINDING: MC-dropout is OVERCONFIDENT -- re-measured on real data, depth pattern INVERTED
D-017  BUG: mc_dropout_predict leaked train() mode to the caller
D-018  RED-TEAM: the SYNTHETIC banner can silently switch itself off
D-019  RED-TEAM: fresh-clone verification is part of Definition of Done
```

### 20.3 Literature — the papers this work is positioned against

All rows are **`[ABSTRACT-ONLY]`**: compiled from published abstracts and landing pages. **No
methods section has been read on this machine.**

| paper | region | inputs | depth | model | uncertainty | overlap with us |
|---|---|---|---|---|---|---|
| **Meng et al. 2021**, JGR Oceans, doi:10.1029/2021JC017605 | Central Pacific | SLA, SST, SSS, wind stress | 26 levels to 2000 m | CNN, 15 hidden layers | none | **high on approach**; monthly, Pacific |
| **TS-Cast 2026**, *Ocean Science* 22, 2161 | NW Pacific (Kuroshio) | SST, SSS, ADT **+ satellite error fields** | 10–700 dbar | U-Net + **FiLM** | **yes** — depth-dependent log variances for T, S, ρ | **the paper we reimplemented**; the one to compare against honestly |
| **DORS 2022**, *Remote Sensing* 14(13) 3198 | **global** | multisource RS + gridded Argo | to 2000 m | **ConvLSTM** | not stated | its existence is why a global-novelty claim is unavailable |
| **FFPG-net 2025** | — | — | — | feature fusion + physical guidance (EOF modes) | — | physics-guided reconstruction is already done |
| **NeSPReSO 2025** | — | — | — | — | — | beats GEM, MLR, ISOP — a stronger baseline bar than ours |
| **JTECH 40(11) 2023** | — | — | — | objective-mapping optimisation of BGC Argo deployment | — | **our observation-priority idea, done rigorously** |

TS-Cast's stated limit — that surface data bounds deep and high-frequency skill — **is the same one
we must report**, and §8.3 measures our version of it.

### 20.4 Two measured disagreements with the paper we reimplemented

1. **The 31-day input window is the worst of three at our data scale** (0.9267 vs 0.8529 at 11 days
   vs 0.9096 at 1 day) and carries the largest warm bias. TS-Cast used ±15 days on 1/8° data with
   ~155 k profiles; at our sample budget ±5 days wins.
2. **The eq. 5 density constraint costs accuracy** (0.8593 with it ON vs 0.8548 with it OFF) and
   worsens the warm bias (+0.1598 vs +0.1055).

Both are reported as **measured disagreements**, not as reimplementation failures — and both are
qualified by the fact that our data scale is far smaller than theirs.

### 20.5 One-paragraph summary, for a reader with thirty seconds

> OceanEmbed reconstructs 15-level subsurface ocean temperature (0–1000 m) across the North Indian
> Ocean at 0.25°, daily, **from satellite surface observations alone**. The shipped model is
> TS-Cast-NIO stage 1 — a 3-D CNN satellite encoder feeding a decoder that *adjusts the monthly
> climatology* rather than guessing a profile — 548,582 parameters, trained on 388 consecutive days
> of seven-channel satellite input against a GLORYS12V1 target. Against **962 independent Argo
> profiles it scores RMSE 0.9078 °C, correlation 0.8812, bias +0.1003 °C, and +26 % skill over
> climatology**, beating climatology at 14 of 15 depths. It ships with a ±2σ band whose coverage is
> reported as a **range** (80.1–95.5 % by depth) because the mean would hide an 80 % depth, fifteen
> dashboards, a NetCDF export and an HTTP API, 820 tests, an 18-check freeze, a 44-check bundle
> verifier and a 17-row PS audit that reads **16 PASS / 0 FAIL / 1 BLOCKED**. Its known flaws are
> stated rather than hidden: it runs warm, its mixed layer is worse than the reanalysis, its
> thermocline error is inherited from the training target, an Arabian Sea satellite penalty is
> reproducible across seeds and **unexplained after four tested hypotheses**, and its uncertainty is
> improved rather than calibrated. It claims **system-level** contribution only — the reconstruction
> method and the observation-priority idea are both published prior art.

---

*End of record. Every figure above was read from a file or produced by a command during compilation
on 2026-09-05 at commit `139cb7e`. Figures that could not be checked here are tagged
**[INFERRED]** or **[UNKNOWN]** and are listed in §16. The working tree was moving during
compilation; §17 is a snapshot at 21:09 IST.*
