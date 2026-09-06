"""What the monsoon costs a model that must see the surface.

OWNER: Unit A (Arjhun). NOT a page.

Infrared SST cannot see through cloud. This blanks it on purpose and measures what the
reconstruction loses. Pure artifact renderer -- no model call, so it is instant.

THE CURVE IS NOT MONOTONE, AND THAT IS THE ENTIRE POINT
RMSE gets BETTER as the first 15% of SST is blanked. It would be easy, and completely wrong, to
report that as "the model tolerates cloud cover". What is actually happening is two errors
cancelling: the deliverable carries a +0.10 degC warm bias, a blanked pixel reaches the encoder as
the channel mean (which pulls the prediction cooler), and the RMSE minimum sits exactly where the
bias crosses zero. The dip is arithmetic, not skill.

So this feature is built to make the wrong reading hard to reach: the bias curve sits beside the
RMSE curve, the zero-crossing is drawn on both, and the headline says "bias finding" before it
says anything else.
"""
from __future__ import annotations

import json
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import theme, ux


@st.cache_data(show_spinner=False)
def _result() -> dict:
    p = base.art("cloud_dropout.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _frame(r: dict) -> pd.DataFrame:
    rows = []
    for k, v in (r.get("by_fraction") or {}).items():
        rows.append({"fraction": float(k), "rmse": v["mean_rmse"], "bias": v["mean_bias"],
                     "spread": v["spread"], "draws": v["n_draws"],
                     "delta": v["delta_vs_control"]})
    return pd.DataFrame(rows).sort_values("fraction").reset_index(drop=True)


def render(ctx) -> None:
    r = _result()
    if not r:
        st.error("`artifacts/cloud_dropout.json` is not on this machine, so there is nothing to "
                 "show. This panel never invents a curve.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe scripts/phase2/run_cloud_dropout.py")
        return

    if not r.get("control_agrees"):
        st.error("The 0%-masked control does NOT reproduce the checkpoint's recorded RMSE, so "
                 "every degradation below it could be the harness rather than the masking. "
                 "Nothing here is trustworthy until that is fixed.")
        return

    a = r.get("analysis") or {}
    df = _frame(r)
    ctrl = r["control_rmse"]
    best_f = a.get("rmse_minimising_fraction")
    best = a.get("rmse_at_minimum")
    gain = a.get("improvement_vs_control")
    cross = a.get("bias_zero_crossing_fraction")
    worst = df.iloc[-1]

    c = st.columns([1.4, 1.4, 4.2])
    with c[0]:
        ux.explain("masking", label="How the masking works")
    with c[1]:
        ux.explain("biasfinding", label="Why the dip is not good news")

    ux.tiles([
        ("CONTROL, 0% MASKED", f"{ctrl:.4f}", "°C",
         f"reproduces the checkpoint exactly ({r['recorded_rmse']:.4f})"),
        (f"BEST, AT {best_f:.0%} MASKED", f"{best:.4f}", "°C", f"−{gain:.4f} vs control"),
        (f"AT {worst.fraction:.0%} MASKED", f"{worst.rmse:.4f}", "°C",
         f"+{worst.delta:.4f} vs control"),
        ("WARM BIAS, UNMASKED", f"{a.get('control_bias', float('nan')):+.4f}", "°C",
         "the thing the dip is cancelling"),
    ])

    st.success(
        f"**The control reproduces the checkpoint's own number exactly** — "
        f"{ctrl:.4f} against {r['recorded_rmse']:.4f} recorded. That is what makes every "
        f"degradation below attributable to the masking rather than to the harness.",
        icon=":material/check_circle:")

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**How much accuracy is lost**")
        band = alt.Chart(df).mark_area(opacity=0.22, color=theme.CYAN).encode(
            x=alt.X("fraction:Q", title="fraction of ocean SST blanked",
                    axis=alt.Axis(format="%")),
            y=alt.Y("lo:Q", title="RMSE vs Argo (°C)", scale=alt.Scale(zero=False)),
            y2="hi:Q").transform_calculate(
            lo="datum.rmse - datum.spread / 2", hi="datum.rmse + datum.spread / 2")
        line = alt.Chart(df).mark_line(point=True, color=theme.CYAN, strokeWidth=2).encode(
            x=alt.X("fraction:Q", axis=alt.Axis(format="%")),
            y=alt.Y("rmse:Q", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("fraction:Q", format=".0%", title="masked"),
                     alt.Tooltip("rmse:Q", format=".4f", title="RMSE °C"),
                     alt.Tooltip("spread:Q", format=".4f", title="spread (max−min)"),
                     alt.Tooltip("draws:Q", title="mask draws")])
        ref = alt.Chart(pd.DataFrame({"y": [ctrl]})).mark_rule(
            color=theme.INK_DIM, strokeDash=[4, 3]).encode(y="y:Q")
        mark = alt.Chart(pd.DataFrame({"x": [best_f]})).mark_rule(
            color=theme.AZURE, strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart((band + ref + mark + line).properties(height=330),
                        use_container_width=True)
        st.caption(
            f"Band is the spread across **{r['by_fraction'][str(best_f)]['n_draws']}** independent "
            f"mask draws — that is max minus min, a range, not a standard deviation. Grey = the "
            f"unmasked control. Blue = the RMSE minimum. Past it the curve only rises: "
            f"**+{worst.delta:.4f} °C** by {worst.fraction:.0%}.")

    with right:
        st.markdown("**And why the dip on the left is not good news**")
        bline = alt.Chart(df).mark_line(point=True, color=theme.AMBER, strokeWidth=2).encode(
            x=alt.X("fraction:Q", title="fraction of ocean SST blanked",
                    axis=alt.Axis(format="%")),
            y=alt.Y("bias:Q", title="bias vs Argo (°C)"),
            tooltip=[alt.Tooltip("fraction:Q", format=".0%", title="masked"),
                     alt.Tooltip("bias:Q", format=".4f", title="bias °C")])
        zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(
            color=theme.INK_DIM).encode(y="y:Q")
        xr = alt.Chart(pd.DataFrame({"x": [cross]})).mark_rule(
            color=theme.AMBER, strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart((zero + xr + bline).properties(height=330), use_container_width=True)
        st.caption(
            f"The model runs **{a.get('control_bias'):+.4f} °C warm** with nothing masked. A "
            f"blanked pixel arrives as the channel mean, which pulls the prediction cooler, so "
            f"the bias walks down and crosses zero at **{cross:.0%}** — right where RMSE bottoms "
            f"out. The apparent gain is that cancellation.")

    ux.caveat(
        f"**Read this as a bias finding, not a robustness finding.** The deliverable carries a "
        f"{a.get('control_bias'):+.4f} °C warm bias against independent Argo. Removing it is "
        f"worth about {gain:.4f} °C of RMSE — which is exactly what the dip at {best_f:.0%} "
        f"masking is accidentally buying. A bias correction buys the same thing without throwing "
        f"away {best_f:.0%} of the input.")

    with st.expander(f"Every leg, as run  ·  {len(r.get('legs', []))}"):
        legs = pd.DataFrame(r.get("legs", []))
        st.dataframe(legs, use_container_width=True, hide_index=True, height=300)
        st.caption(f"Checkpoint `{r.get('checkpoint')}`, channel `{r.get('channel_masked')}`, "
                   f"T_SEQ={r.get('t_seq')}, {r.get('argo_profiles'):,} independent Argo "
                   f"profiles. No retraining — the frozen checkpoint is run unmodified.")

    # ---- 02 - the mathematics ------------------------------------------------------
    ux.maths(
        r"x_{\text{masked}} \;=\; \mathrm{NaN} \;\xrightarrow{\text{z-score}}\; 0"
        r"\;=\; \frac{\mu_c - \mu_c}{\sigma_c}"
        r"\qquad\quad \mathrm{RMSE}^2 \;=\; \mathrm{bias}^2 + \mathrm{variance}",
        [("x_masked", "an SST pixel blanked by the harness, in physical units", "°C",
          "phase2.validation.dropout.apply_cloud"),
         ("μ_c, σ_c", "the channel's training mean and standard deviation", "°C",
          "the normalisation the checkpoint was fitted under"),
         ("0", "what the encoder actually receives — which IS the channel mean, so the model "
               "cannot tell a missing pixel from average water", "—",
          "src/phase2/tscast_nio/dataset.py"),
         ("bias", "systematic offset against Argo; +0.1003 °C unmasked", "°C",
          "artifacts/cloud_dropout.json analysis.control_bias"),
         ("RMSE² = bias² + var", "why cancelling the bias lowers RMSE without improving the "
                                 "model at all", "—", "the identity the whole finding rests on")],
        "Masking is applied in PHYSICAL units before normalisation, so it is a real blanking of "
        "the input rather than a poke at the z-scored tensor. Only SST is masked — SSS is "
        "microwave and SSH is altimetry, and neither is blinded by cloud.")

    # ---- 03 - the inference --------------------------------------------------------
    ux.inference(
        what=("What happens to the reconstruction as monsoon cloud progressively blinds the "
              "infrared SST sensor, from nothing masked to everything."),
        conclude=("Past about 20% the model degrades steadily and predictably, and by 90% it is "
                  "worse than climatology — so SST is doing most of the work and there is no "
                  "hidden robustness here. The improvement on the left is two errors cancelling, "
                  "and the honest use of it is as evidence for a bias correction."),
        limits=[
            ("The dip at low masking is bias cancellation, not skill. It is reported as a bias "
             "finding about the deliverable.", "artifacts/cloud_dropout.json -> analysis"),
            ("The model has no missing-data channel — it cannot know a pixel was blanked, because "
             "a blanked pixel and average water reach it as the same number.",
             "phase2.validation.dropout.masking_is_indistinguishable_from_mean_fill"),
            ("Pixels are masked at random and independently per day. Real cloud is spatially "
             "correlated and sits over the monsoon for weeks, which is a harder problem than "
             "this.", "phase2.validation.dropout.cloud_mask"),
            ("Only SST is masked. A real cloudy day does not blind altimetry.",
             "phase2.validation.dropout.DEFAULT_CHANNEL"),
            ("The bundle already leaves about 2.4% of ocean SST missing at its edges, so the "
             "x-axis is the fraction REQUESTED, not the fraction finally absent.",
             "cloud_dropout.json legs[].fraction_now_missing"),
        ])
