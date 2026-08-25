"""Generate tiny SYNTHETIC fixtures so all three units can develop in parallel from Day 1.

These are FAKE numbers with the CORRECT shapes/dtypes/columns — for wiring code only, NOT science.
Real data (same shapes) replaces them later with zero code change.

Run:  python scripts/make_fixtures.py
Owner: Unit B (Darshan).
"""
from __future__ import annotations
import os
import sys
import numpy as np
import pandas as pd

# Allow running without `pip install -e .`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from oceanembed import config
from oceanembed.utils import io, grids

N = 500
RNG = np.random.default_rng(config.SEED)


def main() -> None:
    os.makedirs(config.ARTIFACTS, exist_ok=True)

    # Random grid cells + dates in the TRAIN period
    lats = RNG.choice(config.LAT, size=N)
    lons = RNG.choice(config.LON, size=N)
    dates = pd.to_datetime("2020-01-01") + pd.to_timedelta(RNG.integers(0, 365, size=N), unit="D")

    # Build X in FEATURES order with roughly plausible ranges (still synthetic!)
    X = np.zeros((N, config.N_FEAT), dtype="float32")
    X[:, 0] = RNG.uniform(24, 31, N)          # sst  (deg C)
    X[:, 1] = RNG.uniform(32, 37, N)          # sss  (psu)
    X[:, 2] = RNG.uniform(-0.3, 0.5, N)       # ssh  (m)
    X[:, 3] = RNG.uniform(-1, 1, N)           # u    (m/s)
    X[:, 4] = RNG.uniform(-1, 1, N)           # v    (m/s)
    for k in range(N):
        sl, cl, so, co = grids.latlon_features(float(lats[k]), float(lons[k]))
        sd, cd = grids.day_of_year_features(int(dates[k].dayofyear))
        X[k, 5:] = [sl, cl, so, co, sd, cd]

    # Build y: a synthetic monotonically-decreasing-with-depth temperature profile
    y = np.zeros((N, config.N_DEPTHS), dtype="float32")
    surface = X[:, 0]
    for d_idx, depth in enumerate(config.DEPTHS):
        decay = np.exp(-depth / 250.0)
        y[:, d_idx] = (surface - 6.0) * decay + 6.0 + RNG.normal(0, 0.2, N)

    cell_ids = np.array([grids.latlon_to_cell_id(float(la), float(lo)) for la, lo in zip(lats, lons)])
    meta = pd.DataFrame({
        "lat": lats.astype("float32"),
        "lon": lons.astype("float32"),
        "date": dates.astype("datetime64[ns]"),
        "month": dates.month.astype("int16"),
        "cell_id": cell_ids.astype("int32"),
    })

    io.save_npy(X, config.art("sample_X.npy"))
    io.save_npy(y, config.art("sample_y.npy"))
    saved_meta = io.save_table(meta, config.art("sample_meta"))

    print(f"[VERIFIED] wrote fixtures to {config.ARTIFACTS}")
    print(f"  sample_X.npy    shape={X.shape} dtype={X.dtype}")
    print(f"  sample_y.npy    shape={y.shape} dtype={y.dtype}")
    print(f"  {os.path.basename(saved_meta)}  rows={len(meta)} cols={list(meta.columns)}")


if __name__ == "__main__":
    main()
