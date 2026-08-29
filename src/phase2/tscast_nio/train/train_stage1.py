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
import copy
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
    ap.add_argument("--patience", type=int, default=4,
                    help="stop after this many epochs with no held-out improvement")
    ap.add_argument("--weight-decay", type=float, default=1e-2)
    ap.add_argument("--device", default="auto",
                    help="auto | cpu | cuda. At T_SEQ=31 the encoder sees 43x the input elements "
                         "it does at T_SEQ=1, which is days per run on CPU.")
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--latent", type=int, default=None,
                    help="latent width; defaults to config.LATENT_DIM")
    ap.add_argument("--unet-width", type=int, nargs="+", default=None,
                    help="decoder channel widths; defaults to config.UNET_CHANNELS")
    ap.add_argument("--decoder", choices=["film", "simple"], default="film",
                    help="'simple' is the bake-off's head. Varying this INDEPENDENTLY of --loss is "
                         "the point: the move from the bake-off model to TS-Cast changed the "
                         "decoder AND the loss at once, and no amount of tuning inside that "
                         "confound could say which caused the regression.")
    ap.add_argument("--loss", choices=["nll", "mse"], default="nll")
    ap.add_argument("--data", choices=["monthly", "daily"], default="monthly")
    ap.add_argument("--t-seq", type=int, default=None,
                    help="input window length. Only meaningful with --data daily; "
                         "the monthly archive has no daily neighbours.")
    ap.add_argument("--test-samples", type=int, default=12000)
    ap.add_argument("--beta", type=float, default=0.5,
                    help="beta-NLL (Seitzer 2022). 0 = the paper's plain eq. 3, which we MEASURED "
                         "collapsing variance instead of learning the mean; 1 = MSE gradient for "
                         "mu; 0.5 = recommended default.")
    a = ap.parse_args()

    enc, enc_why = (a.encoder, "chosen on the command line") if a.encoder else winning_encoder()
    dev = torch.device(("cuda" if torch.cuda.is_available() else "cpu")
                       if a.device == "auto" else a.device)
    print(f"encoder: {enc}  ({enc_why})")
    print(f"device : {dev}   beta-NLL: {a.beta}")

    def objective(mu, logvar, y, mk):
        if a.loss == "mse":
            m = mk.float()
            return (((mu - y) ** 2) * m).sum() / m.sum().clamp(min=1.0)
        return gaussian_nll(mu, logvar, y, mk, beta=a.beta)

    def heldout(mu, logvar, y, mk):
        """Held out ALWAYS on plain NLL when the head is probabilistic, so early stopping and
        cross-run comparison never move with --loss or --beta. Under --loss mse there is no
        variance head to score, so it falls back to MSE."""
        if a.loss == "mse":
            m = mk.float()
            return (((mu - y) ** 2) * m).sum() / m.sum().clamp(min=1.0)
        return gaussian_nll(mu, logvar, y, mk, beta=0.0)
    if dev.type != "cuda":
        print("         CPU. Fine at T_SEQ=1. A T_SEQ=31 run here is days, not hours -- the "
              "encoder sees 43x the input elements.")

    if a.data == "daily":
        d = D.load_daily()
        tr_t, te_t = D.daily_split_indices(d["times"])
    else:
        d = D.load_monthly()
        tr_t, te_t = D.split_indices(d["times"])
    t_seq = int(a.t_seq or 1)
    if a.data == "monthly" and t_seq != 1:
        raise SystemExit("--t-seq > 1 needs --data daily: the monthly archive has one sample per "
                         "month, so a window of 31 steps would span 31 MONTHS, not 31 days.")
    print(f"data   : {a.data}, {len(d['times'])} steps, T_SEQ={t_seq}, "
          f"train {len(tr_t)} / test {len(te_t)}")
    # 2019-2021 climatology, DISJOINT from the 2025-26 daily period -> no leakage path.
    # See scripts/phase2/build_daily_climatology.py for why not a train-split climatology.
    clim = np.load(base.art("climatology.npy"))

    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=t_seq,
                             max_samples=a.train_samples, seed=base.SEED,
                             clim=clim, return_clim=True)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=t_seq,
                             max_samples=a.test_samples,
                             seed=base.SEED + 1, clim=clim, return_clim=True)
    print(f"train {len(ds_tr):,} samples  |  held-out GLORYS {len(ds_te):,}")

    torch.manual_seed(base.SEED)
    latent = a.latent or config.LATENT_DIM
    widths = tuple(a.unet_width) if a.unet_width else tuple(config.UNET_CHANNELS)
    model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent,
                      residual=not a.no_residual, unet_channels=widths,
                      decoder=a.decoder).to(dev)
    n_enc = sum(q.numel() for q in model.encoder.parameters())
    n_dec = sum(q.numel() for q in model.parameters()) - n_enc
    print(f"params : {n_enc + n_dec:,} total  ({n_enc:,} encoder + {n_dec:,} decoder), "
          f"latent {latent}, decoder {a.decoder}, loss {a.loss}")
    torch.manual_seed(base.SEED)                    # seed AFTER build: init consumes the RNG
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    loader = DataLoader(ds_tr, batch_size=a.batch_size, shuffle=True,
                        num_workers=a.num_workers)
    te_loader = DataLoader(ds_te, batch_size=512, shuffle=False,
                           num_workers=a.num_workers)

    # Keep the BEST-on-held-out weights, never the last. Measured on the first real run, held-out
    # NLL bottomed at epoch 4 and rose every epoch after while train NLL kept falling; saving the
    # final epoch would have checkpointed the single most overfit model and then reported its Argo
    # numbers as the result.
    t0 = time.time()
    best = {"nll": float("inf"), "epoch": 0, "state": None}
    curve, stale = [], 0
    for ep in range(a.epochs):
        model.train()
        tot, nb = 0.0, 0
        for x, g, y, mk, _, cp, mo in loader:
            x, g, y, mk, cp, mo = (t.to(dev) for t in (x, g, y, mk, cp, mo))
            loss = objective(*model(x, g, cp, mo), y, mk)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach())
            nb += 1
        model.eval()
        vt, vn = 0.0, 0
        with torch.no_grad():
            for x, g, y, mk, _, cp, mo in te_loader:
                x, g, y, mk, cp, mo = (t.to(dev) for t in (x, g, y, mk, cp, mo))
                vt += float(heldout(*model(x, g, cp, mo), y, mk))
                vn += 1
        tr_nll, va_nll = tot / max(nb, 1), vt / max(vn, 1)
        curve.append({"epoch": ep + 1, "train_nll": round(tr_nll, 4),
                      "heldout_nll": round(va_nll, 4)})

        if va_nll < best["nll"] - 1e-4:
            best = {"nll": va_nll, "epoch": ep + 1,
                    "state": copy.deepcopy(model.state_dict())}
            stale, flag = 0, "  <- best"
        else:
            stale += 1
            flag = f"  ({stale}/{a.patience} without improvement)"
        print(f"  epoch {ep + 1}/{a.epochs}  train NLL {tr_nll:.4f}   "
              f"held-out NLL {va_nll:.4f}{flag}", flush=True)

        if stale >= a.patience:
            print(f"  early stop: no held-out improvement for {a.patience} epochs")
            break
    secs = time.time() - t0

    if best["state"] is None:
        raise RuntimeError("no epoch improved on the initial held-out loss; refusing to save")
    model.load_state_dict(best["state"])
    model.eval()
    print(f"\nrestored the best epoch: {best['epoch']} (held-out NLL {best['nll']:.4f}). "
          f"Everything below is that model, not the last one.")

    # ---- independent Argo -------------------------------------------------
    # The Argo set MUST cover the same period as the data. artifacts/argo_test.parquet is 2022;
    # against a 2026 test window the +/-5 day filter matches nothing, and the run then died on
    # "need at least one array to concatenate" AFTER a full training run had completed.
    if a.data == "daily":
        argo_path = base.art("argo_daily_period.parquet")
        if not os.path.exists(argo_path):
            raise SystemExit(
                f"--data daily needs {argo_path}. artifacts/argo_test.parquet is 2022 only and "
                "would match zero profiles in the 2026 test window. Run "
                "scripts/phase2/fetch_argo_daily_period.py first.")
        argo_df = pd.read_parquet(argo_path)
    else:
        argo_df = VA.load_argo()
    keys, truth = VA.pivot_profiles(argo_df)
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
    print(f"independent Argo in the test window: {int(keep.sum())} profiles "
          f"(median offset {int(np.median(offs.min(axis=1)[keep]))} d)")
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
    torch.save({"state_dict": {k: v.cpu() for k, v in model.state_dict().items()}, "encoder": enc, "seed": base.SEED,
                "residual": not a.no_residual, "channels": d["channels"],
                "P": config.P, "T_SEQ": t_seq, "latent": latent, "unet_channels": list(widths),
                "norm": [v.tolist() for v in ds_tr.norm],
                "epochs": best["epoch"], "lr": a.lr,
                "batch_size": a.batch_size}, ck)

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
        "device": str(dev), "data": a.data, "T_SEQ": t_seq, "latent": latent, "unet_channels": list(widths),
        "n_params_encoder": n_enc, "n_params_decoder": n_dec,
        "seed": base.SEED, "epochs_requested": a.epochs, "epochs_run": len(curve),
        "best_epoch": best["epoch"], "best_heldout_nll": round(best["nll"], 4),
        "patience": a.patience, "weight_decay": a.weight_decay, "beta_nll": a.beta,
        "decoder": a.decoder, "loss": a.loss,
        "beta_nll_why": ("plain NLL (beta=0) was measured collapsing variance: train NLL -1.0610 vs held-out +0.6732, best epoch 3/20, Argo RMSE 1.1861 against 0.9891 for the same encoder under MSE. beta re-weights by a stop-gradient sigma^(2*beta) to cancel the 1/sigma^2 term. Held-out NLL is still scored at beta=0."),
        "training_curve": curve,
        "checkpoint_is": "the BEST held-out epoch, not the last -- this run overfits after a handful of epochs",
        "lr": a.lr, "batch_size": a.batch_size,
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
