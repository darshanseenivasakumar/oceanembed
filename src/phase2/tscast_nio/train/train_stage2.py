"""Train TS-Cast-NIO stage 2: temperature AND salinity, with the paper's eq. 5 density constraint.

WHAT STAGE 2 ADDS, AND WHY IT IS A SEPARATE FILE
Stage 1 produced the shipped result (0.8612 degC, 7 channels, 962 independent Argo profiles). That
number has to stay reproducible, so `train_stage1.py` is imported here and not edited: the loss,
the calibration measurement and the best-epoch rule are the SAME functions, not copies that could
drift from the ones that produced the published number.

THE THREE LOSSES  [VERIFIED from the paper, pages 6-7, not from memory]
    eq. 3  L_T    = mean_i [ (1/(2 sigma_T,i^2)) (T_i - That_i)^2 + 0.5 log sigma_T,i^2 ]
    eq. 4  L_S    = the same on salinity
    eq. 5  L_rho  = the same on DENSITY, where rho_hat = EOS-80(That, Shat) and rho = EOS-80(T, S)
    eq. 6  L_total = L_T + L_S + L_rho          <- an unweighted sum, and the paper says why:
           "Instead of using fixed hyperparameters, the model learns the optimal, data-dependent
           weight for each observation through the predicted variance." The predicted variances
           ARE the weighting, which is also how the three terms coexist despite living on wildly
           different scales (degC, psu, kg m-3) without pre-standardisation.

WHERE WE DEVIATE, AND WHY IT IS RECORDED RATHER THAN QUIET
The paper uses plain NLL (beta = 0). On our data that was MEASURED to collapse the variance --
train NLL -1.0610 against held-out +0.6732, Argo RMSE 1.1861 versus 0.9891 for the same encoder
under MSE. So beta-NLL (Seitzer et al. 2022) at beta=0.5 is applied to all three terms, exactly as
stage 1 does. `--beta 0` reproduces the paper's formulation for anyone who wants to see it fail.

--w-density exists so eq. 5 can be ABLATED (--w-density 0 trains T and S with no physical
constraint at all). A physics term nobody measured the effect of is decoration, not physics.

Run:  PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage2 \
          --t-seq 11 --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5 --tag s2
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import time

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import config, dataset as D, metrics
from phase2.tscast_nio.models.tscast import TSCastNIO, density_nll, gaussian_nll
from phase2.physics import seawater

# The stage-1 module IS the reference implementation of these. Importing rather than re-deriving
# is what makes "measured the same way" a fact instead of an intention.
from phase2.tscast_nio.train.train_stage1 import MAX_DAYS, calibration


def salinity_calibration(pred, sigma, truth):
    """Per-depth RMSE / RMS(sigma) for salinity, aggregated exactly as `calibration` does for T."""
    return calibration(pred, sigma, truth)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--train-samples", type=int, default=60000)
    ap.add_argument("--test-samples", type=int, default=12000)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--encoder", default="cnn3d")
    ap.add_argument("--no-residual", action="store_true")
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--weight-decay", type=float, default=1e-2)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--latent", type=int, default=None)
    ap.add_argument("--t-seq", type=int, default=11,
                    help="11 won the stage-1 ablation by 0.0567 degC over T_SEQ=1")
    ap.add_argument("--beta", type=float, default=0.5,
                    help="beta-NLL. 0 reproduces the paper's eq. 3/4/5 exactly, which we measured "
                         "collapsing the variance on this data")
    ap.add_argument("--w-density", type=float, default=1.0,
                    help="weight on eq. 5. The paper uses 1.0 (eq. 6 is an unweighted sum). "
                         "0 ablates the physical constraint entirely -- run it, do not assume it")
    ap.add_argument("--daily-dir", default=None)
    ap.add_argument("--tag", default="s2",
                    help="filename suffix; writes tscast_stage2_<tag>.pt")
    a = ap.parse_args()

    dev = torch.device(("cuda" if torch.cuda.is_available() else "cpu")
                       if a.device == "auto" else a.device)
    print(f"device : {dev}   beta-NLL: {a.beta}   eq.5 weight: {a.w_density}")

    d = D.load_daily(a.daily_dir)
    if "salinity" not in d:
        raise SystemExit(
            "the daily bundle carries no salinity, so there is no stage-2 target. Rebuild it with "
            "`python -m phase2.tscast_nio.daily_pipeline` (salinity is on by default).")
    tr_t, te_t = D.daily_split_indices(d["times"])
    t_seq = int(a.t_seq)

    _t = np.asarray(d["times"], dtype="datetime64[D]")
    train_period = (str(_t[tr_t].min()), str(_t[tr_t].max()))
    test_period = (str(_t[te_t].min()), str(_t[te_t].max()))
    trained_on = (f"daily bundle, T_SEQ={t_seq}, train {train_period[0]}..{train_period[1]}, "
                  f"held-out GLORYS {test_period[0]}..{test_period[1]}, "
                  f"{len(d['channels'])} channels {[str(c) for c in d['channels']]}")
    print(f"data   : daily, {len(d['times'])} steps, T_SEQ={t_seq}, "
          f"train {len(tr_t)} / test {len(te_t)}")

    # 2019-2021 climatology, DISJOINT from the 2025-26 daily period -> no leakage path.
    clim = np.load(base.art("climatology.npy"))

    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, t_seq=t_seq, max_samples=a.train_samples, seed=base.SEED,
                             clim=clim, return_clim=True,
                             salinity=d["salinity"], return_salinity=True)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, t_seq=t_seq, max_samples=a.test_samples,
                             seed=base.SEED + 1, clim=clim, return_clim=True,
                             salinity=d["salinity"], return_salinity=True)
    print(f"train {len(ds_tr):,} samples  |  held-out GLORYS {len(ds_te):,}")

    # Normalisation constants as tensors, so the density term can return z-scores to degC/psu.
    y_mean = torch.tensor(ds_tr.y_mean, device=dev)
    y_std = torch.tensor(ds_tr.y_std, device=dev)
    s_mean = torch.tensor(ds_tr.s_mean, device=dev)
    s_std = torch.tensor(ds_tr.s_std, device=dev)
    print(f"salinity target: mean {ds_tr.s_mean.mean():.3f} psu, "
          f"std {ds_tr.s_std.mean():.3f} psu (train split only)")

    torch.manual_seed(base.SEED)
    latent = a.latent or config.LATENT_DIM
    model = TSCastNIO(a.encoder, len(d["channels"]), t_seq=1, p=config.P, latent=latent,
                      residual=not a.no_residual, decoder="simple", stage=2).to(dev)
    n_all = sum(q.numel() for q in model.parameters())
    print(f"params : {n_all:,} total, latent {latent}, decoder simple, stage 2")
    torch.manual_seed(base.SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)

    loader = DataLoader(ds_tr, batch_size=a.batch_size, shuffle=True, num_workers=a.num_workers)
    te_loader = DataLoader(ds_te, batch_size=512, shuffle=False, num_workers=a.num_workers)

    def losses(out, y, mk, ys, sk, beta):
        mu_t, lv_t, mu_s, lv_s, lv_rho = out
        lt = gaussian_nll(mu_t, lv_t, y, mk, beta=beta)
        ls = gaussian_nll(mu_s, lv_s, ys, sk, beta=beta)
        # Density needs BOTH to be real at that level; a level with temperature but no salinity
        # cannot contribute a density residual and must not contribute a zero one.
        both = mk & sk
        lr = density_nll(mu_t, mu_s, lv_rho, y, ys, both,
                         y_mean, y_std, s_mean, s_std, beta=beta)
        return lt, ls, lr

    t0 = time.time()
    best = {"nll": float("inf"), "epoch": 0, "state": None}
    curve, stale = [], 0
    for ep in range(a.epochs):
        model.train()
        acc = np.zeros(4)
        nb = 0
        for x, g, y, mk, _, cp, mo, ys, sk in loader:
            x, g, y, mk, cp, mo, ys, sk = (t.to(dev) for t in (x, g, y, mk, cp, mo, ys, sk))
            lt, ls, lr = losses(model(x, g, cp, mo), y, mk, ys, sk, a.beta)
            loss = lt + ls + a.w_density * lr
            opt.zero_grad()
            loss.backward()
            opt.step()
            acc += np.array([float(loss.detach()), float(lt.detach()),
                             float(ls.detach()), float(lr.detach())])
            nb += 1

        model.eval()
        vacc = np.zeros(4)
        vn = 0
        with torch.no_grad():
            for x, g, y, mk, _, cp, mo, ys, sk in te_loader:
                x, g, y, mk, cp, mo, ys, sk = (t.to(dev) for t in (x, g, y, mk, cp, mo, ys, sk))
                # Held-out is scored at beta=0 always, so the number a run is SELECTED on never
                # moves with --beta and two runs stay comparable.
                lt, ls, lr = losses(model(x, g, cp, mo), y, mk, ys, sk, 0.0)
                vacc += np.array([float(lt + ls + a.w_density * lr),
                                  float(lt), float(ls), float(lr)])
                vn += 1
        tr_l, va_l = acc / max(nb, 1), vacc / max(vn, 1)
        curve.append({"epoch": ep + 1,
                      "train_total": round(tr_l[0], 4), "train_T": round(tr_l[1], 4),
                      "train_S": round(tr_l[2], 4), "train_rho": round(tr_l[3], 4),
                      "heldout_total": round(va_l[0], 4), "heldout_T": round(va_l[1], 4),
                      "heldout_S": round(va_l[2], 4), "heldout_rho": round(va_l[3], 4)})

        if va_l[0] < best["nll"] - 1e-4:
            best = {"nll": va_l[0], "epoch": ep + 1, "state": copy.deepcopy(model.state_dict())}
            stale, flag = 0, "  <- best"
        else:
            stale += 1
            flag = f"  ({stale}/{a.patience} without improvement)"
        print(f"  epoch {ep + 1}/{a.epochs}  train {tr_l[0]:.4f} "
              f"(T {tr_l[1]:.3f} S {tr_l[2]:.3f} rho {tr_l[3]:.3f})   "
              f"held-out {va_l[0]:.4f} (T {va_l[1]:.3f} S {va_l[2]:.3f} rho {va_l[3]:.3f})"
              f"{flag}", flush=True)
        if stale >= a.patience:
            print(f"  early stop: no held-out improvement for {a.patience} epochs")
            break
    secs = time.time() - t0

    if best["state"] is None:
        raise RuntimeError("no epoch improved on the initial held-out loss; refusing to save")
    model.load_state_dict(best["state"])
    model.eval()
    print(f"\nrestored the best epoch: {best['epoch']} (held-out {best['nll']:.4f}).")

    # ---- independent Argo, temperature AND salinity ------------------------------------
    ts_path = base.art("argo_daily_period_ts.parquet")
    t_only = base.art("argo_daily_period.parquet")
    has_argo_salinity = os.path.exists(ts_path)
    argo_path = ts_path if has_argo_salinity else t_only
    if not os.path.exists(argo_path):
        raise SystemExit(f"need {argo_path}; run scripts/phase2/fetch_argo_ts_daily_period.py")
    argo_df = pd.read_parquet(argo_path)
    if not has_argo_salinity:
        print(f"\nWARNING: {os.path.basename(ts_path)} is absent, so salinity has NO independent "
              f"check and will be scored against held-out GLORYS only -- the reanalysis it was "
              f"trained on. Temperature is still independent. This is stated in the metrics file.")

    keys, truth_t = VA.pivot_profiles(argo_df)
    truth_s = None
    if has_argo_salinity and "psal" in argo_df.columns:
        # Reuse the SAME pivot rather than writing a second one. The temp column must be DROPPED
        # first: renaming psal->temp beside an existing temp yields two columns with one name, and
        # pandas then hands the pivot whichever it likes -- silently scoring salinity against
        # temperature or the reverse.
        sdf = argo_df.drop(columns=["temp"]).rename(columns={"psal": "temp"})
        k_s, truth_s = VA.pivot_profiles(sdf)
        if not k_s.equals(keys):
            raise SystemExit(
                "the salinity pivot returned a different profile ordering than the temperature "
                "pivot; they must be row-aligned or every S metric is scored against the wrong "
                "profile.")

    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= MAX_DAYS
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)
    if int(keep.sum()) == 0:
        raise SystemExit("no Argo profile falls in the test window; refusing to report metrics "
                         "computed on zero profiles.")
    print(f"independent Argo in the test window: {int(keep.sum())} profiles "
          f"(median offset {int(np.median(offs.min(axis=1)[keep]))} d)")

    ds_te.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mt, lt_, ms, ls_, lr_ = [], [], [], [], []
    with torch.no_grad():
        for x, g, _, _, _, cp, mo, _, _ in DataLoader(ds_te, batch_size=512, shuffle=False):
            x, g, cp, mo = (t.to(dev) for t in (x, g, cp, mo))
            o = model(x, g, cp, mo)
            for sink, val in zip((mt, lt_, ms, ls_, lr_), o):
                sink.append(val.cpu().numpy())

    mu_t = np.concatenate(mt) * ds_te.y_std + ds_te.y_mean               # degC
    sig_t = np.sqrt(np.exp(np.concatenate(lt_))) * ds_te.y_std
    mu_s = np.concatenate(ms) * ds_te.s_std + ds_te.s_mean               # psu
    sig_s = np.sqrt(np.exp(np.concatenate(ls_))) * ds_te.s_std
    sig_rho = np.sqrt(np.exp(np.concatenate(lr_)))                       # kg m-3, already physical

    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la, lo, :]
    m_t = metrics.per_depth(mu_t, truth_t[keep], clim=clim_at[keep], reference="argo")
    cal_t = calibration(mu_t, sig_t, truth_t[keep])

    print(f"\nTEMPERATURE  {'depth':>6} {'n':>5} {'RMSE':>7} {'corr':>7} {'bias':>8} {'skill':>7}")
    for i, dep in enumerate(m_t["depths_m"]):
        print(f"{'':12}{dep:>6} {m_t['n'][i]:>5} {m_t['rmse'][i]:>7.3f} "
              f"{m_t['correlation'][i]:>7.3f} {m_t['bias'][i]:>+8.3f} "
              f"{m_t['skill_rmse_ratio'][i]:>7.3f}")
    print(f"OVERALL T  rmse={m_t['overall']['rmse']:.4f}  "
          f"skill={m_t['overall']['skill_rmse_ratio']:+.4f}")

    m_s = cal_s = None
    if truth_s is not None:
        m_s = metrics.per_depth(mu_s, truth_s[keep], clim=None, reference="argo")
        cal_s = salinity_calibration(mu_s, sig_s, truth_s[keep])
        print(f"\nSALINITY     {'depth':>6} {'n':>5} {'RMSE':>7} {'corr':>7} {'bias':>8}")
        for i, dep in enumerate(m_s["depths_m"]):
            print(f"{'':12}{dep:>6} {m_s['n'][i]:>5} {m_s['rmse'][i]:>7.3f} "
                  f"{m_s['correlation'][i]:>7.3f} {m_s['bias'][i]:>+8.3f}")
        print(f"OVERALL S  rmse={m_s['overall']['rmse']:.4f} psu   "
              f"(the paper reports 0.1 psu south / 0.2 psu north in ITS basin -- a different "
              f"ocean, quoted for scale only, never as a comparison)")

    # Density agreement is the whole point of eq. 5, so it is MEASURED, not assumed.
    rho_stats = None
    if truth_s is not None:
        rho_pred = seawater.density(mu_s, mu_t)
        rho_true = seawater.density(truth_s[keep], truth_t[keep])
        ok = np.isfinite(rho_pred) & np.isfinite(rho_true)
        if ok.sum():
            err = rho_pred[ok] - rho_true[ok]
            rms_sig = float(np.sqrt(np.mean(sig_rho[ok] ** 2)))
            rho_stats = {
                "n": int(ok.sum()),
                "rmse_kg_m3": round(float(np.sqrt(np.mean(err ** 2))), 4),
                "bias_kg_m3": round(float(err.mean()), 4),
                "predicted_rms_sigma_kg_m3": round(rms_sig, 4),
                "calibration_ratio": (round(float(np.sqrt(np.mean(err ** 2))) / rms_sig, 3)
                                      if rms_sig > 1e-9 else None),
                "what": "EOS-80 density from predicted (T,S) vs from independent-Argo (T,S)",
            }
            print(f"\nDENSITY (eq. 5 target)  RMSE {rho_stats['rmse_kg_m3']:.4f} kg m-3, "
                  f"bias {rho_stats['bias_kg_m3']:+.4f}, "
                  f"predicted sigma {rms_sig:.4f}, ratio {rho_stats['calibration_ratio']}")

    suffix = f"_{a.tag}" if a.tag else ""
    ck = base.art(f"tscast_stage2{suffix}.pt")
    torch.save({"state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
                "encoder": a.encoder, "seed": base.SEED, "residual": not a.no_residual,
                "channels": d["channels"], "P": config.P, "T_SEQ": t_seq, "built_t_seq": 1,
                "latent": latent, "unet_channels": None,
                "decoder": "simple", "loss": "nll", "beta_nll": a.beta, "data": "daily",
                "stage": 2, "w_density": a.w_density,
                "norm": [np.asarray(v).tolist() for v in ds_tr.norm],
                "trained_on": trained_on,
                "train_period": list(train_period), "test_period": list(test_period),
                "epochs": best["epoch"], "lr": a.lr, "batch_size": a.batch_size}, ck)

    out = {
        "model": "tscast-nio-stage2",
        "stage": 2,
        "stage_note": ("temperature + salinity + the eq. 5 density constraint. Density is NOT a "
                       "model output: it is computed from the predicted (T,S) by EOS-80 and "
                       "compared to density from the truth, so the constraint couples the two "
                       "heads rather than adding a third prediction."),
        "encoder": a.encoder, "decoder": "simple", "loss": "nll+nll+density_nll",
        "loss_note": ("paper eq. 6, L_total = L_T + L_S + L_rho, unweighted -- the predicted "
                      "variances ARE the weighting, which is how three terms in degC, psu and "
                      "kg m-3 coexist without pre-standardisation"),
        "beta_nll": a.beta,
        "beta_nll_why": ("the paper uses plain NLL (beta=0); on this data that was MEASURED to "
                         "collapse the variance (train NLL -1.0610 vs held-out +0.6732), so all "
                         "three terms use beta-NLL (Seitzer 2022). --beta 0 reproduces the paper."),
        "w_density": a.w_density,
        "eos": "EOS-80 / UNESCO (1983), Fofonoff & Millard -- the same reference the paper cites",
        "trained_on": trained_on,
        "train_period": list(train_period), "test_period": list(test_period),
        "data": "daily", "T_SEQ": t_seq,
        "channels": [str(c) for c in d["channels"]],
        "device": str(dev), "latent": latent, "n_params": n_all, "seed": base.SEED,
        "epochs_requested": a.epochs, "epochs_run": len(curve), "best_epoch": best["epoch"],
        "best_heldout_total": round(best["nll"], 4),
        "patience": a.patience, "weight_decay": a.weight_decay, "lr": a.lr,
        "batch_size": a.batch_size, "train_samples": a.train_samples,
        "train_seconds": round(secs, 1),
        "training_curve": curve,
        "checkpoint_is": "the BEST held-out epoch, not the last",
        "argo_profiles": int(keep.sum()), "max_days_offset": MAX_DAYS,
        "argo_table": os.path.basename(argo_path),
        "salinity_is_independently_validated": bool(truth_s is not None),
        "salinity_validation_note": (
            "scored against Argo PSAL, independent of training"
            if truth_s is not None else
            "NO independent salinity was available; salinity is unvalidated against observations"),
        "metrics": m_t,
        "metrics_salinity": m_s,
        "calibration": cal_t,
        "calibration_salinity": cal_s,
        "density": rho_stats,
        "compare_against": {
            "stage1_rmse": 0.8612,
            "stage1_skill_rmse_ratio": 0.2975,
            "which": "stage-1 7-channel run, artifacts/tscast_stage1_7ch_metrics.json",
            "caveat": ("same bundle, same split, same T_SEQ and same seed, so the temperature "
                       "delta is attributable to stage 2's extra heads and the eq. 5 term -- "
                       "NOT to a different test set."),
        },
        "checkpoint": os.path.basename(ck),
    }
    mp = base.art(f"tscast_stage2{suffix}_metrics.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {ck}\nwrote {mp}")


if __name__ == "__main__":
    main()
