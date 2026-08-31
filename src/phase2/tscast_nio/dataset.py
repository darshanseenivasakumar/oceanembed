"""Patch sampler: gridded surface fields -> the per-sample tensors of tscast_data_model.md sec 4.

Runs unchanged on the monthly archive (T_SEQ=1) and on the daily bundle (T_SEQ=31). That is the
whole point -- the model is built and ranked now, and going daily is a config change.

Design notes that are not cosmetic:

  * Patches are cut from a grid padded with NaN, never wrapped. 45 E and 105 E are opposite sides
    of the basin, not neighbours; a wrapped patch would teach the model that Somalia predicts
    Sumatra.
  * Normalisation statistics come from the TRAIN split only. Using all-data statistics leaks the
    test distribution into training and inflates every score that follows.
  * NaN (land, or off-grid) becomes 0.0 AFTER z-scoring, i.e. the channel mean, and a companion
    `finite` mask records where that happened so a model can learn to distrust those cells.
"""
from __future__ import annotations

import os

import numpy as np
import torch
from torch.utils.data import Dataset

from oceanembed import config as base
from oceanembed.utils import grids
from phase2.tscast_nio import config


def cell_index(lat, lon):
    """Grid cell for a position -- delegating to the FROZEN helpers, never reimplemented.

    `np.searchsorted(LAT, lat) - 1` looks equivalent and is not: it takes the cell BELOW whenever
    the coordinate lands on a grid line, and it snaps to the lower edge rather than the nearest
    centre. Measured against the real Argo set, the two conventions disagree on 75.5% of profiles
    by one cell (~28 km). The frozen pipeline (predict.py, glorys_vs_argo.py) uses nearest-centre,
    so everything here must too, or our numbers are not comparable to the published ones.
    """
    lat = np.atleast_1d(np.asarray(lat, dtype="float64"))
    lon = np.atleast_1d(np.asarray(lon, dtype="float64"))
    i = np.array([grids.nearest_lat_index(float(v)) for v in lat])
    j = np.array([grids.nearest_lon_index(float(v)) for v in lon])
    return i, j

def geo_encoding(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    """Paper eq. 1 (Sinha & Abernathey 2021). Returns (..., 3): X, Y, Z."""
    phi, lam = np.deg2rad(lat_deg), np.deg2rad(lon_deg)
    return np.stack([np.sin(phi),
                     np.sin(lam) * np.cos(phi),
                     -np.cos(lam) * np.cos(phi)], axis=-1)


class GriddedPatches(Dataset):
    """One sample = a (C, T_SEQ, P, P) patch + geo encoding -> (15,) temperature profile."""

    def __init__(self, surface, temp, times, land_mask, channels,
                 t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None,
                 stride=1, clim=None, return_clim=False, salinity=None, return_salinity=False):
        self.C = surface.shape[-1]
        self.T_SEQ = int(config.T_SEQ if t_seq is None else t_seq)
        self.P = int(config.P if p is None else p)
        self.half = self.P // 2
        self.channels = list(channels)
        self.times = times
        self.temp = temp
        self.n_t = surface.shape[0]
        # (12, n_lat, n_lon, 15) monthly climatology -- the physical prior the decoder adjusts.
        # MUST be built from training years only; see tscast_data_model.md section 3.
        # return_clim is OPT-IN so the 5-tuple every existing consumer unpacks is unchanged.
        self.clim = clim
        self.return_clim = bool(return_clim)
        if self.return_clim and clim is None:
            raise ValueError('return_clim=True needs a climatology array; refusing to '
                             'fabricate a zero prior')
        # Stage-2 target. OPT-IN for the same reason as return_clim: every stage-1 consumer
        # unpacks a fixed-length tuple, so the default must leave that tuple untouched.
        self.salinity = salinity
        self.return_salinity = bool(return_salinity)
        if self.return_salinity and salinity is None:
            raise ValueError("return_salinity=True needs a salinity array; refusing to train a "
                             "salinity head against a fabricated target")
        self.month = np.array([int(str(t)[5:7]) - 1 for t in times])

        # pad space with NaN so an edge patch is explicitly "missing", not fabricated
        self.surface = np.pad(
            surface, ((0, 0), (self.half, self.half), (self.half, self.half), (0, 0)),
            mode="constant", constant_values=np.nan).astype("float32")

        # normalisation from TRAIN indices only
        if norm is None:
            tr = surface[t_indices]
            self.mean = np.nanmean(tr, axis=(0, 1, 2)).astype("float32")
            self.std = np.nanstd(tr, axis=(0, 1, 2)).astype("float32")
            self.std[self.std < 1e-6] = 1.0
            self.y_mean = np.nanmean(temp[t_indices], axis=(0, 1, 2)).astype("float32")
            self.y_std = np.nanstd(temp[t_indices], axis=(0, 1, 2)).astype("float32")
            self.y_std[self.y_std < 1e-6] = 1.0
            # Salinity stats, TRAIN indices only -- same rule as temperature. Computed whenever a
            # salinity array is present so the stats travel with the checkpoint even if this
            # particular dataset is not returning salinity.
            if salinity is not None:
                self.s_mean = np.nanmean(salinity[t_indices], axis=(0, 1, 2)).astype("float32")
                self.s_std = np.nanstd(salinity[t_indices], axis=(0, 1, 2)).astype("float32")
                self.s_std[self.s_std < 1e-6] = 1.0
            else:
                self.s_mean = self.s_std = None
        elif len(norm) == 6:
            self.mean, self.std, self.y_mean, self.y_std, self.s_mean, self.s_std = norm
        elif len(norm) == 4:
            # A stage-1 checkpoint's norm. Accepted so stage-1 models keep loading unchanged.
            self.mean, self.std, self.y_mean, self.y_std = norm
            self.s_mean = self.s_std = None
        else:
            raise ValueError(f"norm must have 4 (stage 1) or 6 (stage 2) entries, got {len(norm)}")
        if self.return_salinity and self.s_mean is None:
            raise ValueError(
                "return_salinity=True but no salinity normalisation is available: the `norm` "
                "passed in is a 4-entry stage-1 tuple and no salinity array was given to derive "
                "one from. Z-scoring salinity with temperature's statistics would be a silent "
                "20x error of exactly the D-014 kind.")

        # valid sample positions: ocean, and a finite target at the surface level
        ok = (~land_mask)[None, :, :] & np.isfinite(temp[:, :, :, 0])
        ok = ok[t_indices]
        tt, ii, jj = np.nonzero(ok)
        idx = np.stack([np.asarray(t_indices)[tt], ii, jj], axis=1)
        if stride > 1:
            idx = idx[::stride]
        if max_samples is not None and len(idx) > max_samples:
            rng = np.random.default_rng(base.SEED if seed is None else seed)
            idx = idx[rng.choice(len(idx), max_samples, replace=False)]
        self.index = idx

    @property
    def norm(self):
        """4 entries at stage 1, 6 when salinity statistics exist. Length says which."""
        if self.s_mean is None:
            return (self.mean, self.std, self.y_mean, self.y_std)
        return (self.mean, self.std, self.y_mean, self.y_std, self.s_mean, self.s_std)

    def __len__(self):
        return len(self.index)

    def _window(self, t: int) -> list[int]:
        """T_SEQ time steps centred on t, clamped at the ends (never wrapped across years)."""
        if self.T_SEQ == 1:
            return [t]
        h = self.T_SEQ // 2
        return [int(np.clip(k, 0, self.n_t - 1)) for k in range(t - h, t + h + 1)]

    def __getitem__(self, k: int):
        t, i, j = (int(v) for v in self.index[k])
        w = self._window(t)
        # padded grid: cell (i,j) sits at (i+half, j+half); slice is [i : i+P]
        patch = self.surface[w, i:i + self.P, j:j + self.P, :]       # (T, P, P, C)
        patch = (patch - self.mean) / self.std
        finite = np.isfinite(patch)
        patch = np.where(finite, patch, 0.0)
        x = np.transpose(patch, (3, 0, 1, 2)).astype("float32")      # (C, T, P, P)

        lat = base.LAT[i]
        lon = base.LON[j]
        g = geo_encoding(np.float64(lat), np.float64(lon)).astype("float32")
        x_geo = np.broadcast_to(g[:, None, None, None], (3, 1, self.P, self.P)).astype("float32")

        y = self.temp[t, i, j, :].astype("float32")
        y_valid = np.isfinite(y)
        y_z = np.where(y_valid, (y - self.y_mean) / self.y_std, 0.0).astype("float32")

        sample = (torch.from_numpy(x), torch.from_numpy(x_geo),
                torch.from_numpy(y_z), torch.from_numpy(y_valid),
                torch.tensor([lat, lon], dtype=torch.float32))
        if not self.return_clim:
            return sample

        cp = self.clim[:, i, j, :].astype("float32")              # (12, 15): all 12 months
        cp_z = np.where(np.isfinite(cp), (cp - self.y_mean) / self.y_std, 0.0).astype("float32")
        sample = sample + (torch.from_numpy(cp_z), torch.tensor(int(self.month[t])))
        if not self.return_salinity:
            return sample

        sal = self.salinity[t, i, j, :].astype("float32")
        s_valid = np.isfinite(sal)
        s_z = np.where(s_valid, (sal - self.s_mean) / self.s_std, 0.0).astype("float32")
        return sample + (torch.from_numpy(s_z), torch.from_numpy(s_valid))


def load_monthly(path=None):
    """The existing 48-month archive, in the shape the sampler wants. 5 channels: no wind yet."""
    import os
    path = path or os.path.join(base.DATA_PROCESSED, "grids.npz")
    g = np.load(path, allow_pickle=True)
    chans = ["sst", "sss", "ssh", "u", "v"]
    surface = np.stack([g[c] for c in chans], axis=-1).astype("float32")
    return dict(surface=surface, temp=g["temp"].astype("float32"), times=g["times"],
                land_mask=g["land_mask"], valid_mask=g["valid_mask"], channels=chans)


def load_daily(d=None):
    """The 388-day bundle built by phase2.tscast_nio.daily_pipeline.

    Same dict shape as load_monthly(), so every consumer -- sampler, trainer, ablation -- works
    unchanged. That is the whole point of the T_SEQ/P contract: going daily is a data swap and a
    config flip, not a rewrite.
    """
    import glob as _glob
    d = d or os.path.join(base.DATA_PROCESSED, "daily")
    files = sorted(_glob.glob(os.path.join(d, "*.npz")))
    if not files:
        raise FileNotFoundError(f"no daily bundle in {d}; run phase2.tscast_nio.daily_pipeline")
    times, surface, temp, sal = [], [], [], []
    land = valid = chans = None
    for f in files:
        z = np.load(f, allow_pickle=True)
        times.append(z["times"]); surface.append(z["surface"]); temp.append(z["temp"])
        if "salinity" in z.files:
            sal.append(z["salinity"])
        land = z["land_mask"] if land is None else land
        valid = z["valid_mask"] if valid is None else valid
        chans = list(z["channels"]) if chans is None else chans
    times = np.concatenate(times)
    order = np.argsort(times)
    out = dict(surface=np.concatenate(surface)[order], temp=np.concatenate(temp)[order],
               times=times[order], land_mask=land, valid_mask=valid, channels=chans)
    if sal:
        out["salinity"] = np.concatenate(sal)[order]
    return out


# The daily split, from the v2 brief. Temporal holdout, and asserted disjoint below.
DAILY_TRAIN = (np.datetime64("2025-06-01"), np.datetime64("2026-03-31"))
DAILY_TEST = (np.datetime64("2026-04-01"), np.datetime64("2026-06-23"))


def daily_split_indices(times):
    """Train / test indices for the daily bundle. Test comes strictly AFTER train."""
    t = np.asarray(times, dtype="datetime64[D]")
    tr = np.nonzero((t >= DAILY_TRAIN[0]) & (t <= DAILY_TRAIN[1]))[0]
    te = np.nonzero((t >= DAILY_TEST[0]) & (t <= DAILY_TEST[1]))[0]
    assert len(np.intersect1d(tr, te)) == 0, "daily train and test windows overlap"
    assert t[tr].max() < t[te].min(), "test window must start after train ends: no future leakage"
    return tr, te


def split_indices(times, train_years=None, test_years=None):
    """Temporal holdout from the frozen config. Never a random split of adjacent cells."""
    yrs = np.array([int(str(t)[:4]) for t in times])
    tr = np.nonzero(np.isin(yrs, train_years or base.TRAIN_YEARS))[0]
    te = np.nonzero(np.isin(yrs, test_years or base.TEST_YEARS))[0]
    assert len(np.intersect1d(tr, te)) == 0, "train and test windows overlap"
    return tr, te
