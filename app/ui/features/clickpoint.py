"""Click any pixel of the sea; get the whole column beneath it.

OWNER: Unit A (Arjhun). NOT a page.

This is the feature that turns a picture into an instrument. Everything else on the dashboard
shows what the model produced; this one lets a judge interrogate it at a point of their choosing,
which is a different and much harder thing to fake.

LAND IS CLICKABLE ON PURPOSE. A cell with no water returns "there is no water here", not silence.
An absence is a real answer and the map should be able to give it -- see maps.py trap 2.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from phase2.derived import mapframe as MF

from app.ui import data as D
from app.ui import maps, theme, ux


def _profile_chart(depths, temp, sigma, calibrated: bool):
    df = pd.DataFrame({"depth": depths, "t": temp, "lo": temp - sigma, "hi": temp + sigma})
    df = df.dropna(subset=["t"])
    if df.empty:
        return None
    pad = max(0.4, float(np.nanmax(df.hi) - np.nanmin(df.lo)) * 0.08)
    dom = [float(np.nanmin(df.lo)) - pad, float(np.nanmax(df.hi)) + pad]

    base = alt.Chart(df)
    # zero=False and an explicit domain: mark_area otherwise forces a zero baseline and the
    # +/-1 sigma band becomes an invisible sliver against a 0..30 degC axis.
    band = base.mark_area(opacity=0.22, color=theme.CYAN).encode(
        x=alt.X("lo:Q", title="temperature (°C)",
                scale=alt.Scale(domain=dom, zero=False, nice=False)),
        x2="hi:Q",
        y=alt.Y("depth:Q", title="depth (m)",
                scale=alt.Scale(reverse=True, zero=True)))
    line = base.mark_line(point=True, color=theme.CYAN, strokeWidth=2).encode(
        x=alt.X("t:Q", scale=alt.Scale(domain=dom, zero=False, nice=False)),
        y=alt.Y("depth:Q", scale=alt.Scale(reverse=True, zero=True)),
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)", format=".0f"),
                 alt.Tooltip("t:Q", title="°C", format=".2f"),
                 alt.Tooltip("lo:Q", title="−1σ", format=".2f"),
                 alt.Tooltip("hi:Q", title="+1σ", format=".2f")])
    return (band + line).properties(height=430)


def render(ctx) -> None:
    c = st.columns([2.2, 3.6], vertical_alignment="bottom")
    with c[0]:
        with ux.control("depth", ratio=(5, 2)):
            level = st.select_slider("Depth (m)", options=D.DEPTHS, value=100, key="cp_depth")
    with c[1]:
        ux.explain("clickmap", label="How to read this map")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)

    k = MF.nearest_level(D.DEPTHS, level)
    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")
    fr = maps.frame(f["temperature"][:, :, k], f["land_mask"], lat, lon,
                    extra={"sigma": f["sigma"][:, :, k]})

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        chart = maps.clickable(fr, units="°C", key="cp_map", scheme="turbo", width=880,
                               tooltip_extra=(("sigma", "±1σ (°C)"),))
        st.altair_chart(chart, key="cp_map", on_select="rerun")
        n = MF.counts(fr)
        st.caption(f"{D.DEPTHS[k]:.0f} m · {n.get('water', 0):,} water cells · "
                   f"{n.get('below the seafloor', 0):,} below the sea floor · "
                   f"{n.get('land', 0):,} land")

    with right:
        picked = maps.selected_cell(st.session_state.get("cp_map"))
        if picked is None:
            st.info("Click any cell on the map to pull the full column beneath it.",
                    icon=":material/touch_app:")
            return
        plat, plon = picked
        i, j = int(np.argmin(np.abs(lat - plat))), int(np.argmin(np.abs(lon - plon)))
        kind = str(fr["kind"][i * len(lon) + j])

        st.markdown(f"**{plat:.2f}°N  {plon:.2f}°E**")
        if kind != MF.WATER:
            st.warning(MF.KIND_NOTE[kind].format(depth=f"{D.DEPTHS[k]:.0f} m"),
                       icon=":material/block:")
            return

        temp = np.asarray(f["temperature"][i, j, :], dtype="float64")
        sig = np.asarray(f["sigma"][i, j, :], dtype="float64")
        ch = _profile_chart(D.DEPTHS, temp, sig, True)
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)

        deepest = np.max(np.asarray(D.DEPTHS)[np.isfinite(temp)]) if np.isfinite(temp).any() else 0
        ux.tiles([("SURFACE", f"{temp[0]:.2f}", "°C"),
                  ("AT 100 m", f"{temp[MF.nearest_level(D.DEPTHS, 100)]:.2f}", "°C"),
                  ("WATER TO", f"{deepest:.0f}", "m")])

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\hat{T}(z),\ \hat{\sigma}(z) \;=\; f_\theta\big(\mathbf{S}_{t-10:t}\big),"
        r"\qquad z \in \{0,10,\dots,1000\}\ \mathrm{m}",
        [("S", "an 11-day stack of surface maps: SST, SSS, SSH, u, v and wind stress", "—",
          "satellite observations"),
         ("t−10:t", "the 11-day window ending on the chosen date", "days",
          "T_SEQ=11, chosen by ablation"),
         ("T̂(z)", "reconstructed temperature at each of 15 depths", "°C", "model output"),
         ("σ̂(z)", "the model's own uncertainty at that depth", "°C", "model output"),
         ("θ", "network weights, frozen after training", "—",
          "artifacts/tscast_stage1_sat_7ch_s42.pt")],
        "The shaded band is ±1σ. It widens at the thermocline because that is where temperature "
        "changes fastest with depth.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("One column of ocean, inferred from the surface alone. Warm water near the top, a "
              "sharp drop through the thermocline, then cold and nearly constant below."),
        conclude=("Where the band is narrow the model is confident and the number can be used. "
                  "Where it is wide — usually 100–150 m — treat the value as indicative and lean "
                  "on the shape of the profile rather than any single depth."),
        limits=[
            ("The error bars come from the model's own estimate, corrected afterwards against "
             "floats. After correction ±2σ covers 80–96 % of real measurements, not 95 %.",
             "artifacts/uncertainty_calibration.json"),
            ("The model runs about +0.10 °C warm across the basin. Measured, not corrected — the "
             "shipped checkpoint is frozen.", "artifacts/frozen_manifest.json overall_bias"),
            ("Nothing below 1000 m is modelled. A column ending early is the sea floor.",
             "oceanembed.config.DEPTHS"),
        ])
