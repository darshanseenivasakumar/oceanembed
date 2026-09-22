"""What-If Calculator: edit the inputs the model sees, watch the output move.

OWNER: Unit A (Arjhun). NOT a page.

Backend: `src/oceanembed/whatif/` (Unit B, Darshan). This file only renders it — it never
re-implements any science. `baseline()` reads the real surface/profile at a point; `apply()` runs
the SAME handler twice (real inputs vs edited inputs) and diffs, so an empty edit reproduces the
baseline exactly and every difference on screen is caused by something the user changed.

EVERYTHING UNDER HERE IS HYPOTHETICAL. The real-data rule (CLAUDE.md) is not suspended for a
sandbox: every What-If number carries `hypothetical: True` from the backend, and this page says so
on every tab. The measured baseline is always drawn beside the edit so the two are never confused.

THE REGISTRY IS THE SOURCE OF TRUTH. Tabs and their widgets are generated from
`whatif.list_formulas()` and each `spec.inputs`; a formula added to the registry later appears here
with no change to this file.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import data as D
from app.ui import maps, theme, ux

try:
    from oceanembed import whatif as W
    _IMPORT_ERR: Exception | None = None
except Exception as e:                       # pragma: no cover - import guard
    W = None
    _IMPORT_ERR = e

_HYPOTHETICAL = ("These numbers come from inputs you edited, not from measured observations. "
                 "Every What-If result is hypothetical — the measured baseline is shown beside it.")


# --------------------------------------------------------------------------- widgets from a spec
def _input_widget(inp, baseline_val, kp: str):
    """One Streamlit widget for one InputSpec, defaulted to the real baseline value.

    Returns the current value. `min`/`max` are the spec's advisory range; the slider clamps the
    baseline into it only so the handle is always placed, never to forbid an extreme what-if — a
    user who types past the range is doing exactly what this tool is for, but a slider must show a
    handle, so the RANGE is widened to include the baseline rather than the baseline moved.
    """
    key = f"{kp}_{inp.name}"
    if inp.kind == "bool":
        return st.toggle(inp.label, value=bool(baseline_val if baseline_val is not None
                                               else inp.default), key=key)
    b = float(baseline_val if baseline_val is not None
              else (inp.default if inp.default is not None else 0.0))
    lo = float(inp.min) if inp.min is not None else b - 1.0
    hi = float(inp.max) if inp.max is not None else b + 1.0
    lo, hi = min(lo, b), max(hi, b)                       # never crop the real value out of view
    step = round((hi - lo) / 100.0, 4) or 0.01
    unit = f"  ({inp.unit})" if inp.unit else ""
    return st.slider(f"{inp.label}{unit}", lo, hi, b, step=step, key=key)


def _overrides(spec, baseline_values: dict, kp: str) -> dict:
    """Render every input of a spec and collect the edited values."""
    out = {}
    for inp in spec.inputs:
        out[inp.name] = _input_widget(inp, baseline_values.get(inp.name), kp)
    return out


def _didx(target: float) -> int:
    return int(np.argmin(np.abs(np.asarray(D.DEPTHS, dtype="float64") - target)))


# ------------------------------------------------------------------------------- profile (point)
def _dual_profile(depths, base_t, what_t):
    """Baseline and what-if temperature on one reversed depth axis."""
    df = pd.DataFrame({
        "depth": list(depths) + list(depths),
        "t": [None if v is None else float(v) for v in base_t]
             + [None if v is None else float(v) for v in what_t],
        "which": ["measured baseline"] * len(depths) + ["what-if"] * len(depths),
    }).dropna(subset=["t"])
    if df.empty:
        return None
    pad = max(0.4, float(df.t.max() - df.t.min()) * 0.08)
    dom = [float(df.t.min()) - pad, float(df.t.max()) + pad]
    return alt.Chart(df).mark_line(point=True, strokeWidth=2).encode(
        x=alt.X("t:Q", title="temperature (°C)", scale=alt.Scale(domain=dom, zero=False, nice=False)),
        y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True, zero=True)),
        color=alt.Color("which:N", title=None,
                        scale=alt.Scale(domain=["measured baseline", "what-if"],
                                        range=[theme.AMBER, theme.CYAN])),
        tooltip=[alt.Tooltip("which:N", title=""), alt.Tooltip("depth:Q", format=".0f", title="m"),
                 alt.Tooltip("t:Q", format=".2f", title="°C")],
    ).properties(height=430)


def _profile_tab(spec, ctx, src: str) -> None:
    st.markdown("**1 · Pick a point, then edit the surface the model reads from it.**")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)
    lat = np.asarray(base.LAT, dtype="float64")
    lon = np.asarray(base.LON, dtype="float64")
    fr = maps.frame(f["temperature"][:, :, 0], f["land_mask"], lat, lon)

    left, right = st.columns([2.7, 2.3], gap="large")
    with left:
        st.altair_chart(maps.clickable(fr, units="°C (0 m)", key="wi_pick", scheme="turbo",
                                       width=520), key="wi_pick", on_select="rerun")
        st.caption("Surface temperature. Click any sea cell to load its real profile.")

    picked = maps.selected_cell(st.session_state.get("wi_pick"))
    if picked is None:
        with right:
            st.info("Click a point on the map to begin.", icon=":material/touch_app:")
        return
    plat, plon = picked

    ck = f"wi_ctx_{plat:.3f}_{plon:.3f}_{ctx.date}_{src}"
    if st.session_state.get(ck) is None:
        with st.spinner("Reading the real inputs at this point …"):
            st.session_state[ck] = W.baseline(plat, plon, ctx.date, src)
    wctx = st.session_state[ck]

    with right:
        st.markdown(f"**{wctx.lat:.2f}°N  {wctx.lon:.2f}°E**")
        if wctx.is_land or wctx.surface is None:
            st.warning("There is no water column here — pick a sea cell.", icon=":material/block:")
            return
        ov = _overrides(spec, dict(wctx.surface), "wi_prof")
        run = st.button("Run what-if", type="primary", key="wi_prof_run",
                        use_container_width=True)

    rk = "wi_prof_res"
    if run:
        with st.spinner("Running the model on your edited surface …"):
            st.session_state[rk] = W.apply(spec.id, ov, wctx)
    res = st.session_state.get(rk)
    if res is None:
        with right:
            st.caption("Move the sliders, then press **Run what-if**.")
        return
    if not res["whatif"].get("available", True):
        with right:
            st.warning(res["whatif"].get("reason", "unavailable"), icon=":material/block:")
        return

    bt = res["baseline"]["profile_mean"]
    wt = res["whatif"]["profile_mean"]
    dt = res["delta"].get("profile_mean") or [w - b for b, w in zip(bt, wt)]
    ch = _dual_profile(D.DEPTHS, bt, wt)
    if ch is not None:
        st.altair_chart(ch, use_container_width=True)
    ux.tiles([(f"Δ AT {lbl}", f"{dt[_didx(z)]:+.2f}", "°C",
               f"{bt[_didx(z)]:.2f} → {wt[_didx(z)]:.2f}")
              for lbl, z in (("SURFACE", 0), ("100 m", 100), ("500 m", 500))])


# ------------------------------------------------------------------------- anomaly extremes (grid)
def _anomaly_tab(spec, wctx) -> None:
    st.markdown("**1 · Move the threshold k and watch how many cells count as extreme.**")
    ov = _overrides(spec, {}, "wi_anom")
    with st.spinner("Scoring anomalies across the basin …"):
        res = W.apply(spec.id, ov, wctx)
    b, w = res["baseline"], res["whatif"]
    if not w.get("available", True):
        st.warning(w.get("reason", "unavailable"), icon=":material/block:")
        return

    nb, nw = b["n_extreme_by_depth"], w["n_extreme_by_depth"]
    ux.tiles([("EXTREME CELLS · BASELINE", f"{sum(nb):,}", "", f"k = {b['k']:.2f} σ"),
              ("EXTREME CELLS · WHAT-IF", f"{sum(nw):,}", "", f"k = {w['k']:.2f} σ"),
              ("CHANGE", f"{sum(nw) - sum(nb):+,}", "cells",
               "more permissive k finds more" if w['k'] < b['k'] else "stricter k finds fewer")])

    df = pd.DataFrame({
        "depth": list(D.DEPTHS) + list(D.DEPTHS),
        "n": [int(x) for x in nb] + [int(x) for x in nw],
        "which": [f"baseline (k={b['k']:.2f})"] * len(D.DEPTHS)
                 + [f"what-if (k={w['k']:.2f})"] * len(D.DEPTHS),
    })
    ch = alt.Chart(df).mark_bar(opacity=0.85).encode(
        y=alt.Y("depth:N", title="depth (m)", sort=list(D.DEPTHS)),
        x=alt.X("n:Q", title="cells flagged extreme"),
        color=alt.Color("which:N", title=None, scale=alt.Scale(range=[theme.AMBER, theme.CYAN])),
        yOffset="which:N",
        tooltip=[alt.Tooltip("which:N", title=""), alt.Tooltip("depth:N", title="m"),
                 alt.Tooltip("n:Q", format=",", title="cells")],
    ).properties(height=430)
    st.altair_chart(ch, use_container_width=True)


# ---------------------------------------------------------------------- observation priority (grid)
def _priority_map(grid2d, land_mask, lat, lon, key: str):
    fr = maps.frame(grid2d.astype("float32"), land_mask, lat, lon)
    return maps.clickable(fr, units="priority", key=key, scheme="magma", width=460)


def _priority_tab(spec, wctx) -> None:
    st.markdown("**1 · Re-weight the priority score and see where the basin says to measure next.**")
    ov = _overrides(spec, {}, "wi_prio")
    with st.spinner("Ranking the basin …"):
        res = W.apply(spec.id, ov, wctx)
        g = wctx.grid()                                    # cache hit after apply() built it
    b, w = res["baseline"], res["whatif"]
    if not w.get("available", True):
        st.warning(w.get("reason", "unavailable"), icon=":material/block:")
        return

    lat = np.asarray(base.LAT, dtype="float64")
    lon = np.asarray(base.LON, dtype="float64")
    lm = g["land_mask"]

    def _fmt(x):
        return "—" if x is None else f"{x:.3f}"
    ux.tiles([("BASIN MAX · BASELINE", _fmt(b["basin_max"]), "", f"weights {b['weights']}"),
              ("BASIN MAX · WHAT-IF", _fmt(w["basin_max"]), "", f"weights {w['weights']}"),
              ("BASIN MEAN", f"{_fmt(b['basin_mean'])} → {_fmt(w['basin_mean'])}", "",
               f"{w['valid_cells']:,} ranked cells")])

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Baseline weights**")
        st.altair_chart(_priority_map(b["grid_priority"], lm, lat, lon, "wi_prio_b"),
                        key="wi_prio_b")
    with c2:
        st.markdown("**Your weights**")
        st.altair_chart(_priority_map(w["grid_priority"], lm, lat, lon, "wi_prio_w"),
                        key="wi_prio_w")


# --------------------------------------------------------------------------------------- render
def render(ctx) -> None:
    if W is None:
        st.error("The What-If backend (`oceanembed.whatif`) did not import, so there is nothing to "
                 "run. This panel never fabricates a result.")
        st.caption(f"import error: `{_IMPORT_ERR}`")
        return

    src = "satellite" if ctx.is_satellite else "glorys"

    # ---------------------------------------------------------------- 01 · the instrument
    ux.instrument("Edit the inputs to the real model and formulas, and read the effect against the "
                  "measured baseline. The same code runs both times — only your inputs differ.")
    ux.caveat(_HYPOTHETICAL)

    specs = W.list_formulas()
    tabs = st.tabs([s.label for s in specs])
    for tab, spec in zip(tabs, specs):
        with tab:
            if spec.id == "subsurface_profile":
                _profile_tab(spec, ctx, src)
            elif spec.scope == "grid":
                # Grid formulas rank the whole basin; the point only reads out one cell. Anchor the
                # context at a known Arabian-Sea ocean cell so the readout is water, not land.
                gk = f"wi_gctx_{ctx.date}_{src}"
                if st.session_state.get(gk) is None:
                    with st.spinner("Preparing the basin …"):
                        st.session_state[gk] = W.baseline(15.0, 65.0, ctx.date, src)
                gctx = st.session_state[gk]
                if spec.id == "anomaly_extremes":
                    _anomaly_tab(spec, gctx)
                elif spec.id == "observation_priority":
                    _priority_tab(spec, gctx)
                else:
                    st.info(f"No renderer yet for `{spec.id}` — add one in whatif.py.")
            else:
                st.info(f"No renderer yet for `{spec.id}` — add one in whatif.py.")

    # ---------------------------------------------------------------- 02 · the mathematics
    ux.maths(
        r"\text{what-if} = f(\text{your inputs}),\quad "
        r"\text{baseline} = f(\text{measured inputs}),\quad "
        r"\Delta = \text{what-if} - \text{baseline}",
        [("f", "the real model / anomaly / priority code, called unchanged", "—",
          "src/oceanembed/whatif imports the shipped functions"),
         ("measured inputs", "the true surface / weights at this point and date", "—",
          "predict.reconstruct, the same source as every other panel"),
         ("your inputs", "the values you set with the sliders", "—", "this page"),
         ("Δ", "the change your edit caused, per depth or per cell", "—", "engine.apply")],
        "Because f is identical on both sides, an unchanged input gives Δ = 0. Any difference you "
        "see is caused only by what you moved — this is a controlled comparison, not two runs.")

    # ---------------------------------------------------------------- 03 · the inference
    ux.inference(
        what=("The real model being asked a question it was never given data for: what would the "
              "depths look like if the surface — or the anomaly threshold, or the priority weights "
              "— were different from what was actually observed."),
        conclude=("Which inputs the model leans on, and how hard. A surface change that barely "
                  "moves the deep profile means the model reads little signal there; a weight that "
                  "reshapes the whole priority map shows what that panel is really driven by."),
        limits=[
            ("Every number here is hypothetical. It answers 'what would the model say', not 'what "
             "is true' — the inputs did not happen.", "engine.apply → hypothetical: True"),
            ("The model is unchanged and still bounded by what the surface can carry to depth. An "
             "impossible surface gives an answer, but not a trustworthy one.",
             "frozen checkpoint; see the observability panel for what depth is even informed"),
            ("Grid tabs rank the basin for the chosen date; the first run of a date reconstructs "
             "the whole field and is slow, then cached.", "whatif.compute._baseline_grid lru_cache"),
        ])
