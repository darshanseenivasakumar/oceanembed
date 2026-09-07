"""Patch sampler: gridded surface fields -> the per-sample tensors of tscast_data_model.md sec 4.

Runs unchanged on the monthly archive (T_SEQ=1) and on the daily bundle (T_SEQ=31). That is the
whole point -- the model is built and ranked now, and going daily is a config change.

Design notes that are not cosmetic:

  * Patches are cut from a grid padded with NaN, never wrapped. 45 E and 105 E are opposite sides
    of the basin, not neighbours; a wrapped patch would teach the model that Somalia predicts
    Sumatra.
  * Normalisation statistics come from the TRAIN split only. Using all-data statistics leaks the
    test distribution into training and inflates every score that follows.
  * NaN (land, off-grid, or a channel the product does not serve at that cell) becomes 0.0
    AFTER z-scoring, i.e. the channel mean. With `mask_channels=True` a companion per-channel
    presence mask is APPENDED to the input -- C extra channels, 1 where the value was observed,
    0 where it was filled -- so the encoder can tell a gap from average water. It is OFF by
    default: the shipped checkpoint was trained without it. Until 2026-09-07 (audit #13) the mask
    was computed here and thrown away while this docstring claimed it was recorded; on the shipped
    satellite bundle 5.5% of ocean cells are missing at least one channel on every day, and an
    ocean-centred 17x17 patch is 15% land on average, all of it fed in as the channel mean.
"""
from __future__ import annotations

import os

import numpy as np
import torch
from torch.utils.data import Dataset

from oceanembed import config as base
from oceanembed.utils import grids
from phase2.tscast_nio import config


def input_channels(channels, mask_channels: bool) -> int:
    """How many channels the encoder receives: the values, plus a presence mask per value when
    `mask_channels` is on. Every place that builds a TSCastNIO from a checkpoint must use this
    with the checkpoint's own `mask_channels`, never `len(channels)` alone."""
    return len(list(channels)) * (2 if mask_channels else 1)


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
                 stride=1, clim=None, return_clim=False, salinity=None, return_salinity=False,
                 mask_channels=False):
        self.C = surface.shape[-1]
        #: Append a per-channel presence mask to `x` (audit #13). Off by default; see the module
        #: docstring. `C_in` is what the encoder must be built for.
        self.mask_channels = bool(mask_channels)
        self.C_in = self.C * (2 if self.mask_channels else 1)
        self.T_SEQ = int(config.T_SEQ if t_seq is None else t_seq)
        if self.T_SEQ < 1 or self.T_SEQ % 2 == 0:
            # `_window` takes T_SEQ // 2 steps each side of the target, so an even value builds a
            # window ONE STEP LONGER than asked and every artifact then records the wrong T_SEQ.
            # Measured 2026-09-06: t_seq=10 produced an 11-step window with no error.
            raise ValueError(
                f"t_seq={self.T_SEQ} must be a positive odd number. The window is centred on the "
                f"target day, so t_seq={self.T_SEQ} would silently build "
                f"{2 * (self.T_SEQ // 2) + 1} steps, not {self.T_SEQ}.")
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
        if self.mask_channels:
            # 1 where the value above was observed, 0 where it is the fill. Appended, not
            # interleaved, so channel c's mask is channel C + c and the value block is unchanged.
            m = np.transpose(finite, (3, 0, 1, 2)).astype("float32")
            x = np.concatenate([x, m], axis=0)                            # (2C, T, P, P)

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
    prov = None
    for f in files:
        z = np.load(f, allow_pickle=True)
        if prov is None and "provenance" in z.files:
            import json as _json
            try:
                prov = _json.loads(str(z["provenance"]))
            except Exception:
                prov = {"raw": str(z["provenance"])}
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
    out["provenance"] = prov
    out["input_source"] = bundle_input_source(prov)
    return out


def bundle_input_source(prov) -> str:
    """What actually fed the encoder, read from the bundle rather than asserted.

    `inference.py` hardcoded `"input_source": "glorys"` as a string literal, and the training
    metrics carried no such field at all. Both were harmless while GLORYS was the only bundle, and
    became a false provenance claim the moment a satellite bundle existed: the shipped
    satellite-input model would have served every prediction labelled `glorys`.

    Returns "unknown" rather than guessing when the bundle says nothing. Callers that make a
    compliance claim on this must refuse "unknown"; silently defaulting to either source is how a
    label stops being evidence.
    """
    if not isinstance(prov, dict):
        return "unknown"
    if prov.get("input_source"):
        return str(prov["input_source"])
    # The GLORYS bundle predates the field and identifies itself in `source` instead.
    src = str(prov.get("source", "")).lower()
    if "glorys" in src or "reanalysis" in src:
        return "glorys"
    return "unknown"


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


def embargo_indices(t_indices, t_seq, forbidden_start):
    """Drop training targets whose T_SEQ input window would reach into the test block.

    THE BUG THIS EXISTS FOR
    `GriddedPatches._window` builds a window of `t_seq` steps centred on the target and clamps it
    to the ARRAY bounds [0, n_t-1] -- not to the split boundary. So a training target within
    `t_seq // 2` days of the first test day silently reads test-period SURFACE fields as input.
    Measured on the shipped daily bundle at T_SEQ=11: the last 5 training days (1.64% of targets,
    ~987 of 60,000 drawn samples) were affected.

    It was never caught because `test_monthly_train_and_test_target_indices_never_overlap` checked only target INDEX
    overlap, not window overlap -- and on the monthly split, not the daily one.

    WHY THIS IS SOLVED HERE AND NOT IN `_window`
    Clamping inside `_window` would silently shorten the window for boundary targets, so those
    samples would carry a different amount of temporal context than every other sample while
    still being trained on. Dropping the target is honest: it costs 5 of 304 days and every
    surviving sample sees exactly `t_seq` steps.

    The TEST indices are deliberately NOT embargoed. A test target reaching back into the train
    period is not leakage -- those observations genuinely exist before the forecast date, and
    withholding them would model an operational setting nobody runs.

    t_indices      : candidate target indices (the train split)
    t_seq          : window length; `t_seq <= 1` embargoes nothing
    forbidden_start: first index of the block that must not be read (the first test index).
                     None disables the embargo and returns the input unchanged.
    """
    t_indices = np.asarray(t_indices)
    if forbidden_start is None or int(t_seq) <= 1:
        return t_indices
    h = int(t_seq) // 2
    return t_indices[t_indices + h < int(forbidden_start)]


SELECTION_PROTOCOL = "val_carved_v1"
LEGACY_SELECTION_PROTOCOL = "test_period_v0"
VAL_FRACTION = 0.15
MIN_VAL_STEPS = 3


def selection_split(times, t_indices, te_t, t_seq, val_days=None, n_blocks=1):
    """Carve the model-selection set out of the END of the TRAIN block, never from the test block.

    THE BUG THIS EXISTS FOR
    `train_stage1` used to build its early-stopping loader from `te_t` -- the GLORYS test period --
    and keep the epoch with the lowest NLL on it. The Argo headline is then scored on that same
    period, so the epoch that shipped was the one that best fit the block being scored. The
    embargo already stopped training INPUTS from reaching the test block; nothing stopped the
    SELECTION SIGNAL from being computed on it. Runs before this function are recorded as
    `LEGACY_SELECTION_PROTOCOL` and their epoch choice is not independent of their headline.

    WHAT THIS DOES INSTEAD
    The last `val_days` steps of the train block become the validation set. Chronological, never
    random: adjacent days share input frames through the T_SEQ window, so a random split would put
    a target's own neighbours on both sides of the split and report an optimistic number.

    TWO EMBARGOES, NOT ONE
      train -> val : a training target within `t_seq // 2` of the val block reads val surface
                     fields as input, which flatters the selection signal. Dropped.
      val   -> test: a validation target within `t_seq // 2` of the first test day reads TEST
                     surface fields. That is harmless for a TEST target -- those observations
                     genuinely precede the forecast date, see `embargo_indices` -- but not for a
                     SELECTION target, because it is the leak this function exists to remove.
                     Dropped.
    The train -> test embargo then comes for free: val sits between them, so a training target
    that cannot reach val cannot reach test either. Asserted below rather than assumed.

    times     : the bundle's time axis, one entry per step
    t_indices : the train split, before any carving
    te_t      : the test split, used only for its FIRST index
    t_seq     : window length; <= 1 embargoes nothing
    val_days  : TOTAL train steps to reserve. None -> VAL_FRACTION of the train block, at least
                MIN_VAL_STEPS.
    n_blocks  : 1 (default) reserves them as one trailing block. Above 1 splits them into evenly
                spaced blocks running from the start of train to its end, which is what gives the
                selection signal seasonal coverage; every block is purged from the training set on
                BOTH sides, so the cost is val_days + 2 * n_blocks * (t_seq // 2) training steps.

    Returns (train_indices, val_indices, info). `info` goes verbatim into the run's metrics JSON,
    so a reader can tell the two protocols apart without rerunning anything.
    """
    t = np.asarray(times, dtype="datetime64[D]")
    tr = np.sort(np.asarray(t_indices))
    te = np.sort(np.asarray(te_t))
    h = int(t_seq) // 2 if int(t_seq) > 1 else 0

    n_val = int(val_days) if val_days else max(MIN_VAL_STEPS, round(len(tr) * VAL_FRACTION))
    n_blocks = int(n_blocks)
    if n_val < MIN_VAL_STEPS:
        raise SystemExit(f"--val-days {n_val} is below MIN_VAL_STEPS={MIN_VAL_STEPS}: a selection "
                         "signal that small is noise, and early stopping would follow it.")
    if n_val >= len(tr) - MIN_VAL_STEPS:
        raise SystemExit(f"--val-days {n_val} leaves {len(tr) - n_val} of {len(tr)} training "
                         "steps. Refusing: the run would be selecting on more data than it trains "
                         "on.")

    if n_blocks < 1:
        raise SystemExit(f"--val-blocks {n_blocks} makes no sense; it must be at least 1")
    if n_blocks == 1:
        blocks = [tr[-n_val:]]
    else:
        m = n_val // n_blocks
        if m < MIN_VAL_STEPS:
            raise SystemExit(f"{n_val} val steps over {n_blocks} blocks is {m} each, below "
                             f"MIN_VAL_STEPS={MIN_VAL_STEPS}. Raise --val-days or drop a block.")
        # Placed so the FIRST block starts at the start of train and the LAST ends at its end.
        # That is what buys the seasonal coverage: this bundle's train block opens in June, the
        # same season as the back half of the scored window, which no trailing block can reach.
        span = len(tr) - m
        starts = [round(i * span / (n_blocks - 1)) for i in range(n_blocks)]
        if any(b - a < m + 2 * h for a, b in zip(starts, starts[1:])):
            raise SystemExit(
                f"{n_blocks} blocks of {m} steps do not fit in {len(tr)} training steps with a "
                f"{h}-step purge on each side. Use fewer blocks or fewer --val-days.")
        blocks = [tr[s:s + m] for s in starts]
    va_all = np.sort(np.concatenate(blocks))

    # A training target is dropped if its window touches ANY val block or the test block. The
    # single-sided `embargo_indices` cannot express that, so the forbidden days are marked on the
    # time axis and every window is checked against them.
    forbidden = np.zeros(len(t), dtype=bool)
    forbidden[va_all] = True
    if len(te):
        forbidden[te] = True
    tr_rest = np.setdiff1d(tr, va_all)
    reaches = np.array([bool(forbidden[max(0, int(i) - h):int(i) + h + 1].any()) for i in tr_rest],
                       dtype=bool)
    tr_keep = tr_rest[~reaches]
    va_keep = embargo_indices(va_all, t_seq, int(te.min())) if len(te) else va_all

    if len(va_keep) < MIN_VAL_STEPS:
        raise SystemExit(f"the val block is {len(va_keep)} steps after its embargo against the "
                         f"test block (T_SEQ={t_seq} costs {h} steps). Raise --val-days.")
    if not len(tr_keep):
        raise SystemExit("the embargo against the val block left no training targets at all")

    assert not np.intersect1d(tr_keep, va_keep).size, "train and val target indices overlap"
    assert not np.intersect1d(va_keep, te).size, "val and test target indices overlap"
    assert not np.intersect1d(tr_keep, te).size, "train and test target indices overlap"
    va_set = set(va_all.tolist()) | (set(te.tolist()) if len(te) else set())
    for i in tr_keep:
        w = range(max(0, int(i) - h), int(i) + h + 1)
        assert not (set(w) & va_set), f"training target {int(i)} still reads a held-out day"
    if len(te):
        assert va_keep.max() + h < te.min(), "a validation window still reaches the test block"

    info = {
        "selection_protocol": SELECTION_PROTOCOL,
        "why": ("early stopping and the epoch choice read ONLY the val block, which is carved "
                "from the end of train. The test period is not touched until the final Argo "
                f"score. Runs recorded as {LEGACY_SELECTION_PROTOCOL} selected on the test "
                "period itself and their epoch choice is not independent of their headline."),
        "val_days_requested": int(n_val),
        "n_blocks": int(n_blocks),
        "blocks": [[str(t[b].min()), str(t[b].max())] for b in blocks],
        "val_months": sorted({int(str(x)[5:7]) for x in t[va_keep]}),
        "n_train_targets": int(len(tr_keep)),
        "n_val_targets": int(len(va_keep)),
        "n_train_dropped_embargo": int(len(tr_rest) - len(tr_keep)),
        "n_val_dropped_embargo": int(len(va_all) - len(va_keep)),
        "train_period": [str(t[tr_keep].min()), str(t[tr_keep].max())],
        "val_period": [str(t[va_keep].min()), str(t[va_keep].max())],
        "test_period": [str(t[te].min()), str(t[te].max())] if len(te) else None,
    }
    return tr_keep, va_keep, info


def split_indices(times, train_years=None, test_years=None):
    """Temporal holdout from the frozen config. Never a random split of adjacent cells."""
    yrs = np.array([int(str(t)[:4]) for t in times])
    tr = np.nonzero(np.isin(yrs, train_years or base.TRAIN_YEARS))[0]
    te = np.nonzero(np.isin(yrs, test_years or base.TEST_YEARS))[0]
    assert len(np.intersect1d(tr, te)) == 0, "train and test windows overlap"
    return tr, te


def bundle_for_checkpoint(ck: dict, checkpoint_path: str | None = None) -> tuple[str, str]:
    """WHICH bundle a checkpoint was trained on. Resolved from evidence, never defaulted silently.

    THE BUG THIS EXISTS FOR
    `inference.py` called `load_daily()` with no argument, which defaults to
    `data/processed/daily` -- the GLORYS bundle. The shipped model is trained on
    `data/processed/daily_sat/v001`. So the dashboard fed GLORYS reanalysis into a
    satellite-trained network and served the result as a prediction. Measured at 15N 68E on
    2026-05-15: 18.84 degC at 100 m against an independent float reading 26.85, an 8.01 degC error,
    while the same model on its own bundle gives 26.24 (error 0.61).

    Nothing caught it. The checkpoint records `data: "daily"` -- a CADENCE, not a path -- and the
    channel-order guard passes because both bundles carry the same seven channels in the same
    order. `calibrate_uncertainty.py` had the same call, so the per-depth sigma scales were fitted
    on errors the shipped model does not make.

    Returns (path, how_it_was_resolved). "defaulted" in the second slot means UNVERIFIED and the
    caller must say so in its provenance rather than presenting the bundle as confirmed.
    """
    if ck.get("daily_dir"):
        return str(ck["daily_dir"]), "recorded in the checkpoint"

    # Runs before 2026-09-02 recorded the path only in the sibling metrics artifact.
    if checkpoint_path:
        mp = checkpoint_path[:-3] + "_metrics.json" if checkpoint_path.endswith(".pt") else None
        if mp and os.path.exists(mp):
            try:
                import json as _json
                with open(mp, encoding="utf-8") as f:
                    dd = _json.load(f).get("daily_dir")
                if dd:
                    return str(dd), f"read from {os.path.basename(mp)}"
            except Exception:
                pass

    return os.path.join(base.DATA_PROCESSED, "daily"), "defaulted"


def assert_bundle_matches_checkpoint(bundle: dict, ck: dict, where: str = "") -> None:
    """Refuse a bundle whose input source is not the one the checkpoint was trained on.

    The channel-order check cannot see this: the GLORYS and satellite bundles carry identical
    channel names in identical order and differ only in what the numbers MEAN. This compares the
    thing that actually differs.
    """
    want = ck.get("input_source")
    if not want:
        return          # pre-2026-09-02 checkpoints do not record it; nothing to compare
    got = bundle.get("input_source", "unknown")
    if got != want:
        raise ValueError(
            f"input-source mismatch{' in ' + where if where else ''}: this checkpoint was trained "
            f"on {want!r} inputs and the loaded bundle is {got!r}. The channel names and order "
            f"match, so nothing else would have caught this -- and feeding the wrong source "
            f"produced an 8.01 degC error at 100 m the one time it happened. Pass the correct "
            f"bundle explicitly, or use dataset.bundle_for_checkpoint().")
