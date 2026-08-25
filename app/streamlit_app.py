"""OceanEmbed demo shell.

OWNER: Unit B (Darshan).

PANEL POLICY (no collisions): if Unit C's app/panels/<x>_panel.py implements render(), the shell uses it.
Otherwise the shell draws a MINIMAL built-in fallback so the demo is always clickable. Unit C's panels
replace the fallbacks automatically — no edits to this file needed.

Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from oceanembed import config  # noqa: E402
from oceanembed.inference import predict as P  # noqa: E402

st.set_page_config(page_title="OceanEmbed — NIO subsurface", layout="wide")


def _to_image(arr):
    """Normalize a (lat,lon) array to a displayable image, flipped so north is up."""
    a = np.asarray(arr, dtype="float32")
    lo, hi = np.nanmin(a), np.nanmax(a)
    norm = np.zeros_like(a) if hi <= lo else (a - lo) / (hi - lo)
    return np.flipud(np.nan_to_num(norm))


def _panel(name: str):
    """Return Unit C's render() if it exists and is implemented, else None."""
    try:
        mod = __import__(f"app.panels.{name}_panel", fromlist=["render"])
        fn = getattr(mod, "render", None)
        return fn if callable(fn) else None
    except Exception:
        return None


st.title("OceanEmbed — North Indian Ocean subsurface temperature")
st.caption("SIH26066 · reconstruction + uncertainty + anomaly + observation-priority")

# ---- data availability -------------------------------------------------------
try:
    dates = P.available_dates()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

synthetic = os.path.exists(os.path.join(config.DATA_RAW, "synthetic_glorys.nc"))
if synthetic:
    st.warning(
        "**SYNTHETIC DATA MODE** — these fields are simulated for pipeline testing. "
        "Numbers are illustrative, **not** real ocean performance. Run the real CMEMS download "
        "(`prepare_dataset.py --real`) before showing results to judges.", icon="⚠️")

with st.sidebar:
    st.header("Query")
    lat = st.slider("Latitude (°N)", float(config.LAT.min()), float(config.LAT.max()), 15.0, 0.25)
    lon = st.slider("Longitude (°E)", float(config.LON.min()), float(config.LON.max()), 75.0, 0.25)
    date = st.selectbox("Date", dates, index=len(dates) - 1)
    st.divider()
    show_map = st.checkbox("Compute full-grid maps (slower)", value=False)
    run = st.button("Reconstruct", type="primary")

if not run:
    st.info("Pick a location and date, then press **Reconstruct**. "
            "Every number shown is produced by the trained model — nothing is hardcoded.")
    st.stop()

# ---- point reconstruction ----------------------------------------------------
with st.spinner("Running model…"):
    out = P.reconstruct(lat, lon, date)

if out["is_land"]:
    st.error(f"({out['lat']:.2f}°N, {out['lon']:.2f}°E) is land / no data. Pick an ocean point.")
    st.stop()

st.success(f"LIVE INFERENCE · {out['lat']:.2f}°N, {out['lon']:.2f}°E · {out['date']}")

c = st.columns(5)
for col, (k, unit) in zip(c, [("sst", "°C"), ("sss", "psu"), ("ssh", "m"), ("u", "m/s"), ("v", "m/s")]):
    col.metric(k.upper(), f"{out['surface'][k]:.2f} {unit}")

left, right = st.columns([2, 3])

with left:
    st.subheader("Vertical temperature profile")
    fn = _panel("profile")
    if fn:
        fn(out)
    else:
        df = pd.DataFrame({
            "depth": out["depths"],
            "prediction": out["profile_mean"],
            "−1σ": out["profile_mean"] - out["profile_std"],
            "+1σ": out["profile_mean"] + out["profile_std"],
        })
        if out["climatology"] is not None:
            df["climatology"] = out["climatology"]
        st.line_chart(df.set_index("depth"))
        st.caption("Depth (m) on the x-axis; band = ±1σ MC-dropout spread. "
                   "_Fallback view — Unit C's profile_panel replaces this._")

with right:
    st.subheader("Per-depth detail")
    tbl = pd.DataFrame({
        "depth (m)": out["depths"],
        "temp (°C)": np.round(out["profile_mean"], 3),
        "± std (°C)": np.round(out["profile_std"], 3),
        "reliability": out["reliability"],
    })
    if out["anomaly"] is not None:
        tbl["anomaly (°C)"] = np.round(out["anomaly"], 3)
    st.dataframe(tbl, hide_index=True, use_container_width=True)
    st.caption("Reliability is derived from the MC-dropout spread — not an invented confidence number.")

# ---- optional grid maps ------------------------------------------------------
if show_map:
    st.divider()
    with st.spinner("Reconstructing the full grid…"):
        gout = P.reconstruct_grid(date)

    surf = gout["temp"][:, :, 0]
    st.subheader(f"Surface-level reconstruction — {gout['date']}")
    fn = _panel("map")
    if fn:
        fn(gout)
    else:
        st.image(_to_image(surf), caption="Reconstructed 0 m temperature (fallback view)",
                 use_container_width=True)

    if gout["priority"] is not None:
        st.subheader("Observation priority")
        fn = _panel("priority")
        fn(gout) if fn else st.image(_to_image(gout["priority"]), use_container_width=True)
        st.caption("Regions where **additional in-situ observations may provide high scientific value** "
                   "(anomaly × uncertainty × observation sparsity). Not a deployment directive.")
    else:
        st.info("Observation-priority map appears once Unit A implements `observation_priority()`.")
