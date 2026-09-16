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


def compute_profile(ctx: "WhatIfContext", inputs: dict) -> dict:
    """Rebuild the 11-feature raw vector, override the 5 surface entries, run MC-dropout.

    Uses predict.py's own lookups so the layout is identical to _features_at; only the
    first 5 entries change. Mirrors reconstruct()'s seed order and below-seafloor blanking.
    """
    import torch as _t
    from oceanembed.inference.uncertainty import mc_dropout_predict

    if ctx.is_land or ctx.surface is None:
        return {"available": False, "reason": "point is land / no data",
                "depths": list(config.DEPTHS)}

    model = P._model()                      # load BEFORE seeding (see reconstruct() for why)
    _t.manual_seed(config.SEED)

    xraw = P._features_at(ctx.i, ctx.j, ctx.t)[None, :].copy()
    for idx, name in enumerate(("sst", "sss", "ssh", "u", "v")):
        xraw[0, idx] = float(inputs[name])

    mean, std = mc_dropout_predict(model, xraw)
    mean, std = mean[0], std[0]

    vm = P._valid_mask()
    if vm is not None:
        below = ~vm[ctx.i, ctx.j]
        mean = np.where(below, np.nan, mean)
        std = np.where(below, np.nan, std)

    clim = ctx.climatology_profile
    point_anom = (mean - clim).astype("float32") if clim is not None else None

    return {
        "available": True,
        "depths": list(config.DEPTHS),
        "profile_mean": [float(x) for x in mean],
        "profile_std": [float(x) for x in std],
        "point_anomaly": None if point_anom is None else [float(x) for x in point_anom],
        "surface_used": {k: float(inputs[k]) for k in ("sst", "sss", "ssh", "u", "v")},
    }


def compute_anomaly_extremes(ctx: "WhatIfContext", inputs: dict) -> dict:
    """standardized_anomaly (k-independent context) + flag_extremes at threshold k, basin-wide.

    Called as-is on the cached basin grid; the picked point is read out for the side-by-side.
    """
    from oceanembed.products.anomaly import standardized_anomaly, flag_extremes

    g = ctx.grid()
    clim = g["clim"]
    if clim is None:
        return {"available": False, "reason": "climatology.npy missing",
                "depths": list(config.DEPTHS)}

    k = float(inputs["k"])
    temp = g["temp"]
    z = standardized_anomaly(temp, clim, ctx.month)          # (100,240,15)
    ext = flag_extremes(temp, clim, ctx.month, k=k)          # (100,240,15) bool
    ocean = np.isfinite(z)

    return {
        "available": True,
        "k": k,
        "depths": list(config.DEPTHS),
        "point_standardized_anomaly": [float(x) for x in z[ctx.i, ctx.j, :]],
        "point_is_extreme": [bool(x) for x in ext[ctx.i, ctx.j, :]],
        "n_extreme_by_depth": [int(v) for v in ext.reshape(-1, ext.shape[-1]).sum(0)],
        "n_ocean_by_depth": [int(v) for v in ocean.reshape(-1, ocean.shape[-1]).sum(0)],
        "grid_standardized_anomaly": z,
        "grid_is_extreme": ext,
    }


def compute_observation_priority(ctx: "WhatIfContext", inputs: dict) -> dict:
    """observation_priority() on the cached basin factors, with overridden weights/robust."""
    from oceanembed.products.observation_priority import observation_priority

    g = ctx.grid()
    w = (float(inputs["w_anomaly"]), float(inputs["w_uncertainty"]), float(inputs["w_sparsity"]))
    robust = bool(inputs["robust"])

    with warnings.catch_warnings():                 # degenerate/land factors warn by design
        warnings.simplefilter("ignore", RuntimeWarning)
        prio = observation_priority(g["a2d"], g["u2d"], g["sparsity"], weights=w, robust=robust)

    pv = prio[ctx.i, ctx.j]
    finite = prio[np.isfinite(prio)]
    return {
        "available": True,
        "weights": list(w),
        "robust": robust,
        "point_priority": float(pv) if np.isfinite(pv) else None,
        "basin_max": float(finite.max()) if finite.size else None,
        "basin_mean": float(finite.mean()) if finite.size else None,
        "valid_cells": int(finite.size),
        "grid_priority": prio,
    }
