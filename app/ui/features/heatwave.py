"""A heatwave the surface does not show.

OWNER: Unit A (Arjhun). NOT a page. Detection engine and baseline builders are Darshan's
(`phase2.events.heatwave`, `phase2.derived.mhw_baseline`, `phase2.derived.mhw_field`), merged
2026-09-07; this is the instrument's stage for them, in the house shape.

WHY THIS FEATURE EARNS ITS PLACE
Every other feature answers "what is the temperature down there". This one answers "what is
ANOMALOUS down there", which is a different question and the one an operational user actually
asks. And it is the sharpest statement of the project's premise: a marine heatwave is defined by
DAILY persistence -- five consecutive days above a seasonal 90th percentile -- so it could not be
computed at all until the daily bundle existed, and a heatwave at 100 m need leave no trace on the
sea-surface temperature a satellite measures.

WHAT THIS ADDS OVER THE STANDALONE PAGE (app/phase2/mhw_page.py, port 8518)
  * The shared basin map, so land and sea floor are drawn as their own layers rather than painted
    with whatever colour the value scale gives null.
  * Click a cell and get the ACTUAL events under it -- start, duration, peak intensity, Hobday
    category -- instead of only the fraction of days. An event list is checkable; a fraction is not.
  * The surface-vs-depth decoupling, MEASURED. "A heatwave at depth can be invisible from orbit"
    was prose everywhere in this project. Here it is a number -- and the measurement corrected the
    claim: at 100 m over 388 days, 8,667 of 9,745 flagged cells have MOST of their heatwave days
    unaccompanied by a surface one, but 11,783 cells also show the reverse. The two levels are in
    heatwaves at different times in BOTH directions, which is a stronger statement than one-way
    invisibility and a different one. "At least one hidden day" was the first metric tried and is
    vacuous: over 388 days almost every cell clears it.

WHAT IT DOES NOT DO
It does not forecast. It flags heatwaves present in a temperature series -- the GLORYS truth, or
the reconstruction -- and compares the two.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config as base
from phase2.derived import mhw_baseline as mb
from phase2.derived import mhw_field as mf
from phase2.events import heatwave as hw

from app.ui import maps, ux

#: The satellite leg first: it is the deliverable. The GLORYS leg is the comparator Darshan ran.
COMPARISONS = ("mhw_comparison_satellite.json", "mhw_comparison_glorys.json", "mhw_comparison.json")

SURFACE_Z = 0


# ----------------------------------------------------------------- data


@st.cache_data(show_spinner=False)
def _truth_stack():
    """The GLORYS daily temperature stack the detector runs on, plus its calendar and masks."""
    daily = os.path.join(base.DATA_PROCESSED, "daily")
    parts = [np.load(os.path.join(daily, f"{y}.npz"), allow_pickle=True) for y in (2025, 2026)]
    temp = np.concatenate([p["temp"] for p in parts], axis=0)
    times = np.concatenate([p["times"] for p in parts])
    return temp, times, np.asarray(parts[0]["land_mask"], bool)


@st.cache_data(show_spinner=False)
def _baseline(z: int):
    """Monthly climatology and 90th-percentile threshold at one level, mapped onto every day.

    The PILOT baseline: 2019-2022 monthly from grids.npz, not a 30-year day-of-year curve. That
    inflates absolute counts (see the caveats) and cancels in the model-vs-truth comparison,
    because both are scored against this same threshold.
    """
    g = np.load(os.path.join(base.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    clim12, thr12 = mb.monthly_climatology_threshold(g["temp"][:, :, :, z], g["times"],
                                                     pct=mb.PERCENTILE)
    _t, times, _l = _truth_stack()
    return (mb.map_monthly_to_series(clim12, times), mb.map_monthly_to_series(thr12, times))


@st.cache_data(show_spinner=False)
def _flags(z: int) -> np.ndarray:
    """(N, lat, lon) — was this cell inside a heatwave on this day, at level z."""
    temp, _times, land = _truth_stack()
    clim, thr = _baseline(z)
    return mf.mhw_day_flags_grid(temp[:, :, :, z].astype("float64"), clim, thr, land)


@st.cache_data(show_spinner=False)
def _surface_blind(z: int) -> dict:
    """How much of the heatwave at depth `z` never reaches the surface.

    Per cell: days inside a heatwave at depth, days at the surface, and days at depth while the
    surface is NOT in one. The last is the quantity the project's premise rests on, and it had
    never been counted.
    """
    deep, surf = _flags(z), _flags(SURFACE_Z)
    _t, _ti, land = _truth_stack()
    d_days = deep.sum(axis=0).astype("float64")
    s_days = surf.sum(axis=0).astype("float64")
    h_days = (deep & ~surf).sum(axis=0).astype("float64")
    r_days = (surf & ~deep).sum(axis=0).astype("float64")     # the SAME effect, other direction
    for a in (d_days, s_days, h_days, r_days):
        a[land] = np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(d_days > 0, h_days / d_days, np.nan)
    return {"deep_days": d_days, "surface_days": s_days, "hidden_days": h_days,
            "reverse_days": r_days, "hidden_share": share, "n_days": int(deep.shape[0])}


def _comparison() -> tuple[dict | None, str | None]:
    for name in COMPARISONS:
        p = os.path.join(base.ARTIFACTS, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f), name
    return None, None


# ----------------------------------------------------------------- render


def render(ctx) -> None:
    depths = list(base.DEPTHS)
    c = st.columns([2.6, 2.2, 2.4], vertical_alignment="bottom")
    with c[0]:
        with ux.control("mhwdepth", ratio=(5, 2)):
            depth = st.select_slider("Depth", depths, value=100, key="hw_depth",
                                     format_func=lambda d: f"{d} m")
    with c[1]:
        with ux.control("mhwshow", ratio=(5, 2)):
            show = st.segmented_control(
                "Show", ["In a heatwave", "Hidden from the surface"],
                default="In a heatwave", key="hw_show") or "In a heatwave"
    with c[2]:
        ux.explain("mhwbaseline", label="Why are the counts high?")

    z = depths.index(int(depth))
    with st.spinner(f"Detecting heatwaves at {depth} m across 388 days …"):
        sb = _surface_blind(z)
    n_days = sb["n_days"]

    hidden_map = show.startswith("Hidden")
    vals = (sb["hidden_days"] if hidden_map else sb["deep_days"]) / max(n_days, 1)
    units = "fraction of days"
    scheme = "magma" if hidden_map else "inferno"

    lat = np.asarray(base.LAT, dtype="float64")
    lon = np.asarray(base.LON, dtype="float64")
    _t, _ti, land = _truth_stack()
    fr = maps.frame(vals, land, lat, lon,
                    extra={"hidden": np.asarray(sb["hidden_share"], dtype="float64")})

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        st.altair_chart(maps.clickable(fr, units=units, key="hw_map", scheme=scheme, width=880,
                                       tooltip_extra=(("hidden", "hidden from surface (share)"),)),
                        key="hw_map", on_select="rerun")
        st.caption(
            (f"Days at {depth} m inside a heatwave while the SURFACE was not, as a fraction "
             f"of {n_days} days. Bright = an SST product would have shown nothing that day."
             if hidden_map else
             f"Days at {depth} m inside a heatwave, as a fraction of {n_days} days "
             f"({_ti[0]} … {_ti[-1]}). Read the pattern, not the level — see the caveat above.")
            + " Click a cell for the events beneath it.")

    with right:
        deep, hid = sb["deep_days"], sb["hidden_days"]
        fin = np.isfinite(deep)
        ever = int(np.nansum(deep > 0))
        # "at least one hidden day" is a bar almost every cell clears over 388 days and says
        # nothing; the share of a cell's OWN heatwave days that the surface missed does.
        mostly = int(np.nansum(np.nan_to_num(sb["hidden_share"]) > 0.5))
        reverse = int(np.nansum(sb["reverse_days"] > 0))
        ux.tiles([
            ("CELLS EVER IN A HEATWAVE", f"{ever:,}", f"of {int(fin.sum()):,} ocean cells at "
             f"{depth} m", "the surface flags nearly all of them — see the caveat"),
            ("MOST OF THEIR EVENT DAYS UNSEEN", f"{mostly:,}",
             f"{100 * mostly / ever:.0f}% of those cells" if ever else "—",
             "over half this cell's heatwave days had no surface heatwave that day"),
            ("MEDIAN UNSEEN SHARE", f"{np.nanmedian(sb['hidden_share']):.2f}" if ever else "—",
             "of a cell's heatwave days"),
            ("THE REVERSE, TOO", f"{reverse:,}", "cells",
             "days the SURFACE was in a heatwave and this depth was not"),
        ])

        picked = maps.selected_cell(st.session_state.get("hw_map"))
        if picked is None:
            st.info("Click the map to list the actual events under one column.",
                    icon=":material/touch_app:")
        else:
            plat, plon = picked
            i = int(np.argmin(np.abs(lat - plat)))
            j = int(np.argmin(np.abs(lon - plon)))
            st.markdown(f"**{plat:.2f}°N  {plon:.2f}°E · {depth} m**")
            _render_events(i, j, z, depth)

    _render_agreement()

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\text{MHW} \iff T(t) > T_{90}\big(\mathrm{doy}(t)\big)\ \ \text{for}\ \geq 5"
        r"\ \text{consecutive days}\qquad I(t)=T(t)-\bar{T}\big(\mathrm{doy}(t)\big)",
        [("T₉₀", "seasonally varying 90th percentile of the baseline period — the threshold that "
                 "decides IF a day counts", "°C",
          "Hobday et al. 2016 · phase2.derived.mhw_baseline"),
         ("T̄", "baseline climatological mean — what intensity is measured ABOVE. Not the "
                "threshold: using T₉₀ here would understate every event", "°C",
          "phase2.derived.mhw_baseline"),
         ("≥ 5 days", "the persistence rule. This is why monthly fields cannot detect a heatwave "
                      "at all, and why the feature was blocked until the daily bundle existed",
          "days", f"phase2.events.heatwave.MIN_DURATION_DAYS = {hw.MIN_DURATION_DAYS}"),
         ("gap ≤ 2", "two events separated by two days or fewer are one event, gap days folded in",
          "days", f"heatwave.MAX_GAP_DAYS = {hw.MAX_GAP_DAYS}"),
         ("category", "⌊(T−T̄)/(T₉₀−T̄)⌋ at the peak day: 1 Moderate, 2 Strong, 3 Severe, "
                      "4 Extreme", "—", "Hobday et al. 2018 · heatwave.category_at"),
         ("hidden", "days in a heatwave at this depth while the SURFACE cell, same day, is not",
          "days", "computed here from the same flags at level 0")],
        f"Baseline is the {mb.PERCENTILE:.0f}th percentile of 2019–2022 MONTHLY fields, not a "
        f"30-year day-of-year curve. NaN is never a heatwave: a land, below-seafloor or missing "
        f"day breaks a run rather than extending it.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=(f"Where the ocean at {depth} m spent days hotter than its own seasonal 90th "
              "percentile for five days or more — and, on the second view, where it did so while "
              "the surface above it did not."),
        conclude=("Surface and depth are in heatwaves at DIFFERENT TIMES, and in both "
                  "directions: most flagged cells have over half their heatwave days at depth "
                  "unaccompanied by a surface one, and nearly as many cells show the reverse. So "
                  "an SST observation is not merely an incomplete view of the subsurface state — "
                  "it is a different signal, and reading one from the other is a guess. That is "
                  "this project's premise stated as a count rather than a claim."),
        limits=[
            ("The baseline is a 2019–2022 MONTHLY pilot, not Hobday's 30-year day-of-year "
             "climatology. Ocean warming between the baseline and 2025–26 inflates every absolute "
             "count; the model-vs-truth agreement below is unaffected because both are scored "
             "against this same threshold.", "phase2.derived.mhw_baseline.monthly_climatology_threshold"),
            ("The map is detection in the GLORYS TRUTH, not in the reconstruction. It shows what "
             "is there to be found; the agreement panel shows how much of it the model finds.",
             "data/processed/daily/*.npz"),
            ("A monthly baseline mapped onto daily fields steps at month boundaries, so an event "
             "spanning one can be split or joined by the baseline rather than by the ocean.",
             "phase2.derived.mhw_baseline.map_monthly_to_series"),
            ("'Unseen' compares level 0 with the chosen depth in the same dataset. It says a "
             "surface OBSERVATION would not have flagged that day — not that no surface signature "
             "of any kind exists.", "app/ui/features/heatwave.py _surface_blind"),
            ("How severe the baseline bias is, measured: against the 2019–2022 pilot the SURFACE "
             "is flagged at some point in 11,831 of 11,832 ocean cells. Nearly the whole basin "
             "reads 'above the 90th percentile' somewhere in 388 days, which is the warming trend, "
             "not an epidemic. Only the pattern and the model-vs-truth agreement survive it.",
             "measured 2026-09-07 · phase2.derived.mhw_baseline"),
        ])


def _render_events(i: int, j: int, z: int, depth: int) -> None:
    """The actual events under one column: dates, duration, peak intensity, category."""
    temp, times, _land = _truth_stack()
    clim, thr = _baseline(z)
    series = temp[:, i, j, z].astype("float64")
    if not np.isfinite(series).any():
        st.warning("No water column here — land, or below the sea floor at this depth.",
                   icon=":material/block:")
        return
    events = hw.detect_events(series, clim[:, i, j], thr[:, i, j])
    s = hw.summarise(events)
    # The strongest event's OWN category. `summarise` reports the max category across all events,
    # which can belong to a different one -- pairing the two would mislabel the tile.
    peak_ev = max(events, key=lambda e: e["max_intensity_c"]) if events else None
    ux.tiles([("EVENTS", f"{s['n_events']}", f"in {len(series)} days"),
              ("DAYS IN A HEATWAVE", f"{s['total_mhw_days']}", ""),
              ("STRONGEST", f"{peak_ev['max_intensity_c']:+.2f}" if peak_ev else "—",
               "°C above normal", peak_ev["category_name"] if peak_ev else "")])
    if not events:
        st.caption("No event here reached five consecutive days above the threshold.")
        return
    day = np.asarray(times, dtype="datetime64[D]")
    rows = [{"start": str(day[e["start"]]), "end": str(day[e["end"]]),
             "days": e["duration_days"], "peak °C": round(e["max_intensity_c"], 2),
             "category": e["category_name"]} for e in events]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(
        f"Every event at {depth} m under this cell. Intensity is measured above the climatological "
        f"mean, not above the threshold. **Category is relative to THIS cell's variability** — it "
        f"counts how many multiples of the local (90th percentile − mean) gap the peak reached — "
        f"so a larger °C anomaly in a variable region can rank lower than a smaller one in a "
        f"steady region. Measured here: +3.82 °C at 18°N 88°E is Moderate, +2.59 °C at 15°N 68°E "
        f"is Extreme. That is Hobday 2018 working correctly, not a sorting error.")


def _render_agreement() -> None:
    """Per-depth model-vs-truth detection skill, if the comparison has been run."""
    import altair as alt

    cmp, name = _comparison()
    st.divider()
    if cmp is None:
        st.info("The model-vs-truth agreement has not been computed on this machine. Run "
                "`python scripts/phase2/run_mhw_comparison.py --checkpoint artifacts/"
                "tscast_stage1.pt` for the satellite leg.", icon=":material/pending:")
        return
    rows = []
    for d, c in cmp["per_depth"].items():
        for metric in ("pod", "csi", "far"):
            if c.get(metric) is not None:
                rows.append({"depth": int(d), "metric": metric.upper(), "value": c[metric]})
    if not rows:
        st.warning("The comparison artifact has no scored depth — every rate had a zero "
                   "denominator.", icon=":material/warning:")
        return
    st.markdown("**Can the reconstruction see them?**  Agreement with the GLORYS truth, per depth.")
    chart = (alt.Chart(pd.DataFrame(rows)).mark_line(point=True)
             .encode(x=alt.X("value:Q", title="skill", scale=alt.Scale(domain=[0, 1])),
                     y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)),
                     color=alt.Color("metric:N", title=None),
                     tooltip=["depth", "metric", alt.Tooltip("value:Q", format=".3f")])
             .properties(height=300))
    st.altair_chart(chart, use_container_width=True)
    st.caption(f"POD caught a real heatwave · CSI overall · FAR cried wolf (lower is better). "
               f"Both legs share one threshold, so the baseline's warming bias cancels here even "
               f"though it inflates the map. Source: `artifacts/{name}` — {cmp.get('model_leg', '')}")
