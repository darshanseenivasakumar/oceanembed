"""Streamlit map panel: def render(grid_output, argo_df=None).

OWNER: Unit C (Mitun+Niru).

Consumes reconstruct_grid()'s dict: {date, temp(100,240,11), uncertainty|None, anomaly|None,
priority(100,240)|None, land_mask(100,240)}.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from oceanembed import config
from app.panels._viz import colorize, value_range


def _extent_caption() -> str:
    return (f"{config.LAT.min():.2f}–{config.LAT.max():.2f}°N, "
            f"{config.LON.min():.2f}–{config.LON.max():.2f}°E · 0.25° grid · north is up")


def render(grid_output: dict, argo_df=None) -> None:
    g = grid_output
    temp = np.asarray(g["temp"], dtype="float32")
    land = np.asarray(g["land_mask"]).astype(bool) if g.get("land_mask") is not None else None

    layer_opts = ["Temperature"]
    if g.get("anomaly") is not None:
        layer_opts.append("Anomaly vs climatology")
    if g.get("uncertainty") is not None:
        layer_opts.append("Uncertainty (±1σ)")

    c1, c2 = st.columns([2, 3])
    with c1:
        layer = st.radio("Layer", layer_opts, horizontal=False, key="map_layer")
    with c2:
        depth_idx = st.select_slider(
            "Depth (m)", options=list(range(len(config.DEPTHS))),
            value=0, format_func=lambda i: f"{config.DEPTHS[i]} m", key="map_depth")

    if layer == "Temperature":
        field, diverging, unit = temp[:, :, depth_idx], False, "°C"
    elif layer.startswith("Anomaly"):
        field, diverging, unit = np.asarray(g["anomaly"], "float32")[:, :, depth_idx], True, "°C"
    else:
        field, diverging, unit = np.asarray(g["uncertainty"], "float32")[:, :, depth_idx], False, "°C"

    if not np.isfinite(field).any():
        st.warning(f"No finite values at {config.DEPTHS[depth_idx]} m for this layer.")
        return

    st.image(colorize(field, land_mask=land, diverging=diverging),
             width='stretch',
             caption=f"{layer} at {config.DEPTHS[depth_idx]} m — {g.get('date', '')}")

    lo, hi = value_range(field)
    scale = (f"diverging scale centred on 0, ±{max(abs(lo), abs(hi)):.2f} {unit}"
             if diverging else f"{lo:.2f} → {hi:.2f} {unit} (2nd–98th percentile)")
    st.caption(f"{_extent_caption()} · {scale} · grey = land / no data")

    ocean = field[np.isfinite(field)]
    m1, m2, m3 = st.columns(3)
    m1.metric(f"min {unit}", f"{ocean.min():.2f}")
    m2.metric(f"mean {unit}", f"{ocean.mean():.2f}")
    m3.metric(f"max {unit}", f"{ocean.max():.2f}")

    if diverging:
        st.caption("Blue = cooler than climatology, red = warmer. Anomaly is a **difference from "
                   "the monthly mean**, not an extreme-event detection.")
