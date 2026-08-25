"""Shared plotting helpers for the Unit C panels.

OWNER: Unit C (Mitun+Niru).

Deliberately depends only on numpy + altair (altair ships with Streamlit). matplotlib and
plotly are in requirements.txt but are NOT guaranteed to be installed on a teammate's or a
demo machine, and a panel that ImportErrors on demo day is worse than a plainer chart.
"""
from __future__ import annotations

import numpy as np

# Viridis anchor points (perceptually uniform, colour-blind safe, prints legibly in greyscale).
_VIRIDIS = np.array([
    [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142],
    [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89],
    [180, 222, 44], [253, 231, 37],
], dtype="float32")

# Diverging blue -> white -> red, for anomalies where the SIGN carries the meaning.
_DIVERGING = np.array([
    [5, 48, 97], [33, 102, 172], [67, 147, 195], [146, 197, 222],
    [209, 229, 240], [247, 247, 247], [253, 219, 199], [244, 165, 130],
    [214, 96, 77], [178, 24, 43], [103, 0, 31],
], dtype="float32")

LAND_RGB = (38, 42, 48)  # dark grey, clearly not part of any colour scale


def _lut(anchors: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Linearly interpolate an anchor table at positions t in [0,1] -> (..., 3) uint8."""
    t = np.clip(np.nan_to_num(t, nan=0.0), 0.0, 1.0) * (len(anchors) - 1)
    lo = np.floor(t).astype(int)
    hi = np.minimum(lo + 1, len(anchors) - 1)
    frac = (t - lo)[..., None]
    return (anchors[lo] * (1 - frac) + anchors[hi] * frac).astype("uint8")


def colorize(grid: np.ndarray, land_mask: np.ndarray | None = None,
             diverging: bool = False, robust: bool = True) -> np.ndarray:
    """(H,W) float -> (H,W,3) uint8, north-up, land painted grey.

    robust=True clips to the 2nd-98th percentile so one outlier cell cannot flatten the basin.
    diverging=True centres the scale on zero, so an anomaly's sign is readable.
    """
    g = np.asarray(grid, dtype="float32")
    finite = np.isfinite(g)
    if not finite.any():
        return np.full((*g.shape, 3), LAND_RGB, dtype="uint8")

    if diverging:
        m = np.nanpercentile(np.abs(g[finite]), 98) if robust else np.nanmax(np.abs(g[finite]))
        m = max(float(m), 1e-6)
        t = (g + m) / (2 * m)
        rgb = _lut(_DIVERGING, t)
    else:
        lo, hi = (np.nanpercentile(g[finite], [2, 98]) if robust
                  else (np.nanmin(g[finite]), np.nanmax(g[finite])))
        hi = hi if hi > lo else lo + 1e-6
        rgb = _lut(_VIRIDIS, (g - lo) / (hi - lo))

    dead = ~finite
    if land_mask is not None:
        dead |= np.asarray(land_mask).astype(bool)
    rgb[dead] = LAND_RGB

    # Row 0 of the arrays is the SOUTHERNMOST latitude; images draw row 0 at the top.
    # Without this flip every map is upside-down -- easy to miss and embarrassing on stage.
    return np.flipud(rgb)


def value_range(grid: np.ndarray, robust: bool = True) -> tuple[float, float]:
    """The (lo, hi) actually used by colorize, so a caption can state the real scale."""
    g = np.asarray(grid, dtype="float32")
    finite = np.isfinite(g)
    if not finite.any():
        return (float("nan"), float("nan"))
    if robust:
        lo, hi = np.nanpercentile(g[finite], [2, 98])
    else:
        lo, hi = np.nanmin(g[finite]), np.nanmax(g[finite])
    return float(lo), float(hi)


def nearest_argo(argo_df, lat: float, lon: float, max_deg: float = 2.0):
    """Closest Argo profile to (lat, lon) within max_deg, as a depth-sorted DataFrame or None.

    Uses a plain degree distance -- fine at this scale for picking a nearest neighbour, and it
    is only ever used for display, never for a metric.
    """
    if argo_df is None or len(argo_df) == 0:
        return None
    if not {"lat", "lon"}.issubset(argo_df.columns):
        return None

    d = np.hypot(argo_df["lat"].to_numpy() - lat, argo_df["lon"].to_numpy() - lon)
    if float(d.min()) > max_deg:
        return None

    hit = argo_df.iloc[[int(np.argmin(d))]]
    same = argo_df[(argo_df["lat"] == float(hit["lat"].iloc[0]))
                   & (argo_df["lon"] == float(hit["lon"].iloc[0]))]
    return same.sort_values("depth_idx") if "depth_idx" in same.columns else same
