"""Turn an OceanCube into the flat arrays a 3-D volume renderer wants. F2b's data layer.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Pure numpy -- imports no plotting library at all.

WHY THIS IS SEPARATE FROM THE PAGE
The page can fail for reasons that have nothing to do with the science: plotly missing, a browser
that will not composite WebGL, a laptop that chokes on 360,000 points. None of that should make
the *data* untestable. Everything here is numpy in, numpy out, so the subsampling and the
sea-floor masking are covered by tests that run with no renderer installed.

THE TWO THINGS THAT MAKE OCEAN DATA AWKWARD IN 3-D

1. **Depth points DOWN.** Plotly's z axis increases upward, so depth is emitted as NEGATIVE
   metres: the surface sits at 0 and 1000 m at -1000. Plotting +depth would render the ocean
   upside down, with the sea floor above the surface -- exactly the mistake the F1 page's caption
   warns about ("depth increases downward, as an oceanographer would plot it").

2. **The axes are in different units.** Longitude spans 60 degrees, latitude 25, depth 1000
   metres. Left alone, a renderer draws a 1000-unit-tall spike over a 60-unit-wide base and the
   basin becomes an unreadable needle. `aspect_ratio()` returns the scene scaling that makes the
   volume look like an ocean: wide, shallow, and recognisable.

SIZE. The full cube is 100 x 240 x 15 = 360,000 points. Plotly's own volume examples use 27,000
to 64,000. `stride` subsamples in lat/lon (never in depth -- there are only 15 levels and the
thermocline is the interesting part). The default keeps ~41,000 points.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

#: Subsample every Nth cell in lat and lon. 3 -> ~34 x 80 x 15 = 40,800 points, in the range
#: plotly's own examples use. Depth is never strided: 15 levels is already coarse.
DEFAULT_STRIDE = 3

#: Above this, a browser starts to struggle. The page warns rather than silently freezing.
POINT_BUDGET = 120_000


def to_volume_arrays(cube, *, stride: int = DEFAULT_STRIDE, what: str = "temperature") -> dict:
    """Flatten a cube into x/y/z/value arrays for a volume or isosurface trace.

    Returns lon (x), lat (y), NEGATIVE depth in metres (z), the field value, and enough metadata
    for the page to describe honestly what it is showing.

    Cells below the sea floor come through as NaN -- the renderer leaves them empty, which is the
    correct picture: there is no water there. The count is reported so the page can say so rather
    than let a reader assume the gaps are missing data.
    """
    if stride < 1:
        raise ValueError(f"stride must be >= 1, got {stride}")

    values_3d = cube._field(what)                      # (n_lat, n_lon, n_depth), NaN below floor
    lat = np.asarray(config.LAT, dtype="float64")[::stride]
    lon = np.asarray(config.LON, dtype="float64")[::stride]
    depth = np.asarray(config.DEPTHS, dtype="float64")

    sub = values_3d[::stride, ::stride, :]
    mask = cube.valid_mask[::stride, ::stride, :]
    sub = np.where(mask, sub, np.nan)

    # meshgrid over (lat, lon, depth) in the SAME axis order as the array, so a value never
    # lands at the wrong coordinate. indexing="ij" is what keeps that true.
    LAT3, LON3, DEP3 = np.meshgrid(lat, lon, depth, indexing="ij")

    finite = np.isfinite(sub)
    n_total = int(sub.size)
    n_water = int(finite.sum())

    return {
        "x": LON3.ravel(),
        "y": LAT3.ravel(),
        "z": -DEP3.ravel(),                 # NEGATIVE: depth points DOWN
        "value": sub.ravel(),
        "what": what,
        "stride": int(stride),
        "shape": sub.shape,
        "n_points": n_total,
        "n_with_water": n_water,
        "n_below_seafloor": n_total - n_water,
        "over_budget": n_total > POINT_BUDGET,
        "value_range": (float(np.nanmin(sub)), float(np.nanmax(sub))) if n_water else
                       (float("nan"), float("nan")),
        "depth_axis": "negative metres -- surface at 0, sea floor downward",
        "units": {"temperature": "degC", "uncertainty": "degC (1 sigma)",
                  "anomaly": "degC vs climatology"}.get(what, ""),
        "provenance": cube._prov(kind="volume", stride=int(stride), field=what,
                                 n_points=n_total),
    }


def aspect_ratio(z_exaggeration: float = 1.0) -> dict:
    """Scene aspect that makes the basin look like a basin.

    Longitude spans 60 deg, latitude 25 deg, depth 1000 m. Rendered on equal axes the volume is a
    tall needle. This scales x:y by their true degree extents and gives depth a fixed, modest
    share, so the picture reads as a wide shallow sea -- which is what it is. `z_exaggeration`
    lets a user stretch the vertical to see the thermocline; it is a VIEWING choice and the page
    says so, because an exaggerated axis that is not labelled is a lie about proportion.
    """
    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")
    lon_span = float(lon[-1] - lon[0])
    lat_span = float(lat[-1] - lat[0])
    return {"x": 1.0,
            "y": lat_span / lon_span,
            "z": 0.35 * float(z_exaggeration),
            "z_exaggeration": float(z_exaggeration)}


def isosurface_levels(vol: dict, n: int = 4) -> list[float]:
    """Evenly spaced values between the field's percentiles, for isosurface shells.

    Percentiles rather than min/max: a single extreme cell would otherwise put every shell in a
    corner of the range and the picture would show one blob.
    """
    v = vol["value"]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return []
    lo, hi = float(np.percentile(v, 5)), float(np.percentile(v, 95))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return []
    return [float(x) for x in np.linspace(lo, hi, n)]
