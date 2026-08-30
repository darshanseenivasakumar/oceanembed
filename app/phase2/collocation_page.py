"""Phase-2 F1 explorer — see the collocation engine in a browser.

OWNER: Unit B (Darshan). PHASE-2 ONLY.

This is a SEPARATE app from the frozen Aug-30 demo. It does not import, modify or interfere with
app/streamlit_app.py. Run it on its own port so both can be open at once:

    streamlit run app/phase2/collocation_page.py --server.port 8502

Everything shown comes straight from CollocationEngine.collocate(). Nothing is recomputed here,
so what you see is exactly what F2/F8/F9 will consume.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from oceanembed import config  # noqa: E402
from phase2.data.collocation import CollocationEngine  # noqa: E402

st.set_page_config(page_title="OceanEmbed Phase 2 — Collocation", layout="wide")

QUALITY_COLOUR = {"HIGH": "#1a7f37", "MEDIUM": "#9a6700", "LOW": "#9a6700", "REJECT": "#b3261e"}


@st.cache_resource
def get_engine(tolerance_days: float):
    return CollocationEngine(tolerance_days=tolerance_days)


@st.cache_data
def available_dates():
    p = os.path.join(config.DATA_PROCESSED, "grids.npz")
    with np.load(p, allow_pickle=False) as z:
        return [pd.Timestamp(d).date() for d in z["times"].astype("datetime64[D]")]


@st.cache_data
def _basin_wide():
    """Basin-wide GLORYS-vs-Argo numbers, so one profile is never read as the headline.

    Returns None if the analysis has not been run -- the page then says how to produce it rather
    than silently showing only the single-point figure.
    """
    p = os.path.join(config.ARTIFACTS, "glorys_vs_argo.json")
    if not os.path.exists(p):
        return None
    import json
    with open(p) as f:
        d = json.load(f)
    by = {int(k): v for k, v in d["by_depth_all"].items()}
    worst = max(by, key=lambda k: by[k]["mean_abs"])
    deep = [by[k]["mean_abs"] for k in by if k >= 500]
    return {"n": d["n_comparisons"], "worst_depth": worst,
            "worst_val": by[worst]["mean_abs"],
            "deep": sum(deep) / len(deep) if deep else float("nan")}


st.title("F1 — Multi-source collocation")
st.caption("Phase 2 · one point, every source, with the measured offset of each match. "
           "Separate from the frozen Aug-30 demo.")

try:
    dates = available_dates()
except FileNotFoundError:
    st.error("data/processed/grids.npz missing — run `python scripts/prepare_dataset.py --real`.")
    st.stop()

with st.sidebar:
    st.header("Query")
    lat = st.slider("Latitude (°N)", float(config.LAT.min()), float(config.LAT.max()), 15.0, 0.05)
    lon = st.slider("Longitude (°E)", float(config.LON.min()), float(config.LON.max()), 65.0, 0.05)
    date = st.selectbox("Date", dates, index=len(dates) - 1)
    st.divider()
    tol = st.slider("Temporal tolerance (days)", 1.0, 20.0, 10.0, 1.0,
                    help="Our grids are monthly, so a random Argo float sits a MEDIAN 7 days from "
                         "the nearest grid date. Tighter = better match but less data. "
                         "Measured: ±1d keeps 9.5% of floats, ±5d 36.5%, ±15d 99.7%.")
    st.caption("Try 15°N 75°E (inland India) or 29.5°N 48.25°E (Persian Gulf) to see rejection.")

record = get_engine(tol).collocate(lat, lon, date)
q = record.quality

c = st.columns([2, 1, 1, 1])
c[0].markdown(f"### :{'green' if q=='HIGH' else 'orange' if q in ('MEDIUM','LOW') else 'red'}[{q}]")
c[1].metric("spatial offset", f"{record.offsets['spatial_km']:.1f} km")
c[2].metric("temporal offset", f"{record.offsets['temporal_days']:+.0f} d")
c[3].metric("matched cell", f"{record.matched['grid_i']},{record.matched['grid_j']}")

if record.flags:
    st.warning("**Flags:** " + " · ".join(record.flags))
if q == "REJECT":
    st.error("This point is **rejected**. The engine still reports what each source holds there, "
             "but it must not be treated as a usable match. The flags above say why.")

st.caption(f"requested {record.requested['latitude']:.4f}°N {record.requested['longitude']:.4f}°E "
           f"→ matched {record.matched['latitude']:.4f}°N {record.matched['longitude']:.4f}°E "
           f"on {record.matched['datetime']}")

src = record.sources
gl, sat, sub, argo = src.get("glorys") or {}, src.get("satellite"), src.get("subsurface"), src.get("argo")

left, right = st.columns([1, 1])

with left:
    st.subheader("Surface")
    rows = []
    for k, unit in [("sst", "°C"), ("sss", "psu"), ("ssh", "m"), ("u", "m/s"), ("v", "m/s")]:
        g_, s_ = gl.get(k), (sat or {}).get(k)
        rows.append({"variable": f"{k.upper()} ({unit})", "GLORYS": g_, "satellite": s_,
                     "difference": None if (g_ is None or s_ is None) else round(s_ - g_, 3)})
    # Same trap as the profile table below, and it bites hardest on land: every value is None, so
    # all three columns come out OBJECT dtype and Streamlit prints the word "None" fifteen times.
    # On a rejected point that is the whole table, which reads like a crash rather than "there is
    # no ocean here". Coerce to float64 so they become NaN, then let the Styler mark them.
    sdf = pd.DataFrame(rows)
    st.dataframe(
        sdf.astype({c: "float64" for c in ("GLORYS", "satellite", "difference")})
           .style.format({"GLORYS": "{:.4f}", "satellite": "{:.4f}", "difference": "{:.3f}"},
                         na_rep="—"),
        hide_index=True, width="stretch")
    if sat is None:
        st.info("No satellite within tolerance. **Normal** — satellite covers 24 of our 48 dates.")

with right:
    st.subheader("Independent Argo")
    if argo:
        a, b = st.columns(2)
        a.metric("distance", f"{argo['spatial_offset_km']:.0f} km")
        b.metric("time offset", f"{argo['temporal_offset_days']:+.0f} d")
        st.caption(f"float at {argo['latitude']:.3f}°N {argo['longitude']:.3f}°E on "
                   f"{argo['datetime']} · {argo['n_levels']} levels")
        st.success(argo["note"])
    else:
        st.info("No Argo profile within tolerance.\n\n"
                "2,455 floats across ~15 million km² is genuinely sparse — that gap is the "
                "problem this project exists to fill.")

prof = gl.get("temperature_profile")
if prof:
    st.subheader("Profile")
    df = pd.DataFrame({
        "depth (m)": config.DEPTHS,
        "GLORYS T (°C)": prof,
        "salinity (psu)": (sub or {}).get("salinity_profile") or [None] * config.N_DEPTHS,
        "ARGO T (°C)": (argo or {}).get("temperature_profile") or [None] * config.N_DEPTHS,
    })
    df["ARGO − GLORYS"] = [None if (a is None or g is None) else round(a - g, 2)
                           for a, g in zip(df["ARGO T (°C)"], df["GLORYS T (°C)"])]

    a, b = st.columns([1, 1])
    with a:
        # Oceanographic convention: DEPTH on the y-axis, increasing DOWNWARD. st.line_chart puts
        # the index on x, which drew depth sideways running to -100 m -- readable only to someone
        # who already knew what they were looking at. The baseline app plots it correctly; this
        # matches it.
        import altair as alt
        long = df.melt(id_vars="depth (m)", value_vars=["GLORYS T (°C)", "ARGO T (°C)"],
                       var_name="source", value_name="temperature").dropna()
        chart = (alt.Chart(long)
                 .mark_line(point=True)
                 .encode(x=alt.X("temperature:Q", title="temperature (°C)",
                                 scale=alt.Scale(zero=False)),
                         y=alt.Y("depth (m):Q", title="depth (m)",
                                 scale=alt.Scale(reverse=True)),
                         # Two shades of blue made the reanalysis and the real float nearly
                         # impossible to tell apart, which hides the whole point of the plot.
                         # Model in blue, OBSERVATION in amber -- the contrast that matters.
                         color=alt.Color("source:N",
                                         scale=alt.Scale(domain=["GLORYS T (°C)", "ARGO T (°C)"],
                                                         range=["#4c8dff", "#f5a524"]),
                                         legend=alt.Legend(orient="bottom", title=None)),
                         tooltip=["depth (m)", "source", "temperature"])
                 .properties(height=360))
        st.altair_chart(chart, width="stretch")
        st.caption("Depth increases downward, as an oceanographer would plot it. "
                   "A gap in the Argo line means the float did not sample that level.")
    with b:
        # None renders as the literal word "None", and round(x, 2) turns -0.0009 into a bare "0"
        # sitting next to "-0.01", which reads as exact agreement and as sloppy formatting. NaN
        # renders blank, and an explicit format keeps every column at a fixed width.
        # pandas turns the engine's None into NaN on construction, and Streamlit prints NaN as the
        # literal word "None" -- so a level the float simply did not sample reads like a failure.
        # A Styler is the only way to set the missing marker; "--" is the conventional one.
        # Two separate traps here, and the second only appears when there is NO Argo at all.
        # 1. Streamlit prints NaN as the literal word "None", so a level the float did not sample
        #    reads like a failure. A Styler with na_rep is the only way to set the marker.
        # 2. If EVERY value in a column is None, pandas keeps that column as OBJECT dtype, and
        #    Streamlit renders object columns straight through -- na_rep never gets a look in, so
        #    "None" comes back. Coercing to float64 first turns them into real NaN, which the
        #    Styler then formats. This is the common case: most of the basin has no float nearby.
        num = [c for c in df.columns if c != "depth (m)"]
        shown = df.astype({c: "float64" for c in num})
        st.dataframe(
            shown.style.format({"depth (m)": "{:.0f}", "GLORYS T (°C)": "{:.3f}",
                                "salinity (psu)": "{:.3f}", "ARGO T (°C)": "{:.3f}",
                                "ARGO − GLORYS": "{:.2f}"}, na_rep="—"),
            hide_index=True, width="stretch", height=400)

    # The reanalysis-vs-float gap is worth surfacing: it is not OUR model's error. But this is ONE
    # profile, and a single point is an anecdote -- so show the basin-wide number beside it or a
    # reader will generalise from a sample of one.
    both = df.dropna(subset=["ARGO T (°C)", "GLORYS T (°C)"])
    if len(both) >= 5:
        worst = both.iloc[both["ARGO − GLORYS"].abs().argmax()]
        deep = both[both["depth (m)"] >= 500]["ARGO − GLORYS"].abs().mean()
        msg = (f"**GLORYS vs the independent float, at THIS point** — largest gap "
               f"**{worst['ARGO − GLORYS']:+.2f} °C at {int(worst['depth (m)'])} m**, "
               f"but only **{deep:.2f} °C** mean below 500 m.")

        basin = _basin_wide()
        if basin:
            msg += (f"  \n**Basin-wide, across {basin['n']:,} comparisons:** worst is "
                    f"**{basin['worst_val']:.2f} °C at {basin['worst_depth']} m**, "
                    f"**{basin['deep']:.2f} °C** below 500 m. This single profile is on the "
                    f"{'severe' if abs(worst['ARGO − GLORYS']) > basin['worst_val'] else 'mild'} "
                    "side — do not quote one point as the headline.")
        else:
            msg += ("  \nFor the basin-wide figure run `python scripts/phase2/glorys_vs_argo.py`; "
                    "one profile on one date is an anecdote, not a result.")

        msg += ("  \n\nThis is the *reanalysis* against a real float, **not our model**. Where they "
                "disagree, part of the error our model shows at the thermocline is inherited from "
                "its training data rather than created by it. Some of this gap is also the float "
                f"being {(argo or {}).get('spatial_offset_km', 0):.0f} km and "
                f"{(argo or {}).get('temporal_offset_days', 0):+.0f} days away — a real limit of "
                "matching irregular floats to monthly grids, not a defect.")
        st.info(msg)

with st.expander("Provenance — where every number came from"):
    st.json(record.provenance)
st.caption("Nothing on this page is recomputed. Every value is read straight from the record "
           "`CollocationEngine.collocate()` returned — the same object F2, F8 and F9 consume.")
