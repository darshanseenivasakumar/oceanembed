"""End-to-end vertical slice: data -> climatology baseline -> MLP -> metrics -> uncertainty.

Prints an HONEST comparison (MLP vs climatology on the 2022 test set) and appends to docs/EXPERIMENT_LOG.md.
NOTE: on the synthetic dataset the numbers are ILLUSTRATIVE (fake inputs); the pipeline is real. Real numbers
appear once real GLORYS data is used.

Run:  python scripts/run_slice.py
"""
from __future__ import annotations
import os, sys, datetime as dt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config  # noqa: E402
from oceanembed.utils import io  # noqa: E402
from oceanembed.climatology import build_climatology, climatology_predict  # noqa: E402
from oceanembed.validation.metrics import compute_metrics  # noqa: E402
from oceanembed.train import train_mlp  # noqa: E402
from oceanembed.models.mlp_profile import predict_mlp  # noqa: E402
from oceanembed.inference.uncertainty import mc_dropout_predict  # noqa: E402


def main() -> None:
    if not os.path.exists(config.art("X_train.npy")):
        raise SystemExit("Run `python scripts/prepare_dataset.py` first to build artifacts.")

    y_train = io.load_npy(config.art("y_train.npy"))
    y_test = io.load_npy(config.art("y_test.npy"))
    X_test = io.load_npy(config.art("X_test.npy"))
    meta_train = io.load_table(config.art("meta_train"))
    meta_test = io.load_table(config.art("meta_test"))

    print("== 1. climatology baseline ==")
    build_climatology(y_train, meta_train)
    y_clim = climatology_predict(meta_test)
    clim_m = compute_metrics(y_test, y_clim, y_clim=y_clim)
    print(f"   climatology  RMSE={clim_m['rmse']:.3f}C  MAE={clim_m['mae']:.3f}  R2={clim_m['r2']:.3f}")

    print("== 2. train MLP ==")
    model = train_mlp.train(verbose=True)

    print("== 3. evaluate MLP on 2022 test (honest) ==")
    y_pred = predict_mlp(model, X_test)
    mlp_m = compute_metrics(y_test, y_pred, y_clim=y_clim)
    print(f"   MLP          RMSE={mlp_m['rmse']:.3f}C  MAE={mlp_m['mae']:.3f}  R2={mlp_m['r2']:.3f}  "
          f"skill_vs_clim={mlp_m['skill_vs_clim']:+.3f}")
    verdict = "MLP BEATS climatology" if (mlp_m["skill_vs_clim"] or 0) > 0 else "climatology wins (report honestly!)"
    print(f"   -> {verdict}")
    # Per-depth skill vs climatology is more meaningful than raw RMSE: deep water is naturally less
    # variable, so a small deep RMSE does NOT by itself mean the model is skilful there.
    print("   per-depth  RMSE_mlp | RMSE_clim | skill (>0 = better than climatology):")
    for k, d in enumerate(config.DEPTHS):
        r_m = float(np.sqrt(np.nanmean((y_pred[:, k] - y_test[:, k]) ** 2)))
        r_c = float(np.sqrt(np.nanmean((y_clim[:, k] - y_test[:, k]) ** 2)))
        sk = 1 - r_m / r_c if r_c > 0 else float("nan")
        print(f"      {d:4d} m : {r_m:6.3f}C | {r_c:6.3f}C | {sk:+.3f}")

    print("== 4. MC-dropout uncertainty ==")
    mean, std = mc_dropout_predict(model, X_test[:2000])
    by_depth = std.mean(0)
    natural = np.nanstd(y_test, axis=0)  # natural variability of each depth level
    print("   depth |  MC std  | natural std | ratio (std / natural variability)")
    for k, d in enumerate(config.DEPTHS):
        ratio = by_depth[k] / natural[k] if natural[k] > 0 else float("nan")
        print(f"      {d:4d} m : {by_depth[k]:6.3f}C | {natural[k]:8.3f}C  | {ratio:.3f}")
    print("   NOTE: absolute MC std often SHRINKS with depth simply because deep water varies less."
          "\n   The honest diagnostic is the RATIO above and the per-depth skill in step 3.")

    # log
    synthetic = os.path.exists(os.path.join(config.DATA_RAW, "synthetic_glorys.nc"))
    line = (f"\n## slice {dt.datetime.now():%Y-%m-%d %H:%M}\n"
            f"model: MLPProfile{config.MLP['hidden']} dropout={config.MLP['dropout']} | dataset: "
            f"{'SYNTHETIC (illustrative)' if synthetic else 'REAL GLORYS'} | split: train{config.TRAIN_YEARS} test{config.TEST_YEARS} | seed: {config.SEED}\n"
            f"metrics: RMSE={mlp_m['rmse']:.3f} MAE={mlp_m['mae']:.3f} R2={mlp_m['r2']:.3f} "
            f"skill_vs_clim={mlp_m['skill_vs_clim']:+.3f} | clim_RMSE={clim_m['rmse']:.3f} | checkpoint: artifacts/mlp_model.pt\n")
    with open(os.path.join(config.ROOT, "docs", "EXPERIMENT_LOG.md"), "a", encoding="utf-8") as f:
        f.write(line)
    print("\n[logged to docs/EXPERIMENT_LOG.md]")


if __name__ == "__main__":
    main()
