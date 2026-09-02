"""Whole-field reconstruction from the v2 model: one date -> (100, 240, 15). (Unit A / Arjhun.)

WHY THIS EXISTS
`TSCastPredictor.reconstruct` answers one (lat, lon, date). Every derived product in this project
-- the 3-D cube, thermocline and mixed-layer depth, ocean heat content, eddy detection -- needs a
FIELD, and none of them had a way to get one from the v2 model. So they all read
`data/processed/grids.npz`: Phase-1 MONTHLY GLORYS, 2019-2022. The 3-D view and the physics pages
have been rendering a different model, on different data, from a different era, the whole time.
That is risk U4 from the 2026-09-01 forensic audit, unaddressed until now.

This module closes it. It is deliberately thin: it batches the SAME dataset, the SAME model and the
SAME denormalisation that `inference.py` uses for a single point, so a field value at a cell equals
the point value at that cell. If those two ever disagree, one of them is wrong and the test in
tests/phase2/test_field.py says so.

Cost: ~11.8k ocean cells per date, which is 24 batches of 512 -- seconds on the GPU, under a minute
on CPU. Cheap enough to do live in the dashboard for one date.
"""
from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import DataLoader

from oceanembed import config as base
from phase2.tscast_nio import config


def predict_field(predictor, date, batch_size: int = 512, device: str | None = None) -> dict:
    """Reconstruct every ocean cell for one date.

    Returns
        temperature (100, 240, 15) degC, NaN on land and below the seafloor
        sigma       (100, 240, 15) degC, the CALIBRATED sigma if the predictor carries scales
        valid_mask  (100, 240, 15) bool
        land_mask   (100, 240)     bool
        provenance  dict -- the same fields a point record carries, so a cube can be traced

    The predictor is used as-is. This function does not build a model, choose a bundle or apply a
    normalisation of its own: doing any of that would create a second definition of "the v2
    prediction", which is exactly the drift that produced an 8 degC error on the dashboard.
    """
    t_idx, days_off = predictor._time(date)
    land = np.asarray(predictor.data["land_mask"], bool)
    temp_truth = predictor.data["temp"][t_idx]                      # (100, 240, 15)
    ocean = ~land
    ii, jj = np.nonzero(ocean)

    ds = predictor.ds
    saved = ds.index
    try:
        ds.index = np.stack([np.full(ii.size, t_idx), ii, jj], axis=1)
        dev = torch.device(device) if device else next(predictor.model.parameters()).device
        mus, lvs = [], []
        predictor.model.eval()
        with torch.no_grad():
            for x, g, _, _, _, cp, mo in DataLoader(ds, batch_size=batch_size, shuffle=False):
                x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
                mu, lv = predictor.model(x, g, cp, mo)
                mus.append(mu.cpu().numpy())
                lvs.append(lv.cpu().numpy())
    finally:
        ds.index = saved                                            # never leave it mutated

    mu = np.concatenate(mus) * predictor.y_std + predictor.y_mean
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * predictor.y_std

    # The calibrated sigma, decided by the SAME function the point path uses.
    #
    # This first checked `cal.get("applied")`, which does not exist on the raw calibration JSON --
    # `applied` is a field `output.build_record` WRITES after asking `_calibration_applies_to`. So
    # the check was always False and the field silently carried raw sigma while the point record
    # beside it carried calibrated sigma, for the same cell, on the same screen. A second copy of a
    # decision is a second chance to get it wrong; there is now one copy.
    from phase2.tscast_nio import output as _output

    cal = getattr(predictor, "calibration", None)
    applied, why = False, "no calibration artifact loaded"
    if cal:
        applied, why = _output._calibration_applies_to(cal, {
            "T_SEQ": predictor.meta.get("T_SEQ"),
            "channels": [str(c) for c in predictor.data["channels"]]})
        if applied:
            for k, d in enumerate(config.DEPTHS):
                sc = cal["scales"].get(str(int(d))) or cal["scales"].get(int(d))
                if sc:
                    sigma[:, k] *= float(sc)

    shape = (len(base.LAT), len(base.LON), config.N_DEPTHS)
    T = np.full(shape, np.nan)
    S = np.full(shape, np.nan)
    T[ii, jj, :] = mu
    S[ii, jj, :] = sigma

    # Below the seafloor there is no ocean. The GLORYS target is NaN there, and a reconstruction
    # that filled it with a number would be inventing water.
    valid = np.isfinite(temp_truth) & ocean[:, :, None]
    T[~valid] = np.nan
    S[~valid] = np.nan

    return {
        "date": str(np.asarray(predictor.data["times"])[t_idx]),
        "temperature": T, "sigma": S, "valid_mask": valid, "land_mask": land,
        "provenance": {
            "model": "tscast-nio-stage1",
            "input_source": predictor.data.get("input_source", "unknown"),
            "bundle": predictor.meta.get("bundle"),
            "checkpoint": predictor.meta.get("promoted_from") or "unpromoted",
            "encoder": predictor.meta.get("encoder"),
            "seed": predictor.meta.get("seed"),
            "T_SEQ": predictor.meta.get("T_SEQ"),
            "days_from_requested": days_off,
            "sigma_is_calibrated": applied,
            "sigma_calibration_note": why,
            "n_cells": int(ii.size),
        },
    }
