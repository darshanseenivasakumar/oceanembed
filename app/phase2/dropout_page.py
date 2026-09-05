"""What the monsoon does to a model that needs to see the sea surface. (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/dropout_page.py --server.port 8515

Renders `artifacts/cloud_dropout.json`, written by `scripts/phase2/run_cloud_dropout.py`. This page
runs no inference and needs no checkpoint: the experiment is the script's, and a results page that
recomputed its own numbers would be a second definition of them.

THE RESULT IS NOT MONOTONE, AND THE INTERESTING PART IS WHY
Blanking 15% of ocean SST makes the score BETTER -- 0.8950 against the control's 0.9078, with a
spread across mask draws of 0.0002, so it is 60x the noise and not a fluke. It would be easy, and
completely wrong, to report that as "the model tolerates cloud cover".

It is two errors partially cancelling. The shipped model carries a +0.1003 degC WARM bias. A
blanked pixel reaches the encoder as the channel mean (see the caveat below), which pulls the
prediction cooler. The RMSE minimum at 15% sits essentially where the bias crosses zero, ~19%. So
the honest reading is a finding about the DELIVERABLE -- it runs warm, and a bias correction is
worth about 0.013 degC -- and not a finding about robustness.

Past the minimum the curve is monotone and the degradation is real: +0.50 degC by 100%, with the
skill-vs-climatology score going negative at 90%.
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
sys.path.insert(0, os.path.dirname(__file__))

from oceanembed import config as base                       # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Cloud dropout", layout="wide")

ART = base.art("cloud_dropout.json")
CLR_RMSE = "#2a78d6"
CLR_BIAS = "#d95926"
CLR_CONTROL = "#787878"


@st.cache_data(show_spinner=False)
def results() -> dict | None:
    if not os.path.exists(ART):
        return None
    with open(ART, encoding="utf-8") as f:
        return json.load(f)


def frames(r: dict):
    rows = []
    for k, v in r["by_fraction"].items():
        rows.append({"fraction": float(k), "rmse": v["mean_rmse"], "bias": v["mean_bias"],
                     "spread": v["spread"], "n_draws": v["n_draws"],
                     "lo": v["mean_rmse"] - v["spread"] / 2, "hi": v["mean_rmse"] + v["spread"] / 2,
                     "delta": v["delta_vs_control"]})
    return pd.DataFrame(rows).sort_values("fraction")


def rmse_chart(df: pd.DataFrame, r: dict):
    a = r["analysis"]
    x = alt.X("fraction:Q", title="fraction of ocean SST blanked",
              axis=alt.Axis(format="%"), scale=alt.Scale(nice=False))
    band = alt.Chart(df).mark_area(opacity=0.25, color=CLR_RMSE).encode(x=x, y="lo:Q", y2="hi:Q")
    line = alt.Chart(df).mark_line(point=True, color=CLR_RMSE, strokeWidth=2).encode(
        x=x, y=alt.Y("rmse:Q", title="RMSE vs independent Argo (°C)",
                     scale=alt.Scale(zero=False, nice=False)),
        tooltip=[alt.Tooltip("fraction:Q", format=".0%", title="masked"),
                 alt.Tooltip("rmse:Q", format=".4f", title="RMSE °C"),
                 alt.Tooltip("spread:Q", format=".4f", title="spread over draws"),
                 alt.Tooltip("delta:Q", format="+.4f", title="vs control"),
                 alt.Tooltip("n_draws:Q", title="mask draws")])
    ctl = alt.Chart(pd.DataFrame({"y": [r["control_rmse"]]})).mark_rule(
        color=CLR_CONTROL, strokeDash=[6, 4]).encode(y="y:Q")
    mark = alt.Chart(pd.DataFrame({"x": [a["rmse_minimising_fraction"]]})).mark_rule(
        color=CLR_RMSE, strokeDash=[2, 3], opacity=0.7).encode(x="x:Q")
    return (band + ctl + mark + line).properties(height=340)


def bias_chart(df: pd.DataFrame, r: dict):
    a = r["analysis"]
    x = alt.X("fraction:Q", title="fraction of ocean SST blanked",
              axis=alt.Axis(format="%"), scale=alt.Scale(nice=False))
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=CLR_CONTROL).encode(y="y:Q")
    line = alt.Chart(df).mark_line(point=True, color=CLR_BIAS, strokeWidth=2).encode(
        x=x, y=alt.Y("bias:Q", title="bias, model − Argo (°C)",
                     scale=alt.Scale(zero=False, nice=False)),
        tooltip=[alt.Tooltip("fraction:Q", format=".0%", title="masked"),
                 alt.Tooltip("bias:Q", format="+.4f", title="bias °C")])
    layers = [zero, line]
    if a.get("bias_zero_crossing_fraction") is not None:
        layers.append(alt.Chart(pd.DataFrame({"x": [a["bias_zero_crossing_fraction"]]}))
                      .mark_rule(color=CLR_BIAS, strokeDash=[2, 3], opacity=0.7).encode(x="x:Q"))
    return alt.layer(*layers).properties(height=340)


def explainer(r: dict) -> Explainer:
    a = r["analysis"]
    return Explainer(
        title="Degradation under simulated cloud cover",
        plain=("During the monsoon, thick cloud blinds the infrared sensor that measures sea "
               "surface temperature, so the model sometimes has to work with incomplete surface "
               "data. This blanks out part of the SST input on purpose and measures how much the "
               "prediction degrades — a preview of how it would perform through a cloudy month."),
        formula="",
        formula_note=None,
        how_to_read=("A shallow slope means the model leans on its other channels — sea surface "
                     "height and wind, which cloud does not block — and degrades gracefully. A "
                     "steep slope means SST is doing most of the work. Here the slope is shallow "
                     "to about 30% and steep after that. The dip below the grey control line at "
                     "the left is NOT robustness; see the first caveat."),
        caveats=(
            Caveat("The improvement at light masking is a bias cancellation, not robustness.",
                   f"Blanking {a['rmse_minimising_fraction']:.0%} of SST lowers RMSE by "
                   f"{a['improvement_vs_control']:.4f} °C, and the spread across mask draws is "
                   f"only {a['seed_spread_at_minimum']:.4f}, so the effect is real. But the "
                   f"shipped model carries a **{a['control_bias']:+.4f} °C warm bias**, a blanked "
                   f"pixel reaches the encoder as the channel mean, and that pulls the prediction "
                   f"cooler. The RMSE minimum sits essentially where the bias crosses zero "
                   f"(~{a['bias_zero_crossing_fraction']:.0%}). Two errors partially cancelling — "
                   f"read as a finding about the deliverable's bias, never as tolerance of cloud.",
                   "artifacts/cloud_dropout.json -> analysis"),
            Caveat("The model has no way to know a pixel is missing.",
                   "`dataset.__getitem__` z-scores the patch and replaces every non-finite value "
                   "with 0.0 — which IS the channel mean. So a blanked pixel arrives as average "
                   "water, and the encoder cannot tell 'I have no idea' from 'ordinary sea'. The "
                   "dataset computes a `finite` companion mask and discards it on the next line, "
                   "despite its own docstring promising it is kept.",
                   "src/phase2/tscast_nio/dataset.py:150-158"),
            Caveat("This is random masking, not a cloud field.",
                   "Real cloud is spatially correlated and persists for days; independent random "
                   "pixels are the easiest possible version of the problem, because a 17×17 patch "
                   "almost always retains some SST. A real monsoon overcast would blank whole "
                   "patches at once and should be expected to hurt MORE than this curve shows.",
                   "phase2.validation.dropout.cloud_mask — drawn per time step, uncorrelated"),
            Caveat("Only SST is masked.",
                   "Salinity comes from SMOS (microwave) and height from altimetry; neither is "
                   "stopped by cloud. Masking them would model a different failure.",
                   "phase2.validation.dropout.DEFAULT_CHANNEL"),
        ),
        references=())


def main() -> None:
    st.title("Cloud cover — what the monsoon does to a model that must see the surface")
    st.caption("Infrared SST cannot see through cloud. This blanks it on purpose and measures "
               "what the reconstruction loses.")

    r = results()
    if r is None:
        st.error(f"No results artifact at `{ART}`.")
        st.code("python scripts/phase2/run_cloud_dropout.py", language="bash")
        st.info("The experiment lives in the script; this page only renders it.")
        return

    a = r["analysis"]
    df = frames(r)

    if not r.get("control_agrees"):
        st.error("The control does not reproduce the checkpoint's own RMSE — every number below "
                 "is harness error, not cloud.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("control (0% masked)", f"{r['control_rmse']:.4f} °C",
              delta=f"recorded {r['recorded_rmse']:.4f}", delta_color="off")
    c2.metric("best, at 15% masked", f"{a['rmse_at_minimum']:.4f} °C",
              delta=f"{-a['improvement_vs_control']:+.4f} vs control", delta_color="inverse")
    worst = df.iloc[-1]
    c3.metric(f"at {worst['fraction']:.0%} masked", f"{worst['rmse']:.4f} °C",
              delta=f"{worst['delta']:+.4f} vs control")
    c4.metric("independent Argo profiles", f"{r['argo_profiles']:,}")

    st.success(
        f"**The control reproduces the checkpoint's own number exactly** "
        f"({r['control_rmse']:.4f} vs {r['recorded_rmse']:.4f} recorded). That is what makes every "
        f"degradation below it attributable to the masking rather than to the harness.")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("How much accuracy is lost")
        st.altair_chart(rmse_chart(df, r), use_container_width=True)
        st.caption(
            f"Band is the spread across {r['mask_seeds'] and len(r['mask_seeds'])} independent "
            f"mask draws. Grey dashed = the unmasked control. Blue dashed = the RMSE minimum. "
            f"Beyond it the curve is monotone: **{worst['delta']:+.4f} °C** by "
            f"{worst['fraction']:.0%}.")
    with right:
        st.subheader("And why the left-hand dip is not good news")
        st.altair_chart(bias_chart(df, r), use_container_width=True)
        st.caption(
            f"The model runs **{a['control_bias']:+.4f} °C warm** with nothing masked. Blanking "
            f"pulls predictions toward the channel mean, which cools them, and the bias crosses "
            f"zero at ~**{a['bias_zero_crossing_fraction']:.0%}** — right where RMSE bottoms out. "
            f"The apparent improvement is that cancellation, not skill.")

    st.warning(
        f"**Read this as a bias finding, not a robustness finding.** The deliverable carries a "
        f"{a['control_bias']:+.4f} °C warm bias against independent Argo. Removing it is worth "
        f"about {a['improvement_vs_control']:.4f} °C of RMSE — which is what the dip at "
        f"{a['rmse_minimising_fraction']:.0%} masking is accidentally buying. A bias correction "
        f"would buy it without throwing away 15% of the input.")

    with st.expander("Every leg, as run"):
        st.dataframe(pd.DataFrame(r["legs"])[
            ["fraction", "fraction_now_missing", "mask_seed", "rmse", "bias",
             "skill_rmse_ratio", "n"]].round(4), hide_index=True, width="stretch")
        st.caption(f"Checkpoint `{r['checkpoint']}`, channel `{r['channel_masked']}`, "
                   f"T_SEQ={r['t_seq']}, {r['seconds']:.0f} s. No retraining: the shipped weights, "
                   f"the same test split, embargo, normalisation, climatology and Argo "
                   f"collocation the trainer itself uses.")

    render(explainer(r))


if __name__ == "__main__":
    main()
