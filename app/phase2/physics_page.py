"""F5 -- ocean structure: mixed layer, barrier layer, thermocline, heat content.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/physics_page.py --server.port 8505

All science lives in `phase2.physics`. This file only lays it out — if a number appears here that
the library did not compute, that is a bug.

Charts are altair, which ships with Streamlit. `app/panels/_viz.py` records why that matters:
a panel that ImportErrors on demo day is worse than a plainer chart.

THE SOURCE TOGGLE (added 2026-09-03), AND THE ERA BUG IT FIXED
This page used to read `data/processed/grids.npz` exclusively: Phase-1 GLORYS, 48 MONTHLY steps,
2019-01-15..2022-12-15. So every panel showed 2022 while the shipped model two ports away ran on
2025-2026 -- and nothing on screen said the two were different eras. `data/processed/daily` has
carried GLORYS daily 2025-06-01..2026-06-23, salinity included, the whole time.

Both toggle positions now read the SAME DAY from the SAME bundle:

  * "glorys"       -- the GLORYS12V1 target itself: all four fields, real density rho(S, theta).
  * "v2 satellite" -- the shipped model's reconstruction: thermocline, ILD and a CONSTANT-density
                      OHC. MLD and the barrier layer are REFUSED.

That makes the toggle a model-vs-truth comparison on one grid and one date, which is what it
should have been. It is not a comparison of two eras, and neither position is Phase-1 monthly.

WHY THE REFUSAL IS NOT A MISSING FEATURE
`salinity` sits in the very bundle the v2 branch reads, and the glorys branch uses it. It is
GLORYS REANALYSIS -- target-side, byte-identical between both bundles -- not anything the seven
satellite input channels produced. Borrowing it for a "v2 satellite" MLD would put reanalysis
inside a number labelled satellite: the exact contamination the anti-GLORYS guard exists to catch,
and what the PS excludes with "only surface satellite observations". The model carries a SURFACE
`sss` input; nothing in it predicts salinity AT DEPTH, and stage 2, which would, has never been
trained on satellite input. So the refusal is a compliance boundary, and the honest result.

Section 3 alone still reads the Phase-1 2019-2022 monthly bundle, because a seasonal climatology
needs several years per month and its published magnitudes were measured there. It says so.
"""
from __future__ import annotations

import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config  # noqa: E402
from phase2.physics import layers, ohc  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Ocean structure", layout="wide")

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SUBSURFACE = os.path.join(config.DATA_PROCESSED, "subsurface.npz")

#: LEGACY, AND DELIBERATELY NOT THE CANONICAL PARTITION.
#: `src/phase2/basins.py` is the one canonical Arabian Sea / Bay of Bengal definition, and every
#: model metric goes through it. These two small boxes are kept ONLY because the validated
#: seasonal claim on this page was measured over them: swapping in the canonical masks would
#: silently change a published magnitude without re-deriving it. They are frozen to that claim.
#: Do not reuse them anywhere else, and do not add a third definition -- import phase2.basins.
#: Stated here rather than buried, because Unit B and Unit A used DIFFERENT boxes and got
#: different magnitudes for the same (correct) conclusion — so the box definition is part of
#: the result.
BOB = {"name": "Bay of Bengal", "lat": (15.0, 22.0), "lon": (85.0, 95.0)}
ARABIAN = {"name": "Arabian Sea", "lat": (10.0, 22.0), "lon": (60.0, 72.0)}


@st.cache_data(show_spinner="Loading the ocean …")
def load():
    g = np.load(GRIDS, allow_pickle=True)
    s = np.load(SUBSURFACE, allow_pickle=True)
    return (np.asarray(g["temp"], "float64"), np.asarray(s["salinity"], "float64"),
            np.asarray(g["times"]).astype("datetime64[D]"),
            np.asarray(g["land_mask"], bool))


def _v2_version() -> str:
    """Cache key for the two v2 caches below. See `field.v2_cache_version` for why this exists."""
    from phase2.tscast_nio.field import v2_cache_version
    return v2_cache_version()


@st.cache_resource(show_spinner="Loading the shipped model …")
def _v2_predictor(version: str):
    from phase2.tscast_nio.inference import TSCastPredictor
    return TSCastPredictor()


def _v2_dates(version: str) -> list[str]:
    """The v2 model's real calendar (2025-06-01..2026-06-23) -- never the GLORYS list.

    cube_page carried this exact bug: offering GLORYS' 48 2019-2022 dates while silently
    reconstructing 1000+ days away on the satellite bundle. Fixed there in this same commit; this
    page gets its v2 date list built correctly from the start rather than inheriting the bug.
    """
    times = np.asarray(_v2_predictor(version).data["times"]).astype("datetime64[D]")
    return [str(t) for t in times]


@st.cache_data(show_spinner="Reading GLORYS at this date …")
def layer_fields_glorys(date_str: str, version: str) -> dict:
    """All four fields from GLORYS daily reanalysis — the model's own training target.

    Reads `temp` and `salinity` straight out of the bundle the predictor ALREADY holds. Those two
    arrays are byte-identical to `data/processed/daily` (checked 2026-09-03: both bundles carry the
    same GLORYS12V1 target), so this costs no second load — and, more to the point, it guarantees
    the two toggle positions are the same grid, the same day and the same file. That makes the
    toggle a real model-vs-truth comparison instead of two different eras, which is what it was
    when this page read the Phase-1 2019-2022 monthly grids and the v2 branch read 2025-2026.

    The subsurface salinity here is GLORYS, NOT satellite-derived — which is exactly why
    `layer_fields_v2` refuses to borrow it. See that function.
    """
    p = _v2_predictor(version)
    t_idx, _ = p._time(date_str)
    t = np.asarray(p.data["temp"][t_idx], "float64")
    s = np.asarray(p.data["salinity"][t_idx], "float64")
    land = np.asarray(p.data["land_mask"], bool)

    th = layers.thermocline(t)
    out = {"MLD (density, m)": layers.mixed_layer_depth(s, t),
           "Thermocline depth (m)": th["depth"],
           "Barrier layer (m)": layers.barrier_layer_thickness(s, t),
           "OHC 0–300 m (GJ/m²)": ohc.ohc(s, t, 300.0),
           "ILD (temperature, m)": layers.isothermal_layer_depth(t)}
    out = {k: np.where(land, np.nan, v) for k, v in out.items()}
    out.update({
        "temperature": t, "salinity": s, "land_mask": land,
        "date": str(np.asarray(p.data["times"])[t_idx])[:10],
        "provenance": {
            "source": "GLORYS12V1 daily reanalysis (the model's training target)",
            "bundle": p.meta.get("bundle"),
            "density": "real ρ(S, θ) from EOS-80 — not an assumed constant",
            "note": "reanalysis, not an observation and not a model prediction",
        },
    })
    return out


@st.cache_data(show_spinner="Reconstructing from satellite …")
def layer_fields_v2(date_str: str, version: str) -> dict:
    """Thermocline, ILD and constant-density OHC from the SHIPPED v2 model. Temperature only.

    `"MLD (density, m)"` and `"Barrier layer (m)"` are present and `None`, and the caller must
    render that as a refusal -- not skip the key and let a KeyError stand in for an explicit
    "not available".

    WHY REFUSE, WHEN SALINITY IS SITTING RIGHT THERE
    `p.data["salinity"]` exists in this very bundle and `layer_fields_glorys` above uses it. It is
    GLORYS12V1 REANALYSIS -- the target side, byte-identical to the GLORYS bundle -- not anything
    the satellite inputs produced. Combining it with v2's reconstructed temperature would put a
    reanalysis field inside a number labelled "satellite", which is the exact contamination
    `scripts/phase2/verify_sat_bundle.py` and the anti-GLORYS guard exist to prevent, and it is
    what the PS means by "only surface satellite observations". The 7 input channels carry a
    SURFACE `sss` (SMOS blend); nothing in this model predicts salinity AT DEPTH, and stage 2,
    which would, has never been trained on satellite input.

    So the refusal is a compliance boundary, not a missing feature. Switch the source toggle to
    glorys to see all four fields honestly labelled as reanalysis.

    `"OHC 0–300 m (GJ/m²)"` here is `ohc_constant_density`, NOT the real-density `ohc.ohc` the
    glorys panel shows -- see the module docstring. The two are not the same claim and must never
    be shown side by side without saying which is which.
    """
    from phase2.tscast_nio.field import predict_field

    f = predict_field(_v2_predictor(version), date_str)
    t = f["temperature"]                                    # (lat, lon, depth) -- matches layers/ohc
    th = layers.thermocline(t)
    ild = layers.isothermal_layer_depth(t)
    heat = ohc.ohc_constant_density(t, 300.0)
    return {
        "MLD (density, m)": None,
        "Thermocline depth (m)": th["depth"],
        "Barrier layer (m)": None,
        "OHC 0–300 m (GJ/m²)": heat,
        "ILD (temperature, m)": ild,
        "temperature": t,
        "land_mask": f["land_mask"],
        "date": f["date"],
        "provenance": f["provenance"],
    }


@st.cache_data(show_spinner="Measuring the seasonal cycle …")
def barrier_by_month():
    """The validated F5 claim, measured across ALL months.

    Unit B's lesson, learned the hard way: a SINGLE DATE inverts this signal. The Bay of Bengal
    barrier layer peaks in March and through the monsoon and collapses in winter, so December
    alone shows the Arabian Sea thicker and looks like a refutation.
    """
    theta, sal, times, land = load()
    blt = layers.barrier_layer_thickness(sal, theta)
    lat, lon = np.asarray(config.LAT), np.asarray(config.LON)
    months = np.array([int(str(t)[5:7]) for t in times])
    rows = []
    for box in (BOB, ARABIAN):
        i = (lat >= box["lat"][0]) & (lat <= box["lat"][1])
        j = (lon >= box["lon"][0]) & (lon <= box["lon"][1])
        for m in range(1, 13):
            sel = blt[months == m][:, i][:, :, j]
            rows.append({"month": m, "box": box["name"],
                         "thickness_m": float(np.nanmean(sel))})
    return pd.DataFrame(rows)


def _map(field: np.ndarray, title: str, scheme: str = "viridis", reverse: bool = False):
    lat, lon = np.asarray(config.LAT), np.asarray(config.LON)
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "value": field.ravel()}).dropna(subset=["value"])
    return alt.Chart(df).mark_rect().encode(
        x=alt.X("lon:O", title="longitude (°E)", axis=alt.Axis(values=list(range(45, 106, 10)))),
        y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                axis=alt.Axis(values=list(range(5, 31, 5)))),
        color=alt.Color("value:Q", title=None,
                        scale=alt.Scale(scheme=scheme, reverse=reverse)),
        tooltip=["lat", "lon", alt.Tooltip("value:Q", format=".1f")],
    ).properties(height=300, title=title)


def main() -> None:
    if not (os.path.exists(GRIDS) and os.path.exists(SUBSURFACE)):
        st.title("Ocean structure")
        st.error(f"Needs {GRIDS} and {SUBSURFACE}. Both are gitignored and ship in the data "
                 "bundle.")
        st.stop()
        return

    v2v = _v2_version()
    dates = _v2_dates(v2v)
    with st.sidebar:
        st.header("Snapshot")
        source = st.radio(
            "Source", ["v2 satellite", "glorys"], index=0,
            help="Both read the SAME day from the SAME bundle, so this is a model-vs-truth "
                 "comparison, not two different eras. v2 satellite = the shipped model's "
                 "reconstruction, temperature only -- MLD and the barrier layer are refused "
                 "because borrowing GLORYS salinity would put reanalysis inside a number "
                 "labelled satellite. glorys = the GLORYS12V1 target itself, real density "
                 "from S and theta -- all four fields.")
        is_v2 = source == "v2 satellite"
        date_str = st.selectbox("Date", options=dates, index=len(dates) - 6)
        st.divider()
        st.caption("Profile inspector")
        p_lat = st.slider("Latitude (°N)", float(config.LAT[0]), float(config.LAT[-1]), 18.0, 0.25)
        p_lon = st.slider("Longitude (°E)", float(config.LON[0]), float(config.LON[-1]), 88.0, 0.25)

    st.title("Ocean structure")
    if is_v2:
        st.caption("Mixed layer, barrier layer, thermocline and heat content — from the "
                   "**shipped v2 satellite model, temperature only**. MLD and the barrier layer "
                   "need salinity AT DEPTH, which no satellite observes and this model does not "
                   "predict; they are refused below, not approximated.")
    else:
        st.caption("Mixed layer, barrier layer, thermocline and heat content — from the "
                   "**GLORYS12V1 daily reanalysis**, the model's own training target, with "
                   "**real seawater density** ρ(S, θ) rather than an assumed constant. "
                   "Reanalysis, not an observation.")

    fields = layer_fields_v2(date_str, v2v) if is_v2 else layer_fields_glorys(date_str, v2v)

    # ---- 1. the maps -------------------------------------------------------------------
    st.subheader("1 · Structure across the basin")
    c1, c2 = st.columns(2)
    with c1:
        if fields["MLD (density, m)"] is None:
            st.warning("**MLD (density) not available on v2** — needs salinity; the shipped "
                       "model predicts temperature only.")
        else:
            st.altair_chart(_map(fields["MLD (density, m)"], "Mixed layer depth (m) — density "
                                 "criterion", "blues"), use_container_width=True)
    with c2:
        st.altair_chart(_map(fields["Thermocline depth (m)"], "Thermocline depth (m)", "plasma"),
                        use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        if fields["Barrier layer (m)"] is None:
            st.warning("**Barrier layer not available on v2** — it is ILD − MLD, and MLD needs "
                       "salinity (see above).")
        else:
            st.altair_chart(_map(fields["Barrier layer (m)"], "Barrier layer thickness (m)",
                                 "purples"), use_container_width=True)
    with c4:
        ohc_title = ("Ocean heat content 0–300 m (GJ/m²) — constant density" if is_v2 else
                     "Ocean heat content 0–300 m (GJ/m²)")
        st.altair_chart(_map(fields["OHC 0–300 m (GJ/m²)"], ohc_title, "inferno"),
                        use_container_width=True)

    if is_v2:
        st.info(
            "**Thermocline and OHC above are real v2 output; MLD and the barrier layer are "
            "refused, not approximated.** OHC here uses an ASSUMED CONSTANT density — the "
            "glorys panel's real-density ρ(S, θ) integral needs salinity this model does not "
            "predict. `phase2/physics/ohc.py` measures that assumption's cost directly at up to "
            "~2%, worst in the northern Bay of Bengal river-plume region — so read v2's OHC as "
            "an approximation, not the calibrated headline number. Switch to **glorys** for the "
            "real-density product and the density-criterion MLD."
        )
    else:
        st.info(
            "**The mixed layer uses the DENSITY criterion** (de Boyer Montégut et al. 2004, "
            "0.03 kg/m³ from 10 m), not temperature. The two disagree wherever salinity sets the "
            "stratification — and **their difference IS the barrier layer**. A temperature-only MLD "
            "is systematically too deep in the northern Bay of Bengal, by ≥ 50 m on a realistic "
            "river-plume profile: the cyclone-genesis region, and the cell our priority map ranks "
            "first."
        )

    # ---- 2. the profile ----------------------------------------------------------------
    st.subheader("2 · One column")
    i = int(np.argmin(np.abs(np.asarray(config.LAT) - p_lat)))
    j = int(np.argmin(np.abs(np.asarray(config.LON) - p_lon)))

    if is_v2:
        land = fields["land_mask"]
        if land[i, j]:
            st.warning(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E is land.")
        else:
            t_col = fields["temperature"][i, j]
            prof = pd.DataFrame({"depth": config.DEPTHS, "temperature": t_col})
            ild = float(fields["ILD (temperature, m)"][i, j])
            thd = float(fields["Thermocline depth (m)"][i, j])

            base = alt.Chart(prof).mark_line(point=True).encode(
                y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)))
            t_line = base.encode(x=alt.X("temperature:Q", title="temperature (°C)"),
                                 tooltip=["depth", "temperature"]).properties(height=380)
            marks = alt.Chart(pd.DataFrame({
                "depth": [ild, thd],
                "layer": ["ILD (temperature)", "thermocline"],
            })).mark_rule(strokeDash=[5, 3]).encode(
                y="depth:Q", color=alt.Color("layer:N", title=None),
                tooltip=["layer", alt.Tooltip("depth:Q", format=".0f")])

            st.altair_chart(t_line + marks, use_container_width=True)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("MLD (density)", "n/a", help="needs salinity — not predicted by v2")
            m2.metric("ILD (temperature)", f"{ild:.0f} m")
            m3.metric("Barrier layer", "n/a", help="needs MLD — not available on v2")
            m4.metric("Thermocline", f"{thd:.0f} m")
            st.caption(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E on {fields['date']}. "
                       "v2 satellite model, temperature only — no salinity line, no MLD, no "
                       "barrier layer.")
        with st.expander("Provenance — what produced the fields above"):
            st.json(fields["provenance"])
    else:
        land = fields["land_mask"]
        if land[i, j]:
            st.warning(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E is land.")
        else:
            t_col, s_col = fields["temperature"][i, j], fields["salinity"][i, j]
            prof = pd.DataFrame({"depth": config.DEPTHS, "temperature": t_col, "salinity": s_col})
            mld = float(fields["MLD (density, m)"][i, j])
            ild = float(fields["ILD (temperature, m)"][i, j])
            thd = float(fields["Thermocline depth (m)"][i, j])

            base = alt.Chart(prof).mark_line(point=True).encode(
                y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)))
            t_line = base.encode(x=alt.X("temperature:Q", title="temperature (°C)"),
                                 tooltip=["depth", "temperature"]).properties(height=380)
            s_line = base.mark_line(point=True, color="#8c6bb1").encode(
                x=alt.X("salinity:Q", title="salinity (psu)"),
                tooltip=["depth", "salinity"]).properties(height=380)

            marks = alt.Chart(pd.DataFrame({
                "depth": [mld, ild, thd],
                "layer": ["MLD (density)", "ILD (temperature)", "thermocline"],
            })).mark_rule(strokeDash=[5, 3]).encode(
                y="depth:Q", color=alt.Color("layer:N", title=None),
                tooltip=["layer", alt.Tooltip("depth:Q", format=".0f")])

            st.altair_chart(alt.hconcat(t_line + marks, s_line + marks), use_container_width=True)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("MLD (density)", f"{mld:.0f} m")
            m2.metric("ILD (temperature)", f"{ild:.0f} m")
            m3.metric("Barrier layer", f"{ild - mld:.0f} m")
            m4.metric("Thermocline", f"{thd:.0f} m")
            st.caption(f"{config.LAT[i]:.2f}°N {config.LON[j]:.2f}°E on {fields['date']}. "
                       "GLORYS reanalysis. Barrier layer = ILD − MLD: the layer that is "
                       "isothermal but **not** isopycnal, because fresh water is holding it "
                       "apart.")
        with st.expander("Provenance — what produced the fields above"):
            st.json(fields["provenance"])

    # ---- 3. the validated claim --------------------------------------------------------
    st.subheader("3 · The barrier layer is seasonal — and that is the result")
    st.caption("Measured on **Phase-1 GLORYS monthly, 2019–2022** — a different bundle from the "
               "2025–2026 daily one the panels above use, and unaffected by the source toggle. A "
               "seasonal climatology needs several years per month; the 388-day daily bundle "
               "covers each month about once, and recomputing on it would silently change the "
               "published magnitudes below.")
    df = barrier_by_month()
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("month:O", title="month"),
        y=alt.Y("thickness_m:Q", title="mean barrier layer (m)"),
        color=alt.Color("box:N", title=None,
                        scale=alt.Scale(range=["#4a1486", "#9ecae1"])),
        xOffset="box:N",
        tooltip=["month", "box", alt.Tooltip("thickness_m:Q", format=".1f")],
    ).properties(height=320)
    st.altair_chart(chart, use_container_width=True)

    piv = df.pivot(index="month", columns="box", values="thickness_m")
    bob_wins = int((piv[BOB["name"]] > piv[ARABIAN["name"]]).sum())
    a, b = st.columns(2)
    a.metric(f"{BOB['name']} annual mean", f"{piv[BOB['name']].mean():.1f} m")
    b.metric(f"{ARABIAN['name']} annual mean", f"{piv[ARABIAN['name']].mean():.1f} m")
    st.warning(
        f"**A single date inverts this signal — measure across months.** The Bay of Bengal is "
        f"thicker in **{bob_wins} of 12** months, peaking in March and through the monsoon with "
        f"river discharge, and collapsing in winter when cooling deepens the mixed layer. Unit B "
        f"first checked one December date, got the opposite answer, and nearly reported a false "
        f"failure. Boxes: BoB {BOB['lat'][0]:.0f}–{BOB['lat'][1]:.0f}°N "
        f"{BOB['lon'][0]:.0f}–{BOB['lon'][1]:.0f}°E, Arabian "
        f"{ARABIAN['lat'][0]:.0f}–{ARABIAN['lat'][1]:.0f}°N "
        f"{ARABIAN['lon'][0]:.0f}–{ARABIAN['lon'][1]:.0f}°E — the two units used different boxes "
        f"and got different magnitudes for the same conclusion, so the box is part of the result."
    )

    with st.expander("What this is NOT"):
        st.markdown(
            "- **Not a validated OHC in absolute terms, even on glorys.** The density there is "
            "real ρ(S, θ); the integral still assumes a constant specific heat capacity.\n"
            "- **The barrier layer is a derived quantity**, not an observation. It is ILD − MLD, "
            "so it inherits every assumption in both criteria.\n"
            "- **One snapshot at a time on both sources** — monthly on glorys, daily on v2 "
            "satellite, but neither shows an event, a storm response, or day-to-day variability "
            "here.\n"
            "- **v2 satellite has no MLD, no barrier layer, and only the constant-density OHC "
            "approximation** — salinity has never been trained on the satellite bundle. That is "
            "an explicit refusal, not a silent fallback to glorys under the v2 label."
        )


if __name__ == "__main__":
    main()
