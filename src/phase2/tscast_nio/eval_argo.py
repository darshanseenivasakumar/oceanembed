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

WHAT THE SCORER DECLINES TO SCORE, AND SAYS SO (audit 2026-09-06)
  * Below the training target's seafloor. `output.build_record` returns None wherever the GLORYS
    bundle has no water, yet every scorer compared the model's raw mu against Argo at exactly those
    depths: 93 of 12,829 comparisons on the shipped run (RMSE 1.614 there) plus one profile on a
    GLORYS land cell. `apply_seafloor_mask` removes them and COUNTS them, so the metric and the
    product finally agree on what a valid prediction is. `SCORING_PROTOCOL` names the convention in
    every artifact, because a 0.90 that declined 93 comparisons is a different claim from a 0.90
    that declined none. Every artifact written before 2026-09-07 is `unmasked_v1`.
  * Against a climatology that does not exist. `build_samples.py` drops any cell whose column has
    a NaN, so a cell shallower than 1000 m contributes no rows and `climatology.build_climatology`
    fills it with the basin-mean profile at EVERY depth. Skill against that fill is not skill
    against climatology -- it read +0.55 at the 67 shelf profiles and +0.15 at the 895 with a real
    baseline. `baseline_exists_mask` marks the profiles where the comparison is fair, and
    `metrics.per_depth(baseline_ok=...)` reports the skill on those beside the blended one.
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

#: Which comparisons the scorer declines to make. Stamped into every artifact beside the score.
SCORING_PROTOCOL = "seafloor_masked_v1"
#: What every artifact before 2026-09-07 was scored under: the model's raw output compared against
#: Argo at every depth the float sampled, including depths the product itself refuses to serve.
UNMASKED_PROTOCOL = "unmasked_v1"


def seafloor_mask(la, lo, valid_mask, land_mask) -> np.ndarray:
    """(N, 15) True where the training target has WATER at that profile's cell and depth.

    `valid_mask` is the bundle's static (lat, lon, depth) bathymetry -- True where GLORYS has a
    finite temperature at every time step -- and `land_mask` its (lat, lon) coastline. A land cell
    has no water at any depth, whatever the bathymetry array says.
    """
    la = np.asarray(la, dtype=int)
    lo = np.asarray(lo, dtype=int)
    water = np.asarray(valid_mask, dtype=bool)[la, lo, :]
    land = np.asarray(land_mask, dtype=bool)[la, lo]
    return water & ~land[:, None]


def apply_seafloor_mask(truth, la, lo, valid_mask, land_mask):
    """NaN the truth where the target has no water, and COUNT what was declined.

    Returns (masked_truth, refusals). Refusing silently would be the same defect from the other
    side, so the counts travel with the score. A level the float never reached is not a refusal --
    it was never a comparison -- so only finite truths that lose their water are counted.
    """
    truth = np.asarray(truth, dtype="float64")
    water = seafloor_mask(la, lo, valid_mask, land_mask)
    if water.shape != truth.shape:
        raise ValueError(f"water mask {water.shape} does not match truth {truth.shape}")
    refused = np.isfinite(truth) & ~water
    masked = np.where(water, truth, np.nan)
    on_land = np.asarray(land_mask, dtype=bool)[np.asarray(la, int), np.asarray(lo, int)]
    return masked, {
        "scoring_protocol": SCORING_PROTOCOL,
        "n_refused_below_seafloor": int(refused.sum()),
        "n_profiles_on_land": int(on_land.sum()),
        "per_depth_refused": refused.sum(axis=0).astype(int).tolist(),
        "why": ("comparisons at depths where the GLORYS target has no water are declined, because "
                "output.build_record refuses to serve a value there; scoring the model's raw output "
                "at those depths charged the product for numbers it never emits"),
    }


def baseline_exists_mask(la, lo, valid_mask, land_mask) -> np.ndarray:
    """(N,) True where the cell has a REAL climatology rather than the basin-mean fill.

    `oceanembed.features.build_samples` keeps a (date, cell) row only if all 15 depths are finite,
    so a cell whose column is dry anywhere contributes NO rows, and `climatology.build_climatology`
    then fills every one of its (month, depth) entries with that month's basin-mean profile. The
    fill is a plausible-looking column with no local information in it -- rule 8's failure inside
    the baseline. A cell has a real climatology exactly when the target has water at every depth,
    which is what this returns. (Bathymetry is static in these bundles: no cell's finiteness varies
    over time, verified on the shipped bundle, so the per-depth `valid_mask` is exact for this.)
    """
    la = np.asarray(la, dtype=int)
    lo = np.asarray(lo, dtype=int)
    full = np.asarray(valid_mask, dtype=bool)[la, lo, :].all(axis=-1)
    return full & ~np.asarray(land_mask, dtype=bool)[la, lo]


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
    """Match Argo profiles to test-window grid cells. Returns everything the caller needs.

    Returns (keys, truth, keep, t_idx, la, lo, refusals). `truth` is already seafloor-masked for
    the kept rows and `refusals` says how many comparisons that declined and why -- a caller that
    records the score must record the refusals beside it.
    """
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
    truth = np.asarray(truth, dtype="float64").copy()
    truth[keep], refusals = apply_seafloor_mask(truth[keep], la[keep], lo[keep],
                                                d["valid_mask"], d["land_mask"])
    if verbose:
        print(f"independent Argo in the test window: {int(keep.sum())} profiles "
              f"(median offset {int(np.median(offs.min(axis=1)[keep]))} d); "
              f"{refusals['n_refused_below_seafloor']} comparisons below the target's seafloor "
              f"declined, {refusals['n_profiles_on_land']} profile(s) on a land cell "
              f"[{SCORING_PROTOCOL}]")
    return keys, truth, keep, t_idx, la, lo, refusals


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
