"""Train the 11 LightGBM boosters; save artifacts/lgbm_model.pkl (+ lgbm_quantiles.pkl).

OWNER: Unit A (Arjhun). Reproducible (fixed seed). Early stopping on a random val split -- for
STOPPING ONLY. The honest evaluation is the 2022 test set in scripts/run_slice.py.

Mirrors train_mlp.train() so run_slice.py can call either interchangeably.

Usage:
    python -m oceanembed.train.train_lgbm            # real artifacts (X_train.npy)
    python -m oceanembed.train.train_lgbm --fixtures # sample_*.npy, before the pipeline exists
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np

from oceanembed import config
from oceanembed.models.lgbm_baseline import (
    load_lgbm,
    predict_lgbm,
    quantile_uncertainty,
    save_lgbm,
    train_boosters,
)
from oceanembed.utils import io


def _load(fixtures: bool) -> tuple[np.ndarray, np.ndarray, str]:
    if fixtures:
        return (
            io.load_npy(config.art("sample_X.npy")).astype("float32"),
            io.load_npy(config.art("sample_y.npy")).astype("float32"),
            "FIXTURES (artifacts/sample_*.npy)",
        )
    return (
        io.load_npy(config.art("X_train.npy")).astype("float32"),
        io.load_npy(config.art("y_train.npy")).astype("float32"),
        "real artifacts (X_train.npy / y_train.npy)",
    )


def train(
    fixtures: bool = False,
    val_frac: float = 0.1,
    with_quantiles: bool = True,
    verbose: bool = True,
) -> dict:
    """Train the baseline. Returns a summary dict; writes artifacts/lgbm_model.pkl."""
    np.random.seed(config.SEED)

    X, y, source = _load(fixtures)
    assert len(X) == len(y), f"X/y row mismatch: {len(X)} vs {len(y)}"

    n_val = max(1, int(len(X) * val_frac))
    idx = np.random.permutation(len(X))
    va, tr = idx[:n_val], idx[n_val:]
    Xt, yt, Xv, yv = X[tr], y[tr], X[va], y[va]

    if verbose:
        print(f"data source : {source}")
        print(f"train/val   : {len(Xt)} / {len(Xv)} rows")
        print(f"model       : {config.N_DEPTHS} LightGBM boosters (one per depth), seed={config.SEED}")
        print("-" * 62)

    t0 = time.time()
    models = train_boosters(Xt, yt, Xv, yv)
    save_lgbm(models, config.art("lgbm_model.pkl"))

    quantiles = None
    if with_quantiles:
        q10 = train_boosters(Xt, yt, Xv, yv, alpha=0.1)
        q90 = train_boosters(Xt, yt, Xv, yv, alpha=0.9)
        quantiles = {"q10": q10, "q90": q90}
        save_lgbm(quantiles, config.art("lgbm_quantiles.pkl"))

    pred = predict_lgbm(models, Xv)
    rmse_by_depth = np.sqrt(((pred - yv) ** 2).mean(axis=0))
    clim_rmse = float(np.sqrt(((yt.mean(axis=0) - yv) ** 2).mean()))
    rmse = float(np.sqrt(((pred - yv) ** 2).mean()))

    summary = {
        "source": source,
        "rmse": rmse,
        "clim_rmse": clim_rmse,
        "skill_vs_clim": 1.0 - rmse / clim_rmse if clim_rmse > 0 else float("nan"),
        "rmse_by_depth": rmse_by_depth.astype(float).tolist(),
        "best_iterations": [int(b.best_iteration or 0) for b in models],
        "checkpoint": config.art("lgbm_model.pkl"),
        "seconds": round(time.time() - t0, 1),
    }

    if verbose:
        print(f"trained {len(models)} boosters in {summary['seconds']}s")
        print(f"  best_iteration per depth: {summary['best_iterations']}")
        print(f"saved: {summary['checkpoint']}")
        if quantiles:
            print(f"saved: {config.art('lgbm_quantiles.pkl')}  (q10/q90 backup uncertainty)")
        print("-" * 62)
        print("VAL RMSE per depth (degC)   [val split = stopping only, NOT the honest test]")
        for d, r in zip(config.DEPTHS, rmse_by_depth):
            print(f"  {d:5d} m : {r:6.3f}")
        print(f"  overall : {rmse:6.3f}   vs climatology {clim_rmse:6.3f}"
              f"   skill {summary['skill_vs_clim']:+.3f}")
        if quantiles:
            sigma = quantile_uncertainty(quantiles["q10"], quantiles["q90"], Xv)
            print(f"  quantile sigma-equivalent: mean {sigma.mean():.3f} degC "
                  f"({sigma.mean(axis=0)[0]:.3f} at 0 m -> {sigma.mean(axis=0)[-1]:.3f} at "
                  f"{config.DEPTHS[-1]} m)")
        if fixtures:
            print()
            print("=" * 62)
            print("FIXTURES -- synthetic. PLUMBING ONLY, never a reported result.")
            print("=" * 62)

    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Train the LightGBM baseline")
    p.add_argument("--fixtures", action="store_true", help="train on sample_*.npy")
    p.add_argument("--no-quantiles", action="store_true", help="skip the q10/q90 boosters")
    p.add_argument("--val-frac", type=float, default=0.1)
    args = p.parse_args()

    if not args.fixtures and not os.path.exists(config.art("X_train.npy")):
        raise SystemExit(
            "artifacts/X_train.npy not found. Run `python scripts/prepare_dataset.py` first,\n"
            "or use --fixtures to develop against artifacts/sample_*.npy.\n"
            "NOTE: prepare_dataset.py is currently BROKEN on a fresh clone -- "
            "src/oceanembed/data/ is excluded by .gitignore (see docs/HANDOFF.md)."
        )
    train(fixtures=args.fixtures, val_frac=args.val_frac, with_quantiles=not args.no_quantiles)


if __name__ == "__main__":
    main()
