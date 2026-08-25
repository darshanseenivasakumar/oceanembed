"""Anomaly = reconstruction - climatology.

OWNER: Unit C (Mitun+Niru). Baseline period = TRAIN years climatology (see DECISIONS.md).

UNITS ARE SPLIT ON PURPOSE
--------------------------
`anomaly()` returns **degrees C**, matching `inference/predict.py`'s fallback definition and the
"anomaly (degC)" labels in the UI. `standardized_anomaly()` returns **sigma units** for
thresholding. They are separate functions rather than one function with a flag, because a single
entry point whose units depend on an argument is exactly how a degC number ends up plotted on a
sigma scale -- the same silent-unit failure recorded in DECISIONS.md D-014.

WHAT SIGMA WE CAN AND CANNOT COMPUTE  [IMPORTANT LIMITATION]
------------------------------------------------------------
A proper standardized anomaly divides by the INTERANNUAL standard deviation at each
(cell, depth, month) -- how much this place, this depth, this month actually varies year to year.
That needs the full training time series. All we are handed is the climatology MEAN,
`(12, 100, 240, 11)`, which contains no variability information at all.

So `standardized_anomaly()` normalises by the SPATIAL spread of the anomaly field at each depth:
"how unusual is this cell compared to the rest of the basin today". That is a real and useful
quantity, but it is NOT a climatological sigma and must not be described as one -- a cell can be
2 sigma spatially while being perfectly normal for that location in that month.

To get the real thing, Unit B would need to save a climatology STD array alongside the mean
(same shape). Requested in docs/HANDOFF.md.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config

# Threshold for flag_extremes(). 2.0 sigma is a deliberately conventional choice, not tuned to
# make our maps look interesting. State k wherever a count of "extreme" cells is reported.
DEFAULT_K = 2.0


def anomaly(pred_grid: np.ndarray, climatology: np.ndarray, month: int) -> np.ndarray:
    """pred_grid:(100,240,11), climatology:(12,100,240,11), month:1..12 -> anomaly (100,240,11) in degC.

    The shape assert is strict on purpose. `predict.py` currently calls this with a single
    profile reshaped to (1,1,11); that would broadcast against the whole basin and the caller's
    `[0,0]` would silently read the south-west corner instead of the queried point. Failing the
    assert makes it fall back to the correct per-point definition instead of returning a wrong
    number. See docs/HANDOFF.md.
    """
    pred_grid = np.asarray(pred_grid, dtype="float32")
    climatology = np.asarray(climatology, dtype="float32")

    assert pred_grid.shape == (config.N_LAT, config.N_LON, config.N_DEPTHS), (
        f"pred_grid must be ({config.N_LAT},{config.N_LON},{config.N_DEPTHS}), got {pred_grid.shape}"
    )
    assert climatology.shape == (12, config.N_LAT, config.N_LON, config.N_DEPTHS), (
        f"climatology must be (12,{config.N_LAT},{config.N_LON},{config.N_DEPTHS}), "
        f"got {climatology.shape}"
    )
    assert 1 <= int(month) <= 12, f"month must be 1..12, got {month}"

    return (pred_grid - climatology[int(month) - 1]).astype("float32")


def standardized_anomaly(pred_grid: np.ndarray, climatology: np.ndarray, month: int) -> np.ndarray:
    """Anomaly in SIGMA units, normalised per depth by the field's SPATIAL spread.

    Read as "unusual compared with the rest of the basin at this depth today" -- NOT as
    "unusual for this location at this time of year". See the module docstring.

    Land (NaN) stays NaN. A depth whose anomalies are all identical yields 0, not inf.
    """
    a = anomaly(pred_grid, climatology, month)

    # Per-depth spatial std over ocean cells only.
    sigma = np.nanstd(a.reshape(-1, a.shape[-1]), axis=0)
    sigma = np.where(np.isfinite(sigma) & (sigma > 1e-6), sigma, np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        z = a / sigma[None, None, :]

    # A degenerate depth (no spatial variation) carries no information -> 0, not inf/NaN,
    # so a downstream count of extremes is not silently corrupted.
    z = np.where(np.isfinite(z), z, np.where(np.isnan(a), np.nan, 0.0))
    return z.astype("float32")


def flag_extremes(pred_grid: np.ndarray, climatology: np.ndarray, month: int,
                  k: float = DEFAULT_K) -> np.ndarray:
    """Boolean (100,240,11): |standardized anomaly| >= k. Land is False, never True.

    k defaults to 2.0 sigma. Report k alongside any count -- "1,240 extreme cells" means nothing
    without it, and picking k after seeing the map is how a threshold becomes a story.
    """
    assert k > 0, f"k must be positive, got {k}"
    z = standardized_anomaly(pred_grid, climatology, month)
    return (np.abs(np.nan_to_num(z, nan=0.0)) >= float(k)) & np.isfinite(z)


def summarize(pred_grid: np.ndarray, climatology: np.ndarray, month: int,
              k: float = DEFAULT_K) -> dict:
    """Per-depth anomaly summary for the UI and for EXPERIMENT_LOG entries."""
    a = anomaly(pred_grid, climatology, month)
    z = standardized_anomaly(pred_grid, climatology, month)
    ext = flag_extremes(pred_grid, climatology, month, k=k)
    flat = a.reshape(-1, a.shape[-1])

    with np.errstate(invalid="ignore"):
        return dict(
            month=int(month),
            k=float(k),
            depths=list(config.DEPTHS),
            mean_anomaly_degC=[float(v) for v in np.nanmean(flat, axis=0)],
            max_abs_anomaly_degC=[float(v) for v in np.nanmax(np.abs(flat), axis=0)],
            spatial_sigma_degC=[float(v) for v in np.nanstd(flat, axis=0)],
            n_extreme=[int(v) for v in ext.reshape(-1, ext.shape[-1]).sum(axis=0)],
            n_ocean=[int(v) for v in np.isfinite(flat).sum(axis=0)],
            sigma_basis="spatial spread per depth (NOT climatological interannual sigma)",
        )
