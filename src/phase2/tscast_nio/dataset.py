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

import numpy as np
import torch
from torch.utils.data import Dataset

from oceanembed import config as base
from phase2.tscast_nio import config


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
                 stride=1):
        self.C = surface.shape[-1]
        self.T_SEQ = int(config.T_SEQ if t_seq is None else t_seq)
        self.P = int(config.P if p is None else p)
        self.half = self.P // 2
        self.channels = list(channels)
        self.times = times
        self.temp = temp
        self.n_t = surface.shape[0]

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
        else:
            self.mean, self.std, self.y_mean, self.y_std = norm

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
        return (self.mean, self.std, self.y_mean, self.y_std)

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

        return (torch.from_numpy(x), torch.from_numpy(x_geo),
                torch.from_numpy(y_z), torch.from_numpy(y_valid),
                torch.tensor([lat, lon], dtype=torch.float32))


def load_monthly(path=None):
    """The existing 48-month archive, in the shape the sampler wants. 5 channels: no wind yet."""
    import os
    path = path or os.path.join(base.DATA_PROCESSED, "grids.npz")
    g = np.load(path, allow_pickle=True)
    chans = ["sst", "sss", "ssh", "u", "v"]
    surface = np.stack([g[c] for c in chans], axis=-1).astype("float32")
    return dict(surface=surface, temp=g["temp"].astype("float32"), times=g["times"],
                land_mask=g["land_mask"], valid_mask=g["valid_mask"], channels=chans)


def split_indices(times, train_years=None, test_years=None):
    """Temporal holdout from the frozen config. Never a random split of adjacent cells."""
    yrs = np.array([int(str(t)[:4]) for t in times])
    tr = np.nonzero(np.isin(yrs, train_years or base.TRAIN_YEARS))[0]
    te = np.nonzero(np.isin(yrs, test_years or base.TEST_YEARS))[0]
    assert len(np.intersect1d(tr, te)) == 0, "train and test windows overlap"
    return tr, te
