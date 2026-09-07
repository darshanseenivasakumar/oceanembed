"""Acoustic structure from a reconstructed water column. Owner: Unit A (Arjhun).

Sound speed is the operational reason a navy or a fisheries agency wants subsurface temperature at
all: it decides how far a sonar hears, where a signal bends, and where a target can hide. It is
also the one derived product where this model's weakness is not the limiting factor -- see the
error budget below.

WHAT CAN AND CANNOT BE SHIPPED FROM A 0-1000 m GRID
---------------------------------------------------
SONIC LAYER DEPTH -- YES. The near-surface sound-speed maximum. [MEASURED 2026-09-05 on GLORYS
T/S, daily_sat/v001, 2025-09-09, 8,973 full-depth cells] the median SLD is 30 m, and restricting
the search to 0-150 m, 0-300 m or 0-500 m changes the answer for 0.1% of cells or fewer -- the
sound speed is still falling at 1000 m almost everywhere, so the whole-column maximum IS the
near-surface one. 17.5% of cells have it at the surface, which is a real result meaning there is
no surface duct, not a missing value.

SOFAR CHANNEL AXIS -- MOSTLY NO, AND THAT IS THE HONEST ANSWER. The axis is the sound-speed
minimum below the sonic layer. [MEASURED, same field] **8,502 of 8,973 cells -- 94.75% -- have
their minimum at the deepest sampled level, 1000 m.** The tropical Indian Ocean SOFAR axis sits
near 1500-2000 m, BELOW this project's grid. So a basin-wide "SOFAR axis depth" map would be a
picture of the bottom of the grid 95% of the time. `profile_features.extremum_depth` refuses that
case by design and returns AT_DEEPEST_LEVEL; what ships instead is a categorical map of WHERE the
axis is resolvable, plus its depth at the ~5% of points where it genuinely is.

WHY SALINITY UNCERTAINTY BARELY MATTERS HERE, AND TEMPERATURE IS THE WHOLE GAME
------------------------------------------------------------------------------
Mackenzie's temperature terms are far stronger than its salinity term over this basin's range.
[MEASURED at mean basin conditions, T = 20.81 degC, S = 35.19 psu, 100 m]

    the deliverable's temperature RMSE   0.9006 degC  ->  2.392 m/s
    stage 2's salinity RMSE (A18)        0.2695 psu   ->  0.304 m/s
                                                          ------- temperature dominates 7.9x

That is what makes an acoustic product from this model defensible: it is essentially a
temperature product, and temperature is what the model actually predicts and validates.
`error_budget` computes this for any conditions rather than quoting the one number.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config as base
from phase2.derived import profile_features as pf
from phase2.physics.seawater import sound_speed, sound_speed_in_range

DEPTHS = np.asarray(base.DEPTHS, dtype="float64")

#: Reasons, re-exported so a caller need not import both modules to read a result.
OK = pf.OK
NO_DUCT = pf.AT_SHALLOWEST_LEVEL          # the maximum is at the surface: no surface duct
BELOW_GRID = pf.AT_DEEPEST_LEVEL          # the extremum is deeper than 1000 m
NO_DATA = pf.NO_DATA
TOO_SHALLOW = pf.COLUMN_TOO_SHALLOW        # the water is too shallow to host a sound channel

#: A SOFAR axis claim requires a FULL water column. Without this guard, 336 of 848 cells that
#: reported "axis resolved" on real GLORYS T/S -- 40% of them -- sat in water shallower than 300 m,
#: and their "axis" came back at 5, 10, 20, 30 m. A five-metre dip in a ten-metre column in the
#: Palk Strait is not a sound channel; it is a shelf, and calling it an axis is precisely the
#: plausible-looking wrong number this project keeps having to catch. [MEASURED 2026-09-05; found
#: by clicking 8.25 N 78.00 E on the page and reading what it claimed.] With the guard, the 471
#: surviving cells report axis depths of 200, 300, 500 and 700 m only -- all physically sensible.
SOFAR_MIN_COLUMN_M = 1000.0

#: A label per reason, for a legend. The SOFAR wording differs from the SLD wording on purpose:
#: the same code means two different physical things depending on which feature was asked for.
SLD_LABEL = {OK: "duct resolved", NO_DUCT: "no surface duct", NO_DATA: "no water column",
             pf.TOO_FEW_LEVELS: "too few levels", BELOW_GRID: "maximum below 1000 m"}
SOFAR_LABEL = {OK: "axis resolved", BELOW_GRID: "axis below 1000 m", NO_DATA: "no water column",
               pf.TOO_FEW_LEVELS: "too few levels", NO_DUCT: "minimum at the surface",
               pf.NO_LEVELS_BELOW: "no levels below the sonic layer",
               TOO_SHALLOW: "water too shallow for a sound channel"}


def sound_speed_field(salinity, theta, depths=DEPTHS) -> np.ndarray:
    """Mackenzie sound speed over a whole (..., n_depths) field, m/s.

    Argument order follows `seawater.sound_speed` and the rest of that module: SALINITY FIRST.
    """
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    if S.shape != t.shape:
        raise ValueError(f"salinity {S.shape} against theta {t.shape}")
    z = np.asarray(depths, dtype="float64")
    if S.shape[-1] != z.size:
        raise ValueError(f"last axis is {S.shape[-1]}, expected {z.size} depths")
    return sound_speed(S, t, z)


def in_envelope(salinity, theta, depths=DEPTHS) -> np.ndarray:
    """Where Mackenzie's quoted validity range holds. See `seawater.sound_speed_in_range`."""
    return sound_speed_in_range(np.asarray(salinity, dtype="float64"),
                                np.asarray(theta, dtype="float64"),
                                np.asarray(depths, dtype="float64"))


def sonic_layer_depth(c_profile, depths=DEPTHS):
    """Depth of the near-surface sound-speed maximum, m. -> (depth, reason).

    A maximum at the surface returns 0.0 with reason NO_DUCT -- a finite, meaningful answer
    ("there is no surface duct here"), not an absence. 17.5% of the real basin is like that.

    The search is the whole column, not a near-surface window, because the two agree: restricting
    to 0-150/300/500 m moves 0.1% of cells or fewer, since sound speed is still falling at 1000 m
    almost everywhere. Using the whole column avoids a window parameter nobody could justify a
    value for.
    """
    return pf.extremum_depth(c_profile, depths, "max")


def sofar_axis(c_profile, depths=DEPTHS, *, below_m: float | None = None,
               min_column_m: float = SOFAR_MIN_COLUMN_M):
    """Depth of the sound-speed minimum below the sonic layer, m. -> (depth, reason).

    Returns BELOW_GRID for the great majority of real profiles, and that is the correct answer --
    see the module docstring. A caller must render that as its own category, never as 1000 m.

    `min_column_m` is the guard SOFAR_MIN_COLUMN_M documents: a sound channel is a deep-ocean
    feature, and a minimum found in a shelf column is an artifact of where the seafloor happens to
    be, not a channel. Pass a smaller value only with a reason.
    """
    c = np.asarray(c_profile, dtype="float64")
    z = np.asarray(depths, dtype="float64")
    finite = np.isfinite(c)
    if not finite.any():
        return float("nan"), NO_DATA
    if float(z[finite].max()) < float(min_column_m):
        return float("nan"), TOO_SHALLOW
    return pf.extremum_depth(c, z, "min", below_m=below_m)


def profile(salinity_1d, theta_1d, depths=DEPTHS) -> dict:
    """Everything one water column has to say acoustically.

    Returns sound_speed (n_depths), in_envelope (n_depths bool), sld/sld_reason,
    sofar/sofar_reason, and the surface-to-axis speed range where both are known.
    """
    c = sound_speed_field(np.asarray(salinity_1d, dtype="float64"),
                          np.asarray(theta_1d, dtype="float64"), depths)
    sld, sld_why = sonic_layer_depth(c, depths)
    axis, axis_why = sofar_axis(c, depths, below_m=(sld if np.isfinite(sld) else None))
    finite = np.isfinite(c)
    return {
        "depths": np.asarray(depths, dtype="float64"), "sound_speed": c,
        "in_envelope": in_envelope(salinity_1d, theta_1d, depths),
        "sld_m": sld, "sld_reason": sld_why,
        "sofar_m": axis, "sofar_reason": axis_why,
        "c_min": float(np.nanmin(c)) if finite.any() else float("nan"),
        "c_max": float(np.nanmax(c)) if finite.any() else float("nan"),
        "n_levels": int(finite.sum()),
    }


def layer_maps(salinity, theta, depths=DEPTHS) -> dict:
    """Basin-wide SLD and SOFAR, each with a per-cell reason code.

    Returns {"sound_speed": (...,15), "sld": {...}, "sofar": {...}} where each inner dict is the
    `profile_features._field_apply` shape: depth, reason (int8), reason_meanings, counts.

    The SOFAR search is NOT restricted below each cell's own SLD here: doing so would make the
    window vary cell by cell and the resulting map impossible to read as one quantity. At basin
    scale the distinction is moot -- the minimum is below the grid almost everywhere either way.
    """
    c = sound_speed_field(salinity, theta, depths)
    return {"sound_speed": c,
            "sld": pf.extremum_depth_field(c, depths, "max"),
            "sofar": pf._field_apply(c, depths, lambda v, zz: sofar_axis(v, zz))}


def error_budget(theta_c: float, salinity_psu: float, depth_m: float, *,
                 t_rmse: float, s_rmse: float) -> dict:
    """How much of a sound-speed error comes from temperature, and how much from salinity.

    The question that decides whether an acoustic product from a temperature model is defensible.
    Both are evaluated as a one-sided perturbation at the given conditions, because Mackenzie is
    mildly non-linear in T and a symmetric difference would hide that.

    t_rmse : the temperature model's RMSE, degC   (the deliverable: 0.9006 against 962 Argo,
             scoring protocol seafloor_masked_v1; it read 0.9078 under unmasked_v1)
    s_rmse : the salinity source's RMSE, psu      (stage 2: 0.2695, A18, seeds 42/43/44)
    """
    c0 = float(sound_speed(salinity_psu, theta_c, depth_m))
    dt = float(sound_speed(salinity_psu, theta_c + float(t_rmse), depth_m)) - c0
    ds = float(sound_speed(salinity_psu + float(s_rmse), theta_c, depth_m)) - c0
    total = abs(dt) + abs(ds)
    return {
        "c0_m_s": c0,
        "from_temperature_m_s": dt, "from_salinity_m_s": ds,
        "t_rmse_c": float(t_rmse), "s_rmse_psu": float(s_rmse),
        "temperature_share": (abs(dt) / total) if total else float("nan"),
        "dominance": (abs(dt) / abs(ds)) if ds else float("inf"),
        "at": {"theta_c": float(theta_c), "salinity_psu": float(salinity_psu),
               "depth_m": float(depth_m)},
    }
