"""Streamlit profile panel: def render(recon_output, argo_df=None).

OWNER: Unit C (Mitun+Niru).

Plots depth DOWNWARD on the y-axis -- the convention every oceanographer reads profiles in.
The shell's fallback puts depth on the x-axis, which is readable but reads as unfamiliar to a
domain judge.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from app.panels._viz import nearest_argo


def render(recon_output: dict, argo_df=None) -> None:
    out = recon_output

    if out.get("is_land") or out.get("profile_mean") is None:
        st.info("Land or no-data point — pick an ocean location.")
        return

    depths = np.asarray(out["depths"], dtype="float32")
    mean = np.asarray(out["profile_mean"], dtype="float32")
    std = np.asarray(out["profile_std"], dtype="float32")

    df = pd.DataFrame({
        "depth": depths,
        "temperature": mean,
        "lo": mean - std,
        "hi": mean + std,
    })

    band = alt.Chart(df).mark_area(opacity=0.22, color="#4c9be8").encode(
        x=alt.X("lo:Q", title="Temperature (°C)", scale=alt.Scale(zero=False)),
        x2="hi:Q",
        y=alt.Y("depth:Q", title="Depth (m)", scale=alt.Scale(reverse=True)),
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                 alt.Tooltip("lo:Q", format=".2f", title="−1σ"),
                 alt.Tooltip("hi:Q", format=".2f", title="+1σ")],
    )
    line = alt.Chart(df).mark_line(point=True, color="#1f77b4", strokeWidth=2.5).encode(
        x=alt.X("temperature:Q", scale=alt.Scale(zero=False)),
        y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                 alt.Tooltip("temperature:Q", format=".2f", title="°C")],
    )
    layers = [band, line]

    if out.get("climatology") is not None:
        clim_df = pd.DataFrame({"depth": depths,
                                "temperature": np.asarray(out["climatology"], dtype="float32")})
        layers.append(
            alt.Chart(clim_df).mark_line(strokeDash=[6, 4], color="#8c8c8c").encode(
                x=alt.X("temperature:Q", scale=alt.Scale(zero=False)),
                y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
                tooltip=[alt.Tooltip("temperature:Q", format=".2f", title="climatology °C")],
            )
        )

    argo = nearest_argo(argo_df, out["lat"], out["lon"])
    if argo is not None and "temp" in argo.columns:
        a_depth = (depths[argo["depth_idx"].to_numpy().astype(int)]
                   if "depth_idx" in argo.columns else depths[: len(argo)])
        a_df = pd.DataFrame({"depth": a_depth, "temperature": argo["temp"].to_numpy()})
        layers.append(
            alt.Chart(a_df).mark_point(shape="diamond", size=95, color="#e4572e", filled=True).encode(
                x=alt.X("temperature:Q", scale=alt.Scale(zero=False)),
                y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
                tooltip=[alt.Tooltip("temperature:Q", format=".2f", title="ARGO °C")],
            )
        )

    st.altair_chart(alt.layer(*layers).properties(height=430), width='stretch')

    bits = ["**solid** = reconstruction", "**band** = ±1σ MC-dropout spread"]
    if out.get("climatology") is not None:
        bits.append("**dashed** = climatology")
    if argo is not None:
        bits.append("**◆ red** = nearest independent ARGO profile")
    else:
        bits.append("_no ARGO profile within 2° of this point_")
    st.caption(" · ".join(bits))

    # Honesty: the spread narrows with depth, and a reader will take that as growing confidence.
    # docs/DECISIONS.md D-016 measured it as an artefact of un-normalization, not real certainty.
    if len(std) > 1 and std[-1] < std[0]:
        st.caption(
            f"⚠️ The ±1σ band narrows with depth ({std[0]:.3f} → {std[-1]:.3f} °C). This is a known "
            "artefact of MC-dropout on a shared trunk, **not** higher confidence at depth. The "
            "spread is overconfident at **every** depth — measured 1.6× to 3.5× too narrow against "
            "independent Argo, and **worst in the mixed layer (20–50 m)**, not at depth "
            "(DECISIONS.md D-016, remeasured 2026-08-26). Read it as relative, not absolute."
        )
