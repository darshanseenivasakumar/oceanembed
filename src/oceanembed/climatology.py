"""Climatology baseline: monthly-mean temperature per cell/depth over the TRAIN years.

OWNER: Unit C (Mitun+Niru). Mandatory baseline (every model scored vs this) + anomaly reference.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from oceanembed import config
from oceanembed.utils import io, grids


def build_climatology(y_train: np.ndarray, meta_train: pd.DataFrame, save: bool = True) -> np.ndarray:
    """y_train:(N,15) + meta_train[month,cell_id] -> (12,100,240,15). Empty cells filled by monthly-global mean."""
    assert y_train.shape[1] == config.N_DEPTHS, "y_train must be (N,15)"
    shape = (12, config.N_LAT, config.N_LON, config.N_DEPTHS)
    ssum = np.zeros(shape, dtype="float64")
    cnt = np.zeros((12, config.N_LAT, config.N_LON), dtype="int64")

    months = meta_train["month"].to_numpy().astype(int) - 1
    cells = meta_train["cell_id"].to_numpy().astype(int)
    ii, jj = np.divmod(cells, config.N_LON)
    np.add.at(ssum, (months, ii, jj), y_train.astype("float64"))
    np.add.at(cnt, (months, ii, jj), 1)

    clim = np.full(shape, np.nan, dtype="float32")
    nz = cnt > 0
    clim[nz] = (ssum[nz] / cnt[nz][:, None]).astype("float32")

    # Fill empty (month,cell) with that month's global-ocean mean profile; if a month has NO data at all
    # (possible with sparse/subsampled input), fall back to the all-month mean.
    global_mean = np.nanmean(clim.reshape(-1, config.N_DEPTHS), axis=0)
    for m in range(12):
        if nz[m].any():
            month_mean = np.nanmean(clim[m].reshape(-1, config.N_DEPTHS), axis=0)
        else:
            month_mean = global_mean
        clim[m][~nz[m]] = month_mean

    if save:
        io.save_npy(clim, config.art("climatology.npy"))
    return clim


def climatology_predict(meta: pd.DataFrame, clim: np.ndarray | None = None) -> np.ndarray:
    """Look up climatology at each row's (month, cell) -> (N,15)."""
    if clim is None:
        clim = io.load_npy(config.art("climatology.npy"))
    months = meta["month"].to_numpy().astype(int) - 1
    cells = meta["cell_id"].to_numpy().astype(int)
    ii, jj = np.divmod(cells, config.N_LON)
    return clim[months, ii, jj].astype("float32")
