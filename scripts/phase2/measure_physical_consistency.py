"""Is the SHIPPED model's profile physically sensible? Owner: Unit A (Arjhun).

    python scripts/phase2/measure_physical_consistency.py

The half of F5 that needs no training at all, and is worth having whatever the loss sweep shows: a
measurement of the deliverable itself, against the two properties the new loss terms exist to
protect.

WHY THIS IS A SEPARATE QUESTION FROM RMSE
RMSE scores each of the 15 levels independently. It never asks whether the SHAPE between them
survived, so a model can hit every level to within a degree while smearing a sharp thermocline into
a gentle slope -- and a smeared thermocline is exactly what a cyclone forecaster, an acoustician or
a fisheries analyst would be reading the profile FOR.

    GRADIENT      how much of the real dT/dz does the model reproduce, level by level, and
                  especially across the thermocline (75-125 m)?
    STABILITY     how often does the model predict lighter water beneath heavier -- a column that
                  would overturn immediately? Needs salinity at depth, so STAGE 2 only. Stage 1
                  predicts temperature alone and the question cannot be asked of it, which is
                  reported as "not applicable" rather than as zero violations.

Scored against INDEPENDENT ARGO, using the trainer's own collocation -- not against GLORYS, which
is the training target and would flatter both numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                        # noqa: E402
from oceanembed.validation import validate_argo as VA        # noqa: E402
from phase2.tscast_nio import config, dataset as D           # noqa: E402
from phase2.tscast_nio.models.tscast import TSCastNIO        # noqa: E402

MAX_DAYS = 5
OUT = base.art("physical_consistency.json")
THERMOCLINE = (75.0, 125.0)
DEPTHS = np.asarray(config.DEPTHS, dtype="float64")


def gradients(profiles: np.ndarray) -> np.ndarray:
    """dT/dz between adjacent levels, degC per metre. (N, 15) -> (N, 14)."""
    return np.diff(profiles, axis=-1) / np.diff(DEPTHS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="sat_7ch_s42")
    ap.add_argument("--daily-dir", default=os.path.join("data", "processed", "daily_sat", "v001"))
    ap.add_argument("--t-seq", type=int, default=config.T_SEQ)
    ap.add_argument("--device", default="cpu",
                    help="cpu by default so this can run beside a training sweep")
    a = ap.parse_args()

    ckpt = base.art(f"tscast_stage1_{a.tag}.pt")
    if not os.path.exists(ckpt):
        raise SystemExit(f"no checkpoint at {ckpt}")

    d = D.load_daily(a.daily_dir)
    tr_t, te_t = D.daily_split_indices(d["times"])
    tr_t = D.embargo_indices(tr_t, a.t_seq, int(te_t.min()) if len(te_t) else None)
    clim = np.load(base.art("climatology.npy"))
    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=a.t_seq, max_samples=40000, seed=base.SEED,
                             clim=clim, return_clim=True)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=a.t_seq, max_samples=12000,
                             seed=base.SEED + 1, clim=clim, return_clim=True)

    ck = torch.load(ckpt, map_location=a.device, weights_only=False)
    model = TSCastNIO(ck.get("encoder", "cnn3d"), len(d["channels"]), t_seq=1, p=config.P,
                      latent=config.LATENT_DIM, residual=True,
                      unet_channels=tuple(config.UNET_CHANNELS), decoder="simple").to(a.device)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    argo_df = pd.read_parquet(base.art("argo_daily_period.parquet"))
    keys, truth = VA.pivot_profiles(argo_df)
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)

    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus = []
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(a.device) for t in (x, g, cp, mo))
            mu, _lv = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
    pred = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean
    obs = np.asarray(truth[keep], dtype="float64")
    print(f"scored {pred.shape[0]} independent Argo profiles on {a.device}")

    # ---- gradient fidelity, per level pair ------------------------------------------------
    gp, go = gradients(pred), gradients(obs)
    both = np.isfinite(gp) & np.isfinite(go)
    mids = (DEPTHS[1:] + DEPTHS[:-1]) / 2.0

    per_pair = []
    for k in range(gp.shape[1]):
        m = both[:, k]
        if m.sum() < 5:
            per_pair.append({"mid_depth_m": float(mids[k]), "n": int(m.sum()),
                             "rmse_gradient": None, "predicted_over_observed": None,
                             "note": "too few overlapping profiles to score"})
            continue
        # The RATIO of predicted to observed gradient MAGNITUDE is the smoothing number: below 1
        # means the model's profile is flatter than the ocean's.
        per_pair.append({
            "mid_depth_m": float(mids[k]), "n": int(m.sum()),
            "rmse_gradient": float(np.sqrt(np.mean((gp[m, k] - go[m, k]) ** 2))),
            "rms_observed": float(np.sqrt(np.mean(go[m, k] ** 2))),
            "rms_predicted": float(np.sqrt(np.mean(gp[m, k] ** 2))),
            "predicted_over_observed": float(np.sqrt(np.mean(gp[m, k] ** 2))
                                             / np.sqrt(np.mean(go[m, k] ** 2))),
        })

    th = [p for p in per_pair if THERMOCLINE[0] <= p["mid_depth_m"] <= THERMOCLINE[1]
          and p.get("predicted_over_observed") is not None]
    th_ratio = float(np.mean([p["predicted_over_observed"] for p in th])) if th else None
    whole = [p for p in per_pair if p.get("predicted_over_observed") is not None]
    all_ratio = float(np.mean([p["predicted_over_observed"] for p in whole])) if whole else None

    # ---- static stability ------------------------------------------------------------------
    s2 = base.art("tscast_stage2_sat_s2.pt")
    stability = {
        "applicable": False,
        "why": ("stage 1 predicts temperature only, so it produces no density profile and the "
                "question cannot be asked of it. Reported as not-applicable rather than as zero "
                "violations, which would be a claim it has not earned."),
        "stage2_checkpoint_present": os.path.exists(s2),
    }

    out = {
        "what": "does the shipped model reproduce the SHAPE of a profile, not just its values?",
        "checkpoint": os.path.basename(ckpt), "tag": a.tag,
        "argo_profiles": int(pred.shape[0]), "reference": "independent Argo",
        "thermocline_window_m": list(THERMOCLINE),
        "gradient_ratio_thermocline": th_ratio,
        "gradient_ratio_whole_column": all_ratio,
        "interpretation": (
            "predicted_over_observed is the RMS predicted gradient divided by the RMS observed "
            "one. Below 1 the model's profile is FLATTER than the ocean's -- it is smoothing. "
            "This is invisible to RMSE, which scores levels independently."),
        "per_level_pair": per_pair,
        "static_stability": stability,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    print("")
    print("%-12s %6s %12s %12s %8s" % ("mid depth", "n", "rms obs dT/dz", "rms pred", "ratio"))
    for p in per_pair:
        if p.get("predicted_over_observed") is None:
            print("%-12.0f %6d   %s" % (p["mid_depth_m"], p["n"], p.get("note", "")))
            continue
        print("%-12.0f %6d %12.5f %12.5f %8.3f"
              % (p["mid_depth_m"], p["n"], p["rms_observed"], p["rms_predicted"],
                 p["predicted_over_observed"]))
    print("")
    if th_ratio is not None:
        print(f"THERMOCLINE ({THERMOCLINE[0]:.0f}-{THERMOCLINE[1]:.0f} m): the model reproduces "
              f"{th_ratio:.1%} of the observed gradient magnitude")
    if all_ratio is not None:
        print(f"WHOLE COLUMN                : {all_ratio:.1%}")
    print(f"static stability: not applicable to stage 1 -- {stability['why'][:60]}...")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
