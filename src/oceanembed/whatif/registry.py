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
