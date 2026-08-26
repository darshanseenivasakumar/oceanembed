"""Streamlit observation-priority panel: def render(grid_output, argo_df=None).

OWNER: Unit C (Mitun+Niru).

WORDING IS PART OF THE DELIVERABLE. This map says "regions where additional observations may
provide high scientific value". It must never read as "the AI tells MoES where to deploy Argo
floats" -- we have no mandate, no cost model, and no float logistics. See docs/NOVELTY_MATRIX.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config
from app.panels._viz import colorize, value_range


def _top_k(priority: np.ndarray, k: int, min_sep: int = 6) -> pd.DataFrame:
    """K highest-priority cells, greedily spaced at least min_sep cells apart.

    Without the spacing, the top 10 are 10 neighbouring cells of one blob -- which looks like ten
    findings but is one.
    """
    p = np.where(np.isfinite(priority), priority, -np.inf)
    picked: list[tuple[int, int]] = []
    for flat in np.argsort(p, axis=None)[::-1]:
        i, j = np.unravel_index(flat, p.shape)
        if not np.isfinite(p[i, j]):
            break
        if all(max(abs(i - a), abs(j - b)) >= min_sep for a, b in picked):
            picked.append((int(i), int(j)))
        if len(picked) == k:
            break

    return pd.DataFrame({
        "rank": np.arange(1, len(picked) + 1),
        "lat (°N)": [round(float(config.LAT[i]), 2) for i, _ in picked],
        "lon (°E)": [round(float(config.LON[j]), 2) for _, j in picked],
        "priority": [round(float(priority[i, j]), 3) for i, j in picked],
    })


def render(grid_output: dict, argo_df=None) -> None:
    g = grid_output
    priority = g.get("priority")

    if priority is None:
        st.info("Observation-priority map appears once `observation_priority()` is available.")
        return

    priority = np.asarray(priority, dtype="float32")
    land = np.asarray(g["land_mask"]).astype(bool) if g.get("land_mask") is not None else None

    if not np.isfinite(priority).any():
        st.warning(
            "Priority is undefined everywhere — all three inputs (anomaly, uncertainty, "
            "observation sparsity) are constant, so nothing can be ranked. This usually means "
            "`argo_test` has not been built yet."
        )
        return

    st.image(colorize(priority, land_mask=land), width='stretch',
             caption=f"Observation priority — {g.get('date', '')}")

    lo, hi = value_range(priority)
    st.caption(
        f"{config.LAT.min():.2f}–{config.LAT.max():.2f}°N, {config.LON.min():.2f}–"
        f"{config.LON.max():.2f}°E · scale {lo:.2f} → {hi:.2f} · brighter = higher priority · "
        "grey = land / no data"
    )

    k = st.slider("How many locations to list", 3, 15, 8, key="priority_k")
    st.dataframe(_top_k(priority, k), hide_index=True, width='stretch')

    st.markdown(
        "**What this is:** a combination of how anomalous the reconstruction is, how uncertain the "
        "model is there, and how far the cell sits from the nearest recent ARGO profile — the "
        "weighted geometric mean of those three, normalised to [0, 1]. High means *all three* hold "
        "at once, so it flags **regions where additional in-situ observations may add scientific "
        "value**."
    )
    st.markdown(
        "**What this is not:** this is **not a deployment recommendation**. It carries no cost "
        "model, no float drift physics, and no operational constraints, and its uncertainty term is "
        "currently known to be overconfident at **every** depth, worst in the mixed layer "
        "(20–50 m) (`docs/DECISIONS.md` D-016, remeasured 2026-08-26). Treat it as a "
        "discussion aid, not a directive."
    )
