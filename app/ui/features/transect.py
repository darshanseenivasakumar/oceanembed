"""A vertical slice through the basin: distance across, depth down.

OWNER: Unit A (Arjhun). NOT a page.

The map views show one depth at a time. This is the view an oceanographer actually reads -- the
wall of water exposed by cutting the ocean along a line, with the thermocline visible as the
place where the colours crowd together.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from phase2.derived import transect as T

from app.ui import data as D
from app.ui import theme, ux

#: A default line that crosses the Arabian Sea into the Bay of Bengal -- it passes through both
#: basins, so the contrast a judge is being shown is visible without them hunting for it.
DEFAULT = (8.0, 55.0, 18.0, 92.0)


def _section_chart(sec: dict, show_iso: bool):
    dist = np.asarray(sec["distance_km"], dtype="float64")
    depths = np.asarray(T.DEPTHS, dtype="float64")
    temp = np.asarray(sec["temperature"], dtype="float64")     # (n_points, n_depths)

    dd, zz = np.meshgrid(dist, depths, indexing="ij")
    df = pd.DataFrame({"km": dd.ravel(), "depth": zz.ravel(), "t": temp.ravel()})

    # Explicit cell edges, or mark_rect guesses a band width and the section renders as stripes.
    step = float(np.median(np.diff(dist))) if dist.size > 1 else 25.0
    df["km0"] = df.km - step / 2
    df["km1"] = df.km + step / 2
    edges = np.concatenate([[0.0], (depths[1:] + depths[:-1]) / 2, [depths[-1] * 1.05]])
    idx = {float(z): q for q, z in enumerate(depths)}
    df["z0"] = df.depth.map(lambda z: edges[idx[z]])
    df["z1"] = df.depth.map(lambda z: edges[idx[z] + 1])

    heat = alt.Chart(df).mark_rect(stroke=None, invalid="show").encode(
        x=alt.X("km0:Q", title="distance along the line (km)", scale=alt.Scale(nice=False)),
        x2="km1:Q",
        y=alt.Y("z0:Q", title="depth (m)", scale=alt.Scale(reverse=True, nice=False)),
        y2="z1:Q",
        color=alt.Color("t:Q", title="°C", scale=alt.Scale(scheme="turbo"),
                        legend=alt.Legend(gradientLength=200)),
        tooltip=[alt.Tooltip("km:Q", format=".0f", title="km"),
                 alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                 alt.Tooltip("t:Q", format=".2f", title="°C")],
    ).properties(height=440)

    if not show_iso:
        return heat, None

    iso = T.isotherm_line(sec, threshold_c=26.0)
    idf = pd.DataFrame({"km": dist, "z": np.asarray(iso, dtype="float64")}).dropna()
    if idf.empty:
        return heat, 0
    line = alt.Chart(idf).mark_line(color=theme.CYAN, strokeWidth=2.5).encode(
        x="km:Q", y=alt.Y("z:Q", scale=alt.Scale(reverse=True, nice=False)))
    return heat + line, len(idf)


def render(ctx) -> None:
    c = st.columns([1.3, 1.3, 1.3, 1.3, 1.6, 1.6], vertical_alignment="bottom")
    with c[0]:
        lat0 = st.number_input("from °N", 5.0, 30.0, DEFAULT[0], 0.5, key="tr_lat0")
    with c[1]:
        lon0 = st.number_input("from °E", 45.0, 105.0, DEFAULT[1], 0.5, key="tr_lon0")
    with c[2]:
        lat1 = st.number_input("to °N", 5.0, 30.0, DEFAULT[2], 0.5, key="tr_lat1")
    with c[3]:
        lon1 = st.number_input("to °E", 45.0, 105.0, DEFAULT[3], 0.5, key="tr_lon1")
    with c[4]:
        with ux.control("npoints", ratio=(5, 2)):
            n = st.slider("Samples", 20, 160, 90, 10, key="tr_n")
    with c[5]:
        with ux.control("contours", ratio=(5, 2)):
            show_iso = st.toggle("26 °C line", value=True, key="tr_iso")

    e = st.columns([1.4, 4.6])
    with e[0]:
        ux.explain("endpoints")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)

    track = T.track_points(lat0, lon0, lat1, lon1, n=n)
    sec = T.sample_transect(track, f, keys=("temperature", "sigma"))

    temp = np.asarray(sec["temperature"], dtype="float64")
    if not np.isfinite(temp).any():
        st.warning("This line lies entirely over land or outside the grid. Move an endpoint.",
                   icon=":material/block:")
        return

    chart, n_iso = _section_chart(sec, show_iso)
    st.altair_chart(chart, use_container_width=True)

    total_km = float(np.asarray(sec["distance_km"])[-1])
    ux.tiles([
        ("LINE LENGTH", f"{total_km:,.0f}", "km"),
        ("COLUMNS SAMPLED", f"{n:,}", "", "reconstructed along the line"),
        ("SURFACE RANGE", f"{np.nanmin(temp[:, 0]):.1f}–{np.nanmax(temp[:, 0]):.1f}", "°C"),
        ("26 °C LINE FOUND", f"{n_iso:,}" if n_iso is not None else "off", "",
         "columns where it could be resolved" if n_iso is not None else ""),
    ])
    if show_iso and n_iso == 0:
        st.info("The 26 °C line could not be drawn anywhere along this track — either the surface "
                "is already below 26 °C, or the column never crosses it. That is a real answer, "
                "not a rendering failure.", icon=":material/info:")

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"d(\mathbf{p}_0,\mathbf{p}_1)=2R\arcsin\!\sqrt{\sin^2\tfrac{\Delta\varphi}{2}"
        r"+\cos\varphi_0\cos\varphi_1\sin^2\tfrac{\Delta\lambda}{2}}"
        r"\qquad T(\mathbf{p})=\sum_{c}w_c\,T_c",
        [("d", "great-circle distance along the line", "km", "haversine, transect.py"),
         ("R", "Earth radius", "6371.0088 km", "src/phase2/derived/transect.py EARTH_R_KM"),
         ("φ, λ", "latitude and longitude in radians", "rad", "the two endpoints you set"),
         ("w_c", "bilinear weights over the four grid cells surrounding the sample point", "—",
          "transect.bilinear_at"),
         ("T_c", "reconstructed temperature at one surrounding grid cell", "°C", "model output")],
        "Points are spaced evenly along the great circle, then each column is interpolated "
        "bilinearly from the four surrounding 0.25° cells. No new model call per point — the "
        "whole field is reconstructed once and sampled.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("A wall of water. Warm at the top, cold at the bottom, and the band where the "
              "colours crowd together is the thermocline — the ocean's lid."),
        conclude=("Where the warm layer is thick, heat is stored deep and is available to a "
                  "storm. Where the thermocline rises towards the surface, cold water is close "
                  "behind — often a sign of upwelling, which is also where fisheries concentrate."),
        limits=[
            ("Only 15 depths exist. The smooth vertical gradient here is drawn between them, not "
             "measured at every metre.", "oceanembed.config.DEPTHS"),
            ("Interpolation is bilinear across 0.25° cells, so features narrower than about 27 km "
             "cannot appear at all.", "src/phase2/derived/transect.py bilinear_at"),
            ("The model reproduces 100.6 % of the observed thermocline gradient but flattens the "
             "top 30 m to about 42 % — a limit of what a daily-mean satellite field can carry.",
             "artifacts/physical_consistency.json"),
        ])
