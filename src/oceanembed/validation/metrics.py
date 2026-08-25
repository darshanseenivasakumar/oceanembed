"""Error metrics for reconstruction, reported relative to the climatology baseline.

OWNER: Unit C (Mitun+Niru).

READ BEFORE QUOTING R-SQUARED
-----------------------------
`r2` is POOLED across all depths, so its denominator is dominated by the vertical temperature
gradient (~28 degC at the surface to ~9 degC at 500 m). Simply knowing that water gets colder
with depth already explains most of that variance, so pooled R2 sits on a very high floor:

    [VERIFIED on realistic synthetic profiles]
      predictor                      pooled R2     per-depth R2
      climatology (mean profile)       +0.9538        0.0000
      one global mean everywhere       +0.0000      -78.5937

Climatology scoring +0.95 is the tell. A reported "R2 = 0.999" therefore sounds near-perfect while
the useful skill is only the gap above ~0.95 -- and a judge will read the absolute number.

**Quote `r2_by_depth` (or `skill_vs_clim`), not `r2`.** `r2_by_depth` measures each depth against
that depth's OWN mean, so climatology scores 0.0 by construction and any positive value is real
skill. `r2` is retained only so existing callers keep working.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_clim: np.ndarray | None = None) -> dict:
    """y_true,y_pred:(N,11) -> metrics dict. NaN-safe.

    Returns
    -------
    rmse, mae        : float, pooled over all depths
    rmse_by_depth    : list[11]
    r2               : float, POOLED -- inflated, see module docstring. Kept for compatibility.
    r2_by_depth      : list[11], each depth vs its OWN mean. THIS is the honest one.
    skill_vs_clim    : float | None -- 1 - RMSE_pred/RMSE_clim. >0 means better than climatology.
    """
    y_true = np.asarray(y_true, dtype="float64")
    y_pred = np.asarray(y_pred, dtype="float64")
    assert y_true.shape == y_pred.shape and y_true.shape[1] == config.N_DEPTHS, "shapes must be (N,11)"

    err = y_pred - y_true
    rmse = float(np.sqrt(np.nanmean(err ** 2)))
    mae = float(np.nanmean(np.abs(err)))
    rmse_by_depth = np.sqrt(np.nanmean(err ** 2, axis=0)).astype(float).tolist()

    # Pooled R2 -- kept for backward compatibility. Inflated; see docstring.
    ss_res = np.nansum(err ** 2)
    ss_tot = np.nansum((y_true - np.nanmean(y_true)) ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    # Honest R2: each depth against its own mean, so climatology scores exactly 0.
    res_d = np.nansum(err ** 2, axis=0)
    tot_d = np.nansum((y_true - np.nanmean(y_true, axis=0)) ** 2, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r2_by_depth = np.where(tot_d > 0, 1.0 - res_d / tot_d, np.nan)

    skill = None
    if y_clim is not None:
        y_clim = np.asarray(y_clim, dtype="float64")
        # Without this assert a mis-shaped baseline broadcasts silently and skill_vs_clim is wrong.
        assert y_clim.shape == y_true.shape, (
            f"y_clim must be {y_true.shape}, got {y_clim.shape}"
        )
        rmse_clim = float(np.sqrt(np.nanmean((y_clim - y_true) ** 2)))
        skill = float(1.0 - rmse / rmse_clim) if rmse_clim > 0 else None

    return dict(
        rmse=rmse,
        mae=mae,
        r2=r2,
        r2_by_depth=[float(v) for v in r2_by_depth],
        rmse_by_depth=rmse_by_depth,
        skill_vs_clim=skill,
    )
