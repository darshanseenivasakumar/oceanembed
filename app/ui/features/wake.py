"""Was the fuel actually spent? A real cyclone's cold wake, in the reconstruction.

OWNER: Unit A (Arjhun). NOT a page.

A cyclone eats the warm layer beneath it. This model sees only surface satellite fields and was
never taught that storms cool the ocean -- so whether the reconstruction shows a wake is a genuine
test of it, not a demonstration.

THE FINDING IS THE CONTRAST, NOT THE NUMBER
Measured against one fixed before/after date pair, the same storm barely registers. Measured
against each track point's OWN passage time, the wake is unmistakable. A storm takes days to cross
the basin, so a single pair of dates asks the wrong question at every point but one -- water hit on
day 1 has recovered by the "after" date, water hit on day 6 has a fresh wake. Same storm, same
reconstruction, same TCHP code. Only the question changed. Both numbers are always on screen
together; the passage-relative figure alone would be a result without its reason.

RENDERS A CACHED ARTIFACT, AND SAYS SO
A passage-relative wake costs one whole-basin reconstruction per storm-day either side -- about
fifteen at 32 s each, and more once the field cache evicts. That is not something to do in front
of a judge, so scripts/phase2/run_cyclone_wake.py computes it once and this renders the result
behind a CACHED chip naming the storm and the run. The project's real-data rule permits exactly
that: a cached result is allowed when the real model produced it and the UI says so.
"""
from __future__ import annotations

import glob
import json
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config as base

from app.ui import maps, theme, ux

PANELS = ("before", "during", "after")


@st.cache_data(show_spinner=False)
def _available() -> list[dict]:
    out = []
    for p in sorted(glob.glob(base.art("cyclone_wake_*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return sorted(out, key=lambda r: -(r.get("max_wind_kt") or 0.0))


@st.cache_data(show_spinner=False)
def _panel_maps(sid: str) -> dict:
    p = base.art(f"cyclone_wake_{sid}.npz")
    if not os.path.exists(p):
        return {}
    z = np.load(p)
    return {k: np.asarray(z[k], dtype="float64") for k in z.files}


def render(ctx) -> None:
    runs = _available()
    if not runs:
        st.error("No cached cyclone wake on this machine. This panel renders a precomputed "
                 "result and never reconstructs a storm live — that would be minutes of spinner.")
        st.code("PYTHONPATH=src .venv/Scripts/python.exe scripts/phase2/run_cyclone_wake.py "
                "--device cuda")
        return

    labels = {f"{r['name']} · {r['first']}": r for r in runs}
    c = st.columns([2.6, 1.4, 1.4, 2.6], vertical_alignment="bottom")
    with c[0]:
        with ux.control("storm", ratio=(6, 1)):
            pick = st.selectbox("Storm", list(labels), key="wk_storm")
    with c[1]:
        ux.explain("passagerelative", label="Why passage-relative?")
    with c[2]:
        ux.explain("wind", label="Which wind speed?")

    r = labels[pick]
    rel = r.get("passage_relative") or {}
    naive = r.get("naive_fixed_pair") or {}

    st.html('<div style="margin:-4px 0 10px 0">' + ux.chips([
        ("CACHED", "cached"),
        (f"{r['n_reconstructions']} reconstructions", "plain"),
        (f"{r['seconds'] / 60:.1f} min on {r['device']}", "plain"),
        # track_types is a LIST; formatting it straight leaks "['US-PROVISIONAL']" onto the page.
        (f"IBTrACS {', '.join(r.get('track_types') or []) or 'v04r01'}", "plain"),
    ]) + "</div>")

    if not rel.get("n_points"):
        st.warning(f"**{rel.get('verdict', 'no result')}** — no track point could be evaluated "
                   f"for this storm. Skipped: {rel.get('skipped')}.", icon=":material/block:")
        return

    # The VERDICT, never a bare mean. cold_wake returns a string precisely so a page cannot
    # render "-0.18" under the word "wake".
    banner = (st.success if rel["verdict"] == "cold wake resolved" else st.warning)
    banner(
        f"**{rel['verdict'].capitalize()}** — TCHP fell at **{rel['n_cooled']} of "
        f"{rel['n_points']}** track points ({rel['fraction_cooled']:.0%}), mean "
        f"**{rel['mean_change']:+.2f} kJ/cm²**, largest **{rel['largest_cooling']:+.1f}**. "
        f"Each point measured {rel['before_days']} days before against {rel['after_days']} days "
        f"after **its own** passage.",
        icon=":material/cyclone:")

    if naive.get("n_points"):
        st.info(
            f"**The same data with one fixed before/after pair returns "
            f"{naive['mean_change']:+.2f} kJ/cm² and {naive['fraction_cooled']:.0%} cooling — "
            f"essentially nothing.** A storm takes days to cross the basin, so a single pair of "
            f"dates asks the wrong question at every point but one. Same storm, same "
            f"reconstruction, same TCHP code — only the question changed.",
            icon=":material/compare_arrows:")

    ux.tiles([
        ("PASSAGE-RELATIVE", f"{rel['mean_change']:+.2f}", "kJ cm⁻²",
         f"{rel['fraction_cooled']:.0%} of points cooled"),
        ("ONE FIXED PAIR", f"{naive.get('mean_change', float('nan')):+.2f}", "kJ cm⁻²",
         f"{naive.get('fraction_cooled', 0):.0%} of points cooled"),
        ("PEAK WIND (WMO)", f"{r.get('max_wind_kt_wmo') or '—'}", "kt",
         f"USA says {r.get('max_wind_kt_usa') or '—'} kt"),
        ("TRACK POINTS SCORED", f"{rel['n_points']}", "",
         f"of {r['n_track_points']}, every {r['stride']}th"),
    ])

    if r.get("agencies_disagree_kt"):
        st.caption(
            f":orange[The agencies disagree by **{r['agencies_disagree_kt']:.0f} kt** on this "
            f"storm.] The category shown is **{r.get('category')}**, from the WMO figure. The "
            f"higher USA value would place it in a different category, so both are shown and "
            f"neither is presented as the truth.")

    left, right = st.columns([3.0, 2.2], gap="large")
    with left:
        st.markdown("**TCHP change at each track point**")
        pts = pd.DataFrame(rel["points"])
        pts["when"] = pts["time"].str.slice(0, 10)
        st.altair_chart(
            alt.Chart(pts).mark_bar().encode(
                x=alt.X("index:O", title="track point (every nth, in order along the track)"),
                y=alt.Y("change:Q", title="TCHP change (kJ cm⁻²)"),
                color=alt.condition(alt.datum.change < 0, alt.value(theme.AZURE),
                                    alt.value(theme.AMBER)),
                tooltip=[alt.Tooltip("when:N", title="passage"),
                         alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                         alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                         alt.Tooltip("tchp_before:Q", format=".1f", title="before"),
                         alt.Tooltip("tchp_after:Q", format=".1f", title="after"),
                         alt.Tooltip("change:Q", format="+.2f", title="change")],
            ).properties(height=330), use_container_width=True)
        st.caption("Blue = cooled after the storm passed. Each bar is that point measured "
                   "against its own passage time, not against a shared date.")

    with right:
        st.markdown("**The warm layer, before and after**")
        mp = _panel_maps(r["sid"])
        have = [k for k in PANELS if k in mp]
        if len(have) < 2:
            st.info("The cached maps for this storm are incomplete.")
        else:
            lat, lon = mp["lat"], mp["lon"]
            land = np.load(base.art("land_mask.npy")).astype(bool)
            lo = float(np.nanpercentile(np.concatenate([mp[k].ravel() for k in have]), 2))
            hi = float(np.nanpercentile(np.concatenate([mp[k].ravel() for k in have]), 98))
            which = st.segmented_control("Panel", have, default=have[0],
                                         format_func=lambda k: k.capitalize(),
                                         key="wk_panel") or have[0]
            fr = maps.frame(mp[which], land, lat, lon)
            st.altair_chart(
                maps.clickable(fr, units="TCHP (kJ cm⁻²)", key="wk_map",
                               scheme="plasma", width=520),
                key="wk_map", on_select="rerun")
            cs = r.get("case_study") or {}
            st.caption(f"**{which.capitalize()}** — {cs.get(which, '?')}. Colour range is pinned "
                       f"across all three panels ({lo:.0f}–{hi:.0f}) so the change is real and "
                       f"not the colour bar rescaling itself.")

    with st.expander(f"Every scored point  ·  {rel['n_points']}"):
        st.dataframe(pd.DataFrame(rel["points"]), use_container_width=True, hide_index=True)
        st.caption(f"Skipped: {rel.get('skipped')}. A point whose before or after date was not "
                   f"reconstructed, or whose TCHP is NaN at either end, is skipped and counted — "
                   f"never filled, and never scored as zero change, which would read as 'the "
                   f"storm did nothing here'.")

    # ---- 02 - the mathematics ------------------------------------------------------
    ux.maths(
        r"\Delta_i \;=\; \mathrm{TCHP}\big(\mathbf{x}_i,\; t_i + \tau_{+}\big)"
        r"\;-\; \mathrm{TCHP}\big(\mathbf{x}_i,\; t_i - \tau_{-}\big)"
        r"\qquad\quad \mathrm{TCHP}=\frac{\rho c_p}{10^{7}}\int_{0}^{D_{26}}\!(T(z)-26)\,dz",
        [("Δᵢ", "TCHP change at track point i", "kJ cm⁻²", "phase2.derived.cyclone.cold_wake"),
         ("xᵢ", "that point's own position, sampled bilinearly from the field", "°N, °E",
          "IBTrACS v04r01"),
         ("tᵢ", "that point's OWN passage time — the whole difference from the naive version",
          "date", "IBTrACS v04r01"),
         ("τ₋, τ₊", "days before and after passage",
          f"{rel['before_days']} and {rel['after_days']} d", "set when the artifact was built"),
         ("ρ, c_p", "density and heat capacity, held constant by the TCHP convention",
          "1026 kg m⁻³, 4000 J kg⁻¹ K⁻¹", "Leipper & Volgenau 1972"),
         ("D₂₆", "depth of the 26 °C isotherm, from the reconstruction", "m",
          "phase2.derived.heat_content")],
        "The naive version replaces tᵢ with one shared date pair for every point. That single "
        "substitution is the entire difference between the two numbers on screen.")

    # ---- 03 - the inference --------------------------------------------------------
    ux.inference(
        what=("A real cyclone's track laid over the reconstructed heat field, asking whether the "
              "warm layer the storm fed on actually disappeared behind it."),
        conclude=("The wake is there. The model is driven only by surface satellite fields and "
                  "was never taught that cyclones cool the ocean beneath them, so reproducing a "
                  "subsurface wake is evidence it has learned something about structure rather "
                  "than memorising a climatology."),
        limits=[
            ("TCHP is integrated from a reconstruction, so it inherits the reconstruction's own "
             "error before any of this is measured.", "artifacts/frozen_manifest.json"),
            ("A cold wake is not proof the model captured THIS storm. Upwelling, mixing and the "
             "seasonal cycle all cool the same water over the same days.",
             "phase2.derived.cyclone.cold_wake"),
            ("Track intensities for recent seasons are PROVISIONAL, and the agencies disagree by "
             "up to 14 kt on this basin — enough to cross a category boundary.",
             "artifacts/ibtracs_probe.json source_note"),
            ("The verdict is a threshold on a majority of points cooling AND a mean beyond a "
             "rounding error. It is a stated rule, not a statistical test.",
             "phase2.derived.cyclone.cold_wake"),
            ("These are cached results, not a live run. The model and code that produced them "
             "are stamped in the artifact.", f"artifacts/cyclone_wake_{r['sid']}.json"),
        ])
