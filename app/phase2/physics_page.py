"""F5 -- ocean structure: mixed layer, barrier layer, thermocline, heat content.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/physics_page.py --server.port 8505

All science lives in `phase2.physics`. This file only lays it out — if a number appears here that
the library did not compute, that is a bug.

Charts are altair, which ships with Streamlit. `app/panels/_viz.py` records why that matters:
a panel that ImportErrors on demo day is worse than a plainer chart.
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
from phase2.physics import layers, ohc  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Ocean structure", layout="wide")

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SUBSURFACE = os.path.join(config.DATA_PROCESSED, "subsurface.npz")

#: The two boxes the validated seasonal claim is made over. Stated here rather than buried,
#: because Unit B and Unit A used DIFFERENT boxes and got different magnitudes for the same
#: (correct) conclusion — so the box definition is part of the result.
BOB = {"name": "Bay of Bengal", "lat": (15.0, 22.0), "lon": (85.0, 95.0)}
ARABIAN = {"name": "Arabian Sea", "lat": (10.0, 22.0), "lon": (60.0, 72.0)}


@st.cache_data(show_spinner="Loading the ocean …")
def load():
    g = np.load(GRIDS, allow_pickle=True)
    s = np.load(SUBSURFACE, allow_pickle=True)
    return (np.asarray(g["temp"], "float64"), np.asarray(s["salinity"], "float64"),
            np.asarray(g["times"]).astype("datetime64[D]"),
            np.asarray(g["land_mask"], bool))


@st.cache_data(show_spinner="Computing layers …")
def layer_fields(k: int):
    theta, sal, _, land = load()
    t, sa = theta[k], sal[k]
    mld = layers.mixed_layer_depth(sa, t)
    ild = layers.isothermal_layer_depth(t)
    blt = layers.barrier_layer_thickness(sa, t)
    th = layers.thermocline(t)
    heat = ohc.ohc(sa, t, 300.0)
    out = {"MLD (density, m)": mld, "Thermocline depth (m)": th["depth"],
           "Barrier layer (m)": blt, "OHC 0–300 m (GJ/m²)": heat,
           "ILD (temperature, m)": ild}
    return {k2: np.where(land, np.nan, v) for k2, v in out.items()}


@st.cache_data(show_spinner="Measuring the seasonal cycle …")
def barrier_by_month():
    """The validated F5 claim, measured across ALL months.

    Unit B's lesson, learned the hard way: a SINGLE DATE inverts this signal. The Bay of Bengal
    barrier layer peaks in March and through the monsoon and collapses in winter, so December
    alone shows the Arabian Sea thicker and looks like a refutation.
    """
    theta, sal, times, land = load()
    blt = layers.barrier_layer_thickness(sal, theta)
    lat, lon = np.asarray(config.LAT), np.asarray(config.LON)
    months = np.array([int(str(t)[5:7]) for t in times])
    rows = []
    for box in (BOB, ARABIAN):
        i = (lat >= box["lat"][0]) & (lat <= box["lat"][1])
        j = (lon >= box["lon"][0]) & (lon <= box["lon"][1])
        for m in range(1, 13):
            sel = blt[months == m][:, i][:, :, j]
            rows.append({"month": m, "box": box["name"],
                         "thickness_m": float(np.nanmean(sel))})
    return pd.DataFrame(rows)


def _map(field: np.ndarray, title: str, scheme: str = "viridis", reverse: bool = False):
    lat, lon = np.asarray(config.LAT), np.asarray(config.LON)
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "value": field.ravel()}).dropna(subset=["value"])
    return alt.Chart(df).mark_rect().encode(
        x=alt.X("lon:O", title="longitude (°E)", axis=alt.Axis(values=list(range(45, 106, 10)))),
        y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                axis=alt.Axis(values=list(range(5, 31, 5)))),
        color=alt.Color("value:Q", title=None,
                        scale=alt.Scale(scheme=scheme, reverse=reverse)),
        tooltip=["lat", "lon", alt.Tooltip("value:Q", format=".1f")],
    ).properties(height=300, title=title)


def main() -> None:
    st.title("Ocean structure")
    st.caption("Mixed layer, barrier layer, thermocline and heat content — computed from **real "
               "seawater density** ρ(S, θ), not an assumed constant.")

    if not (os.path.exists(GRIDS) and os.path.exists(SUBSURFACE)):
        st.error(f"Needs {GRIDS} and {SUBSURFACE}. Both are gitignored and ship in the data "
                 "bundle.")
        st.stop()
        return

    _, _, times, _ = load()
    with st.sidebar:
        st.header("Snapshot")
        idx = st.selectbox("Date", range(len(times)),
                           format_func=lambda i: str(times[i]), index=len(times) - 6)
        st.divider()
        st.caption("Profile inspector")
        p_lat = st.slider("Latitude (°N)", float(config.LAT[0]), float(config.LAT[-1]), 18.0, 0.25)
        p_lon = st.slider("Longitude (°E)", float(config.LON[0]), float(config.LON[-1]), 88.0, 0.25)

    fields = layer_fields(idx)

    # ---- 1. the maps -------------------------------------------------------------------
    st.subheader("1 · Structure across the basin")
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(_map(fields["MLD (density, m)"], "Mixed layer depth (m) — density "
                             "criterion", "blues"), use_container_width=True)
    with c2:
        st.altair_chart(_map(fields["Thermocline depth (m)"], "Thermocline depth (m)", "plasma"),
                        use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        st.altair_chart(_map(fields["Barrier layer (m)"], "Barrier layer thickness (m)", "purples"),
                        use_container_width=True)
    with c4:
        st.altair_chart(_map(fields["OHC 0–300 m (GJ/m²)"], "Ocean heat content 0–300 m (GJ/m²)",
                             "inferno"), use_container_width=True)

    st.info(
        "**The mixed layer uses the DENSITY criterion** (de Boyer Montégut et al. 2004, "
        "0.03 kg/m³ from 10 m), not temperature. The two disagree wherever salinity sets the "
        "stratification — and **their difference IS the barrier layer**. A temperature-only MLD "
        "is systematically too deep in the northern Bay of Bengal, by ≥ 50 m on a realistic "
        "river-plume profile: the cyclone-genesis region, and the cell our priority map ranks "
        "first."
    )

    # ---- 2. the profile ----------------------------------------------------------------
    st.subheader("2 · One column")
    theta, sal, _, land = load()
    i = int(np.argmin(np.abs(np.asarray(config.LAT) - p_lat)))
    j = int(np.argmin(np.abs(np.asarray(config.LON) - p_lon)))
    if land[i, j]:
        st.warning(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E is land.")
    else:
        t_col, s_col = theta[idx, i, j], sal[idx, i, j]
        prof = pd.DataFrame({"depth": config.DEPTHS, "temperature": t_col, "salinity": s_col})
        mld = float(fields["MLD (density, m)"][i, j])
        ild = float(fields["ILD (temperature, m)"][i, j])
        thd = float(fields["Thermocline depth (m)"][i, j])

        base = alt.Chart(prof).mark_line(point=True).encode(
            y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)))
        t_line = base.encode(x=alt.X("temperature:Q", title="temperature (°C)"),
                             tooltip=["depth", "temperature"]).properties(height=380)
        s_line = base.mark_line(point=True, color="#8c6bb1").encode(
            x=alt.X("salinity:Q", title="salinity (psu)"),
            tooltip=["depth", "salinity"]).properties(height=380)

        marks = alt.Chart(pd.DataFrame({
            "depth": [mld, ild, thd],
            "layer": ["MLD (density)", "ILD (temperature)", "thermocline"],
        })).mark_rule(strokeDash=[5, 3]).encode(
            y="depth:Q", color=alt.Color("layer:N", title=None),
            tooltip=["layer", alt.Tooltip("depth:Q", format=".0f")])

        st.altair_chart(alt.hconcat(t_line + marks, s_line + marks), use_container_width=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("MLD (density)", f"{mld:.0f} m")
        m2.metric("ILD (temperature)", f"{ild:.0f} m")
        m3.metric("Barrier layer", f"{ild - mld:.0f} m")
        m4.metric("Thermocline", f"{thd:.0f} m")
        st.caption(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E on {times[idx]}. "
                   "Barrier layer = ILD − MLD: the layer that is isothermal but **not** "
                   "isopycnal, because fresh water is holding it apart.")

    # ---- 3. the validated claim --------------------------------------------------------
    st.subheader("3 · The barrier layer is seasonal — and that is the result")
    df = barrier_by_month()
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("month:O", title="month"),
        y=alt.Y("thickness_m:Q", title="mean barrier layer (m)"),
        color=alt.Color("box:N", title=None,
                        scale=alt.Scale(range=["#4a1486", "#9ecae1"])),
        xOffset="box:N",
        tooltip=["month", "box", alt.Tooltip("thickness_m:Q", format=".1f")],
    ).properties(height=320)
    st.altair_chart(chart, use_container_width=True)

    piv = df.pivot(index="month", columns="box", values="thickness_m")
    bob_wins = int((piv[BOB["name"]] > piv[ARABIAN["name"]]).sum())
    a, b = st.columns(2)
    a.metric(f"{BOB['name']} annual mean", f"{piv[BOB['name']].mean():.1f} m")
    b.metric(f"{ARABIAN['name']} annual mean", f"{piv[ARABIAN['name']].mean():.1f} m")
    st.warning(
        f"**A single date inverts this signal — measure across months.** The Bay of Bengal is "
        f"thicker in **{bob_wins} of 12** months, peaking in March and through the monsoon with "
        f"river discharge, and collapsing in winter when cooling deepens the mixed layer. Unit B "
        f"first checked one December date, got the opposite answer, and nearly reported a false "
        f"failure. Boxes: BoB {BOB['lat'][0]:.0f}–{BOB['lat'][1]:.0f}°N "
        f"{BOB['lon'][0]:.0f}–{BOB['lon'][1]:.0f}°E, Arabian "
        f"{ARABIAN['lat'][0]:.0f}–{ARABIAN['lat'][1]:.0f}°N "
        f"{ARABIAN['lon'][0]:.0f}–{ARABIAN['lon'][1]:.0f}°E — the two units used different boxes "
        f"and got different magnitudes for the same conclusion, so the box is part of the result."
    )

    with st.expander("What this is NOT"):
        st.markdown(
            "- **Not a validated OHC in absolute terms.** The density is real ρ(S, θ); the "
            "integral still assumes a constant specific heat capacity.\n"
            "- **The barrier layer is a derived quantity**, not an observation. It is ILD − MLD, "
            "so it inherits every assumption in both criteria.\n"
            "- **Monthly fields.** No event, no storm response, no daily variability."
        )


if __name__ == "__main__":
    main()
