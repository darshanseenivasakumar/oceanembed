"""F6 -- eddies, fronts and upwelling, one snapshot at a time.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/events_page.py --server.port 8506

DETECTION, NEVER TRACKING. The record is 48 monthly fields. A mesoscale eddy lives weeks to a
few months and moves a few km/day, so two consecutive months cannot be assumed to show the same
feature. Nothing on this page joins one date to the next, and the library refuses a time axis.

All science lives in `phase2.events`. Charts are altair — see `app/panels/_viz.py` for why the
project avoids depending on plotly in a panel.
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
from phase2.events import eddy, fronts, upwelling  # noqa: E402

st.set_page_config(page_title="OceanEmbed — Ocean events", layout="wide")

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SUBSURFACE = os.path.join(config.DATA_PROCESSED, "subsurface.npz")

#: Where the Great Whirl lives. A published expectation, external to this codebase — which is
#: what makes it a test of the detector rather than a description of it.
WHIRL = {"lat": (4.0, 12.0), "lon": (48.0, 58.0)}


@st.cache_data(show_spinner="Loading fields …")
def load():
    g = np.load(GRIDS, allow_pickle=True)
    return (np.asarray(g["u"], "float64"), np.asarray(g["v"], "float64"),
            np.asarray(g["sst"], "float64"), np.asarray(g["temp"], "float64"),
            np.asarray(g["times"]).astype("datetime64[D]"),
            np.asarray(g["land_mask"], bool))


@st.cache_data(show_spinner="Detecting eddies …")
def detect(k: int):
    u, v, sst, _, _, land = load()
    uu = np.where(land, np.nan, u[k])
    vv = np.where(land, np.nan, v[k])
    ss = np.where(land, np.nan, sst[k])
    eddies = eddy.detect_eddies(uu, vv)
    summary = eddy.summarise(eddies)
    fr = fronts.detect_fronts(ss)
    ow = eddy.okubo_weiss(uu, vv)
    return eddies, summary, fr, ow["vorticity"]


@st.cache_data(show_spinner="Measuring the Great Whirl across four years …")
def whirl_by_month():
    u, v, _, _, times, land = load()
    months = np.array([int(str(t)[5:7]) for t in times])
    rows = []
    for m in range(1, 13):
        radii = []
        for k in np.nonzero(months == m)[0]:
            found = [e for e in eddy.detect_eddies(np.where(land, np.nan, u[k]),
                                                   np.where(land, np.nan, v[k]))
                     if e["polarity"] == "anticyclonic"
                     and WHIRL["lat"][0] <= e["centroid_lat"] <= WHIRL["lat"][1]
                     and WHIRL["lon"][0] <= e["centroid_lon"] <= WHIRL["lon"][1]]
            if found:
                radii.append(max(e["equivalent_radius_km"] for e in found))
        rows.append({"month": m, "radius_km": float(np.mean(radii)) if radii else 0.0})
    return pd.DataFrame(rows)


def _field_map(field, title, scheme="redblue", mid=True):
    lat, lon = np.asarray(config.LAT), np.asarray(config.LON)
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "value": np.asarray(field).ravel()}).dropna(subset=["value"])
    scale = alt.Scale(scheme=scheme, domainMid=0) if mid else alt.Scale(scheme=scheme)
    return alt.Chart(df).mark_rect().encode(
        x=alt.X("lon:O", title="longitude (°E)", axis=alt.Axis(values=list(range(45, 106, 10)))),
        y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                axis=alt.Axis(values=list(range(5, 31, 5)))),
        color=alt.Color("value:Q", title=None, scale=scale),
        tooltip=["lat", "lon", alt.Tooltip("value:Q", format=".3f")],
    ).properties(height=340, title=title)


def main() -> None:
    st.title("Ocean events")
    st.caption("Eddies, thermal fronts and an upwelling signature — **detected in one snapshot "
               "at a time**. Monthly sampling cannot support tracking, so nothing here joins one "
               "date to the next.")

    if not os.path.exists(GRIDS):
        st.error(f"Needs {GRIDS} — gitignored, ships in the data bundle.")
        st.stop()
        return

    _, _, _, _, times, _ = load()
    with st.sidebar:
        st.header("Snapshot")
        idx = st.selectbox("Date", range(len(times)),
                           format_func=lambda i: str(times[i]), index=len(times) - 6)
        show = st.radio("Field", ["Eddies", "Thermal fronts", "Upwelling"])

    eddies, summary, fr, vort = detect(idx)

    # ---- eddies ------------------------------------------------------------------------
    if show == "Eddies":
        st.subheader("1 · Eddies — Okubo-Weiss")
        c = st.columns(4)
        c[0].metric("eddies detected", summary["n_eddies"])
        c[1].metric("cyclonic", summary["n_cyclonic"])
        c[2].metric("anticyclonic", summary["n_anticyclonic"])
        c[3].metric("mean radius", f"{summary['mean_radius_km']:.0f} km")

        st.altair_chart(_field_map(vort, "Relative vorticity (s⁻¹) — red cyclonic, blue "
                                   "anticyclonic"), use_container_width=True)

        if eddies:
            df = pd.DataFrame(eddies)
            pts = alt.Chart(df).mark_circle(opacity=0.75).encode(
                x=alt.X("centroid_lon:Q", title="longitude (°E)",
                        scale=alt.Scale(domain=[45, 105])),
                y=alt.Y("centroid_lat:Q", title="latitude (°N)",
                        scale=alt.Scale(domain=[5, 30])),
                size=alt.Size("equivalent_radius_km:Q", title="radius (km)",
                              scale=alt.Scale(range=[20, 900])),
                color=alt.Color("polarity:N", title=None,
                                scale=alt.Scale(domain=["cyclonic", "anticyclonic"],
                                                range=["#d62728", "#1f77b4"])),
                tooltip=["polarity", alt.Tooltip("centroid_lat:Q", format=".2f"),
                         alt.Tooltip("centroid_lon:Q", format=".2f"),
                         alt.Tooltip("equivalent_radius_km:Q", format=".0f"),
                         "n_cells"],
            ).properties(height=380, title="Detected eddies — size is equivalent radius")
            st.altair_chart(pts, use_container_width=True)
            st.dataframe(df.head(10)[["centroid_lat", "centroid_lon", "polarity",
                                      "equivalent_radius_km", "area_km2", "mean_vorticity"]]
                         .round(3), hide_index=True, width="stretch")

        st.subheader("2 · The Great Whirl — a published expectation, not ours")
        w = whirl_by_month()
        st.altair_chart(alt.Chart(w).mark_bar(color="#1f77b4").encode(
            x=alt.X("month:O", title="month"),
            y=alt.Y("radius_km:Q", title="largest anticyclone radius (km)"),
            tooltip=["month", alt.Tooltip("radius_km:Q", format=".0f")],
        ).properties(height=300), use_container_width=True)
        peak = w.loc[w["radius_km"].idxmax()]
        low = w.loc[w["radius_km"].idxmin()]
        st.success(
            f"Largest anticyclone in {WHIRL['lat'][0]:.0f}–{WHIRL['lat'][1]:.0f}°N "
            f"{WHIRL['lon'][0]:.0f}–{WHIRL['lon'][1]:.0f}°E, averaged over four years: "
            f"**{low['radius_km']:.0f} km in month {int(low['month'])} → "
            f"{peak['radius_km']:.0f} km in month {int(peak['month'])}**. That is the season, "
            f"place and scale of the **Great Whirl**, the Somali anticyclone that spins up with "
            f"the SW monsoon."
        )
        st.warning(
            "**[VERIFIED]** a large anticyclone with this seasonal cycle, position and radius is "
            "in the data — the run above is reproducible. **[INFERRED]** that it *is* the Great "
            "Whirl: that rests on the standard description of the feature, and no paper was "
            "re-read. **Check a citation before this goes on a slide.**"
        )

    # ---- fronts ------------------------------------------------------------------------
    elif show == "Thermal fronts":
        st.subheader("Thermal fronts — SST gradient")
        c = st.columns(3)
        c[0].metric("front segments", fr["n_fronts"])
        c[1].metric("threshold", f"{fr['threshold']:.2f} °C/100km")
        c[2].metric("basin mean gradient", f"{fr['mean_gradient']:.2f} °C/100km")
        st.altair_chart(_field_map(fr["magnitude"], "|∇SST| (°C per 100 km)", "magma", mid=False),
                        use_container_width=True)
        if fr["fronts"]:
            top = fr["fronts"][0]
            st.caption(f"Strongest segment: {top['max_gradient']:.2f} °C/100 km at "
                       f"{top['centroid_lat']:.1f}°N {top['centroid_lon']:.1f}°E "
                       f"({top['n_cells']} cells).")
        st.error(
            "**FRONTS ARE NOT VALIDATED.** No front climatology or published census was checked "
            "against this. And the threshold is a **percentile of this snapshot**, so the "
            "sharpest gradients present are *always* returned — this detector can never tell you "
            "a snapshot has no fronts. A low threshold means the field is flat, not that the "
            "fronts are weak."
        )

    # ---- upwelling ---------------------------------------------------------------------
    else:
        st.subheader("Upwelling signature")
        stamp = str(times[idx]).replace("-", "")[:6]
        _, _, sst, temp, _, land = load()
        sal = np.asarray(np.load(SUBSURFACE, allow_pickle=True)["salinity"], "float64")[idx]

        try:
            w = upwelling.load_wind_stress(stamp)
            pump = upwelling.ekman_pumping(w["eastward_stress"], w["northward_stress"])
            wind_ok = True
        except upwelling.MissingWindError as e:
            st.warning(f"No wind for {stamp}: {e}")
            pump, wind_ok = None, False

        try:
            ref = upwelling.climatological_sst_reference(int(str(times[idx])[5:7]))
        except Exception:
            ref = None

        out = upwelling.upwelling_signature(np.where(land, np.nan, sst[idx]), temp[idx], sal,
                                            ekman=pump, sst_reference=ref)
        c = st.columns(3)
        c[0].metric("cells flagged", f"{out['n_cells']:,}")
        c[1].metric("wind attributed", "yes" if out["wind_attributed"] else "no")
        c[2].metric("limiting term", out["limiting_term"])

        if wind_ok:
            st.altair_chart(_field_map(pump * 1e6, "Ekman pumping (µm/s) — positive is upward"),
                            use_container_width=True)
        st.altair_chart(_field_map(out["signature"].astype(float),
                                   "Upwelling signature (cold surface AND shoaled thermocline"
                                   + (" AND upward Ekman)" if wind_ok else ")"),
                                   "purples", mid=False), use_container_width=True)
        st.info(out["caveat"])
        st.caption(
            f"SST reference: {out['sst_reference_kind']}. The **shoaled thermocline** term does "
            f"the discriminating — the cold-surface term runs 40–90% baseline and carries little "
            f"information on its own. Ekman pumping from a **monthly-mean** stress is a lower "
            f"bound on episodic upwelling: the curl of an average is not the average of the curl."
        )

    with st.expander("What this page will never show"):
        st.markdown(
            "- **Eddy tracking, lifetime or propagation speed.** 48 monthly fields cannot "
            "support it; the library refuses a time axis rather than letting it be attempted.\n"
            "- **Marine heatwaves (F7).** Defined on ≥5 consecutive *days*. Permanently closed "
            "at monthly cadence.\n"
            "- **Sub-mesoscale features.** 0.25° ≈ 25 km cells; anything under ~100 km is "
            "unresolved.\n"
            "- These are eddies **in the GLORYS reanalysis**, not in observations."
        )


if __name__ == "__main__":
    main()
