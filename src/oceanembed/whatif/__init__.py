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
