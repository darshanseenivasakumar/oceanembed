"""Click any pixel in the basin, get the model's profile there. (Unit A / Arjhun.)

PHASE-2 ONLY. A NEW file under app/phase2/. The frozen demo (app/streamlit_app.py, app/panels/)
is READ-ONLY and is not imported here.

    streamlit run app/phase2/clickmap_page.py --server.port 8512

WHY THIS VIEW
An Argo float answers "what is the temperature at 1000 m" only where a float happens to be, roughly
every 5-10 days. This page answers it at every one of the basin's 24,000 cells, every day. That is
the whole claim of the project, and this is the only page where a reader can test it themselves:
pick a point -- any point -- and see what the model says is underneath it.

THE PROFILE IS TAKEN FROM THE MAP'S OWN ARRAY, NOT RECONSTRUCTED AGAIN
A second `reconstruct(lat, lon, date)` call would cost another inference and, worse, would let the
number in the side panel drift from the colour under the cursor if the two paths ever disagreed.
`tests/phase2/test_field.py` pins field-equals-point precisely so this shortcut is sound, and
`tests/phase2/test_clickmap.py` re-checks that equality through this page's own resolver.

THE RECTANGLES CARRY EXPLICIT EDGES, AND THAT IS NOT COSMETIC
`mark_rect` against a continuous scale with only `x` and `y` has no idea how wide a cell is, so
Vega-Lite picks a default band and the basin renders as a handful of enormous blocks. [VERIFIED --
that is exactly what the first version of this page drew.] The edges are half a grid cell either
side, the same `_edges` idea `transect_page.py` uses.

THREE KINDS OF BLANK, AND THEY ARE NOT THE SAME THING
A cell with no profile is land, or it is ocean whose seafloor is above the depth you asked for, or
it is outside the grid. START_HERE rule 8 -- an absence is not a value -- and this page is where a
reader is most likely to click one. All three are drawn, all three are clickable, and each says
which it is instead of showing an empty chart. The classification lives in
`phase2.derived.mapframe` so the uncertainty and acoustics maps cannot classify it differently.
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
from phase2.derived import mapframe as MF                   # noqa: E402
from phase2.tscast_nio import config as v2config            # noqa: E402
from phase2.validation.argo_overlay import two_sigma_band   # noqa: E402
from phase2.viz_explainer import Caveat, Explainer, render  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Click a point", layout="wide")

# 24,000 rects is well past Altair's default 5,000-row guard, and the guard raises rather than
# degrading. Measured in an earlier session: 11,832 marks render fine through st.altair_chart,
# which ships data via Arrow rather than inlining it in the chart spec.
alt.data_transformers.disable_max_rows()

#: Cell edges and the basin's true 2.29:1 aspect both live in `mapframe` -- the uncertainty map
#: needs the identical geometry, and the sonic-layer map will be the third caller. Two maps of one
#: basin drawn to two different aspects is a difference a reader would read as data.
MAP_WIDTH, MAP_HEIGHT = MF.map_size(900)
CLR_MODEL = "#2a78d6"
#: Land and below-seafloor cells. Drawn, not omitted -- see `map_chart`.
CLR_NOT_WATER = "#3d3d3d"


@st.cache_data(show_spinner=False)
def slice_frame(date_str: str, depth_m: float, stage: int, version: str,
                device: str | None) -> pd.DataFrame:
    """One depth level as a long frame of clickable cells, land and seafloor included."""
    f = _fields.field(date_str, stage, version, _fields.DEFAULT_KEEP, device)
    k = MF.nearest_level(v2config.DEPTHS, depth_m)
    d = MF.add_edges(MF.level_frame(np.asarray(f["temperature"])[:, :, k],
                                    f["land_mask"], base.LAT, base.LON,
                                    extra={"sigma": np.asarray(f["sigma"])[:, :, k]}))
    df = pd.DataFrame(d)
    df.attrs["level_m"] = float(v2config.DEPTHS[k])
    df.attrs["date"] = f["date"]
    return df


@st.cache_data(show_spinner=False)
def profile_at(i: int, j: int, date_str: str, stage: int, version: str,
               device: str | None) -> dict:
    """The 15-level profile at grid cell (i, j), from the same array the map is drawn from."""
    f = _fields.field(date_str, stage, version, _fields.DEFAULT_KEEP, device)
    mean = np.asarray(f["temperature"])[i, j, :]
    sigma = np.asarray(f["sigma"])[i, j, :]
    band = two_sigma_band(list(mean), list(sigma))
    return {"depths": list(v2config.DEPTHS), "mean": list(mean), "sigma": list(sigma),
            "lo": band["lo"], "hi": band["hi"],
            "calibrated": bool(f["provenance"].get("sigma_is_calibrated")),
            "why": f["provenance"].get("sigma_calibration_note", ""), "date": f["date"]}


def map_chart(df: pd.DataFrame, level_m: float, picked: tuple | None):
    """The depth slice. `selection_point` carries i/j back so a click resolves to a grid cell.

    Geometry -- the true 2.29:1 aspect and the half-cell edges -- comes from `mapframe`, which
    carries the reasoning. Both dimensions are pinned; `use_container_width` gave 1.6.

    THE SELECTED CELL GETS A MARKER, NOT AN OPACITY TWEAK. At 240 columns each cell is a few
    pixels; dimming the other 23,999 by 15% is invisible. A crosshair drawn from the resolved
    (i, j) is not.
    """
    pick = alt.selection_point(name="pick", fields=["i", "j"], empty=False)
    # `invalid=None` IS LOAD-BEARING. Vega-Lite's default is `invalid: "filter"`: a datum whose
    # encoded field is null is DROPPED before rendering. So land and below-seafloor cells were
    # never drawn, a click on India selected nothing, and the panel went on saying "click any cell"
    # -- silence exactly where this page promises an explanation. [VERIFIED in the browser twice:
    # once with no fill, once with mark_rect(fill=...), which overrides the colour encoding and
    # painted the whole basin grey instead.] `invalid=None` means "keep them", and the colour then
    # comes from the condition below.
    base_map = (alt.Chart(df)
                .mark_rect(invalid=None)
                .encode(
                    x=alt.X("lon0:Q", title="longitude (°E)",
                            scale=alt.Scale(nice=False, zero=False)),
                    x2="lon1:Q",
                    y=alt.Y("lat0:Q", title="latitude (°N)",
                            scale=alt.Scale(nice=False, zero=False)),
                    y2="lat1:Q",
                    # A CONDITION, not `mark_rect(fill=...)`: a mark-level fill overrides the
                    # colour encoding outright and painted the entire basin grey. This keeps the
                    # turbo scale where there is a value and falls back only where there is not.
                    color=alt.condition(
                        "isValid(datum.value)",
                        alt.Color("value:Q", title=f"T at {level_m:.0f} m (°C)",
                                  scale=alt.Scale(scheme="turbo"),
                                  legend=alt.Legend(orient="right")),
                        alt.value(CLR_NOT_WATER)),
                    tooltip=[alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
                             alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
                             alt.Tooltip("value:Q", format=".2f", title="T (°C)"),
                             alt.Tooltip("kind:N", title="cell")])
                .add_params(pick))
    layers = [base_map]
    if picked is not None:
        marker = pd.DataFrame({"lat": [picked[0]], "lon": [picked[1]]})
        layers.append(alt.Chart(marker)
                      .mark_point(shape="cross", size=220, stroke="#ffffff", strokeWidth=3,
                                  filled=False)
                      .encode(x="lon:Q", y="lat:Q"))
        layers.append(alt.Chart(marker)
                      .mark_point(shape="cross", size=220, stroke="#000000", strokeWidth=1.2,
                                  filled=False)
                      .encode(x="lon:Q", y="lat:Q"))
    return alt.layer(*layers).properties(width=MAP_WIDTH, height=MAP_HEIGHT)


def profile_chart(p: dict):
    df = pd.DataFrame({"depth": p["depths"], "T": p["mean"], "lo": p["lo"], "hi": p["hi"]})
    df = df[np.isfinite(df["T"])]
    if df.empty:
        return None
    y = alt.Y("depth:Q", scale=alt.Scale(reverse=True), title="depth (m)")
    # The axis must NOT include zero. mark_area with x/x2 forces a zero baseline by default, which
    # stretched the axis to 0-35 degC and squeezed a real +-2 sigma band of 0.83 degC into about 2%
    # of the plot -- an uncertainty band drawn so thin it reads as certainty. Padded by 1 degC
    # either side of the band's own range so the shading is legible at every point.
    lo, hi = float(df["lo"].min()) - 1.0, float(df["hi"].max()) + 1.0
    x_scale = alt.Scale(domain=[lo, hi], zero=False, nice=False)
    band = alt.Chart(df).mark_area(opacity=0.3, color=CLR_MODEL).encode(
        y=y, x=alt.X("lo:Q", title="temperature (°C)", scale=x_scale), x2="hi:Q")
    line = alt.Chart(df).mark_line(point=True, color=CLR_MODEL, strokeWidth=2).encode(
        y=y, x=alt.X("T:Q", title="temperature (°C)", scale=x_scale),
        tooltip=[alt.Tooltip("depth:Q", title="m"), alt.Tooltip("T:Q", format=".2f", title="°C"),
                 alt.Tooltip("lo:Q", format=".2f", title="−2σ"),
                 alt.Tooltip("hi:Q", format=".2f", title="+2σ")])
    return (band + line).properties(height=460)


def explainer(calibrated: bool) -> Explainer:
    caveats = [
        Caveat("The map is a model, not an observation.",
               "Every cell is reconstructed from surface satellite fields. Only a handful of "
               "points on any given day have an Argo float underneath to check against, and those "
               "are on the Argo overlay page (port 8508).",
               "artifacts/frozen_manifest.json -> deliverable_satellite"),
        Caveat("0.9078 °C is a basin-wide average, not this cell's error.",
               "The headline RMSE is measured against 962 independent Argo profiles across the "
               "whole basin and the whole test window. A single point can be much better or much "
               "worse, and the Arabian Sea is measurably worse than the Bay of Bengal.",
               "docs/phase2/AGENT_SYNC.md — Arabian Sea penalty, four mechanisms, still UNKNOWN"),
    ]
    if calibrated:
        caveats.append(Caveat(
            "Calibrated does not mean correct.",
            "The per-depth scales were fitted on train-window Argo, and the 2σ band still covers "
            "about 91% of held-out observations against a nominal 95.4%. It is improved, not "
            "calibrated in the strict sense.",
            "artifacts/uncertainty_calibration.json -> summary_after"))
    else:
        caveats.append(Caveat(
            "The band here is RAW model spread, not calibrated uncertainty.",
            "The calibration artifact does not apply to the checkpoint currently loaded, so the "
            "±2σ shading is the network's own variance output and has no measured coverage.",
            "artifacts/uncertainty_calibration.json"))
    return Explainer(
        title="Predicted profile at a clicked point",
        plain=("This map shows the model's predicted temperature at one depth, everywhere in the "
               "basin — not just where an Argo float happens to be. Click any cell to see the "
               "full vertical profile the model predicts there, with its uncertainty band."),
        formula=r"T(x,y,z),\;\sigma(x,y,z) \;=\; f_\theta\!\big(\mathrm{SST},\mathrm{SSS},"
                r"\mathrm{SSH},u,v,w_u,w_v\big)",
        formula_note=("f_θ is the trained TS-Cast network. The seven inputs are surface satellite "
                      "fields over an 11-day window ending on the chosen date; z runs over the 15 "
                      "standard depths from 0 to 1000 m. The network emits a mean AND a variance "
                      "at every depth, which is where the shaded band comes from."),
        how_to_read=("The shaded band is ±2σ. A tight band means the model is confident here; a "
                     "wide one means treat the exact number with suspicion. A blank cell is land "
                     "or seafloor — click it and the page will say which — never a missing "
                     "prediction."),
        caveats=tuple(caveats),
        references=(
            "Argo float data collected and made freely available by the International Argo "
            "Program and the national programmes that contribute to it (https://argo.ucsd.edu).",
        ))


def _previous_pick(key: str):
    """The cell chosen on the LAST run, from widget state, before the chart is rebuilt.

    `st.altair_chart(..., on_select="rerun")` hands the selection back only as its return value --
    i.e. after the chart has already been built. To draw a marker ON the map the selection has to
    be known first, and Streamlit keeps it in session_state under the chart's key. Same value, read
    one step earlier.
    """
    sel = (st.session_state.get(key) or {}).get("selection", {}).get("pick") or []
    return (int(sel[0]["i"]), int(sel[0]["j"])) if sel else None


def main() -> None:
    st.title("Click a point — what the model says is underneath it")
    st.caption("Every cell in the basin has a full 15-level profile, every day. Pick one.")

    with st.sidebar:
        st.header("What to show")
        stage = 1
        ver = _fields.version(stage)
        date_str = _fields.date_picker(stage, label="date", key="cm_date")
        depth_m = st.select_slider("depth for the map", options=list(v2config.DEPTHS),
                                   value=100, format_func=lambda d: f"{d} m")
        device = _fields.device_picker(key="cm_dev")

    try:
        df = slice_frame(date_str, float(depth_m), stage, ver, device)
    except Exception as e:
        st.error(f"Could not reconstruct {date_str}: {e}")
        st.info("The satellite bundle and the checkpoint must both be on this machine.")
        return

    level_m = float(v2config.DEPTHS[MF.nearest_level(v2config.DEPTHS, depth_m)])
    n = MF.counts({"kind": df["kind"].to_numpy()})

    ij = _previous_pick("cm_map")
    at = None
    if ij is not None:
        hit = df[(df["i"] == ij[0]) & (df["j"] == ij[1])]
        if not hit.empty:
            at = (float(hit.iloc[0]["lat"]), float(hit.iloc[0]["lon"]))

    event = st.altair_chart(map_chart(df, level_m, at), key="cm_map",
                            on_select="rerun", use_container_width=False)
    st.caption(
        f"{df.attrs['date']} · {level_m:.0f} m · {n[MF.WATER]:,} cells with water · "
        f"{n[MF.SEAFLOOR]:,} below the seafloor at this depth · {n[MF.LAND]:,} land. "
        f"Colour is the model's prediction; blank is not ocean.")

    picked = (event or {}).get("selection", {}).get("pick") or []
    calibrated = True
    left, right = st.columns([2, 3], gap="large")

    with left:
        if not picked:
            st.info("**Click any cell on the map.** Its full vertical profile appears here.")
            st.caption("Land and below-seafloor cells are clickable too — they say which they are "
                       "rather than showing an empty chart.")
        else:
            i, j = int(picked[0]["i"]), int(picked[0]["j"])
            row = df[(df["i"] == i) & (df["j"] == j)].iloc[0]
            st.subheader(f"{row['lat']:.2f} °N, {row['lon']:.2f} °E")

            if row["kind"] != MF.WATER:
                st.warning(MF.KIND_NOTE[row["kind"]].format(depth=level_m))
                st.caption("A statement about the ocean floor, not a failed prediction.")
            else:
                p = profile_at(i, j, date_str, stage, ver, device)
                calibrated = bool(p["calibrated"])
                chart = profile_chart(p)
                if chart is None:
                    st.warning("Every level at this cell is below the seafloor.")
                else:
                    st.altair_chart(chart, use_container_width=True)
                    mean = np.asarray(p["mean"], dtype="float64")
                    sig = np.asarray(p["sigma"], dtype="float64")
                    fin = int(np.isfinite(mean).sum())
                    st.caption(
                        f"{p['date']} · {fin} of 15 levels have water · surface "
                        f"{mean[0]:.2f} °C → {np.nanmin(mean):.2f} °C at the deepest · "
                        f"±2σ spans {2 * np.nanmin(sig):.2f}–{2 * np.nanmax(sig):.2f} °C, "
                        f"{'calibrated' if calibrated else 'RAW (uncalibrated)'}")
                    if not calibrated:
                        st.warning(f"Uncertainty is uncalibrated here — {p['why']}")

    with right:
        render(explainer(calibrated))


if __name__ == "__main__":
    main()
