"""Spherical-metric derivatives and connected components on the frozen OceanEmbed grid.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config; modifies nothing.

WHY THIS EXISTS
Every F6 detector is a spatial derivative -- Okubo-Weiss is a velocity-gradient invariant, a front
is an SST gradient, Ekman pumping is a wind-stress curl. Doing any of them on grid INDEX spacing
instead of real distance is a units error that produces a plausible-looking field.

    dx = R * cos(lat) * dlon_radians        <- shrinks toward the pole
    dy = R * dlat_radians                   <- constant

At 5N cos(lat) = 0.9962; at 29.75N it is 0.8686. Ignoring the metric therefore inflates zonal
gradients by ~15% at the north of this domain relative to the south, which would bias every eddy
and every front northward. `CLAUDE.md` rules 10 and 11: never assume units, never assume the
coordinate convention.

NaN POLICY
A derivative that touches a NaN neighbour returns NaN. It is never computed against a fill value
and never quietly filled -- that is how the Phase-1 shelf bug produced 1000 m temperatures in the
~90 m Persian Gulf. Domain-edge rows and columns are NaN for the same reason: a one-sided
difference at the boundary is a different quantity and would not be labelled as one.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

EARTH_RADIUS_M = 6_371_000.0
OMEGA = 7.2921e-5  # rad/s, Earth's rotation rate

_LAT = np.asarray(config.LAT, dtype="float64")
_LON = np.asarray(config.LON, dtype="float64")


def _spacing(a: np.ndarray) -> float:
    """Grid step, asserted uniform -- a non-uniform axis would silently break the metric."""
    d = np.diff(a)
    step = float(d[0])
    if not np.allclose(d, step, atol=1e-6):
        raise ValueError(f"grid axis is not uniformly spaced: steps {d.min()}..{d.max()}")
    return step


def cell_size_m() -> tuple[np.ndarray, float]:
    """(dx per latitude row in metres, dy in metres) for the frozen grid."""
    dlon = np.deg2rad(_spacing(_LON))
    dlat = np.deg2rad(_spacing(_LAT))
    dx = EARTH_RADIUS_M * np.cos(np.deg2rad(_LAT)) * dlon   # (n_lat,)
    dy = EARTH_RADIUS_M * dlat
    return dx, float(dy)


def cell_area_m2() -> np.ndarray:
    """Area of each grid cell, (n_lat, n_lon). Varies with latitude; a constant would over-state
    northern areas by ~15%."""
    dx, dy = cell_size_m()
    return np.repeat((dx * dy)[:, None], len(_LON), axis=1)


def coriolis() -> np.ndarray:
    """f = 2 Omega sin(lat), (n_lat,) in s-1."""
    return 2.0 * OMEGA * np.sin(np.deg2rad(_LAT))


def _check_grid(field: np.ndarray) -> np.ndarray:
    f = np.asarray(field, dtype="float64")
    if f.shape[-2:] != (config.N_LAT, config.N_LON):
        raise ValueError(
            f"last two axes must be the frozen grid {(config.N_LAT, config.N_LON)}, "
            f"got {f.shape[-2:]}. Import config.LAT/LON rather than reshaping."
        )
    return f


def ddx(field: np.ndarray) -> np.ndarray:
    """d/dx in units-per-metre, central difference on the spherical metric.

    Edge columns are NaN. NaN propagates from either neighbour by construction.
    """
    f = _check_grid(field)
    dx, _ = cell_size_m()
    out = np.full_like(f, np.nan)
    out[..., :, 1:-1] = (f[..., :, 2:] - f[..., :, :-2]) / (2.0 * dx[:, None])
    return out


def ddy(field: np.ndarray) -> np.ndarray:
    """d/dy in units-per-metre, central difference. Edge rows are NaN."""
    f = _check_grid(field)
    _, dy = cell_size_m()
    out = np.full_like(f, np.nan)
    out[..., 1:-1, :] = (f[..., 2:, :] - f[..., :-2, :]) / (2.0 * dy)
    return out


def label_components(mask: np.ndarray, min_cells: int = 1) -> tuple[np.ndarray, int]:
    """4-connected components of a boolean mask, dropping any smaller than `min_cells`.

    4-connectivity, not 8: diagonal touching is not physical adjacency for a mesoscale feature,
    and 8-connectivity merges eddies that share only a corner.

    Returns (labels, n) where labels are 1..n and 0 is background.
    """
    from scipy.ndimage import label  # already a project dependency (requirements.txt, and
                                     # oceanembed.inference.predict uses scipy.ndimage)

    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError(f"mask must be 2-D (one snapshot), got {m.shape}")

    labels, n = label(m)
    if min_cells > 1 and n:
        counts = np.bincount(labels.ravel())
        too_small = np.where(counts < min_cells)[0]
        too_small = too_small[too_small != 0]
        if too_small.size:
            labels[np.isin(labels, too_small)] = 0
            keep = [i for i in range(1, n + 1) if i not in set(too_small.tolist())]
            remap = np.zeros(n + 1, dtype=labels.dtype)
            for new, old in enumerate(keep, start=1):
                remap[old] = new
            labels = remap[labels]
            n = len(keep)
    return labels, int(n)
