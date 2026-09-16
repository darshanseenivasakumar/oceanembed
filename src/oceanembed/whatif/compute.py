"""Baseline extraction + the cached basin grid + the formula handlers.

Everything here IMPORTS and CALLS the real model/anomaly/priority code with
different inputs; it never re-implements their maths. torch and the product
functions are imported lazily inside the handlers so importing this module is cheap.
"""
from __future__ import annotations

import functools
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from oceanembed import config
from oceanembed.inference import predict as P
from oceanembed.utils import grids


@dataclass
class WhatIfContext:
    lat: float
    lon: float
    date: object
    source: str
    i: int
    j: int
    t: int
    month: int
    is_land: bool
    surface: dict | None
    profile_mean: object | None          # np.ndarray (15,) or None on land
    profile_std: object | None
    climatology_profile: object | None   # np.ndarray (15,) or None

    def grid(self) -> dict:
        return _baseline_grid(self.date, self.source)


def build_context(lat: float, lon: float, date, source: str) -> WhatIfContext:
    P.set_source(source)
    rec = P.reconstruct(lat, lon, date)         # the REAL baseline for this point
    i = grids.nearest_lat_index(lat)
    j = grids.nearest_lon_index(lon)
    t = P._nearest_time_index(rec["date"])
    g = P._grids()
    month = int(pd.Timestamp(g["times"][t]).month)
    return WhatIfContext(
        lat=float(config.LAT[i]), lon=float(config.LON[j]), date=rec["date"], source=source,
        i=int(i), j=int(j), t=int(t), month=month,
        is_land=bool(rec["is_land"]),
        surface=rec.get("surface"),
        profile_mean=rec.get("profile_mean"),
        profile_std=rec.get("profile_std"),
        climatology_profile=rec.get("climatology"),
    )


def _nanmean_axis2(vol, absolute: bool) -> np.ndarray:
    with warnings.catch_warnings():                 # all-NaN land columns are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        a = np.abs(vol) if absolute else vol
        return np.nanmean(a, axis=2)


@functools.lru_cache(maxsize=8)
def _baseline_grid(date, source) -> dict:
    """The real basin reconstruction + the derived 2-D factors the grid formulas read.

    Mirrors predict.reconstruct_grid()'s own a2d/u2d/sparsity + deep-enough masking so
    the what-if baseline matches the real priority panel. Cached per (date, source).
    """
    P.set_source(source)
    g = P.reconstruct_grid(date)                    # temp, uncertainty, anomaly, priority, land_mask
    clim = P._climatology()

    shape2d = (config.N_LAT, config.N_LON)
    a2d = _nanmean_axis2(g["anomaly"], absolute=True) if g["anomaly"] is not None \
        else np.full(shape2d, np.nan, dtype="float32")
    u2d = _nanmean_axis2(g["uncertainty"], absolute=False) if g["uncertainty"] is not None \
        else np.full(shape2d, np.nan, dtype="float32")
    sparsity = P._argo_sparsity()

    vm = P._valid_mask()
    if vm is not None:                              # rank only cells with water at every depth
        deep = vm[..., -1]
        a2d = np.where(deep, a2d, np.nan)
        u2d = np.where(deep, u2d, np.nan)
        sparsity = np.where(deep, sparsity, np.nan)

    return {"temp": g["temp"], "uncertainty": g["uncertainty"], "anomaly": g["anomaly"],
            "priority": g["priority"], "land_mask": g["land_mask"], "clim": clim,
            "a2d": a2d, "u2d": u2d, "sparsity": sparsity}
