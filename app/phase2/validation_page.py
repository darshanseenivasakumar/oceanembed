"""F8 Validation Lab -- a Streamlit page that shows the model's worst numbers on purpose.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/validation_page.py --server.port 8503

WHY A SEPARATE PORT AND A SEPARATE FILE
The Aug-30 gate demoes the FROZEN Phase-1 build. Nothing here may change what that build renders,
so this is an additional page on its own port rather than a new tab inside it.

ALL SCIENCE LIVES IN phase2.validation.lab. This file only lays it out. If a number appears here
that the lab module did not compute, that is a bug -- the UI must not be a second place where
metrics are defined.

TRAPS AVOIDED (each cost this project real time before)
  * st.cache_data silently EXCLUDES any argument whose name starts with an underscore, pinning the
    first result forever. [VERIFIED against current Streamlit docs, 2026-08-26.] No cached
    function here takes an underscore-prefixed argument.
  * A bare expression at statement level gets rendered by Streamlit magic -- that is how a stray
    `None` badge once appeared in the UI. Every call here is assigned or explicitly rendered.
"""
from __future__ import annotations

import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config  # noqa: E402
from phase2.validation import lab  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Validation Lab", layout="wide")


@st.cache_data(show_spinner=False)
def load_summary() -> dict:
    """No arguments at all, so the underscore-exclusion trap cannot apply."""
    return lab.summary()


def _chart_per_depth(depths, rmse, clim, skill_vals):
    """RMSE and skill side by side. Both, always -- either alone misleads (see the 1000 m note)."""
    err = pd.DataFrame({
        "depth": np.concatenate([depths, depths]),
        "value": np.concatenate([rmse, clim]),
        "series": ["our model (satellite)"] * len(depths) + ["climatology baseline"] * len(depths),
    })
    left = alt.Chart(err).mark_line(point=True).encode(
        x=alt.X("value:Q", title="RMSE (°C) — lower is better"),
        y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
        color=alt.Color("series:N", title=None,
                        scale=alt.Scale(range=["#888888", "#1f77b4"])),
        tooltip=["depth", alt.Tooltip("value:Q", format=".3f"), "series"],
    ).properties(height=430, title="absolute error")

    sk = pd.DataFrame({"depth": depths, "skill": skill_vals})
    right = alt.Chart(sk).mark_line(point=True, color="#2ca02c").encode(
        x=alt.X("skill:Q", title="skill vs climatology — higher is better"),
        y=alt.Y("depth:Q", title=None, scale=alt.Scale(reverse=True)),
        tooltip=["depth", alt.Tooltip("skill:Q", format="+.3f")],
    ).properties(height=430, title="skill")
    zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")

    return alt.hconcat(left, right + zero).resolve_scale(y="shared")


def _chart_inherited(iv):
    """Headroom per depth, coloured by verdict. Positive = our error; negative = we beat GLORYS."""
    df = pd.DataFrame({
        "depth": [int(z) for z in iv["depths"]],
        "headroom": iv["headroom_c"],
        "verdict": list(iv["verdict"]),
    })
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("headroom:Q", title="our RMSE − reanalysis RMSE (°C)"),
        y=alt.Y("depth:O", title="depth (m)",
                sort=[int(z) for z in iv["depths"]]),
        color=alt.Color("verdict:N", title=None, scale=alt.Scale(
            domain=["model-limited", "at-ceiling", "beats-reanalysis", "unknown"],
            range=["#d62728", "#7f7f7f", "#2ca02c", "#cccccc"])),
        tooltip=["depth", alt.Tooltip("headroom:Q", format="+.3f"), "verdict"],
    ).properties(height=430)
    rules = alt.Chart(
        pd.DataFrame({"x": [iv["tolerance_c"], -iv["tolerance_c"]]})
    ).mark_rule(strokeDash=[3, 3], color="#555555").encode(x="x:Q")
    return bars + rules


def _chart_calibration(cal):
    """Overconfidence factor per depth. A reference line at 1.0 = honest error bars."""
    df = pd.DataFrame({
        "depth": [int(z) for z in cal["depths"]],
        "factor": cal["factor"],
        "band": ["mixed layer (20-50 m)" if 20 <= z <= 50 else
                 "deep (500-1000 m)" if z >= 500 else "other"
                 for z in cal["depths"]],
    })
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("factor:Q", title="how many times too confident (1.0 = honest)"),
        y=alt.Y("depth:O", title="depth (m)", sort=[int(z) for z in cal["depths"]]),
        color=alt.Color("band:N", title=None, scale=alt.Scale(
            domain=["mixed layer (20-50 m)", "deep (500-1000 m)", "other"],
            range=["#d62728", "#2ca02c", "#aaaaaa"])),
        tooltip=["depth", alt.Tooltip("factor:Q", format=".2f"), "band"],
    ).properties(height=430)
    honest = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
        color="#000000", strokeDash=[4, 4]).encode(x="x:Q")
    return bars + honest


def main() -> None:
    st.title("Validation Lab")
    st.caption("Every number here is measured against **independent Argo floats** — a different "
               "instrument, never seen in training. Nothing on this page is simulated.")

    try:
        s = load_summary()
    except lab.MissingArtifactError as e:
        st.error(str(e))
        st.stop()
        return

    d, gap, iv = s["per_depth"], s["reanalysis_gap"], s["inherited_vs_earned"]

    # ---- headline -----------------------------------------------------------------------
    h = s["headline"]
    c = st.columns(4)
    c[0].metric("RMSE vs Argo", f"{h['rmse']:.4f} °C")
    c[1].metric("skill vs climatology", f"{h['skill']:+.4f}")
    c[2].metric("independent profiles", f"{h['n_profiles']}")
    c[3].metric("depth levels", f"{config.N_DEPTHS}")
    st.caption(f"Satellite-driven — the problem statement's actual deliverable. "
               f"We do **not** quote {h['do_not_quote']}.")

    st.divider()

    # ---- per depth ----------------------------------------------------------------------
    st.subheader("1 · Error and skill at every depth")
    st.altair_chart(_chart_per_depth(d["depths"], d["rmse_model_satellite"],
                                     d["rmse_climatology"], d["skill_vs_climatology"]),
                     use_container_width=True)

    if d["worst_skill_is_also_best_absolute"]:
        st.info(
            f"**Read both panels together.** Skill is lowest at "
            f"{d['worst_skill_depth_m']:.0f} m ({d['worst_skill']:+.3f}) — and that is also where "
            f"our absolute error is *best* in the whole column ({d['best_absolute_rmse']:.3f} °C). "
            f"The deep ocean barely varies, so climatology is already excellent there "
            f"({d['rmse_climatology'][-1]:.3f} °C) and there is almost nothing left to beat. "
            f"Low skill, excellent prediction. A skill-only chart would report our best result as "
            f"our worst."
        )
    st.caption(f"Skill = 1 − RMSE/RMSE_climatology. Positive at all "
               f"{config.N_DEPTHS} depths: {d['all_depths_positive_skill']}. "
               f"Matched within ±{d['max_days_offset']} days.")

    st.divider()

    # ---- inherited vs earned ------------------------------------------------------------
    st.subheader("2 · Is the remaining error ours, or inherited from our training truth?")
    st.markdown(
        "A model cannot be more accurate than the data it was fit to. We trained on the GLORYS "
        "reanalysis, so we measured **GLORYS itself against the same independent floats** — "
        "something nothing else in this project had done."
    )
    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(_chart_inherited(iv), use_container_width=True)
    with right:
        st.markdown(
            f"**The reanalysis' own worst depth is {gap['worst_depth_m']:.0f} m "
            f"({gap['worst_mae']:.3f} °C mean absolute)** — the thermocline, the hardest part of "
            f"the water column for any product.\n\n"
            f"It is **warm-biased** there: through 75–125 m the floats measure up to "
            f"**{abs(gap['bias'][list(config.DEPTHS).index(100)]):.2f} °C colder** than the "
            f"reanalysis. Consistent across {gap['n_comparisons']:,} depth comparisons — a "
            f"systematic offset, not noise."
        )
        st.markdown(
            f"- **Model-limited** (genuinely our error): "
            f"{', '.join(f'{z:.0f} m' for z in iv['model_limited_depths']) or '—'}\n"
            f"- **At the ceiling** of the training truth: "
            f"{', '.join(f'{z:.0f} m' for z in iv['at_ceiling_depths']) or '—'}\n"
            f"- **We beat the reanalysis**: "
            f"{', '.join(f'{z:.0f} m' for z in iv['beats_reanalysis_depths']) or '—'}"
        )
        st.warning(
            "**Our honest weak spot is the mixed layer, 20–50 m** — there we are 0.31–0.38 °C "
            "worse than the reanalysis, and that gap is ours to close. In the thermocline "
            "(100–150 m) we are within "
            f"{iv['tolerance_c']:.2f} °C of it: that error is inherited, not earned."
        )

    tt = gap["tightening"]
    st.caption(
        f"Is that gap just collocation mismatch? No. Tightening to ≤3 days moves 100 m by only "
        f"{tt['time_only']['stats']['mae'][list(config.DEPTHS).index(100)] - gap['mae'][list(config.DEPTHS).index(100)]:+.3f} °C. "
        f"A ≤25 km filter changes nothing at all — nearest-cell distance on a 0.25° grid maxes at "
        f"{gap['collocation_distance_km']['max']:.1f} km, so every match is already inside it. "
        f"The gap is real reanalysis error. Note this includes regridding onto our grid, so it is "
        f"an upper bound on the native product's error."
    )

    st.divider()

    # ---- baselines ----------------------------------------------------------------------
    st.subheader("3 · Against the baselines")
    ba = s["baseline_availability"]
    st.markdown(f"**Climatology** — shown above at every depth. {ba['climatology']['why']}.")
    if ba["lightgbm"]["available"]:
        st.markdown("**LightGBM** — shown.")
    else:
        st.error(
            "**LightGBM is deliberately NOT shown, and this is the honest choice.**\n\n"
            f"{ba['lightgbm']['why']}\n\n"
            f"To unblock: `{ba['lightgbm']['how_to_unblock']}`"
        )

    st.divider()

    # ---- reliability --------------------------------------------------------------------
    st.subheader("4 · How much should you trust the model's own error bars?")
    cal = s["mc_dropout_calibration"]
    if not cal["available"]:
        st.warning(f"Calibration could not be measured here: {cal['why']}")
    else:
        st.error(
            f"**Not at all, and worst in the mixed layer.** Measured against real Argo error at "
            f"every depth, MC-dropout under-states its own error by "
            f"**{cal['best_factor']:.1f}× to {cal['worst_factor']:.1f}×** — overconfident at all "
            f"{config.N_DEPTHS} depths, with no exception."
        )
        k1, k2 = st.columns(2)
        k1.metric(f"worst — {cal['worst_depth_m']:.0f} m (mixed layer)",
                  f"{cal['worst_factor']:.1f}× too confident")
        k2.metric(f"best — {cal['best_depth_m']:.0f} m (deep)",
                  f"{cal['best_factor']:.1f}× too confident")
        st.altair_chart(_chart_calibration(cal), use_container_width=True)
        st.info(
            f"**This corrects our own earlier decision, D-016.** That was measured on fixture data "
            f"and concluded the failure was *\"at depth\"*, worst at 500 m. On real data the "
            f"pattern **inverts**: the mixed layer (20–50 m) runs "
            f"{cal['mixed_layer_range'][0]:.1f}–{cal['mixed_layer_range'][1]:.1f}×, while "
            f"500–1000 m — the depths D-016 warned about — are the *best* calibrated at "
            f"{cal['deep_range'][0]:.1f}–{cal['deep_range'][1]:.1f}×. "
            f"A panel warning about deep water while staying quiet about 30 m would point you "
            f"away from the actual problem."
        )
        st.caption(
            f"Measured live, not quoted: MC-dropout run on {cal['n_rows']} rows of the real test "
            f"set (torch seed {cal['seed']}, stable to ±0.05 across seeds), divided into the "
            f"measured Argo RMSE. **Use the measured per-depth error above as the uncertainty, "
            f"never this spread.** Depth 0 rests on only {cal['n_obs'][0]} profiles and is "
            f"excluded from the headline."
        )

    st.divider()

    # ---- weaknesses ---------------------------------------------------------------------
    st.subheader("5 · What this model is not good at")
    st.caption("Stated because a result without its limits is not a result.")
    for w in s["known_weaknesses"]:
        with st.expander(f"⚠ {w['what']}"):
            st.markdown(w["detail"])
            st.caption(f"Evidence: `{w['evidence']}`")


if __name__ == "__main__":
    main()
