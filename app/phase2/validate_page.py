"""Validate Live — the model's profile beside a real, independent Argo float.

OWNER: Unit B (Darshan). PHASE-2 ONLY. A NEW file under app/phase2/, a derived product on the
FROZEN model. The frozen demo (app/streamlit_app.py, app/panels/) and everything the freeze covers
are neither touched nor imported.

    streamlit run app/phase2/validate_page.py --server.port 8505

WHAT THIS ANSWERS, BEFORE A JUDGE ASKS IT
"Is it actually real, or did you overfit?" You pick a point; the page runs the SAME frozen model
the dashboard uses and drops a real held-out Argo float on top of the prediction, with the per-depth
error live. The float is independent — never used for training — so the overlay is the model being
checked against ground truth in front of you.

DEMO-SAFE BY CONSTRUCTION (the house rule from cube_page.py)
The point is chosen with latitude/longitude inputs, not a click handler: a selection widget that
ImportErrors or mis-fires on demo day is worse than a plain one that always works. A small map shows
where the point landed. Everything degrades to text rather than blanking.
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
from phase2.validation import argo_overlay as ao  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Validate Live", layout="wide")


def _v2_version() -> str:
    """Cache key that moves when the shipped model or the code that loads it moves.

    Identical in spirit to cube_page._v2_version: st.cache_data keys on arguments and cannot see
    imported module source, so a server started before a fix keeps serving a stale predictor. That
    exact trap produced an 8 °C error on the Profile tab on 2026-09-02. Bust the cache on file mtime.
    """
    import hashlib

    from phase2.tscast_nio import dataset as _D, inference as _I
    from phase2.validation import argo_overlay as _A

    h = hashlib.sha256()
    for p in (config.art("tscast_stage1.pt"), _I.__file__, _D.__file__, _A.__file__):
        try:
            s = os.stat(p)
            h.update(f"{p}:{s.st_mtime_ns}:{s.st_size}".encode())
        except OSError:
            h.update(f"{p}:missing".encode())
    return h.hexdigest()[:16]


@st.cache_data(show_spinner="Running the frozen model and matching a float …")
def run_overlay(lat: float, lon: float, date_str: str, k: int, version: str = "") -> dict:
    """Cached by value only — no underscore-prefixed argument, which cache_data would silently drop
    from the key and pin the first result forever. `version` moves it when the model/code moves."""
    from phase2.tscast_nio.inference import TSCastPredictor

    return ao.overlay(lat, lon, date_str, predictor=TSCastPredictor(), k=k)


def _overlay_chart(depths, mean, band, float_profile) -> alt.LayerChart:
    """Prediction line + shaded ±2σ band + float markers, depth increasing DOWN the y-axis."""
    rows = []
    for k, d in enumerate(depths):
        rows.append({
            "depth": float(d),
            "mean": mean[k], "lo": band["lo"][k], "hi": band["hi"][k],
            "float": float_profile[k],
        })
    df = pd.DataFrame(rows)

    y = alt.Y("depth:Q", scale=alt.Scale(reverse=True), title="depth (m)")
    band_layer = alt.Chart(df).mark_area(opacity=0.25, color="#1f77b4").encode(
        x=alt.X("lo:Q", title="temperature (°C)"), x2="hi:Q", y=y)
    mean_layer = alt.Chart(df).mark_line(strokeWidth=3, color="#1f77b4").encode(
        x="mean:Q", y=y,
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                 alt.Tooltip("mean:Q", format=".2f", title="model °C"),
                 alt.Tooltip("float:Q", format=".2f", title="float °C")])
    float_layer = alt.Chart(df.dropna(subset=["float"])).mark_point(
        size=70, color="#d62728", filled=True).encode(
        x="float:Q", y=y,
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                 alt.Tooltip("float:Q", format=".2f", title="independent float °C")])
    return alt.layer(band_layer, mean_layer, float_layer).properties(
        height=560, title="model profile (line) + ±2σ (band) vs independent Argo float (points)")


def _point_map(lat: float, lon: float, mlat=None, mlon=None) -> alt.Chart:
    pts = [{"lat": lat, "lon": lon, "what": "your point"}]
    if mlat is not None:
        pts.append({"lat": mlat, "lon": mlon, "what": "matched float"})
    df = pd.DataFrame(pts)
    return alt.Chart(df).mark_point(size=140, filled=True).encode(
        x=alt.X("lon:Q", title="longitude (°E)",
                scale=alt.Scale(domain=[config.REGION["lon_min"], config.REGION["lon_max"]])),
        y=alt.Y("lat:Q", title="latitude (°N)",
                scale=alt.Scale(domain=[config.REGION["lat_min"], config.REGION["lat_max"]])),
        color=alt.Color("what:N", title=None),
        shape=alt.Shape("what:N", title=None),
        tooltip=["what", alt.Tooltip("lat:Q", format=".2f"), alt.Tooltip("lon:Q", format=".2f")],
    ).properties(height=280, title="where this profile is")


def main() -> None:
    st.title("Validate Live — trust the float, not us")
    st.caption("Pick a point. The **frozen** model reconstructs its profile; a real, **independent** "
               "Argo float from nearby lands on top, with the per-depth error shown live. The float "
               "was never used for training — this is the model meeting ground truth in front of you.")

    with st.sidebar:
        st.header("Point")
        lat = st.number_input("Latitude (°N)", min_value=float(config.REGION["lat_min"]),
                              max_value=float(config.REGION["lat_max"]), value=15.0, step=0.25)
        lon = st.number_input("Longitude (°E)", min_value=float(config.REGION["lon_min"]),
                              max_value=float(config.REGION["lon_max"]), value=68.0, step=0.25)
        date = st.date_input("Date", value=pd.Timestamp("2026-05-15"),
                             min_value=pd.Timestamp("2025-06-01"),
                             max_value=pd.Timestamp("2026-06-23"))
        k = st.slider("Nearby floats to offer", 1, 5, 5,
                      help="The nearest is shown by default; pick another from the list below.")
        st.caption("The model snaps to the nearest available date and reports the offset.")

    try:
        result = run_overlay(float(lat), float(lon), str(date), int(k), _v2_version())
    except FileNotFoundError as e:
        st.error("The satellite bundle isn't on this machine, so the live model can't run here. "
                 "This page runs where `data/processed/daily_sat/v001` exists (the training box).")
        st.caption(f"Details: {e}")
        return
    except Exception as e:                          # never blank the page on a demo
        st.error(f"Could not produce an overlay: {type(e).__name__}: {e}")
        return

    pred = result["prediction"]
    if pred.get("forecast"):
        st.warning("This date is a **forecast** — beyond the last date with ground truth, so no "
                   "float comparison exists to show. Pick a date on or before 2026-06-23.")

    if not result["has_float"]:
        left, right = st.columns([3, 2])
        with left:
            st.altair_chart(_point_map(float(lat), float(lon)), use_container_width=True)
        with right:
            st.info("**No independent float within the search window** of this point and date. "
                    "Nothing is drawn rather than a fabricated profile — try a point in the open "
                    "Arabian Sea or Bay of Bengal, or a nearby date.")
        return

    # Which nearby float — nearest by default, user may switch.
    labels = [f"{m['spatial_offset_km']:.0f} km / {int(m['temporal_offset_days']):+d} d  "
              f"({m['latitude']:.2f}, {m['longitude']:.2f}), {m['n_levels']} levels"
              for m in result["matches"]]
    idx = st.selectbox("Nearby independent float", range(len(labels)),
                       format_func=lambda i: labels[i], index=0)
    match = result["matches"][idx]
    cmp = result["comparisons"][idx]

    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(
            _overlay_chart(pred["depths_m"], pred["mean"], pred["band_2sigma"],
                           match["temperature_profile"]),
            use_container_width=True)
        st.caption(f"Float **{match['latitude']:.2f}, {match['longitude']:.2f}** on "
                   f"**{match['datetime']}** — {match['spatial_offset_km']:.0f} km and "
                   f"{int(match['temporal_offset_days']):+d} days from your point. "
                   "Band is the model's **calibrated ±2σ**; the PS-deliverable uncertainty envelope.")
    with right:
        st.altair_chart(_point_map(float(lat), float(lon),
                                   match["latitude"], match["longitude"]),
                        use_container_width=True)
        c = st.columns(2)
        c[0].metric("profile RMSE", "—" if cmp["rmse"] is None else f"{cmp['rmse']:.3f} °C")
        c[1].metric("bias (model − float)", "—" if cmp["bias"] is None else f"{cmp['bias']:+.3f} °C")
        st.caption(f"Compared at **{cmp['n_levels_compared']}** depths the float actually sampled"
                   + (f" ({cmp['overlap_depth_range_m'][0]:.0f}–{cmp['overlap_depth_range_m'][1]:.0f} m)."
                      if cmp["overlap_depth_range_m"] else ".")
                   + " Never extrapolated past the float's deepest level.")

    with st.expander("Per-depth detail"):
        table = pd.DataFrame({
            "depth (m)": pred["depths_m"],
            "model (°C)": pred["mean"],
            "float (°C)": match["temperature_profile"],
            "error (model − float, °C)": cmp["per_depth_error"],
        })
        st.dataframe(table, use_container_width=True, hide_index=True)

    with st.expander("Provenance — what produced this prediction"):
        st.json(pred.get("provenance"))


if __name__ == "__main__":
    main()
