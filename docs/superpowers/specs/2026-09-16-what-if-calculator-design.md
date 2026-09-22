# What-If Calculator — design spec

- **Date:** 2026-09-16
- **Owner:** Unit B (Darshan)
- **Status:** approved design → next: implementation plan
- **Source:** feature request "What-If Calculator (separate section)" + `CLAUDE.md`

## 1. What this is

A **backend-only** sandbox that lets a user take a real query point, manually override the
numbers that feed our existing formulas/model, and instantly see how the outputs change
("what if SST were 10.2 instead of 10.0?"). It reuses the real functions as-is; it invents no
new science and retrains nothing.

Every what-if number is **hypothetical** — it comes from user-edited inputs, not measured ocean.
The engine labels it as such. This is allowed under `CLAUDE.md`'s real-data-only rule, which
forbids passing *fabricated* numbers off as real results — not an explicitly-labelled sandbox.

## 2. Scope decisions (settled)

- **Full registry**: all three formula families are exposed from day one
  (model profile, anomaly extremes, observation priority).
- **No UI.** UI/UX is Arjhun's job, on the existing port-8500 instrument (`app/ui/main.py`).
  This deliverable is a **Streamlit-free, importable module** with a clear output contract that a
  future `app/ui/features/whatif.py` can consume. We do **not** build a page, add a port, or edit
  `launch.json`.

### Goals
1. Reuse the real formulas/model with different inputs — no re-implemented math.
2. A data-driven **formula registry** so new tunable formulas register once and any UI picks them up.
3. A tiny, framework-free **engine API** returning baseline vs what-if vs delta, all labelled hypothetical.
4. Tested against real data per `CLAUDE.md`'s engineering loop.

### Non-goals
- No Streamlit page, no UI/UX, no `launch.json` / port changes.
- No new science, no retraining, no model/architecture change.
- No edits to any other unit's files (see constraints).

## 3. Constraints

- **Do not edit:** `products/anomaly.py`, `products/observation_priority.py`,
  `inference/predict.py`, any `models/`/`train/` file, `app/ui/*`, `app/panels/*`, `.claude/launch.json`.
  (Import and call them only.)
- **No new heavy dependencies** — numpy + the code already present.
- **Contract-first:** import constants from `src/oceanembed/config.py`; never hardcode
  `LAT/LON/DEPTHS/FEATURES`.

## 4. The two scopes (core insight)

The tunable inputs fall into two natural scopes:

| Input(s) | Drives | Scope | Cost |
|---|---|---|---|
| `sst, sss, ssh, u, v` | the **model profile** at the picked point | **point** | fast (2×30 MC passes) |
| `k` | `flag_extremes` / `standardized_anomaly` | **grid** | one cached basin grid |
| `w_anomaly, w_uncertainty, w_sparsity`, `robust` | `observation_priority` | **grid** | reuses same cached grid |

Why grid, not point: `standardized_anomaly()` normalizes by the basin's **spatial** spread and
`observation_priority()` ranks **across the basin** — neither is defined for a lone cell. Also
`anomaly()` *asserts* a full-grid `(100,240,15)` shape and will (correctly) reject a single point.

So:
- **Point-scope profile** reports its anomaly the honest way `reconstruct()` already uses:
  `profile_mean − climatology_profile` (a plain per-point difference — it does **not** call
  `anomaly()` at a point, which would assert-fail).
- The real `anomaly()` / `standardized_anomaly()` / `flag_extremes()` / `observation_priority()`
  functions are called **as-is at grid scope**, where their shape contract holds and `k` is meaningful.
  At the picked point we then read that cell out of the grid result for the side-by-side.

The baseline grid is produced **once** via the public `predict.reconstruct_grid(date)` and memoized;
the grid formulas are cheap pure-numpy, so re-running them with new `k`/`weights`/`robust` is instant.

## 5. Package layout (new files only)

```
src/oceanembed/whatif/
  __init__.py     # re-exports the public API
  registry.py     # data: InputSpec / FormulaSpec dataclasses + REGISTRY list + get()/list_formulas()
  compute.py      # WhatIfContext, baseline builders, cached baseline grid, the 3 formula handlers
  engine.py       # public API: baseline(), apply(), list_formulas(); validation + delta
tests/test_whatif.py
docs/HANDOFF.md   # append an API note for Arjhun (allowed: appended by everyone)
```

Dependency direction (no cycles): `engine → {registry, compute}`, `registry → compute`,
`compute → inference.predict + products.* + config`. `compute` keeps `torch`/model imports lazy
(inside functions), exactly as `predict.py` does, so importing the package stays cheap.

## 6. The registry (data, not a framework)

The requested shape `{id, label, function, inputs, outputs}` plus one honest field, `scope`.

```python
@dataclass(frozen=True)
class InputSpec:
    name: str            # e.g. "sst", "k", "w_anomaly", "robust"
    label: str
    kind: str            # "float" | "bool"  -> a generic UI renders from this alone
    default: float | bool | None  # None for surface vars == "use the real baseline value"
    min: float | None = None      # advisory UI range only (see §8) — engine does NOT hard-clamp
    max: float | None = None
    unit: str = ""

@dataclass(frozen=True)
class FormulaSpec:
    id: str
    label: str
    scope: str           # "point" | "grid"
    inputs: tuple[InputSpec, ...]
    function: Callable    # handler(ctx, inputs_dict) -> output_dict   (from compute.py)
    outputs: str          # human description of the output dict keys
```

Registered entries:

1. **`subsurface_profile`** (scope `point`)
   inputs: `sst, sss, ssh, u, v` (kind float, default `None` → real baseline value, `unit` set,
   advisory min/max per variable).
   outputs: `depths[15], profile_mean[15], profile_std[15], point_anomaly[15]|None, surface_used{5}`.

2. **`anomaly_extremes`** (scope `grid`)
   inputs: `k` (float, default `anomaly.DEFAULT_K` = 2.0, advisory min 0.5 / max 5).
   outputs: point `standardized_anomaly[15]` + `is_extreme[15]`; basin `n_extreme_by_depth[15]`,
   `n_ocean_by_depth[15]`; plus the `flag_extremes` / `standardized_anomaly` grids for a UI map.
   Note: `standardized_anomaly` does **not** depend on `k` — it is context, so its baseline/what-if
   delta is legitimately 0; only `is_extreme` and the basin counts move with `k`.

3. **`observation_priority`** (scope `grid`)
   inputs: `w_anomaly, w_uncertainty, w_sparsity` (float, default 1.0 each, from `DEFAULT_WEIGHTS`),
   `robust` (bool, default True). `weights` is flattened to 3 named floats so a generic UI needs
   no special "vector" widget; the handler repacks them into the tuple the function expects.
   outputs: point `priority` value; basin `max/mean/valid_cells`; plus the `priority` grid for a UI map.

**Extensibility:** adding a new tunable formula later = write a handler in `compute.py` (or the
owning unit's module) and append one `FormulaSpec`. No engine or UI structural change.

## 7. Engine API (Streamlit-free)

```python
def list_formulas() -> list[FormulaSpec]: ...

def baseline(lat: float, lon: float, date, source: str = "satellite") -> WhatIfContext:
    """Snap to grid, set source, read the real sst/sss/ssh/u/v and the real point profile.
    Holds lazy access to the cached baseline grid. is_land flagged, never faked."""

def apply(formula_id: str, overrides: dict, ctx: WhatIfContext) -> dict:
    """Return {formula, scope, inputs:{baseline, whatif}, baseline:{...}, whatif:{...},
              delta:{...}, hypothetical: True, notes:[...]}."""
```

**How `apply` stays honest:** it resolves two input sets from the same spec — `baseline` (real
values / spec defaults) and `whatif` (baseline with the user's overrides applied) — then calls the
**same handler** for both and diffs. Identical code path, only the inputs differ. With empty
overrides, `whatif == baseline` exactly (an identity test in §9).

**Reuse map** (imports, never edits):
- point profile: `P._model()` → `torch.manual_seed(config.SEED)` (model loaded *before* seeding,
  mirroring `reconstruct()`), `Xraw = P._features_at(i,j,t)[None,:]`, override `Xraw[0,0:5]`,
  `mc_dropout_predict(model, Xraw)`; blank below-seafloor depths via `P._valid_mask()`.
- grid: `P.reconstruct_grid(date)` (memoized per `(date, source)`), `P._climatology()`,
  `P._argo_sparsity()`, reusing predict.py's own `a2d`/`u2d` + deep-enough masking so the baseline
  matches the real priority panel.
- lookups: `grids.nearest_lat_index/lon_index`, `P._nearest_time_index` — as the request invited.

## 8. Error handling & edge cases

- **Land / no-data point:** `baseline()` sets `is_land=True`; `apply("subsurface_profile", …)`
  returns a clear "not available on land" result — no fabricated profile.
- **Below sea floor:** NaN-blanked via `_valid_mask`, identical to `reconstruct()`.
- **Missing artifacts** (grids/model/climatology): let predict.py's own `FileNotFoundError`
  (with its rebuild hint) propagate — do not swallow.
- **Degenerate priority grid** (all factors flat → NaN): `observation_priority()` already returns
  NaN and warns; the engine passes it through, labelled, rather than inventing a value.
- **Overrides validation:** unknown input key → `ValueError`; wrong `kind` → `ValueError`.
  `min`/`max` are **advisory UI ranges only** — the engine accepts any finite value of the right
  kind, so genuinely extreme what-ifs ("SST = 45°C") are allowed in the sandbox.
- **Source:** `baseline()` calls `P.set_source(source)`; the grid cache is keyed on `(date, source)`,
  matching how the app already switches sources.

## 9. Testing (`tests/test_whatif.py`)

Registry:
- every `FormulaSpec.inputs` entry has a valid `kind`, and float inputs carry advisory min ≤ max.
- `list_formulas()` returns the three expected ids.

Engine (real data; skip cleanly if artifacts absent):
- **identity:** `apply` with empty overrides ⇒ `delta` all ≈ 0 (baseline == whatif).
- **profile sensitivity:** overriding `sst` by +0.2 shifts `profile_mean` (non-zero delta,
  finite, right shape 15); the baseline profile matches `P.reconstruct()` at the same point.
- **k sensitivity:** raising `k` never *increases* the basin extreme count (monotone) and toggles
  the point's `is_extreme` sensibly.
- **weights sensitivity:** zeroing two of three weights changes the point `priority` value.
- **land guard:** a known land cell returns `is_land` and no fabricated numbers.

## 10. Integration note for Arjhun (goes in HANDOFF.md)

```python
from oceanembed.whatif import baseline, apply, list_formulas
ctx = baseline(lat, lon, date, source="satellite")
for spec in list_formulas():           # build inputs generically from spec.inputs (name/kind/default/min/max)
    ...
res = apply("subsurface_profile", {"sst": 10.2}, ctx)   # res["baseline"], res["whatif"], res["delta"]
```
Everything returned is plain dict / list / numpy; grid formulas also return their full grid under
`whatif["grid"]` for map rendering. All what-if figures carry `hypothetical: True` — the UI must
label them "hypothetical / not measured".

## 11. Out of scope
Visual design/layout (Arjhun); editing training data / retraining / architecture; any formula not
already implemented in the repo.
