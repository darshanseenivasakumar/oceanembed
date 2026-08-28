"""Train TS-Cast-NIO stage 1: temperature + per-depth predicted log-variance.

Validates against INDEPENDENT Argo and, critically, measures whether the predicted sigma is
actually calibrated. That is the entire justification for this head existing: D-016 measured
MC-dropout as 1.6x-3.5x too NARROW at every depth, worst in the mixed layer. Replacing one
miscalibrated uncertainty with another would be worse than useless, because it would look fixed.

The calibration ratio is computed EXACTLY the way artifacts/mc_calibration.json computed it:

    ratio(depth) = RMSE(pred - argo) / sqrt(mean(sigma^2))     aggregated per depth, THEN divided

That file explicitly warns that averaging per-point ratios inflates the shallow end roughly 2x
because sigma sits in the denominator. Matching its method is the only way the comparison against
1.6-3.5x means anything.

Run:  PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 [--epochs N]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import warnings

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

warnings.filterwarnings("ignore", message=".*enable_nested_tensor.*")

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import config, dataset as D, metrics
from phase2.tscast_nio.models import TSCastNIO, gaussian_nll

MAX_DAYS = 5


def winning_encoder(default: str = "cnn3d") -> tuple[str, str]:
    """Read the bake-off result. Never guess -- if it has not run, say so."""
    p = base.art("architecture_feasibility.json")
    if not os.path.exists(p):
        return default, f"bake-off has NOT run; falling back to {default!r}"
    f = json.load(open(p))
    return f["winner"], f"bake-off winner over {len(f['results'])} candidates"


def calibration(pred, sigma, truth):
    """Per-depth RMSE / RMS(sigma). >1 means sigma is too NARROW (overconfident)."""
    out = {}
    for k, d in enumerate(config.DEPTHS):
        ok = np.isfinite(pred[:, k]) & np.isfinite(truth[:, k]) & np.isfinite(sigma[:, k])
        if ok.sum() < 30:
            continue
        rmse = float(np.sqrt(np.mean((pred[ok, k] - truth[ok, k]) ** 2)))
        rms_sig = float(np.sqrt(np.mean(sigma[ok, k] ** 2)))
        out[int(d)] = {"n": int(ok.sum()), "rmse": round(rmse, 4),
                       "sigma": round(rms_sig, 4),
                       "ratio": round(rmse / rms_sig, 3) if rms_sig > 1e-9 else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--train-samples", type=int, default=40000)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--encoder", default=None)
    ap.add_argument("--no-residual", action="store_true")
    a = ap.parse_args()

    enc, enc_why = (a.encoder, "chosen on the command line") if a.encoder else winning_encoder()
    print(f"encoder: {enc}  ({enc_why})")

    d = D.load_monthly()
    tr_t, te_t = D.split_indices(d["times"])
    clim = np.load(base.art("climatology.npy"))     # built from TRAIN years only (climatology.py)

    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=config.T_SEQ if config.T_SEQ == 1 else 1,
                             max_samples=a.train_samples, seed=base.SEED,
                             clim=clim, return_clim=True)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=1, max_samples=12000,
                             seed=base.SEED + 1, clim=clim, return_clim=True)
    print(f"train {len(ds_tr):,} samples  |  held-out GLORYS {len(ds_te):,}")

    torch.manual_seed(base.SEED)
    model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=256,
                      residual=not a.no_residual)
    torch.manual_seed(base.SEED)                    # seed AFTER build: init consumes the RNG
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr)
    loader = DataLoader(ds_tr, batch_size=a.batch_size, shuffle=True)
    te_loader = DataLoader(ds_te, batch_size=512, shuffle=False)

    t0 = time.time()
    for ep in range(a.epochs):
        model.train()
        tot, nb = 0.0, 0
        for x, g, y, mk, _, cp, mo in loader:
            loss = gaussian_nll(*model(x, g, cp, mo), y, mk)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach())
            nb += 1
        model.eval()
        vt, vn = 0.0, 0
        with torch.no_grad():
            for x, g, y, mk, _, cp, mo in te_loader:
                vt += float(gaussian_nll(*model(x, g, cp, mo), y, mk))
                vn += 1
        print(f"  epoch {ep + 1}/{a.epochs}  train NLL {tot/max(nb,1):.4f}   "
              f"held-out NLL {vt/max(vn,1):.4f}", flush=True)
    secs = time.time() - t0

    # ---- independent Argo -------------------------------------------------
    keys, truth = VA.pivot_profiles(VA.load_argo())
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la = np.clip(np.searchsorted(base.LAT, keys["lat"].values) - 1, 0, base.N_LAT - 1)
    lo = np.clip(np.searchsorted(base.LON, keys["lon"].values) - 1, 0, base.N_LON - 1)

    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus, lvs = [], []
    model.eval()
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            mu, lv = model(x, g, cp, mo)
            mus.append(mu.numpy())
            lvs.append(lv.numpy())
    mu = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean          # back to degC
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * ds_te.y_std     # sigma scales with y_std

    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    m = metrics.per_depth(mu, truth[keep], clim=clim_at[keep], reference="argo")
    cal = calibration(mu, sigma, truth[keep])

    o = m["overall"]
    print(f"\n{'depth':>6} {'n':>5} {'RMSE':>7} {'corr':>7} {'bias':>8} {'skill':>7} "
          f"{'sigma':>7} {'ratio':>6}")
    for i, dep in enumerate(m["depths_m"]):
        c = cal.get(int(dep), {})
        print(f"{dep:>6} {m['n'][i]:>5} {m['rmse'][i]:>7.3f} {m['correlation'][i]:>7.3f} "
              f"{m['bias'][i]:>+8.3f} {m['skill_rmse_ratio'][i]:>7.3f} "
              f"{c.get('sigma', float('nan')):>7.3f} {c.get('ratio', float('nan')):>6.2f}")
    ratios = [v["ratio"] for v in cal.values() if v["ratio"]]
    print(f"\nOVERALL rmse={o['rmse']:.4f}  corr={o['correlation']:.4f}  bias={o['bias']:+.4f}  "
          f"skill={o['skill_rmse_ratio']:+.4f}")
    if ratios:
        print(f"calibration ratio {min(ratios):.2f}-{max(ratios):.2f}  "
              f"(1.0 = honest; >1 = overconfident. MC-dropout measured 1.56-3.54)")

    ck = base.art("tscast_stage1.pt")
    torch.save({"state_dict": model.state_dict(), "encoder": enc, "seed": base.SEED,
                "residual": not a.no_residual, "channels": d["channels"],
                "P": config.P, "T_SEQ": 1, "latent": 256,
                "norm": [v.tolist() for v in ds_tr.norm],
                "epochs": a.epochs, "lr": a.lr, "batch_size": a.batch_size}, ck)

    out = {
        "model": "tscast-nio-stage1",
        "encoder": enc, "encoder_selected_by": enc_why,
        "residual": not a.no_residual,
        "stage": 1,
        "stage_note": "temperature + log-variance only; salinity and the eq. 5 density "
                      "constraint are stage 2 and start only once this is validated",
        "trained_on": "monthly archive, T_SEQ=1 (the daily bundle had not landed)",
        "channels": d["channels"],
        "channels_note": "5 of the contract's 7; wind arrives with the daily pipeline",
        "seed": base.SEED, "epochs": a.epochs, "lr": a.lr, "batch_size": a.batch_size,
        "train_samples": len(ds_tr), "train_seconds": round(secs, 1),
        "train_years": list(base.TRAIN_YEARS), "test_years": list(base.TEST_YEARS),
        "argo_profiles": int(keep.sum()), "max_days_offset": MAX_DAYS,
        "metrics": m,
        "calibration": cal,
        "calibration_method": ("RMSE(pred-argo) / RMS(sigma), aggregated per depth THEN divided "
                               "-- identical to artifacts/mc_calibration.json so the comparison "
                               "against MC-dropout's 1.56-3.54 is like for like"),
        "mc_dropout_for_comparison": {"worst": 3.54, "best": 1.56,
                                      "source": "artifacts/mc_calibration.json (D-016)"},
        "compare_against": {
            "incumbent_rmse": 0.9736,
            "incumbent_skill_rmse_ratio": 0.3809,
            "which": "GLORYS-driven incumbent, argo_error_by_depth.json -> overall.glorys",
            "why_not_the_headline_0_9638": (
                "grids.npz surface fields ARE GLORYS, so this model is GLORYS-driven. The famous "
                "+0.387 / 0.9638 headline is the SATELLITE-driven path. Comparing a GLORYS-driven "
                "model against the satellite-driven headline would be scoring two different input "
                "pipelines against each other and calling the difference model skill."
            ),
        },
        "checkpoint": os.path.basename(ck),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip(),
    }
    p = base.art("tscast_stage1_metrics.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {ck}\nwrote {p}")


if __name__ == "__main__":
    main()
