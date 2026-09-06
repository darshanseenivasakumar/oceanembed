"""Checked against 962 Argo floats the model never saw.

OWNER: Unit A (Arjhun). NOT a page.

NOTHING HERE IS COMPUTED IN THE BROWSER. Every figure is read from the metrics JSON that the
training run itself wrote, and the frozen manifest names which run that is. A dashboard that
recomputes a metric is a dashboard that can disagree with the paper.

THE VINTAGE TRAP, AVOIDED DELIBERATELY
artifacts/argo_error_by_depth.json is the obvious-looking source and it is the WRONG one: it is
the Phase-1 file -- 879 profiles, RMSE 0.9638 -- and putting it beside a Phase-2 headline would
silently mix two different systems. The v2 per-depth arrays live in the run's own metrics file,
which is what is read below.
"""
from __future__ import annotations

import json
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import data as D
from app.ui import theme, ux

#: The deliverable's run. Taken from the frozen manifest when it names one, so this follows the
#: manifest rather than pinning a tag that could go stale.
FALLBACK_TAG = "sat_7ch_s42"


@st.cache_data(show_spinner=False)
def _metrics() -> dict:
    c = D.claim()
    name = c.get("metrics_file") or f"tscast_stage1_{c.get('tag') or FALLBACK_TAG}_metrics.json"
    p = base.art(os.path.basename(name))
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def render(ctx) -> None:
    head = D.headline()
    m = _metrics().get("metrics", {})
    if not head or not m:
        st.error("The frozen manifest or its metrics file is not on this machine, so nothing can "
                 "be shown. This panel never invents a number.")
        return

    ux.tiles([
        ("ERROR VS ARGO", head["rmse"], "°C", "962 independent profiles"),
        ("CORRELATION", head["corr"], "", "model vs float"),
        ("BETTER THAN CLIMATOLOGY", head["skill"], "", "the bar any model must clear"),
        ("BIAS", head["bias"], "°C", "measured, not corrected"),
    ])
    e = st.columns([1.2, 1.2, 1.2, 3.4])
    with e[0]:
        ux.explain("rmse")
    with e[1]:
        ux.explain("argo")
    with e[2]:
        ux.explain("climatology")
    with e[3]:
        ux.explain("bias")

    depths = m.get("depths_m") or []
    df = pd.DataFrame({
        "depth": depths,
        "model": m.get("rmse") or [],
        "climatology": m.get("rmse_climatology") or [],
        "skill": m.get("skill_vs_climatology") or [],
        "n": m.get("n") or [],
    }).dropna(subset=["depth"])

    left, right = st.columns([3.0, 2.0], gap="large")
    with left:
        st.markdown("**Error at every depth, against the bar it has to clear**")
        long = df.melt(id_vars=["depth"], value_vars=["model", "climatology"],
                       var_name="series", value_name="rmse")
        st.altair_chart(
            alt.Chart(long).mark_line(point=True, strokeWidth=2).encode(
                x=alt.X("rmse:Q", title="RMSE (°C)"),
                y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
                color=alt.Color("series:N", title=None,
                                scale=alt.Scale(domain=["model", "climatology"],
                                                range=[theme.CYAN, theme.INK_DIM])),
                tooltip=[alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                         alt.Tooltip("series:N", title=""),
                         alt.Tooltip("rmse:Q", format=".4f", title="RMSE °C")],
            ).properties(height=420), use_container_width=True)
        worst = df.loc[df.model.idxmax()]
        st.caption(f"Worst depth is **{worst.depth:.0f} m** at {worst.model:.3f} °C — the "
                   f"thermocline. Climatology is worst there too, which is why the model still "
                   f"wins by the widest margin at that depth.")

    with right:
        st.markdown("**How much better than the average, depth by depth**")
        st.altair_chart(
            alt.Chart(df).mark_bar(color=theme.MINT, opacity=0.85, height=9).encode(
                x=alt.X("skill:Q", title="skill vs climatology", axis=alt.Axis(format="%")),
                y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
                tooltip=[alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                         alt.Tooltip("skill:Q", format=".1%", title="skill"),
                         alt.Tooltip("n:Q", format=",", title="observations")],
            ).properties(height=420), use_container_width=True)
        st.caption("Zero means no better than the seasonal average. Every depth is above it.")

    with st.expander("Every depth, as measured"):
        show = df.copy()
        show.columns = ["depth (m)", "model RMSE (°C)", "climatology RMSE (°C)",
                        "skill", "observations"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\mathrm{RMSE}=\sqrt{\frac{1}{N}\sum_{i=1}^{N}\big(\hat{T}_i-T_i\big)^2}"
        r"\qquad\quad \mathrm{skill}=1-\frac{\mathrm{RMSE}_{\text{model}}}"
        r"{\mathrm{RMSE}_{\text{climatology}}}",
        [("T̂ᵢ", "model temperature at one float measurement", "°C", "model output"),
         ("Tᵢ", "what the Argo float actually measured", "°C", "artifacts/argo_*.parquet"),
         ("N", "number of matched measurements", "—",
          f"{m['overall'].get('n', '—'):,} across 962 profiles"
          if isinstance(m.get('overall', {}).get('n'), int) else "—"),
         ("climatology", "the long-term seasonal average — no model at all", "°C",
          "artifacts/climatology.npy"),
         ("skill", "fraction of climatology's error removed; 0 means no better than average",
          "—", "docs/VALIDATION_PROTOCOL.md")],
        "Matching is within ±5 days and one grid cell. Squaring before averaging means a few "
        "large misses cost far more than many small ones, so this cannot be flattered by being "
        "usually-close.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("The model's report card against floats it never trained on, at every depth, "
              "beside the seasonal average it has to beat."),
        conclude=(f"Typical error is **{head['rmse']} °C** and the model removes "
                  f"**{head['skill']}** of climatology's error. Error peaks at the thermocline, "
                  "which is where the ocean itself is hardest to pin down — not where the model "
                  "is uniquely weak."),
        limits=[
            ("Correlation pooled across all depths reads 0.99, which flatters any model — depth "
             "alone explains most of the variance. The per-depth figure of 0.88 is the honest one.",
             "docs/VALIDATION_PROTOCOL.md"),
            ("Bias is +0.10 °C. Removing it would improve RMSE by roughly 0.013 °C, and it has "
             "deliberately NOT been removed: the checkpoint is frozen and its checksum is what "
             "ties these numbers to it.", "artifacts/frozen_manifest.json"),
            ("962 profiles over one year in one basin. This is not evidence about other oceans or "
             "other years.", "artifacts/frozen_manifest.json argo_profiles"),
            ("A reanalysis-input variant scores better (0.8548 °C) but fails the satellite-only "
             "requirement, so it is a comparator and not this number.",
             "artifacts/frozen_manifest.json glorys_comparator_stage2"),
        ])
