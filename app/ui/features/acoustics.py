"""How far sound carries, and where it bends.

OWNER: Unit A (Arjhun). NOT a page.

Sound speed in sea water is dominated by TEMPERATURE, so a temperature model is, with one honest
caveat, an acoustics model. This is the feature that shows the reconstruction being used for
something it was never explicitly trained to do.

TWO THINGS THIS PANEL REFUSES TO HIDE

1. THE SALINITY IS NOT OURS. Stage 1 predicts temperature only. Sound speed needs salinity too,
   so the companion salinity comes from the GLORYS bundle on the same dates -- gridded, real, and
   NOT a model output. The panel says so on screen rather than letting a reader assume the whole
   field was reconstructed.

2. THE SOFAR AXIS IS USUALLY BELOW OUR GRID. The deep sound channel typically sits between 1000
   and 2000 m; this model stops at 1000 m. Over most of the basin the axis therefore cannot be
   resolved, and the map is left BLANK there rather than extrapolated. The resolved fraction is
   printed, because a mostly-blank map needs to explain itself.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from phase2.derived import acoustics as A
from phase2.derived import mapframe as MF

from app.ui import data as D
from app.ui import maps, theme, ux

VIEWS = {"sld": "Sonic layer depth", "sofar": "SOFAR axis"}


@st.cache_data(show_spinner=False)
def _salinity(date_str: str, version: str):
    """GLORYS salinity on the same date, from the bundle. NOT a model output."""
    pred = D._predictor(1, version)
    data = getattr(pred, "data", None)
    if data is None or "salinity" not in data:
        return None
    times = np.asarray(data["times"]).astype("datetime64[D]")
    hits = np.nonzero(times == np.datetime64(str(date_str)[:10]))[0]
    if not hits.size:
        return None
    return np.asarray(data["salinity"][int(hits[0])], dtype="float64")


def render(ctx) -> None:
    c = st.columns([2.4, 2.2, 2.4], vertical_alignment="bottom")
    with c[0]:
        with ux.control("soundmap", ratio=(5, 2)):
            view = st.segmented_control("Layer", list(VIEWS), default="sld",
                                        format_func=lambda k: VIEWS[k],
                                        key="ac_view") or "sld"
    with c[1]:
        ux.explain("soundspeed", label="Why temperature decides this")
    with c[2]:
        ux.explain("soundlimit", label="Why much of the map is blank")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)
    sal = _salinity(ctx.date, ctx.version)
    if sal is None:
        st.error("No companion salinity for this date in the bundle, so sound speed cannot be "
                 "computed. It is never assumed to be a constant — that would invent a field.")
        return

    st.info("**Temperature is reconstructed by the model; salinity is GLORYS observation on the "
            "same date.** Sound speed needs both, and stage 1 predicts temperature only.",
            icon=":material/science:")

    theta = np.asarray(f["temperature"], dtype="float64")
    lm = A.layer_maps(sal, theta)
    layer = lm[view]
    depth2d = np.asarray(layer["depth"], dtype="float64")
    reason = np.asarray(layer["reason"])

    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        fr = maps.frame(depth2d, f["land_mask"], lat, lon)
        st.altair_chart(maps.clickable(fr, units="depth (m)", key="ac_map",
                                       scheme="viridis", width=880),
                        key="ac_map", on_select="rerun")
        counts = layer.get("counts") or {}
        resolved = int(counts.get(A.OK, 0))
        total = int(np.isfinite(depth2d).size)
        ocean = int((~np.asarray(f["land_mask"], dtype=bool)).sum())
        st.caption(
            f"**{resolved:,} of {ocean:,} ocean cells resolved** "
            f"({100.0 * resolved / max(ocean, 1):.1f}%). "
            + " · ".join(f"{layer['reason_meanings'].get(k, k)}: {v:,}"
                         for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v))

    with right:
        picked = maps.selected_cell(st.session_state.get("ac_map"))
        if picked is None:
            st.info("Click a cell to see its sound-speed profile.", icon=":material/touch_app:")
        else:
            plat, plon = picked
            i = int(np.argmin(np.abs(lat - plat)))
            j = int(np.argmin(np.abs(lon - plon)))
            pr = A.profile(sal[i, j, :], theta[i, j, :])
            cprof = np.asarray(pr["sound_speed"], dtype="float64")
            st.markdown(f"**{plat:.2f}°N  {plon:.2f}°E**")
            if not np.isfinite(cprof).any():
                st.warning("No water column here.", icon=":material/block:")
            else:
                df = pd.DataFrame({"depth": list(D.DEPTHS), "c": cprof}).dropna()
                st.altair_chart(
                    alt.Chart(df).mark_line(point=True, color=theme.CYAN, strokeWidth=2).encode(
                        x=alt.X("c:Q", title="sound speed (m s⁻¹)",
                                scale=alt.Scale(zero=False, nice=True)),
                        y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
                        tooltip=[alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                                 alt.Tooltip("c:Q", format=".1f", title="m s⁻¹")],
                    ).properties(height=360), use_container_width=True)
                ux.tiles([("SURFACE", f"{cprof[0]:.1f}", "m s⁻¹"),
                          ("RANGE", f"{np.nanmax(cprof) - np.nanmin(cprof):.1f}", "m s⁻¹",
                           "top to bottom")])

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"c = 1448.96 + 4.591t - 5.304{\times}10^{-2}t^{2} + 2.374{\times}10^{-4}t^{3}"
        r" + 1.340(S-35) + 1.630{\times}10^{-2}D + 1.675{\times}10^{-7}D^{2}"
        r" - 1.025{\times}10^{-2}t(S-35) - 7.139{\times}10^{-13}tD^{3}",
        [("c", "speed of sound in sea water", "m s⁻¹", "Mackenzie 1981, 9-term"),
         ("t", "temperature — the dominant term by far", "°C",
          "reconstructed by the model"),
         ("S", "salinity", "PSU", "GLORYS bundle, NOT a model output"),
         ("D", "depth", "m", "oceanembed.config.DEPTHS"),
         ("SLD", "sonic layer depth: the near-surface sound-speed maximum", "m",
          "acoustics.sonic_layer_depth"),
         ("SOFAR", "the sound-speed minimum below it — where sound travels furthest", "m",
          "acoustics.sofar_axis")],
        "Checked against the published value c(S=35, θ=25, D=1000) = 1550.744 m s⁻¹. Mackenzie "
        "expects in-situ temperature while the bundle supplies potential temperature — about "
        "0.4 m s⁻¹ of error, stated rather than silently absorbed.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("Where sound is trapped and where it escapes. The sonic layer is a near-surface "
              "duct; below it sound bends downward and a shadow zone opens where a surface sonar "
              "cannot hear."),
        conclude=("A deep sonic layer means a surface vessel detects further. A shallow one means "
                  "a target just beneath the duct is acoustically hidden. This is derived from "
                  "satellite-observable inputs alone, with no in-water survey."),
        limits=[
            ("Salinity is GLORYS, not reconstructed. Only the temperature here is this project's "
             "output.", "predictor.data['salinity'] — the daily bundle"),
            ("The SOFAR axis usually lies between 1000 and 2000 m and this grid stops at 1000 m, "
             "so over most of the basin it cannot be resolved and is left blank.",
             "src/phase2/derived/acoustics.py SOFAR_MIN_COLUMN_M"),
            ("Mackenzie's polynomial is valid for 0–30 °C and 30–40 PSU. Roughly a sixth of "
             "surface cells fall outside that envelope, mostly the very fresh Bay of Bengal.",
             "src/phase2/physics/seawater.py sound_speed_in_range"),
            ("Sound speed is computed from a reconstruction, so it inherits the reconstruction's "
             "error before any acoustic modelling begins.", "artifacts/frozen_manifest.json"),
        ])
