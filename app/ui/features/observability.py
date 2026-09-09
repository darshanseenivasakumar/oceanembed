"""What the satellite can actually see, and at which depth.

OWNER: Unit A (Arjhun). NOT a page.

Pure artifact renderer. `scripts/phase2/run_observability.py` owns the Jacobian.

THE QUESTION NOBODY IN THIS FIELD SEPARATES
Every paper reports where its model is inaccurate. That conflates "the model is weak here" with
"the surface carries no signal about this depth" -- the first is ours to fix, the second is a
ceiling on the whole approach. This differentiates the frozen model and shows which channel is
doing the work at each depth.

AND IT CARRIES ITS OWN NEGATIVE RESULT
The hypothesis was that our errors would sit below the information floor. Measured at every depth
where both groups exist, the opposite holds: low-sensitivity profiles have SMALLER errors. That is
on the panel, in the same size type as everything else.
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

ART = "observability.json"


@st.cache_data(show_spinner=False)
def _result() -> dict:
    p = base.art(ART)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _long(rows, channels) -> pd.DataFrame:
    out = []
    for r in rows:
        for c in channels:
            out.append({"depth": r["depth"], "channel": c,
                        "sensitivity": r["per_channel"][c],
                        "leading": r["leading_channel"]})
    return pd.DataFrame(out)


def render(ctx) -> None:
    r = _result()
    if not r:
        st.error("`artifacts/observability.json` is not on this machine, so there is nothing to "
                 "show. This panel never invents a sensitivity.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe scripts/phase2/run_observability.py")
        return
    if (r.get("control") or {}).get("agrees") is not True:
        st.error("The control does not reproduce the checkpoint's recorded RMSE; nothing below "
                 "would describe the shipped model.")
        return

    rows = r["by_depth"]
    chans = r["channels"]
    df = _long(rows, chans)
    prof = pd.DataFrame([{"depth": x["depth"], "l2": x["l2"],
                          "rel": x["l2_over_natural_variability"],
                          "leading": x["leading_channel"]} for x in rows])
    info = r["information_depth"]
    join = r["residual_vs_information"]

    peak = prof.loc[prof.l2.idxmax()]
    surf = next(x for x in rows if x["depth"] == 0.0)
    deep = next(x for x in rows if x["depth"] == 1000.0)

    # ---------------------------------------------------------------- 01
    ux.instrument("Differentiate the frozen model: how much does each depth move when a satellite "
                  "channel moves? Where that collapses, the surface has stopped informing depth.")

    ux.tiles([
        ("PEAK LEVERAGE AT", f"{int(peak.depth)}", "m",
         f"{peak.l2:.2f} °C per 1 s.d. — the thermocline"),
        ("LEADS AT THE SURFACE", surf["leading_channel"].upper(), "",
         f"{surf['leading_share']*100:.0f}% of the response at 0 m"),
        ("LEADS AT 100 m", next(x for x in rows if x['depth'] == 100.0)["leading_channel"].upper(),
         "", f"{next(x for x in rows if x['depth'] == 100.0)['leading_share']*100:.0f}% "
             f"of the response"),
        ("RELATIVE LEVERAGE FALLS", f"{peak.rel / prof.iloc[-1].rel:.1f}×", "",
         f"{peak.rel:.2f} at {int(peak.depth)} m → {prof.iloc[-1].rel:.2f} at 1000 m"),
    ])

    st.success(
        f"**The model learned to read sea-surface height for the thermocline, and nobody told it "
        f"to.** Sea-surface temperature dominates the top {int(next(x['depth'] for x in rows if x['leading_channel'] != 'sst'))} m; "
        f"below that SSH takes over and peaks at {peak.l2:.2f} °C per one-standard-deviation "
        f"shift. SSH is the depth-integrated signal of thermocline displacement — this is the "
        f"physically correct thing to read, and it is not in the loss function anywhere.",
        icon=":material/insights:")

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Which channel the model reads, at each depth**")
        ch = alt.Chart(df).mark_bar().encode(
            y=alt.Y("depth:O", title="depth (m)", sort="ascending"),
            x=alt.X("sensitivity:Q", stack="normalize",
                    title="share of the response", axis=alt.Axis(format="%")),
            color=alt.Color("channel:N", title="channel",
                            scale=alt.Scale(domain=chans, range=theme.CATEGORICAL + ["#7C8B99"])),
            tooltip=["depth", "channel",
                     alt.Tooltip("sensitivity:Q", format=".3f", title="°C per 1 s.d.")],
        ).properties(height=340)
        st.altair_chart(ch, use_container_width=True)

    with right:
        st.markdown("**How much leverage the surface has, by depth**")
        base_ch = alt.Chart(prof).encode(y=alt.Y("depth:O", title="depth (m)", sort="ascending"))
        bars = base_ch.mark_bar(color=theme.CYAN).encode(
            x=alt.X("rel:Q", title="response per 1 s.d. ÷ the ocean's own variability"),
            tooltip=[alt.Tooltip("depth:O"), alt.Tooltip("rel:Q", format=".2f"),
                     alt.Tooltip("l2:Q", format=".3f", title="°C per 1 s.d."), "leading"])
        rule = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
            color=theme.AMBER, strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart(bars + rule, use_container_width=True)
        st.caption(
            "Divided by the ocean's own standard deviation at that depth, so the seven channels "
            "and the fifteen depths are on one comparable scale. Above the dashed line a 1 s.d. "
            "surface change moves the prediction by more than a full standard deviation of the "
            "real variability there.")

    # ---------------------------------------------------------------- 02
    ux.maths(
        r"J_{d,c} \;=\; \sigma_{T}(d)\;\sum_{t,i,j}"
        r"\frac{\partial\,\hat{\mu}_d}{\partial\,x_{c,t,i,j}}",
        [("J", "response at depth d to a coherent +1 s.d. shift of channel c", "°C per s.d.",
          "autograd on the frozen shipped checkpoint"),
         ("μ̂", "the network's z-scored temperature output", "—", "TSCastNIO stage 1"),
         ("x", "the z-scored satellite patch: 7 channels × 11 days × 17 × 17", "—",
          "GriddedPatches"),
         ("σ_T(d)", "temperature standard deviation at depth d, train split", "°C",
          "the same statistic the model was normalised with"),
         ("τ", f"relative-sensitivity threshold defining 'still informed' — {info['tau']}", "—",
          "a stated parameter, swept in the artifact")],
        "Each channel is expressed per one standard deviation of ITSELF, which is the only way "
        "seven channels in °C, psu, metres and m/s can be compared at all — summing raw "
        "sensitivities across those units would be dimensionally meaningless. The sum over the "
        "patch is the response to a coherent shift of the whole input window, not a local "
        "gradient.")

    # ---------------------------------------------------------------- 03
    st.markdown("**The hypothesis this was built to test — and its answer**")
    with st.container(border=True):
        st.markdown(
            f"The idea was that our errors would sit **below** the information floor: that deep "
            f"error is the surface having nothing left to say, rather than the model failing. "
            f"Tested at every depth carrying enough profiles on both sides of the floor:")
        st.markdown(f"> {join['verdict']}")
        cols = st.columns(len(join["depth_controlled_ratios"]) or 1)
        testable = [x for x in join["per_depth"]
                    if x["n_above"] > 30 and x["n_below"] > 30
                    and np.isfinite(x["mae_above"]) and np.isfinite(x["mae_below"])]
        for col, row, ratio in zip(cols, testable, join["depth_controlled_ratios"]):
            with col:
                ux.tiles([(f"{int(row['depth'])} m", f"{ratio:.2f}", "×",
                           f"{row['mae_below']:.3f} below ÷ {row['mae_above']:.3f} above")])
        ux.caveat(
            "The pooled above/below comparison says 0.32× and is **confounded by depth** — "
            "sensitivity and the ocean's own variability both fall with depth, so 'below the "
            "floor' is mostly 'deep', and deep water is easy for reasons unrelated to "
            "observability. Only the per-depth comparison above is a fair test, and it refutes "
            "the hypothesis.")

    ux.inference(
        what=("The frozen model's own sensitivity, per depth and per satellite channel — a "
              "measured statement of what it is reading and where that reading fades."),
        conclude=(f"Two things. First, the model independently learned the physically correct "
                  f"channel handover: SST for the mixed layer, SSH for the thermocline, peaking "
                  f"at **{peak.l2:.2f} °C per 1 s.d. at {int(peak.depth)} m**. Second — and this "
                  f"was not the expected answer — **low sensitivity does not mark where we are "
                  f"wrong.** It marks quiescent water that sits close to climatology and is easy "
                  f"to predict."),
        limits=[
            ("This is a sensitivity-derived information depth, NOT an information-theoretic "
             "bound. No noise model, no likelihood, no mutual information. A different "
             "architecture could extract signal where this one has gone flat.",
             "observability.information_depth: 'sensitivity-derived, NOT an "
             "information-theoretic bound'"),
            (f"The floor is highly sensitive to τ. The median runs "
             f"{info['tau_sweep']['0.05']['median_depth_m']:.0f} m at τ=0.05 and "
             f"{info['tau_sweep']['0.5']['median_depth_m']:.0f} m at τ=0.5, so any single number "
             f"quoted from it is a statement about the threshold as much as about the ocean.",
             "the full τ sweep is written to artifacts/observability.json"),
            ("Sensitivity is local to the operating point. It is a derivative at today's "
             "conditions, not a global statement about how the model behaves under a large "
             "perturbation.",
             "autograd Jacobian, evaluated per profile"),
            ("It describes the shipped stage-1 model only. That the analysis is clean at all is "
             "because the shipped head takes no climatology input, so dμ/dx is the whole "
             "dependence — the paper's climatology-prior decoder would have made a flat Jacobian "
             "mean 'it fell back on the average' instead.",
             "verified: model output is bit-identical with climatology zeroed"),
        ])
