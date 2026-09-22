# What-If Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit-free backend that lets a user override the inputs to our real model/formulas and see baseline-vs-what-if-vs-delta, exposed through a data-driven formula registry.

**Architecture:** A new `src/oceanembed/whatif/` package. `registry.py` holds the formulas as data + pure input resolution. `compute.py` holds the context builder, a cached baseline grid, and three formula handlers that *import and call* the existing model/anomaly/priority functions (never re-implement them). `engine.py` is the public API: `baseline()` reads the real numbers, `apply()` runs a handler twice (baseline inputs vs overridden inputs) and diffs. No UI — the port-8500 instrument consumes this later.

**Tech Stack:** Python 3.12, numpy, pandas, torch (already present, imported lazily), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-16-what-if-calculator-design.md` (read it alongside this plan).

## Global Constraints

- **Do NOT edit** any of: `src/oceanembed/products/anomaly.py`, `src/oceanembed/products/observation_priority.py`, `src/oceanembed/inference/predict.py`, `src/oceanembed/inference/uncertainty.py`, anything under `src/oceanembed/models/` or `train/`, anything under `app/ui/` or `app/panels/`, and `.claude/launch.json`. Import and call them only.
- **No UI.** No Streamlit import anywhere in `src/oceanembed/whatif/`. No new port, no `launch.json` entry.
- **No new dependencies.** Only numpy/pandas/torch already in the repo.
- **Import constants from `src/oceanembed/config.py`** — never hardcode `LAT/LON/DEPTHS/FEATURES/N_*/SEED`.
- **Lazy heavy imports:** in `compute.py`, import `torch`, `mc_dropout_predict`, and the product functions *inside* the functions that use them (mirroring `predict.py`), so importing the package stays cheap.
- **Every what-if result carries `"hypothetical": True`** and a note that the numbers are user-edited, not measured (real-data-only rule).
- **The working tree contains unrelated in-progress work** (tscast/inversion files, `launch.json`, a scripts file). **Never `git add -A` / `git add .`** In every commit step, `git add` only the exact whatif files + test/doc paths listed.
- **Run tests with** `python -m pytest` from the repo root (`pyproject.toml` sets `pythonpath=["src"]`). Real-data tests are guarded by a skip if artifacts are absent; on this machine (model + grids present) they actually run — that is the required real-data smoke test.

---

### Task 1: Registry — formula dataclasses + pure input resolution

Pure Python, no artifacts, no heavy imports. This is the extensibility contract and the input-validation logic, fully unit-testable on its own.

**Files:**
- Create: `src/oceanembed/whatif/__init__.py` (empty placeholder for now — real exports arrive in Task 6)
- Create: `src/oceanembed/whatif/registry.py`
- Test: `tests/test_whatif.py`

**Interfaces:**
- Produces:
  - `InputSpec(name:str, label:str, kind:str, default, min=None, max=None, unit:str="")` — frozen dataclass. `kind` ∈ {"float","bool"}. `default=None` means "fill from the baseline value".
  - `FormulaSpec(id:str, label:str, scope:str, inputs:tuple[InputSpec,...], function:Callable, outputs:str)` — frozen dataclass. `scope` ∈ {"point","grid"}.
  - `REGISTRY: list[FormulaSpec]` (starts empty; later tasks append).
  - `register(spec: FormulaSpec) -> None`
  - `get(formula_id: str) -> FormulaSpec` (raises `KeyError` if absent)
  - `list_formulas() -> list[FormulaSpec]`
  - `resolve_inputs(spec, overrides: dict, baseline_values: dict) -> dict` — validates and returns the concrete input values.

- [ ] **Step 1: Create the empty package marker**

Create `src/oceanembed/whatif/__init__.py` with only a module docstring:

```python
"""What-If Calculator: override the inputs to the real model/formulas and see the effect.

Backend only (no Streamlit). Public API is finalised in engine.py; see
docs/superpowers/plans/2026-09-16-what-if-calculator.md.
"""
```

- [ ] **Step 2: Write the failing tests for the registry**

Create `tests/test_whatif.py`:

```python
"""Tests for the What-If Calculator backend (src/oceanembed/whatif)."""
from __future__ import annotations

import pytest

from oceanembed.whatif import registry as R


def _demo_spec():
    return R.FormulaSpec(
        id="demo", label="Demo", scope="point",
        inputs=(
            R.InputSpec("sst", "SST", "float", None, -2.0, 40.0, "degC"),
            R.InputSpec("k", "k", "float", 2.0, 0.5, 5.0, "sigma"),
            R.InputSpec("robust", "Robust", "bool", True),
        ),
        function=lambda ctx, inputs: inputs,
        outputs="echo",
    )


def test_resolve_fills_defaults_and_baseline():
    got = R.resolve_inputs(_demo_spec(), {}, {"sst": 10.0})
    assert got == {"sst": 10.0, "k": 2.0, "robust": True}


def test_resolve_applies_override():
    got = R.resolve_inputs(_demo_spec(), {"sst": 10.2, "k": 3.0}, {"sst": 10.0})
    assert got["sst"] == 10.2 and got["k"] == 3.0 and got["robust"] is True


def test_unknown_key_raises():
    with pytest.raises(ValueError):
        R.resolve_inputs(_demo_spec(), {"nope": 1}, {"sst": 10.0})


def test_wrong_kind_raises():
    with pytest.raises(ValueError):        # a float where a bool is expected
        R.resolve_inputs(_demo_spec(), {"robust": 1.0}, {"sst": 10.0})
    with pytest.raises(ValueError):        # a bool where a float is expected
        R.resolve_inputs(_demo_spec(), {"sst": True}, {"sst": 10.0})


def test_missing_value_raises():
    with pytest.raises(ValueError):        # sst has default None and no baseline value
        R.resolve_inputs(_demo_spec(), {}, {})


def test_get_missing_formula_raises():
    with pytest.raises(KeyError):
        R.get("does-not-exist")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_whatif.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` (registry members don't exist yet).

- [ ] **Step 4: Implement `registry.py`**

Create `src/oceanembed/whatif/registry.py`:

```python
"""The What-If formula registry: formulas as data, plus pure input resolution.

Each FormulaSpec describes one tunable formula generically, so any UI can render
its inputs from `kind`/`default`/`min`/`max` alone and a new formula is added by
appending one entry. This module is pure (numpy/torch never imported here).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class InputSpec:
    name: str
    label: str
    kind: str                       # "float" | "bool"
    default: object = None          # None for surface vars == "use the real baseline value"
    min: float | None = None        # advisory UI range only; the engine does NOT clamp
    max: float | None = None
    unit: str = ""


@dataclass(frozen=True)
class FormulaSpec:
    id: str
    label: str
    scope: str                      # "point" | "grid"
    inputs: tuple[InputSpec, ...]
    function: Callable              # handler(ctx, inputs: dict) -> dict
    outputs: str


REGISTRY: list[FormulaSpec] = []


def register(spec: FormulaSpec) -> None:
    if any(s.id == spec.id for s in REGISTRY):
        raise ValueError(f"formula id {spec.id!r} already registered")
    REGISTRY.append(spec)


def get(formula_id: str) -> FormulaSpec:
    for s in REGISTRY:
        if s.id == formula_id:
            return s
    raise KeyError(f"no formula {formula_id!r}; registered: {[s.id for s in REGISTRY]}")


def list_formulas() -> list[FormulaSpec]:
    return list(REGISTRY)


def _check_kind(inp: InputSpec, val: object) -> None:
    if inp.kind == "bool":
        if not isinstance(val, bool):
            raise ValueError(f"input {inp.name!r} expects a bool, got {type(val).__name__}")
    elif inp.kind == "float":
        # bool is a subclass of int in Python -- reject it explicitly for a numeric field.
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"input {inp.name!r} expects a number, got {type(val).__name__}")
        if not math.isfinite(float(val)):
            raise ValueError(f"input {inp.name!r} must be finite, got {val}")
    else:
        raise ValueError(f"unknown kind {inp.kind!r} for input {inp.name!r}")


def resolve_inputs(spec: FormulaSpec, overrides: dict, baseline_values: dict) -> dict:
    """Concrete value for every declared input.

    Precedence per input: user override -> static default -> baseline value.
    `min`/`max` are advisory (UI slider hints); any finite value of the right
    kind is accepted so genuinely extreme what-ifs are allowed.
    """
    known = {inp.name for inp in spec.inputs}
    unknown = set(overrides) - known
    if unknown:
        raise ValueError(f"unknown input(s) for {spec.id}: {sorted(unknown)}; valid: {sorted(known)}")

    out: dict = {}
    for inp in spec.inputs:
        if inp.name in overrides:
            val = overrides[inp.name]
            _check_kind(inp, val)
        elif inp.default is not None:
            val = inp.default
        elif inp.name in baseline_values:
            val = baseline_values[inp.name]
        else:
            raise ValueError(
                f"no value for input {inp.name!r} of {spec.id} (no override, no default, no baseline)")
        out[inp.name] = val
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_whatif.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/__init__.py src/oceanembed/whatif/registry.py tests/test_whatif.py
git commit -m "What-If: formula registry dataclasses + pure input resolution"
```

---

### Task 2: Context builder + cached baseline grid + `engine.baseline()`

Reads the *real* baseline for a point (reusing `predict.reconstruct`) and prepares the cached basin grid the grid-formulas need. Real-data smoke test.

**Files:**
- Create: `src/oceanembed/whatif/compute.py`
- Create: `src/oceanembed/whatif/engine.py`
- Test: `tests/test_whatif.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks (Task 1 is independent).
- Produces:
  - `compute.WhatIfContext` — dataclass with fields `lat, lon, date, source, i, j, t, month, is_land, surface(dict|None), profile_mean, profile_std, climatology_profile` and method `grid() -> dict`.
  - `compute.build_context(lat, lon, date, source) -> WhatIfContext`
  - `compute._baseline_grid(date, source) -> dict` with keys `temp, uncertainty, anomaly, priority, land_mask, clim, a2d, u2d, sparsity` (lru-cached).
  - `engine.baseline(lat, lon, date, source="satellite") -> WhatIfContext`
  - `engine.list_formulas` (re-export of `registry.list_formulas`)

- [ ] **Step 1: Write the failing real-data tests**

Append to `tests/test_whatif.py`:

```python
import os
import numpy as np
from oceanembed import config
from oceanembed.whatif import compute, engine


def _artifacts_ready() -> bool:
    from oceanembed.inference import predict as P
    model = os.path.exists(config.art("mlp_model.pt"))
    grids = P.source_available("satellite") or P.source_available("glorys")
    return model and grids


def _source() -> str:
    from oceanembed.inference import predict as P
    return "satellite" if P.source_available("satellite") else "glorys"


def _last_date():
    from oceanembed.inference import predict as P
    P.set_source(_source())
    return P.available_dates()[-1]


needs_data = pytest.mark.skipif(not _artifacts_ready(), reason="needs built artifacts (model + grids)")

# An ocean point (central Arabian Sea) and a land point (central India) inside the bbox.
OCEAN = (15.0, 65.0)
LAND = (23.0, 80.0)


@needs_data
def test_baseline_reads_real_surface_and_profile():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    assert ctx.is_land is False
    assert set(ctx.surface) == {"sst", "sss", "ssh", "u", "v"}
    assert ctx.profile_mean is not None and len(ctx.profile_mean) == config.N_DEPTHS
    assert 1 <= ctx.month <= 12


@needs_data
def test_baseline_land_guard():
    ctx = engine.baseline(*LAND, _last_date(), _source())
    assert ctx.is_land is True
    assert ctx.surface is None


@needs_data
def test_baseline_grid_shapes():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    g = ctx.grid()
    assert g["temp"].shape == (config.N_LAT, config.N_LON, config.N_DEPTHS)
    assert g["a2d"].shape == (config.N_LAT, config.N_LON)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_whatif.py -k baseline -v`
Expected: FAIL — `AttributeError: module 'oceanembed.whatif.engine' has no attribute 'baseline'` (or import error for `compute`).

- [ ] **Step 3: Implement `compute.py`**

Create `src/oceanembed/whatif/compute.py`:

```python
"""Baseline extraction + the cached basin grid + the formula handlers.

Everything here IMPORTS and CALLS the real model/anomaly/priority code with
different inputs; it never re-implements their maths. torch and the product
functions are imported lazily inside the handlers so importing this module is cheap.
"""
from __future__ import annotations

import functools
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from oceanembed import config
from oceanembed.inference import predict as P
from oceanembed.utils import grids


@dataclass
class WhatIfContext:
    lat: float
    lon: float
    date: object
    source: str
    i: int
    j: int
    t: int
    month: int
    is_land: bool
    surface: dict | None
    profile_mean: object | None          # np.ndarray (15,) or None on land
    profile_std: object | None
    climatology_profile: object | None   # np.ndarray (15,) or None

    def grid(self) -> dict:
        return _baseline_grid(self.date, self.source)


def build_context(lat: float, lon: float, date, source: str) -> WhatIfContext:
    P.set_source(source)
    rec = P.reconstruct(lat, lon, date)         # the REAL baseline for this point
    i = grids.nearest_lat_index(lat)
    j = grids.nearest_lon_index(lon)
    t = P._nearest_time_index(rec["date"])
    g = P._grids()
    month = int(pd.Timestamp(g["times"][t]).month)
    return WhatIfContext(
        lat=float(config.LAT[i]), lon=float(config.LON[j]), date=rec["date"], source=source,
        i=int(i), j=int(j), t=int(t), month=month,
        is_land=bool(rec["is_land"]),
        surface=rec.get("surface"),
        profile_mean=rec.get("profile_mean"),
        profile_std=rec.get("profile_std"),
        climatology_profile=rec.get("climatology"),
    )


def _nanmean_axis2(vol, absolute: bool) -> np.ndarray:
    with warnings.catch_warnings():                 # all-NaN land columns are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        a = np.abs(vol) if absolute else vol
        return np.nanmean(a, axis=2)


@functools.lru_cache(maxsize=8)
def _baseline_grid(date, source) -> dict:
    """The real basin reconstruction + the derived 2-D factors the grid formulas read.

    Mirrors predict.reconstruct_grid()'s own a2d/u2d/sparsity + deep-enough masking so
    the what-if baseline matches the real priority panel. Cached per (date, source).
    """
    P.set_source(source)
    g = P.reconstruct_grid(date)                    # temp, uncertainty, anomaly, priority, land_mask
    clim = P._climatology()

    shape2d = (config.N_LAT, config.N_LON)
    a2d = _nanmean_axis2(g["anomaly"], absolute=True) if g["anomaly"] is not None \
        else np.full(shape2d, np.nan, dtype="float32")
    u2d = _nanmean_axis2(g["uncertainty"], absolute=False) if g["uncertainty"] is not None \
        else np.full(shape2d, np.nan, dtype="float32")
    sparsity = P._argo_sparsity()

    vm = P._valid_mask()
    if vm is not None:                              # rank only cells with water at every depth
        deep = vm[..., -1]
        a2d = np.where(deep, a2d, np.nan)
        u2d = np.where(deep, u2d, np.nan)
        sparsity = np.where(deep, sparsity, np.nan)

    return {"temp": g["temp"], "uncertainty": g["uncertainty"], "anomaly": g["anomaly"],
            "priority": g["priority"], "land_mask": g["land_mask"], "clim": clim,
            "a2d": a2d, "u2d": u2d, "sparsity": sparsity}
```

- [ ] **Step 4: Implement `engine.py` (baseline + list_formulas only for now)**

Create `src/oceanembed/whatif/engine.py`:

```python
"""Public API for the What-If Calculator. Streamlit-free; returns plain dict/list/numpy."""
from __future__ import annotations

from oceanembed.whatif import compute
from oceanembed.whatif.registry import list_formulas   # re-export


def baseline(lat: float, lon: float, date, source: str = "satellite") -> compute.WhatIfContext:
    """Snap to grid, set the surface source, read the real sst/sss/ssh/u/v + point profile."""
    return compute.build_context(lat, lon, date, source)
```

- [ ] **Step 5: Run the baseline tests to verify they pass**

Run: `python -m pytest tests/test_whatif.py -k baseline -v`
Expected: PASS (3 tests) on this machine. Elsewhere: SKIPPED.

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/compute.py src/oceanembed/whatif/engine.py tests/test_whatif.py
git commit -m "What-If: context builder + cached baseline grid + engine.baseline()"
```

---

### Task 3: `subsurface_profile` handler (point scope) + register it

The star feature: override the 5 surface inputs and recompute the model profile at the point.

**Files:**
- Modify: `src/oceanembed/whatif/compute.py` (append `compute_profile`)
- Modify: `src/oceanembed/whatif/registry.py` (append the FormulaSpec)
- Test: `tests/test_whatif.py` (append)

**Interfaces:**
- Consumes: `WhatIfContext` (Task 2); `register`, `FormulaSpec`, `InputSpec` (Task 1).
- Produces:
  - `compute.compute_profile(ctx, inputs) -> dict` with keys `available, depths, profile_mean, profile_std, point_anomaly, surface_used`.
  - Registered `FormulaSpec` id `"subsurface_profile"`, inputs `sst,sss,ssh,u,v` (all `default=None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_whatif.py`:

```python
SURF = ("sst", "sss", "ssh", "u", "v")


@needs_data
def test_profile_handler_is_deterministic():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    base_inputs = {k: ctx.surface[k] for k in SURF}
    a = compute.compute_profile(ctx, base_inputs)
    b = compute.compute_profile(ctx, base_inputs)
    assert a["available"] is True
    np.testing.assert_allclose(a["profile_mean"], b["profile_mean"], atol=1e-6)
    assert len(a["profile_mean"]) == config.N_DEPTHS


@needs_data
def test_profile_baseline_matches_reconstruct():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    out = compute.compute_profile(ctx, {k: ctx.surface[k] for k in SURF})
    got = np.nan_to_num(np.array(out["profile_mean"], dtype="float32"))
    base = np.nan_to_num(np.asarray(ctx.profile_mean, dtype="float32"))
    np.testing.assert_allclose(got, base, atol=1e-2)   # same inputs+seed reproduce reconstruct


@needs_data
def test_profile_responds_to_sst_override():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    base = compute.compute_profile(ctx, {k: ctx.surface[k] for k in SURF})
    warm = compute.compute_profile(ctx, {**{k: ctx.surface[k] for k in SURF},
                                         "sst": ctx.surface["sst"] + 0.5})
    d = np.array(warm["profile_mean"]) - np.array(base["profile_mean"])
    assert np.nanmax(np.abs(d)) > 0.0


@needs_data
def test_profile_on_land_not_available():
    ctx = engine.baseline(*LAND, _last_date(), _source())
    out = compute.compute_profile(ctx, {k: 10.0 for k in SURF})
    assert out["available"] is False


def test_profile_registered():
    from oceanembed.whatif import registry as R
    spec = R.get("subsurface_profile")
    assert spec.scope == "point"
    assert tuple(i.name for i in spec.inputs) == SURF
    assert all(i.default is None for i in spec.inputs)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_whatif.py -k profile -v`
Expected: FAIL — `compute` has no `compute_profile`; `R.get("subsurface_profile")` raises `KeyError`.

- [ ] **Step 3: Append `compute_profile` to `compute.py`**

```python
def compute_profile(ctx: "WhatIfContext", inputs: dict) -> dict:
    """Rebuild the 11-feature raw vector, override the 5 surface entries, run MC-dropout.

    Uses predict.py's own lookups so the layout is identical to _features_at; only the
    first 5 entries change. Mirrors reconstruct()'s seed order and below-seafloor blanking.
    """
    import torch as _t
    from oceanembed.inference.uncertainty import mc_dropout_predict

    if ctx.is_land or ctx.surface is None:
        return {"available": False, "reason": "point is land / no data",
                "depths": list(config.DEPTHS)}

    model = P._model()                      # load BEFORE seeding (see reconstruct() for why)
    _t.manual_seed(config.SEED)

    xraw = P._features_at(ctx.i, ctx.j, ctx.t)[None, :].copy()
    for idx, name in enumerate(("sst", "sss", "ssh", "u", "v")):
        xraw[0, idx] = float(inputs[name])

    mean, std = mc_dropout_predict(model, xraw)
    mean, std = mean[0], std[0]

    vm = P._valid_mask()
    if vm is not None:
        below = ~vm[ctx.i, ctx.j]
        mean = np.where(below, np.nan, mean)
        std = np.where(below, np.nan, std)

    clim = ctx.climatology_profile
    point_anom = (mean - clim).astype("float32") if clim is not None else None

    return {
        "available": True,
        "depths": list(config.DEPTHS),
        "profile_mean": [float(x) for x in mean],
        "profile_std": [float(x) for x in std],
        "point_anomaly": None if point_anom is None else [float(x) for x in point_anom],
        "surface_used": {k: float(inputs[k]) for k in ("sst", "sss", "ssh", "u", "v")},
    }
```

- [ ] **Step 4: Register the formula in `registry.py`**

Append to the end of `src/oceanembed/whatif/registry.py`:

```python
# --------------------------------------------------------------------------- registered formulas
# Imported at the bottom so the dataclasses/helpers above are fully defined first.
from oceanembed.whatif import compute as _compute   # noqa: E402

_SURFACE_INPUTS = (
    InputSpec("sst", "Sea-surface temperature", "float", None, -2.0, 40.0, "degC"),
    InputSpec("sss", "Sea-surface salinity", "float", None, 0.0, 45.0, "psu"),
    InputSpec("ssh", "Sea-surface height", "float", None, -2.0, 2.0, "m"),
    InputSpec("u", "Surface current u", "float", None, -3.0, 3.0, "m/s"),
    InputSpec("v", "Surface current v", "float", None, -3.0, 3.0, "m/s"),
)

register(FormulaSpec(
    id="subsurface_profile",
    label="Subsurface temperature profile",
    scope="point",
    inputs=_SURFACE_INPUTS,
    function=_compute.compute_profile,
    outputs="available, depths[15], profile_mean[15], profile_std[15], point_anomaly[15]|None, surface_used",
))
```

- [ ] **Step 5: Run the profile tests to verify they pass**

Run: `python -m pytest tests/test_whatif.py -k profile -v`
Expected: PASS (`test_profile_registered` runs everywhere; the `needs_data` ones PASS here, SKIP elsewhere).
Note: if `test_profile_baseline_matches_reconstruct` fails only by a hair on GPU, widen its `atol` to `5e-2` — MC-dropout is seeded so it should be tight, but device math can differ slightly.

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/compute.py src/oceanembed/whatif/registry.py tests/test_whatif.py
git commit -m "What-If: subsurface_profile handler (surface overrides -> model profile)"
```

---

### Task 4: `anomaly_extremes` handler (grid scope) + register it

Exposes `k` for `flag_extremes`/`standardized_anomaly`, called as-is on the cached basin grid.

**Files:**
- Modify: `src/oceanembed/whatif/compute.py` (append `compute_anomaly_extremes`)
- Modify: `src/oceanembed/whatif/registry.py` (append the FormulaSpec)
- Test: `tests/test_whatif.py` (append)

**Interfaces:**
- Consumes: `WhatIfContext.grid()` (Task 2); `anomaly.DEFAULT_K`, `standardized_anomaly`, `flag_extremes` (existing, imported).
- Produces:
  - `compute.compute_anomaly_extremes(ctx, inputs) -> dict` keys `available, k, depths, point_standardized_anomaly, point_is_extreme, n_extreme_by_depth, n_ocean_by_depth, grid_standardized_anomaly, grid_is_extreme`.
  - Registered `FormulaSpec` id `"anomaly_extremes"`, input `k` (default `anomaly.DEFAULT_K`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_whatif.py`:

```python
@needs_data
def test_anomaly_extremes_z_is_k_independent_and_counts_monotone():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    lo = compute.compute_anomaly_extremes(ctx, {"k": 1.0})
    hi = compute.compute_anomaly_extremes(ctx, {"k": 3.0})
    if not lo["available"]:
        pytest.skip("no climatology artifact")
    np.testing.assert_allclose(lo["point_standardized_anomaly"],
                               hi["point_standardized_anomaly"], atol=1e-6)
    assert sum(hi["n_extreme_by_depth"]) <= sum(lo["n_extreme_by_depth"])
    assert len(lo["point_is_extreme"]) == config.N_DEPTHS


def test_anomaly_extremes_registered():
    from oceanembed.whatif import registry as R
    from oceanembed.products.anomaly import DEFAULT_K
    spec = R.get("anomaly_extremes")
    assert spec.scope == "grid"
    (k_in,) = spec.inputs
    assert k_in.name == "k" and k_in.kind == "float" and k_in.default == DEFAULT_K
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_whatif.py -k anomaly_extremes -v`
Expected: FAIL — no `compute_anomaly_extremes`; `R.get("anomaly_extremes")` raises `KeyError`.

- [ ] **Step 3: Append `compute_anomaly_extremes` to `compute.py`**

```python
def compute_anomaly_extremes(ctx: "WhatIfContext", inputs: dict) -> dict:
    """standardized_anomaly (k-independent context) + flag_extremes at threshold k, basin-wide.

    Called as-is on the cached basin grid; the picked point is read out for the side-by-side.
    """
    from oceanembed.products.anomaly import standardized_anomaly, flag_extremes

    g = ctx.grid()
    clim = g["clim"]
    if clim is None:
        return {"available": False, "reason": "climatology.npy missing",
                "depths": list(config.DEPTHS)}

    k = float(inputs["k"])
    temp = g["temp"]
    z = standardized_anomaly(temp, clim, ctx.month)          # (100,240,15)
    ext = flag_extremes(temp, clim, ctx.month, k=k)          # (100,240,15) bool
    ocean = np.isfinite(z)

    return {
        "available": True,
        "k": k,
        "depths": list(config.DEPTHS),
        "point_standardized_anomaly": [float(x) for x in z[ctx.i, ctx.j, :]],
        "point_is_extreme": [bool(x) for x in ext[ctx.i, ctx.j, :]],
        "n_extreme_by_depth": [int(v) for v in ext.reshape(-1, ext.shape[-1]).sum(0)],
        "n_ocean_by_depth": [int(v) for v in ocean.reshape(-1, ocean.shape[-1]).sum(0)],
        "grid_standardized_anomaly": z,
        "grid_is_extreme": ext,
    }
```

- [ ] **Step 4: Register the formula in `registry.py`**

Append after the `subsurface_profile` registration:

```python
from oceanembed.products.anomaly import DEFAULT_K as _DEFAULT_K   # noqa: E402

register(FormulaSpec(
    id="anomaly_extremes",
    label="Anomaly extremes (threshold k)",
    scope="grid",
    inputs=(InputSpec("k", "Extreme threshold", "float", _DEFAULT_K, 0.5, 5.0, "sigma"),),
    function=_compute.compute_anomaly_extremes,
    outputs=("available, k, depths[15], point_standardized_anomaly[15], point_is_extreme[15], "
             "n_extreme_by_depth[15], n_ocean_by_depth[15], grid_standardized_anomaly, grid_is_extreme"),
))
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_whatif.py -k anomaly_extremes -v`
Expected: PASS (registration test everywhere; data test here, SKIP elsewhere).

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/compute.py src/oceanembed/whatif/registry.py tests/test_whatif.py
git commit -m "What-If: anomaly_extremes handler (k threshold on basin grid)"
```

---

### Task 5: `observation_priority` handler (grid scope) + register it

Exposes `weights` (3 floats) + `robust`, calling `observation_priority` as-is on the cached grid.

**Files:**
- Modify: `src/oceanembed/whatif/compute.py` (append `compute_observation_priority`)
- Modify: `src/oceanembed/whatif/registry.py` (append the FormulaSpec)
- Test: `tests/test_whatif.py` (append)

**Interfaces:**
- Consumes: `WhatIfContext.grid()` (Task 2); `observation_priority`, `DEFAULT_WEIGHTS` (existing).
- Produces:
  - `compute.compute_observation_priority(ctx, inputs) -> dict` keys `available, weights, robust, point_priority, basin_max, basin_mean, valid_cells, grid_priority`.
  - Registered `FormulaSpec` id `"observation_priority"`, inputs `w_anomaly, w_uncertainty, w_sparsity` (default 1.0), `robust` (bool default True).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_whatif.py`:

```python
def _prio_inputs(wa, wu, ws, robust=True):
    return {"w_anomaly": wa, "w_uncertainty": wu, "w_sparsity": ws, "robust": robust}


@needs_data
def test_priority_weights_change_the_map():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    a = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 1.0, 1.0))
    b = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 0.0, 0.0))
    assert a["grid_priority"].shape == (config.N_LAT, config.N_LON)
    assert not np.allclose(np.nan_to_num(a["grid_priority"]),
                           np.nan_to_num(b["grid_priority"]))


@needs_data
def test_priority_robust_toggle_runs():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    out = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 1.0, 1.0, robust=False))
    assert out["available"] is True
    assert out["valid_cells"] >= 0


def test_priority_registered():
    from oceanembed.whatif import registry as R
    spec = R.get("observation_priority")
    assert spec.scope == "grid"
    names = tuple(i.name for i in spec.inputs)
    assert names == ("w_anomaly", "w_uncertainty", "w_sparsity", "robust")
    assert spec.inputs[-1].kind == "bool" and spec.inputs[-1].default is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_whatif.py -k priority -v`
Expected: FAIL — no `compute_observation_priority`; `R.get("observation_priority")` raises `KeyError`.

- [ ] **Step 3: Append `compute_observation_priority` to `compute.py`**

```python
def compute_observation_priority(ctx: "WhatIfContext", inputs: dict) -> dict:
    """observation_priority() on the cached basin factors, with overridden weights/robust."""
    from oceanembed.products.observation_priority import observation_priority

    g = ctx.grid()
    w = (float(inputs["w_anomaly"]), float(inputs["w_uncertainty"]), float(inputs["w_sparsity"]))
    robust = bool(inputs["robust"])

    with warnings.catch_warnings():                 # degenerate/land factors warn by design
        warnings.simplefilter("ignore", RuntimeWarning)
        prio = observation_priority(g["a2d"], g["u2d"], g["sparsity"], weights=w, robust=robust)

    pv = prio[ctx.i, ctx.j]
    finite = prio[np.isfinite(prio)]
    return {
        "available": True,
        "weights": list(w),
        "robust": robust,
        "point_priority": float(pv) if np.isfinite(pv) else None,
        "basin_max": float(finite.max()) if finite.size else None,
        "basin_mean": float(finite.mean()) if finite.size else None,
        "valid_cells": int(finite.size),
        "grid_priority": prio,
    }
```

- [ ] **Step 4: Register the formula in `registry.py`**

Append after the `anomaly_extremes` registration:

```python
from oceanembed.products.observation_priority import DEFAULT_WEIGHTS as _DW   # noqa: E402

register(FormulaSpec(
    id="observation_priority",
    label="Observation priority (weights & robust)",
    scope="grid",
    inputs=(
        InputSpec("w_anomaly", "Weight: anomaly", "float", float(_DW[0]), 0.0, 5.0),
        InputSpec("w_uncertainty", "Weight: uncertainty", "float", float(_DW[1]), 0.0, 5.0),
        InputSpec("w_sparsity", "Weight: sparsity", "float", float(_DW[2]), 0.0, 5.0),
        InputSpec("robust", "Robust scaling (1-99 pct)", "bool", True),
    ),
    function=_compute.compute_observation_priority,
    outputs="available, weights[3], robust, point_priority, basin_max, basin_mean, valid_cells, grid_priority",
))
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_whatif.py -k priority -v`
Expected: PASS (registration test everywhere; data tests here, SKIP elsewhere).

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/compute.py src/oceanembed/whatif/registry.py tests/test_whatif.py
git commit -m "What-If: observation_priority handler (weights & robust on basin grid)"
```

---

### Task 6: `engine.apply()` + delta + package exports

Ties it together: run a formula for baseline inputs and for overridden inputs, then diff. This is where the baseline-vs-what-if-vs-delta contract and the "hypothetical" label live.

**Files:**
- Modify: `src/oceanembed/whatif/engine.py` (add `apply`, `_baseline_values`, `_delta`)
- Modify: `src/oceanembed/whatif/__init__.py` (real exports)
- Test: `tests/test_whatif.py` (append)

**Interfaces:**
- Consumes: `registry.get`, `registry.resolve_inputs` (Task 1); `compute.WhatIfContext` (Task 2); all three registered handlers (Tasks 3–5).
- Produces:
  - `engine.apply(formula_id: str, overrides: dict, ctx) -> dict` with keys `formula, label, scope, hypothetical(True), note, inputs{baseline,whatif}, baseline, whatif, delta`.
  - Package exports from `oceanembed.whatif`: `baseline, apply, list_formulas, get, REGISTRY, InputSpec, FormulaSpec, WhatIfContext, resolve_inputs`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_whatif.py`:

```python
def test_list_formulas_has_the_three_ids():
    ids = {s.id for s in engine.list_formulas()}
    assert {"subsurface_profile", "anomaly_extremes", "observation_priority"} <= ids


@needs_data
def test_apply_identity_gives_zero_delta():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    res = engine.apply("subsurface_profile", {}, ctx)
    assert res["hypothetical"] is True
    assert res["formula"] == "subsurface_profile"
    assert max(abs(x) for x in res["delta"]["profile_mean"]) < 1e-3


@needs_data
def test_apply_sst_override_moves_profile_and_records_input():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    new_sst = ctx.surface["sst"] + 0.5
    res = engine.apply("subsurface_profile", {"sst": new_sst}, ctx)
    assert res["inputs"]["whatif"]["sst"] == new_sst
    assert res["inputs"]["baseline"]["sst"] == ctx.surface["sst"]
    assert max(abs(x) for x in res["delta"]["profile_mean"]) > 0.0


@needs_data
def test_apply_unknown_formula_raises():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    with pytest.raises(KeyError):
        engine.apply("nope", {}, ctx)


def test_package_exports():
    import oceanembed.whatif as W
    for name in ("baseline", "apply", "list_formulas", "get", "REGISTRY",
                 "InputSpec", "FormulaSpec", "WhatIfContext", "resolve_inputs"):
        assert hasattr(W, name), name
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_whatif.py -k "apply or exports or three_ids" -v`
Expected: FAIL — `engine.apply` doesn't exist; package exports missing.

- [ ] **Step 3: Add `apply` + helpers to `engine.py`**

Append to `src/oceanembed/whatif/engine.py`:

```python
from oceanembed.whatif import registry


def _baseline_values(ctx: compute.WhatIfContext) -> dict:
    """Real values used to fill inputs whose default is None (the 5 surface vars)."""
    return dict(ctx.surface) if ctx.surface else {}


def _delta(a: dict, b: dict) -> dict:
    """Numeric change (whatif - baseline) for scalar and equal-length list fields.

    Grids (numpy arrays), bools, strings and None are skipped -- deltas are for the
    numbers a reader compares, not the map arrays.
    """
    def _is_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    out: dict = {}
    for key in set(a) & set(b):
        av, bv = a[key], b[key]
        if _is_num(av) and _is_num(bv):
            out[key] = bv - av
        elif (isinstance(av, list) and isinstance(bv, list) and len(av) == len(bv)
              and all(_is_num(x) for x in av) and all(_is_num(x) for x in bv)):
            out[key] = [y - x for x, y in zip(av, bv)]
    return out


def apply(formula_id: str, overrides: dict, ctx: compute.WhatIfContext) -> dict:
    """Run one formula for its baseline inputs and for the overridden inputs, then diff.

    The SAME handler runs both times -- only the inputs differ -- so the comparison is
    honest and empty overrides reproduce the baseline exactly.
    """
    spec = registry.get(formula_id)
    base_vals = _baseline_values(ctx)
    base_inputs = registry.resolve_inputs(spec, {}, base_vals)
    what_inputs = registry.resolve_inputs(spec, overrides or {}, base_vals)

    base_out = spec.function(ctx, base_inputs)
    what_out = spec.function(ctx, what_inputs)

    return {
        "formula": spec.id,
        "label": spec.label,
        "scope": spec.scope,
        "hypothetical": True,
        "note": "What-if outputs come from user-edited inputs, not measured observations.",
        "inputs": {"baseline": base_inputs, "whatif": what_inputs},
        "baseline": base_out,
        "whatif": what_out,
        "delta": _delta(base_out, what_out),
    }
```

- [ ] **Step 4: Fill in `__init__.py` exports**

Replace the body of `src/oceanembed/whatif/__init__.py` with:

```python
"""What-If Calculator: override the inputs to the real model/formulas and see the effect.

Backend only (no Streamlit). Import order matters: compute defines the handlers,
registry registers them, engine exposes baseline()/apply().
"""
from oceanembed.whatif import compute, registry, engine   # noqa: F401  (import order)
from oceanembed.whatif.registry import (      # noqa: E402
    InputSpec, FormulaSpec, REGISTRY, get, list_formulas, resolve_inputs,
)
from oceanembed.whatif.compute import WhatIfContext        # noqa: E402
from oceanembed.whatif.engine import baseline, apply       # noqa: E402

__all__ = [
    "InputSpec", "FormulaSpec", "REGISTRY", "get", "list_formulas", "resolve_inputs",
    "WhatIfContext", "baseline", "apply",
]
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_whatif.py -k "apply or exports or three_ids" -v`
Expected: PASS (`three_ids` and `exports` everywhere; `apply` data tests here, SKIP elsewhere).

- [ ] **Step 6: Commit**

```bash
git add src/oceanembed/whatif/engine.py src/oceanembed/whatif/__init__.py tests/test_whatif.py
git commit -m "What-If: engine.apply() baseline-vs-whatif-vs-delta + package exports"
```

---

### Task 7: HANDOFF note + full-suite verification

Document the API for Arjhun and prove the whole module runs green together.

**Files:**
- Modify: `docs/HANDOFF.md` (append a dated entry — allowed: appended by everyone)
- Test: none new — run the whole file.

- [ ] **Step 1: Read the tail of `docs/HANDOFF.md`**

Run: `python -c "print(open('docs/HANDOFF.md', encoding='utf-8').read()[-1500:])"`
Purpose: match the file's existing entry format/date style before appending.

- [ ] **Step 2: Append the What-If API note**

Add to the end of `docs/HANDOFF.md` (adjust heading style to match what Step 1 showed):

```markdown
## 2026-09-16 — What-If Calculator backend (Unit B) [VERIFIED tests pass on Darshan's machine]

New package `src/oceanembed/whatif/` — a Streamlit-free sandbox to override formula/model
inputs and see baseline vs what-if vs delta. No UI (Arjhun wires it into port 8500), no new
port, no edits to other units' files. All what-if numbers carry `hypothetical: True`.

For the UI (Arjhun):
    from oceanembed.whatif import baseline, apply, list_formulas
    ctx = baseline(lat, lon, date, source="satellite")   # reads the real sst/sss/ssh/u/v + profile
    for spec in list_formulas():                          # build widgets from spec.inputs
        ...   # each input: .name .label .kind("float"|"bool") .default .min .max .unit
    res = apply("subsurface_profile", {"sst": 10.2}, ctx) # res["baseline"], ["whatif"], ["delta"]

Formulas registered: subsurface_profile (point; inputs sst,sss,ssh,u,v),
anomaly_extremes (grid; input k), observation_priority (grid; inputs w_anomaly,
w_uncertainty, w_sparsity, robust). Grid formulas also return their full grid
(grid_priority / grid_is_extreme / grid_standardized_anomaly) for map rendering.
Add a new tunable formula = one FormulaSpec appended in registry.py; the UI picks it up.

Spec: docs/superpowers/specs/2026-09-16-what-if-calculator-design.md
Plan: docs/superpowers/plans/2026-09-16-what-if-calculator.md
```

- [ ] **Step 3: Run the entire What-If suite**

Run: `python -m pytest tests/test_whatif.py -v`
Expected: all tests PASS (data-backed ones run here; none should error). Capture the summary line.

- [ ] **Step 4: Confirm nothing protected was touched**

Run: `git status --short`
Expected: only `src/oceanembed/whatif/*`, `tests/test_whatif.py`, `docs/HANDOFF.md`, and the pre-existing unrelated changes. If any protected file (predict.py, anomaly.py, observation_priority.py, app/ui/*, app/panels/*, launch.json) shows as modified, revert that change — it was not part of this plan.

- [ ] **Step 5: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "What-If: document backend API for the port-8500 UI (HANDOFF)"
```

---

## Self-Review

**1. Spec coverage:**
- Separate section, no UI, plugs into port 8500 → package is Streamlit-free; `apply`/`baseline`/`list_formulas` are the seam; HANDOFF documents it (Tasks 2/6/7). ✓
- Reuse the real functions unmodified → handlers import & call `mc_dropout_predict`, `anomaly.*`, `observation_priority`, and predict.py lookups; Global Constraints forbid editing them (Tasks 3–5). ✓
- Override 5 surface vars + `k` + `weights` + `robust` → three registered formulas cover all (Tasks 3–5). ✓
- Recompute profile / anomaly-extremes / priority → the three handlers (Tasks 3–5). ✓
- Baseline vs what-if vs delta, labelled hypothetical → `engine.apply` (Task 6). ✓
- Extensible registry as data → `FormulaSpec`/`InputSpec` + `register`; "add one entry" documented (Tasks 1/7). ✓
- No heavy deps; smallest-working-first; real-data smoke test → constraints + `needs_data` tests. ✓

**2. Placeholder scan:** No TBD/TODO; every code and test step is concrete. ✓

**3. Type consistency:** `WhatIfContext` fields and `ctx.grid()` keys (`temp, clim, a2d, u2d, sparsity`) match across compute/handlers; handler names (`compute_profile`, `compute_anomaly_extremes`, `compute_observation_priority`) match their registrations; `resolve_inputs(spec, overrides, baseline_values)` signature matches `apply`'s two calls; input names (`sst…v`, `k`, `w_anomaly/w_uncertainty/w_sparsity`, `robust`) match tests and handlers. ✓
