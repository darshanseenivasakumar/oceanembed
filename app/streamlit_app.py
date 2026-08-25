"""OceanEmbed demo shell.

OWNER: Unit B (Darshan). Sidebar controls + mounts Unit C's panels via their render(recon_output, argo_df).
Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import streamlit as st  # noqa: E402
from oceanembed import config  # noqa: E402

st.set_page_config(page_title="OceanEmbed — NIO subsurface", layout="wide")
st.title("OceanEmbed — North Indian Ocean subsurface temperature")
st.caption("SIH26066 · reconstruction + uncertainty + anomaly + observation-priority")

with st.sidebar:
    st.header("Query")
    lat = st.slider("Latitude", float(config.LAT.min()), float(config.LAT.max()), 15.0, 0.25)
    lon = st.slider("Longitude", float(config.LON.min()), float(config.LON.max()), 75.0, 0.25)
    date = st.date_input("Date")
    run = st.button("Reconstruct")

st.info(
    "Scaffold shell. Unit B wires `inference.predict.reconstruct()` here on Day 4; "
    "Unit C panels (profile / map / priority / validation) mount below. "
    "Every displayed number must come from the real model (LIVE or model-generated CACHED)."
)

# Day 4+:
#   from oceanembed.inference.predict import reconstruct
#   from app.panels import profile_panel, map_panel, priority_panel, validation_panel
#   if run: out = reconstruct(lat, lon, date); profile_panel.render(out, argo_df=...)
