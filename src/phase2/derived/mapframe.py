"""One depth level as a flat table of cells, with every blank explained. (Unit A / Arjhun.)

WHY THIS IS A LIBRARY FUNCTION AND NOT A PAGE HELPER
Three pages want the same thing -- the click map, the uncertainty map, the sonic-layer map -- and
each wants it as "one row per grid cell, ready to draw". Written three times it would be classified
three ways, and the classification is the part that matters.

THE CLASSIFICATION IS THE POINT
A cell with no number is one of three different facts:

    LAND      there is no ocean here at all
    SEAFLOOR  there IS ocean here, but the bottom is above the depth you asked for
    WATER     a real prediction

Collapsing those into "blank" is START_HERE rule 8, and a map is where a reader is most likely to
meet one: on a 24,000-cell picture a grey square in the Persian Gulf and a grey square on the
Deccan Plateau look identical. This returns the reason per cell so a page can answer a click with
which one it was, instead of an empty chart.

numpy only, no pandas and no streamlit -- so it is testable with no display, and so `src/` keeps
the no-Streamlit invariant `tests/phase2/test_viz_explainer.py` asserts for the whole tree.
"""
from __future__ import annotations

import numpy as np

WATER = "water"
SEAFLOOR = "below the seafloor"
LAND = "land"
KINDS = (WATER, SEAFLOOR, LAND)

#: What to tell a reader who clicked a cell of each kind. `{depth}` is filled by the caller.
KIND_NOTE = {
    LAND: "That cell is land. There is no water column here to reconstruct.",
    SEAFLOOR: ("That cell is ocean, but the seafloor is above {depth:.0f} m here, so there is no "
               "water at this depth to predict. The same point usually has a profile nearer the "
               "surface."),
    WATER: "",
}


def nearest_level(depths, depth_m: float) -> int:
    """Index of the sampled level closest to `depth_m`.

    A page offering a free-text depth would otherwise silently snap 137 m to 125 m with no sign
    that it had. Callers show `depths[nearest_level(...)]`, not the number the user typed.
    """
    z = np.asarray(depths, dtype="float64")
    return int(np.argmin(np.abs(z - float(depth_m))))


def level_frame(values_2d, land_mask, lat, lon, *, extra: dict | None = None) -> dict:
    """Every grid cell as parallel flat arrays, ready for a long-format chart.

    values_2d  : (n_lat, n_lon) at ONE depth. NaN where there is no prediction.
    land_mask  : (n_lat, n_lon) bool, True on land.
    extra      : further (n_lat, n_lon) arrays to carry along, e.g. {"sigma": ...}.

    Returns lat, lon, i, j, value, kind -- each length n_lat*n_lon, C-order -- plus any `extra`.
    EVERY cell appears, land included, so a click anywhere on the map lands on a row that can
    explain itself rather than on nothing at all.
    """
    v = np.asarray(values_2d, dtype="float64")
    land = np.asarray(land_mask, dtype=bool)
    la = np.asarray(lat, dtype="float64")
    lo = np.asarray(lon, dtype="float64")
    if v.shape != land.shape:
        raise ValueError(f"values {v.shape} against land_mask {land.shape}")
    if v.shape != (la.size, lo.size):
        raise ValueError(f"values {v.shape} against grid ({la.size}, {lo.size})")

    LA, LO = np.meshgrid(la, lo, indexing="ij")
    # Order matters: a land cell is land even though its value is also NaN. Asking "is it finite"
    # first would label the whole coastline "below the seafloor", which is a claim about bathymetry.
    kind = np.where(land, LAND, np.where(np.isfinite(v), WATER, SEAFLOOR))

    out = {
        "lat": LA.ravel(), "lon": LO.ravel(),
        "i": np.repeat(np.arange(la.size), lo.size),
        "j": np.tile(np.arange(lo.size), la.size),
        "value": v.ravel(), "kind": kind.ravel(),
    }
    for name, arr in (extra or {}).items():
        a = np.asarray(arr, dtype="float64")
        if a.shape != v.shape:
            raise ValueError(f"extra {name!r} is {a.shape}, expected {v.shape}")
        out[name] = a.ravel()
    return out


def counts(frame: dict) -> dict[str, int]:
    """How many cells of each kind, for the caption under a map. Always names all three kinds.

    Zero is reported explicitly rather than omitted: "0 land cells" is a fact about the view, and a
    missing key would read as one nobody counted.
    """
    kind = np.asarray(frame["kind"])
    return {k: int((kind == k).sum()) for k in KINDS}
