"""Public API for the What-If Calculator. Streamlit-free; returns plain dict/list/numpy."""
from __future__ import annotations

from oceanembed.whatif import compute
from oceanembed.whatif.registry import list_formulas   # re-export


def baseline(lat: float, lon: float, date, source: str = "satellite") -> compute.WhatIfContext:
    """Snap to grid, set the surface source, read the real sst/sss/ssh/u/v + point profile."""
    return compute.build_context(lat, lon, date, source)
