"""Temperature-inversion detection (D-020). Owner: Unit B (Darshan). Pure numpy.

WHAT AN INVERSION IS HERE
In the Bay of Bengal in winter, river freshwater floats as a light lid (the barrier layer) that
stops the cooling surface from mixing down. The result is cold water sitting on top of warmer water
-- a temperature inversion, the one profile shape a "warm surface implies warm below" model draws
backwards. We measure it, per column, as the largest amount by which temperature RISES going down,
relative to the coldest water anywhere shallower:

    amplitude = max over z in (0, MAX_DEPTH_M] of [ T(z) - min over z' < z of T(z') ]

A cumulative-minimum scan. It needs no monotonicity, survives a NaN mid-column (that level is
skipped, not treated as the end of the water), and runs identically on the 15-level grid and on a
full-resolution Argo profile because it reads the depth axis it is handed. An inversion is PRESENT
when the amplitude reaches the threshold (D-020: 0.2 degC primary; every result is also reported at
0.1 and 0.5).

WHAT IT IS NOT
It is a temperature-only diagnostic. The barrier layer itself (ILD - MLD) needs salinity and lives
in `physics/layers.py`; this module never computes a model-side barrier layer, because the
satellite deliverable does not predict salinity (E-S2-SAT-03).

CONVENTIONS (shared with `profile_features.py`)
Depths are positive-down metres. Every function is NaN-safe. `amplitude` is 0.0 for a resolved
column with no inversion (a real measurement: "there is none"), and NaN only when the column cannot
be judged (fewer than two finite levels in range), with a `reason` string saying which.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config
from phase2 import basins
from phase2.derived import profile_features as PF

# --- Definition constants (D-020). Do not change without a new ADR. ---
MAX_DEPTH_M = 150.0
THRESHOLD_DEGC = 0.2
SENSITIVITY_THRESHOLDS = (0.1, 0.2, 0.5)

# --- Regions: the basin masks, with the Bay split north/south at 15 N (D-020). ---
NBOB_LAT = 15.0
NORTH_BOB = "north_bob"
SOUTH_BOB = "south_bob"
ARABIAN_SEA = basins.ARABIAN_SEA
UNASSIGNED = basins.UNASSIGNED
REGIONS = (NORTH_BOB, SOUTH_BOB, ARABIAN_SEA)

_DEPTHS = np.asarray(config.DEPTHS, dtype="float64")


def inversion_amplitude(values_1d, depths=None, *, max_depth_m: float = MAX_DEPTH_M) -> dict:
    """Inversion amplitude of one temperature profile, searched over (0, max_depth_m].

    Returns {"amplitude", "depth_max", "depth_top", "thickness", "reason"}:
      amplitude  degC, the largest warming-with-depth; 0.0 if the column is resolved but has none.
      depth_max  m of the warm maximum that realises the amplitude (NaN if amplitude is 0 or unresolved).
      depth_top  m of the shallower minimum it is measured against -- the FIRST level holding that
                 minimum value (NaN likewise).
      thickness  depth_max - depth_top.
      reason     PF.OK when scored (including a clean zero), else PF.NO_DATA / PF.TOO_FEW_LEVELS.
    """
    z_axis = _DEPTHS if depths is None else np.asarray(depths, dtype="float64").ravel()
    v = np.asarray(values_1d, dtype="float64").ravel()
    if v.size != z_axis.size:
        raise ValueError(f"{v.size} values against {z_axis.size} depths")

    in_win = z_axis <= float(max_depth_m)
    vv, zz = v[in_win], z_axis[in_win]
    finite = np.isfinite(vv)
    n = int(finite.sum())
    nan = float("nan")
    if n == 0:
        return {"amplitude": nan, "depth_max": nan, "depth_top": nan, "thickness": nan,
                "reason": PF.NO_DATA}
    if n < 2:
        return {"amplitude": nan, "depth_max": nan, "depth_top": nan, "thickness": nan,
                "reason": PF.TOO_FEW_LEVELS}

    vf, zf = vv[finite], zz[finite]
    run_min = np.minimum.accumulate(vf)                 # coldest value at or above each level
    # index of the FIRST level that holds each running minimum, so depth_top is unambiguous
    is_new_min = np.concatenate(([True], vf[1:] < run_min[:-1]))
    min_src = np.maximum.accumulate(np.where(is_new_min, np.arange(vf.size), 0))
    rises = vf - run_min                                # >= 0 everywhere; 0 at the first level
    k = int(np.argmax(rises))
    amp = float(rises[k])
    if amp <= 0.0:
        return {"amplitude": 0.0, "depth_max": nan, "depth_top": nan, "thickness": nan,
                "reason": PF.OK}
    top = int(min_src[k])
    return {"amplitude": amp, "depth_max": float(zf[k]), "depth_top": float(zf[top]),
            "thickness": float(zf[k] - zf[top]), "reason": PF.OK}


def present(amplitude, *, threshold: float = THRESHOLD_DEGC) -> np.ndarray:
    """Boolean presence at `threshold`. NaN amplitude -> False (unresolved is not an inversion)."""
    a = np.asarray(amplitude, dtype="float64")
    with np.errstate(invalid="ignore"):
        return np.isfinite(a) & (a >= float(threshold))


def inversion_field(values, depths=None, *, max_depth_m: float = MAX_DEPTH_M) -> dict:
    """`inversion_amplitude` over a grid whose LAST axis is depth. Leading axes are preserved.

    Vectorised across columns (the scalar `inversion_amplitude` is the definition; this reproduces
    it exactly -- `test_inversion.test_field_matches_the_reference_scan_column_by_column` pins the
    two together on NaN-holed random fields). Returns dict of arrays (amplitude, depth_max,
    depth_top, thickness) plus an integer `reason` array coded by `profile_features.REASON_CODE`.
    """
    arr = np.asarray(values, dtype="float64")
    z_axis = _DEPTHS if depths is None else np.asarray(depths, dtype="float64").ravel()
    if arr.shape[-1] != z_axis.size:
        raise ValueError(f"last axis {arr.shape[-1]} != {z_axis.size} depths")

    D = z_axis.size
    in_win = z_axis <= float(max_depth_m)                       # (D,) window mask
    finite = np.isfinite(arr) & in_win                          # (..., D)
    count = finite.sum(axis=-1)                                 # finite levels in the window

    # +inf at NaN / out-of-window levels: they can never be a running minimum or its source.
    filled = np.where(finite, arr, np.inf)
    run_min = np.minimum.accumulate(filled, axis=-1)            # coldest at or above, ignoring NaN
    rises = np.where(finite, arr - run_min, -np.inf)            # >=0 at finite levels, 0 at a new min
    k = np.argmax(rises, axis=-1)                               # depth of the largest warming

    idx = np.arange(D)
    prev_min = np.concatenate([np.full(run_min.shape[:-1] + (1,), np.inf),
                               run_min[..., :-1]], axis=-1)
    is_new_min = filled < prev_min                              # strict: ties keep the earlier level
    min_src = np.maximum.accumulate(np.where(is_new_min, idx, 0), axis=-1)

    take = lambda a: np.take_along_axis(a, k[..., None], axis=-1)[..., 0]
    amp = take(rises)
    top_i = take(min_src)
    z_at = z_axis[np.minimum(k, D - 1)]
    z_top = z_axis[np.minimum(top_i, D - 1)]

    scored = count >= 2
    has_inv = scored & np.isfinite(amp) & (amp > 0.0)
    nan = np.full(arr.shape[:-1], np.nan)
    amplitude = np.where(scored, np.where(has_inv, amp, 0.0), np.nan)
    depth_max = np.where(has_inv, z_at, nan)
    depth_top = np.where(has_inv, z_top, nan)
    thickness = np.where(has_inv, z_at - z_top, nan)

    reason = np.where(count == 0, PF.REASON_CODE[PF.NO_DATA],
             np.where(count == 1, PF.REASON_CODE[PF.TOO_FEW_LEVELS],
                      PF.REASON_CODE[PF.OK])).astype("int16")
    return {"amplitude": amplitude, "depth_max": depth_max, "depth_top": depth_top,
            "thickness": thickness, "reason": reason}


def region_labels(lat, lon) -> np.ndarray:
    """Basin label per point, with the Bay of Bengal split at NBOB_LAT into north/south.

    Reuses `basins.classify_points` (longitude-only, land-mask-agnostic -- a real float reports from
    water even when its 0.25 deg cell rounds onto the coast) and refines the Bay by latitude.
    """
    lat = np.asarray(lat, dtype="float64").ravel()
    base = basins.classify_points(lat, lon)
    out = base.astype(object)
    is_bob = base == basins.BAY_OF_BENGAL
    out[is_bob & (lat >= NBOB_LAT)] = NORTH_BOB
    out[is_bob & (lat < NBOB_LAT)] = SOUTH_BOB
    return out.astype(str)
