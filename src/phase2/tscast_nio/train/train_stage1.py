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
from phase2.tscast_nio import config, dataset as D, eval_argo as EA, metrics
from phase2.tscast_nio.models import TSCastNIO, gaussian_nll
from phase2.tscast_nio.models.tscast import gradient_loss
from phase2.tscast_nio.models.tscast import temporal_pool_signature as TSCastNIO_pool_sig

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
        # COVERAGE: the fraction of independent floats that actually land inside the stated band.
        # The ratio alone can look healthy while the errors are the wrong SHAPE -- a heavy tail
        # sits outside 2 sigma no matter how well the RMS matches. Gaussian targets are 68.3 and
        # 95.4 per cent. The paper shows no calibration or coverage figure at all, so this is
        # measured here rather than quoted from it.
        err = np.abs(pred[ok, k] - truth[ok, k])
        out[int(d)] = {"n": int(ok.sum()), "rmse": round(rmse, 4),
                       "sigma": round(rms_sig, 4),
                       "ratio": round(rmse / rms_sig, 3) if rms_sig > 1e-9 else None,
                       "coverage_1sigma": round(float(np.mean(err <= sigma[ok, k])), 4),
                       "coverage_2sigma": round(float(np.mean(err <= 2 * sigma[ok, k])), 4)}
    return out


def _json_safe(o):
    """Replace NaN/Inf with None so the output is valid JSON.

    per_depth leaves skill fields NaN when no climatology is passed. Python emits those as a bare
    `NaN` token: json.load accepts it, JSON.parse throws. Emitting null keeps "not measured"
    distinguishable from zero on both sides.
    """
    import math
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


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
    ap.add_argument("--daily-dir", default=None,
                    help="which daily bundle to train on; default data/processed/daily. Lets a "
                         "5-channel and a 7-channel run be compared with everything else held "
                         "identical, which a rebuilt-in-place bundle cannot support.")
    ap.add_argument("--w-grad", type=float, default=0.0,
                    help="weight on the vertical-gradient loss (models.tscast.gradient_loss). "
                         "0.0 -- the default -- reproduces the shipped objective BIT-IDENTICALLY, "
                         "which tests/phase2/test_physics_loss.py asserts on a fixed batch. "
                         "Ablatable exactly like --w-density, because this project has already "
                         "MEASURED a physics term costing accuracy (eq. 5 density: 0.8593 vs "
                         "0.8548) and no such term is assumed to help.")
    ap.add_argument("--tag", default="",
                    help="suffix for the checkpoint and metrics filenames, e.g. --tag 7ch writes "
                         "tscast_stage1_7ch.pt. Every leg of the T_SEQ sweep overwrote the last "
                         "and the winning checkpoint was lost; this is how that stops happening.")
    ap.add_argument("--t-seq", type=int, default=None,
                    help="input window length. Only meaningful with --data daily; "
                         "the monthly archive has no daily neighbours.")
    ap.add_argument("--val-samples", "--test-samples", dest="val_samples", type=int,
                    default=12000,
                    help="samples drawn from the VALIDATION block for early stopping. "
                         "--test-samples is kept as an alias so older command lines still run; "
                         "it never sized the test scoring, which uses every collocated Argo "
                         "profile.")
    ap.add_argument("--val-days", type=int, default=None,
                    help="trailing TRAIN steps reserved for model selection. Default: "
                         f"{int(D.VAL_FRACTION * 100)}%% of the train block. The test period is "
                         "never used for selection -- see dataset.selection_split.")
    ap.add_argument("--val-blocks", type=int, default=1,
                    help="spread --val-days over this many evenly spaced blocks instead of one "
                         "trailing block. Above 1 buys the selection signal seasonal coverage -- "
                         "this bundle's train block opens in June, the same season as the back "
                         "half of the scored window -- at the cost of purging the training set on "
                         "both sides of every block.")
    ap.add_argument("--drop-channels", nargs="+", default=None,
                    help="channel names to remove before training, e.g. --drop-channels u v for "
                         "the currents ablation. Refuses on a name the bundle does not have, so a "
                         "typo cannot produce a 'no effect' result from an ablation that never "
                         "happened.")
    ap.add_argument("--seed", type=int, default=None,
                    help="override config SEED. Phase 5 needs several, because an effect at "
                         "+/-0.02 degC does not hold its sign across seeds -- wind's own result "
                         "flipped from -0.0149 to +0.0111 under a retrain.")
    ap.add_argument("--beta", type=float, default=0.5,
                    help="beta-NLL (Seitzer 2022). 0 = the paper's plain eq. 3, which we MEASURED "
                         "collapsing variance instead of learning the mean; 1 = MSE gradient for "
                         "mu; 0.5 = recommended default.")
    a = ap.parse_args()

    # One seed for EVERYTHING: sample draw, weight init, data order. A leg of an ablation
    # that differed in any of these would not be a matched comparison.
    # AN EXPERIMENTAL RUN MUST NOT BE ABLE TO OVERWRITE THE DELIVERABLE.
    # `--tag` defaults to "", and the checkpoint path is art(f"tscast_stage1{suffix}.pt") -- so an
    # untagged run writes artifacts/tscast_stage1.pt, which is BYTE-IDENTICAL to the frozen
    # deliverable (sha 53848bb5...). Worse, it is silent: freeze_headline --verify checks the
    # TAGGED copy and would still pass, while the dashboard, output.ERROR_SOURCES and
    # train_stage2._stage1_comparison() all read the untagged name and would start serving the
    # experiment's numbers as the shipped baseline.
    if a.w_grad and not a.tag:
        raise SystemExit(
            "--w-grad is set but --tag is empty, so this run would overwrite "
            f"{base.art('tscast_stage1.pt')} -- the promoted copy of the frozen deliverable. "
            "Give the run its own tag, e.g. --tag grad0p5_s42.")

    seed = int(a.seed if a.seed is not None else base.SEED)
    enc, enc_why = (a.encoder, "chosen on the command line") if a.encoder else winning_encoder()
    dev = torch.device(("cuda" if torch.cuda.is_available() else "cpu")
                       if a.device == "auto" else a.device)
    print(f"encoder: {enc}  ({enc_why})")
    print(f"device : {dev}   beta-NLL: {a.beta}")

    # Physical-unit constants for the gradient term, filled once the dataset exists. The term
    # de-normalises before differencing because y_std is PER DEPTH, so a z-scored difference is not
    # a scaled gradient. See models.tscast.gradient_loss.
    _z: list = []

    def objective(mu, logvar, y, mk):
        if a.loss == "mse":
            m = mk.float()
            base_loss = (((mu - y) ** 2) * m).sum() / m.sum().clamp(min=1.0)
        else:
            base_loss = gaussian_nll(mu, logvar, y, mk, beta=a.beta)
        if not a.w_grad:
            # Returned UNTOUCHED, not `base + 0.0 * term`. Adding a zero-weighted term is
            # bit-identical for finite values, but a NaN term would survive the multiply
            # (0.0 * NaN = NaN) and poison a run that asked for no term at all.
            return base_loss
        return base_loss + a.w_grad * gradient_loss(mu, y, mk, *_z[0])

    def selection_nll(mu, logvar, y, mk):
        """Scored ALWAYS on plain NLL when the head is probabilistic, so early stopping and
        cross-run comparison never move with --loss or --beta. Under --loss mse there is no
        variance head to score, so it falls back to MSE.

        Evaluated on the VALIDATION block only. Pointing this at the test period is the bug that
        `dataset.selection_split` exists to prevent."""
        if a.loss == "mse":
            m = mk.float()
            return (((mu - y) ** 2) * m).sum() / m.sum().clamp(min=1.0)
        return gaussian_nll(mu, logvar, y, mk, beta=0.0)
    if dev.type != "cuda":
        print("         CPU. Fine at T_SEQ=1. A T_SEQ=31 run here is days, not hours -- the "
              "encoder sees 43x the input elements.")

    if a.data == "daily":
        d = D.load_daily(a.daily_dir)
        tr_t, te_t = D.daily_split_indices(d["times"])
    else:
        d = D.load_monthly()
        tr_t, te_t = D.split_indices(d["times"])
    # Channel ablation. Dropped HERE, immediately after load, so the two legs of a comparison
    # differ in exactly one thing: which columns of `surface` exist. Everything downstream --
    # normalisation, sampling, split, seed, Argo set -- is computed from the same code on the same
    # data afterwards, which is what makes the delta attributable to the channel rather than to
    # some other difference that crept in.
    if a.drop_channels:
        have = [str(c) for c in d["channels"]]
        unknown = [c for c in a.drop_channels if c not in have]
        if unknown:
            raise SystemExit(f"--drop-channels {unknown} not in the bundle, which has {have}. "
                             "Refusing to silently drop nothing and report it as an ablation.")
        keep = [i for i, c in enumerate(have) if c not in a.drop_channels]
        if not keep:
            raise SystemExit("--drop-channels would remove every channel")
        d["surface"] = d["surface"][..., keep]
        d["channels"] = [have[i] for i in keep]
        print(f"ablation: dropped {list(a.drop_channels)} -> {len(keep)} channels "
              f"{d['channels']}")

    t_seq = int(a.t_seq or 1)

    # A training target within t_seq//2 of the first test day reads TEST surface fields as input,
    # because _window clamps to the array, not to the split. Drop those targets. Test indices are
    # untouched: a test target reaching BACK into train is not leakage, it is what an operational
    # run would legitimately have.
    n_before = len(tr_t)
    tr_t, va_t, sel = D.selection_split(d["times"], tr_t, te_t, t_seq, val_days=a.val_days,
                                          n_blocks=a.val_blocks)
    n_embargoed = sel["n_train_dropped_embargo"]
    _where = (f"one trailing block, {sel['val_period'][0]}..{sel['val_period'][1]}"
              if sel["n_blocks"] == 1 else
              f"{sel['n_blocks']} blocks, " + " + ".join(f"{a}..{b}" for a, b in sel["blocks"]))
    print(f"selection: {sel['n_val_targets']} val steps carved out of train -- {_where}. "
          f"Early stopping and the epoch choice read ONLY these; the test block is untouched "
          f"until the final Argo score.")
    if n_embargoed or sel["n_val_dropped_embargo"]:
        print(f"embargo: dropped {n_embargoed} of {n_before} training targets whose T_SEQ={t_seq} "
              f"window would have read the val block, and {sel['n_val_dropped_embargo']} val "
              f"targets whose window would have read the test block")
    if a.data == "monthly" and t_seq != 1:
        raise SystemExit("--t-seq > 1 needs --data daily: the monthly archive has one sample per "
                         "month, so a window of 31 steps would span 31 MONTHS, not 31 days.")
    print(f"data   : {a.data}, {len(d['times'])} steps, T_SEQ={t_seq}, "
          f"train {len(tr_t)} / test {len(te_t)}")
    # Derived from the split that actually ran, so it cannot drift from it the way a hand-written
    # `trained_on` string did (it still claimed "monthly archive" on every daily run).
    _t = np.asarray(d["times"], dtype="datetime64[D]")
    train_period = (str(_t[tr_t].min()), str(_t[tr_t].max()))
    test_period = (str(_t[te_t].min()), str(_t[te_t].max()))
    val_period = tuple(sel["val_period"])
    trained_on = (f"{a.data} bundle, T_SEQ={t_seq}, train {train_period[0]}..{train_period[1]}, "
                  f"selection on {val_period[0]}..{val_period[1]}, "
                  f"scored on GLORYS {test_period[0]}..{test_period[1]}, "
                  f"{len(d['channels'])} channels {[str(c) for c in d['channels']]}")
    # 2019-2021 climatology, DISJOINT from the 2025-26 daily period -> no leakage path.
    # See scripts/phase2/build_daily_climatology.py for why not a train-split climatology.
    clim = np.load(base.art("climatology.npy"))

    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=t_seq,
                             max_samples=a.train_samples, seed=seed,
                             clim=clim, return_clim=True)
    ds_va = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             va_t, norm=ds_tr.norm, t_seq=t_seq,
                             max_samples=a.val_samples,
                             seed=seed + 1, clim=clim, return_clim=True)
    print(f"train {len(ds_tr):,} samples  |  validation {len(ds_va):,}")

    torch.manual_seed(seed)
    latent = a.latent or config.LATENT_DIM
    widths = tuple(a.unet_width) if a.unet_width else tuple(config.UNET_CHANNELS)
    if a.w_grad:
        _z.append((torch.tensor(ds_tr.y_mean, dtype=torch.float32, device=dev),
                   torch.tensor(ds_tr.y_std, dtype=torch.float32, device=dev),
                   torch.tensor(config.DEPTHS, dtype=torch.float32, device=dev)))
        print(f"gradient loss ON, weight {a.w_grad} -- vertical dT/dz error in degC/m, on top of "
              f"the {'MSE' if a.loss == 'mse' else 'beta-NLL'} objective")

    model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent,
                      residual=not a.no_residual, unet_channels=widths,
                      decoder=a.decoder).to(dev)
    n_enc = sum(q.numel() for q in model.encoder.parameters())
    n_dec = sum(q.numel() for q in model.parameters()) - n_enc
    print(f"params : {n_enc + n_dec:,} total  ({n_enc:,} encoder + {n_dec:,} decoder), "
          f"latent {latent}, decoder {a.decoder}, loss {a.loss}")
    torch.manual_seed(seed)                         # seed AFTER build: init consumes the RNG
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    loader = DataLoader(ds_tr, batch_size=a.batch_size, shuffle=True,
                        num_workers=a.num_workers)
    va_loader = DataLoader(ds_va, batch_size=512, shuffle=False,
                           num_workers=a.num_workers)

    # Keep the BEST-on-VALIDATION weights, never the last. Measured on the first real run,
    # held-out NLL bottomed at epoch 4 and rose every epoch after while train NLL kept falling;
    # saving the final epoch would have checkpointed the single most overfit model and then
    # reported its Argo numbers as the result. What changed in 2026-09-07 is WHICH block that
    # signal comes from: the val block carved out of train, never the scored test period.
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
            for x, g, y, mk, _, cp, mo in va_loader:
                x, g, y, mk, cp, mo = (t.to(dev) for t in (x, g, y, mk, cp, mo))
                vt += float(selection_nll(*model(x, g, cp, mo), y, mk))
                vn += 1
        tr_nll, va_nll = tot / max(nb, 1), vt / max(vn, 1)
        curve.append({"epoch": ep + 1, "train_nll": round(tr_nll, 4),
                      "val_nll": round(va_nll, 4)})

        if va_nll < best["nll"] - 1e-4:
            best = {"nll": va_nll, "epoch": ep + 1,
                    "state": copy.deepcopy(model.state_dict())}
            stale, flag = 0, "  <- best"
        else:
            stale += 1
            flag = f"  ({stale}/{a.patience} without improvement)"
        print(f"  epoch {ep + 1}/{a.epochs}  train NLL {tr_nll:.4f}   "
              f"val NLL {va_nll:.4f}{flag}", flush=True)

        if stale >= a.patience:
            print(f"  early stop: no validation improvement for {a.patience} epochs")
            break
    secs = time.time() - t0

    if best["state"] is None:
        raise RuntimeError("no epoch improved on the initial validation loss; refusing to save")
    model.load_state_dict(best["state"])
    model.eval()
    print(f"\nrestored the best epoch: {best['epoch']} (val NLL {best['nll']:.4f}). "
          f"Everything below is that model, not the last one.")

    # ---- independent Argo -------------------------------------------------
    # The TEST block is instantiated HERE, after the epoch has been chosen, and nowhere earlier.
    # It used to be built before the training loop and serve as the early-stopping set, which is
    # the leak `dataset.selection_split` exists to remove. The Argo scorer only borrows the object
    # for its normalisation and its T_SEQ window builder: `.index` is overwritten further down
    # with the collocated (time, lat, lon) triples, so nothing here bounds what gets scored.
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=t_seq,
                             seed=seed + 1, clim=clim, return_clim=True)
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
    # Decline what the product declines, and count it (eval_argo.apply_seafloor_mask). The
    # metric and output.build_record must agree on what a valid prediction is; until 2026-09-07
    # they did not, and the score charged the model at depths the product returns None for.
    truth = np.asarray(truth, dtype="float64").copy()
    truth[keep], refusals = EA.apply_seafloor_mask(truth[keep], la[keep], lo[keep],
                                                   d["valid_mask"], d["land_mask"])
    baseline_ok = EA.baseline_exists_mask(la[keep], lo[keep], d["valid_mask"], d["land_mask"])

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
    _first = None
    model.eval()
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds_te, batch_size=512, shuffle=False):
            if _first is None:
                _first = (x[0].clone().numpy(), g[0].clone().numpy(),
                          cp[0].clone().numpy(), int(mo[0]))
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            mu, lv = model(x, g, cp, mo)
            mus.append(mu.cpu().numpy())
            lvs.append(lv.cpu().numpy())
    mu = np.concatenate(mus) * ds_te.y_std + ds_te.y_mean          # back to degC
    sigma = np.sqrt(np.exp(np.concatenate(lvs))) * ds_te.y_std     # sigma scales with y_std

    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    # Dump the predictions this run scored, so any later scorer can be checked against them
    # instead of being trusted. scripts/phase2/score_by_basin.py reproduced neither of two
    # checkpoints' recorded RMSE, and elimination could not say why -- because the one thing never
    # compared was the predictions themselves. A recorded metric that cannot be regenerated from
    # its own checkpoint is not reproducible, whatever else is true of it.
    np.savez_compressed(base.art(f"tscast_stage1{'_' + a.tag if a.tag else ''}_argo_pred.npz"),
                        mu=mu, sigma=sigma, truth=truth[keep],
                        lat=keys["lat"].values[keep], lon=keys["lon"].values[keep],
                        t_idx=t_idx[keep], la=la[keep], lo=lo[keep],
                        x0=_first[0], g0=_first[1], cp0=_first[2], mo0=_first[3])
    m = metrics.per_depth(mu, truth[keep], clim=clim_at[keep], reference="argo",
                          baseline_ok=baseline_ok)
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

    suffix = f"_{a.tag}" if a.tag else ""
    ck = base.art(f"tscast_stage1{suffix}.pt")
    torch.save({"state_dict": {k: v.cpu() for k, v in model.state_dict().items()}, "encoder": enc, "seed": seed,
                "residual": not a.no_residual, "channels": d["channels"],
                "P": config.P, "T_SEQ": t_seq, "latent": latent, "unet_channels": list(widths),
                # Without these the predictor cannot rebuild the network it is loading: it guessed
                # `film` and died with "Missing key(s) decoder.*" on every simple-decoder run.
                "decoder": a.decoder, "loss": a.loss, "beta_nll": a.beta, "w_grad": a.w_grad, "data": a.data,
                # Which temporal protocol produced these weights. Nothing in a checkpoint used to
                # distinguish the boundary-overlap runs from the embargoed ones, so a stale
                # checkpoint could not be told apart from a clean one.
                "protocol": "embargoed_v3_val_carved",
                "n_targets_embargoed": int(n_embargoed),
                "selection_protocol": D.SELECTION_PROTOCOL,
                # The model is CONSTRUCTED at t_seq=1 above while T_SEQ is the DATA window. They are
                # different numbers and only coincide at T_SEQ=1; cnn3d pools over time so its
                # shapes do not change, but a reader must not have to know that to load us.
                "built_t_seq": 1,
                # WHICH bundle, recorded in the checkpoint itself. It used to live
                # only in the sibling metrics JSON, so a consumer holding just the
                # .pt had to guess -- and inference.py guessed wrong for a day.
                "daily_dir": (a.daily_dir or ("data/processed/daily"
                                              if a.data == "daily" else None)),
                "input_source": d.get("input_source", "unknown"),
                # The temporal pooling this network was built with. A consumer that rebuilds
                # wrongly is refused by models.assert_architecture_matches instead of
                # silently predicting differently -- see that function for what happened.
                "pool_signature": TSCastNIO_pool_sig(model),
                "trained_on": trained_on,
                "train_period": list(train_period), "test_period": list(test_period),
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
        "trained_on": trained_on,
        "train_period": list(train_period), "test_period": list(test_period),
        "data": a.data, "T_SEQ": t_seq, "tag": a.tag or None,
        "daily_dir": a.daily_dir or ("data/processed/daily" if a.data == "daily" else None),
        # READ from the bundle, never asserted. This field did not exist until 2026-09-02,
        # so every artifact before then is silent about what actually fed the encoder --
        # which was fine while GLORYS was the only bundle and became a compliance question
        # the moment a satellite one existed. "unknown" is a real answer and is not
        # defaulted away.
        "input_source": d.get("input_source", "unknown"),
        "channels": d["channels"],
        "channels_note": (f"{len(d['channels'])} of the contract's 7 channels"
                          + ("" if len(d["channels"]) == 7 else "; wind (wu, wv) is ABSENT -- every "
                             "number from this run must be quoted with that stated")),
        "device": str(dev),
        "dropped_channels": list(a.drop_channels) if a.drop_channels else [],
        "latent": latent, "unet_channels": list(widths),
        "n_params_encoder": n_enc, "n_params_decoder": n_dec,
        "seed": seed, "epochs_requested": a.epochs, "epochs_run": len(curve),
        "best_epoch": best["epoch"], "best_val_nll": round(best["nll"], 4),
        "protocol": "embargoed_v3_val_carved",
        "protocol_note": ("model selection reads a validation block carved from the END of train, "
                          "never the scored test period; training targets whose T_SEQ window would "
                          "reach the val block are dropped, and val targets whose window would "
                          "reach the test block are dropped too. Runs before 2026-09-07 are "
                          "'embargoed_v2': correctly embargoed on INPUTS but selecting the epoch "
                          "on the test period itself, so their epoch choice is not independent of "
                          "their headline. Runs before 2026-08-31 are 'boundary_overlap_v1' and "
                          "leak inputs as well. None of the three is comparable to another."),
        "n_targets_embargoed": int(n_embargoed),
        "selection": sel,
        "val_period": list(val_period),
        "patience": a.patience, "weight_decay": a.weight_decay, "beta_nll": a.beta, "w_grad": a.w_grad,
        "decoder": a.decoder, "loss": a.loss,
        "beta_nll_why": ("plain NLL (beta=0) was measured collapsing variance: train NLL -1.0610 vs held-out +0.6732, best epoch 3/20, Argo RMSE 1.1861 against 0.9891 for the same encoder under MSE. beta re-weights by a stop-gradient sigma^(2*beta) to cancel the 1/sigma^2 term. Held-out NLL is still scored at beta=0."),
        "training_curve": curve,
        "checkpoint_is": "the BEST held-out epoch, not the last -- this run overfits after a handful of epochs",
        "lr": a.lr, "batch_size": a.batch_size,
        "train_samples": len(ds_tr), "train_seconds": round(secs, 1),
        "train_years": list(base.TRAIN_YEARS), "test_years": list(base.TEST_YEARS),
        "argo_profiles": int(keep.sum()), "max_days_offset": MAX_DAYS,
        "scoring_protocol": EA.SCORING_PROTOCOL, "refusals": refusals,
        "argo_table": (EA.argo_table_provenance(argo_path) if a.data == "daily" else None),
        "metrics": m,
        "calibration": cal,
        "coverage_targets": {"1sigma": 0.683, "2sigma": 0.954,
                             "note": "Gaussian targets. Below = the band is too narrow at that "
                                     "depth; well above = too wide, which is also not honest."},
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
    # SELF-CHECK: reload what we just wrote and re-run the first scored sample through a FRESH
    # model. If this disagrees, the checkpoint does not reproduce its own metrics, and every number
    # in this file is unverifiable from the artifact it names.
    _fresh = TSCastNIO(enc, c_in=len(d["channels"]), t_seq=1, p=config.P, latent=latent,
                       residual=not a.no_residual, unet_channels=tuple(widths),
                       decoder=a.decoder, stage=1)
    _fresh.load_state_dict(torch.load(ck, map_location="cpu", weights_only=False)["state_dict"])
    _fresh.eval()
    with torch.no_grad():
        _mu, _ = _fresh(torch.from_numpy(_first[0])[None], torch.from_numpy(_first[1])[None],
                        torch.from_numpy(_first[2])[None], torch.tensor([_first[3]]))
    _re = _mu.numpy()[0] * ds_te.y_std + ds_te.y_mean
    _ok = bool(np.allclose(_re, mu[0], atol=1e-4))
    with torch.no_grad():
        _lm, _ = model(torch.from_numpy(_first[0])[None].to(dev),
                       torch.from_numpy(_first[1])[None].to(dev),
                       torch.from_numpy(_first[2])[None].to(dev),
                       torch.tensor([_first[3]]).to(dev))
    _lv = _lm.cpu().numpy()[0] * ds_te.y_std + ds_te.y_mean
    print(f'   LIVE model on x0 reproduces its own mu[0]: {bool(np.allclose(_lv, mu[0], atol=1e-4))}')
    print(f'      live {np.round(_lv[:4],4)}  vs scored {np.round(mu[0][:4],4)}')
    _live = model.state_dict()
    _back = _fresh.state_dict()
    _bad = [k for k in _live
            if not torch.equal(_live[k].cpu().float(), _back[k].cpu().float())]
    print(f'   state_dict values identical after round-trip: {not _bad}'
          f"{'' if not _bad else '  DIFFERING: ' + str(_bad[:4])}")
    print("")
    print(f"checkpoint self-check: reloaded prediction "
          f"{'MATCHES' if _ok else 'DIFFERS FROM'} the scored one")
    if not _ok:
        print(f"   scored   {np.round(mu[0][:4], 4)}")
        print(f"   reloaded {np.round(_re[:4], 4)}   max|diff| {np.abs(_re - mu[0]).max():.6f}")

        # LAYER BISECT: run the SAME input through the live model and the reloaded one with
        # forward hooks on every module, and report the FIRST module whose output differs. Weights
        # are byte-identical (torch.equal) and the input is byte-identical, so whichever module
        # diverges first is where the non-reproducibility lives.
        _acts = {"live": {}, "fresh": {}}

        def _mk(which):
            def _reg(name):
                def _h(_m, _i, _o):
                    t = _o[0] if isinstance(_o, tuple) else _o
                    if torch.is_tensor(t):
                        _acts[which][name] = t.detach().float().cpu().clone()
                return _h
            return _reg

        _fresh_d = _fresh.to(dev)
        _hs = []
        for _n, _m in model.named_modules():
            if _n:
                _hs.append(_m.register_forward_hook(_mk("live")(_n)))
        for _n, _m in _fresh_d.named_modules():
            if _n:
                _hs.append(_m.register_forward_hook(_mk("fresh")(_n)))
        _args = (torch.from_numpy(_first[0])[None].to(dev),
                 torch.from_numpy(_first[1])[None].to(dev),
                 torch.from_numpy(_first[2])[None].to(dev),
                 torch.tensor([_first[3]]).to(dev))
        with torch.no_grad():
            model(*_args)
            _fresh_d(*_args)
        for _h in _hs:
            _h.remove()

        _order = [n for n, _ in model.named_modules() if n and n in _acts["fresh"]]
        print("   layer bisect (first divergence wins):")
        _shown = 0
        for _n in _order:
            _a, _b = _acts["live"][_n], _acts["fresh"][_n]
            if _a.shape != _b.shape:
                print(f"      {_n:38} SHAPE {tuple(_a.shape)} vs {tuple(_b.shape)}")
                break
            _d = float((_a - _b).abs().max())
            if _d > 1e-6:
                print(f"      {_n:38} DIVERGES  max|diff| {_d:.6g}")
                _shown += 1
                if _shown >= 5:
                    break
            elif _shown == 0:
                print(f"      {_n:38} ok        max|diff| {_d:.3g}")

    p = base.art(f"tscast_stage1{suffix}_metrics.json")
    with open(p, "w") as f:
        # allow_nan=False + a NaN->None pass: Python's json writes a bare `NaN` token,
        # which json.load accepts and JSON.parse REJECTS. A metrics file the dashboard
        # cannot read is a metrics file nobody checks the UI against.
        json.dump(_json_safe(out), f, indent=1, allow_nan=False)
    print(f"\nwrote {ck}\nwrote {p}")


if __name__ == "__main__":
    main()
