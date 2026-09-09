"""Every emitted profile is statically stable, and that is arithmetic rather than a hope.

OWNER: Unit A (Arjhun). NOT a page.

Pure artifact renderer -- no model call, no projection run here. `scripts/phase2/
run_stability_projection.py` owns the experiment; a panel that recomputed its own violation count
would be a second definition of it.

WHY THIS IS THE STRONGEST OF THE THREE NOVELTIES
TS-Cast and everyone before them put density stratification in the LOSS. A soft penalty makes
violations rare and cannot make them absent, which is why no paper in this specialisation reports a
violation count. We report ours -- 5.98% of adjacent level pairs at the float points, 7.34% across
the basin -- and then remove them by projection.

THE REFUSAL IS PART OF THE FEATURE
Density needs salinity at depth. The shipped deliverable is stage 1, temperature only, so the
question is not well posed there and the panel says so instead of substituting a temperature
monotonicity that would delete Bay of Bengal barrier-layer inversions.
"""
from __future__ import annotations

import json
import os

import altair as alt
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import theme, ux

ART = "stability_projection.json"


@st.cache_data(show_spinner=False)
def _result() -> dict:
    p = base.art(ART)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _bars(legs) -> pd.DataFrame:
    rows = []
    for leg in legs:
        for when in ("before", "after"):
            v = leg[f"violations_{when}"]
            rows.append({"leg": leg["label"], "when": when,
                         "pairs": v["n_violating"], "pct": 100.0 * v["fraction"]})
    return pd.DataFrame(rows)


def render(ctx) -> None:
    r = _result()
    if not r:
        st.error("`artifacts/stability_projection.json` is not on this machine, so there is "
                 "nothing to show. This panel never invents a violation count.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe "
                "scripts/phase2/run_stability_projection.py")
        return

    ctrl = r.get("control") or {}
    if ctrl.get("agrees") is not True:
        st.error("The control does not reproduce the checkpoint's recorded RMSE, so every count "
                 "below it would describe the harness rather than the model.")
        return

    legs = r["legs"]
    baseline = legs[0]
    b, a = baseline["violations_before"], baseline["violations_after"]
    basin = r.get("basin") or {}

    # ---------------------------------------------------------------- 01
    ux.instrument("A predicted column whose density falls with depth would overturn on the spot. "
                  "Each level is individually plausible, so no RMSE can see it.")

    ux.tiles([
        ("UNSTABLE PAIRS, BEFORE", f"{b['n_violating']:,}", "",
         f"{b['fraction']*100:.2f}% of {b['n_pairs']:,} adjacent pairs"),
        ("PROFILES AFFECTED", f"{b['n_profiles_with_violation']:,}", "",
         f"of {baseline['n_profiles']:,} independent-Argo columns"),
        ("UNSTABLE PAIRS, AFTER", f"{a['n_violating']:,}", "",
         "by construction, and re-verified from the projected temperature"),
        ("COST IN RMSE", f"{baseline['rmse_cost_degC']:+.4f}", "°C",
         f"{baseline['metrics_before']['rmse']:.4f} → "
         f"{baseline['metrics_after']['rmse']:.4f} vs independent Argo"),
    ])

    if a["n_violating"] == 0 and baseline["verified_zero"]:
        st.success(
            "**Zero, and verified rather than asserted.** The check recomputes density from the "
            "projected temperature and counts again — it does not trust the algebra that produced "
            "it.", icon=":material/verified:")

    left, right = st.columns([1.25, 1.0], gap="large")
    with left:
        st.markdown("**Unstable adjacent pairs, before and after**")
        df = _bars(legs)
        ch = alt.Chart(df).mark_bar().encode(
            x=alt.X("when:N", title=None, sort=["before", "after"],
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("pairs:Q", title="unstable adjacent pairs"),
            color=alt.Color("when:N", legend=None,
                            scale=alt.Scale(domain=["before", "after"],
                                            range=[theme.CORAL, theme.MINT])),
            column=alt.Column("leg:N", title=None,
                              header=alt.Header(labelLimit=320, labelFontSize=11)),
            tooltip=["leg", "when", "pairs", alt.Tooltip("pct:Q", format=".2f", title="% of pairs")]
        ).properties(width=150, height=300)
        st.altair_chart(ch)

    with right:
        if basin:
            st.markdown("**The same count over the whole basin**")
            bb, ba = basin["violations_before"], basin["violations_after"]
            st.markdown(
                f"On **{basin['date']}**, across **{basin['n_ocean_cells']:,}** ocean cells — "
                f"columns no float ever visited:")
            ux.tiles([
                ("UNSTABLE PAIRS", f"{bb['n_violating']:,}", "",
                 f"{bb['fraction']*100:.2f}% of {bb['n_pairs']:,}"),
                ("CELLS AFFECTED", f"{bb['n_profiles_with_violation']:,}", "",
                 f"of {basin['n_ocean_cells']:,}"),
                ("AFTER PROJECTION", f"{ba['n_violating']:,}", "",
                 f"whole basin in {basin['seconds']:.0f} s"),
            ])
        st.caption(
            f"Projection cost: **{baseline['ms_per_profile']:.2f} ms per profile**. It is a "
            f"closed-form monotone projection, not an optimisation — there is no iteration count "
            f"to tune and no failure mode where it does not converge.")
        if baseline.get("n_refusals"):
            ux.caveat(
                f"**{baseline['n_refusals']} level(s) refused rather than projected.** Below the "
                f"temperature of maximum density — reachable in this basin's freshwater plume — "
                f"cooling makes water lighter, so density does not map one-to-one onto "
                f"temperature. Those levels come back as gaps naming the reason. An earlier "
                f"version kept the original value there, which silently restored the original "
                f"violation inside a function whose whole promise is that there are none.")

    # ---------------------------------------------------------------- 02
    ux.maths(
        r"\rho^{*} = \operatorname*{arg\,min}_{\rho_1 \le \rho_2 \le \cdots \le \rho_{15}}"
        r"\;\sum_{k} \left(\rho_k - \hat{\rho}_k\right)^2"
        r"\qquad T^{*}_k : \rho\!\left(S_k, T^{*}_k\right) = \rho^{*}_k",
        [("ρ̂", "density from the model's predicted T and S", "kg m⁻³",
          "EOS-80, phase2.physics.seawater"),
         ("ρ*", "nearest non-decreasing density sequence", "kg m⁻³",
          "isotonic regression (PAVA), pinned against scikit-learn in tests"),
         ("T*", "the temperature with that density at unchanged salinity", "°C",
          "bisection, tolerance 1e-11 °C"),
         ("S", "predicted salinity, held FIXED", "psu", "stage-2 salinity head"),
         ("k", "the 15 standard depth levels, shallow → deep", "m", "config.DEPTHS")],
        "Isotonic regression, not a sort and not a running maximum. A sort permutes levels, so the "
        "500 m value can land at 100 m — a different profile, not a corrected one. A running "
        "maximum only pushes values up, so one heavy level drags everything beneath it. The "
        "isotonic projection is the unique NEAREST non-decreasing sequence, it moves values both "
        "ways, and on an already-stable column it is exactly the identity — which is what makes it "
        "safe to apply to every profile without testing first.")

    # ---------------------------------------------------------------- 03
    ux.inference(
        what=(f"How often the reconstruction emits a column of water that could not physically "
              f"stand up — **{b['fraction']*100:.2f}%** of adjacent level pairs at the float "
              f"points, in **{b['n_profiles_with_violation']} of {baseline['n_profiles']}** "
              f"columns — and what is left after projecting each profile onto the nearest stable "
              f"one."),
        conclude=(f"The guarantee is free in accuracy terms: **{baseline['rmse_cost_degC']:+.4f} "
                  f"°C** against independent Argo, against a headline error of "
                  f"{baseline['metrics_before']['rmse']:.4f}. Soft penalties make violations rare; "
                  f"this makes them absent, and the count afterwards is arithmetic rather than a "
                  f"hope."),
        limits=[
            ("It cannot be applied to the shipped deliverable. Stage 1 predicts temperature "
             "alone, and density needs salinity at depth, so static stability is not a well-posed "
             "question there — the same boundary the physics panel draws for mixed-layer depth.",
             "phase2.physics.stability.project_profile raises on salinity=None"),
            ("Stability is necessary, not sufficient. A perfectly stable profile can still be "
             "wrong by a degree at every level; this fixes a class of physical impossibility, not "
             "accuracy.",
             f"RMSE {baseline['metrics_before']['rmse']:.4f} → "
             f"{baseline['metrics_after']['rmse']:.4f} °C"),
            ("No model trained with the soft penalty existed before this work, so the comparison "
             "against a soft-constrained model is only available where a --w-stab checkpoint has "
             "been trained and passed in.",
             "train_stage2.py --w-stab, added alongside this feature"),
            ("Salinity is held fixed and only temperature moves. Distributing the correction "
             "across both is defensible and is not what this does.",
             "project_profile: 'the operator moves temperature at FIXED salinity'"),
        ])
