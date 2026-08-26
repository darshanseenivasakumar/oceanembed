# data-model.md — the OceanCube schema

**SHARED FILE.** Both units code against this. To change it: edit here first, post in
`AGENT_SYNC.md`, then change the code. Never the other way round.

**Owner of the implementation:** Unit A (Arjhun), transferred from Unit B 2026-08-26.
**Implementation:** `src/phase2/cube/ocean_cube.py` · **Branch:** `phase2-ocean-cube`
**Status:** F2a implemented, 22 tests. F2b (3-D rendering) not started.

---

## 1. What an OceanCube is

One timestamp's reconstructed subsurface temperature, plus everything needed to use it honestly:
the bathymetry, the uncertainty, the anomaly, and provenance.

```python
from phase2.cube import OceanCube, BelowSeafloorError

cube = OceanCube.reconstruct("2022-07-15", source="satellite")
cube.profile(15.0, 88.0)        # one column
cube.depth_slice(100)           # one level
cube.section(lat=18.0)          # vertical section
cube.value_at(26.0, 52.5, 1000) # raises — the Persian Gulf is 30 m deep here
```

### Fields

| field | shape | dtype | meaning |
|---|---|---|---|
| `date` | scalar | date | the grid date actually used (may differ from the one requested) |
| `temperature` | `(100, 240, 15)` | float64 | °C, NaN below the sea floor |
| `valid_mask` | `(100, 240, 15)` | bool | **True = real water at that depth** |
| `land_mask` | `(100, 240)` | bool | True = land, from the **active source** |
| `uncertainty` | `(100, 240, 15)` or `None` | float64 | °C, 1σ MC-dropout — **see §5, do not present as confidence** |
| `anomaly` | `(100, 240, 15)` or `None` | float64 | °C vs monthly climatology |
| `provenance` | dict | | what produced it (§4) |

Grid and depths are **imported from `oceanembed.config`** — `LAT` (100), `LON` (240),
`DEPTHS` (15 levels, 0→1000 m). Nothing in the cube hardcodes them, and a wrong-shaped array is
refused with `CubeShapeError` rather than reshaped.

All arrays are handed out **read-only**. The cube is a contract object shared between consumers;
an in-place write would corrupt it for everyone else with nothing raising.

---

## 2. The sea floor is a REFUSAL, not a NaN

This is the reason the class exists.

`predict.reconstruct_grid` already NaNs below-bathymetry cells. NaN is easy to `nanmean` over, plot,
or propagate — Phase 1 shipped 1000 m temperatures for the ~20 m Persian Gulf, and a NaN would have
hidden it just as well as a plain number.

- **`value_at()` raises `BelowSeafloorError`**, naming the cell and its actual depth:
  ```
  no water at 1000 m at 26.00N 52.50E: the sea floor there is at 30 m. Requested 1000 m.
  ```
- **`profile()` returns `seafloor_depth_m`, `n_levels_with_water` and a `below_seafloor` mask** —
  the sea floor is stated, not implied by a run of NaNs.
- **`depth_slice()` returns `coverage_fraction`** — a 1000 m map covers 76% of the basin, and a map
  that does not say so implies a complete field.
- **A cube cannot be built without bathymetry.** `_valid_mask_or_all_true` raises rather than
  defaulting to all-True, because all-True is exactly the Phase-1 bug.

[VERIFIED 2026-08-26] coverage by depth (cells both masks call ocean):
100% at 0 m · 92.2% at 30 m · 82.9% at 100 m · **76.1% at 1000 m**.

---

## 3. Two known data quirks the schema exposes

### 3.1 The coastline disagreement — 464 cells

`land_mask` comes from the **active source**; bathymetry **always** comes from GLORYS
(`predict._valid_mask` says so: the satellite file has no subsurface truth to derive a sea floor
from). The two products draw the coastline differently.

[VERIFIED] the masks disagree on **464 cells**: **179 ocean in the satellite product only**, 285 in
GLORYS only. These are the same cells Unit B's F1 emits as `COASTLINE_DISAGREEMENT`.

Consequence: a `source="satellite"` cube has 179 cells with a surface temperature but **no water at
any depth**, so raw surface coverage is 98.47% rather than 100%.

`cube.coastline_disagreement()` reports them. `coverage()` returns **both** denominators —
`coverage_fraction` (cells both masks call ocean) and `coverage_fraction_raw` (all land-mask ocean).
A `source="glorys"` cube has zero disagreement by construction, and a test asserts it.

### 3.2 Depth snapping, and ties

`config.DEPTHS` is irregular (5 m steps near the surface, 200 m near the bottom), so a requested
depth can land between levels. Every slice reports `depth_requested_m` and `snapped_by_m`.

**Ties resolve SHALLOWER.** 400 m is exactly 100 m from both 300 and 500; it snaps to **300**.
The direction is arbitrary but fixed, documented and tested — shallower is the conservative choice
because more cells have water there.

---

## 4. Provenance travels with every extraction

The cube carries provenance, and **every** slice/section/profile returns it with an `extraction`
block describing that specific call.

```python
{
  "produced_by": "phase2.cube.OceanCube.reconstruct",
  "wraps":       "oceanembed.inference.predict.reconstruct_grid",
  "source":      "satellite",
  "date_requested": "2022-07-15",
  "date_used":      "2022-07-15",
  "with_uncertainty": true,
  "units": {"temperature": "degC", "uncertainty": "degC (1 sigma)",
            "anomaly": "degC vs monthly climatology", "depth": "m"},
  "grid":  {"n_lat": 100, "n_lon": 240, "depths_m": [0, 5, ..., 1000]},
  "baseline_provenance": {...},
  "extraction": {"kind": "depth_slice", "depth_m": 100.0, "requested": 100.0,
                 "snapped_by_m": 0.0, "field": "temperature"}
}
```

A bare array handed to a plotting function does not know its own date, source or units. This one
does.

---

## 5. ⚠ Do not present `uncertainty` as confidence

`uncertainty` is the raw MC-dropout spread and it is **not calibrated**.

[VERIFIED 2026-08-26, `docs/DECISIONS.md` D-016 UPDATE] it under-states the real error at **every**
reportable depth by **1.6× to 3.5×**, worst in the **mixed layer (20–50 m)**, best at 500–1000 m.
Measured by `scripts/phase2/measure_mc_calibration.py` as `RMSE / RMS(σ)`, aggregated per depth
over the 879 Argo profiles then divided.

Quote the measured per-depth error from `artifacts/argo_error_by_depth.json` (surfaced by F8,
`phase2.validation.lab`) as the uncertainty. Use `cube.uncertainty` for *relative* shading only,
never as an error bar.

---

## 6. Cost

| call | time |
|---|---|
| `reconstruct(..., with_uncertainty=True)` | ~6.6 s (30 MC-dropout passes over ~11.8k cells) |
| `reconstruct(..., with_uncertainty=False)` | ~0.1 s |

Cache the cube, not the slices. In Streamlit use `@st.cache_data` on a function with **no
underscore-prefixed arguments** — an underscore silently excludes that argument from the cache key
and pins the first result forever.

---

## 7. Not in F2a

`OceanCube` holds **one timestamp**. There is no multi-time cube, and no time axis anywhere in the
API — monthly sampling cannot support tracking or persistence (F6 tracking and F7 are closed for
the same reason).

F2b (Plotly volume / isosurface page) is not started. When built it must degrade to a 2-D
depth-slice view rather than showing a broken page — and note that **plotly is not installed in
this environment** even though it is in `requirements.txt`; `app/panels/_viz.py` records why the
frozen app deliberately uses altair instead.
