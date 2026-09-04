"""Cross-section (transect) view -- depth vs distance along a line the user draws.

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/transect_page.py --server.port 8510

WHY THIS VIEW
A vertical slice is how an oceanographer reads structure -- a tilting thermocline, an eddy's
subsurface core, a coastal gradient -- more directly than spinning a 3-D cube. Two endpoints and a
date in; a (distance x depth) section of temperature (or model spread) out, with the 20 C and 26 C
isotherms drawn as real lines.

TWO HONESTY POINTS, BOTH ENFORCED IN THE MATH, NOT JUST THE CAPTION
  * The section is sampled by BILINEAR interpolation of the field, because reconstruct() snaps to
    the nearest grid centre -- sampling it directly would draw a staircase. (phase2.derived.transect)
  * Land and the seafloor are GAPS, never a value smoothed across them: an interpolated cell that
    touches a NaN corner is itself NaN. So a blank in the section is the coast or the bottom, not
    missing model output.
The isotherms are exact (linear interpolation between bracketing depth levels), so unlike the map
page they are drawn as true lines, not a highlighted band.
"""
from __future__ import annotations

import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config                         # noqa: E402
from phase2.derived import transect as T              # noqa: E402

st.set_page_config(page_title="OceanEmbed — Transect", layout="wide")

COLOR_FIELD = {"temperature": "Temperature (°C)",
               "sigma": "Model spread (°C, 1σ — NOT calibrated)"}


@st.cache_data(show_spinner="Reconstructing the field …")
def build_field(date_str: str, source: str, version: str = ""):
    """One daily field, cached by value. `source='v2 satellite'` is THE SHIPPED MODEL; the other
    options reconstruct with a local checkpoint for machines without the satellite bundle."""
    from phase2.tscast_nio.field import predict_field
    from phase2.tscast_nio.inference import TSCastPredictor
    from phase2.tscast_nio import dataset as D

    if source == "v2 satellite":
        f = predict_field(TSCastPredictor(), date_str)
    else:                                              # local GLORYS checkpoint, its own bundle
        d = D.load_daily(os.path.join(config.DATA_PROCESSED, "daily"))
        f = predict_field(TSCastPredictor(checkpoint=config.art(f"{source}.pt"), data=d), date_str)
    # keep only what the transect needs, so the cache entry is small and picklable
    return {"date": f["date"], "temperature": f["temperature"], "sigma": f["sigma"]}


@st.cache_data(show_spinner="Sampling the section …")
def build_section(date_str, source, lat0, lon0, lat1, lon1, n, version: str = ""):
    field = build_field(date_str, source, version)
    track = T.track_points(lat0, lon0, lat1, lon1, n=n)
    sec = T.sample_transect(track, field)
    sec["d20"] = T.isotherm_line(sec, 20.0)
    sec["d26"] = T.isotherm_line(sec, 26.0)
    sec["date"] = field["date"]
    return sec


def _edges(centres: np.ndarray, floor: float | None = None) -> np.ndarray:
    """Cell-boundary positions for a pcolormesh-style rect plot: midpoints between centres, with
    the two outer edges extended by half the neighbouring spacing."""
    c = np.asarray(centres, dtype="float64")
    mid = (c[:-1] + c[1:]) / 2
    first = c[0] - (mid[0] - c[0])
    last = c[-1] + (c[-1] - mid[-1])
    e = np.concatenate([[first], mid, [last]])
    if floor is not None:
        e[0] = floor                                   # pin the surface edge to 0 m
    return e


def _rect_frame(sec: dict, field: str) -> pd.DataFrame:
    """Long dataframe of (x0,x1,y0,y1,value) rectangles -- one per (point, depth) with data."""
    dist = sec["distance_km"]
    depths = sec["depths"]
    vals = sec[field]
    xe = _edges(dist)
    ye = _edges(depths, floor=0.0)
    rows = []
    for k in range(len(dist)):
        for di in range(len(depths)):
            v = vals[k, di]
            if np.isfinite(v):
                rows.append((xe[k], xe[k + 1], ye[di], ye[di + 1], float(v),
                             float(dist[k]), float(depths[di])))
    return pd.DataFrame(rows, columns=["x0", "x1", "y0", "y1", "value", "distance", "depth"])


def _chart(sec: dict, field: str):
    df = _rect_frame(sec, field)
    if df.empty:
        return None
    scheme = "turbo" if field == "temperature" else "viridis"
    heat = alt.Chart(df).mark_rect().encode(
        x=alt.X("x0:Q", title="distance along track (km)"),
        x2="x1:Q",
        y=alt.Y("y0:Q", scale=alt.Scale(reverse=True), title="depth (m)"),
        y2="y1:Q",
        color=alt.Color("value:Q", title=COLOR_FIELD[field],
                        scale=alt.Scale(scheme=scheme)),
        tooltip=[alt.Tooltip("distance:Q", format=".0f", title="km"),
                 alt.Tooltip("depth:Q", title="m"),
                 alt.Tooltip("value:Q", format=".2f", title=COLOR_FIELD[field])])
    layers = [heat]
    # isotherms as REAL lines (exact interpolation), gapped where the water is too cold
    for key, thr, col in (("d20", 20.0, "#111111"), ("d26", 26.0, "#ffffff")):
        line_df = pd.DataFrame({"distance": sec["distance_km"], "depth": sec[key]}).dropna()
        if not line_df.empty:
            layers.append(alt.Chart(line_df).mark_line(color=col, strokeWidth=2).encode(
                x="distance:Q", y=alt.Y("depth:Q", scale=alt.Scale(reverse=True))))
    return alt.layer(*layers).properties(height=460).interactive()


def main() -> None:
    st.title("Ocean transect — a vertical slice along a line")
    st.caption("Depth vs distance along the great circle between two points. Isotherms: black = "
               "20 °C, white = 26 °C. Blank = land or below the seafloor, never a smoothed value.")

    with st.sidebar:
        st.header("Track")
        c1, c2 = st.columns(2)
        lat0 = c1.number_input("start lat", 5.0, 29.75, 10.0, 0.25)
        lon0 = c2.number_input("start lon", 45.0, 104.75, 85.0, 0.25)
        lat1 = c1.number_input("end lat", 5.0, 29.75, 15.0, 0.25)
        lon1 = c2.number_input("end lon", 45.0, 104.75, 95.0, 0.25)
        n = st.slider("points along track", 20, 120, 60, 10)
        field = st.radio("colour by", list(COLOR_FIELD), format_func=COLOR_FIELD.get)
        source = st.selectbox("model / bundle",
                              ["v2 satellite", "tscast_stage1_7ch", "tscast_stage1_5ch"],
                              help="v2 satellite is the shipped model; the others are local "
                                   "GLORYS checkpoints for machines without the satellite bundle.")
        date_str = st.text_input("date (YYYY-MM-DD)", "2025-12-18")

    try:
        sec = build_section(date_str, source, lat0, lon0, lat1, lon1, n)
    except Exception as e:                             # missing bundle / bad date / no checkpoint
        st.error(f"Could not build the section: {e}")
        st.info("If this is the shipped model, the satellite bundle must be on this machine. "
                "Try a local GLORYS checkpoint from the sidebar instead.")
        return

    chart = _chart(sec, field)
    if chart is None:
        st.warning("The whole track is land or below the seafloor — no section to draw.")
        return

    km = float(sec["distance_km"][-1])
    st.caption(f"{sec['date']} · {km:.0f} km · {sec['temperature'].shape[0]} points, "
               f"sampled by bilinear interpolation of the reconstructed field.")
    st.altair_chart(chart, use_container_width=True)

    d26 = sec["d26"]
    if np.isfinite(d26).any():
        st.caption(f"26 °C isotherm depth along this line: {np.nanmin(d26):.0f}–{np.nanmax(d26):.0f} m "
                   f"({int(np.isnan(d26).sum())} of {d26.size} points never reach 26 °C at the surface).")


if __name__ == "__main__":
    main()
