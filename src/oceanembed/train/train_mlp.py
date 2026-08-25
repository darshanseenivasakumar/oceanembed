"""Train MLPProfile; save artifacts/mlp_model.pt; log the run to docs/EXPERIMENT_LOG.md.

OWNER: Unit A (Arjhun).

Day 1 runs against Darshan's fixtures (artifacts/sample_*.npy). Day 3 swaps to the real
X_train/y_train/X_test/y_test .npy files -- SAME SHAPES, so no code change is needed.

Usage:
    python -m oceanembed.train.train_mlp --fixtures
    python -m oceanembed.train.train_mlp --real
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn

from oceanembed import config
from oceanembed.models.mlp_profile import MLPProfile


def set_seed(seed: int) -> None:
    """Reproducibility -- required by the Definition of Done."""
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_norm_stats(X_tr: np.ndarray, y_tr: np.ndarray) -> tuple[dict, str]:
    """Prefer Unit B's artifacts/norm_stats.json; otherwise derive from the TRAIN split only.

    Deriving from train only (never val/test) is what keeps the evaluation honest.
    Returns (stats, provenance) so the caller can log which path was taken.
    """
    path = config.art("norm_stats.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            s = json.load(fh)
        return s, f"norm_stats.json (Unit B) [{path}]"

    stats = {
        "feat_mean": X_tr.mean(axis=0).tolist(),
        "feat_std": X_tr.std(axis=0).tolist(),
        "targ_mean": y_tr.mean(axis=0).tolist(),
        "targ_std": y_tr.std(axis=0).tolist(),
    }
    return stats, "computed from TRAIN split (norm_stats.json absent -- Unit B has not shipped it)"


def zscore(a: np.ndarray, mean, std) -> np.ndarray:
    mean = np.asarray(mean, dtype="float32")
    std = np.clip(np.asarray(std, dtype="float32"), 1e-6, None)
    return ((a - mean) / std).astype("float32")


def load_data(use_fixtures: bool) -> tuple[np.ndarray, np.ndarray, str]:
    """Fixtures: one array split by row. Real: Unit B's pre-split train file (split by TIME)."""
    if use_fixtures:
        X = np.load(config.art("sample_X.npy")).astype("float32")
        y = np.load(config.art("sample_y.npy")).astype("float32")
        return X, y, "fixtures (artifacts/sample_*.npy)"

    X = np.load(config.art("X_train.npy")).astype("float32")
    y = np.load(config.art("y_train.npy")).astype("float32")
    return X, y, "real (artifacts/X_train.npy, y_train.npy)"


def main() -> None:
    p = argparse.ArgumentParser(description="Train MLPProfile")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--fixtures", action="store_true", help="train on sample_*.npy (Day 1)")
    src.add_argument("--real", action="store_true", help="train on X_train/y_train (Day 3)")
    p.add_argument("--epochs", type=int, default=config.MLP["epochs"])
    p.add_argument("--batch-size", type=int, default=config.MLP["batch_size"])
    p.add_argument("--lr", type=float, default=config.MLP["lr"])
    p.add_argument("--patience", type=int, default=15, help="early-stopping patience")
    p.add_argument("--val-frac", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=config.SEED)
    p.add_argument("--out", type=str, default=config.art("mlp_model.pt"))
    args = p.parse_args()

    use_fixtures = not args.real  # default to the safe path
    set_seed(args.seed)

    X, y, data_src = load_data(use_fixtures)
    assert X.shape[1] == config.N_FEAT, f"X has {X.shape[1]} cols, expected {config.N_FEAT}"
    assert y.shape[1] == config.N_DEPTHS, f"y has {y.shape[1]} cols, expected {config.N_DEPTHS}"
    assert len(X) == len(y), f"X/y row mismatch: {len(X)} vs {len(y)}"

    # Validation split.
    # NOTE: on FIXTURES a random row split is fine (they are synthetic). On REAL data the
    # train/test separation is done by Unit B BY TIME; this only carves a val slice out of train.
    n_val = max(1, int(len(X) * args.val_frac))
    idx = np.random.permutation(len(X))
    val_idx, tr_idx = idx[:n_val], idx[n_val:]
    X_tr, y_tr, X_val, y_val = X[tr_idx], y[tr_idx], X[val_idx], y[val_idx]

    stats, provenance = load_norm_stats(X_tr, y_tr)

    Xtr = torch.from_numpy(zscore(X_tr, stats["feat_mean"], stats["feat_std"]))
    ytr = torch.from_numpy(zscore(y_tr, stats["targ_mean"], stats["targ_std"]))
    Xva = torch.from_numpy(zscore(X_val, stats["feat_mean"], stats["feat_std"]))
    yva = torch.from_numpy(zscore(y_val, stats["targ_mean"], stats["targ_std"]))

    model = MLPProfile()
    model.set_norm_stats(**stats)
    # Stamp provenance into the checkpoint so a fixture-trained model can never be
    # mistaken for a real one downstream (docs/DECISIONS.md D-010).
    model.trained_on_fixtures.fill_(1.0 if use_fixtures else 0.0)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    print(f"data source : {data_src}")
    print(f"norm stats  : {provenance}")
    print(f"train/val   : {len(X_tr)} / {len(X_val)} rows")
    print(f"model       : {config.N_FEAT} -> {list(config.MLP['hidden'])} -> {config.N_DEPTHS}"
          f", dropout={config.MLP['dropout']}, seed={args.seed}")
    print("-" * 62)

    best_val, best_state, bad_epochs = float("inf"), None, 0
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr))
        epoch_loss, n_seen = 0.0, 0
        for i in range(0, len(Xtr), args.batch_size):
            b = perm[i : i + args.batch_size]
            opt.zero_grad()
            loss = loss_fn(model(Xtr[b]), ytr[b])
            loss.backward()
            opt.step()
            epoch_loss += loss.item() * len(b)
            n_seen += len(b)
        train_loss = epoch_loss / n_seen

        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(Xva), yva).item()

        if val_loss < best_val - 1e-5:
            best_val = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1

        if epoch == 1 or epoch % 10 == 0 or bad_epochs >= args.patience:
            print(f"epoch {epoch:4d} | train {train_loss:.5f} | val {val_loss:.5f}"
                  f"{'  <- best' if bad_epochs == 0 else ''}")

        if bad_epochs >= args.patience:
            print(f"early stop at epoch {epoch} (no val improvement for {args.patience})")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    torch.save(model.state_dict(), args.out)

    # Real-units validation RMSE per depth -- the number that actually means something.
    model.eval()
    with torch.no_grad():
        pred = model.denormalize(model(Xva)).numpy()   # Xva is already z-scored here
    rmse_per_depth = np.sqrt(((pred - y_val) ** 2).mean(axis=0))

    print("-" * 62)
    print(f"best val loss (z-scored MSE): {best_val:.5f}   [{time.time() - t0:.1f}s]")
    print(f"saved: {args.out}")
    print("val RMSE per depth (degC):")
    for d, r in zip(config.DEPTHS, rmse_per_depth):
        print(f"  {d:5d} m : {r:6.3f}")
    print(f"  overall : {rmse_per_depth.mean():6.3f}")
    if use_fixtures:
        print()
        print("=" * 62)
        print("FIXTURES -- synthetic data. PLUMBING ONLY, never a reported result.")
        print("Checkpoint stamped trained_on_fixtures=1; load_mlp() will warn.")
        print("MUST be retrained on real GLORYS before it backs the demo.")
        print("=" * 62)


if __name__ == "__main__":
    main()
