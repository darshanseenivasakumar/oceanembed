"""Phase 6: fit per-depth uncertainty scaling on TRAIN-window Argo, evaluate on TEST-window Argo.

The split is the whole point. Fitting the scale on the test profiles would drive coverage to 0.683
by construction, and the reported number would be measuring how well a scale factor fits the data
it was fitted to. The two Argo sets here are disjoint in time by the same embargo the model
respects.

Run:  PYTHONPATH=src python scripts/phase2/calibrate_uncertainty.py --checkpoint <path>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import warnings

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

warnings.filterwarnings("ignore", message=".*enable_nested_tensor.*")

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import calibrate, config, dataset as D
from phase2.tscast_nio.models import TSCastNIO
from phase2.tscast_nio.models.tscast import assert_architecture_matches

MAX_DAYS = 5
SPLIT = np.datetime64("2026-04-01")      # train-window Argo before this, test-window on/after


def predict_at_argo(model, ds, keys, t_idx, keep):
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)
    saved = ds.index
    ds.index = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    mus, lvs = [], []
    model.eval()
    with torch.no_grad():
        for x, g, _, _, _, cp, mo in DataLoader(ds, batch_size=512, shuffle=False):
            mu, lv = model(x, g, cp, mo)
            mus.append(mu.numpy())
            lvs.append(lv.numpy())
    ds.index = saved
    return np.concatenate(mus), np.concatenate(lvs)


def main() -> None:
    ap = argparse.ArgumentParser()
    # The canonical promoted run (scripts/phase2/promote_run.py), NOT a tagged experiment.
    # This defaulted to tscast_stage1_tseq31.pt -- a 5-channel T_SEQ=31 checkpoint -- while
    # output._calibration_applies_to() gates on 7 channels and T_SEQ=11, so the scales it fitted
    # were guaranteed to be refused at serving time and sigma silently stayed raw.
    ap.add_argument("--checkpoint", default=base.art("tscast_stage1.pt"))
    ap.add_argument("--out", default=base.art("uncertainty_calibration.json"))
    a = ap.parse_args()

    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    chans = [str(c) for c in ck["channels"]]
    print(f"checkpoint: T_SEQ={ck['T_SEQ']}  {len(chans)} channels {chans}  seed {ck['seed']}")

    # Same defect as inference.py had: this defaulted to the GLORYS bundle, so every per-depth
    # sigma scale was fitted on errors the shipped model does not make.
    _bundle, _how = D.bundle_for_checkpoint(ck, a.checkpoint)
    print(f"bundle: {_bundle}  ({_how})")
    d = D.load_daily(_bundle)
    D.assert_bundle_matches_checkpoint(d, ck, "calibrate_uncertainty")
    if [str(c) for c in d["channels"]] != chans:
        raise SystemExit(
            f"checkpoint trained on {chans} but the bundle has {[str(c) for c in d['channels']]} -- "
            "calibrating across a channel mismatch would feed the model the wrong variables.")

    clim = np.load(base.art("climatology.npy"))
    norm = [np.asarray(v, dtype="float32") for v in ck["norm"]]
    ds = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                          np.arange(len(d["times"])), norm=norm, t_seq=ck["T_SEQ"], p=ck["P"],
                          max_samples=1, clim=clim, return_clim=True)

    torch.manual_seed(base.SEED)
    # built_t_seq, NOT T_SEQ. The encoder is CONSTRUCTED at t_seq=1 while T_SEQ is the DATA
    # window -- cnn3d sizes its AvgPool3d from the construction value, so building at
    # T_SEQ=11 makes a structurally different network that load_state_dict accepts without
    # complaint (conv weights do not encode temporal extent) and that silently predicts
    # differently. The checkpoint records built_t_seq precisely so no reader has to know.
    model = TSCastNIO(ck["encoder"], len(chans),
                      t_seq=int(ck.get("built_t_seq", 1)), p=ck["P"],
                      latent=ck["latent"], residual=ck["residual"],
                      unet_channels=tuple(ck.get("unet_channels", config.UNET_CHANNELS)),
                      decoder=ck.get("decoder", "simple"))
    # Refuse a wrongly-rebuilt architecture BEFORE loading. load_state_dict accepts a
    # t_seq mismatch silently -- conv weights do not encode temporal extent -- and the
    # model then predicts differently on identical input.
    assert_architecture_matches(model, ck, 'calibrate_uncertainty')
    model.load_state_dict(ck["state_dict"])

    argo = pd.read_parquet(base.art("argo_daily_period.parquet"))
    keys, truth = VA.pivot_profiles(argo)
    times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((times - x).astype("timedelta64[D]").astype(int)) for x in dts])
    near = offs.min(axis=1) <= MAX_DAYS
    t_idx = offs.argmin(axis=1)

    is_test = dts >= SPLIT
    fit_mask = near & ~is_test          # TRAIN-window Argo -> fit the scales
    eval_mask = near & is_test          # TEST-window Argo  -> report coverage
    print(f"calibration set: {int(fit_mask.sum())} profiles (before {SPLIT})")
    print(f"evaluation set : {int(eval_mask.sum())} profiles (on/after {SPLIT})")
    if fit_mask.sum() < 200 or eval_mask.sum() < 200:
        raise SystemExit("not enough profiles on one side of the split to calibrate honestly")

    y_std = norm[3]
    out = {}
    for name, m in (("fit", fit_mask), ("eval", eval_mask)):
        mu_z, lv_z = predict_at_argo(model, ds, keys, t_idx, m)
        out[name] = (mu_z * y_std + norm[2], np.sqrt(np.exp(lv_z)) * y_std, truth[m])

    mu_f, sig_f, y_f = out["fit"]
    mu_e, sig_e, y_e = out["eval"]

    # Both methods, side by side. They disagree on real data because the residuals are
    # heavy-tailed, and reporting only one would hide that.
    results = {}
    for meth in ("variance", "coverage"):
        f = calibrate.fit_scales(mu_f, sig_f, y_f, method=meth)
        sc = calibrate.apply_scales(sig_e, f["scales"])
        results[meth] = {"fit": f, "cov": calibrate.coverage(mu_e, sc, y_e),
                         "pit": calibrate.pit(mu_e, sc, y_e)}
        results[meth]["summary"] = calibrate.summarise(results[meth]["cov"])

    fitted = results["coverage"]["fit"]                    # the method section 11 asks for
    sig_e_cal = calibrate.apply_scales(sig_e, fitted["scales"])
    cov_before = calibrate.coverage(mu_e, sig_e, y_e)
    cov_after = results["coverage"]["cov"]
    s_before, s_after = calibrate.summarise(cov_before), results["coverage"]["summary"]

    print()
    print("  method     cov1    cov2    PIT dev   (targets 0.683 / 0.954 / 0)")
    print(f"  {'raw':10} {s_before['cov1_mean']:.3f}   {s_before['cov2_mean']:.3f}   "
          f"{calibrate.pit(mu_e, sig_e, y_e)['uniform_deviation']:.4f}")
    for meth in ("variance", "coverage"):
        r = results[meth]
        print(f"  {meth:10} {r['summary']['cov1_mean']:.3f}   {r['summary']['cov2_mean']:.3f}   "
              f"{r['pit']['uniform_deviation']:.4f}")

    print(f"\n{'depth':>6} {'n':>5} {'scale':>7} {'cov1 before':>12} {'cov1 after':>11} "
          f"{'cov2 after':>11}")
    for dep in config.DEPTHS:
        s = fitted["scales"][int(dep)]
        b, aft = cov_before[int(dep)], cov_after[int(dep)]
        st = f"{s:.3f}" if s is not None else "  --  "
        print(f"{dep:>6} {aft['n']:>5} {st:>7} "
              f"{('%.3f' % b['cov1']) if b['cov1'] is not None else '  --':>12} "
              f"{('%.3f' % aft['cov1']) if aft['cov1'] is not None else '  --':>11} "
              f"{('%.3f' % aft['cov2']) if aft['cov2'] is not None else '  --':>11}")

    print(f"\ncov1  before {s_before['cov1_mean']}  ->  after {s_after['cov1_mean']}   "
          f"(target 0.683)")
    print(f"cov2  before {s_before['cov2_mean']}  ->  after {s_after['cov2_mean']}   "
          f"(target 0.954)")
    pit_b = calibrate.pit(mu_e, sig_e, y_e)
    pit_a = calibrate.pit(mu_e, sig_e_cal, y_e)
    print(f"PIT uniform deviation  {pit_b['uniform_deviation']} -> {pit_a['uniform_deviation']} "
          f"(0 = perfect)")

    payload = {
        "what": "Post-hoc per-depth variance scaling. Scales FITTED on train-window Argo, "
                "coverage REPORTED on test-window Argo. The two are disjoint in time.",
        "checkpoint": os.path.basename(a.checkpoint),
        "T_SEQ": ck["T_SEQ"], "channels": chans, "seed": ck["seed"],
        "is_shipped_model": len(chans) == 7 and ck["T_SEQ"] == 11,
        "n_fit_profiles": int(fit_mask.sum()), "n_eval_profiles": int(eval_mask.sum()),
        "split": str(SPLIT), "max_days_offset": MAX_DAYS,
        "method_used": "coverage",
        "method_comparison": {m: {"summary": results[m]["summary"],
                                  "pit_uniform_deviation": results[m]["pit"]["uniform_deviation"],
                                  "scales": results[m]["fit"]["scales"]}
                              for m in results},
        "scales": fitted["scales"], "n_per_depth_fit": fitted["n"], "min_n": fitted["min_n"],
        "coverage_before": cov_before, "coverage_after": cov_after,
        "summary_before": s_before, "summary_after": s_after,
        "pit_before": pit_b, "pit_after": pit_a,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip(),
    }
    with open(a.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\nwrote {a.out}")
    if not payload["is_shipped_model"]:
        print("NOTE: this is NOT the shipped model (T_SEQ=11, 7 channels). The scaling method is "
              "model-agnostic; re-run against artifacts/frozen/ once Phase 1 lands.")


if __name__ == "__main__":
    main()
