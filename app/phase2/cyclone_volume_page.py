"""Did the ocean cool where the cyclone went? (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/cyclone_volume_page.py --server.port 8517

A cyclone mixes and upwells cold water, leaving a COLD WAKE visible for a week or more. If a
reconstruction driven only by surface satellite fields shows that wake, it is reproducing a process
nobody taught it -- a stronger statement than any RMSE.

WHAT IS 3-D HERE, AND WHAT IS NOT
TCHP is a DEPTH INTEGRAL: heat above the 26 degC isotherm, in kJ/cm2. It is a 2-D field and it has
no volume, so "a 3-D TCHP volume" is dimensionally confused and this page does not draw one. What
IS three-dimensional, and is exactly the thing a cyclone eats, is the WARM LAYER ITSELF -- the body
of water above 26 degC, whose thickness is D26 and whose heat content is TCHP. That is what the
isosurface shows, and watching it thin along the track is watching the fuel being spent.

THE MEASUREMENT IS PASSAGE-RELATIVE, AND THAT IS THE FEATURE
One fixed before/after pair gives a NULL result on this storm -- the page shows that too, because
the contrast is the point. See `phase2.derived.cyclone` for the measured numbers.

TCHP / D26 ARE NOT RECOMPUTED HERE. `heat_content_field` is the shipped implementation and is
called as-is; a second definition of TCHP is a second chance to get it wrong.
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
from phase2.data import ibtracs as IB                       # noqa: E402
from phase2.derived import cyclone as CY                    # noqa: E402
from phase2.derived import heat_content as HC               # noqa: E402
from phase2.derived import mapframe as MF                   # noqa: E402
from phase2.tscast_nio import config as v2config            # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Cyclone case study", layout="wide")
alt.data_transformers.disable_max_rows()

WINDOW = ("2025-06-01", "2026-06-23")
MAP_W, MAP_H = MF.map_size(430)
CLR_NOT_WATER = "#3d3d3d"
ISO_C = 26.0


@st.cache_data(show_spinner=False)
def storms() -> dict:
    return IB.load_tracks(window=WINDOW)


@st.cache_data(show_spinner="Reconstructing the days around the storm …")
def wake(sid: str, before_days: int, after_days: int, stride: int, version: str,
         device: str | None) -> dict:
    s = storms()[sid]
    cs_pre = IB.case_study_dates(s, before_days=before_days, after_days=after_days)
    # The three case-study panels need their OWN dates too. `dates_needed` returns the
    # passage-relative pairs; the PEAK date ("during") is a storm date and is not among them, so
    # without this the middle panel had no field -- and reported that as "outside the bundle",
    # which is a different fact entirely.
    need = sorted(set(CY.dates_needed(s, before_days=before_days, after_days=after_days,
                                      stride=stride))
                  | {cs_pre[k] for k in ("before", "during", "after") if cs_pre.get(k)})
    tchp = {}
    for d in need:
        if not (WINDOW[0] <= d <= WINDOW[1]):
            continue                       # outside the bundle: skipped, and counted by cold_wake
        tchp[d] = HC.heat_content_field(_fields.field(d, 1, version, _fields.DEFAULT_KEEP,
                                                      device))["tchp"]
    cs = cs_pre
    naive = (CY.naive_wake(s, tchp, cs["before"], cs["after"], stride=stride)
             if cs.get("peak_index") is not None else {"n_points": 0})
    return {"wake": CY.cold_wake(s, tchp, before_days=before_days, after_days=after_days,
                                 stride=stride),
            "naive": naive, "case": cs, "tchp": tchp, "dates": sorted(tchp)}


@st.cache_data(show_spinner=False)
def panel_field(date_str: str, version: str, device: str | None) -> dict:
    f = _fields.field(date_str, 1, version, _fields.DEFAULT_KEEP, device)
    hc = HC.heat_content_field(f)
    return {"tchp": hc["tchp"], "d26": hc["d26"], "temperature": np.asarray(f["temperature"]),
            "land_mask": np.asarray(f["land_mask"], bool), "date": f["date"]}


def tchp_map(field: dict, storm: dict, upto: str | None, title: str, vmax: float):
    df = pd.DataFrame(MF.add_edges(MF.level_frame(field["tchp"], field["land_mask"],
                                                  base.LAT, base.LON)))
    heat = alt.Chart(df).mark_rect(invalid=None).encode(
        x=alt.X("lon0:Q", title=None, scale=alt.Scale(nice=False, zero=False)), x2="lon1:Q",
        y=alt.Y("lat0:Q", title=None, scale=alt.Scale(nice=False, zero=False)), y2="lat1:Q",
        color=alt.condition("isValid(datum.value)",
                            alt.Color("value:Q", title="TCHP (kJ/cm²)",
                                      scale=alt.Scale(scheme="magma", domain=[0, vmax],
                                                      clamp=True),
                                      legend=alt.Legend(orient="bottom")),
                            alt.value(CLR_NOT_WATER)),
        tooltip=[alt.Tooltip("lat:Q", format=".2f"), alt.Tooltip("lon:Q", format=".2f"),
                 alt.Tooltip("value:Q", format=".0f", title="TCHP")])
    layers = [heat]
    keep = [i for i, t in enumerate(storm["time"]) if upto is None or t[:10] <= upto]
    if keep:
        tdf = pd.DataFrame({"lat": storm["lat"][keep], "lon": storm["lon"][keep],
                            "wind": [storm["wind_kt"][i] for i in keep],
                            "time": [storm["time"][i] for i in keep]})
        layers.append(alt.Chart(tdf).mark_line(color="#00e5ff", strokeWidth=1.6).encode(
            x="lon:Q", y="lat:Q", order="time:N"))
        layers.append(alt.Chart(tdf).mark_point(
            size=26, filled=True, color="#00e5ff", stroke="#00303a", strokeWidth=0.5).encode(
            x="lon:Q", y="lat:Q",
            tooltip=[alt.Tooltip("time:N"), alt.Tooltip("wind:Q", title="kt"),
                     alt.Tooltip("lat:Q", format=".2f"), alt.Tooltip("lon:Q", format=".2f")]))
    return alt.layer(*layers).properties(width=MAP_W, height=MAP_H, title=title)


def wake_chart(w: dict):
    df = pd.DataFrame(w["points"])
    if df.empty:
        return None
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color="#787878").encode(y="y:Q")
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("time:N", title="when the storm passed this point",
                axis=alt.Axis(labelAngle=-45, labelOverlap=True)),
        y=alt.Y("change:Q", title="TCHP change (kJ/cm²)"),
        color=alt.condition("datum.change < 0", alt.value("#2a78d6"), alt.value("#d95926")),
        tooltip=[alt.Tooltip("time:N", title="passage"),
                 alt.Tooltip("lat:Q", format=".2f"), alt.Tooltip("lon:Q", format=".2f"),
                 alt.Tooltip("wind_kt:Q", title="kt"),
                 alt.Tooltip("tchp_before:Q", format=".1f", title="before"),
                 alt.Tooltip("tchp_after:Q", format=".1f", title="after"),
                 alt.Tooltip("change:Q", format="+.1f", title="change")])
    return (bars + zero).properties(height=300)


def volume_figure(field: dict, storm: dict, stride: int = 3):
    """The WARM LAYER as a 3-D body: the 26 degC isosurface over the temperature volume.

    Not a "TCHP volume" -- TCHP is a depth integral and has none. This is the water a cyclone
    actually draws on, and its thickness IS D26.

    Every array goes through `.tolist()`. Plotly >= 6 serialises numpy as base64 that Streamlit's
    bundled plotly.js cannot decode, and the failure is an EMPTY BOX rather than an error -- the
    trap `cube/volume.py` already documents.
    """
    try:
        import plotly.graph_objects as go
    except Exception:
        return None

    t = np.asarray(field["temperature"])[::stride, ::stride, :]
    lat = np.asarray(base.LAT, float)[::stride]
    lon = np.asarray(base.LON, float)[::stride]
    z = np.asarray(v2config.DEPTHS, float)
    LA, LO, Z = np.meshgrid(lat, lon, z, indexing="ij")
    ok = np.isfinite(t)
    if ok.sum() < 1000:
        return None

    fig = go.Figure(go.Isosurface(
        x=LO[ok].tolist(), y=LA[ok].tolist(), z=(-Z[ok]).tolist(), value=t[ok].tolist(),
        isomin=ISO_C, isomax=ISO_C, surface_count=1, caps=dict(x_show=False, y_show=False),
        colorscale="Inferno", showscale=False, opacity=0.55,
        name=f"{ISO_C:.0f} °C surface"))
    fig.add_trace(go.Scatter3d(
        x=storm["lon"].tolist(), y=storm["lat"].tolist(),
        z=[5.0] * len(storm["lat"]), mode="lines+markers",
        line=dict(color="#00e5ff", width=5), marker=dict(size=3, color="#00e5ff"),
        name=storm["name"]))
    fig.update_layout(
        height=560, margin=dict(l=0, r=0, t=10, b=0),
        scene=dict(xaxis_title="longitude (°E)", yaxis_title="latitude (°N)",
                   zaxis_title="depth (m)",
                   aspectratio=dict(x=2.0, y=1.0, z=0.8)),      # depth exaggerated, or it is flat
        showlegend=False, paper_bgcolor="rgba(0,0,0,0)")
    return fig


def explainer(s: dict, w: dict, naive: dict) -> Explainer:
    caveats = [
        Caveat("This is the model's reconstruction, not an observation of the wake.",
               "The cooling shown is what the model produces from surface satellite inputs. That "
               "it produces a wake at all is the interesting part — the process was never in the "
               "training objective — but it is not an independent measurement of one.",
               "artifacts/frozen_manifest.json -> deliverable_satellite"),
        Caveat("A single before/after pair gives the wrong answer, and the page shows it.",
               f"Applied to the whole track with one fixed pair of dates, the same data returns "
               f"{naive.get('mean_change', float('nan')):+.2f} kJ/cm² and "
               f"{naive.get('fraction_cooled', 0):.0%} of points cooling — essentially nothing. A "
               f"storm takes days to cross a basin, so one pair asks the wrong question at every "
               f"point but one. Measured against each point's own passage time the answer is "
               f"{w.get('mean_change', float('nan')):+.2f} and "
               f"{w.get('fraction_cooled', 0):.0%}.",
               "src/phase2/derived/cyclone.py — both numbers, same TCHP code"),
        Caveat("Best-track intensity is provisional, and the agencies disagree.",
               f"{s['name']} is recorded as {s['track_types']}. WMO peaks it at "
               f"{s['max_wind_kt_wmo']:.0f} kt and the US agency at {s['max_wind_kt_usa']:.0f} kt "
               f"— {s['agencies_disagree_kt']:.0f} kt apart, which spans a category boundary. Both "
               f"are carried rather than one being chosen silently.",
               "data/raw/ibtracs — WMO_WIND and USA_WIND columns"),
        Caveat("TCHP integrates temperature only.",
               "It uses fixed ρ and cp (1026 kg/m³, 4000 J/kg/K) rather than density from the "
               "model, and D26 comes from the same temperature field — so the two are not "
               "independent of each other.",
               "src/phase2/derived/heat_content.py — RHO_TCHP, CP_TCHP"),
    ]
    return Explainer(
        title="Tropical cyclone heat potential and the cold wake",
        plain=("Tropical cyclone heat potential is the heat stored in water warm enough to fuel a "
               "storm's rapid intensification — literally the fuel reservoir beneath it. A "
               "cyclone mixes and upwells cold water as it passes, leaving a cold wake behind it. "
               "This asks whether the reconstruction shows that wake along a real storm's track."),
        formula=r"\text{TCHP} = \rho c_p \int_{0}^{D_{26}} \big(T(z) - 26\big)\, dz",
        formula_note=("ρ = 1026 kg/m³ and c_p = 4000 J/kg/K are the conventional TCHP constants; "
                      "D₂₆ is the depth of the 26 °C isotherm, the base of the layer warm enough "
                      "to matter to a storm. The integral runs from the surface down to that "
                      "depth, so TCHP is a heat per unit AREA — kJ/cm² — and is a 2-D field with "
                      "no volume of its own. The 3-D view shows the warm LAYER whose thickness is "
                      "D₂₆ and whose integral this is."),
        how_to_read=("Bright regions are where a storm passing overhead could intensify fast. The "
                     "cyan line is the track. In the bar chart, blue bars are points that cooled "
                     "after the storm passed — that is the wake. Each bar compares that point "
                     "against its own passage time, not against one date for the whole track."),
        caveats=tuple(caveats),
        references=("IBTrACS v04r01, NOAA NCEI — the WMO-endorsed best-track archive.",))


def main() -> None:
    st.title("Cyclone case study — was the fuel actually spent?")
    st.caption("A storm eats the warm layer beneath it. This asks whether the reconstruction "
               "shows that happening along a real track.")

    try:
        all_storms = storms()
    except FileNotFoundError as e:
        st.error(str(e))
        st.code("python scripts/phase2/probe_ibtracs.py", language="bash")
        return

    rated = {k: v for k, v in all_storms.items() if v["max_wind_kt"]}
    if not rated:
        st.warning("No rated storm in the model's window.")
        return
    order = sorted(rated, key=lambda k: -rated[k]["max_wind_kt"])

    with st.sidebar:
        st.header("Storm")
        sid = st.selectbox(
            "which", order,
            format_func=lambda k: (f"{rated[k]['name']} · {rated[k]['max_wind_kt']:.0f} kt · "
                                   f"{rated[k]['first']}"))
        s = rated[sid]
        before_days = st.slider("days before passage", 1, 7, CY.DEFAULT_BEFORE_DAYS)
        after_days = st.slider("days after passage", 2, 12, CY.DEFAULT_AFTER_DAYS)
        stride = st.slider("sample every nth track point", 1, 8, 4,
                           help="IBTrACS is 3–6 hourly and consecutive points fall inside one "
                                "0.25° cell, so a stride stops the sample being repeats of the "
                                "same water.")
        show3d = st.checkbox("3-D warm layer", value=True)
        device = _fields.device_picker(key="cy_dev")
        ver = _fields.version(1)

    st.markdown(f"### {s['name']} — {s['first']} to {s['last']}, {s['category']}, "
                f"{s['n_points']} track points")
    if s.get("agencies_disagree_kt"):
        st.caption(f"Intensity is provisional and the agencies disagree: WMO "
                   f"{s['max_wind_kt_wmo']:.0f} kt against the US agency "
                   f"{s['max_wind_kt_usa']:.0f} kt. Track type {', '.join(s['track_types'])}.")

    # Say the cost BEFORE paying it. A passage-relative wake needs a field per storm-day either
    # side, which for a week-long track is ~14 whole-basin reconstructions -- about 30 s each on
    # CPU and 8 s on GPU. A page that simply goes quiet for seven minutes looks broken.
    n_needed = len(CY.dates_needed(s, before_days=before_days, after_days=after_days,
                                   stride=stride))
    per = 8 if device == "cuda" else 32
    st.caption(f"This needs **{n_needed} whole-basin reconstructions** (one per storm-day either "
               f"side) — roughly {n_needed * per // 60} min {n_needed * per % 60} s at "
               f"~{per} s each on {'GPU' if device == 'cuda' else 'CPU'}. They are cached, so "
               f"changing the stride or the windows afterwards is instant."
               + ("" if device == "cuda" else " Turn on **reconstruct on GPU** to cut it to about "
                                              "a quarter."))

    try:
        r = wake(sid, before_days, after_days, stride, ver, device)
    except Exception as e:
        st.error(f"Could not build the case study: {e}")
        return
    w, naive, cs = r["wake"], r["naive"], r["case"]

    if w["n_points"] == 0:
        st.warning(f"No track point could be evaluated — {w['skipped']}. Most likely the storm's "
                   f"passage-relative dates fall outside the reconstruction bundle "
                   f"({WINDOW[0]} to {WINDOW[1]}).")
        return

    banner = st.success if w["verdict"] == "cold wake resolved" else st.warning
    banner(f"**{w['verdict'].capitalize()}** — TCHP fell at **{w['n_cooled']} of "
           f"{w['n_points']}** track points ({w['fraction_cooled']:.0%}), mean "
           f"**{w['mean_change']:+.2f} kJ/cm²**, largest **{w['largest_cooling']:+.1f}**, "
           f"measured {before_days} days before against {after_days} days after each point's own "
           f"passage.")

    if naive.get("n_points"):
        st.info(
            f"**The same data with one fixed before/after pair returns "
            f"{naive['mean_change']:+.2f} kJ/cm² and {naive['fraction_cooled']:.0%} cooling — "
            f"essentially nothing.** A storm takes days to cross the basin, so a single pair of "
            f"dates asks the wrong question at every point but one: water hit on day 1 has "
            f"recovered by the 'after' date, water hit on day 6 has a fresh wake. Same storm, same "
            f"TCHP code — only the question changed.")

    if cs.get("peak_index") is not None:
        vmax = float(np.nanpercentile(
            np.concatenate([r["tchp"][d][np.isfinite(r["tchp"][d])] for d in r["dates"][:3]]), 99))
        cols = st.columns(3, gap="small")
        for col, label in zip(cols, ("before", "during", "after")):
            d = cs[label]
            if d not in r["tchp"]:
                inside = WINDOW[0] <= d <= WINDOW[1]
                col.warning(f"{label}: {d} " + ("was not reconstructed" if inside else
                                                f"is outside the bundle ({WINDOW[0]}..{WINDOW[1]})"))
                continue
            f = panel_field(d, ver, device)
            col.altair_chart(tchp_map(f, s, d, f"{label} — {d}", vmax),
                             use_container_width=False)
        st.caption(f"Peak intensity {cs['peak_wind_kt']:.0f} kt at {cs['peak_time']}, "
                   f"{cs['peak_lat']:.1f} °N {cs['peak_lon']:.1f} °E. The track is drawn only up "
                   f"to each panel's own date — a full track on the 'before' panel would show the "
                   f"storm where it had not yet been.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("TCHP change at each track point")
        ch = wake_chart(w)
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
            st.caption("Blue = cooled after the storm passed. Each bar is that point measured "
                       "against its own passage time.")
    with right:
        st.subheader("Every point, as measured")
        st.dataframe(pd.DataFrame(w["points"])[
            ["time", "lat", "lon", "wind_kt", "tchp_before", "tchp_after", "change"]].round(2),
            hide_index=True, width="stretch")

    if show3d and cs.get("peak_index") is not None and cs["during"] in r["tchp"]:
        st.subheader(f"The warm layer itself — the {ISO_C:.0f} °C surface on {cs['during']}")
        fig = volume_figure(panel_field(cs["during"], ver, device), s)
        if fig is None:
            st.info("Plotly is unavailable or the field is too sparse — the 2-D panels above carry "
                    "the same information.")
        else:
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"The body of water above {ISO_C:.0f} °C, with the track along the surface. "
                       f"Its thickness is D₂₆ and its heat content is the TCHP mapped above — TCHP "
                       f"itself is a depth integral and has no volume, so this shows the layer, "
                       f"not the quantity. Depth is exaggerated or it renders flat.")

    render(explainer(s, w, naive))


if __name__ == "__main__":
    main()
