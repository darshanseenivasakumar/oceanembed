"""ONE evaluation path against independent Argo, shared by training and by any later scorer.

WHY THIS MODULE EXISTS
`train_stage1.py` scored every run inline. When `scripts/phase2/score_by_basin.py` needed the same
predictions split by basin, it REIMPLEMENTED that block -- and produced 0.9297 for a checkpoint
whose own metrics say 0.9078. Same checkpoint, same 962 profiles, same n=12,829, different
predictions. The per-depth values were off in BOTH directions, so it was not an offset: it was a
different evaluation.

That is the producer/consumer drift that blanked the dashboard, appearing again in evaluation code,
where it is far more dangerous -- a basin split that cannot reproduce its own overall RMSE is not
evidence, and nothing would have flagged it. So there is now exactly one implementation, and the
test for it is that it reproduces a run's recorded numbers from that run's own checkpoint.

Anything that needs model-vs-Argo predictions imports `predict_at_argo` and does NOT rewrite it.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import dataset as D

MAX_DAYS = 5


def load_argo_table(data: str = "daily"):
    """The Argo set matching the bundle's period. Refuses the mismatched one loudly."""
    if data != "daily":
        return VA.load_argo()
    path = base.art("argo_daily_period.parquet")
    if not os.path.exists(path):
        raise SystemExit(
            f"--data daily needs {path}. artifacts/argo_test.parquet is 2022 only and would match "
            f"zero profiles in the 2026 test window. Run "
            f"scripts/phase2/fetch_argo_daily_period.py first.")
    return pd.read_parquet(path)


def collocate(d, te_t, data: str = "daily", verbose: bool = True):
    """Match Argo profiles to test-window grid cells. Returns everything the caller needs."""
    keys, truth = VA.pivot_profiles(load_argo_table(data))
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)

    if int(keep.sum()) == 0:
        raise SystemExit(
            f"NO Argo profile falls within +/-{MAX_DAYS} days of the test window "
            f"({str(all_times[te_t].min())}..{str(all_times[te_t].max())}). The Argo set spans "
            f"{keys['date'].min()}..{keys['date'].max()}. Scoring is impossible; refusing to "
            f"report metrics computed on zero profiles.")
    if verbose:
        print(f"independent Argo in the test window: {int(keep.sum())} profiles "
              f"(median offset {int(np.median(offs.min(axis=1)[keep]))} d)")
    return keys, truth, keep, t_idx, la, lo


def predict_at_argo(model, ds_te, keys, truth, keep, t_idx, la, lo, clim, dev):
    """Run the model at the collocated cells and return (mu, sigma, truth_kept, clim_at_kept).

    `ds_te.index` is REPLACED with the Argo cells -- exactly what training does. The dataset is
    otherwise untouched, so normalisation, patch geometry and the climatology prior are whatever
    that dataset was built with.
    """
    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus, lvs = [], []
    model.eval()
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            mu, lv = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
            lvs.append(lv.cpu().numpy())
    mu = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean          # back to degC
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * ds_te.y_std     # sigma scales with y_std
    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    return mu, sigma, truth[keep], clim_at[keep]
