"""How far sound carries, and where it bends. (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/acoustics_page.py --server.port 8514

WHY THIS VIEW
Sound speed is the operational reason an agency wants subsurface temperature at all: it decides how
far a sonar hears, where a signal refracts, and where the surface duct is deep enough to be worth
using. It turns a temperature field into something an operator acts on.

WHY IT IS DEFENSIBLE FROM A TEMPERATURE MODEL -- and this is measured, not argued
Mackenzie's temperature terms dominate its salinity term over this basin's range. At mean basin
conditions the deliverable's 0.9063 degC temperature RMSE moves sound speed by about 2.4 m/s, while
stage 2's 0.2695 psu salinity RMSE moves it by 0.30 m/s -- temperature is 89% of the budget. The
page computes that live rather than quoting it, so a reader can see it move with conditions.

THE SOURCE MENU MATCHES physics_page's, AND ITS THIRD ENTRY IS NAMED FOR WHAT IT IS
`physics_page` REFUSES to compute MLD from v2 temperature plus GLORYS salinity, because that would
"put a reanalysis field inside a number labelled satellite". That boundary is right and this page
keeps it: nothing here is ever labelled "satellite" while containing reanalysis. The build spec for
this feature asks for exactly that hybrid, so it is offered -- but as its own clearly-named source,
"v2 temperature + GLORYS salinity", never as the deliverable. The other two options make it
checkable: stage 2 is fully satellite-derived, glorys is fully reanalysis, and the error budget
shows the three cannot differ by much.

WHAT THE SPEC ASKED FOR THAT CANNOT HONESTLY BE SHIPPED
A basin map of SOFAR axis depth. [MEASURED: 94.75% of full-depth cells have their sound-speed
minimum at 1000 m -- the tropical Indian Ocean axis sits near 1500-2000 m, below this grid.] Such a
map would be a picture of the bottom of the grid. What ships instead is a map of WHERE the axis is
resolvable at all, with its depth at the ~5% of points where it genuinely is.
"""
from __future__ import annotations

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
from phase2.derived import acoustics as AC                  # noqa: E402
from phase2.derived import mapframe as MF                   # noqa: E402
from phase2.tscast_nio import config as v2config            # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Acoustics", layout="wide")
alt.data_transformers.disable_max_rows()

MAP_WIDTH, MAP_HEIGHT = MF.map_size(900)
CLR_NOT_WATER = "#3d3d3d"
#: A resolved ABSENCE -- "there is no duct here" -- which is a real answer and must not be read as
#: a value on the depth ramp. Deliberately off the viridis gamut (which runs dark purple -> blue ->
#: green -> yellow): the first choice, #6b5a7a, sat right on its deep end and read as "deep duct".
CLR_UNRESOLVED = "#b08968"
CLR_SSP = "#2a9d8f"

S2 = "v2 stage-2 (unpromoted)"
HYBRID = "v2 temperature + GLORYS salinity"
GLORYS = "glorys"
SOURCES = [S2, HYBRID, GLORYS]

SLD_VIEW = "sonic layer depth"
SOFAR_VIEW = "where the SOFAR axis is resolvable"

#: The RMSEs the error budget is computed from. Both measured against INDEPENDENT Argo.
T_RMSE_DELIVERABLE = 0.9063          # frozen_manifest.json -> deliverable_satellite, seafloor_masked_v2 (2026-09-07)
S_RMSE_STAGE2 = 0.2695               # AGENT_SYNC A18, mean over seeds 42/43/44, spread 0.0207


@st.cache_data(show_spinner="Reconstructing …")
def columns(date_str: str, source: str, version: str, device: str | None) -> dict:
    """(salinity, theta) for the whole basin on one date, from the chosen source.

    Every branch returns GLORYS-era-aligned arrays for the SAME day, so switching source is a
    model-vs-truth comparison rather than two different eras -- the same guarantee physics_page
    makes, and the reason the 2019-2022 bug cannot recur here.
    """
    from phase2.tscast_nio import field_cache as FC

    if source == S2:
        f = FC.field_for(date_str, stage=2, keep=FC.ALL_KEYS, device=device)
        if f.get("salinity") is None:
            raise RuntimeError("the stage-2 checkpoint returned no salinity")
        return {"salinity": np.asarray(f["salinity"]), "theta": np.asarray(f["temperature"]),
                "land_mask": np.asarray(f["land_mask"], bool), "date": f["date"],
                "provenance": f["provenance"], "salinity_is": "predicted by the stage-2 model",
                "theta_is": "predicted by the stage-2 model"}

    p = FC.get_predictor(1)
    t_idx, _ = p._time(date_str)
    glorys_s = np.asarray(p.data["salinity"][t_idx], dtype="float64")
    land = np.asarray(p.data["land_mask"], bool)
    day = str(np.asarray(p.data["times"])[t_idx])[:10]

    if source == GLORYS:
        return {"salinity": glorys_s, "theta": np.asarray(p.data["temp"][t_idx], dtype="float64"),
                "land_mask": land, "date": day, "provenance": {"source": "GLORYS12V1 reanalysis"},
                "salinity_is": "GLORYS12V1 reanalysis", "theta_is": "GLORYS12V1 reanalysis"}

    f = FC.field_for(date_str, stage=1, device=device)
    return {"salinity": glorys_s, "theta": np.asarray(f["temperature"]),
            "land_mask": land, "date": f["date"], "provenance": f["provenance"],
            "salinity_is": "GLORYS12V1 reanalysis — NOT satellite-derived",
            "theta_is": "predicted by the shipped stage-1 model"}


@st.cache_data(show_spinner="Computing sound speed …")
def maps(date_str: str, source: str, version: str, device: str | None) -> dict:
    col = columns(date_str, source, version, device)
    m = AC.layer_maps(col["salinity"], col["theta"])
    env = AC.in_envelope(col["salinity"], col["theta"])
    return {**m, "land_mask": col["land_mask"], "date": col["date"],
            "out_of_envelope": np.asarray(~env & np.isfinite(col["theta"])),
            "salinity_is": col["salinity_is"], "theta_is": col["theta_is"],
            "theta": col["theta"], "salinity": col["salinity"]}


def frame(m: dict, view: str) -> pd.DataFrame:
    """One clickable row per cell, with the depth AND the reason for this view."""
    which = "sld" if view == SLD_VIEW else "sofar"
    labels = AC.SLD_LABEL if which == "sld" else AC.SOFAR_LABEL
    res = m[which]
    depth = res["depth"].copy()
    reason = np.asarray(res["reason"])
    status = np.vectorize(lambda c: labels.get(res["reason_meanings"][int(c)],
                                               res["reason_meanings"][int(c)]))(reason)

    # `resolved` carries the depth ONLY where the feature was actually found. Everything else is
    # NaN so the continuous colour scale cannot paint a number onto a cell that has none -- an
    # unresolved SOFAR axis drawn at 1000 m would be the grid edge presented as a measurement.
    resolved = np.where(reason == MF_OK_CODE(res), depth, np.nan)

    d = MF.add_edges(MF.level_frame(resolved, m["land_mask"], base.LAT, base.LON,
                                    extra={"any_depth": depth}))
    df = pd.DataFrame(d)
    df["status"] = status.ravel()
    df["out_of_envelope"] = m["out_of_envelope"].any(axis=-1).ravel()
    df.attrs["counts"] = {labels.get(k, k): v for k, v in res["counts"].items()}
    return df


def MF_OK_CODE(res: dict) -> int:
    """The integer code meaning 'resolved' in a *_field result."""
    return next(c for c, name in res["reason_meanings"].items() if name == AC.OK)


def map_chart(df: pd.DataFrame, view: str):
    pick = alt.selection_point(name="pick", fields=["i", "j"], empty=False)
    common = dict(
        x=alt.X("lon0:Q", title="longitude (°E)", scale=alt.Scale(nice=False, zero=False)),
        x2="lon1:Q",
        y=alt.Y("lat0:Q", title="latitude (°N)", scale=alt.Scale(nice=False, zero=False)),
        y2="lat1:Q",
        tooltip=[alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                 alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                 alt.Tooltip("value:Q", format=".0f", title="depth (m)"),
                 alt.Tooltip("status:N", title="result")])

    if view == SLD_VIEW:
        # Continuous where the duct was found; one flat colour elsewhere, named in the caption.
        # `viridis` rather than turbo so this map is not mistaken for a temperature map.
        enc = dict(common, color=alt.condition(
            "isValid(datum.value)",
            alt.Color("value:Q", title="sonic layer depth (m)",
                      scale=alt.Scale(scheme="viridis", reverse=True),
                      legend=alt.Legend(orient="right")),
            alt.value(CLR_UNRESOLVED)))
    else:
        enc = dict(common, color=alt.Color(
            "status:N", title="SOFAR axis",
            scale=alt.Scale(range=["#4cc9f0", CLR_UNRESOLVED, CLR_NOT_WATER, "#8d99ae"]),
            legend=alt.Legend(orient="right")))

    return (alt.Chart(df).mark_rect(invalid=None).encode(**enc).add_params(pick)
            .properties(width=MAP_WIDTH, height=MAP_HEIGHT))


def ssp_chart(p: dict):
    """The sound-speed profile at one point, with the sonic layer marked."""
    c = np.asarray(p["sound_speed"], dtype="float64")
    z = np.asarray(p["depths"], dtype="float64")
    ok = np.isfinite(c)
    if not ok.any():
        return None
    df = pd.DataFrame({"depth": z[ok], "c": c[ok], "in_envelope": np.asarray(p["in_envelope"])[ok]})
    y = alt.Y("depth:Q", scale=alt.Scale(reverse=True), title="depth (m)")
    x = alt.X("c:Q", title="sound speed (m/s)", scale=alt.Scale(zero=False, nice=False))
    line = alt.Chart(df).mark_line(color=CLR_SSP, strokeWidth=2).encode(
        y=y, x=x,
        tooltip=[alt.Tooltip("depth:Q", title="m"), alt.Tooltip("c:Q", format=".1f", title="m/s"),
                 alt.Tooltip("in_envelope:N", title="inside Mackenzie's range")])
    # A point outside Mackenzie's quoted range is an extrapolation, so it is marked rather than
    # drawn identically to a value the formula was fitted for.
    pts = alt.Chart(df).mark_point(size=55, filled=True).encode(
        y=y, x=x,
        color=alt.Color("in_envelope:N", title="inside Mackenzie's range",
                        scale=alt.Scale(domain=[True, False], range=[CLR_SSP, "#d62828"]),
                        legend=alt.Legend(orient="bottom")))
    layers = [line, pts]
    if np.isfinite(p["sld_m"]):
        layers.append(alt.Chart(pd.DataFrame({"depth": [p["sld_m"]]}))
                      .mark_rule(color="#ffffff", strokeDash=[5, 3]).encode(y="depth:Q"))
    if np.isfinite(p["sofar_m"]):
        layers.append(alt.Chart(pd.DataFrame({"depth": [p["sofar_m"]]}))
                      .mark_rule(color="#e9c46a", strokeDash=[2, 2]).encode(y="depth:Q"))
    return alt.layer(*layers).properties(height=420)


def explainer(source: str, budget: dict) -> Explainer:
    caveats = [
        Caveat("The SOFAR axis is below this grid almost everywhere.",
               "94.75% of full-depth cells have their sound-speed minimum at 1000 m, the deepest "
               "level here — the tropical Indian Ocean axis sits nearer 1500–2000 m. Those cells "
               "are drawn as “axis below 1000 m”, never as an axis AT 1000 m, which would be the "
               "edge of the grid presented as a measurement.",
               "src/phase2/derived/acoustics.py — measured on daily_sat/v001, 2025-09-09"),
        Caveat("Roughly a sixth of the surface is outside Mackenzie's quoted range.",
               "Salinity in the Ganges/Meghna plume falls to 1.6 psu against the formula's stated "
               "floor of 30, and the warm pool exceeds its 30 °C ceiling. The polynomial still "
               "returns a number there — it cannot refuse — so those points are marked red on the "
               "profile rather than drawn as if the formula had been fitted for them.",
               "seawater.sound_speed_in_range"),
        Caveat("Sound speed is not the same claim as sonar range.",
               "This is the physical property that governs refraction. Turning it into a detection "
               "range needs a propagation model, a source level and a noise field, none of which "
               "are in this project.",
               "docs/phase2/NOVELTY_MATRIX.md — scope of claims"),
    ]
    if source == HYBRID:
        caveats.insert(0, Caveat(
            "This view mixes a satellite-derived temperature with a reanalysis salinity.",
            "The deliverable predicts temperature only. This source pairs it with GLORYS12V1 "
            "salinity, which is reanalysis, not an observation the model made. It is named for "
            "that and is never called “satellite”; physics_page refuses the same combination "
            "outright for MLD, where salinity is structurally essential rather than a minor term.",
            "app/phase2/physics_page.py — the compliance-boundary refusal"))
    elif source == S2:
        caveats.insert(0, Caveat(
            "Stage 2 is an unpromoted run, not the deliverable.",
            "It predicts salinity at depth as well as temperature, so this view is fully "
            "satellite-derived — but it does NOT beat stage 1 on temperature: seed 42 read "
            "+0.0224 better, seeds 43 and 44 read −0.0018 and −0.0080, and the mean +0.0042 sits "
            "inside a 0.0304 spread. Its σ is also uncalibrated.",
            "docs/phase2/AGENT_SYNC.md A18"))

    return Explainer(
        title="Sound speed, the sonic layer and the SOFAR axis",
        plain=("Sound travels faster in warmer, saltier and deeper water. This converts the "
               "temperature and salinity at each depth into how fast sound moves there, in metres "
               "per second — the property that decides how far a sonar hears and where its signal "
               "bends."),
        formula=r"c \approx 1448.96 + 4.591T - 5.304{\times}10^{-2}T^2 + 2.374{\times}10^{-4}T^3"
                r" + 1.340(S{-}35) + 1.630{\times}10^{-2}z + 1.675{\times}10^{-7}z^2"
                r" - 1.025{\times}10^{-2}T(S{-}35) - 7.139{\times}10^{-13}Tz^3",
        formula_note=(
            "Mackenzie (1981), the nine-term equation. T is potential temperature in °C, S is "
            "practical salinity (PSS-78), z is depth in metres — depth, not pressure, so the 15 "
            "standard levels feed straight in. Quoted valid for 0–30 °C, 30–40 psu, 0–8000 m. "
            f"At mean basin conditions a {budget['t_rmse_c']:.4f} °C temperature error moves c by "
            f"{budget['from_temperature_m_s']:+.2f} m/s and a {budget['s_rmse_psu']:.4f} psu "
            f"salinity error by {budget['from_salinity_m_s']:+.2f} m/s — temperature is "
            f"{budget['temperature_share']:.0%} of the budget."),
        how_to_read=("On the profile, contour lines bunched together mean sound speed is changing "
                     "fast with depth — that is where sound waves bend. The white dashed line is "
                     "the sonic layer depth: above it, sound is trapped near the surface. A deep "
                     "sonic layer favours surface-ship sonar. On the map, a cell with no duct is a "
                     "real result, not a gap — it means the sound-speed maximum is at the surface."),
        caveats=tuple(caveats),
        references=(
            "Mackenzie, K. V. (1981), “Nine-term equation for sound speed in the oceans”, "
            "J. Acoust. Soc. Am. 70(3), 807–812.",))


def main() -> None:
    st.title("Acoustics — how far sound carries, and where it bends")
    st.caption("The operational reason to want subsurface temperature: sound speed decides sonar "
               "range and refraction.")

    with st.sidebar:
        st.header("What to show")
        source = st.radio(
            "Source", SOURCES, index=0,
            help="All three read the SAME day, so this is a model-vs-truth comparison and not two "
                 "different eras. Stage 2 predicts salinity at depth, so it is fully "
                 "satellite-derived — but it is unpromoted and not the deliverable. The hybrid "
                 "uses the SHIPPED model's temperature with GLORYS salinity, and is named for "
                 "that. glorys is the reanalysis itself.")
        stage = 2 if source == S2 else 1
        ver = _fields.version(stage)
        date_str = _fields.date_picker(1, label="date", key="ac_date")
        view = st.radio("map", [SLD_VIEW, SOFAR_VIEW])
        device = _fields.device_picker(key="ac_dev")

    try:
        m = maps(date_str, source, ver, device)
    except Exception as e:
        st.error(f"Could not build the acoustic fields for {date_str}: {e}")
        st.info("Stage 2 needs artifacts/tscast_stage2_sat_s2.pt on this machine.")
        return

    df = frame(m, view)
    st.info(f"**Temperature: {m['theta_is']}. Salinity: {m['salinity_is']}.**")

    event = st.altair_chart(map_chart(df, view), key="ac_map", on_select="rerun",
                            use_container_width=False)
    counts = df.attrs["counts"]
    st.caption(f"{m['date']} · " + " · ".join(f"**{v:,}** {k}" for k, v in counts.items()) +
               ". The tan colour is a resolved *absence* — a real statement about the water "
               "column — while dark grey is land.")

    # the error budget, at this date's own mean conditions rather than a remembered number
    t = np.asarray(m["theta"])
    s = np.asarray(m["salinity"])
    ok = np.isfinite(t) & np.isfinite(s)
    budget = AC.error_budget(float(np.mean(t[ok])), float(np.mean(s[ok])), 100.0,
                             t_rmse=T_RMSE_DELIVERABLE, s_rmse=S_RMSE_STAGE2)

    left, right = st.columns([3, 2], gap="large")
    picked = (event or {}).get("selection", {}).get("pick") or []

    with left:
        st.subheader("Sound-speed profile")
        if not picked:
            st.info("**Click any cell on the map** to see its sound-speed profile.")
        else:
            i, j = int(picked[0]["i"]), int(picked[0]["j"])
            row = df[(df["i"] == i) & (df["j"] == j)].iloc[0]
            st.markdown(f"**{row['lat']:.2f} °N, {row['lon']:.2f} °E** — {row['status']}")
            p = AC.profile(s[i, j], t[i, j])
            chart = ssp_chart(p)
            if chart is None:
                st.warning("No water column at this cell.")
            else:
                st.altair_chart(chart, use_container_width=True)
                sld = (f"{p['sld_m']:.0f} m" if p["sld_reason"] == AC.OK
                       else f"none — {AC.SLD_LABEL.get(p['sld_reason'], p['sld_reason'])}")
                axis = (f"{p['sofar_m']:.0f} m" if p["sofar_reason"] == AC.OK
                        else AC.SOFAR_LABEL.get(p["sofar_reason"], p["sofar_reason"]))
                st.caption(
                    f"c spans **{p['c_min']:.1f}–{p['c_max']:.1f} m/s** over {p['n_levels']} "
                    f"levels · sonic layer **{sld}** (white dash) · SOFAR axis **{axis}** · "
                    f"{int(np.sum(p['in_envelope']))} of {p['n_levels']} levels inside "
                    f"Mackenzie's quoted range.")

    with right:
        st.subheader("Why a temperature model can claim this")
        c1, c2 = st.columns(2)
        c1.metric(f"from {T_RMSE_DELIVERABLE} °C in T", f"{budget['from_temperature_m_s']:+.2f} m/s")
        c2.metric("from 0.2695 psu in S", f"{budget['from_salinity_m_s']:+.2f} m/s")
        st.markdown(
            f"At this date's mean basin conditions — **{budget['at']['theta_c']:.2f} °C**, "
            f"**{budget['at']['salinity_psu']:.2f} psu**, 100 m — the deliverable's temperature "
            f"error moves sound speed **{budget['dominance']:.1f}×** more than stage 2's salinity "
            f"error does. Temperature is **{budget['temperature_share']:.0%}** of the budget.\n\n"
            "That is what makes an acoustic product from a temperature model defensible: it is "
            "essentially a temperature product, and temperature is the thing this project "
            "actually predicts and validates against 962 independent Argo profiles.")
        # Denominator is OCEAN cells, not all 24,000. Dividing by the whole grid would report
        # 24% where the real figure is 48%, because two thirds of the grid is land and land has no
        # salinity to be out of range -- a fraction quietly diluted by cells that cannot qualify.
        out = int(df["out_of_envelope"].sum())
        ocean = int((df["status"] != AC.SLD_LABEL[AC.NO_DATA]).sum()) if view == SLD_VIEW else             int(np.isfinite(np.asarray(m["theta"])).any(axis=-1).sum())
        st.caption(f"**{out:,} of {ocean:,} ocean cells** ({out / max(ocean, 1):.0%}) have at least "
                   f"one level outside Mackenzie's quoted salinity/temperature range — mostly the "
                   f"Ganges/Meghna plume and the warm pool. Marked red on the profile when you "
                   f"click one.")

    render(explainer(source, budget))


if __name__ == "__main__":
    main()
