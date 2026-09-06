"""Temperature and doubt on one map, plus where the doubt lives with depth.

OWNER: Unit A (Arjhun). NOT a page.

Most reconstructions publish a field. This one publishes a field AND its own uncertainty, and
this feature is where that is made visible: colour carries the value, transparency carries the
confidence. Faded regions are where the model is guessing.

THE HONEST PART, WHICH IS THE POINT
The raw spread was measured TOO NARROW against independent floats -- the model claimed more
confidence than it had earned. A post-hoc per-depth calibration widens it, fitted on one period
and checked on a later one it never saw. The panel says which state it is in, every time.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from phase2.derived import mapframe as MF

from app.ui import data as D
from app.ui import maps, theme, ux

A_MIN, A_MAX = 0.14, 1.0


def _alpha(sigma_2d: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Map sigma to opacity between its 2nd and 98th percentile.

    Percentiles, not min/max: one extreme cell would otherwise flatten every other cell to the
    same opacity and the picture would carry no information at all.
    """
    s = np.asarray(sigma_2d, dtype="float64")
    ok = np.isfinite(s)
    if not ok.any():
        return np.full(s.shape, A_MAX), float("nan"), float("nan")
    lo, hi = np.percentile(s[ok], [2, 98])
    if not np.isfinite(lo) or hi <= lo:
        return np.full(s.shape, A_MAX), float(lo), float(hi)
    a = A_MAX - (A_MAX - A_MIN) * np.clip((s - lo) / (hi - lo), 0, 1)
    return a, float(lo), float(hi)


def _by_depth_chart(depths, sigma_by_depth):
    df = pd.DataFrame({"depth": depths, "sigma": sigma_by_depth}).dropna()
    if df.empty:
        return None
    peak = float(df.loc[df.sigma.idxmax(), "depth"])
    bars = alt.Chart(df).mark_bar(color=theme.AMBER, opacity=0.85, height=9).encode(
        x=alt.X("sigma:Q", title="mean ±1σ across the basin (°C)"),
        y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
        tooltip=[alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                 alt.Tooltip("sigma:Q", format=".3f", title="±1σ (°C)")])
    rule = alt.Chart(pd.DataFrame({"d": [peak]})).mark_rule(
        color=theme.CYAN, strokeDash=[4, 3]).encode(y="d:Q")
    return (bars + rule).properties(height=380), peak


def render(ctx) -> None:
    c = st.columns([2.2, 2.2, 2.4], vertical_alignment="bottom")
    with c[0]:
        with ux.control("depth", ratio=(5, 2)):
            level = st.select_slider("Depth (m)", options=D.DEPTHS, value=100, key="cf_depth")
    with c[1]:
        with ux.control("viewmode", ratio=(5, 2)):
            mode = st.segmented_control("View", ["Both", "Uncertainty only"],
                                        default="Both", key="cf_mode") or "Both"
    with c[2]:
        ux.explain("calibrated", label="Is the error bar trustworthy?")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)

    k = MF.nearest_level(D.DEPTHS, level)
    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")
    t2 = np.asarray(f["temperature"][:, :, k], dtype="float64")
    s2 = np.asarray(f["sigma"][:, :, k], dtype="float64")
    alpha, s_lo, s_hi = _alpha(s2)

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        if mode == "Uncertainty only":
            fr = maps.frame(s2, f["land_mask"], lat, lon)
            st.altair_chart(maps.clickable(fr, units="±1σ (°C)", key="cf_map",
                                           scheme="magma", width=880),
                            key="cf_map", on_select="rerun")
            st.caption(f"Model spread at {D.DEPTHS[k]:.0f} m. Bright is uncertain.")
        else:
            fr = maps.frame(t2, f["land_mask"], lat, lon,
                            extra={"sigma": s2, "alpha": alpha})
            df = pd.DataFrame({q: v for q, v in fr.items() if isinstance(v, np.ndarray)})
            w, h = MF.map_size(880)
            pos = dict(
                x=alt.X("lon0:Q", title="longitude (°E)",
                        scale=alt.Scale(domain=[float(df.lon0.min()), float(df.lon1.max())],
                                        nice=False)),
                x2="lon1:Q",
                y=alt.Y("lat0:Q", title="latitude (°N)",
                        scale=alt.Scale(domain=[float(df.lat0.min()), float(df.lat1.max())],
                                        nice=False)),
                y2="lat1:Q")
            b = alt.Chart(df)
            # Same three-layer discipline as maps.clickable: absences get their own flat colour
            # instead of being painted from the temperature scale.
            land = b.transform_filter(alt.datum.kind == MF.LAND).mark_rect(
                fill=theme.LAND, stroke=None).encode(**pos)
            floor = b.transform_filter(alt.datum.kind == MF.SEAFLOOR).mark_rect(
                fill=theme.FLOOR, stroke=None).encode(**pos)
            water = b.transform_filter(alt.datum.kind == MF.WATER).mark_rect(
                stroke=None).encode(
                color=alt.Color("value:Q", title="°C", scale=alt.Scale(scheme="turbo"),
                                legend=alt.Legend(gradientLength=190)),
                opacity=alt.Opacity("alpha:Q", legend=None,
                                    scale=alt.Scale(domain=[A_MIN, A_MAX],
                                                    range=[A_MIN, A_MAX])),
                tooltip=[alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                         alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                         alt.Tooltip("value:Q", format=".2f", title="°C"),
                         alt.Tooltip("sigma:Q", format=".3f", title="±1σ (°C)")],
                **pos)
            st.altair_chart(alt.layer(land, floor, water).properties(width=w, height=h),
                            use_container_width=False)
            st.caption(f"{D.DEPTHS[k]:.0f} m — colour is temperature, fade is doubt. "
                       f"Opacity spans ±1σ of {s_lo:.3f} to {s_hi:.3f} °C.")

    with right:
        by_depth = [float(np.nanmean(f["sigma"][:, :, q])) for q in range(len(D.DEPTHS))]
        out = _by_depth_chart(D.DEPTHS, by_depth)
        if out is not None:
            ch, peak = out
            st.markdown("**Which depths the model is least sure about**")
            st.altair_chart(ch, use_container_width=True)
            st.caption(f"Peak doubt at **{peak:.0f} m** — the thermocline, where temperature "
                       f"falls fastest with depth.")

    cal = D.calibration_summary()
    def _f(x, nd=3):
        return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "—"
    r2 = cal.get("cov2_range") or [None, None]
    ux.tiles([
        ("±1σ COVERAGE", _f(cal.get("cov1")), "",
         f"was {_f(cal.get('cov1_before'))} · ideal {_f(cal.get('target1'), 3)}"),
        ("±2σ COVERAGE", _f(cal.get("cov2")), "",
         f"{_f(r2[0])}–{_f(r2[1])} across depths · ideal {_f(cal.get('target2'), 3)}"),
        ("MEAN ±1σ HERE", f"{np.nanmean(s2):.3f}", "°C", f"at {D.DEPTHS[k]:.0f} m"),
        ("CHECKED ON", f"{cal.get('n_eval') or '—':,}" if cal.get("n_eval") else "—", "profiles",
         "a later period the fit never saw"),
    ])

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\alpha \;=\; \alpha_{\max}-(\alpha_{\max}-\alpha_{\min})\,"
        r"\frac{\sigma-\sigma_{2\%}}{\sigma_{98\%}-\sigma_{2\%}}"
        r"\qquad\quad \sigma \;=\; \exp\!\big(\tfrac{1}{2}\log \hat{v}\big)\cdot s_z",
        [("α", "opacity of a cell on the map", "—", "this panel"),
         ("σ", "the model's uncertainty at that cell and depth", "°C", "model output"),
         ("σ₂%, σ₉₈%", "2nd and 98th percentile of σ across the basin, so one outlier cannot "
                        "flatten the picture", "°C", "computed per frame"),
         ("log v̂", "the network's second output head — it predicts log-variance, not just a "
                    "temperature", "—", "src/phase2/tscast_nio/models/tscast.py"),
         ("s_z", "per-depth calibration scale, fitted on floats and checked on a later period",
          "—", "artifacts/uncertainty_calibration.json")],
        "The network is trained with a β-NLL loss (β = 0.5), which is what makes the second head "
        "learn a useful spread instead of collapsing it to zero.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("Where the model is confident and where it is guessing. Doubt concentrates at the "
              "thermocline and in energetic eddy regions."),
        conclude=("Do not quote a faded region's exact number. Read it as a hint about *where* "
                  "the model is unsure, then go and measure there — which is exactly what the "
                  "'where to measure next' feature ranks."),
        limits=[
            ("Coverage after calibration is 80–96 % at ±2σ depending on depth, against an ideal "
             "95 %. It is better, not perfect.",
             "artifacts/uncertainty_calibration.json cov2_range"),
            ("Calibration was fitted on 3,423 profiles and evaluated on 908 later ones. It is not "
             "guaranteed to hold outside that period.",
             "artifacts/uncertainty_calibration.json"),
            ("Uncertainty is the model's opinion of its own error. It cannot know about a bias "
             "shared by all its training data.", "docs/DECISIONS.md D-016"),
        ])
