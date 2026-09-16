"""Public API for the What-If Calculator. Streamlit-free; returns plain dict/list/numpy."""
from __future__ import annotations

from oceanembed.whatif import compute
from oceanembed.whatif.registry import list_formulas   # re-export


def baseline(lat: float, lon: float, date, source: str = "satellite") -> compute.WhatIfContext:
    """Snap to grid, set the surface source, read the real sst/sss/ssh/u/v + point profile."""
    return compute.build_context(lat, lon, date, source)


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
