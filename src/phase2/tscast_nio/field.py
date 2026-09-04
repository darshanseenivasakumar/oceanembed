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

import hashlib
import json
import os

import numpy as np
import torch
from torch.utils.data import DataLoader

from oceanembed import config as base
from phase2.tscast_nio import config


def _promoted_from(predictor) -> str:
    """Which run this checkpoint was promoted from -- or "unpromoted", decided by hash.

    `promote_run.py` writes `promoted_from` into the METRICS artifact, never into the checkpoint.
    So `predictor.meta.get("promoted_from")` was always None, and every provenance panel built on
    this field told the reader "unpromoted" about the shipped, promoted model -- a false claim in
    the one place a jury goes to check provenance.

    Reading the metrics file on its own would be the opposite error: it would pin the promotion
    onto whatever checkpoint happened to be loaded, including an experimental one. So the name is
    returned only when the loaded file's sha256 IS the one promotion recorded -- the same equality
    freeze.py checks -- and "unpromoted" otherwise.
    """
    path = getattr(predictor, "checkpoint_path", None)
    mp = base.art("tscast_stage1_metrics.json")
    if not path or not os.path.exists(path) or not os.path.exists(mp):
        return "unpromoted"
    try:
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if m.get("promoted_from") and m.get("checkpoint_sha256") == h.hexdigest():
            return str(m["promoted_from"])
    except Exception:            # a provenance lookup must never take down a reconstruction
        return "unpromoted"
    return "unpromoted"


def v2_cache_version() -> str:
    """Cache key for any Streamlit page that keys a resource/data cache on the shipped v2 model.

    `st.cache_resource`/`st.cache_data` key on the function's ARGUMENTS, not on the source of
    modules the function imports. On 2026-09-02 `inference.py` was fixed at 19:27 to load the
    bundle the checkpoint was trained on; a server started at 19:17 went on serving a predictor
    built 9.5 minutes earlier from the wrong bundle -- the Profile tab showed an 8 degC error while
    the same call outside Streamlit was correct. The code was fixed and the screen was not.

    This was written three times (tscast_page, cube_page, and now physics_page) before being
    factored out here -- the exact kind of safety mechanism where a missed copy is a silent stale
    dashboard, not a test failure. New callers should use THIS, not paste a fourth copy.
    """
    h = hashlib.sha256()
    from phase2.tscast_nio import dataset as _D, inference as _I
    for p in (base.art("tscast_stage1.pt"), _I.__file__, _D.__file__, __file__):
        try:
            st_ = os.stat(p)
            h.update(f"{p}:{st_.st_mtime_ns}:{st_.st_size}".encode())
        except OSError:
            h.update(f"{p}:missing".encode())
    return h.hexdigest()[:16]


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
        s_mus, s_lvs = [], []
        stage = int(getattr(predictor, "stage", 1))
        with torch.no_grad():
            for x, g, _, _, _, cp, mo in DataLoader(ds, batch_size=batch_size, shuffle=False):
                x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
                out = predictor.model(x, g, cp, mo)
                mus.append(out[0].cpu().numpy())
                lvs.append(out[1].cpu().numpy())
                if stage == 2:
                    # out = (mu_t, logvar_t, mu_s, logvar_s, logvar_rho). Same order the point
                    # path unpacks in inference.py -- one definition of the v2 prediction.
                    s_mus.append(out[2].cpu().numpy())
                    s_lvs.append(out[3].cpu().numpy())
    finally:
        ds.index = saved                                            # never leave it mutated

    mu = np.concatenate(mus) * predictor.y_std + predictor.y_mean
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * predictor.y_std

    # Salinity, denormalised with ITS OWN mean and std -- scaling it with temperature's would be a
    # units error nothing downstream could catch, which is why the predictor refuses a stage-2
    # checkpoint that does not carry six normalisation entries.
    sal = sig_s = None
    if stage == 2:
        sal = np.concatenate(s_mus) * predictor.s_std + predictor.s_mean
        sig_s = np.sqrt(np.exp(np.concatenate(s_lvs))) * predictor.s_std

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
            "stage": stage,          # without this a stage-2 field takes stage-1's scales
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
    SAL = SIG_S = RHO = None
    if stage == 2:
        SAL, SIG_S = np.full(shape, np.nan), np.full(shape, np.nan)
        SAL[ii, jj, :], SIG_S[ii, jj, :] = sal, sig_s

    # Below the seafloor there is no ocean. The GLORYS target is NaN there, and a reconstruction
    # that filled it with a number would be inventing water.
    valid = np.isfinite(temp_truth) & ocean[:, :, None]
    T[~valid] = np.nan
    S[~valid] = np.nan
    if stage == 2:
        SAL[~valid] = np.nan
        SIG_S[~valid] = np.nan
        from phase2.physics import seawater as _sw
        RHO = _sw.density(SAL, T)          # EOS-80, the same call the point path makes

    return {
        "date": str(np.asarray(predictor.data["times"])[t_idx]),
        "temperature": T, "sigma": S, "valid_mask": valid, "land_mask": land,
        # None on stage 1 -- absent, not zero. A caller that needs salinity must check.
        "stage": stage, "salinity": SAL, "sigma_s": SIG_S, "density": RHO,
        "provenance": {
            "model": "tscast-nio-stage1",
            "input_source": predictor.data.get("input_source", "unknown"),
            "bundle": predictor.meta.get("bundle"),
            "checkpoint": _promoted_from(predictor),
            "encoder": predictor.meta.get("encoder"),
            "seed": predictor.meta.get("seed"),
            "T_SEQ": predictor.meta.get("T_SEQ"),
            "days_from_requested": days_off,
            "sigma_is_calibrated": applied,
            "sigma_calibration_note": why,
            "n_cells": int(ii.size),
        },
    }
