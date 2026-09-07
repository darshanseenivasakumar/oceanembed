"""Subsurface Marine Heatwave Detector -- Streamlit page.

OWNER: Unit A (Arjhun / MHW feature). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/mhw_page.py --server.port 8518

WHAT THIS SHOWS
1. Where heatwaves are, at any depth, in the 2025-26 GLORYS truth -- including SUBSURFACE ones a
   satellite SST map cannot see.
2. How well the reconstruction AGREES with the truth about heatwaves, per depth (the honest headline,
   from artifacts/mhw_comparison.json -- robust to the baseline warming bias because model and truth
   share one threshold).

Every number's provenance is shown, and the two honest caveats (GLORYS-input leg, monthly pilot
baseline) are stated at the top, not buried.
"""
from __future__ import annotations

import json
import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config  # noqa: E402
from phase2.derived import mhw_baseline as mb  # noqa: E402
from phase2.derived import mhw_field as mf  # noqa: E402
from phase2 import viz_explainer  # noqa: E402

alt.data_transformers.disable_max_rows()   # the basin map is ~24k cells (> Altair's 5000 default)
st.set_page_config(page_title="OceanEmbed — Subsurface Heatwave Detector", layout="wide")

COMPARISON_JSON = os.path.join(config.ARTIFACTS, "mhw_comparison.json")


@st.cache_data(show_spinner=False)
def load_comparison() -> dict | None:
    """The per-depth model-vs-GLORYS skill table, or None if it has not been produced yet."""
    if not os.path.exists(COMPARISON_JSON):
        return None
    with open(COMPARISON_JSON, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=True)
def truth_mhw_fraction(depth_m: int) -> np.ndarray:
    """Fraction of the 2025-26 window each ocean cell spent inside a heatwave, at one depth, in the
    GLORYS truth. Uses the monthly pilot baseline (grids.npz). Cached per depth (~6 s first call)."""
    d25 = np.load(os.path.join(config.DATA_PROCESSED, "daily", "2025.npz"), allow_pickle=True)
    d26 = np.load(os.path.join(config.DATA_PROCESSED, "daily", "2026.npz"), allow_pickle=True)
    z = list(config.DEPTHS).index(depth_m)
    temp = np.concatenate([d25["temp"], d26["temp"]], axis=0)[:, :, :, z].astype("float64")
    times = np.concatenate([d25["times"], d26["times"]])
    land = d25["land_mask"]

    g = np.load(os.path.join(config.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    _, thr12 = mb.monthly_climatology_threshold(g["temp"][:, :, :, z], g["times"], pct=mb.PERCENTILE)
    clm12, _ = mb.monthly_climatology_threshold(g["temp"][:, :, :, z], g["times"], pct=mb.PERCENTILE)
    thr = mb.map_monthly_to_series(thr12, times)
    clm = mb.map_monthly_to_series(clm12, times)

    flags = mf.mhw_day_flags_grid(temp, clm, thr, land)   # (N, lat, lon) bool
    frac = flags.mean(axis=0)                              # fraction of days in a heatwave
    frac[land] = np.nan
    return frac


def _map_frame(frac: np.ndarray) -> pd.DataFrame:
    lat = np.asarray(config.LAT); lon = np.asarray(config.LON)
    LO, LA = np.meshgrid(lon, lat)
    df = pd.DataFrame({"lat": LA.ravel(), "lon": LO.ravel(), "frac": frac.ravel()})
    return df.dropna(subset=["frac"])


def _skill_frame(cmp: dict) -> pd.DataFrame:
    rows = []
    for depth, c in cmp["per_depth"].items():
        for metric in ("pod", "csi", "far"):
            v = c.get(metric)
            if v is not None:
                rows.append({"depth": int(depth), "metric": metric.upper(), "value": v})
    return pd.DataFrame(rows)


def main() -> None:
    st.title("Subsurface Marine Heatwave Detector")
    st.caption("A heatwave the ocean hides: warmer than the 90th percentile of normal for the time "
               "of year, for 5+ days — often with **no surface signature at all**.")

    cmp = load_comparison()
    if cmp is None:
        st.info("The model-vs-GLORYS comparison has not been produced yet. Run "
                "`python scripts/phase2/run_mhw_comparison.py`. The map below still works.")
    else:
        # honest provenance banner -- stated, never buried
        st.warning(f"**Leg:** {cmp['model_leg']}\n\n**Baseline:** {cmp['baseline']}\n\n"
                   f"**Window:** {cmp['window'][0]} … {cmp['window'][1]} ({cmp['n_days']} days)")

    # ---- 1 · where the heatwaves are ---------------------------------------------------
    st.subheader("1 · Where heatwaves sit in the water column")
    depth_m = st.selectbox("Depth (m)", list(config.DEPTHS), index=list(config.DEPTHS).index(100))
    frac = truth_mhw_fraction(int(depth_m))
    dfm = _map_frame(frac)
    chart = alt.Chart(dfm).mark_rect().encode(
        x=alt.X("lon:Q", title="longitude", scale=alt.Scale(domain=[config.LON[0], config.LON[-1]])),
        y=alt.Y("lat:Q", title="latitude", scale=alt.Scale(domain=[config.LAT[0], config.LAT[-1]])),
        color=alt.Color("frac:Q", title="fraction of days in a heatwave",
                        scale=alt.Scale(scheme="inferno")),
        tooltip=[alt.Tooltip("lat:Q", format=".2f"), alt.Tooltip("lon:Q", format=".2f"),
                 alt.Tooltip("frac:Q", format=".2f")],
    ).properties(height=430)
    st.altair_chart(chart, use_container_width=True)
    st.caption(f"GLORYS truth at {depth_m} m, 2025-06 … 2026-06. Bright = more days in a heatwave. "
               "Absolute fractions are inflated by the pilot baseline's warming bias — read the "
               "PATTERN (where), not the level.")

    # ---- 2 · does the model agree with the truth? --------------------------------------
    if cmp is not None:
        st.divider()
        st.subheader("2 · Can the model SEE these heatwaves? (agreement with the truth, per depth)")
        sk = _skill_frame(cmp)
        line = alt.Chart(sk).mark_line(point=True).encode(
            x=alt.X("value:Q", title="skill (higher = better)", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
            color=alt.Color("metric:N", title=None),
            tooltip=["depth", "metric", alt.Tooltip("value:Q", format=".3f")],
        ).properties(height=430)
        st.altair_chart(line, use_container_width=True)
        st.caption("POD = probability of detection (caught a real heatwave). CSI = overall success. "
                   "FAR = false-alarm ratio (lower better). This agreement is robust to the baseline "
                   "bias because model and truth are scored against the SAME threshold.")

    # ---- explainer footer ---------------------------------------------------------------
    viz_explainer.render_explainer(
        st,
        title="the marine-heatwave definition",
        formula=r"T(x,y,z,t) > T_{90}(x,y,z,\mathrm{doy}(t))\ \ \text{for}\ \geq 5\ \text{consecutive days}",
        plain="A marine heatwave is not just warm water — it is water hotter than the top 10% of what "
              "is normal for **this time of year at this depth**, staying that hot for at least 5 days "
              "in a row. Because we reconstruct the full water column, we can find heatwaves at depth "
              "that leave no trace on the sea-surface temperature a satellite measures directly.",
        how_to_read="On the map, bright regions spend more of the year in a heatwave. In the skill "
                    "chart, a high POD/CSI at a depth means the reconstruction reliably catches the "
                    "heatwaves the truth shows there.",
        caveats=[
            "Runs the GLORYS-input reconstruction (the satellite-input bundle is on another machine), "
            "so this measures reconstruction fidelity given reanalysis inputs, not the satellite deliverable.",
            "Baseline is a MONTHLY pilot (2019-2022), not a 30-year day-of-year climatology, so absolute "
            "heatwave counts are inflated by ocean warming between the baseline and 2025-26. The "
            "model-vs-truth AGREEMENT is unaffected; the absolute map level is.",
            "Continental-shelf (<200 m) cells are where the reconstruction is weakest (Argo cannot train "
            "there), so shelf heatwaves are the least certain.",
        ],
    )


if __name__ == "__main__":
    main()
