"""Turn processed grids into model-ready samples: X/y/meta, norm_stats, land_mask.

OWNER: Unit B (Darshan). Pure numpy/pandas -> fully testable.

Writes to artifacts/ (see docs/DATA_CONTRACT.md):
  X_train.npy, X_test.npy      float32 (N, 11)  RAW units, FEATURES order (D-009)
  y_train.npy, y_test.npy      float32 (N, 11)  temperature (deg C, real units)
  meta_train.*, meta_test.*    [lat, lon, date, month, cell_id]
  norm_stats.json              {feat_mean[11],feat_std[11],targ_mean[11],targ_std[11]}
  land_mask.npy                bool (100, 240)
  provenance.json              {source: synthetic|real-glorys, built, x_units} (D-018)
"""
from __future__ import annotations
import datetime as _dt
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

    # Stats come from TRAIN rows ONLY (never val/test) -- that is what keeps evaluation honest.
    # X is written in RAW units: the model owns the whole normalization transform (DECISIONS D-009),
    # so no caller can double-normalize or skip it. norm_stats.json carries the stats for whoever
    # needs them (train_mlp bakes them into the checkpoint's buffers).
    feat_mean = X[tr].mean(axis=0); feat_std = X[tr].std(axis=0) + 1e-6
    targ_mean = y[tr].mean(axis=0); targ_std = y[tr].std(axis=0) + 1e-6
    X = X.astype("float32")

    stats = dict(feat_mean=feat_mean.tolist(), feat_std=feat_std.tolist(),
                 targ_mean=targ_mean.tolist(), targ_std=targ_std.tolist())

    source = str(g["source"]) if "source" in g else "unknown"
    result = dict(n_train=int(tr.sum()), n_test=int(te.sum()), stats=stats, source=source)
    if write:
        io.save_npy(X[tr], config.art("X_train.npy")); io.save_npy(y[tr], config.art("y_train.npy"))
        io.save_npy(X[te], config.art("X_test.npy"));  io.save_npy(y[te], config.art("y_test.npy"))
        io.save_table(meta.loc[tr].reset_index(drop=True), config.art("meta_train"))
        io.save_table(meta.loc[te].reset_index(drop=True), config.art("meta_test"))
        io.save_json(stats, config.art("norm_stats.json"))
        io.save_npy(g["land_mask"], config.art("land_mask.npy"))
        # D-018: provenance lives IN the artifacts. artifacts/ is small and portable while
        # data/raw/ is large and gitignored, so anything that infers "is this synthetic?" from a
        # sibling file silently reads "real" the moment the artifacts are copied to a demo laptop.
        io.save_json({"source": source,
                      "built": _dt.datetime.now().isoformat(timespec="seconds"),
                      "x_units": "raw (model normalizes internally, DECISIONS D-009)",
                      "n_train": result["n_train"], "n_test": result["n_test"]},
                     config.art("provenance.json"))
        print(f"[build_samples] source={source} train={result['n_train']} test={result['n_test']} -> artifacts/")
    return result


if __name__ == "__main__":
    import os
    run(os.path.join(config.DATA_PROCESSED, "grids.npz"))
