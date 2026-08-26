"""F2b -- the OceanCube in three dimensions, with a 2-D view it can always fall back to.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. A NEW file under app/phase2/.
The frozen demo (app/streamlit_app.py, app/panels/) is READ-ONLY and is not touched or imported.

    streamlit run app/phase2/cube_page.py --server.port 8504

GRACEFUL DEGRADATION IS THE REQUIREMENT, NOT A NICETY
A 3-D volume needs plotly, and `app/panels/_viz.py` already records why that is a risk:

    plotly ... [is] NOT guaranteed to be installed on a teammate's or a demo machine, and a
    panel that ImportErrors on demo day is worse than a plainer chart.

That is not hypothetical -- the F8 page ImportError'd on plotly earlier today on this very
laptop. So this page NEVER assumes the renderer. If plotly is missing, or the volume build
raises, or the point count is beyond what a browser will chew, it renders a 2-D depth slice in
altair (which ships with Streamlit) and says why. The 3-D view is the good case, not the only
case.

WHAT THE PICTURE HONESTLY SHOWS
  * gaps are the SEA FLOOR, not missing data -- 24% of ocean cells never reach 1000 m
  * lat/lon are subsampled for the renderer; the science is unchanged, the picture is coarser
  * the vertical axis is EXAGGERATED by default, and the caption says by how much. 1000 m over
    60 degrees of longitude is a film of water; drawn to scale you would see nothing.
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
from phase2.cube import OceanCube, volume  # noqa: E402

st.set_page_config(page_title="OceanEmbed — OceanCube 3-D", layout="wide")

FIELDS = {"temperature": "Temperature (°C)",
          "uncertainty": "Model spread (°C, 1σ — NOT calibrated)",
          "anomaly": "Anomaly vs climatology (°C)"}


@st.cache_data(show_spinner="Reconstructing the volume …")
def build_cube(date_str: str, source: str, with_uncertainty: bool):
    """Cached by value only -- no underscore-prefixed argument, which would be silently
    excluded from the cache key and pin the first result forever."""
    return OceanCube.reconstruct(date_str, source=source, with_uncertainty=with_uncertainty)


def plotly_available() -> bool:
    try:
        import plotly.graph_objects as go  # noqa: F401
        return True
    except Exception:
        return False


def _fig_3d(vol: dict, mode: str, z_exag: float, colorscale: str):
    import plotly.graph_objects as go

    aspect = volume.aspect_ratio(z_exag)

    # .tolist() IS THE FIX, not a style choice. plotly >= 6 serialises a numpy array as
    # {"dtype": "f8", "bdata": "<base64>"}, and the plotly.js bundled by Streamlit does not
    # decode it -- the trace arrives in the browser with EMPTY x/y/z/value while the scalar
    # fields (isomin, isomax) survive. The result is an empty box with axes defaulting to
    # -1..1 and a correct-looking colourbar, which is the worst kind of failure: it renders,
    # so it looks like the data is wrong rather than the transport. Plain lists serialise as
    # plain JSON. Covered by test_plotly_receives_real_arrays_not_base64_blobs.
    common = dict(x=vol["x"].tolist(), y=vol["y"].tolist(), z=vol["z"].tolist(),
                  value=vol["value"].tolist(),
                  colorscale=colorscale,
                  colorbar=dict(title=vol["units"] or vol["what"]))
    lo, hi = vol["value_range"]

    if mode == "isosurface":
        levels = volume.isosurface_levels(vol, n=4)
        trace = go.Isosurface(**common, isomin=levels[0] if levels else lo,
                              isomax=levels[-1] if levels else hi,
                              surface_count=len(levels) or 3, opacity=0.45,
                              caps=dict(x_show=False, y_show=False, z_show=False))
    else:
        trace = go.Volume(**common, isomin=lo, isomax=hi,
                          opacity=0.12,          # small, so you can see through the stack
                          surface_count=18)

    fig = go.Figure(data=trace)
    fig.update_layout(
        height=650, margin=dict(l=0, r=0, t=10, b=0),
        scene=dict(
            xaxis_title="longitude (°E)",
            yaxis_title="latitude (°N)",
            zaxis_title="depth (m, negative = down)",
            aspectmode="manual",
            aspectratio=dict(x=aspect["x"], y=aspect["y"], z=aspect["z"]),
        ),
    )
    return fig


def _fig_2d_fallback(cube, depth_m: float, what: str):
    """The view that always works: one horizontal level, altair, no extra dependency."""
    sl = cube.depth_slice(depth_m, what=what)
    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "value": np.asarray(sl["values"]).ravel()}).dropna(subset=["value"])
    chart = alt.Chart(df).mark_rect().encode(
        x=alt.X("lon:O", title="longitude (°E)", axis=alt.Axis(values=list(range(45, 106, 10)))),
        y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                axis=alt.Axis(values=list(range(5, 31, 5)))),
        color=alt.Color("value:Q", title=sl["what"], scale=alt.Scale(scheme="turbo")),
        tooltip=["lat", "lon", alt.Tooltip("value:Q", format=".2f")],
    ).properties(height=520)
    return chart, sl


def main() -> None:
    st.title("OceanCube — 3-D")
    st.caption("One reconstructed volume: temperature over latitude, longitude and depth. "
               "Built on F2a, which enforces the sea floor — gaps below are **not missing data**.")

    with st.sidebar:
        st.header("Volume")
        dates = _dates()
        date_str = st.selectbox("Date", options=dates, index=max(0, len(dates) - 6))
        source = st.radio("Surface source", ["satellite", "glorys"], index=0,
                          help="satellite = the problem statement's deliverable; "
                               "glorys = the model's own training source")
        what = st.selectbox("Field", list(FIELDS), format_func=lambda k: FIELDS[k])
        mode = st.radio("Render", ["volume", "isosurface"], index=0,
                        help="volume = translucent stack; isosurface = shells at fixed values")
        stride = st.slider("Detail (lower = finer, slower)", 1, 6, volume.DEFAULT_STRIDE)
        z_exag = st.slider("Vertical exaggeration", 0.5, 6.0, 2.5, 0.5,
                           help="A VIEWING choice. 1000 m over 60° of longitude is a film of "
                                "water; drawn to scale you would see nothing.")
        st.divider()
        force_2d = st.checkbox("Force the 2-D fallback view", value=False)
        fb_depth = st.select_slider("Fallback depth (m)", options=list(config.DEPTHS), value=100)

    cube = build_cube(date_str, source, what == "uncertainty")

    # ---- the 3-D view, with every reason it might not work handled --------------------
    reason = None
    if force_2d:
        reason = "you asked for it (sidebar)"
    elif not plotly_available():
        reason = ("plotly is not installed. It is in requirements.txt but is not guaranteed on "
                  "any given machine — see app/panels/_viz.py")

    fig = None
    vol = None
    if reason is None:
        try:
            vol = volume.to_volume_arrays(cube, stride=stride, what=what)
            if vol["over_budget"]:
                reason = (f"{vol['n_points']:,} points is beyond the {volume.POINT_BUDGET:,} "
                          f"budget — raise 'Detail' to coarsen it")
            else:
                fig = _fig_3d(vol, mode, z_exag, "turbo" if what != "anomaly" else "RdBu_r")
        except Exception as e:                    # a render failure must not blank the page
            reason = f"the 3-D build raised {type(e).__name__}: {e}"

    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
        c = st.columns(4)
        c[0].metric("points rendered", f"{vol['n_with_water']:,}")
        c[1].metric("below the sea floor", f"{vol['n_below_seafloor']:,}")
        c[2].metric("grid", f"{vol['shape'][0]}×{vol['shape'][1]}×{vol['shape'][2]}")
        c[3].metric("vertical exaggeration", f"{z_exag:g}×")
        st.caption(
            f"Latitude and longitude are subsampled every **{stride}** cells for the renderer — "
            f"the science is unchanged, the picture is coarser. The empty region underneath is "
            f"the **sea floor**: {vol['n_below_seafloor']:,} of {vol['n_points']:,} sampled "
            f"points have no water. Depth is plotted **negative so it points down**, and the "
            f"vertical axis is stretched **{z_exag:g}×** — a viewing choice, not the true "
            f"proportion."
        )
    else:
        st.warning(f"**Showing the 2-D view instead** — {reason}.")
        chart, sl = _fig_2d_fallback(cube, fb_depth, what)
        st.altair_chart(chart, use_container_width=True)
        st.caption(
            f"{FIELDS[what]} at **{sl['depth_m']:.0f} m**. Coverage "
            f"{100 * sl['coverage_fraction']:.1f}% — the rest of the basin has no water at this "
            f"depth. This view needs only altair, which ships with Streamlit, so it renders "
            f"wherever the app runs."
        )

    if what == "uncertainty":
        st.info("**This is the raw MC-dropout spread and it is not calibrated.** Measured against "
                "independent Argo it is 1.6× to 3.5× too narrow, worst in the mixed layer "
                "(20–50 m) — see `docs/DECISIONS.md` D-016 and the Validation Lab. Read it as "
                "relative shading, never as an error bar.")

    with st.expander("Provenance — what produced this volume"):
        st.json(cube.provenance)


def _dates() -> list[str]:
    from oceanembed.inference import predict as P
    return [str(d) for d in P.available_dates()]


if __name__ == "__main__":
    main()
