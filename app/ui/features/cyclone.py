"""The heat a storm can actually reach.

OWNER: Unit A (Arjhun). NOT a page.

Sea surface temperature is a poor predictor of whether a cyclone will intensify, because a storm
stirs the ocean and drags up whatever is underneath. What matters is how much warm water sits
above the 26 degC line -- and that is a SUBSURFACE quantity, which is exactly what this project
reconstructs from the surface.

This is the clearest answer to "why not just use SST?", and it is the feature most likely to be
asked about by a domain judge.
"""
from __future__ import annotations

import numpy as np
import streamlit as st

from phase2.derived import mapframe as MF
from phase2.derived.heat_content import CP_TCHP, ISO_C, RHO_TCHP, heat_content_field

from app.ui import data as D
from app.ui import maps, ux

PRODUCTS = {
    "tchp": ("Tropical Cyclone Heat Potential", "kJ cm⁻²", "plasma"),
    "d26": ("Depth of the 26 °C layer", "m", "viridis"),
    "ohc": ("Ocean heat content, 0–700 m", "GJ m⁻²", "inferno"),
}


def render(ctx) -> None:
    c = st.columns([2.4, 2.4, 2.6], vertical_alignment="bottom")
    with c[0]:
        with ux.control("product", ratio=(5, 2)):
            which = st.segmented_control("Show", list(PRODUCTS), default="tchp",
                                         format_func=lambda k: PRODUCTS[k][0].split(",")[0],
                                         key="cy_which") or "tchp"
    with c[1]:
        ux.explain("tchp", label="Why not just use surface temperature?")
    with c[2]:
        ux.explain("d26surface", label="What is the 26 °C layer?")

    with st.spinner("Reconstructing the field …"):
        f = D.field(ctx.date, ctx.stage, ctx.version, device=ctx.device)
    hc = heat_content_field(f)

    title, units, scheme = PRODUCTS[which]
    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")
    vals = np.asarray(hc[which], dtype="float64")
    fr = maps.frame(vals, f["land_mask"], lat, lon,
                    extra={"d26": np.asarray(hc["d26"], dtype="float64")})

    left, right = st.columns([3.1, 2.0], gap="large")
    with left:
        st.altair_chart(maps.clickable(fr, units=units, key="cy_map", scheme=scheme, width=880,
                                       tooltip_extra=(("d26", "26 °C depth (m)"),)),
                        key="cy_map", on_select="rerun")
        st.caption(f"{title} on {f['date']}. Click a cell for the column beneath it.")

    with right:
        finite = np.isfinite(vals)
        ux.tiles([
            ("BASIN MEDIAN", f"{np.nanmedian(vals):.1f}" if finite.any() else "—", units),
            ("HIGHEST", f"{np.nanmax(vals):.1f}" if finite.any() else "—", units),
            ("CELLS SCORED", f"{int(finite.sum()):,}", "", "the rest are land or too shallow"),
        ])
        picked = maps.selected_cell(st.session_state.get("cy_map"))
        if picked is None:
            st.info("Click the map to inspect one column.", icon=":material/touch_app:")
        else:
            plat, plon = picked
            i = int(np.argmin(np.abs(lat - plat)))
            j = int(np.argmin(np.abs(lon - plon)))
            st.markdown(f"**{plat:.2f}°N  {plon:.2f}°E**")
            d26 = float(hc["d26"][i, j])
            tchp = float(hc["tchp"][i, j])
            if not np.isfinite(d26):
                st.warning("No 26 °C layer here — the surface is already below 26 °C, or there is "
                           "no water column to integrate.", icon=":material/block:")
            else:
                ux.tiles([("26 °C DEPTH", f"{d26:.0f}", "m"),
                          ("TCHP", f"{tchp:.1f}", "kJ cm⁻²",
                           "above 50 supports rapid intensification")])
                st.caption("The integral below is evaluated for exactly this column.")

    # ---- 02 · the mathematics ------------------------------------------------------
    ux.maths(
        r"\mathrm{TCHP}=\frac{\rho\,c_p}{10^{7}}\int_{0}^{D_{26}}\!\big(T(z)-26\big)\,dz"
        r"\qquad\quad D_{26}=z_{k-1}+\Delta z\,\frac{T_{k-1}-26}{T_{k-1}-T_{k}}",
        [("ρ", "sea water density, held constant by the TCHP convention", "1026 kg m⁻³",
          "Leipper & Volgenau 1972 · docs/phase2/f_cyclone_heat.md"),
         ("c_p", "specific heat capacity, likewise held constant", "4000 J kg⁻¹ K⁻¹",
          "docs/phase2/f_cyclone_heat.md"),
         ("D₂₆", "depth at which temperature falls through 26 °C, linearly interpolated between "
                 "the two bracketing levels", "m", "derived from the reconstruction"),
         ("T(z)", "reconstructed temperature at depth z", "°C", "model output"),
         ("10⁷", "converts J m⁻² to the kJ cm⁻² forecasters use", "—",
          "docs/phase2/f_cyclone_heat.md"),
         ("OHC", "the same integral to a fixed 700 m against a 0 °C reference — a climate "
                 "measure, not a storm one", "GJ m⁻²", "docs/phase2/f5-physics.md")],
        f"ρ and c_p follow the TCHP convention ({RHO_TCHP:.0f}, {CP_TCHP:.0f}), which differs "
        f"deliberately from the OHC-budget convention (1025, 3985). Threshold is {ISO_C:.0f} °C.")

    # ---- 03 · the inference --------------------------------------------------------
    ux.inference(
        what=("Not how warm the sea surface is, but how much warm water is stacked beneath it — "
              "the reservoir a cyclone can actually draw on as it churns the column."),
        conclude=("High TCHP with a deep 26 °C layer is where a storm crossing can keep "
                  "intensifying. A hot but shallow surface layer looks dangerous on an SST map "
                  "and is not: the storm mixes up cold water and weakens itself."),
        limits=[
            ("TCHP is integrated from a reconstruction, so it inherits the reconstruction's "
             "error — roughly 0.9 °C per level, correlated down the column.",
             "artifacts/frozen_manifest.json"),
            ("ρ and c_p are held constant. That is the standard convention, not a claim that they "
             "are constant in the real ocean.", "docs/phase2/f_cyclone_heat.md"),
            ("Where the whole column is above 26 °C there is no crossing to interpolate, and D₂₆ "
             "is reported at the deepest valid level rather than guessed.",
             "src/phase2/derived/heat_content.py d26_from_profile"),
            ("This is ocean heat only. Cyclone intensity also depends on wind shear, humidity and "
             "storm structure, none of which are modelled here.", "docs/MASTER_SPEC.md"),
        ])
