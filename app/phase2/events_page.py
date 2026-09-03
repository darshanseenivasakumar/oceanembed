"""F6 -- eddies, fronts and upwelling, one snapshot at a time.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/events_page.py --server.port 8506

DETECTION, NOT TRACKING -- AND THE REASON CHANGED ON 2026-09-03
This page used to read `data/processed/grids.npz` exclusively: Phase-1 GLORYS, 48 MONTHLY fields,
2019-2022. That made tracking genuinely impossible (an eddy moves a few km/day, so consecutive
MONTHS cannot be assumed to show the same feature) and the docstring said so as a permanent fact.

It now reads the daily bundles instead -- 388 CONSECUTIVE DAYS, 2025-06-01..2026-06-23 -- so that
argument no longer holds. Tracking, and marine heatwaves with it, are now UNBUILT rather than
impossible. Nothing here joins one date to the next and the library still refuses a time axis;
that is a gap we are stating, not a limit of the data. Do not let the old wording stand in for a
justification it no longer provides.

The source toggle picks which SURFACE fields the detectors read:
  * "satellite" -- GLOBCURRENT currents + OSTIA SST, genuine observations, the PS deliverable
  * "glorys"    -- the reanalysis of the same days
No model reconstruction is involved in either: eddies and fronts are surface diagnostics. The
upwelling panel is the exception -- its shoaled-thermocline term needs subsurface T and S, which
is GLORYS in both bundles, and it says so on screen.

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

#: Phase-1 GLORYS monthly, 2019-2022. Still read by the Great Whirl seasonal panel ONLY --
#: that claim is a four-year climatology and cannot be recomputed on a 388-day record.
GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")

#: Where the Great Whirl lives. A published expectation, external to this codebase — which is
#: what makes it a test of the detector rather than a description of it.
WHIRL = {"lat": (4.0, 12.0), "lon": (48.0, 58.0)}


#: The two daily bundles, both 2025-06-01..2026-06-23. They differ ONLY in their surface fields:
#: `daily_sat/v001` carries genuine satellite observations (the PS deliverable), `daily` carries
#: GLORYS reanalysis. Their subsurface `temp`/`salinity` are byte-identical GLORYS target data
#: (checked 2026-09-03), which is why the upwelling panel reads the same either way and says so.
BUNDLES = {"satellite": os.path.join(config.DATA_PROCESSED, "daily_sat", "v001"),
           "glorys": os.path.join(config.DATA_PROCESSED, "daily")}

#: What each source's SURFACE currents and SST actually are, for `eddy.summarise(source=...)`.
SOURCE_LABEL = {
    "satellite": "satellite observations (COPERNICUS-GLOBCURRENT total surface currents, "
                 "OSTIA SST) -- not reanalysis",
    "glorys": "GLORYS12V1 reanalysis surface currents and SST -- not observations",
}


@st.cache_data(show_spinner="Loading fields …")
def load():
    """Phase-1 GLORYS monthly, 2019-2022. Used ONLY by the Great Whirl seasonal panel."""
    g = np.load(GRIDS, allow_pickle=True)
    return (np.asarray(g["u"], "float64"), np.asarray(g["v"], "float64"),
            np.asarray(g["sst"], "float64"), np.asarray(g["temp"], "float64"),
            np.asarray(g["times"]).astype("datetime64[D]"),
            np.asarray(g["land_mask"], bool))


@st.cache_resource(show_spinner="Loading the daily bundle …")
def _bundle(source: str):
    from phase2.tscast_nio import dataset as D
    return D.load_daily(BUNDLES[source])


def daily_dates(source: str) -> list[str]:
    return [str(t) for t in np.asarray(_bundle(source)["times"]).astype("datetime64[D]")]


@st.cache_data(show_spinner="Detecting eddies …")
def detect_daily(date_str: str, source: str):
    """Eddies, fronts and vorticity from ONE day of the chosen bundle's surface fields.

    Surface only -- no model reconstruction is involved, so "satellite" here means the detectors
    are reading real observations rather than a reanalysis of them.
    """
    b = _bundle(source)
    ch = [str(c) for c in b["channels"]]
    times = np.asarray(b["times"]).astype("datetime64[D]")
    k = int(np.argmin(np.abs(times - np.datetime64(date_str))))
    land = np.asarray(b["land_mask"], bool)

    def surf(name):
        return np.where(land, np.nan,
                        np.asarray(b["surface"][k, :, :, ch.index(name)], "float64"))

    uu, vv, ss = surf("u"), surf("v"), surf("sst")
    eddies = eddy.detect_eddies(uu, vv)
    summary = eddy.summarise(eddies, source=SOURCE_LABEL[source])
    fr = fronts.detect_fronts(ss)
    ow = eddy.okubo_weiss(uu, vv)
    return eddies, summary, fr, ow["vorticity"], str(times[k]), k


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
    if not os.path.exists(GRIDS):
        st.error(f"Needs {GRIDS} — gitignored, ships in the data bundle.")
        st.stop()
        return

    with st.sidebar:
        st.header("Snapshot")
        source = st.radio(
            "Surface source", ["satellite", "glorys"], index=0,
            help="Both are daily 2025-06-01..2026-06-23 and differ only in their SURFACE fields. "
                 "satellite = real observations (GLOBCURRENT currents, OSTIA SST) -- the PS "
                 "deliverable. glorys = the reanalysis of the same days. No model reconstruction "
                 "is involved either way: eddies and fronts are surface diagnostics.")
        dates = daily_dates(source)
        date_str = st.selectbox("Date", options=dates, index=len(dates) - 6)
        show = st.radio("Field", ["Eddies", "Thermal fronts", "Upwelling"])

    st.title("Ocean events")
    st.caption(f"Eddies, thermal fronts and an upwelling signature — **detected in one snapshot "
               f"at a time**, from **{source}** surface fields. The record is daily, so tracking "
               f"is no longer ruled out by cadence — but nothing here joins one date to the next, "
               f"because no tracking has been built or validated.")

    eddies, summary, fr, vort, actual_date, idx = detect_daily(date_str, source)

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
        st.caption("Measured on **Phase-1 GLORYS monthly, 2019–2022** — a different "
                   "bundle from the daily one above, and unaffected by the source "
                   "toggle. A four-year seasonal climatology cannot be recomputed on a "
                   "388-day record.")
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
        stamp = actual_date.replace("-", "")[:6]
        b = _bundle(source)
        ch = [str(c) for c in b["channels"]]
        land = np.asarray(b["land_mask"], bool)
        sst_k = np.where(land, np.nan,
                         np.asarray(b["surface"][idx, :, :, ch.index("sst")], "float64"))
        temp_k = np.asarray(b["temp"][idx], "float64")
        sal = np.asarray(b["salinity"][idx], "float64")

        st.info(
            "**The subsurface half of this panel is GLORYS either way.** The shoaled-thermocline "
            "term needs temperature AND salinity at depth; `temp`/`salinity` are byte-identical "
            "between the two bundles because both carry the same GLORYS target. Only the SST "
            f"term above reads **{source}**. Nothing here is a satellite-only product."
        )

        try:
            w = upwelling.load_wind_stress(stamp)
            pump = upwelling.ekman_pumping(w["eastward_stress"], w["northward_stress"])
            wind_ok = True
        except upwelling.MissingWindError:
            st.warning(
                f"**No Ekman attribution for {stamp}.** The wind-stress product runs 2019-01 to "
                "2022-12 only, so it cannot reach this bundle's 2025-2026 window. The signature "
                "below is therefore cold-surface AND shoaled-thermocline, with **no wind term** "
                "— a signature, not an attribution. `wind_attributed` records this as data."
            )
            pump, wind_ok = None, False

        try:
            ref = upwelling.climatological_sst_reference(int(actual_date[5:7]))
        except Exception:
            ref = None

        out = upwelling.upwelling_signature(sst_k, temp_k, sal, ekman=pump, sst_reference=ref)
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
            f"information on its own."
            + (" Ekman pumping from a **monthly-mean** stress is a lower bound on episodic "
               "upwelling: the curl of an average is not the average of the curl."
               if wind_ok else
               " No Ekman term was available for this date, so the monthly-mean-stress caveat "
               "does not apply here — there is simply no wind forcing in this result.")
        )

    with st.expander("What this page does not show"):
        st.markdown(
            f"- **Eddy tracking, lifetime or propagation speed.** NOT built and NOT validated. "
            f"The old reason — 48 monthly fields — no longer applies: this bundle is 388 "
            f"consecutive days, which does resolve a feature moving a few km/day. The library "
            f"still refuses a time axis, so nothing here attempts it. This is now a gap, not an "
            f"impossibility.\n"
            f"- **Marine heatwaves (F7).** Defined on ≥5 consecutive *days*. Previously called "
            f"'permanently closed at monthly cadence' — that is no longer true either, for the "
            f"same reason. Still unbuilt.\n"
            f"- **Sub-mesoscale features.** 0.25° ≈ 25 km cells; anything under ~100 km is "
            f"unresolved. This one is a real limit and does not move.\n"
            f"- **The eddies and fronts above are from `{source}` surface fields** — "
            f"{SOURCE_LABEL[source]}. The upwelling panel's subsurface half is GLORYS regardless."
        )


if __name__ == "__main__":
    main()
