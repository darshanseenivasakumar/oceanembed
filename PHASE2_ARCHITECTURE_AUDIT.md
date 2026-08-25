# PHASE2_ARCHITECTURE_AUDIT.md

**Stage 1 deliverable. No Phase-2 feature code has been written.**
Branch: `phase2` (level with `main` @ `4995444`, 142 tests passing).
Audit date: 2026-08-26. Author: Unit B (Darshan).

---

## 1. BASELINE STATUS — FROZEN AND HEALTHY

`main` is tagged **`v1.0-demo-aug30`** and is the Aug-30 demo. It is **read-only for Phase 2**.

| check | result |
|---|---|
| Tests | **142 passed, 1 skipped** |
| App | serves HTTP 200, no tracebacks |
| Provenance | `real-glorys`, 15 depths, not stale |
| Determinism | identical across repeated runs [VERIFIED] |
| Fresh-clone install | passes on an independent dependency resolve |

**Headline (reproducible):** satellite-driven reconstruction vs **879 independent Argo profiles** —
RMSE **0.9638 °C**, skill **+0.387** vs climatology, 15 depths to 1000 m.

---

## 2. CURRENT ARCHITECTURE

```
CMEMS GLORYS12 (48 dates 2019-2022) ─┐
OSTIA/DUACS/Multiobs L4 (24 dates) ──┼─> preprocess ─> data/processed/*.npz
Argo GDAC (2,455 profiles, 2022) ────┘                        │
                                                              v
                                          build_samples -> artifacts/X,y,meta
                                                              │
                        MLPProfile (11->128->128->15, 19,983 params)  +  LightGBM (15 boosters)
                                                              │
                                        inference/predict.py :: reconstruct() / reconstruct_grid()
                                                              │
                                       Streamlit app + 4 panels (profile/map/priority/validation)
```

### Frozen baseline — DO NOT MODIFY
`src/oceanembed/` (all), `app/streamlit_app.py`, `app/panels/`, `scripts/`, `tests/`, `config.py`.

### Safe to IMPORT (stable public API, verified present)
| function | gives Phase 2 |
|---|---|
| `predict.reconstruct(lat, lon, date)` | point profile + spread + measured error + anomaly |
| `predict.reconstruct_grid(date)` | full 3-D field: temp / uncertainty / anomaly / priority |
| `predict.set_source / current_source / source_available` | GLORYS ↔ satellite switching |
| `predict.provenance()` | data-source stamp incl. staleness detection |
| `predict.available_dates()` | valid query dates |
| `climatology.climatology_predict(meta)` | baseline reference |
| `validation.metrics.compute_metrics()` | RMSE/MAE/R²/per-depth/skill |
| `uncertainty.mc_dropout_predict / calibration_ratio / relative_uncertainty` | spread + calibration diagnostics |
| `products.anomaly` (+`standardized_anomaly`, `flag_extremes`) | anomaly products |
| `products.observation_priority()` | existing 3-factor heuristic |
| `utils.grids` | lat/lon↔index, cell_id, cyclic encodings |

**Reuse rule:** import these. Do not re-implement, do not edit. Wrap in `src/phase2/` adapters if
behaviour must differ.

---

## 3. CANONICAL CONVENTIONS (already established — Phase 2 must inherit, not redefine)

```
LAT     arange(5.0, 30.0, 0.25)      100 cells, ascending
LON     arange(45.0, 105.0, 0.25)    240 cells, ascending, 0-360 style (no wrap in-domain)
DEPTH   [0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]  15 levels, positive-down, metres
TIME    datetime64[D], 48 GLORYS dates / 24 satellite dates, one per month
UNITS   temperature °C · salinity PSS-78 · SSH m · currents m/s
SPLIT   train 2019-2021 · test 2022 (by TIME, never random)
SEED    42
MASKS   land_mask (100,240)   valid_mask (100,240,15) = real bathymetry
```

`phase2/config/ocean_domain.yaml` must be **generated from `config.py`**, never hand-typed.

---

## 4. 🔴 DATA GAPS — THESE CONSTRAIN THE TEN FEATURES

Measured on disk, not assumed. **This is the most important section of the audit.**

| gap | evidence | features affected |
|---|---|---|
| **No subsurface salinity.** `grids.npz` has surface `sss` only; no 3-D salinity field. | `'so' in grids.npz` → **False** | **F5 OHC** — density needs T *and* S. |
| **No wind data at all.** No wind product downloaded. | no `*wind*` in `data/raw/` | **F6 upwelling** — the spec itself says do not infer wind-driven upwelling without wind. |
| **Monthly sampling, not daily.** 48 GLORYS dates over 4 years = 1/month. | `times` = 48 values | **F7 persistence** — a marine heatwave is defined on ≥5 consecutive *days*. Cannot be computed. **F6 eddy tracking** likewise. |
| **Satellite covers 24 dates vs GLORYS 48.** | `(24,100,240)` vs `(48,…)` | **F1 collocation** — satellite unavailable for half the GLORYS dates. |
| **Argo is test-year only (2022).** | `argo_test.parquet` | **F8 Validation Lab** — no Argo for train years. |
| **24% of cells shallower than 1000 m.** | `valid_mask` | all 3-D features must respect bathymetry. |

### Honest consequences — decide these BEFORE building
1. **OHC (F5)** is computable only under an assumed constant seawater density and heat capacity.
   That is defensible **if documented**. Alternative: download GLORYS `so` at depth (~+2.6 GB, ~2 h).
2. **Upwelling (F6)** must either be dropped, downloaded (CMEMS wind), or reframed as
   *"cold-surface + raised-thermocline signature"* with **no wind attribution**.
3. **Persistence (F7)** must be dropped or the data densified to daily/weekly.
   A "marine heatwave" label cannot be honestly issued on monthly snapshots.
4. **F6 eddy tracking over time** is not possible at monthly cadence — single-snapshot eddy
   *detection* is, tracking is not.

**Recommendation:** before F5–F7, run one background download for **subsurface salinity + wind**
(~3 h, resumable, same pattern as the GLORYS pull). That converts three "cannot do honestly"
features into real ones. This is the single highest-value pre-build action.

---

## 5. TWO AGENTS, NOT THREE

The source prompt assumes three Claude accounts. We have **two** (Darshan, Arjhun), so ownership is
redistributed. **No agent edits another's area.** Baseline stays read-only for both.

### DARSHAN (Unit B) — DATA, 3D, VALIDATION
Owns `src/phase2/data/`, `src/phase2/cube/`, `src/phase2/validation/`, `app/phase2/` shell,
`phase2/config/`, provenance, coordinate consistency.

| feature | branch |
|---|---|
| F1 Collocation engine | `phase2/collocation` |
| F2 OceanCube 3-D model | `phase2/ocean-cube` |
| F8 Validation Lab | `phase2/validation` |
| F10 Observation Priority v2 | `phase2/observation-priority` |
| UI shell + 3-D view | `phase2/ui-3d` |

### ARJHUN (Unit A) — AI, PHYSICS, MONITORING
Owns `src/phase2/models/`, `src/phase2/physics/`, `src/phase2/events/`, `src/phase2/reliability/`,
`src/phase2/sentinel/`.

| feature | branch |
|---|---|
| F3 Spatial CNN model | `phase2/spatial-ai` |
| F4 Calibrated uncertainty + OOD | `phase2/reliability` |
| F5 Physics (thermocline / MLD / OHC) | `phase2/physics` |
| F6 Event detection | `phase2/events` |
| F9 Ocean Sentinel | `phase2/sentinel` |

**Shared contract file** (edited by agreement only, like the Phase-1 DATA_CONTRACT):
`docs/phase2/data-model.md` — defines the OceanCube schema both sides code against.

---

## 6. PROPOSED PHASE-2 FILE TREE

```
src/phase2/
  config/ocean_domain.yaml        # GENERATED from config.py
  data/collocation.py             # F1   [Darshan]
  cube/ocean_cube.py              # F2   [Darshan]
  models/spatial_cnn.py           # F3   [Arjhun]
  reliability/calibration.py ood.py  # F4 [Arjhun]
  physics/thermocline.py mld.py ohc.py # F5 [Arjhun]
  events/eddy.py fronts.py upwelling.py # F6 [Arjhun]
  events/heatwave.py              # F7   [Arjhun]
  validation/lab.py               # F8   [Darshan]
  sentinel/                       # F9   [Arjhun]
  priority/next_best_obs.py       # F10  [Darshan]
  provenance.py                   # shared record stamp [Darshan]
app/phase2/                       # nav layer; baseline page untouched
tests/phase2/                     # mirrors the above
docs/phase2/                      # 10 docs per the spec
scripts/phase2/benchmark_models.py
reports/phase2/
```

---

## 7. RECOMMENDED IMPLEMENTATION ORDER

Dependencies force this; it is not arbitrary.

1. **F1 Collocation** — everything else consumes its records.
2. **F2 OceanCube** — the canonical object; F5–F10 all read it.
3. **Provenance + coordinate consistency** — must exist before any number reaches a UI.
4. **F5 Physics** — pure functions on a profile; testable immediately.
5. **F4 Reliability/OOD** — needs F2 + baseline uncertainty.
6. **F8 Validation Lab** — needs F1 + F2.
7. **F3 Spatial CNN** — heaviest; do after the data layer is trustworthy.
8. **F6 Events**, **F7 Heatwave** — gated on the data gaps in §4.
9. **F9 Sentinel**, **F10 Priority v2** — consume everything above.
10. **3-D UI + integration.**

---

## 8. RISKS

| risk | mitigation |
|---|---|
| Phase-2 code accidentally edits baseline | all new code under `src/phase2/`; import-only; CI check that `main` files are unchanged |
| Two agents collide | strict ownership (§5); one shared contract file |
| Feature built on data we do not have | §4 gaps resolved **before** F5–F7 start |
| A number in the 3-D UI disagrees with the backend | UI must call the OceanCube, never recompute — spec §15 |
| "Validated" claimed because tests pass | `PHASE2_STATUS.md` separates TESTED from VALIDATED |
| Repeat of Phase-1 pattern: correct arrays, plausible values, wrong data | every feature needs a *scientific* sanity test, not just a shape test |

---

## 9. EXACT COMMANDS TO RUN THE BASELINE

```bash
git checkout main            # frozen demo
pip install -r requirements.txt && pip install -e .
python -m pytest -q                     # expect 142 passed, 1 skipped
python -m streamlit run app/streamlit_app.py
```
Requires `artifacts/` (142 MB) and `data/processed/` (35 MB). **`data/raw/` (2.9 GB) is NOT needed
at runtime** — only to rebuild.

---

## 10. BLOCKERS BEFORE FEATURE WORK

1. **Decide the §4 data question** — download subsurface salinity + wind (~3 h), or formally
   de-scope OHC-with-density, wind-driven upwelling, and heatwave persistence.
2. **Confirm the two-agent split** in §5.
3. Nothing else blocks. F1/F2 can start immediately on existing data.

**STAGE 1 COMPLETE — awaiting approval before any Phase-2 feature code.**
