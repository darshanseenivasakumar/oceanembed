"""Thermal front detection from SST gradient, one snapshot at a time.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config; modifies nothing.

METHOD
Gradient magnitude |grad SST| on the spherical metric (see `_metric`), reported in degC / 100 km
so the number is directly comparable to published front strengths rather than being in an
implementation-defined unit.

THRESHOLD -- a percentile, and the reason matters
The front mask is the top `percentile` of the in-domain gradient distribution for that snapshot,
NOT an absolute degC/km cutoff. We have no independent front climatology for the North Indian
Ocean to calibrate an absolute threshold against, and a value borrowed from a well-studied system
(the California Current, the Gulf Stream) would either flood this basin or empty it. A percentile
is a stated convention that a reader can argue with; a borrowed constant would be a fabricated
number wearing a citation.

The consequence, stated plainly: this detector finds the SHARPEST fronts PRESENT, always. It
cannot tell you a snapshot has no fronts. `mean_gradient` and `threshold` are returned so that a
"front" in a flat field is visible as a weak one instead of being reported as a detection.

Belkin & O'Reilly (2009) J. Marine Systems 78, 319-326 is the standard reference for SST front
detection. We implement the plain gradient step, not their contextual median filter -- said here
so the citation is not read as more than it is.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

from . import _metric

#: Top decile of the gradient distribution. A convention, not a published constant.
PERCENTILE = 90.0

#: A front is a connected feature; one isolated hot pixel is noise.
MIN_CELLS = 3

_M_PER_100KM = 1e5


def sst_gradient(sst) -> dict:
    """SST gradient on the spherical metric.

    sst : (..., n_lat, n_lon) in degC.

    Returns {"magnitude", "d_dx", "d_dy"} in **degC per 100 km**. Edge and land-adjacent cells
    are NaN.
    """
    t = np.asarray(sst, dtype="float64")
    d_dx = _metric.ddx(t) * _M_PER_100KM
    d_dy = _metric.ddy(t) * _M_PER_100KM
    return {
        "magnitude": np.hypot(d_dx, d_dy),
        "d_dx": d_dx,
        "d_dy": d_dy,
        "units": "degC/100km",
    }


def detect_fronts(sst, *, percentile: float = PERCENTILE, min_cells: int = MIN_CELLS) -> dict:
    """Front segments in ONE SST snapshot.

    sst : (n_lat, n_lon) in degC.

    Returns the mask, the gradient field, the threshold that produced them, and one dict per
    connected front segment.
    """
    t = np.asarray(sst, dtype="float64")
    if t.ndim != 2:
        raise ValueError(
            f"detect_fronts takes ONE snapshot, shape (n_lat, n_lon); got {t.shape}."
        )
    if not 0.0 < percentile < 100.0:
        raise ValueError(f"percentile must be in (0, 100), got {percentile}")

    grad = sst_gradient(t)
    mag = grad["magnitude"]
    finite = np.isfinite(mag)
    if not finite.any():
        raise ValueError("SST gradient is NaN everywhere -- check the field was loaded.")

    threshold = float(np.percentile(mag[finite], percentile))
    mask = finite & (mag >= threshold)
    labels, n = _metric.label_components(mask, min_cells=min_cells)

    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")

    segments: list[dict] = []
    for k in range(1, n + 1):
        sel = labels == k
        rows, cols = np.nonzero(sel)
        segments.append({
            "centroid_lat": float(lat[rows].mean()),
            "centroid_lon": float(lon[cols].mean()),
            "n_cells": int(sel.sum()),
            "mean_gradient": float(np.nanmean(mag[sel])),
            "max_gradient": float(np.nanmax(mag[sel])),
        })
    segments.sort(key=lambda s: s["max_gradient"], reverse=True)

    return {
        "mask": labels > 0,
        "labels": labels,
        "magnitude": mag,
        "threshold": threshold,
        "percentile": float(percentile),
        "n_fronts": n,
        "fronts": segments,
        "mean_gradient": float(np.nanmean(mag[finite])),
        "units": "degC/100km",
        # Restated in the payload so a downstream panel cannot present a weak field as a detection.
        "note": "threshold is a percentile of THIS snapshot; the strongest gradients are always "
                "returned, so a low `threshold` means the field is flat, not that fronts are strong",
    }
