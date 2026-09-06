"""Where another measurement would teach the model most.

OWNER: Unit A (Arjhun). NOT a page.

THE WORDING HERE IS LOAD-BEARING AND IS NOT TO BE LOOSENED.
This does NOT tell anyone where to deploy a float. It surfaces "regions where additional
observations may provide high scientific value". Formal observing-system design is a much larger
discipline; this is a lightweight, interpretable heuristic that is complementary to it. Both
CLAIM and NOT_A_CLAIM come from the product module itself so the phrasing cannot drift.

THE SHALLOW-WATER GUARD
v1 ranked the Persian Gulf -- about 20 m of water -- at the top, because a place no float can
enter is by definition a place with no floats. v2 moved that guard INSIDE priority(), which takes
the full 3-D valid_mask and collapses it itself. So this caller hands over the whole mask and
does not pre-collapse it; omitting it entirely is a deliberate act that the returned provenance
records.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from phase2.products import priority_v2 as P

from app.ui import data as D
from app.ui import maps, ux


def render(ctx) -> None:
    c = st.columns([1.7, 1.7, 1.7, 1.7, 2.2], vertical_alignment="bottom")
    with c[0]:
        with ux.control("window", ratio=(5, 2)):
            win = st.slider("Mean-flow days", 5, 90, P.DEFAULT_WINDOW_DAYS, 5, key="pr_win")
    with c[1]:
        with ux.control("weights", ratio=(5, 2)):
            w_sig = st.slider("Weight: doubt", 0.0, 2.0, 1.0, 0.1, key="pr_ws")
    with c[2]:
        w_eke = st.slider("Weight: energy", 0.0, 2.0, 1.0, 0.1, key="pr_we")
    with c[3]:
        with ux.control("shallowguard", ratio=(5, 2)):
            guard = st.toggle("Deep water only", value=True, key="pr_guard")
    with c[4]:
        with ux.control("topn", ratio=(5, 2)):
            k = st.slider("Top regions", 5, 40, 15, 5, key="pr_k")

    e = st.columns([1.3, 1.3, 3.4])
    with e[0]:
        ux.explain("eke")
    with e[1]:
        ux.explain("notaclaim", label="What this is NOT")

    st.caption(f"Highlights {P.CLAIM}.")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)

    if w_sig == 0 and w_eke == 0:
        st.warning("Both weights are zero, so nothing is being ranked.",
                   icon=":material/warning:")
        return

    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")

    # Doubt, depth-averaged over the column. Uncertainty at a single level would rank a place
    # by how unsure the model is about one number, not about the water.
    sigma2d = np.nanmean(np.asarray(f["sigma"], dtype="float64"), axis=2)

    eke = _eke(ctx, win)
    if eke is None:
        st.error("Surface currents for this date are not on this machine, so eddy energy cannot "
                 "be computed. This panel will not rank on uncertainty alone — that would be a "
                 "different product wearing this one's label.")
        return

    # The FULL 3-D mask. priority() takes (n_lat, n_lon, n_depths) and applies [..., -1] itself
    # to find the columns that reach the deepest level; handing it a pre-collapsed 2-D array
    # raises rather than silently ranking everything.
    valid = np.asarray(f["valid_mask"]) if guard else None
    if not guard:
        st.warning("Shallow-water guard is OFF. Expect the ranking to fill with shelf and gulf "
                   "cells where the model is unsure only because there is almost no water.",
                   icon=":material/warning:")

    r = P.priority(sigma2d, eke, valid_mask=valid, weights=(w_sig, w_eke))
    score = np.asarray(r["priority"], dtype="float64")

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        fr = maps.frame(score, f["land_mask"], lat, lon,
                        extra={"sigma": sigma2d, "eke": np.asarray(eke, dtype="float64")})
        st.altair_chart(maps.clickable(fr, units="priority", key="pr_map",
                                       scheme="inferno", width=880,
                                       tooltip_extra=(("sigma", "±1σ (°C)"),
                                                      ("eke", "EKE (m²s⁻²)"))),
                        key="pr_map", on_select="rerun")
        st.caption("Bright is where high model doubt meets an energetic ocean. Both must be high "
                   "— the two are combined as a geometric mean, so one alone will not rank.")

    with right:
        st.markdown(f"**Top {k} candidate regions**")
        top = P.top_cells(r, k=k, lat=lat, lon=lon)
        if top:
            import pandas as pd
            df = pd.DataFrame(top)
            # top_cells returns sigma_norm / eke_norm (normalised to [0,1]), not the raw
            # fields -- selecting "sigma"/"eke" would have quietly shown neither.
            cols = [q for q in ("rank", "lat", "lon", "priority", "sigma_norm", "eke_norm")
                    if q in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True,
                         height=min(430, 38 + 29 * len(df)),
                         column_config={
                             "priority": st.column_config.NumberColumn(format="%.3f"),
                             "sigma_norm": st.column_config.NumberColumn("doubt", format="%.2f"),
                             "eke_norm": st.column_config.NumberColumn("energy", format="%.2f"),
                             "lat": st.column_config.NumberColumn("lat °N", format="%.2f"),
                             "lon": st.column_config.NumberColumn("lon °E", format="%.2f")})
        else:
            st.info("Nothing ranked under these settings.")

    ux.tiles([
        ("CELLS RANKED", f"{int(np.isfinite(score).sum()):,}"),
        ("MEAN-FLOW WINDOW", f"{win}", "days", "the monsoon reverses, so this matters"),
        ("BALANCE", f"{w_sig:g} : {w_eke:g}", "", "doubt : energy"),
    ])

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\mathrm{EKE}=\tfrac{1}{2}\big(u'^2+v'^2\big),\qquad u'=u-\bar{u}_{W}"
        r"\qquad\quad \mathrm{Priority}=\big[\hat{\sigma}\cdot\widehat{\mathrm{EKE}}\big]^{1/2}",
        [("u, v", "surface current components", "m s⁻¹", "satellite altimetry"),
         ("ū_W", "the steady flow: a rolling mean over the window you set", "m s⁻¹",
          f"W = ±{win} days"),
         ("u′, v′", "what is left after the steady flow is removed — the swirling part", "m s⁻¹",
          "computed per frame"),
         ("EKE", "eddy kinetic energy: how much the ocean is churning", "m² s⁻²",
          "src/phase2/products/priority_v2.py"),
         ("σ̂, EKÊ", "each normalised to [0,1] between its 1st and 99th percentile", "—",
          "priority_v2._norm01_robust"),
         ("[ · ]^½", "geometric mean — a region must score on BOTH factors to rank", "—",
          "priority_v2.priority")],
        "The rolling mean matters here specifically: the North Indian Ocean reverses with the "
        "monsoon, so a yearly average would label a strong seasonal current as no flow at all.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("Where the model's own uncertainty overlaps with an energetic, eddying ocean — the "
              "places its surface inputs are least able to pin down what lies beneath."),
        conclude=("These are regions where an additional profile would be informative. The "
                  "geometric mean is deliberate: a calm patch the model happens to be unsure "
                  "about does not rank, and neither does a well-understood fast current."),
        limits=[
            (P.NOT_A_CLAIM, "src/phase2/products/priority_v2.py NOT_A_CLAIM"),
            ("Uncertainty here is the model's own opinion. It cannot flag a region where the "
             "model is confidently wrong.", "artifacts/uncertainty_calibration.json"),
            ("Ranking says nothing about whether a float can physically be deployed there — "
             "shipping lanes, national waters and currents are not modelled.",
             "docs/NOVELTY_MATRIX.md"),
            ("Formal observing-system design uses adjoint sensitivity or ensemble spread. This is "
             "a heuristic, complementary to that work and not a replacement for it.",
             "docs/NOVELTY_MATRIX.md"),
        ])


@st.cache_data(show_spinner=False)
def _eke_cached(date_str: str, version: str, window: int):
    """Eddy kinetic energy from the bundle's own surface currents on that date."""
    import numpy as np
    pred = D._predictor(1, version)
    data = getattr(pred, "data", None)
    if data is None:
        return None
    chans = [str(x) for x in data.get("channels", [])]
    if "u" not in chans or "v" not in chans:
        return None
    times = np.asarray(data["times"]).astype("datetime64[D]")
    want = np.datetime64(str(date_str)[:10])
    hits = np.nonzero(times == want)[0]
    if not hits.size:
        return None
    t = int(hits[0])
    surf = data["surface"]
    u = np.asarray(surf[:, :, :, chans.index("u")], dtype="float64")
    v = np.asarray(surf[:, :, :, chans.index("v")], dtype="float64")
    # eddy_kinetic_energy returns a DICT (eke, u_prime, v_prime, window, mean_speed).
    # Passing the dict straight to priority() would rank on a dictionary.
    return P.eddy_kinetic_energy(u, v, t_index=t, window_days=window)["eke"]


def _eke(ctx, window: int):
    try:
        return _eke_cached(ctx.date, ctx.version, window)
    except Exception:
        return None
