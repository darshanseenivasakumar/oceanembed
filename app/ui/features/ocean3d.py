"""The basin in three dimensions, with the 26 degC layer floating inside it.

OWNER: Unit A (Arjhun). NOT a page.

THE FALLBACK LADDER IS MANDATORY, NOT A NICETY

    three.js WebGL        the good case: 15 alpha-blended depth planes, the 26 degC layer as a
      |                   real mesh, land, Argo floats, orbit and click-to-profile
      |  no WebGL / three.js missing / the scene raised
    Plotly 3-D volume     already built and tested in app/phase2/cube_page.py, reused as-is
      |  plotly not installed / too many points
    Altair 2-D slice      ships with Streamlit, renders wherever the app runs

Every rung says in one line WHY it is the one being shown. Never a silent downgrade, never a
crash. The rung can also be FORCED from the control row, because a ladder nobody has climbed is
a ladder nobody knows is broken.

THE 26 degC LAYER IS A HEIGHTMAP, NOT AN ISOSURFACE
Exactly one depth per lat/lon, which is what heat_content_field already returns as `d26`. A
marching-cubes mesh through 15 unevenly spaced levels would interpolate far more than it measures
and would invent geometry wherever a column crosses 26 degC twice -- and scikit-image, the tool
the build spec names for that job, is not installed on this machine.

THE PICTURE IS HONEST ABOUT THREE THINGS
  * gaps are the SEA FLOOR, not missing data -- the count is on screen
  * lat/lon are subsampled for the Plotly rung; the science is unchanged, the picture is coarser
  * the vertical axis is EXAGGERATED and the TRUE factor is printed, because an unlabelled
    exaggeration is a lie about proportion
"""
from __future__ import annotations

import os

import numpy as np
import streamlit as st

from app.ui import data as D
from app.ui import theme, ux
from app.ui.three_d import hero as H

FIELDS = {"temperature": "Temperature", "uncertainty": "Uncertainty"}

#: Plotly's z aspect is 0.35 * stretch against x = 1, and the basin is 6328 km wide over 1000 m
#: of depth. So a TRUE exaggeration of N is stretch = N / 2215, and one slider can mean the same
#: thing on either rung instead of two controls that look alike and are not.
PLOTLY_STRETCH_PER_X = 0.35 * 6328.0


def _plotly():
    """Plotly if it is importable, else None.

    OCEANEMBED_NO_PLOTLY=1 forces None. That hook exists so rung 3 can actually be EXERCISED on a
    machine that has plotly installed -- otherwise the only way to test the bottom of the ladder
    is to uninstall a dependency, which nobody does, which is how the bottom rung quietly rots.
    """
    if os.environ.get("OCEANEMBED_NO_PLOTLY"):
        return None
    try:
        import plotly.graph_objects as go
        return go
    except Exception:
        return None


def render(ctx) -> None:
    c = st.columns([1.5, 1.9, 1.3, 1.3, 1.6], vertical_alignment="bottom")
    with c[0]:
        with ux.control("field", ratio=(5, 2)):
            what = st.selectbox("Show", list(FIELDS), format_func=lambda k: FIELDS[k],
                                key="o3_what")
    with c[1]:
        with ux.control("exaggeration", ratio=(5, 2)):
            exag = st.slider("Vertical exaggeration", 200, 3000, 1200, 100, key="o3_zx")
    with c[2]:
        with ux.control("floats", ratio=(5, 2)):
            floats = st.toggle("Argo floats", value=True, key="o3_floats")
    with c[3]:
        rotate = st.toggle("Auto-rotate", value=True, key="o3_rot")
    with c[4]:
        with ux.control("renderer", ratio=(5, 2)):
            forced = st.selectbox("Renderer", ["auto", "Plotly", "2-D"], key="o3_rung")

    clicked, rung, reason = None, None, None
    if forced == "auto":
        if H.vendored_bytes() == 0:
            reason = ("the vendored three.js copy is missing from "
                      "app/ui/three_d/frontend/vendor/")
        else:
            try:
                with st.spinner("Preparing the volume for WebGL ..."):
                    payload = H.build_payload(ctx.date, ctx.version, what, ctx.device, floats)
                clicked = H.render(payload, key="hero3d", height=620, exaggeration=exag,
                                   field=what, show_floats=floats, autorotate=rotate)
                rung = "webgl"
            except Exception as e:
                reason = f"the WebGL scene raised {type(e).__name__}: {e}"
    else:
        reason = "you selected it (Renderer)"

    if rung is None:
        _fallback(ctx, what, exag, forced, reason)
    else:
        st.caption("Drag to orbit, wheel to zoom, **click the sea** for the column beneath it. "
                   "It resumes turning after 8 s of stillness.")
        _clicked_profile(ctx, clicked)

    ux.explain("seafloor", label="Why parts of the volume are empty")

    # ---- 02 - the mathematics ------------------------------------------------------
    ux.maths(
        r"T(x,y,z),\ \sigma(x,y,z) \;=\; f_\theta\big(\mathrm{SST},\ \mathrm{SSS},\ "
        r"\mathrm{SSH},\ u,\ v,\ w_u,\ w_v\big)"
        r"\qquad E \;=\; \frac{\Delta z_{\text{drawn}} / \Delta z}"
        r"{\Delta x_{\text{drawn}} / \Delta x}",
        [("f_θ", "the trained network: a 3-D residual CNN encoder into a 128-dim latent, then a "
                 "decoder to 15 depths", "", "src/phase2/tscast_nio/models/tscast.py"),
         ("SST, SSS, SSH", "sea surface temperature, salinity and height", "°C, PSU, m",
          "satellite observations"),
         ("u, v, wᵤ, wᵥ", "surface currents and wind stress", "m s⁻¹", "satellite observations"),
         ("T", "reconstructed temperature at 15 depths", "°C", "model output"),
         ("σ", "the model's own uncertainty at each depth", "°C", "model output"),
         ("E", f"vertical exaggeration, currently ×{exag:,}", "",
          "1000 m of depth across 6,328 km of basin"),
         ("Δz drawn", "the depth extent actually rendered on screen", "scene units",
          "set by the slider")],
        f"Drawn to true scale this ocean is 1 km deep across 6,328 km, a film of water you could "
        f"not see. E = {exag:,} is what makes structure visible, and it is printed rather than "
        f"assumed.")

    # ---- 03 - the inference --------------------------------------------------------
    ux.inference(
        what=("A single day's ocean, reconstructed from the surface alone. Warm water sits in a "
              "shallow lens near the top; the cyan sheet is the depth at which it cools through "
              "26 °C. Green points are real Argo floats near this date."),
        conclude=("Where the cyan sheet dips deep, a cyclone crossing has a large reservoir of "
                  "warm water to draw on and can keep intensifying. Where it rides close to the "
                  "surface, a storm churns up cold water and weakens itself."),
        limits=[
            (f"The vertical axis is stretched ×{exag:,}. The basin is far flatter than it looks.",
             "printed in the scene's own overlay"),
            ("Values are quantised to one byte for transport, about 0.1 °C, a tenth of the "
             "model's own error. Read the colour as a field, not as a measurement.",
             "app/ui/three_d/hero.py _quantise"),
            ("Argo points show where independent observations exist on this date. They are not "
             "compared against the model here; that is the Validation feature.",
             "artifacts/argo_daily_period.parquet"),
            ("Uncertainty shading is the raw model spread and is NOT calibrated.",
             "artifacts/uncertainty_calibration.json"),
            ("The grid stops at 1000 m. Nothing below that depth is modelled at all.",
             "oceanembed.config.DEPTHS"),
        ])


def _clicked_profile(ctx, clicked) -> None:
    """The column under the last click in the 3-D scene. This is what makes it an instrument."""
    if not isinstance(clicked, dict) or "lat" not in clicked:
        return
    import altair as alt
    import pandas as pd

    lat, lon = float(clicked["lat"]), float(clicked["lon"])
    f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)
    la = np.asarray(D.base.LAT, dtype="float64")
    lo = np.asarray(D.base.LON, dtype="float64")
    i, j = int(np.argmin(np.abs(la - lat))), int(np.argmin(np.abs(lo - lon)))

    t = np.asarray(f["temperature"][i, j, :], dtype="float64")
    s = np.asarray(f["sigma"][i, j, :], dtype="float64")
    left, right = st.columns([1.4, 3.0], gap="large")
    with left:
        st.markdown(f"**{lat:.2f}°N  {lon:.2f}°E**")
        if not np.isfinite(t).any():
            st.warning("No water column here.", icon=":material/block:")
            return
        deepest = float(np.max(np.asarray(D.DEPTHS)[np.isfinite(t)]))
        ux.tiles([("SURFACE", f"{t[0]:.2f}", "°C"), ("WATER TO", f"{deepest:.0f}", "m")])
    with right:
        df = pd.DataFrame({"depth": list(D.DEPTHS), "t": t, "lo": t - s, "hi": t + s}).dropna()
        if df.empty:
            return
        pad = max(0.4, float(df.hi.max() - df.lo.min()) * 0.08)
        dom = [float(df.lo.min()) - pad, float(df.hi.max()) + pad]
        base = alt.Chart(df)
        band = base.mark_area(opacity=0.22, color=theme.CYAN).encode(
            x=alt.X("lo:Q", title="temperature (°C)",
                    scale=alt.Scale(domain=dom, zero=False, nice=False)),
            x2="hi:Q", y=alt.Y("depth:Q", title="depth (m)", scale=alt.Scale(reverse=True)))
        line = base.mark_line(point=True, color=theme.CYAN, strokeWidth=2).encode(
            x=alt.X("t:Q", scale=alt.Scale(domain=dom, zero=False, nice=False)),
            y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
            tooltip=[alt.Tooltip("depth:Q", format=".0f", title="depth (m)"),
                     alt.Tooltip("t:Q", format=".2f", title="°C")])
        st.altair_chart((band + line).properties(height=250), use_container_width=True)


def _fallback(ctx, what: str, exag: float, forced: str, reason: str | None) -> None:
    """Rungs 2 and 3, each saying why it is the one being shown."""
    from phase2.cube import OceanCube, volume
    go = _plotly()

    with st.spinner("Reconstructing the volume ..."):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)
    cube = OceanCube(date=f["date"], temperature=f["temperature"],
                     valid_mask=f["valid_mask"], land_mask=f["land_mask"],
                     uncertainty=f["sigma"], provenance=f["provenance"])
    vol = volume.to_volume_arrays(cube, stride=volume.DEFAULT_STRIDE, what=what)

    if forced == "2-D" or go is None or vol["over_budget"]:
        why = ("you selected it" if forced == "2-D"
               else "plotly is not installed on this machine" if go is None
               else f"{vol['n_points']:,} points is beyond the {volume.POINT_BUDGET:,} "
                    f"the browser will composite")
        st.warning(f"**2-D slice, rung 3 of 3.** {why}.", icon=":material/layers:")
        _fallback_2d(cube, what)
        return

    st.warning(f"**Plotly volume, rung 2 of 3.** {reason or 'the WebGL rung is unavailable'}.",
               icon=":material/layers:")
    zx = max(0.1, exag / PLOTLY_STRETCH_PER_X)
    scale = theme.SEQ_UNCERTAINTY if what == "uncertainty" else theme.SEQ_TEMPERATURE
    lo, hi = vol["value_range"]
    # .tolist() is the FIX, not a style choice: plotly >= 6 serialises numpy as a base64 blob the
    # bundled plotly.js does not decode, and the trace arrives with EMPTY coordinates -- an empty
    # box with a correct-looking colourbar. Plotly here is 7.0.
    trace = go.Volume(x=vol["x"].tolist(), y=vol["y"].tolist(), z=vol["z"].tolist(),
                      value=vol["value"].tolist(), colorscale=scale,
                      isomin=lo, isomax=hi, opacity=0.13, surface_count=18,
                      colorbar=dict(title=dict(text=vol["units"], side="right"),
                                    outlinewidth=0, len=0.72))
    fig = go.Figure(data=[trace])
    fig.update_layout(**theme.plotly_layout(520),
                      scene=theme.scene_axes("longitude (°E)", "latitude (°N)",
                                             "depth (m, negative = down)",
                                             volume.aspect_ratio(zx)))
    st.plotly_chart(fig, use_container_width=True, theme=None)
    ux.tiles([("WATER CELLS DRAWN", f"{vol['n_with_water']:,}"),
              ("SEA FLOOR", f"{vol['n_below_seafloor']:,}", "", "no water, not missing data"),
              ("GRID", "x".join(str(s) for s in vol["shape"])),
              ("VERTICAL EXAGGERATION", f"{exag:,.0f}", "×", "a viewing choice")])


def _fallback_2d(cube, what: str) -> None:
    """The view that always works: one horizontal level, altair, no extra dependency."""
    import altair as alt
    import pandas as pd

    sl = cube.depth_slice(100.0, what=what)
    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")
    LAT2, LON2 = np.meshgrid(lat, lon, indexing="ij")
    df = pd.DataFrame({"lat": LAT2.ravel(), "lon": LON2.ravel(),
                       "v": np.asarray(sl["values"]).ravel()}).dropna(subset=["v"])
    st.altair_chart(
        alt.Chart(df).mark_rect().encode(
            x=alt.X("lon:O", title="longitude (°E)",
                    axis=alt.Axis(values=list(range(45, 106, 10)))),
            y=alt.Y("lat:O", title="latitude (°N)", sort="descending",
                    axis=alt.Axis(values=list(range(5, 31, 5)))),
            color=alt.Color("v:Q", title=sl["what"], scale=alt.Scale(scheme="turbo")),
        ).properties(height=460), use_container_width=True)
    st.caption(f"{sl['what']} at {sl['depth_m']:.0f} m. Altair ships with Streamlit, so this "
               f"renders wherever the app runs.")
