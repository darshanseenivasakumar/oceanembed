"""Depth-of-a-feature primitives that say WHY when they cannot answer. Owner: Unit A (Arjhun).

WHY THIS EXISTS RATHER THAN REUSING isotherm_depth
--------------------------------------------------
`transect.isotherm_depth` finds the depth of an isotherm, and it is correct for that. But it is
temperature-shaped in two ways that make it silently wrong for anything else:

  * `transect.py:159` returns NaN unless the SURFACE value already exceeds the threshold, and
  * `transect.py:163` returns NaN if the profile never falls below it.

Both encode "warm at the top, colder underneath". Potential density and sound speed INCREASE with
depth, so their surface value is below every interior threshold and `isotherm_depth` returns NaN at
every point -- a blank contour line, with no error and no warning. [VERIFIED by reading the source;
the build spec for this work claimed a sigma_theta section could be fed to `isotherm_line` "and it
draws isopycnals for free", which is not the case.]

The shipped D26 path is frozen and is NOT edited here. This is a companion module.

EVERY FUNCTION RETURNS (value, reason)
--------------------------------------
START_HERE rule 8: an absence is not a value. A bare NaN from a depth-finder conflates at least
five different facts --

    no data here at all             (land, or the whole column is below the seafloor)
    too few levels to bracket anything
    the threshold is never attained anywhere in the column
    it IS attained, but only crossing the other way
    the extremum sits on the deepest sampled level, so the TRUE extremum is below the column

-- and on a cyclone or acoustics panel the reader is hunting for exactly one of them. That is the
same conflation that made a transect report 17 land points as "already below 26 degC at the
surface" (fixed in 6bb088f). Here the reason is part of the return type, so a caller cannot
accidentally not have it.

WHY MULTIPLE CROSSINGS ARE REPORTED RATHER THAN SILENTLY RESOLVED
-----------------------------------------------------------------
"The first crossing" is a choice, not a fact, whenever a profile crosses a threshold more than
once -- an inversion, a subsurface salinity maximum, a double thermocline. The value returned is
still the first one, because that is what a contour line needs, but the reason says the answer is
not unique so a caller can say so instead of implying there was only ever one.
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------- reasons

OK = "ok"                                  # exactly one crossing / an interior extremum
MULTIPLE_CROSSINGS = "multiple_crossings"  # >1 crossing; the FIRST is returned, and it is finite
NO_DATA = "no_data"                        # every level NaN: land, or wholly below the seafloor
TOO_FEW_LEVELS = "too_few_levels"          # < 2 finite levels: cannot bracket or compare
OUTSIDE_PROFILE_RANGE = "outside_profile_range"   # threshold never attained anywhere in the column
WRONG_DIRECTION = "wrong_direction"        # attained, but only crossing the way the caller excluded
AT_DEEPEST_LEVEL = "at_deepest_level"      # extremum on the last level -> the true one is deeper
AT_SHALLOWEST_LEVEL = "at_shallowest_level"
NO_LEVELS_BELOW = "no_levels_below"        # `below_m` excluded every finite level
COLUMN_TOO_SHALLOW = "column_too_shallow"  # the water is too shallow for the feature to exist

#: Every reason, in a fixed order, so the integer codes the *_field helpers return are stable
#: across runs and across machines. Appending is safe; reordering is not.
REASONS = (OK, MULTIPLE_CROSSINGS, NO_DATA, TOO_FEW_LEVELS, OUTSIDE_PROFILE_RANGE,
           WRONG_DIRECTION, AT_DEEPEST_LEVEL, AT_SHALLOWEST_LEVEL, NO_LEVELS_BELOW,
           COLUMN_TOO_SHALLOW)
REASON_CODE = {r: i for i, r in enumerate(REASONS)}
CODE_REASON = {i: r for r, i in REASON_CODE.items()}

#: A finite depth comes back with one of these. The others always carry NaN.
FINITE_REASONS = (OK, MULTIPLE_CROSSINGS, AT_SHALLOWEST_LEVEL)

DIRECTIONS = ("either", "decreasing", "increasing")


def _finite(values_1d, depths):
    v = np.asarray(values_1d, dtype="float64").ravel()
    z = np.asarray(depths, dtype="float64").ravel()
    if v.size != z.size:
        raise ValueError(f"{v.size} values against {z.size} depths")
    ok = np.isfinite(v)
    return v[ok], z[ok]


# --------------------------------------------------------------------------- crossings

def crossing_depth(values_1d, depths, threshold, *, direction: str = "either"):
    """Depth where a profile crosses `threshold`, linearly interpolated. -> (depth_m, reason).

    direction : which way the quantity moves ACROSS the threshold as depth increases.
        "decreasing" -- above the threshold at the top, below it underneath (temperature isotherms)
        "increasing" -- below at the top, above underneath (isopycnals, isohalines)
        "either"     -- the first bracket of either sense

    Unlike `transect.isotherm_depth` this does NOT require the surface value to be on a particular
    side of the threshold. A profile that starts below 26 degC and warms downward is a real thing --
    a winter Arabian Sea column, an upwelling cell -- and refusing to contour it is a bug, not
    caution.

    NaN levels are skipped, not treated as the end of the column, so a mid-column gap is bridged and
    the interpolation happens between the two finite levels that actually bracket the threshold.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction={direction!r}, expected one of {DIRECTIONS}")
    v, z = _finite(values_1d, depths)
    if v.size == 0:
        return float("nan"), NO_DATA
    if v.size < 2:
        return float("nan"), TOO_FEW_LEVELS

    thr = float(threshold)
    first = float("nan")
    n_wanted = 0
    n_any = 0
    for k in range(v.size - 1):
        a, b = v[k], v[k + 1]
        falls = a >= thr > b
        rises = a <= thr < b
        if not (falls or rises):
            continue
        n_any += 1
        if direction == "decreasing" and not falls:
            continue
        if direction == "increasing" and not rises:
            continue
        n_wanted += 1
        if n_wanted == 1:
            frac = 0.0 if a == b else (thr - a) / (b - a)
            first = float(z[k] + frac * (z[k + 1] - z[k]))

    if n_wanted == 1:
        return first, OK
    if n_wanted > 1:
        return first, MULTIPLE_CROSSINGS
    if n_any:                                    # crossed, but only the way the caller excluded
        return float("nan"), WRONG_DIRECTION
    return float("nan"), OUTSIDE_PROFILE_RANGE


def contour_line(section_2d, depths, threshold, *, direction: str = "either"):
    """`crossing_depth` at every along-track point of a section. -> (depths (n,), reasons list).

    section_2d : (n_points, n_depths), e.g. a `sample_transect` field.

    The reasons list is the point of this over a bare comprehension: a caller plotting the line can
    report WHY it is broken -- "12 of 60 points are land, none are cold" -- instead of drawing a gap
    the reader has to guess at. `transect_page.py:171-191` currently reconstructs that explanation
    after the fact by re-reading the temperature array, which is a second definition of the reason.
    """
    sec = np.asarray(section_2d, dtype="float64")
    if sec.ndim != 2:
        raise ValueError(f"section is {sec.shape}, expected 2-D (n_points, n_depths)")
    out = np.full(sec.shape[0], np.nan)
    why: list[str] = []
    for k in range(sec.shape[0]):
        out[k], reason = crossing_depth(sec[k], depths, threshold, direction=direction)
        why.append(reason)
    return out, why


# --------------------------------------------------------------------------- extrema

def extremum_depth(values_1d, depths, kind: str = "min", *, below_m: float | None = None):
    """Depth of the profile's minimum or maximum. -> (depth_m, reason).

    kind    : "min" or "max".
    below_m : ignore levels shallower than this, for a feature defined as "the minimum BELOW the
              sonic layer" (the SOFAR axis) rather than the minimum of the whole column.

    Returns the sampled LEVEL depth, not a sub-level parabolic refinement. `config.DEPTHS` is 5 m
    apart near the surface and 200-300 m apart at the bottom, so a refinement would be precise where
    it is not needed and fictitious where it is.

    THE TWO EDGE CASES ARE TREATED DIFFERENTLY, AND THE ASYMMETRY IS PHYSICAL
    ------------------------------------------------------------------------
    DEEPEST level -> NaN, reason AT_DEEPEST_LEVEL. An extremum landing on the last sampled level
    almost always means the true extremum is deeper than the column, not that it sits at 1000 m.

        [VERIFIED 2026-09-05 on real GLORYS T/S, data/processed/daily_sat/v001, 2025-09-09:
         of 8,973 cells with water at all 15 levels, 8,502 -- 94.75% -- have their sound-speed
         minimum at the 1000 m level. Only 471 have an interior minimum, all at 200-700 m. The
         tropical Indian Ocean SOFAR axis sits near 1500-2000 m, below this project's deepest
         level.]

    Returning 1000 m there would put a grid artifact on a basin map 95% of the time.

    SHALLOWEST level -> the depth IS returned, reason AT_SHALLOWEST_LEVEL. A sound-speed maximum at
    the surface is a real, meaningful answer: it means there is no sonic layer, the duct is absent.

        [VERIFIED on the same field: 1,574 of 8,973 cells -- 17.54% -- have their sound-speed
         maximum at the surface. That is a sixth of the basin, and it is physics, not a gap.]

    Nulling it would itself be reporting a measurement as an absence -- rule 8 in the other
    direction. The reason is flagged so a caller can caption it, not so it can be discarded.
    """
    if kind not in ("min", "max"):
        raise ValueError(f"kind={kind!r}, expected 'min' or 'max'")
    v, z = _finite(values_1d, depths)
    if v.size == 0:
        return float("nan"), NO_DATA
    if below_m is not None:
        keep = z >= float(below_m)
        if not keep.any():
            return float("nan"), NO_LEVELS_BELOW
        v, z = v[keep], z[keep]
    if v.size < 2:
        return float("nan"), TOO_FEW_LEVELS

    k = int(np.argmin(v) if kind == "min" else np.argmax(v))
    if k == v.size - 1:
        return float("nan"), AT_DEEPEST_LEVEL
    if k == 0:
        return float(z[0]), AT_SHALLOWEST_LEVEL
    return float(z[k]), OK


# --------------------------------------------------------------------------- whole-field

def _field_apply(values, depths, fn) -> dict:
    """Run a per-profile finder over a (n_lat, n_lon, n_depths) grid.

    Returns {"depth": (n_lat, n_lon) float, "reason": (n_lat, n_lon) int8, "reason_meanings": {...},
             "counts": {reason: n}}.

    The reason grid is INTEGER-CODED so it renders directly as a categorical map -- which is the
    product F7 actually ships, since the SOFAR-axis depth map cannot be shipped (see
    `extremum_depth`). Codes come from REASONS and are stable across runs.

    A python loop over ocean cells, deliberately. ~9-12k cells at 15 levels is well under a second,
    and every vectorised alternative would need its own copy of the reason logic -- a second
    definition of the one thing this module exists to get right.
    """
    a = np.asarray(values, dtype="float64")
    if a.ndim != 3:
        raise ValueError(f"values is {a.shape}, expected 3-D (n_lat, n_lon, n_depths)")
    n_lat, n_lon, _ = a.shape
    depth = np.full((n_lat, n_lon), np.nan)
    code = np.full((n_lat, n_lon), REASON_CODE[NO_DATA], dtype="int8")
    wet = np.isfinite(a).any(axis=-1)
    for i in range(n_lat):
        for j in range(n_lon):
            if not wet[i, j]:
                continue                                  # already NO_DATA; skip the call
            d, reason = fn(a[i, j], depths)
            depth[i, j] = d
            code[i, j] = REASON_CODE[reason]
    counts = {CODE_REASON[int(c)]: int(n) for c, n in zip(*np.unique(code, return_counts=True))}
    return {"depth": depth, "reason": code, "reason_meanings": dict(CODE_REASON),
            "counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))}


def extremum_depth_field(values, depths, kind: str = "min", *, below_m: float | None = None):
    """`extremum_depth` over a whole (n_lat, n_lon, n_depths) grid. See `_field_apply`."""
    return _field_apply(values, depths,
                        lambda v, z: extremum_depth(v, z, kind, below_m=below_m))


def crossing_depth_field(values, depths, threshold, *, direction: str = "either"):
    """`crossing_depth` over a whole (n_lat, n_lon, n_depths) grid. See `_field_apply`."""
    return _field_apply(values, depths,
                        lambda v, z: crossing_depth(v, z, threshold, direction=direction))


def tally(reasons) -> dict[str, int]:
    """Count reasons, for a one-line caption under a broken contour. Most common first."""
    counts: dict[str, int] = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
