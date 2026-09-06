"""One clickable basin map, shared by every feature that draws one.

OWNER: Unit A (Arjhun). NOT a page.

FIVE FEATURES DRAW THIS MAP. Written once, so the four traps below are solved once:

1. `mark_rect` against a CONTINUOUS scale has no idea how wide a cell is. Without explicit
   x/x2 and y/y2 edges Vega-Lite picks a default band and the basin renders as a handful of
   enormous blocks. mapframe.add_edges supplies the edges; HALF_CELL is 0.125 deg.

2. Vega-Lite's default `invalid: "filter"` DROPS marks whose colour value is null, so land and
   sea-floor cells vanish and a reader clicking where India should be hits nothing.
   `invalid="show"` keeps them, which is why land is clickable and can answer "there is no
   water here". It belongs on the MARK; Altair 6 raises SchemaValidationError if it is passed
   as a Color channel parameter instead.

3. The basin's true width:height is 2.29, not 1. Left to `use_container_width` it came out 1.6 and
   the Bay of Bengal was the wrong shape -- which destroys the geographic intuition a click map
   exists to exploit. Both dimensions are pinned from mapframe.map_size.

4. A diverging field must have its pale midpoint pinned to ZERO (domainMid=0), or "neutral" lands
   on whatever the data's midpoint happens to be.
"""
from __future__ import annotations

import altair as alt
import numpy as np

from phase2.derived import mapframe as MF

from app.ui import theme

#: Altair chokes above 5,000 rows by default; a full level is 24,000 cells.
alt.data_transformers.disable_max_rows()


def frame(values_2d, land_mask, lat, lon, extra: dict | None = None) -> dict:
    return MF.add_edges(MF.level_frame(values_2d, land_mask, lat, lon, extra=extra))


def _scale(scheme: str, diverging: bool):
    if diverging:
        return alt.Scale(range=theme.DIVERGING_RANGE, domainMid=0, type="linear")
    return alt.Scale(scheme=scheme)


def clickable(fr: dict, *, units: str, key: str, scheme: str = "turbo",
              diverging: bool = False, width: int = 900, tooltip_extra=()):
    """A basin map whose water cells can be clicked.

    THREE LAYERS, not one. Land and sea floor carry no value, and a single-layer chart has to
    paint them with whatever colour the scale happens to give null -- which came out as a washed
    blob roughly the colour of warm water, i.e. the map lied about where India is. Drawing them
    as their own flat-grey layers is both honest and legible, and it keeps the value scale free
    to span only real data.

    Read the selection from st.session_state[key] after
    st.altair_chart(chart, key=key, on_select="rerun").
    """
    import pandas as pd

    w, h = MF.map_size(width)
    df = pd.DataFrame({k: v for k, v in fr.items() if isinstance(v, np.ndarray)})
    sel = alt.selection_point(name="cell", fields=["lat", "lon"], on="click", clear="dblclick")

    pos = dict(
        x=alt.X("lon0:Q", title="longitude (°E)",
                scale=alt.Scale(domain=[float(df.lon0.min()), float(df.lon1.max())], nice=False)),
        x2="lon1:Q",
        y=alt.Y("lat0:Q", title="latitude (°N)",
                scale=alt.Scale(domain=[float(df.lat0.min()), float(df.lat1.max())], nice=False)),
        y2="lat1:Q")

    base = alt.Chart(df)
    land = base.transform_filter(alt.datum.kind == MF.LAND).mark_rect(
        fill=theme.LAND, stroke=None).encode(
        tooltip=[alt.Tooltip("kind:N", title="")], **pos)
    floor = base.transform_filter(alt.datum.kind == MF.SEAFLOOR).mark_rect(
        fill=theme.FLOOR, stroke=None).encode(
        tooltip=[alt.Tooltip("kind:N", title="")], **pos)

    tips = [alt.Tooltip("lat:Q", format=".2f", title="lat °N"),
            alt.Tooltip("lon:Q", format=".2f", title="lon °E"),
            alt.Tooltip("value:Q", format=".2f", title=units)]
    tips += [alt.Tooltip(f"{f}:Q", format=".2f", title=t) for f, t in tooltip_extra]

    water = base.transform_filter(alt.datum.kind == MF.WATER).mark_rect(stroke=None).encode(
        color=alt.Color("value:Q", title=units, scale=_scale(scheme, diverging),
                        legend=alt.Legend(gradientLength=190)),
        # empty=False ON THE CONDITION is load-bearing, and it is the only place it works:
        # a Vega-Lite point selection defaults to empty=True, so before the first click an
        # EMPTY selection matches EVERY mark. Each cell took the "selected" branch and got a
        # 1.8px cyan stroke -- wider than a 0.25 deg cell -- and the whole basin rendered as
        # flat cyan with the colour scale invisible beneath it.
        # Passing empty=False to selection_point() does NOT work: Altair 6 accepts the keyword
        # and then drops it during serialisation. [VERIFIED by inspecting the emitted spec.]
        opacity=alt.condition(sel, alt.value(1.0), alt.value(0.80), empty=False),
        stroke=alt.condition(sel, alt.value(theme.CYAN), alt.value(None), empty=False),
        strokeWidth=alt.condition(sel, alt.value(1.8), alt.value(0.0), empty=False),
        tooltip=tips, **pos)

    # The param goes on the LAYER, not on the child layer that uses it. Streamlit reads
    # selections from the spec's TOP-LEVEL `params`; a param declared inside a child layer
    # renders and highlights correctly but never reaches st.session_state, so every click
    # looked like it had been ignored. Child layers can still reference it by name.
    return alt.layer(land, floor, water).add_params(sel).properties(width=w, height=h)


def selected_cell(state) -> tuple[float, float] | None:
    """Pull (lat, lon) out of an Altair selection payload, or None if nothing is selected."""
    try:
        pts = (state or {}).get("selection", {}).get("cell", [])
        if not pts:
            return None
        p = pts[0]
        return float(p["lat"]), float(p["lon"])
    except Exception:
        return None
