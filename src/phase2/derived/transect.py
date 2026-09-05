"""Depth-vs-distance cross-sections (transects) through the reconstructed field.

The view an oceanographer actually reads structure in: a vertical slice along a line, not a
lat/lon cube. Two endpoints in, a (distance x depth) grid of temperature + sigma out, with the
20 C and 26 C isotherms drawn as real lines on top.

WHY BILINEAR, NOT REPEATED reconstruct()
----------------------------------------
`TSCastPredictor.reconstruct(lat, lon, date)` snaps its argument to the nearest 0.25 deg grid
CENTRE and returns that cell's profile. [VERIFIED 2026-09-04] four points up to 0.12 deg off a
centre all returned a byte-identical profile; only crossing into the next cell changed it. So
sampling a transect by calling reconstruct() at each along-track point would return a staircase --
the same value repeated across every point that snaps to one cell -- which is exactly wrong for a
plot whose whole purpose is a smooth thermocline tilt. Instead we sample by BILINEAR interpolation
of the precomputed `predict_field()` grid, implemented and tested here as a pure function.

LAND IS A GAP, NEVER A SMOOTHED VALUE
-------------------------------------
`predict_field()` already writes NaN on land and below the seafloor. `bilinear_at` returns NaN if
ANY of the four surrounding grid corners is NaN, so a point on or adjacent to a land cell -- or a
depth below the local seafloor -- becomes a gap in the section, never an average that quietly
bridges the coast or the bottom. This is per depth: a shelf point is valid in the mixed layer and
NaN at 1000 m, exactly as it should be.
"""
from __future__ import annotations

import numpy as np

from phase2.tscast_nio import config

DEPTHS = np.asarray(config.DEPTHS, dtype="float64")
EARTH_R_KM = 6371.0088


# --------------------------------------------------------------------- geometry

def haversine_km(lat0, lon0, lat1, lon1) -> np.ndarray:
    """Great-circle distance in km. Vectorised; scalars return a 0-d array."""
    lat0, lon0, lat1, lon1 = (np.deg2rad(np.asarray(v, dtype="float64"))
                              for v in (lat0, lon0, lat1, lon1))
    dlat, dlon = lat1 - lat0, lon1 - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin(dlon / 2) ** 2
    return EARTH_R_KM * 2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _unit(lat_deg, lon_deg) -> np.ndarray:
    phi, lam = np.deg2rad(lat_deg), np.deg2rad(lon_deg)
    return np.array([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)])


def track_points(lat0, lon0, lat1, lon1, n: int = 50):
    """`n` points along the great circle between the endpoints, EVENLY SPACED BY DISTANCE.

    Uses spherical linear interpolation (slerp) of the endpoints' unit vectors, so the spacing is
    even in arc length rather than in degrees -- at this basin's latitudes 1 deg of longitude is
    ~15% shorter than 1 deg of latitude, and naive lat/lon interpolation would bunch points where
    the track runs east-west. Returns (lat, lon, distance_km), each length n, distance measured
    from the first endpoint.
    """
    if n < 2:
        raise ValueError(f"n={n}: a transect needs at least two points")
    v0, v1 = _unit(lat0, lon0), _unit(lat1, lon1)
    omega = float(np.arccos(np.clip(np.dot(v0, v1), -1.0, 1.0)))
    f = np.linspace(0.0, 1.0, n)
    if omega < 1e-9:                                   # endpoints coincide (or nearly)
        lat = np.full(n, float(lat0)); lon = np.full(n, float(lon0))
    else:
        s0 = np.sin((1 - f) * omega) / np.sin(omega)
        s1 = np.sin(f * omega) / np.sin(omega)
        v = s0[:, None] * v0[None, :] + s1[:, None] * v1[None, :]
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        lat = np.rad2deg(np.arcsin(np.clip(v[:, 2], -1.0, 1.0)))
        lon = np.rad2deg(np.arctan2(v[:, 1], v[:, 0]))
    dist = f * (omega * EARTH_R_KM)
    return lat, lon, dist


# ------------------------------------------------------------------ interpolation

def bilinear_at(field_2d, lat, lon, lat_grid, lon_grid) -> float:
    """Bilinear sample of a (n_lat, n_lon) field at one (lat, lon). Pure and NaN-strict.

    lat_grid / lon_grid are the ASCENDING cell-centre coordinates. Returns NaN when the point is
    outside the grid (never extrapolates) or when ANY of the four surrounding corners is NaN (never
    smooths through land or the seafloor). Exact at a grid node.
    """
    field_2d = np.asarray(field_2d, dtype="float64")
    lat_grid = np.asarray(lat_grid, dtype="float64")
    lon_grid = np.asarray(lon_grid, dtype="float64")
    lat, lon = float(lat), float(lon)

    if not (lat_grid[0] <= lat <= lat_grid[-1] and lon_grid[0] <= lon <= lon_grid[-1]):
        return float("nan")

    i = int(np.clip(np.searchsorted(lat_grid, lat, side="right") - 1, 0, lat_grid.size - 2))
    j = int(np.clip(np.searchsorted(lon_grid, lon, side="right") - 1, 0, lon_grid.size - 2))

    f00, f01 = field_2d[i, j], field_2d[i, j + 1]
    f10, f11 = field_2d[i + 1, j], field_2d[i + 1, j + 1]
    if not np.isfinite([f00, f01, f10, f11]).all():
        return float("nan")                            # land / seafloor adjacent -> gap, not blend

    dy = lat_grid[i + 1] - lat_grid[i]
    dx = lon_grid[j + 1] - lon_grid[j]
    ty = 0.0 if dy == 0 else (lat - lat_grid[i]) / dy
    tx = 0.0 if dx == 0 else (lon - lon_grid[j]) / dx
    top = f00 * (1 - tx) + f01 * tx
    bot = f10 * (1 - tx) + f11 * tx
    return float(top * (1 - ty) + bot * ty)


def sample_transect(track, field_dict, *, keys=("temperature", "sigma")) -> dict:
    """Sample a `predict_field()` output along a track into (n_points, 15) sections.

    track       : (lat, lon, distance_km) from `track_points`.
    field_dict  : output of `phase2.tscast_nio.field.predict_field`. Each named key must be
                  (100, 240, 15), NaN on land / below the seafloor.
    keys        : which fields to sample. The default is the original pair, so every existing
                  caller is unchanged; pass ("temperature", "sigma", "salinity") to carry the
                  salinity a density or sound-speed overlay needs.

    Returns one (n_points, 15) array per key, plus the track arrays and DEPTHS, so the caller
    plots distance (x) against depth (y) directly. Every value comes through bilinear_at, so land
    and the seafloor are gaps, per depth.
    """
    lat, lon, dist = track
    lat = np.asarray(lat, dtype="float64")
    lon = np.asarray(lon, dtype="float64")
    keys = tuple(keys)
    missing = [k for k in keys if field_dict.get(k) is None]
    if missing:
        raise KeyError(f"the field carries no {missing}; a stage-1 field has no salinity")

    arrays = {k: np.asarray(field_dict[k], dtype="float64") for k in keys}
    want = (config.N_LAT, config.N_LON, config.N_DEPTHS)
    for name, a in arrays.items():
        if a.shape != want:
            raise ValueError(f"{name} is {a.shape}, expected {want}")
    n_d = want[2]

    lat_grid = np.asarray(config.LAT, dtype="float64")
    lon_grid = np.asarray(config.LON, dtype="float64")
    out = {name: np.full((lat.size, n_d), np.nan) for name in keys}
    for k in range(lat.size):
        for d in range(n_d):
            for name, a in arrays.items():
                out[name][k, d] = bilinear_at(a[:, :, d], lat[k], lon[k], lat_grid, lon_grid)
    out.update({"lat": lat, "lon": lon,
                "distance_km": np.asarray(dist, dtype="float64"), "depths": DEPTHS.copy()})
    return out


# --------------------------------------------------------------------- isotherms

def isotherm_depth(temp_1d, depths=DEPTHS, threshold_c: float = 26.0) -> float:
    """Depth of the first crossing of `threshold_c`, linearly interpolated between the two
    bracketing levels. NaN if the surface is already below the threshold or the profile never
    crosses it.

    Generalises heat_content.d26_from_profile (which fixes 26 C) to any threshold, using the same
    bracketing method. Deliberately a separate function: the shipped D26 code is frozen and not
    edited here.
    """
    t = np.asarray(temp_1d, dtype="float64")
    z = np.asarray(depths, dtype="float64")
    ok = np.isfinite(t)
    if not ok.any() or not ok[0] or t[0] < threshold_c:
        return float("nan")
    zt, tt = z[ok], t[ok]
    warm = tt >= threshold_c
    if warm.all():
        return float("nan")                            # never crosses within the sampled column
    first_cold = int(np.argmax(~warm))                 # first level below the threshold
    if first_cold == 0:
        return float("nan")
    t_hi, t_lo = tt[first_cold - 1], tt[first_cold]     # bracket: warm above, cold below
    z_hi, z_lo = zt[first_cold - 1], zt[first_cold]
    if t_hi == t_lo:
        return float(z_hi)
    frac = (t_hi - threshold_c) / (t_hi - t_lo)
    return float(z_hi + frac * (z_lo - z_hi))


def isotherm_line(section: dict, threshold_c: float = 26.0) -> np.ndarray:
    """The isotherm depth at each along-track point of a `sample_transect` section. NaN where the
    point does not reach the threshold (open a gap in the line, do not draw through it)."""
    T = section["temperature"]
    z = section["depths"]
    return np.array([isotherm_depth(T[k], z, threshold_c) for k in range(T.shape[0])])


# ------------------------------------------------------------------ derived overlays

def add_derived(section: dict) -> dict:
    """Add sigma_theta and sound_speed to a section that already carries temperature AND salinity.

    In place, and returns the same dict. Both are computed level by level from the section's own
    sampled values, so a gap in either input is a gap in the output rather than a number bridged
    across the seafloor.

    THE OVERLAYS THESE FEED CANNOT USE `isotherm_line`
    Density and sound speed both change in the opposite sense to temperature over most of the
    column, and `isotherm_depth` returns NaN unless the SURFACE value already exceeds the
    threshold. Use `profile_features.contour_line(..., direction="increasing")` instead; see that
    module's docstring for the measurement.
    """
    if "salinity" not in section:
        raise KeyError("add_derived needs a section sampled with keys including 'salinity'")
    from phase2.physics.seawater import sigma_theta, sound_speed

    t = np.asarray(section["temperature"], dtype="float64")
    s = np.asarray(section["salinity"], dtype="float64")
    z = np.asarray(section["depths"], dtype="float64")
    section["sigma_theta"] = sigma_theta(s, t)
    section["sound_speed"] = sound_speed(s, t, z[None, :])
    return section


def floats_near_track(track, when, field_dict, *, max_km: float = 75.0, search_days: float = 5.0,
                      key: str = "temperature", engine=None) -> list[dict]:
    """Independent Argo profiles lying near the track, positioned ALONG it. -> list of dicts.

    Each float is placed at the along-track distance of its nearest track point, so it can be
    scattered straight onto a (distance x depth) section. The model profile is sampled at the
    FLOAT's own position by `bilinear_at`, not at the nearest track point -- the float is what is
    being compared against, so the model has to be read where the float actually was.

    `offset_km` and `temporal_offset_days` travel with every match: a float 60 km and 4 days away
    is a weaker check than one 5 km and same-day, and a panel that hides that is overstating its
    own validation. Returns [] when nothing is in the window, which the caller must show honestly
    rather than drawing an empty overlay that reads as agreement.
    """
    from phase2.validation.argo_overlay import find_nearest_profiles

    lat, lon, dist = (np.asarray(a, dtype="float64") for a in track)
    span = max(float(lat.max() - lat.min()), float(lon.max() - lon.min())) / 2.0
    mid_lat = float((lat.max() + lat.min()) / 2.0)
    mid_lon = float((lon.max() + lon.min()) / 2.0)
    # A generous k: `find_nearest_profiles` ranks by distance to the CENTRE, so on a long track a
    # small k would return only floats bunched near the midpoint and silently drop both ends.
    matches = find_nearest_profiles(mid_lat, mid_lon, when, k=400,
                                    search_deg=span + max_km / 100.0 + 0.5,
                                    search_days=search_days, engine=engine)

    arr = np.asarray(field_dict[key], dtype="float64")
    lat_grid = np.asarray(config.LAT, dtype="float64")
    lon_grid = np.asarray(config.LON, dtype="float64")
    depths = DEPTHS
    out: list[dict] = []
    for m in matches:
        d_to_track = haversine_km(m.latitude, m.longitude, lat, lon)
        i = int(np.argmin(d_to_track))
        if float(d_to_track[i]) > float(max_km):
            continue
        model = np.array([bilinear_at(arr[:, :, k], m.latitude, m.longitude, lat_grid, lon_grid)
                          for k in range(depths.size)])
        floatp = np.array([np.nan if v is None else float(v) for v in m.temperature_profile])
        both = np.isfinite(model) & np.isfinite(floatp)
        if not both.any():
            continue                      # no overlapping level: a real absence, not a zero error
        out.append({
            "lat": float(m.latitude), "lon": float(m.longitude), "datetime": str(m.datetime),
            "distance_km": float(dist[i]), "offset_km": float(d_to_track[i]),
            "temporal_offset_days": float(m.temporal_offset_days),
            "depths": depths.copy(), "float": floatp, "model": model,
            "error": np.where(both, model - floatp, np.nan),
            "n_levels_compared": int(both.sum()),
            "rmse": float(np.sqrt(np.mean((model[both] - floatp[both]) ** 2))),
        })
    out.sort(key=lambda d: d["distance_km"])
    return out


def slide(lon0: float, lon1: float, shift: float, lon_min: float, lon_max: float):
    """Move a track east/west by `shift` degrees WITHOUT changing its shape. -> (lon0, lon1, used).

    The obvious implementation -- clip each endpoint against the grid independently -- lets one end
    stop at the boundary while the other keeps going, so the track silently SHRINKS instead of
    sliding. A control that promises to hold a line's shape and quietly deforms it is worse than no
    control: the section changes and nothing says so.

    Clipping the SHIFT instead, bounded by whichever end reaches the edge first, preserves the span
    by construction. `used` differs from `shift` exactly when the request was trimmed, so a caller
    can say so.
    """
    room_east = float(lon_max) - max(float(lon0), float(lon1))
    room_west = float(lon_min) - min(float(lon0), float(lon1))
    used = float(np.clip(float(shift), room_west, room_east))
    return float(lon0) + used, float(lon1) + used, used
