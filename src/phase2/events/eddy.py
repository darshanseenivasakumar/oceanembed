"""Mesoscale eddy DETECTION from surface currents, one snapshot at a time.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config; modifies nothing.

DETECTION, NOT TRACKING -- and the distinction is the whole honesty of this module.
Our record is 48 monthly fields. A mesoscale eddy in the North Indian Ocean lives weeks to a few
months and translates a few km/day, so two consecutive monthly snapshots cannot be assumed to show
the same feature. Linking them would produce trajectories that look authoritative and mean nothing.
No function here takes a time series, by design.

METHOD -- Okubo-Weiss
    Sn = du/dx - dv/dy          normal strain
    Ss = dv/dx + du/dy          shear strain
    w  = dv/dx - du/dy          relative vorticity
    W  = Sn^2 + Ss^2 - w^2

W separates strain-dominated flow (W > 0) from rotation-dominated flow (W < 0). Eddy cores are
rotation-dominated. Okubo (1970) Deep-Sea Res. 17, 445-454; Weiss (1991) Physica D 48, 273-294.

THRESHOLD
Cores are W < -0.2 * sigma_W, with sigma_W the spatial standard deviation of W over valid ocean
cells IN THAT SNAPSHOT -- Isern-Fontanet et al. (2003) J. Atmos. Oceanic Technol. 20, 772-778, as
used by Chelton et al. (2007) GRL 34, L15606. The threshold is deliberately RELATIVE to the field
rather than an absolute s^-2 value: an absolute cutoff calibrated on another basin would either
flood or empty this one, and we have no independent eddy census here to calibrate against.

KNOWN LIMITATION, stated because it is a real weakness of the choice
Okubo-Weiss is threshold-sensitive and over-detects in noisy velocity fields; Chelton et al. (2007)
discuss exactly this. A geometry-based alternative (Nencioli et al. 2010, JTECH 27, 564-579) avoids
the threshold entirely. We take Okubo-Weiss first because it is a direct computation on fields we
already have, and we record the alternative rather than pretending the choice was free.

The currents are GLORYS REANALYSIS, not observations. Anything found here is an eddy in the
reanalysis. That belongs next to any count we quote.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

from . import _metric

#: Chelton et al. (2007) / Isern-Fontanet et al. (2003) core threshold, in units of sigma_W.
W_FACTOR = -0.2

#: A 0.25 deg cell is ~25 km. Mesoscale eddies in this basin are ~100-200 km across, so a feature
#: smaller than a few cells is a gradient artifact, not a resolved eddy.
MIN_CELLS = 4


def okubo_weiss(u, v) -> dict:
    """Okubo-Weiss parameter and its components from surface currents.

    u, v : (..., n_lat, n_lon) eastward / northward velocity in m/s.

    Returns {"W", "vorticity", "normal_strain", "shear_strain"} in s-2 (W) and s-1 (the rest),
    each the same shape as the input. Domain-edge rows/columns and any cell adjacent to land are
    NaN -- see `_metric` for why that is deliberate.
    """
    u = np.asarray(u, dtype="float64")
    v = np.asarray(v, dtype="float64")
    if u.shape != v.shape:
        raise ValueError(f"u and v must have the same shape, got {u.shape} and {v.shape}")

    du_dx, du_dy = _metric.ddx(u), _metric.ddy(u)
    dv_dx, dv_dy = _metric.ddx(v), _metric.ddy(v)

    normal_strain = du_dx - dv_dy
    shear_strain = dv_dx + du_dy
    vorticity = dv_dx - du_dy
    W = normal_strain**2 + shear_strain**2 - vorticity**2

    return {
        "W": W,
        "vorticity": vorticity,
        "normal_strain": normal_strain,
        "shear_strain": shear_strain,
    }


def eddy_core_mask(u, v, *, w_factor: float = W_FACTOR) -> dict:
    """Boolean mask of rotation-dominated cells, plus the threshold actually used.

    Returned so a caller can see the threshold rather than trust it.
    """
    ow = okubo_weiss(u, v)
    W = ow["W"]
    finite = np.isfinite(W)
    if not finite.any():
        raise ValueError("Okubo-Weiss is NaN everywhere -- check the currents were loaded.")
    sigma_w = float(np.nanstd(W[finite]))
    threshold = w_factor * sigma_w
    return {"mask": finite & (W < threshold), "threshold": threshold,
            "sigma_W": sigma_w, **ow}


def detect_eddies(u, v, *, w_factor: float = W_FACTOR, min_cells: int = MIN_CELLS) -> list[dict]:
    """Discrete eddies in ONE snapshot of surface currents.

    u, v : (n_lat, n_lon). A time axis is rejected rather than looped over, because a caller
    passing 48 months here is usually about to try tracking.

    Returns a list of dicts, largest first, each with centroid, size, polarity and the vorticity
    that decided the polarity. Empty list is a legitimate answer.
    """
    u = np.asarray(u, dtype="float64")
    if u.ndim != 2:
        raise ValueError(
            f"detect_eddies takes ONE snapshot, shape (n_lat, n_lon); got {u.shape}. "
            "Eddy TRACKING across months is not supported -- monthly sampling cannot support it."
        )

    core = eddy_core_mask(u, v, w_factor=w_factor)
    labels, n = _metric.label_components(core["mask"], min_cells=min_cells)

    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")
    area = _metric.cell_area_m2()
    vort = core["vorticity"]

    out: list[dict] = []
    for k in range(1, n + 1):
        sel = labels == k
        rows, cols = np.nonzero(sel)
        a = float(area[sel].sum())
        mean_vort = float(np.nanmean(vort[sel]))
        # Northern hemisphere: positive relative vorticity is cyclonic. The whole domain is
        # 5-30N, so there is no sign flip to handle -- asserted rather than assumed.
        out.append({
            "centroid_lat": float(lat[rows].mean()),
            "centroid_lon": float(lon[cols].mean()),
            "n_cells": int(sel.sum()),
            "area_km2": a / 1e6,
            "equivalent_radius_km": float(np.sqrt(a / np.pi) / 1000.0),
            "polarity": "cyclonic" if mean_vort > 0 else "anticyclonic",
            "mean_vorticity": mean_vort,
            "min_W": float(np.nanmin(core["W"][sel])),
        })

    out.sort(key=lambda e: e["area_km2"], reverse=True)
    return out


def summarise(eddies: list[dict], *, source: str | None = None) -> dict:
    """Counts by polarity -- the shape of the answer the Sentinel and the UI want.

    `source` DESCRIBES THE CURRENTS THE CALLER PASSED TO `detect_eddies`, and the caller is the
    only one who knows it -- this function receives a list of eddies and cannot tell GLORYS from
    satellite. It used to hardcode "GLORYS reanalysis surface currents, not observations", which
    was accidentally true while the only caller read the Phase-1 grids and became a FALSE
    provenance claim the moment one read the satellite bundle (measured 2026-09-03: fed
    GLOBCURRENT satellite currents, it still reported GLORYS). Same defect as the hardcoded
    `"input_source": "glorys"` in inference.py.

    Omitting it yields an explicit "unspecified" rather than a guess, so an un-updated caller
    reads as unknown instead of confidently wrong.
    """
    cyc = sum(1 for e in eddies if e["polarity"] == "cyclonic")
    return {
        "n_eddies": len(eddies),
        "n_cyclonic": cyc,
        "n_anticyclonic": len(eddies) - cyc,
        "mean_radius_km": float(np.mean([e["equivalent_radius_km"] for e in eddies]))
        if eddies else float("nan"),
        "method": "okubo-weiss",
        "tracking": False,
        "source": source or "unspecified -- the caller did not say which currents these are",
    }
