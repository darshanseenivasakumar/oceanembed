"""Turn processed grids into model-ready samples: X/y/meta, norm_stats, land_mask.

OWNER: Unit B (Darshan). Pure numpy/pandas -> fully testable.

Writes to artifacts/ (see docs/DATA_CONTRACT.md):
  X_train.npy, X_test.npy      float32 (N, 11)  z-scored, FEATURES order
  y_train.npy, y_test.npy      float32 (N, 11)  temperature (deg C, real units)
  meta_train.*, meta_test.*    [lat, lon, date, month, cell_id]
  norm_stats.json              {feat_mean[11],feat_std[11],targ_mean[11],targ_std[11]}
  land_mask.npy                bool (100, 240)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from oceanembed import config
from oceanembed.utils import io, grids


def _rows_for_frame(t_idx, date, g) -> tuple[np.ndarray, np.ndarray, list]:
    """Build raw feature rows + target rows for all OCEAN cells of one time frame."""
    sst, sss, ssh = g["sst"][t_idx], g["sss"][t_idx], g["ssh"][t_idx]
    u, v, temp = g["u"][t_idx], g["v"][t_idx], g["temp"][t_idx]
    ocean = ~g["land_mask"] & ~np.isnan(sst)
    ii, jj = np.where(ocean)

    doy = pd.Timestamp(date).dayofyear
    sd, cd = grids.day_of_year_features(doy)

    X = np.empty((len(ii), config.N_FEAT), dtype="float32")
    y = np.empty((len(ii), config.N_DEPTHS), dtype="float32")
    meta = []
    for k, (i, j) in enumerate(zip(ii, jj)):
        la, lo = float(config.LAT[i]), float(config.LON[j])
        sl, cl, so, co = grids.latlon_features(la, lo)
        X[k] = [sst[i, j], sss[i, j], ssh[i, j], u[i, j], v[i, j], sl, cl, so, co, sd, cd]
        y[k] = temp[i, j, :]
        meta.append((la, lo, pd.Timestamp(date), int(pd.Timestamp(date).month),
                     grids.latlon_to_cell_id(la, lo)))
    return X, y, meta


def run(processed_path: str, write: bool = True) -> dict:
    g = dict(np.load(processed_path, allow_pickle=False))
    times = g["times"].astype("datetime64[D]")
    years = times.astype("datetime64[Y]").astype(int) + 1970

    X_all, y_all, meta_all, split_all = [], [], [], []
    for t_idx, (date, yr) in enumerate(zip(times, years)):
        X, y, meta = _rows_for_frame(t_idx, date, g)
        X_all.append(X); y_all.append(y); meta_all.extend(meta)
        split_all.append(np.full(len(X), "train" if yr in config.TRAIN_YEARS else "test"))

    X = np.concatenate(X_all); y = np.concatenate(y_all)
    split = np.concatenate(split_all)
    meta = pd.DataFrame(meta_all, columns=["lat", "lon", "date", "month", "cell_id"])

    # drop any rows with NaN target (e.g. cell shallower than 500 m or bad interp)
    good = ~np.isnan(y).any(axis=1)
    X, y, split, meta = X[good], y[good], split[good], meta.loc[good].reset_index(drop=True)

    tr, te = split == "train", split == "test"
    if tr.sum() == 0:
        raise ValueError("no TRAIN rows — check TRAIN_YEARS vs the data's time range")

    # Normalize features using TRAIN rows only; keep y in real units (targ stats for the model to use)
    feat_mean = X[tr].mean(axis=0); feat_std = X[tr].std(axis=0) + 1e-6
    targ_mean = y[tr].mean(axis=0); targ_std = y[tr].std(axis=0) + 1e-6
    Xn = ((X - feat_mean) / feat_std).astype("float32")

    stats = dict(feat_mean=feat_mean.tolist(), feat_std=feat_std.tolist(),
                 targ_mean=targ_mean.tolist(), targ_std=targ_std.tolist())

    result = dict(n_train=int(tr.sum()), n_test=int(te.sum()), stats=stats)
    if write:
        io.save_npy(Xn[tr], config.art("X_train.npy")); io.save_npy(y[tr], config.art("y_train.npy"))
        io.save_npy(Xn[te], config.art("X_test.npy"));  io.save_npy(y[te], config.art("y_test.npy"))
        io.save_table(meta.loc[tr].reset_index(drop=True), config.art("meta_train"))
        io.save_table(meta.loc[te].reset_index(drop=True), config.art("meta_test"))
        io.save_json(stats, config.art("norm_stats.json"))
        io.save_npy(g["land_mask"], config.art("land_mask.npy"))
        print(f"[build_samples] train={result['n_train']} test={result['n_test']} -> artifacts/")
    return result


if __name__ == "__main__":
    import os
    run(os.path.join(config.DATA_PROCESSED, "grids.npz"))
