"""TS-Cast-NIO v2 — explain every output, with the ground-truth check beside every number.

OWNER: Unit B (Darshan). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is neither touched nor
imported.

    streamlit run app/phase2/tscast_page.py --server.port 8507

WHY A SEPARATE PORT AND FILE
The Aug-30 gate demoes the FROZEN Phase-1 build. Nothing here may change what that build renders,
so this is an additional page on its own port (8503 is the F8 Validation Lab).

THE ONE RULE THIS FILE OBEYS
Every number shown here comes out of a prediction record or a measured metrics artifact. This file
lays out; it does not compute science. If a figure appears here that neither the predictor nor the
metrics JSON produced, that is a bug -- the UI must never become a second place where metrics are
defined, because two definitions drift and only one can be right.

TRAPS AVOIDED (each cost this project real time before)
  * st.cache_data silently EXCLUDES any argument whose name starts with an underscore, pinning the
    first result forever. No cached function here takes an underscore-prefixed argument.
  * A bare expression at statement level gets rendered by Streamlit magic -- that is how a stray
    `None` badge once appeared in the UI. Every call here is assigned or explicitly rendered.
  * altair only. `app/panels/_viz.py` records why; the demo laptop is not the build laptop.
  * Two skill definitions exist and read very differently (1 - RMSE/RMSEclim vs Murphy). Both are
    always shown, always labelled, and never mixed.
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
from phase2.tscast_nio import ui_tables as T  # noqa: E402

st.set_page_config(page_title="OceanEmbed — TS-Cast-NIO v2", layout="wide")

# The metrics file and the checkpoint must come from the SAME run. Showing stage-2 numbers above a
# Profile tab that reconstructs from the stage-1 checkpoint is precisely the CACHED-vs-LIVE lie
# this page exists to prevent, and nothing in the UI would look wrong while it happened.
_RUNS = (("tscast_stage2_s2_metrics.json", "tscast_stage2_s2.pt"),
         ("tscast_stage1_metrics.json", "tscast_stage1.pt"))


def _newest_run() -> tuple[str, str]:
    """The newest run for which BOTH the metrics and its checkpoint are present.

    Named explicitly rather than globbed: a page that picked up whatever appeared in artifacts/
    would render an ablation run as if it were the shipped model.
    """
    for mname, cname in _RUNS:
        mp, cp = config.art(mname), config.art(cname)
        if os.path.exists(mp) and os.path.exists(cp):
            return mp, cp
    return config.art("tscast_stage1_metrics.json"), config.art("tscast_stage1.pt")


METRICS, CHECKPOINT = _newest_run()
GLORYS_VS_ARGO = config.art("glorys_vs_argo.json")
TSEQ = config.art("tseq_ablation.json")
MC_CAL = config.art("mc_calibration.json")

# The last day GLORYS truth exists for. Past this a prediction is a FORECAST and carries no
# accuracy claim, because nothing has been measured against it.
LAST_GLORYS = "2026-06-23"

SMOKE_SAMPLES = 10_000   # below this a run is a load-test fixture, not a result


# ── loading (cached, no underscore-prefixed arguments anywhere) ────────────────────────

@st.cache_data(show_spinner=False)
def load_metrics() -> dict | None:
    if not os.path.exists(METRICS):
        return None
    with open(METRICS, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _predictor_version() -> str:
    """A key that changes whenever the model, its bundle resolution, or the loader code changes.

    WHY THIS EXISTS. `st.cache_resource` keys on the function's ARGUMENTS. It does not see the
    source of modules the function imports. On 2026-09-02 `inference.py` was fixed at 19:27 to load
    the bundle the checkpoint was trained on; a server started at 19:17 went on serving a predictor
    object built 9.5 minutes earlier from the GLORYS bundle, and the Profile tab kept rendering
    18.84 degC at 100 m against a float reading 26.85 -- an 8.01 degC error -- while the same call
    outside Streamlit returned 26.24. The code was fixed and the screen was not.

    Nothing about that was visible: no error, no warning, and a full-looking profile. So the cache
    is now versioned on everything that can change the answer -- the checkpoint bytes and the two
    modules that decide which inputs reach the model.
    """
    import hashlib
    from phase2.tscast_nio import dataset as _D, inference as _I

    h = hashlib.sha256()
    for p in (CHECKPOINT, _I.__file__, _D.__file__):
        try:
            s = os.stat(p)
            h.update(f"{p}:{s.st_mtime_ns}:{s.st_size}".encode())
        except OSError:
            h.update(f"{p}:missing".encode())
    return h.hexdigest()[:16]


@st.cache_resource(show_spinner="loading the checkpoint…")
def load_predictor(version: str):
    """The real model, and the SAME run the metrics above came from. Never a stub -- an untrained
    network would render as a perfectly confident profile.

    `version` is not used in the body: it exists so the cache key moves when the checkpoint or the
    loading code does. See `_predictor_version`.
    """
    from phase2.tscast_nio.inference import TSCastPredictor

    return TSCastPredictor(checkpoint=CHECKPOINT)


def _clean(text: str) -> str:
    """Strip numpy scalar reprs that older metrics files embedded in free text."""
    return str(text).replace("np.str_(", "").replace("')", "'").replace("'", "")


def provenance_banner(m: dict | None) -> None:
    """Say what produced these numbers before showing any of them."""
    if m is None:
        st.error(
            f"No metrics artifact at `{METRICS}`. Nothing on this page can be shown, because "
            "every number here comes from a measured run. Train a model first:\n\n"
            "`PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 --data daily "
            "--t-seq 11 --decoder simple --loss nll`")
        st.stop()

    n_ch = len(m.get("channels", []))
    samples = int(m.get("train_samples", 0))
    left, right = st.columns([3, 2])
    with left:
        st.caption(
            f"**{m.get('model')}** · encoder `{m.get('encoder')}` · decoder `{m.get('decoder')}` · "
            f"loss `{m.get('loss')}` (β={m.get('beta_nll')}) · seed {m.get('seed')}")
        st.caption(f"trained on: {_clean(m.get('trained_on', 'UNRECORDED'))}")
    with right:
        st.caption(f"**CACHED** — read from `{os.path.basename(METRICS)}`, written by the training "
                   f"run itself. Nothing on this tab is recomputed in the browser. The Profile tab "
                   f"is **LIVE** from `{os.path.basename(CHECKPOINT)}`, the checkpoint of that "
                   f"same run.")
        st.caption(f"{n_ch} of 7 contract channels · {m.get('argo_profiles', '?')} independent "
                   f"Argo profiles · ±{m.get('max_days_offset', '?')} day collocation")

    if samples and samples < SMOKE_SAMPLES:
        st.error(
            f"**These numbers are a test fixture, not a result.** This checkpoint was trained on "
            f"{samples:,} samples for {m.get('epochs_run')} epoch(s) — enough to prove the load "
            f"path works, nothing more. Do not quote anything on this page until a full run "
            f"replaces it.")
    if n_ch and n_ch < 7:
        st.warning(
            f"**{n_ch} of 7 channels — wind (wu, wv) is absent from this run.** PS requirement 8 "
            f"is not represented in these numbers. Any comparison against a 7-channel run is a "
            f"comparison of two different models.")


# ── tab 1: the profile ─────────────────────────────────────────────────────────────────

def profile_chart(record: dict) -> alt.LayerChart:
    """Temperature against depth with a ±2σ band. Only valid depths are drawn.

    TWO SIGMA ONLY, measured rather than stylistic -- and reported by RANGE, not by mean. Against
    908 held-out Argo profiles the band covers 80.1% to 95.5% depending on depth, against 95.4%
    for a Gaussian of that width. The mean is 91.2%, and quoting only the mean hides the weak
    band: at 50 m coverage is 80.1% and +/-1 sigma falls to 46.1%. Below 75 m it
    recovers to 93-95%. The caption renders the same figures; the Calibration tab renders them per
    depth. One measurement, three views -- if they ever disagree, that is a bug.

    CORRECTED TWICE on 2026-09-02. First it claimed 96.5% coverage and per-depth scales reaching
    5.4x at 100 m, from a calibration fitted while calibrate_uncertainty.py loaded the GLORYS
    bundle for a satellite-trained model. Then it quoted the 91.2% mean alone, which reads as
    uniform coverage the data does not support.
    """
    rows = []
    for k, d in enumerate(record["depths_m"]):
        t, s = record["temperature"][k], record["sigma_t"][k]
        if t is None or s is None:
            continue
        two = 2.0 * float(s)
        rows.append({"depth": d, "temperature": float(t), "sigma2": two,
                     "lo": float(t) - two, "hi": float(t) + two,
                     "why": record["reasons"][k]})
    df = pd.DataFrame(rows)

    band = alt.Chart(df).mark_area(opacity=0.22, color="#1f77b4").encode(
        x=alt.X("lo:Q", title="temperature (°C)", scale=alt.Scale(zero=False)),
        x2="hi:Q",
        y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)))
    line = alt.Chart(df).mark_line(point=True, color="#1f77b4").encode(
        x=alt.X("temperature:Q", scale=alt.Scale(zero=False)),
        y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
        tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                 alt.Tooltip("temperature:Q", format=".2f", title="°C"),
                 alt.Tooltip("sigma2:Q", format=".2f", title="± 2σ °C"),
                 alt.Tooltip("why:N", title="why")])

    layers = [band, line]
    ac = record.get("argo_check")
    if ac and ac.get("argo_temperature"):
        arows = [{"depth": d, "temperature": float(t)}
                 for d, t in zip(record["depths_m"], ac["argo_temperature"]) if t is not None]
        if arows:
            layers.append(
                alt.Chart(pd.DataFrame(arows)).mark_point(
                    color="#d62728", size=70, filled=True, shape="diamond").encode(
                    x=alt.X("temperature:Q", scale=alt.Scale(zero=False)),
                    y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
                    tooltip=[alt.Tooltip("depth:Q", title="depth (m)"),
                             alt.Tooltip("temperature:Q", format=".2f",
                                         title="independent float °C")]))
    return alt.layer(*layers).properties(height=560, title="reconstructed profile, ±2σ")


def render_profile_tab() -> None:
    st.subheader("One point, one date, and everything we know about it")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    lat = c1.number_input("latitude °N", 5.0, 30.0, 15.0, step=0.25)
    lon = c2.number_input("longitude °E", 45.0, 105.0, 68.0, step=0.25)
    date = c3.text_input("date (YYYY-MM-DD)", "2026-05-15")
    c4.caption(" ")
    go = c4.button("reconstruct", type="primary", use_container_width=True)

    if not go:
        st.info("Pick a point in the North Indian Ocean and press **reconstruct**. Every depth "
                "will explain its own error bar, and the nearest independent Argo float — one the "
                "model never saw — is drawn beside the prediction.")
        return

    try:
        pred = load_predictor(_predictor_version())
        record = pred.reconstruct(float(lat), float(lon), date)
    except Exception as e:                                    # refusal with a reason, not a stack
        st.error(f"**Refused.** {type(e).__name__}: {e}")
        return

    if record["forecast"]:
        st.warning(
            f"**FORECAST.** GLORYS truth ends {LAST_GLORYS}; this date is past it. No accuracy "
            f"claim is made for this profile and no Argo check is attached, because nothing has "
            f"been measured against it.")

    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(profile_chart(record), use_container_width=True)
        # The uncertainty statement, in the UI rather than only in a doc. Wording agreed with
        # Unit B (AGENT_SYNC 2026-09-02, Call 3): show the band we measured as honest, refuse the
        # one we measured as too narrow, and say which is which where the number appears.
        st.caption(
            "**The band is ±2σ. Its coverage of independent Argo profiles ranges "
            "80.1% to 95.5% by depth** — a Gaussian of that width would be 95.4%. "
            "The mean is 91.2%, but quoting the mean hides where it is weak: "
            "**at 50 m only 80.1% of floats fall inside the band**, and that is the "
            "number to judge us on. Coverage recovers to 93–95% below 75 m. "
            "**We show no ±1σ band and no confidence percentage:** ±1σ averages "
            "63.9% against 68.3% and drops to 46.1% at 50 m. "
            "The 0 m band is unfitted — only 20 profiles reach it. "
            "Per-depth coverage is on the Calibration tab; this caption is its summary, not a "
            "different measurement.")

    with right:
        render_argo_check(record)

    st.markdown("#### every depth, and why its error bar is that wide")
    rows = T.profile_rows(record)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    s2 = T.stage2_profile_rows(record)
    if s2:
        st.markdown("#### salinity and density at this point")
        st.dataframe(pd.DataFrame(s2), use_container_width=True, hide_index=True)
        st.caption("Density is not predicted: it is EOS-80 evaluated on the temperature and "
                   "salinity above, so it can never disagree with them.")

    n_ref = sum(1 for r in rows if r["temperature (°C)"] is None)
    if n_ref:
        st.caption(f"{n_ref} of {len(rows)} depths are refusals, not blanks. A 1000 m map covers "
                   f"75.8% of ocean cells and must say so rather than render an empty square.")

    with st.expander("provenance — what produced this record"):
        st.json(record["provenance"])


def render_argo_check(record: dict) -> None:
    """Never a number without its ground-truth check beside it."""
    st.markdown("#### checked against an independent float")
    ac = record.get("argo_check")
    if ac is None:
        if record["forecast"]:
            st.info("No check: this is a forecast, so no observation exists to check it against.")
        else:
            st.warning(
                "**No independent float within range of this point and date.** That is a real "
                "statement about Argo coverage, not a failure — this part of the ocean was not "
                "sampled near this date. The prediction stands unverified here, and is labelled "
                "so rather than shown as if it had been confirmed.")
        return

    q = ac.get("quality", "?")
    colour = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🟠", "REJECT": "🔴"}.get(q, "⚪")
    st.markdown(f"{colour} **{q}** — {ac.get('quality_reason', '')}")
    c1, c2 = st.columns(2)
    c1.metric("distance", f"{ac['distance_km']:.0f} km")
    c2.metric("time offset", f"{ac['days_offset']:.0f} days")

    rows = T.argo_comparison_rows(record)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     height=330)
        st.caption(f"Profile `{ac.get('profile_id')}` from `{ac.get('source')}`. This float is "
                   f"**independent** — never used for training.")
    else:
        st.caption("The float matched, but reported no levels overlapping our depths.")


# ── tab 2: the benchmark ───────────────────────────────────────────────────────────────

#: Checked with the palette validator, not chosen by eye, and checked against BOTH surfaces --
#: no theme is pinned in this project, so Streamlit follows the viewer's browser and the demo
#: laptop decides the mode, not us. This pair passes all six checks in light AND dark:
#: lightness band, chroma floor, CVD separation (worst adjacent dE 25.4 protan), normal-vision
#: floor (32.3) and 3:1 contrast.
#:
#: The previous pair was #1f77b4 with #999999: the grey FAILED the chroma floor outright and sat
#: at 2.78:1 contrast. The first fix, #eb6834, passed on white and FAILED the dark lightness band
#: at 0.671 -- which is exactly why the rule is to validate per surface instead of flipping.
CLR_MODEL, CLR_CLIM = "#2a78d6", "#d95926"

#: Annotation ink. Streamlit themes AXIS text but NOT free `mark_text`, which defaults to BLACK --
#: measured on the running page as rgb(0,0,0) on a rgb(14,17,23) surface, 1.11:1, invisible. Since
#: no theme is pinned, this grey is the balanced optimum across both surfaces: 4.30:1 on the light
#: surface and 4.28:1 on the dark one. Labels wear text ink, never a series colour.
INK_ANNOTATION = "#787878"
NAME_MODEL, NAME_CLIM = "TS-Cast-NIO v2", "climatology baseline"


def _depth_error_chart(depths, rmse, clim) -> alt.LayerChart:
    """RMSE against depth, ours vs the baseline. The one plot that shows we understand the ocean.

    THE BUG THIS REPLACES
    The old chart was `mark_line(point=True)` with x=RMSE and y=depth. Altair sorts a line by its
    X encoding unless told otherwise, and RMSE is NOT monotonic in depth (0.40 at the surface,
    1.19 at 50 m, 1.08 at 75 m, 1.22 at 100 m), so the line was drawn in ascending-RMSE order and
    came out as a zigzag through itself. The numbers were right and the picture was unreadable --
    which is worse than no picture, because it looks like the model is unstable. `order` fixes it.

    WHAT THE SHAPE SAYS, AND WHAT IT MUST NOT OVERSTATE
    Error is small at the surface (SST is half-observed), peaks in the THERMOCLINE where the
    vertical gradient is steepest and a surface field constrains depth least, then collapses below
    500 m where the ocean barely varies. That is the physics, visible at a glance.

    But the model does NOT beat climatology everywhere: at 1000 m climatology wins by 0.012 degC
    (0.293 vs 0.305). 14 of 15 depths, not 15. The shaded band is therefore drawn from the SIGNED
    difference and the crossover is labelled outright, because a jury that later finds the one
    depth we glossed over stops believing the fourteen we did not.
    """
    df = pd.DataFrame({"depth": depths, "model": rmse, "clim": clim})
    df["gain"] = df["clim"] - df["model"]

    long = pd.DataFrame({
        "depth": list(depths) * 2,
        "value": list(rmse) + list(clim),
        "series": [NAME_MODEL] * len(depths) + [NAME_CLIM] * len(depths)})

    y = alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True))
    # Headroom on x so the direct labels sit INSIDE the plot. Without it they are clipped by the
    # right edge -- the annotation that carries the argument is the one that gets cut.
    x_max = float(max(max(rmse), max(clim))) * 1.5
    x_scale = alt.Scale(domain=[0.0, x_max], nice=False)

    # The gap between the curves IS the skill. Shaded so it reads as one quantity, not two lines
    # that happen to be apart.
    band = alt.Chart(df).mark_area(opacity=0.15, color=CLR_MODEL).encode(
        y=y, x=alt.X("model:Q", title="RMSE (°C) — lower is better", scale=x_scale),
        x2="clim:Q")

    lines = alt.Chart(long).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=55, filled=True)
    ).encode(
        x=alt.X("value:Q", title="RMSE (°C) — lower is better", scale=x_scale),
        y=y,
        # WITHOUT THIS the line follows ascending RMSE instead of depth. See the docstring.
        order=alt.Order("depth:Q"),
        color=alt.Color("series:N", title=None,
                        scale=alt.Scale(domain=[NAME_MODEL, NAME_CLIM],
                                        range=[CLR_MODEL, CLR_CLIM]),
                        legend=alt.Legend(orient="bottom", direction="horizontal",
                                          title=None)),
        tooltip=["depth", alt.Tooltip("value:Q", format=".4f"), "series"],
    )

    # Direct-label the two depths that carry the argument -- the extremes only, never every point.
    k_gain = int(max(range(len(depths)), key=lambda i: df["gain"][i]))
    k_worst = int(max(range(len(depths)), key=lambda i: rmse[i]))
    notes = pd.DataFrame([
        {"depth": depths[k_gain], "value": clim[k_gain],
         "label": f"widest gain {df['gain'][k_gain]:+.2f} °C"},
        {"depth": depths[k_worst], "value": rmse[k_worst],
         "label": f"our worst {rmse[k_worst]:.2f} °C · thermocline"},
    ])
    text = alt.Chart(notes).mark_text(
        align="left", dx=8, dy=-6, fontSize=12, color=INK_ANNOTATION
    ).encode(y=y, x="value:Q", text="label:N")

    layers = [band, lines, text]

    # The one depth where the baseline wins. Called out rather than left for someone to find.
    losing = df[df["gain"] < 0]
    if not losing.empty:
        r = losing.iloc[losing["gain"].argmin()]
        layers.append(alt.Chart(pd.DataFrame([{
            "depth": r["depth"], "value": max(r["model"], r["clim"]),
            "label": f"climatology wins by {abs(r['gain']):.3f} °C here"}])
        ).mark_text(align="left", dx=8, dy=10, fontSize=12, color=INK_ANNOTATION
                    ).encode(y=y, x="value:Q", text="label:N"))

    return alt.layer(*layers).properties(
        height=430, title="error against independent Argo, by depth"
    ).configure_axis(grid=True, gridOpacity=0.18, gridDash=[])


def render_benchmark_tab(m: dict) -> None:
    st.subheader("How wrong is it, per depth, against floats it never saw")
    mm = m["metrics"]
    depths = mm["depths_m"]

    o = mm.get("overall") or {}

    head = T.headline(m)

    def show(key: str, fmt: str, unit: str = "") -> str:
        """A missing or non-finite number says so. `nan` on a slide reads as a bug, not a gap."""
        v = head.get(key)
        return "not recorded" if v is None else format(v, fmt) + unit

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("overall RMSE", show("overall RMSE", ".4f", " °C"))
    c2.metric("skill  1 − RMSE/RMSEclim", show("skill 1−RMSE/RMSEclim", "+.4f"))
    c3.metric("skill  Murphy", show("skill Murphy", "+.4f"))
    c4.metric("climatology RMSE", show("climatology RMSE", ".4f", " °C"))
    if head.get("climatology RMSE") is None:
        c4.caption("this artifact predates the field; re-train to populate it")
    st.caption(
        "**Two skill definitions, both shown, never mixed.** `1 − RMSE/RMSEclim` is what the frozen "
        "Phase-1 headline (+0.387) used; Murphy (`1 − MSE/MSEclim`) is roughly its square and reads "
        "much larger for the same model. Quoting one as the other inflates the result. The "
        "climatology RMSE sits beside them because skill without its baseline is unreadable — at "
        "1000 m this model has its *worst* skill and its *best* absolute error at the same time.")

    df = pd.DataFrame(T.benchmark_rows(m))

    chart = _depth_error_chart(depths, [float(v) for v in mm["rmse"]],
                               [float(v) for v in mm["rmse_climatology"]])

    left, right = st.columns([3, 2])
    left.altair_chart(chart, use_container_width=True)
    right.dataframe(df, use_container_width=True, hide_index=True, height=430)

    w = mm.get("window") or {}
    st.caption(
        f"Test window {w.get('start', '?')} … {w.get('end', '?')} · reference "
        f"`{mm.get('reference', '?')}` · bias convention: {mm.get('bias_convention', '?')} · "
        f"n is per depth and falls with depth because floats stop reporting, not because cells "
        f"are dropped.")

    ca = m.get("compare_against") or None
    if ca:
        st.info(
            f"**Comparator: {ca.get('which')}** — RMSE {ca.get('incumbent_rmse')} °C, skill "
            f"{ca.get('incumbent_skill_rmse_ratio')}. {ca.get('why_not_the_headline_0_9638', '')}")
    st.warning(
        "**Do not compare this against the monthly numbers.** The daily model is scored on 2026 "
        "Argo and the monthly model on 2022 Argo. Different test sets — a difference between them "
        "is not an improvement. Only rows measured on the same profiles may be subtracted.")


# ── tab 3: calibration — the figure the paper does not contain ─────────────────────────

def render_calibration_tab(m: dict) -> None:
    st.subheader("Is the error bar honest?")
    st.caption(
        "A model that says ±0.5 °C and is wrong by 2 °C is worse than one that admits ±2 °C. "
        "TS-Cast (Chae, Donohue & Park 2026) contains **no calibration or coverage figure at all** "
        "[VERIFIED from the full text], so there is nothing to copy here — this is measured.")

    cal = m.get("calibration") or {}
    if not cal:
        st.error("No calibration block in the metrics artifact.")
        return

    depths = sorted(int(d) for d in cal)
    df = pd.DataFrame(T.calibration_rows(m))

    mc = m.get("mc_dropout_for_comparison") or {}
    ratios = [r for r in df["ratio RMSE/σ"] if r is not None]
    if ratios:
        c1, c2 = st.columns(2)
        c1.metric("v2 calibration ratio", f"{min(ratios):.2f} – {max(ratios):.2f}")
        c2.metric("MC-dropout, same measure", f"{mc.get('best', '?')} – {mc.get('worst', '?')}",
                  help=str(mc.get("source", "")))
        st.caption(
            "1.0 is honest. Above 1 the band is too narrow (overconfident); below 1 it is too wide, "
            "which is also not honest. Both columns use the identical aggregation — RMSE and RMS(σ) "
            "pooled per depth *then* divided — so they are directly comparable. Averaging per-point "
            "ratios instead inflates the shallow end roughly 2×.")

    ratio_df = df.dropna(subset=["ratio RMSE/σ"])
    chart = alt.Chart(ratio_df).mark_bar(color="#1f77b4").encode(
        x=alt.X("ratio RMSE/σ:Q", title="RMSE / RMS(σ)   —   1.0 is honest"),
        y=alt.Y("depth (m):O", title="depth (m)", sort=depths),
        tooltip=list(ratio_df.columns)).properties(height=400, title="calibration ratio by depth")
    rule = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
        color="#d62728", strokeDash=[5, 4]).encode(x="x:Q")

    have_cov = df["within ±1σ"].notna().any()
    left, right = st.columns(2)
    left.altair_chart(alt.layer(chart, rule), use_container_width=True)

    if have_cov:
        cov = pd.DataFrame({
            "depth (m)": list(df["depth (m)"]) * 2,
            "coverage": [float(v) for v in df["within ±1σ"]] + [float(v) for v in df["within ±2σ"]],
            "band": ["within ±1σ"] * len(df) + ["within ±2σ"] * len(df)})
        cov_chart = alt.Chart(cov).mark_bar().encode(
            x=alt.X("coverage:Q", title="fraction of independent floats inside the band",
                    axis=alt.Axis(format="%")),
            y=alt.Y("depth (m):O", sort=depths, title=None),
            color=alt.Color("band:N", title=None,
                            scale=alt.Scale(range=["#1f77b4", "#aec7e8"])),
            yOffset="band:N",
            tooltip=["depth (m)", "band", alt.Tooltip("coverage:Q", format=".1%")],
        ).properties(height=400, title="coverage: do the floats actually land inside?")
        targets = alt.Chart(pd.DataFrame({"x": [0.683, 0.954]})).mark_rule(
            color="#d62728", strokeDash=[5, 4]).encode(x="x:Q")
        right.altair_chart(alt.layer(cov_chart, targets), use_container_width=True)
        right.caption("Dashed lines are the Gaussian targets, 68.3% and 95.4%.")
    else:
        right.info(
            "Coverage was not measured in this run. It is computed by `calibration()` in "
            "`train_stage1.py`; re-train to populate it. It is deliberately **not** computed here "
            "— the UI must not become a second place where a metric is defined.")

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"Method: {m.get('calibration_method', '')}")


# ── tab 4: honesty ─────────────────────────────────────────────────────────────────────

def render_honesty_tab(m: dict) -> None:
    st.subheader("What this model cannot do")

    n_ch = len(m.get("channels", []))
    st.markdown(f"##### 1. Inputs — {n_ch} of the contract's 7 channels")
    st.write(f"`{list(m.get('channels', []))}`")
    st.caption(m.get("channels_note", ""))
    if n_ch < 7:
        st.warning(
            "Wind (wu, wv) is **absent**. PS requirement 8 asks for it, GLORYS is ocean-only and "
            "carries none, and no daily L4 wind product covers 2025–26 — the only global gap-filled "
            "option is hourly, averaged down by us. Every number on this page was produced without "
            "it, and that belongs beside each of them rather than in a footnote.")
    else:
        st.success("All 7 contract channels present, including wind — PS requirement 8 satisfied.")

    st.markdown("##### 2. The mixed layer is genuinely ours to fix")
    gva = load_json(GLORYS_VS_ARGO)
    st.caption(
        "At 20–75 m this model is worse than the reanalysis it was trained on, so that error is "
        "**model-limited** — it is ours. At 100–150 m it is already at the ceiling of the training "
        "truth: the reanalysis' own worst depth is 100 m, so that error is **inherited** and no "
        "amount of tuning here removes it. Distinguishing the two is the difference between a "
        "roadmap and an excuse.")
    if gva:
        st.json({k: gva[k] for k in list(gva)[:6]}, expanded=False)

    st.markdown("##### 3. The 1000 m paradox, stated rather than hidden")
    st.caption(
        "At 1000 m the model has its **worst skill** and its **best absolute RMSE** at the same "
        "time. Both are true: deep water barely varies, so climatology is already excellent there "
        "and there is little skill left to win, while the absolute error is small because the "
        "target itself is nearly constant. Reporting skill alone would look like failure; "
        "reporting RMSE alone would look like triumph.")

    st.markdown("##### 4. What we deliberately did not build")
    st.table(pd.DataFrame([
        {"cut": "F7 marine heatwave", "why": "persistence needs a full pipeline the data cannot support in this round"},
        {"cut": "F9 Sentinel", "why": "never built; not started now"},
        {"cut": "F10 priority v2", "why": "not in the problem statement, and not novel"},
        {"cut": "F6 events / anomaly maps", "why": "code kept and validated; nothing new built on it"},
        {"cut": "FiLM climatology decoder", "why": "measured to cost ~0.18 °C at our data scale under either loss — the paper's own Fig. 5 found only modest gains, so rejecting it is defensible with the paper's own finding"},
    ]))

    st.markdown("##### 5. The paper's window loses at our data scale")
    ab = load_json(TSEQ)
    if ab:
        legs = ab.get("legs", {})
        st.table(pd.DataFrame([
            {"T_SEQ (days of context)": int(k), "Argo RMSE (°C)": v.get("rmse"),
             "bias (°C)": v.get("bias"), "provenance": v.get("source", "?")}
            for k, v in sorted(legs.items(), key=lambda kv: int(kv[0]))]))
        st.caption(
            "The paper uses a ±15-day window (T_SEQ=31). On 962 independent profiles with seed, "
            "decoder, loss, samples and encoder held identical, it is the **worst** of the three "
            "here. `provenance` says whether each row was measured from a log or declared from "
            "AGENT_SYNC — a number whose source cannot travel with it should not be quoted.")

    st.markdown("##### 6. Evidence tags")
    st.table(pd.DataFrame([
        {"tag": "[VERIFIED]", "means": "the code was run, the data inspected, the source read. Only these are facts."},
        {"tag": "[INFERRED]", "means": "a reasonable guess that has not been tested. Labelled as such, never as fact."},
        {"tag": "[UNKNOWN]", "means": "not verified. Said plainly rather than dressed up."},
    ]))
    st.caption("CACHED = read from a metrics artifact the real model wrote. LIVE = computed in this "
               "session from the real checkpoint. There is no third category, and no demo data.")


# ── stage 2: salinity and the density constraint ───────────────────────────────────────

def render_stage2_tab(m: dict) -> None:
    st.subheader("Salinity, and whether the physics actually holds")
    st.caption(
        "Stage 2 adds a salinity head and TS-Cast's eq. 5: density is computed from the predicted "
        "(T, S) by EOS-80 and compared to density from the truth, so the constraint couples the "
        "two heads instead of letting each be independently plausible. The network never outputs "
        "density — only its uncertainty, which is predicted separately because the paper states "
        "T/S error covariance is non-negligible.")

    rows = T.salinity_rows(m)
    if not rows:
        st.warning(
            "**Salinity was not validated against observations in this run.** "
            f"{m.get('salinity_validation_note', '')} A salinity number scored only against the "
            "reanalysis it was trained on is not independent, and is not shown here as if it were.")
    else:
        df = pd.DataFrame(rows)
        o = (m.get("metrics_salinity") or {}).get("overall") or {}
        c1, c2, c3 = st.columns(3)
        c1.metric("overall salinity RMSE",
                  "not recorded" if o.get("rmse") is None else f"{float(o['rmse']):.4f} psu")
        c2.metric("mean correlation",
                  "not recorded" if o.get("correlation") is None else f"{float(o['correlation']):.4f}")
        c3.metric("independent profiles", f"{m.get('argo_profiles', '?')}")
        st.caption(
            f"Scored against Argo PSAL from `{m.get('argo_table', '?')}` — the same floats, the "
            f"same collocation, the same window as temperature. TS-Cast reports 0.1 psu (south) "
            f"to 0.2 psu (north) in the **Northwestern Pacific**: a different ocean with different "
            f"water masses, quoted for scale only and never as a like-for-like comparison.")

        chart = alt.Chart(df.dropna(subset=["RMSE (psu)"])).mark_line(point=True, color="#2ca02c").encode(
            x=alt.X("RMSE (psu):Q", title="salinity RMSE (psu) — lower is better"),
            y=alt.Y("depth (m):Q", title="depth (m)", scale=alt.Scale(reverse=True)),
            tooltip=list(df.columns)).properties(height=420, title="salinity error by depth")
        left, right = st.columns([2, 3])
        left.altair_chart(chart, use_container_width=True)
        right.dataframe(df, use_container_width=True, hide_index=True, height=420)

    st.markdown("#### Does eq. 5 hold? — the constraint, measured")
    dens = T.density_summary(m)
    if dens is None:
        st.info("No density block in this artifact: eq. 5 could not be checked without "
                "independent salinity.")
    else:
        cols = st.columns(len(dens))
        for col, (k, v) in zip(cols, dens.items()):
            col.metric(k, "—" if v is None else f"{v}")
        st.caption(
            "This is EOS-80 density from our predicted (T, S) against EOS-80 density from the "
            "independent floats' (T, S) — the exact quantity eq. 5 minimises, measured on data the "
            "model never saw. Surface seawater is roughly 1023 kg m⁻³, so read the RMSE against "
            "that scale. The calibration ratio is RMSE/RMS(σ): 1.0 means the predicted density "
            "uncertainty is honest.")

    w = m.get("w_density")
    if w is not None:
        st.caption(f"eq. 5 weight in this run: **{w}** "
                   + ("(the paper's unweighted sum, eq. 6)" if w == 1.0 else
                      "(**ablated** — this run trained with no physical constraint at all)"))


# ── page ───────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("TS-Cast-NIO v2 — subsurface temperature, and how much to trust it")
    m = load_metrics()
    provenance_banner(m)

    names = ["Profile", "Benchmark", "Calibration", "Honesty"]
    if T.is_stage2(m):
        names.insert(3, "Salinity & density")
    tabs = st.tabs(names)
    with tabs[0]:
        render_profile_tab()
    with tabs[1]:
        render_benchmark_tab(m)
    with tabs[2]:
        render_calibration_tab(m)
    if T.is_stage2(m):
        with tabs[3]:
            render_stage2_tab(m)
    with tabs[-1]:
        render_honesty_tab(m)


main()
