"""Does the SHAPE of the profile survive, and did trying to enforce it help?

OWNER: Unit A (Arjhun). NOT a page. Pure artifact renderer -- no model call.

TWO ARTIFACTS, ONE ARGUMENT, IN THAT ORDER

  1. physical_consistency.json   how much of the real dT/dz the shipped model reproduces
  2. physics_loss_sweep.json     what happened when a loss term was built to protect it

RMSE scores each of the 15 levels independently, so it never asks whether the shape BETWEEN them
survived. A model can hit every level to within a degree while smearing a sharp thermocline into
a gentle slope -- and a smeared thermocline is exactly what a cyclone forecaster or an acoustician
would be reading the profile FOR.

The measurement says the thermocline is at 100.6% of observed: not smoothed at all. The sweep then
says the gradient loss did not help, on three seeds. Those two facts belong on one screen, because
the first is the reason for the second. A null result with its cause beside it is a finding; the
same null result alone is just a failed experiment.

WHAT THIS PANEL MUST NOT SAY
static_stability is `applicable: false` -- stage 1 predicts temperature only, so it has no density
profile and the question cannot be asked of it. Rendering that as "0 violations" would be claiming
a pass the model never sat for.
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

#: The upper-ocean summary is computed here, not stored in the artifact. The n > 100 filter drops
#: the 2.5 m level pair, which rests on 21 profiles against ~950 for every other level -- a number
#: that thin would swing the mean and could not be defended if a judge asked what it was built on.
SHALLOW_M = 30.0
MIN_PROFILES = 100


@st.cache_data(show_spinner=False)
def _load(name: str) -> dict:
    p = base.art(name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def render(ctx) -> None:
    pc = _load("physical_consistency.json")
    sw = _load("physics_loss_sweep.json")
    if not pc:
        st.error("`artifacts/physical_consistency.json` is not on this machine.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe "
                "scripts/phase2/measure_physical_consistency.py")
        return

    pairs = [p for p in pc.get("per_level_pair", [])
             if p.get("predicted_over_observed") is not None]
    df = pd.DataFrame(pairs)
    shallow = [p["predicted_over_observed"] for p in pairs
               if p["mid_depth_m"] <= SHALLOW_M and p.get("n", 0) > MIN_PROFILES]
    shallow_mean = float(np.mean(shallow)) if shallow else float("nan")
    thermo = pc.get("gradient_ratio_thermocline")
    whole = pc.get("gradient_ratio_whole_column")

    c = st.columns([1.5, 1.5, 4.0])
    with c[0]:
        ux.explain("gradient", label="What a gradient ratio is")
    with c[1]:
        ux.explain("negative", label="Why show a failed experiment?")

    ux.tiles([
        ("THERMOCLINE 75–125 m", f"{thermo:.1%}", "", "of the observed dT/dz — not smoothed"),
        ("UPPER 30 m", f"{shallow_mean:.1%}", "", "genuinely flattened"),
        ("WHOLE COLUMN", f"{whole:.1%}", "", "mean over all 14 level pairs"),
        ("INDEPENDENT PROFILES", f"{pc.get('argo_profiles', 0):,}", "", "scored against Argo"),
    ])

    left, right = st.columns([3.0, 2.2], gap="large")
    with left:
        st.markdown("**How much of the real gradient the model reproduces, depth by depth**")
        ref = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
            color=theme.INK_DIM, strokeDash=[4, 3]).encode(x="x:Q")
        line = alt.Chart(df).mark_line(point=True, color=theme.CYAN, strokeWidth=2).encode(
            x=alt.X("predicted_over_observed:Q", title="predicted ÷ observed |dT/dz|",
                    scale=alt.Scale(zero=False)),
            y=alt.Y("mid_depth_m:Q", title="depth (m)",
                    scale=alt.Scale(reverse=True, type="symlog")),
            tooltip=[alt.Tooltip("mid_depth_m:Q", format=".0f", title="depth (m)"),
                     alt.Tooltip("predicted_over_observed:Q", format=".3f", title="ratio"),
                     alt.Tooltip("rms_observed:Q", format=".5f", title="observed °C/m"),
                     alt.Tooltip("rms_predicted:Q", format=".5f", title="predicted °C/m"),
                     alt.Tooltip("n:Q", format=",", title="profiles")])
        st.altair_chart((ref + line).properties(height=360), use_container_width=True)
        st.caption("1.0 means the model's profile is exactly as steep as the ocean's; below 1 it "
                   "is flatter. Scored against **independent Argo**, never against GLORYS — "
                   "GLORYS is the training target and would flatter this number.")

    with right:
        st.markdown("**Then a loss term was built to protect it**")
        if not sw:
            st.info("`artifacts/physics_loss_sweep.json` is not on this machine, so the sweep "
                    "result cannot be shown.")
        else:
            legs = sw.get("legs") or {}
            rows = []
            for w, leg in sorted(legs.items(), key=lambda kv: float(kv[0])):
                rows.append({"w_grad": float(w), "mean Δ RMSE": leg["mean_delta"],
                             "per-seed": ", ".join(f"{d:+.4f}" for d in leg["deltas"]),
                             "sign holds": bool(leg["sign_holds"])})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                         column_config={"mean Δ RMSE":
                                        st.column_config.NumberColumn(format="%+.4f")})
            spread = sw.get("control_spread")
            st.caption(f"Control is the same configuration at three seeds: mean "
                       f"**{sw.get('control_mean'):.4f} °C**, seed spread **{spread:.4f}** — the "
                       f"noise floor any effect has to clear.")
            st.error(
                f"**It did not help.** w=100 is measurably worse. w=1000's mean of "
                f"{legs['1000.0']['mean_delta']:+.4f} is smaller than the control's own seed "
                f"spread of {spread:.4f}, and its sign flips across seeds. Neither weight "
                f"survives a reseed.", icon=":material/science:")

    st.info(
        f"**And the measurement on the left is why.** At 75–125 m the model already reproduces "
        f"**{thermo:.1%}** of the observed gradient — the thermocline was never smoothed, so the "
        f"loss term was built to protect structure that did not need protecting. A null result "
        f"is what it should have produced.", icon=":material/lightbulb:")

    ss = pc.get("static_stability") or {}
    with st.expander("The other half of the physics, and why it is blank"):
        st.markdown(
            f"**Static stability: {'not applicable' if not ss.get('applicable') else 'measured'}.** "
            f"{ss.get('why', '')}")
        st.caption("This is a not-applicable, not a pass. Reporting it as zero violations would "
                   "be claiming a check the model never sat.")

    # ---- 02 - the mathematics ------------------------------------------------------
    ux.maths(
        r"R(z) \;=\; \frac{\big\langle (\partial \hat T/\partial z)^2 \big\rangle^{1/2}}"
        r"{\big\langle (\partial T/\partial z)^2 \big\rangle^{1/2}}"
        r"\qquad\quad L_{\text{grad}} \;=\; \Big\langle \Big(\frac{\partial \hat T}{\partial z}"
        r" - \frac{\partial T}{\partial z}\Big)^{2}\Big\rangle",
        [("R(z)", "the gradient ratio: RMS predicted steepness over RMS observed, at one level "
                  "pair. Below 1 the model is flatter than the ocean", "—",
          "artifacts/physical_consistency.json per_level_pair"),
         ("∂T/∂z", "finite difference between adjacent levels, divided by the real spacing", "°C/m",
          "scripts/phase2/measure_physical_consistency.py"),
         ("⟨·⟩", "mean over the independent Argo profiles at that level pair", "—",
          f"{pc.get('argo_profiles', 0):,} profiles"),
         ("L_grad", "the loss term that was added to penalise gradient error directly, behind a "
                    "--w-grad flag so it could be ablated", "°C²/m²",
          "src/phase2/tscast_nio/models/tscast.py"),
         ("w_grad", "its weight. Chosen by measurement, not guessed: on a real 2,048-sample batch "
                    "the term is 4.85e-4 against a β-NLL objective of −0.1834, so w=100 is 21% of "
                    "the loss and w=1000 is 72%", "—",
          "scripts/phase2/run_physics_loss_sweep.py")],
        "Depth spacing is uneven — 5 m near the surface, 300 m at the bottom — so the difference "
        "must be divided by the real Δz or the term is 60× more sensitive at the deepest gap.")

    # ---- 03 - the inference --------------------------------------------------------
    ux.inference(
        what=("Whether the reconstruction has the right SHAPE, not just the right values. RMSE "
              "scores each depth on its own and is blind to this."),
        conclude=("The thermocline is reproduced at full strength, so the profile is usable for "
                  "the things people read a profile for. The top 30 m is genuinely flattened — "
                  "plausibly an information limit, since a daily-mean satellite field cannot see "
                  "the diurnal cycle that sets the near-surface gradient. And forcing the "
                  "gradient with a loss term did not help, which is the correct outcome given "
                  "the first sentence."),
        limits=[
            ("Static stability is NOT measured. Stage 1 predicts temperature only, so it has no "
             "density profile and the question cannot be asked — this is a not-applicable, not a "
             "pass.", "artifacts/physical_consistency.json static_stability"),
            ("A ratio near 1 proves the model gets the right gradient MAGNITUDE. It does not "
             "prove the gradient is in the right place.",
             "scripts/phase2/measure_physical_consistency.py"),
            ("The 2.5 m level pair rests on 21 profiles against ~950 elsewhere, and is excluded "
             "from the upper-30 m figure for that reason.",
             "artifacts/physical_consistency.json per_level_pair[0].n"),
            ("Training is not deterministic here — no deterministic algorithms, no "
             "cudnn.deterministic, and it runs on CUDA. That is why the control is three seeds "
             "and why a single seed proves nothing.",
             "artifacts/physics_loss_sweep.json determinism"),
            ("Seed 42 improved under BOTH weights. Reporting one seed would have claimed a "
             "0.019 °C win that does not exist.",
             "artifacts/physics_loss_sweep.json legs[].deltas"),
        ])
