"""Cross-section (transect) view -- depth vs distance along a line the user draws.

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/transect_page.py --server.port 8510

WHY THIS VIEW
A vertical slice is how an oceanographer reads structure -- a tilting thermocline, an eddy's
subsurface core, a coastal gradient -- more directly than spinning a 3-D cube. Two endpoints and a
date in; a (distance x depth) section out, with real contour lines on top.

TWO HONESTY POINTS, BOTH ENFORCED IN THE MATH, NOT JUST THE CAPTION
  * The section is sampled by BILINEAR interpolation of the field, because reconstruct() snaps to
    the nearest grid centre -- sampling it directly would draw a staircase. (phase2.derived.transect)
  * Land and the seafloor are GAPS, never a value smoothed across them: an interpolated cell that
    touches a NaN corner is itself NaN. So a blank in the section is the coast or the bottom, not
    missing model output.

WHAT THE UPGRADE ADDED, AND THE THREE BUGS IT FIXED ON THE WAY
  * Model vs GLORYS side by side, with independent Argo floats scattered on top and coloured by
    model-minus-float error. Temperature only, so it needs no salinity and no compliance argument.
  * A sliding slice: the same track swept east or west, so a reader can watch a front move rather
    than re-typing four numbers.
  * Isopycnal and sound-speed contours, which need salinity -- see the source menu.

  1. `build_section` took a `version` cache-key argument that `main` never passed, so its
     `st.cache_data` never invalidated when the checkpoint changed. That is the exact mechanism
     behind the 8 degC dashboard error of 2026-09-02.
  2. The date was a free text box. `_time()` is an argmin with NO bound, so 1850-01-01 returned
     bundle index 0 and a complete, plausible section. It is a picker over the model's real
     calendar now.
  3. The colour legend called the model spread "NOT calibrated". `predict_field` applies the
     per-depth calibration scales whenever `_calibration_applies_to` passes, which for the shipped
     stage-1 model it does -- so the page was UNDERSTATING its own uncertainty quality. The label
     now reads the provenance instead of asserting.

CONTOURS COME FROM `profile_features.contour_line`, NOT `isotherm_line`
`isotherm_depth` returns NaN unless the surface value already exceeds the threshold, so on density
-- which increases with depth -- it fails at every point, silently. [MEASURED on a real 60-point
Arabian Sea section: the 24 kg/m3 isopycnal is resolved at 26 points by `contour_line` and at 0 by
`isotherm_line`.] The 20 lines that used to reconstruct a missing-D26 explanation by re-reading the
temperature array are gone too: the primitive returns the reason alongside the depth.
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
from oceanembed import config                               # noqa: E402
from phase2.derived import profile_features as pf           # noqa: E402
from phase2.derived import transect as T                    # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Transect", layout="wide")
alt.data_transformers.disable_max_rows()

V2 = "v2 satellite (temperature only)"
S2 = "v2 stage-2 (unpromoted)"
GLORYS = "glorys"
SOURCES = [V2, S2, GLORYS]

#: Which sections a source can produce. Temperature and the model spread need only temperature;
#: density and sound speed need salinity at depth, which the shipped stage-1 model does not predict.
NEEDS_SALINITY = ("salinity", "sigma_theta", "sound_speed")

FIELD_LABEL = {
    "temperature": "Temperature (°C)",
    "sigma": "Model spread (°C, 1σ)",
    "salinity": "Salinity (PSS-78)",
    "sigma_theta": "Potential density anomaly σθ (kg/m³)",
    "sound_speed": "Sound speed (m/s)",
}
SCHEME = {"temperature": "turbo", "sigma": "inferno", "salinity": "viridis",
          "sigma_theta": "plasma", "sound_speed": "cividis"}

OVERLAYS = {
    "20 °C isotherm": ("temperature", 20.0, "decreasing", "#111111"),
    "26 °C isotherm": ("temperature", 26.0, "decreasing", "#ffffff"),
    "σθ = 24 kg/m³": ("sigma_theta", 24.0, "increasing", "#00e5ff"),
    "σθ = 26 kg/m³": ("sigma_theta", 26.0, "increasing", "#ff5ca8"),
    "1520 m/s": ("sound_speed", 1520.0, "decreasing", "#ffd166"),
}


@st.cache_data(show_spinner="Reconstructing the field …")
def build_field(date_str: str, source: str, version: str, device: str | None) -> dict:
    """One daily field, cached by value. `version` is NOT optional -- see the module docstring."""
    from phase2.tscast_nio import field_cache as FC

    if source == GLORYS:
        p = FC.get_predictor(1)
        t_idx, _ = p._time(date_str)
        return {"date": str(np.asarray(p.data["times"])[t_idx])[:10],
                "temperature": np.asarray(p.data["temp"][t_idx], dtype="float64"),
                "salinity": np.asarray(p.data["salinity"][t_idx], dtype="float64"),
                "sigma": np.full((config.N_LAT, config.N_LON, config.N_DEPTHS), np.nan),
                "calibrated": None, "why": "GLORYS is the target, not a prediction"}
    stage = 2 if source == S2 else 1
    f = FC.field_for(date_str, stage=stage, keep=FC.ALL_KEYS, device=device)
    return {"date": f["date"], "temperature": np.asarray(f["temperature"]),
            "sigma": np.asarray(f["sigma"]),
            "salinity": None if f.get("salinity") is None else np.asarray(f["salinity"]),
            "calibrated": bool(f["provenance"].get("sigma_is_calibrated")),
            "why": f["provenance"].get("sigma_calibration_note", "")}


@st.cache_data(show_spinner="Sampling the section …")
def build_section(date_str, source, lat0, lon0, lat1, lon1, n, version: str,
                  device: str | None) -> dict:
    field = build_field(date_str, source, version, device)
    keys = ["temperature", "sigma"] + (["salinity"] if field.get("salinity") is not None else [])
    track = T.track_points(lat0, lon0, lat1, lon1, n=n)
    sec = T.sample_transect(track, field, keys=tuple(keys))
    if "salinity" in sec:
        T.add_derived(sec)
    sec["date"] = field["date"]
    sec["calibrated"] = field["calibrated"]
    sec["why"] = field["why"]
    return sec


@st.cache_data(show_spinner="Finding independent floats …")
def build_floats(date_str, source, lat0, lon0, lat1, lon1, n, max_km, version: str,
                 device: str | None) -> list[dict]:
    field = build_field(date_str, source, version, device)
    track = T.track_points(lat0, lon0, lat1, lon1, n=n)
    return T.floats_near_track(track, field["date"], field, max_km=max_km)


def _edges(centres: np.ndarray, floor: float | None = None) -> np.ndarray:
    """Cell-boundary positions for a pcolormesh-style rect plot: midpoints between centres, with
    the two outer edges extended by half the neighbouring spacing."""
    c = np.asarray(centres, dtype="float64")
    mid = (c[:-1] + c[1:]) / 2
    e = np.concatenate([[c[0] - (mid[0] - c[0])], mid, [c[-1] + (c[-1] - mid[-1])]])
    if floor is not None:
        e[0] = floor                                   # pin the surface edge to 0 m
    return e


def _rect_frame(sec: dict, field: str) -> pd.DataFrame:
    dist, depths, vals = sec["distance_km"], sec["depths"], sec[field]
    xe, ye = _edges(dist), _edges(depths, floor=0.0)
    rows = [(xe[k], xe[k + 1], ye[d], ye[d + 1], float(vals[k, d]),
             float(dist[k]), float(depths[d]))
            for k in range(len(dist)) for d in range(len(depths))
            if np.isfinite(vals[k, d])]
    return pd.DataFrame(rows, columns=["x0", "x1", "y0", "y1", "value", "distance", "depth"])


def _chart(sec: dict, field: str, overlays: list[str], floats: list[dict], title: str):
    df = _rect_frame(sec, field)
    if df.empty:
        return None, {}
    heat = alt.Chart(df).mark_rect().encode(
        x=alt.X("x0:Q", title="distance along track (km)"), x2="x1:Q",
        y=alt.Y("y0:Q", scale=alt.Scale(reverse=True), title="depth (m)"), y2="y1:Q",
        color=alt.Color("value:Q", title=FIELD_LABEL[field],
                        scale=alt.Scale(scheme=SCHEME[field], zero=False)),
        tooltip=[alt.Tooltip("distance:Q", format=".0f", title="km"),
                 alt.Tooltip("depth:Q", title="m"),
                 alt.Tooltip("value:Q", format=".2f", title=FIELD_LABEL[field])])
    layers, why = [heat], {}
    for name in overlays:
        key, level, direction, colour = OVERLAYS[name]
        if key not in sec:
            continue
        line, reasons = pf.contour_line(sec[key], sec["depths"], level, direction=direction)
        why[name] = pf.tally(reasons)
        ldf = pd.DataFrame({"distance": sec["distance_km"], "depth": line}).dropna()
        if not ldf.empty:
            layers.append(alt.Chart(ldf).mark_line(color=colour, strokeWidth=2).encode(
                x="distance:Q", y=alt.Y("depth:Q", scale=alt.Scale(reverse=True))))
    if floats:
        rows = [{"distance": f["distance_km"], "depth": float(z), "error": float(e),
                 "offset_km": f["offset_km"], "days": f["temporal_offset_days"]}
                for f in floats for z, e in zip(f["depths"], f["error"]) if np.isfinite(e)]
        if rows:
            layers.append(alt.Chart(pd.DataFrame(rows)).mark_point(
                size=48, filled=True, stroke="#000000", strokeWidth=0.5).encode(
                x="distance:Q", y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
                color=alt.Color("error:Q", title="model − float (°C)",
                                scale=alt.Scale(scheme="redblue", reverse=True, domainMid=0)),
                tooltip=[alt.Tooltip("error:Q", format="+.2f", title="model − float °C"),
                         alt.Tooltip("depth:Q", title="m"),
                         alt.Tooltip("offset_km:Q", format=".0f", title="km from track"),
                         alt.Tooltip("days:Q", format="+.0f", title="days from date")]))
    return alt.layer(*layers).properties(height=420, title=title), why


def explainer(source: str, overlays: list[str], calibrated) -> Explainer:
    caveats = [
        Caveat("A blank in the section is the coast or the seafloor, never a missing prediction.",
               "Sampling is NaN-strict: an interpolated point whose four surrounding grid corners "
               "are not all finite is itself NaN, per depth. So a shelf point is drawn in the "
               "mixed layer and blank at 1000 m, which is exactly right.",
               "phase2.derived.transect.bilinear_at"),
        Caveat("A broken contour line has a reason, and the caption gives it.",
               "A line can stop because the water is land, because the threshold is never reached, "
               "or because it is only crossed the other way. Those are three different statements "
               "about the ocean and the page separates them rather than drawing one gap.",
               "phase2.derived.profile_features.contour_line"),
    ]
    if any(OVERLAYS[o][0] in NEEDS_SALINITY for o in overlays) and source != GLORYS:
        caveats.append(Caveat(
            "Density and sound-speed contours need salinity at depth.",
            "The shipped stage-1 model predicts temperature only. These lines come from the "
            "stage-2 run, which predicts salinity too — it is fully satellite-derived but "
            "UNPROMOTED and is not better than stage 1 on temperature.",
            "docs/phase2/AGENT_SYNC.md A18"))
    if calibrated is False:
        caveats.append(Caveat(
            "The model-spread section is RAW σ, not calibrated.",
            "The calibration artifact does not apply to the checkpoint loaded, so those values are "
            "the network's own variance with no measured coverage.",
            "artifacts/uncertainty_calibration.json"))
    return Explainer(
        title="Depth-versus-distance section",
        plain=("A vertical slice through the reconstructed ocean along the line between two "
               "points. This is how structure is actually read: a tilting thermocline, the "
               "subsurface core of an eddy, the sharp gradient where two water masses meet."),
        formula=r"\sigma_\theta = \rho(S,\theta) - 1000",
        formula_note=("ρ is one-atmosphere seawater density from EOS-80 (UNESCO 1983), S is "
                      "practical salinity and θ is potential temperature. σθ is the potential "
                      "density anomaly in kg/m³ — subtracting 1000 just makes the numbers "
                      "readable, since seawater is about 1025 kg/m³."),
        how_to_read=("Lines of constant density (isopycnals) show where water of the same weight "
                     "sits. Where they bunch together and slope steeply, two different water "
                     "masses are meeting — that is a front. Flat, widely-spaced lines mean "
                     "well-mixed water. Argo dots are independent floats: blue means the model "
                     "reads colder than the float, red warmer, and a dot far from the line or far "
                     "from the date is a weaker check than a near one."),
        caveats=tuple(caveats),
        references=("UNESCO (1983), Algorithms for computation of fundamental properties of "
                    "seawater, Technical Papers in Marine Science 44.",))


def main() -> None:
    st.title("Ocean transect — a vertical slice along a line")
    st.caption("Depth vs distance along the great circle between two points. Blank = land or "
               "below the seafloor, never a smoothed value.")

    with st.sidebar:
        st.header("Track")
        c1, c2 = st.columns(2)
        lat0 = c1.number_input("start lat", 5.0, 29.75, 10.0, 0.25)
        lon0 = c2.number_input("start lon", 45.0, 104.75, 85.0, 0.25)
        lat1 = c1.number_input("end lat", 5.0, 29.75, 15.0, 0.25)
        lon1 = c2.number_input("end lon", 45.0, 104.75, 95.0, 0.25)
        shift = st.slider("slide the whole track east/west (°)", -20.0, 20.0, 0.0, 0.25,
                          help="Sweeps the same line across the basin, holding its shape, so a "
                               "front can be watched moving instead of retyping four numbers.")
        n = st.slider("points along track", 20, 120, 60, 10)
        st.divider()
        source = st.radio("source", SOURCES, index=0,
                          help="All three read the SAME day, so this is model-vs-truth and not "
                               "two eras. Stage 1 predicts temperature only, so density and "
                               "sound-speed contours need stage 2 or glorys.")
        stage = 2 if source == S2 else 1
        ver = _fields.version(stage)
        date_str = _fields.date_picker(1, label="date", key="tr_date", default="2025-12-18")
        device = _fields.device_picker(key="tr_dev")

    # The shift is clipped, NOT the endpoints -- see `transect.slide` for why that distinction
    # matters and what clipping the endpoints does to the track's shape.
    lon0_s, lon1_s, shift_used = T.slide(lon0, lon1, shift, config.LON[0], config.LON[-1])
    if abs(shift_used - shift) > 1e-9:
        st.caption(f"Slide limited to {shift_used:+.2f}° — {shift:+.2f}° would push one end of the "
                   f"track off the grid, and stretching it instead would change the section you "
                   f"asked for.")

    try:
        sec = build_section(date_str, source, lat0, lon0_s, lat1, lon1_s, n, ver, device)
    except Exception as e:
        st.error(f"Could not build the section: {e}")
        st.info("The satellite bundle and the checkpoint must both be on this machine.")
        return

    available = [k for k in FIELD_LABEL if k in sec]
    with st.sidebar:
        field = st.radio("colour by", available, format_func=FIELD_LABEL.get)
        usable = [o for o in OVERLAYS if OVERLAYS[o][0] in sec]
        overlays = st.multiselect("contour lines", usable,
                                  default=[o for o in ("20 °C isotherm", "26 °C isotherm")
                                           if o in usable])
        show_argo = st.checkbox("independent Argo floats", value=True)
        max_km = st.slider("float must be within (km)", 25, 200, 75, 25, disabled=not show_argo)
        compare = st.checkbox("compare with GLORYS", value=False,
                              disabled=(source == GLORYS))

    missing = [o for o in OVERLAYS if o not in usable]
    if missing and source == V2:
        st.info(f"**{len(missing)} contour(s) unavailable from this source** — "
                f"{', '.join(missing)} need salinity at depth, which the shipped stage-1 model "
                f"does not predict. Switch to stage 2 (satellite-derived) or glorys.")

    floats = []
    if show_argo:
        try:
            floats = build_floats(date_str, source, lat0, lon0_s, lat1, lon1_s, n, float(max_km),
                                  ver, device)
        except Exception as e:
            st.warning(f"Argo overlay unavailable: {e}")

    chart, why = _chart(sec, field, overlays, floats,
                        f"{source} — {sec['date']}")
    if chart is None:
        st.warning("The whole track is land or below the seafloor — no section to draw.")
        return

    if compare and source != GLORYS:
        gsec = build_section(date_str, GLORYS, lat0, lon0_s, lat1, lon1_s, n, ver, device)
        gfield = field if field in gsec else "temperature"
        gchart, _ = _chart(gsec, gfield, [o for o in overlays if OVERLAYS[o][0] in gsec],
                           floats, f"GLORYS (target) — {gsec['date']}")
        left, right = st.columns(2, gap="small")
        left.altair_chart(chart, use_container_width=True)
        if gchart is not None:
            right.altair_chart(gchart, use_container_width=True)
        if field in gsec:
            a, b = sec[field], gsec[field]
            both = np.isfinite(a) & np.isfinite(b)
            if both.any():
                st.caption(
                    f"**Model − GLORYS over this section:** bias "
                    f"{np.mean(a[both] - b[both]):+.3f}, RMSE "
                    f"{np.sqrt(np.mean((a[both] - b[both]) ** 2)):.3f} "
                    f"{FIELD_LABEL[field].split('(')[-1].rstrip(')')} over {int(both.sum())} "
                    f"section points. GLORYS is the training target, so this is agreement with "
                    f"what the model was fitted to — NOT independent validation. The Argo dots are.")
    else:
        st.altair_chart(chart, use_container_width=True)

    km = float(sec["distance_km"][-1])
    bits = [f"{sec['date']}", f"{km:.0f} km", f"{sec['temperature'].shape[0]} points",
            f"{lat0:.2f}N {lon0_s:.2f}E → {lat1:.2f}N {lon1_s:.2f}E"]
    if sec.get("calibrated") is not None:
        bits.append("σ calibrated" if sec["calibrated"] else "σ RAW (uncalibrated)")
    st.caption(" · ".join(bits) + ". Sampled by bilinear interpolation of the reconstructed field.")

    for name, tally in why.items():
        total = sum(tally.values())
        drawn = tally.get(pf.OK, 0) + tally.get(pf.MULTIPLE_CROSSINGS, 0)
        if drawn == total:
            continue
        parts = {pf.NO_DATA: "land or below the seafloor",
                 pf.OUTSIDE_PROFILE_RANGE: "never reach it",
                 pf.WRONG_DIRECTION: "cross it the other way",
                 pf.TOO_FEW_LEVELS: "have too few levels"}
        detail = ", ".join(f"{v} {parts.get(k, k)}" for k, v in tally.items() if k != pf.OK)
        st.caption(f"**{name}** drawn at {drawn} of {total} points — {detail}.")

    if show_argo:
        if floats:
            rmse = float(np.sqrt(np.mean([f["rmse"] ** 2 for f in floats])))
            st.caption(
                f"**{len(floats)} independent Argo profile(s)** within {max_km} km of the track "
                f"and ±5 days · pooled RMSE **{rmse:.3f} °C** · offsets "
                f"{min(f['offset_km'] for f in floats):.0f}–"
                f"{max(f['offset_km'] for f in floats):.0f} km. These are the only numbers here "
                f"the model was not fitted to.")
        else:
            st.caption(f"**No Argo profile within {max_km} km and ±5 days of this track.** That is "
                       f"a fact about float coverage, not about the model — floats drift and "
                       f"revisit a spot every 5–10 days.")

    render(explainer(source, overlays, sec.get("calibrated")))


if __name__ == "__main__":
    main()
