"""Where the reconstruction can honestly answer, defined ONCE.

OWNER: shared (Phase-2). Deliberately light -- numpy and the baseline config only, no torch -- so
the collocation engine, the API and the predictor can all import it.

THE BUG THIS EXISTS FOR (audit #22)
Two gates disagreed about the same point. `data/collocation.py` tested
`config.LAT.min() <= lat <= config.LAT.max()`, which is 5.00..29.75 -- the range of cell CENTRES --
while `tscast_nio.inference.assert_point_in_domain` tested `config.REGION`, which is 5.0..30.0, the
advertised box. So 29.9 N was inside the domain for the predictor and OUTSIDE_DOMAIN for the
collocation engine, and the UI showed both. Neither was wrong on its own; having two was.

WHICH ONE WINS, AND WHY
`config.REGION`, the advertised box. It is what the problem statement asks for, what the sliders
offer and what every download used, so refusing a point inside it would contradict the contract the
project publishes. The northern 0.125 deg strip between the last cell centre (29.75) and the box
edge (30.0) is genuinely served by extrapolating the nearest centre; that is a DISTANCE question,
not a membership one, and `collocation` already flags it separately as
SPATIAL_OFFSET_EXCEEDS_CELL. Keeping the two questions apart is the point: "is this place in our
domain?" and "how far is it from a cell we actually computed?" have different answers and deserve
different flags.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config as base

__all__ = ["in_domain", "domain_box", "distance_to_nearest_centre_deg"]


def domain_box() -> dict:
    """The advertised domain, as floats. The single source both gates read."""
    r = base.REGION
    return {k: float(r[k]) for k in ("lat_min", "lat_max", "lon_min", "lon_max")}


def in_domain(lat, lon) -> bool:
    """Is this point inside the advertised box (edges included)?

    Returns False for NaN or non-numeric input rather than raising: a membership predicate that
    throws forces every caller into a try/except, and `assert_point_in_domain` already exists for
    the callers that want a refusal with a diagnosis.
    """
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if not (np.isfinite(la) and np.isfinite(lo)):
        return False
    b = domain_box()
    return (b["lat_min"] <= la <= b["lat_max"]) and (b["lon_min"] <= lo <= b["lon_max"])


def distance_to_nearest_centre_deg(lat, lon) -> float:
    """Degrees from a point to the nearest grid CENTRE, per axis, as the larger of the two.

    A point inside the box but beyond the last centre -- the 0.125 deg strip at each edge -- is
    answerable only by extrapolating that centre. This says how far, so a caller can flag it
    instead of pretending the cell sits under the point.
    """
    la, lo = float(lat), float(lon)
    d_lat = float(np.min(np.abs(np.asarray(base.LAT, dtype="float64") - la)))
    d_lon = float(np.min(np.abs(np.asarray(base.LON, dtype="float64") - lo)))
    return max(d_lat, d_lon)
