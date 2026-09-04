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


def sample_transect(track, field_dict) -> dict:
    """Sample a `predict_field()` output along a track into a (n_points, 15) section.

    track       : (lat, lon, distance_km) from `track_points`.
    field_dict  : output of `phase2.tscast_nio.field.predict_field` -- needs 'temperature' and
                  'sigma', each (100, 240, 15), NaN on land / below the seafloor.

    Returns temperature and sigma as (n_points, 15), plus the track arrays and DEPTHS, so the
    caller plots distance (x) against depth (y) directly. Every value comes through bilinear_at,
    so land and the seafloor are gaps, per depth.
    """
    lat, lon, dist = track
    lat = np.asarray(lat, dtype="float64")
    lon = np.asarray(lon, dtype="float64")
    temp = np.asarray(field_dict["temperature"], dtype="float64")
    sig = np.asarray(field_dict["sigma"], dtype="float64")
    n_lat, n_lon, n_d = temp.shape
    if (n_lat, n_lon, n_d) != (config.N_LAT, config.N_LON, config.N_DEPTHS):
        raise ValueError(f"field is {temp.shape}, expected "
                         f"{(config.N_LAT, config.N_LON, config.N_DEPTHS)}")

    lat_grid = np.asarray(config.LAT, dtype="float64")
    lon_grid = np.asarray(config.LON, dtype="float64")
    T = np.full((lat.size, n_d), np.nan)
    S = np.full((lat.size, n_d), np.nan)
    for k in range(lat.size):
        for d in range(n_d):
            T[k, d] = bilinear_at(temp[:, :, d], lat[k], lon[k], lat_grid, lon_grid)
            S[k, d] = bilinear_at(sig[:, :, d], lat[k], lon[k], lat_grid, lon_grid)
    return {"temperature": T, "sigma": S, "lat": lat, "lon": lon,
            "distance_km": np.asarray(dist, dtype="float64"), "depths": DEPTHS.copy()}


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
