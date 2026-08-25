"""Grid helpers for the frozen 0.25 deg North Indian Ocean grid.

Owner: Unit B (Darshan).
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def nearest_lat_index(lat: float) -> int:
    """Index into config.LAT of the nearest grid latitude."""
    return int(np.argmin(np.abs(config.LAT - lat)))


def nearest_lon_index(lon: float) -> int:
    """Index into config.LON of the nearest grid longitude."""
    return int(np.argmin(np.abs(config.LON - lon)))


def latlon_to_cell_id(lat: float, lon: float) -> int:
    """Flat cell id in row-major (lat, lon) order: id = i_lat * N_LON + i_lon."""
    i = nearest_lat_index(lat)
    j = nearest_lon_index(lon)
    return i * config.N_LON + j


def cell_id_to_latlon(cell_id: int) -> tuple[float, float]:
    """Inverse of latlon_to_cell_id -> (grid_lat, grid_lon)."""
    i, j = divmod(int(cell_id), config.N_LON)
    return float(config.LAT[i]), float(config.LON[j])


def day_of_year_features(doy: int) -> tuple[float, float]:
    """Cyclic encoding of day-of-year (1..366) -> (sin, cos)."""
    ang = 2.0 * np.pi * (doy / 365.25)
    return float(np.sin(ang)), float(np.cos(ang))


def latlon_features(lat: float, lon: float) -> tuple[float, float, float, float]:
    """Cyclic-ish encoding of coordinates -> (sin_lat, cos_lat, sin_lon, cos_lon)."""
    la = np.deg2rad(lat)
    lo = np.deg2rad(lon)
    return float(np.sin(la)), float(np.cos(la)), float(np.sin(lo)), float(np.cos(lo))
