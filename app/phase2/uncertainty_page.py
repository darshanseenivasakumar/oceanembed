"""Where the model does not know, and how much that has been checked. (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/uncertainty_page.py --server.port 8513

WHY THIS VIEW
A reconstruction that reports only a temperature invites a reader to trust every cell equally, and
they are not equal. The network emits a variance beside every mean, so the honest picture is the
two together: colour for what it predicts, fade for how much that prediction should be leaned on.

THE SIGMA HERE IS THE CALIBRATED PHASE-2 SIGMA, AND NEVER MC-DROPOUT
`src/oceanembed/inference/uncertainty.py` produces an MC-dropout spread that D-016 measured
overconfident by 1.6-3.5x at depth. It is Phase-1 and it is not used here. `predict_field` applies
the per-depth scales from `artifacts/uncertainty_calibration.json` through the SAME
`_calibration_applies_to` the point path uses, and this page reads `sigma_is_calibrated` off the
provenance rather than assuming it.

"CALIBRATED" IS STILL NOT "CORRECT", AND THE PAGE SAYS THE NUMBER
After calibration the 2-sigma band covers 91.19% of held-out Argo observations against a nominal
95.4%. That gap is displayed, not buried: a page about uncertainty that overstated its own
uncertainty would be self-refuting.

THE OPACITY SCALE IS RELATIVE TO THE VIEW, AND THAT IS STATED
Sigma at 5 m and sigma at 1000 m are different quantities in size, so one fixed opacity domain
would render whole depths uniformly vivid or uniformly faded. The domain is the 2nd-98th percentile
of sigma AT THE SHOWN DEPTH, and the two end values are printed in degC under the map -- so "faded"
is a claim a reader can check rather than one they have to take.

A FADED CELL ALSO LOOKS COLDER, WHICH IS A REAL RISK
Opacity over a dark ground pulls every hue toward the background, so a low-confidence warm cell can
read as a cool one. The "uncertainty alone" mode exists so that reading is checkable in one click,
and the caveat says so.
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

import _fields                                              # noqa: E402
from oceanembed import config as base                       # noqa: E402
from phase2.derived import mapframe as MF                   # noqa: E402
from phase2.tscast_nio import config as v2config            # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Uncertainty", layout="wide")
alt.data_transformers.disable_max_rows()

MAP_WIDTH, MAP_HEIGHT = MF.map_size(900)
CLR_NOT_WATER = "#3d3d3d"

BOTH = "temperature × confidence"
SIGMA_ONLY = "uncertainty alone"

#: Opacity of the least-confident cell. Not 0 -- a cell the model is unsure about still HAS a
#: prediction, and fading it to invisible would make it indistinguishable from land.
ALPHA_MIN, ALPHA_MAX = 0.18, 1.0


@st.cache_data(show_spinner=False)
def calibration() -> dict:
    """The shipped calibration artifact, or an empty dict. Read, never hardcoded -- every number
    this page quotes about its own uncertainty has to move when the artifact does."""
    p = base.art("uncertainty_calibration.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def slice_frame(date_str: str, depth_m: float, stage: int, version: str,
                device: str | None) -> pd.DataFrame:
    f = _fields.field(date_str, stage, version, _fields.DEFAULT_KEEP, device)
    k = MF.nearest_level(v2config.DEPTHS, depth_m)
    d = MF.add_edges(MF.level_frame(np.asarray(f["temperature"])[:, :, k],
                                    f["land_mask"], base.LAT, base.LON,
                                    extra={"sigma": np.asarray(f["sigma"])[:, :, k]}))
    df = pd.DataFrame(d)
    df.attrs["level_m"] = float(v2config.DEPTHS[k])
    df.attrs["date"] = f["date"]
    df.attrs["calibrated"] = bool(f["provenance"].get("sigma_is_calibrated"))
    df.attrs["why"] = f["provenance"].get("sigma_calibration_note", "")
    return df


@st.cache_data(show_spinner=False)
def sigma_by_depth(date_str: str, stage: int, version: str, device: str | None) -> pd.DataFrame:
    """Basin-wide sigma at each of the 15 levels: median, and the 10th-90th percentile spread.

    The median rather than the mean, because a handful of eddy cells with very large sigma would
    drag a mean and make every depth look equally uncertain.
    """
    f = _fields.field(date_str, stage, version, _fields.DEFAULT_KEEP, device)
    sig = np.asarray(f["sigma"])
    rows = []
    for k, z in enumerate(v2config.DEPTHS):
        col = sig[:, :, k]
        col = col[np.isfinite(col)]
        if col.size == 0:
            continue                       # no water at this level anywhere -- omit, do not plot 0
        rows.append({"depth": float(z), "median": float(np.median(col)),
                     "p10": float(np.percentile(col, 10)), "p90": float(np.percentile(col, 90)),
                     "n": int(col.size)})
    return pd.DataFrame(rows)


def map_chart(df: pd.DataFrame, level_m: float, mode: str, lo: float, hi: float):
    """The basin at one depth. Two modes, because the double encoding needs a way to be checked."""
    common = dict(
        x=alt.X("lon0:Q", title="longitude (°E)", scale=alt.Scale(nice=False, zero=False)),
        x2="lon1:Q",
        y=alt.Y("lat0:Q", title="latitude (°N)", scale=alt.Scale(nice=False, zero=False)),
        y2="lat1:Q",
        tooltip=[alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                 alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                 alt.Tooltip("value:Q", format=".2f", title="T (°C)"),
                 alt.Tooltip("sigma:Q", format=".3f", title="σ (°C)"),
                 alt.Tooltip("kind:N", title="cell")])

    if mode == SIGMA_ONLY:
        enc = dict(common, color=alt.condition(
            "isValid(datum.sigma)",
            alt.Color("sigma:Q", title=f"σ at {level_m:.0f} m (°C)",
                      scale=alt.Scale(scheme="inferno", domain=[lo, hi], clamp=True),
                      legend=alt.Legend(orient="right")),
            alt.value(CLR_NOT_WATER)))
    else:
        enc = dict(
            common,
            color=alt.condition(
                "isValid(datum.value)",
                alt.Color("value:Q", title=f"T at {level_m:.0f} m (°C)",
                          scale=alt.Scale(scheme="turbo"),
                          legend=alt.Legend(orient="right")),
                alt.value(CLR_NOT_WATER)),
            # Reversed on purpose: the SMALLEST sigma is the most opaque. `clamp` keeps the 2% tails
            # at the ends of the range instead of extrapolating past full opacity.
            opacity=alt.Opacity("sigma:Q", title="confidence",
                                scale=alt.Scale(domain=[lo, hi], range=[ALPHA_MAX, ALPHA_MIN],
                                                clamp=True),
                                legend=None))

    # `invalid=None` keeps land and below-seafloor cells: dropped, they leave a hole a reader
    # cannot tell from a low-confidence region, which on THIS page is the one confusion that
    # matters. See the click map for the full note.
    return (alt.Chart(df).mark_rect(invalid=None).encode(**enc)
            .properties(width=MAP_WIDTH, height=MAP_HEIGHT))


def depth_chart(df: pd.DataFrame, level_m: float):
    """Sigma against depth: where in the water column the model is least sure."""
    if df.empty:
        return None
    y = alt.Y("depth:Q", scale=alt.Scale(reverse=True), title="depth (m)")
    band = alt.Chart(df).mark_area(opacity=0.25, color="#d95926").encode(
        y=y, x=alt.X("p10:Q", title="σ (°C)", scale=alt.Scale(zero=False, nice=False)), x2="p90:Q")
    line = alt.Chart(df).mark_line(point=True, color="#d95926", strokeWidth=2).encode(
        y=y, x=alt.X("median:Q", title="σ (°C)", scale=alt.Scale(zero=False, nice=False)),
        tooltip=[alt.Tooltip("depth:Q", title="m"),
                 alt.Tooltip("median:Q", format=".3f", title="median σ"),
                 alt.Tooltip("p10:Q", format=".3f"), alt.Tooltip("p90:Q", format=".3f"),
                 alt.Tooltip("n:Q", format=",", title="cells")])
    rule = alt.Chart(pd.DataFrame({"depth": [level_m]})).mark_rule(
        color="#787878", strokeDash=[4, 3]).encode(y="depth:Q")
    return (band + line + rule).properties(height=380)


def explainer(calibrated: bool, cal: dict, level_m: float) -> Explainer:
    after = cal.get("summary_after") or {}
    cov2 = after.get("cov2_mean")
    target = after.get("target_cov2")
    n_eval = cal.get("n_eval_profiles")
    scale = (cal.get("scales") or {}).get(str(int(level_m)))

    caveats = [
        Caveat("The fade is relative to this view, not an absolute scale.",
               "The opacity range is the 2nd–98th percentile of σ at the depth on screen, because "
               "σ near the surface and σ at 1000 m differ enough in size that one fixed range "
               "would render whole depths uniformly vivid or uniformly faded. The two end values "
               "are printed under the map, so a comparison between two views is one you can make "
               "deliberately rather than one the colours imply.",
               "app/phase2/uncertainty_page.py — the caption under the map"),
        Caveat("A faded cell also looks colder than it is.",
               "Opacity over a dark background pulls every hue toward that background, so a "
               "low-confidence warm cell can read as a cool one. Switch to “uncertainty alone” to "
               "read σ without the temperature hue interfering.",
               "the view selector in the sidebar"),
        Caveat("This is the calibrated Phase-2 σ, never the Phase-1 MC-dropout spread.",
               "The MC-dropout uncertainty in src/oceanembed/inference/uncertainty.py was measured "
               "overconfident by 1.6–3.5× at depth and is not used anywhere on this page.",
               "docs/DECISIONS.md D-016"),
    ]
    if calibrated and cov2 is not None:
        caveats.append(Caveat(
            "Calibrated does not mean correct — the band is still too narrow.",
            f"After calibration the ±2σ band covers **{cov2:.1%}** of held-out Argo observations "
            f"against a nominal **{target:.1%}**"
            + (f", measured on {n_eval:,} profiles held out after {cal.get('split')}." if n_eval
               else ".")
            + " So it is improved, not calibrated in the strict sense, and a 2σ band here should "
              "be read as “about right, slightly optimistic” rather than as a 95% interval.",
            "artifacts/uncertainty_calibration.json -> summary_after"))
    else:
        caveats.append(Caveat(
            "The σ on screen is RAW model output, with no calibration applied.",
            "The calibration artifact does not apply to the checkpoint currently loaded, so these "
            "values are the network's own variance and have no measured coverage at all.",
            "artifacts/uncertainty_calibration.json"))

    note = ("σ is the standard deviation the network predicts at that cell and depth, in °C — the "
            "second output of the β-NLL loss, beside the temperature itself. α is the opacity a "
            "cell is drawn with. The relationship is monotone and decreasing, not literally "
            "reciprocal: α runs linearly from "
            f"{ALPHA_MAX:g} down to {ALPHA_MIN:g} across the σ range printed under the map.")
    if scale:
        note += (f" At {level_m:.0f} m the σ shown has been multiplied by {float(scale):.4f}, the "
                 f"per-depth calibration scale fitted on train-window Argo.")

    return Explainer(
        title="Temperature and confidence, on one map",
        plain=("Colour shows the predicted temperature. Transparency shows how confident the model "
               "is — vivid means confident, faded means uncertain, which tends to happen in "
               "dynamic eddies and where the surface satellite inputs are sparsest."),
        formula=r"\alpha \;=\; \alpha_{\max} - (\alpha_{\max}-\alpha_{\min})\,"
                r"\frac{\sigma - \sigma_{2\%}}{\sigma_{98\%} - \sigma_{2\%}}",
        formula_note=note,
        how_to_read=("Don't quote a faded region's exact number. It is a hint about *where* the "
                     "model is guessing, not a value to carry into a decision. The panel below "
                     "the map shows which depths are least certain basin-wide — the peak sits at "
                     "the thermocline, where temperature changes fastest with depth and a small "
                     "error in depth becomes a large error in temperature."),
        caveats=tuple(caveats),
        references=(
            "Seitzinger et al., β-NLL: on the pitfalls of heteroscedastic regression (the loss "
            "that produces this σ). See docs/phase2/tscast_output_schema.md §3.",))


def main() -> None:
    st.title("Where the model is unsure — and how far that has been checked")
    subtitle = st.empty()          # filled once the view mode is known -- see below

    with st.sidebar:
        st.header("What to show")
        stage = 1
        ver = _fields.version(stage)
        date_str = _fields.date_picker(stage, label="date", key="un_date")
        depth_m = st.select_slider("depth for the map", options=list(v2config.DEPTHS),
                                   value=100, format_func=lambda d: f"{d} m")
        mode = st.radio("view", [BOTH, SIGMA_ONLY],
                        help="The second mode drops the temperature hue so σ can be read on its "
                             "own — the fade in the first mode also darkens the colour.")
        device = _fields.device_picker(key="un_dev")

    try:
        df = slice_frame(date_str, float(depth_m), stage, ver, device)
        prof = sigma_by_depth(date_str, stage, ver, device)
    except Exception as e:
        st.error(f"Could not reconstruct {date_str}: {e}")
        st.info("The satellite bundle and the checkpoint must both be on this machine.")
        return

    level_m = float(df.attrs["level_m"])
    calibrated = bool(df.attrs["calibrated"])
    cal = calibration()

    water = df["sigma"][np.isfinite(df["sigma"])]
    if water.empty:
        st.warning(f"No cell in the basin has water at {level_m:.0f} m on this date.")
        return
    lo, hi = (float(np.percentile(water, 2)), float(np.percentile(water, 98)))
    if hi <= lo:
        hi = lo + 1e-6                    # a uniform-sigma level would give a degenerate scale

    # Written only now, because a subtitle that describes the OTHER mode is exactly the kind of
    # caption-not-matching-its-chart this project keeps finding.
    subtitle.caption(
        "Colour is the prediction. Fade is the model's own doubt, after calibration against "
        "independent Argo floats." if mode == BOTH else
        "Colour IS the doubt: the calibrated σ the model predicts at each cell, in °C. Temperature "
        "is not shown in this mode.")

    if not calibrated:
        st.warning(f"**σ on this page is uncalibrated.** {df.attrs['why']}")

    st.altair_chart(map_chart(df, level_m, mode, lo, hi), use_container_width=False)
    n = MF.counts({"kind": df["kind"].to_numpy()})
    st.caption(
        f"{df.attrs['date']} · {level_m:.0f} m · σ spans **{lo:.3f}–{hi:.3f} °C** across this view "
        f"(2nd–98th percentile of {n[MF.WATER]:,} cells with water); "
        f"{'vivid = low σ, faded = high σ' if mode == BOTH else 'bright = high σ'}. "
        f"Grey is land or below the seafloor, not a low-confidence prediction.")

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.subheader("Which depths the model is least sure about")
        chart = depth_chart(prof, level_m)
        if chart is None:
            st.info("No finite σ anywhere on this date.")
        else:
            st.altair_chart(chart, use_container_width=True)
            worst = prof.loc[prof["median"].idxmax()]
            best = prof.loc[prof["median"].idxmin()]
            st.caption(
                f"Line is the basin median σ, band is the 10th–90th percentile. Least certain at "
                f"**{worst['depth']:.0f} m** (median {worst['median']:.3f} °C), most certain at "
                f"**{best['depth']:.0f} m** ({best['median']:.3f} °C). Dashed line marks the depth "
                f"drawn above.")

    with right:
        st.subheader("What “calibrated” means here")
        scales = cal.get("scales") or {}
        after = cal.get("summary_after") or {}
        if not scales:
            st.info("No calibration artifact on this machine — σ is raw network output.")
        else:
            c1, c2, c3 = st.columns(3)
            s_here = scales.get(str(int(level_m)))
            c1.metric(f"scale at {level_m:.0f} m", f"×{float(s_here):.3f}" if s_here else "—")
            if after.get("cov2_mean") is not None:
                c2.metric("±2σ actually covers", f"{after['cov2_mean']:.1%}",
                          delta=f"{after['cov2_mean'] - after['target_cov2']:+.1%} vs nominal",
                          delta_color="inverse")
            c3.metric("held-out profiles", f"{cal.get('n_eval_profiles', 0):,}")
            st.markdown(
                f"Every predicted σ is multiplied by a factor fitted per depth on Argo profiles "
                f"from **before {cal.get('split')}**, then scored on profiles from after it — so "
                f"the coverage number beside it is measured on data the fit never saw. "
                f"The factors run from **×{min(map(float, scales.values())):.3f}** to "
                f"**×{max(map(float, scales.values())):.3f}**; the largest correction is at the "
                f"thermocline, where the raw model was most overconfident.")
            tbl = pd.DataFrame({"depth (m)": [int(k) for k in scales],
                                "σ multiplied by": [round(float(v), 4) for v in scales.values()]})
            with st.expander("Per-depth calibration scales"):
                st.dataframe(tbl, hide_index=True, width="stretch")

    render(explainer(calibrated, cal, level_m))


if __name__ == "__main__":
    main()
