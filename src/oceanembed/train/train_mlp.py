"""Train MLPProfile on z-scored X and z-scored y; save artifacts/mlp_model.pt.

OWNER: Unit A (Arjhun). Reproducible (fixed seed). Early stopping on a random val split (for stopping only;
the HONEST evaluation is the 2022 test set in scripts/run_slice.py).
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
from oceanembed import config
from oceanembed.utils import io
from oceanembed.models.mlp_profile import MLPProfile


def _seed(s: int = config.SEED):
    np.random.seed(s)
    torch.manual_seed(s)


def train(epochs: int = config.MLP["epochs"], patience: int = 8, val_frac: float = 0.1, verbose: bool = True):
    _seed()
    X = io.load_npy(config.art("X_train.npy")).astype("float32")
    y = io.load_npy(config.art("y_train.npy")).astype("float32")
    s = io.load_json(config.art("norm_stats.json"))
    tm, ts = np.asarray(s["targ_mean"], "float32"), np.asarray(s["targ_std"], "float32")
    yn = (y - tm) / ts  # train in normalized target space

    n = len(X)
    idx = np.random.permutation(n)
    n_val = int(n * val_frac)
    va, tr = idx[:n_val], idx[n_val:]

    Xt = torch.as_tensor(X[tr]); yt = torch.as_tensor(yn[tr])
    Xv = torch.as_tensor(X[va]); yv = torch.as_tensor(yn[va])

    model = MLPProfile()
    opt = torch.optim.Adam(model.parameters(), lr=config.MLP["lr"])
    loss_fn = nn.MSELoss()
    bs = config.MLP["batch_size"]

    best_val, best_state, bad = float("inf"), None, 0
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xt))
        for k in range(0, len(Xt), bs):
            b = perm[k:k + bs]
            opt.zero_grad()
            loss = loss_fn(model(Xt[b]), yt[b])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            vloss = float(loss_fn(model(Xv), yv))
        if vloss < best_val - 1e-5:
            best_val, best_state, bad = vloss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
        if verbose and (ep % 5 == 0 or bad == 0):
            print(f"  epoch {ep:3d}  val_mse(norm)={vloss:.4f}  best={best_val:.4f}")
        if bad >= patience:
            print(f"  early stop at epoch {ep} (best val_mse={best_val:.4f})")
            break

    model.load_state_dict(best_state)
    torch.save(model.state_dict(), config.art("mlp_model.pt"))
    print(f"[train_mlp] saved {config.art('mlp_model.pt')}  best_val_mse(norm)={best_val:.4f}")
    return model


if __name__ == "__main__":
    train()
