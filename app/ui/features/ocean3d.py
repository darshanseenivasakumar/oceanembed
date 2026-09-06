"""The basin in three dimensions, with the 26 degC layer floating inside it.

OWNER: Unit A (Arjhun). NOT a page.

WHY PLOTLY AND NOT A HAND-WRITTEN WEBGL SCENE
The volume renderer, its sea-floor discipline and its aspect ratio are already built and unit
tested in src/phase2/cube/volume.py, and they run with no dependency this machine lacks. The
26 degC layer is likewise already a validated product -- heat_content_field returns `d26`.

That last point is worth stating plainly, because it is a physics argument and not a convenience
one: the 26 degC isotherm is a HEIGHTMAP. Exactly one depth per lat/lon. A general isosurface
mesh through 15 unevenly spaced levels would interpolate far more than it measures, and would
invent geometry wherever a column crosses 26 degC more than once. Drawing `d26` directly is both
cheaper and more defensible.

THE PICTURE IS HONEST ABOUT THREE THINGS
  * gaps are the SEA FLOOR, not missing data -- the count is on screen
  * lat/lon are subsampled for the renderer; the science is unchanged, the picture is coarser
  * the vertical axis is EXAGGERATED, and by how much is printed, because an unlabelled
    exaggeration is a lie about proportion
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from app.ui import data as D
from app.ui import theme, ux

FIELDS = {"temperature": "Temperature", "anomaly": "Anomaly", "uncertainty": "Uncertainty"}


def _plotly():
    try:
        import plotly.graph_objects as go
        return go
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _anomaly(date_str: str, version: str, temperature_shape: tuple) -> np.ndarray | None:
    """Temperature minus the MONTHLY climatology for that date's month.

    climatology.npy is (12, lat, lon, depth) -- one field per calendar month, which is what
    OceanCube's own units string ("degC vs monthly climatology") describes. Month index comes
    from the date, so this is a lookup, not a fit.
    """
    import os

    from oceanembed import config as base
    p = base.art("climatology.npy")
    if not os.path.exists(p):
        return None
    clim = np.load(p, mmap_mode="r")
    month = int(str(date_str)[5:7])
    c = np.asarray(clim[month - 1], dtype="float64")
    return c if c.shape == tuple(temperature_shape) else None


def _land_surface(go, land_mask, lat, lon):
    """Land as a flat dark sheet at z=0, so a judge can orient by coastline rather than ticks."""
    z = np.where(np.asarray(land_mask, dtype=bool), 0.0, np.nan)
    return go.Surface(
        x=lon.tolist(), y=lat.tolist(), z=z.tolist(),
        colorscale=[[0, "#1A2333"], [1, "#1A2333"]], showscale=False,
        hoverinfo="skip", name="land", opacity=1.0)


def _d26_surface(go, d26, lat, lon):
    """The 26 degC layer. The only glow in the product, and it has earned it."""
    z = -np.asarray(d26, dtype="float64")          # negative: depth points DOWN
    return go.Surface(
        x=lon.tolist(), y=lat.tolist(), z=z.tolist(),
        surfacecolor=np.zeros_like(z).tolist(),
        colorscale=[[0, theme.CYAN], [1, theme.CYAN]], showscale=False,
        opacity=0.55, name="26 °C layer",
        lighting=dict(ambient=0.85, diffuse=0.5, specular=0.2),
        hovertemplate="26 °C layer<br>%{y:.2f}°N %{x:.2f}°E<br>%{z:.0f} m<extra></extra>")


def render(ctx) -> None:
    go = _plotly()
    from phase2.cube import OceanCube, volume

    # ---- controls -----------------------------------------------------------------
    c = st.columns([1.6, 1.6, 1.6, 1.4], vertical_alignment="bottom")
    with c[0]:
        with ux.control("field", ratio=(5, 2)):
            what = st.selectbox("Show", list(FIELDS), format_func=lambda k: FIELDS[k],
                                key="o3_what")
    with c[1]:
        with ux.control("exaggeration", ratio=(5, 2)):
            zx = st.slider("Vertical stretch", 0.5, 8.0, 1.5, 0.5, key="o3_zx")
    with c[2]:
        with ux.control("detail", ratio=(5, 2)):
            stride = st.slider("Detail", 1, 6, volume.DEFAULT_STRIDE, key="o3_stride")
    with c[3]:
        with ux.control("d26surface", ratio=(5, 2)):
            show26 = st.toggle("26 °C layer", value=True, key="o3_d26")

    keep = D.FC.DEFAULT_KEEP
    with st.spinner("Reconstructing the volume …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, keep=keep, device=ctx.device)

    anomaly = None
    if what == "anomaly":
        anomaly = _anomaly(ctx.date, ctx.version, f["temperature"].shape)
        if anomaly is not None:
            anomaly = f["temperature"] - anomaly
        else:
            st.info("No monthly climatology on this machine, so anomaly cannot be drawn. "
                    "Showing temperature instead.")
            what = "temperature"

    cube = OceanCube(date=f["date"], temperature=f["temperature"],
                     valid_mask=f["valid_mask"], land_mask=f["land_mask"],
                     uncertainty=f["sigma"], anomaly=anomaly, provenance=f["provenance"])

    vol = volume.to_volume_arrays(cube, stride=stride, what=what)

    # ---- the picture --------------------------------------------------------------
    drew_3d = False
    if go is None:
        st.warning("**2-D view** — plotly is not installed on this machine.")
    elif vol["over_budget"]:
        st.warning(f"**2-D view** — {vol['n_points']:,} points is beyond the "
                   f"{volume.POINT_BUDGET:,} the browser will composite. Raise *Detail*.")
    else:
        diverging = what == "anomaly"
        scale = (theme.BLUE_PURPLE_DIVERGING if diverging else
                 theme.SEQ_UNCERTAINTY if what == "uncertainty" else theme.SEQ_TEMPERATURE)
        lo, hi = vol["value_range"]
        # .tolist() is the FIX, not a style choice: plotly >= 6 serialises numpy as a base64
        # blob that the bundled plotly.js does not decode, and the trace arrives with EMPTY
        # coordinates -- an empty box with a correct-looking colourbar, the worst kind of
        # failure because it looks like bad data rather than bad transport. Plotly here is 7.0.
        trace = go.Volume(
            x=vol["x"].tolist(), y=vol["y"].tolist(), z=vol["z"].tolist(),
            value=vol["value"].tolist(), colorscale=scale,
            isomin=lo, isomax=hi, opacity=0.13, surface_count=18,
            colorbar=dict(title=dict(text=vol["units"], side="right"),
                          outlinewidth=0, tickcolor=theme.EDGE, len=0.72),
            **({"cmid": 0.0} if diverging else {}))

        data = [trace]
        lat = np.asarray(D.base.LAT, dtype="float64")
        lon = np.asarray(D.base.LON, dtype="float64")
        data.append(_land_surface(go, f["land_mask"], lat, lon))

        d26_med = None
        if show26:
            from phase2.derived.heat_content import heat_content_field
            hc = heat_content_field(f)
            d26 = np.asarray(hc["d26"], dtype="float64")
            if np.isfinite(d26).any():
                data.append(_d26_surface(go, d26, lat, lon))
                d26_med = float(np.nanmedian(d26))

        fig = go.Figure(data=data)
        fig.update_layout(**theme.plotly_layout(600),
                          scene=theme.scene_axes("longitude (°E)", "latitude (°N)",
                                                 "depth (m, negative = down)",
                                                 volume.aspect_ratio(zx)))
        st.plotly_chart(fig, use_container_width=True, theme=None)
        drew_3d = True

    if not drew_3d:
        _fallback_2d(cube, what)

    ux.tiles([
        ("WATER CELLS DRAWN", f"{vol['n_with_water']:,}"),
        ("SEA FLOOR", f"{vol['n_below_seafloor']:,}", "", "no water — not missing data"),
        ("GRID", "×".join(str(s) for s in vol["shape"])),
        ("VERTICAL STRETCH", f"{zx:g}", "×", "a viewing choice"),
    ] + ([("MEDIAN 26 °C DEPTH", f"{d26_med:.0f}", "m", "basin-wide")]
         if drew_3d and show26 and d26_med is not None else []))

    ux.explain("seafloor", label="Why parts of the volume are empty")

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"T(x,y,z),\ \sigma(x,y,z) \;=\; f_\theta\big(\mathrm{SST},\ \mathrm{SSS},\ "
        r"\mathrm{SSH},\ u,\ v,\ w_u,\ w_v\big)",
        [("f_θ", "the trained network — a 3-D residual CNN encoder into a 128-dim latent, "
                 "then a decoder to 15 depths", "", "src/phase2/tscast_nio/models/tscast.py"),
         ("SST, SSS, SSH", "sea surface temperature, salinity and height", "°C, PSU, m",
          "satellite observations"),
         ("u, v, w_u, w_v", "surface currents and wind stress", "m s⁻¹", "satellite observations"),
         ("T", "reconstructed temperature at 15 depths", "°C", "model output"),
         ("σ", "the model's own uncertainty at each depth", "°C", "model output"),
         ("z", "depth, 15 levels from 0 to 1000 m", "m", "oceanembed.config.DEPTHS")],
        "The network sees an 11-day window of surface maps and returns the whole column. "
        "It is never shown a subsurface measurement at inference time.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("A single day's ocean, reconstructed from the surface alone. Warm water sits in a "
              "shallow lens near the top; the cyan sheet is the depth at which it cools through "
              "26 °C."),
        conclude=("Where the cyan sheet dips deep, a cyclone crossing has a large reservoir of "
                  "warm water to draw on and can keep intensifying. Where it rides close to the "
                  "surface, a storm churns up cold water and weakens itself."),
        limits=[
            ("The vertical axis is stretched, so the basin looks far deeper than it is.",
             "printed on screen as the stretch factor"),
            ("Latitude and longitude are subsampled for the renderer — the picture is coarser "
             "than the science.", f"stride={stride}, shape {vol['shape']}"),
            ("Uncertainty shading here is the raw model spread and is NOT calibrated.",
             "artifacts/uncertainty_calibration.json"),
            ("The grid stops at 1000 m. Nothing below that depth is modelled at all.",
             "oceanembed.config.DEPTHS"),
        ])


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
        ).properties(height=480), use_container_width=True)
    st.caption(f"{sl['what']} at {sl['depth_m']:.0f} m — altair ships with Streamlit, so this "
               f"renders wherever the app runs.")
