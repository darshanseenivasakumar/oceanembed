"""Cyclone Heat — Tropical Cyclone Heat Potential, daily, from satellites alone.

OWNER: Unit B (Darshan). PHASE-2 ONLY. A NEW file under app/phase2/, a derived product on the
FROZEN model. The frozen demo and everything the freeze covers are neither touched nor imported.

    streamlit run app/phase2/cyclone_heat_page.py --server.port 8509

THE HEADLINE THIS UNLOCKS
TCHP is the ocean's cyclone-intensification variable: the heat stored above the 26 °C isotherm. We
produce it daily over the Bay of Bengal and Arabian Sea from satellite-only inputs — no in-situ
floats. For a Disaster-Management PS under INCOIS, this is the feature that makes the project
nationally relevant, not just accurate.

DEMO-SAFE, like cube_page.py: the inspect point is chosen with lat/lon inputs (a widget that always
works), everything degrades to a message rather than blanking, and the version-keyed cache prevents
the stale-predictor trap that produced an 8 °C error on this app once.
"""
from __future__ import annotations

import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config  # noqa: E402
from phase2.derived import heat_content as hc  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Cyclone Heat", layout="wide")

FIELDS = {
    "tchp": ("Tropical Cyclone Heat Potential", "kJ/cm²"),
    "ohc_0_zref": ("Ocean Heat Content (0–700 m)", "GJ/m²"),
    "d26": ("Depth of the 26 °C isotherm", "m"),
}


def _v2_version() -> str:
    """Cache key that moves when the shipped model or the code that loads it moves — see
    cube_page._v2_version for why (a stale predictor once served an 8 °C error for 9.5 minutes)."""
    import hashlib

    from phase2.tscast_nio import dataset as _D, field as _F, inference as _I
    from phase2.derived import heat_content as _H

    h = hashlib.sha256()
    for p in (config.art("tscast_stage1.pt"), _I.__file__, _D.__file__, _F.__file__, _H.__file__):
        try:
            s = os.stat(p)
            h.update(f"{p}:{s.st_mtime_ns}:{s.st_size}".encode())
        except OSError:
            h.update(f"{p}:missing".encode())
    return h.hexdigest()[:16]


@st.cache_data(show_spinner="Reconstructing the field and computing heat content …")
def build(date_str: str, version: str = "") -> dict:
    """predict_field (frozen) -> heat_content_field. Cached by value only; `version` busts it."""
    from phase2.tscast_nio.field import predict_field
    from phase2.tscast_nio.inference import TSCastPredictor

    field = predict_field(TSCastPredictor(), date_str)
    products = hc.heat_content_field(field)
    products["temperature"] = field["temperature"]     # kept for the click-point profile panel
    return products


def _map(values: np.ndarray, what: str) -> alt.LayerChart:
    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "value": np.asarray(values).ravel()}).dropna(subset=["value"])
    _, units = FIELDS[what]
    # TCHP gets a perceptually-uniform warm ramp; D26 reversed (shallow warm layer = more heat).
    scheme = {"tchp": "inferno", "ohc_0_zref": "inferno", "d26": "viridis"}[what]
    heat = alt.Chart(df).mark_rect().encode(
        x=alt.X("lon:O", title="longitude (°E)", axis=alt.Axis(values=list(range(45, 106, 10)))),
        y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                axis=alt.Axis(values=list(range(5, 31, 5)))),
        color=alt.Color("value:Q", title=units, scale=alt.Scale(scheme=scheme)),
        tooltip=["lat", "lon", alt.Tooltip("value:Q", format=".1f", title=units)],
    ).properties(height=520)

    # The 50 and 80 kJ/cm^2 lines are the forecaster's reference thresholds (RI-supportive / high).
    # Drawn as marked cells rather than true contours: altair has no contour mark, and an honest
    # highlight beats a fake smooth line the data does not support at 0.25°.
    if what == "tchp":
        for thr, col in ((50.0, "#4daf4a"), (80.0, "#ffffff")):
            band = df[(df["value"] >= thr) & (df["value"] < thr + 2.0)]
            if not band.empty:
                heat += alt.Chart(band).mark_point(size=6, color=col, opacity=0.6).encode(
                    x="lon:O", y=alt.Y("lat:O", sort="descending"))
    return heat


def _profile_panel(temp_col: np.ndarray, lat: float, lon: float):
    depths = np.asarray(config.DEPTHS, dtype="float64")
    df = pd.DataFrame({"depth": depths, "temp": temp_col}).dropna(subset=["temp"])
    if df.empty:
        st.info("No ocean at this point (land or below the seafloor).")
        return
    line = alt.Chart(df).mark_line(point=True, color="#e6550d").encode(
        x=alt.X("temp:Q", title="temperature (°C)"),
        y=alt.Y("depth:Q", scale=alt.Scale(reverse=True), title="depth (m)"),
        tooltip=[alt.Tooltip("depth:Q", title="m"), alt.Tooltip("temp:Q", format=".2f", title="°C")])
    iso = alt.Chart(pd.DataFrame({"x": [hc.ISO_C]})).mark_rule(
        color="#333", strokeDash=[5, 4]).encode(x="x:Q")
    st.altair_chart((line + iso).properties(
        height=360, title="the profile TCHP integrated — dashed line is 26 °C"),
        use_container_width=True)


def main() -> None:
    st.title("Cyclone Heat — TCHP from satellites alone")
    st.caption("**Tropical Cyclone Heat Potential** is the heat stored above the 26 °C isotherm — "
               "the ocean variable that fuels rapid intensification. We produce it daily over the "
               "Bay of Bengal and Arabian Sea from satellite-only inputs, with no in-situ floats.")

    with st.sidebar:
        st.header("Field")
        date = st.date_input("Date", value=pd.Timestamp("2026-05-15"),
                             min_value=pd.Timestamp("2025-06-01"),
                             max_value=pd.Timestamp("2026-06-23"))
        what = st.selectbox("Show", list(FIELDS), format_func=lambda k: FIELDS[k][0])
        st.divider()
        st.subheader("Inspect a point")
        plat = st.number_input("Latitude (°N)", min_value=float(config.REGION["lat_min"]),
                               max_value=float(config.REGION["lat_max"]), value=15.0, step=0.25)
        plon = st.number_input("Longitude (°E)", min_value=float(config.REGION["lon_min"]),
                               max_value=float(config.REGION["lon_max"]), value=88.0, step=0.25)

    try:
        products = build(str(date), _v2_version())
    except FileNotFoundError as e:
        st.error("The satellite bundle isn't on this machine, so the live model can't run here. "
                 "This page runs where `data/processed/daily_sat/v001` exists (the training box).")
        st.caption(f"Details: {e}")
        return
    except Exception as e:
        st.error(f"Could not build the field: {type(e).__name__}: {e}")
        return

    values = products["tchp"] if what == "tchp" else products[what]
    name, units = FIELDS[what]

    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(_map(values, what), use_container_width=True)
        if what == "tchp":
            st.caption("Marked cells trace the **50** (green) and **80** (white) kJ/cm² levels: "
                       "above ~50 is generally supportive of rapid intensification, above ~80 is "
                       "high. Reference context for a forecaster, not a hard rule.")
    with right:
        i, j = _cell(float(plat), float(plon))
        tchp_v, d26_v, ohc_v = (products["tchp"][i, j], products["d26"][i, j],
                                products["ohc_0_zref"][i, j])
        c = st.columns(3)
        c[0].metric("TCHP", "—" if not np.isfinite(tchp_v) else f"{tchp_v:.0f}", help="kJ/cm²")
        c[1].metric("D26", "—" if not np.isfinite(d26_v) else f"{d26_v:.0f} m")
        c[2].metric("OHC 0–700", "—" if not np.isfinite(ohc_v) else f"{ohc_v:.2f}", help="GJ/m²")
        _profile_panel(products["temperature"][i, j], float(plat), float(plon))

    with st.expander(f"About {name}"):
        st.write({"tchp": "Heat above the 26 °C isotherm; the cyclone-intensification variable.",
                  "ohc_0_zref": "Total heat content in the top 700 m.",
                  "d26": "Depth of the 26 °C isotherm; a deep warm layer resists storm-driven "
                         "cooling."}[what])
    with st.expander("Provenance"):
        st.json(products.get("provenance"))


def _cell(lat: float, lon: float) -> tuple[int, int]:
    i = int(np.abs(np.asarray(config.LAT) - lat).argmin())
    j = int(np.abs(np.asarray(config.LON) - lon).argmin())
    return i, j


if __name__ == "__main__":
    main()
