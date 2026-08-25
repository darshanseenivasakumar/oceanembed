"""Generate tiny SYNTHETIC fixtures so all three units can develop in parallel from Day 1.

FAKE numbers with the CORRECT shapes/dtypes/columns -- for wiring code only, NOT science.
Real data (same shapes) replaces them with zero code change.

D-011 FIX (raised by Unit A): the previous version built the target as a pure function of SST,
    y[:,d] = (sst - 6) * exp(-depth/250) + 6 + noise
so ssh/sss/u/v/lat/lon/day-of-year were all DECOYS -- measured r(ssh, T) = -0.002..+0.041 at every
depth. Nothing exercised the multi-feature problem, and Unit C's panels rendered an ocean where SSH
did nothing.

Now the profile is built the way the real ocean actually encodes subsurface information:

    T(z) = T_deep + (T_surface - T_deep) * 0.5 * (1 + tanh((z_t - z) / w))

a two-layer profile whose THERMOCLINE DEPTH z_t is displaced by SSH (a positive sea-level anomaly
means a deeper thermocline -- warm water piled up, as in an anticyclonic eddy) and modulated
seasonally. So:
  * SST      sets the mixed-layer temperature      -> dominates near the surface
  * SSH      sets where the transition happens     -> dominates at THERMOCLINE depths
  * day-of-year shifts both seasonally
  * u, v     add a weak upwelling/downwelling tilt
  * SSS      stays only weakly informative -- honest, since salinity says little about temperature
This is still synthetic, but it is the right SHAPE of problem: a model must combine features, and
the hardest depths are the thermocline -- which is what we observe on real GLORYS too.

Run:  python scripts/make_fixtures.py
Owner: Unit B (Darshan).
"""
from __future__ import annotations
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from oceanembed import config
from oceanembed.utils import io, grids

N = 500
RNG = np.random.default_rng(config.SEED)

# Deep water is not constant: below the thermocline the NIO still varies spatially, and our real
# Argo shows ~7.98 degC at 1000 m. A constant T_DEEP made depths 500-1000 m PURE NOISE (r ~ 0.02),
# so nothing at those levels was learnable and deep-depth tests proved nothing. Deep temperature
# now varies weakly with latitude and SSH -- weak but real signal, which is the honest shape.
Z0 = 120.0            # mean thermocline depth (m)
SSH_TO_DEPTH = 180.0  # m of thermocline displacement per metre of SSH
WIDTH = 90.0          # thermocline sharpness (m)
NOISE = 0.15          # deg C observation noise


def main() -> None:
    os.makedirs(config.ARTIFACTS, exist_ok=True)

    lats = RNG.choice(config.LAT, size=N)
    lons = RNG.choice(config.LON, size=N)
    dates = pd.to_datetime("2020-01-01") + pd.to_timedelta(RNG.integers(0, 365, size=N), unit="D")
    doy = dates.dayofyear.to_numpy()
    seas = np.cos(2 * np.pi * (doy / 365.25))          # +1 in Jan, -1 in Jul

    # --- surface fields (the model's inputs) ---------------------------------
    sst = 28.5 - 0.12 * (lats - 5.0) + 1.2 * seas + RNG.normal(0, 0.4, N)
    ssh = 0.15 * seas + RNG.normal(0, 0.18, N)          # metres
    sss = 35.0 + 0.4 * np.sin(np.deg2rad(lats)) + RNG.normal(0, 0.3, N)
    u = RNG.normal(0, 0.35, N)
    v = RNG.normal(0, 0.35, N)

    # --- the physics that makes the features MATTER --------------------------
    # SSH displaces the thermocline; season modulates it; currents tilt it slightly.
    z_t = Z0 + SSH_TO_DEPTH * ssh + 25.0 * seas + 30.0 * v
    z_t = np.clip(z_t, 40.0, 400.0)

    # Weak, learnable deep structure (see note at T_DEEP above).
    t_deep = 8.0 - 0.05 * (lats - 5.0) + 0.6 * ssh + RNG.normal(0, 0.15, N)

    depths = np.asarray(config.DEPTHS, dtype="float64")[None, :]      # (1, D)
    shape_fn = 0.5 * (1.0 + np.tanh((z_t[:, None] - depths) / WIDTH))  # 1 above, 0 below
    y = (t_deep[:, None] + (sst[:, None] - t_deep[:, None]) * shape_fn
         + RNG.normal(0, NOISE, (N, config.N_DEPTHS))).astype("float32")

    # --- assemble X in FEATURES order ----------------------------------------
    X = np.zeros((N, config.N_FEAT), dtype="float32")
    X[:, 0], X[:, 1], X[:, 2], X[:, 3], X[:, 4] = sst, sss, ssh, u, v
    for k in range(N):
        sl, cl, so, co = grids.latlon_features(float(lats[k]), float(lons[k]))
        sd, cd = grids.day_of_year_features(int(doy[k]))
        X[k, 5:] = [sl, cl, so, co, sd, cd]

    cell_ids = np.array([grids.latlon_to_cell_id(float(la), float(lo)) for la, lo in zip(lats, lons)])
    meta = pd.DataFrame({
        "lat": lats.astype("float32"), "lon": lons.astype("float32"),
        "date": dates.astype("datetime64[ns]"), "month": dates.month.astype("int16"),
        "cell_id": cell_ids.astype("int32"),
    })

    io.save_npy(X, config.art("sample_X.npy"))
    io.save_npy(y, config.art("sample_y.npy"))
    saved_meta = io.save_table(meta, config.art("sample_meta"))

    print(f"[VERIFIED] wrote fixtures to {config.ARTIFACTS}")
    print(f"  sample_X.npy  shape={X.shape} dtype={X.dtype}  (RAW units)")
    print(f"  sample_y.npy  shape={y.shape} dtype={y.dtype}")
    print(f"  {os.path.basename(saved_meta)}  rows={len(meta)}")

    # D-011 acceptance check: SSH must now carry real information at depth.
    print("\n  feature-target correlation by depth (D-011 check):")
    print("    depth |  r(sst,T) | r(ssh,T) | r(sin_doy,T)")
    for d_i, d in enumerate(config.DEPTHS):
        r_sst = np.corrcoef(sst, y[:, d_i])[0, 1]
        r_ssh = np.corrcoef(ssh, y[:, d_i])[0, 1]
        r_doy = np.corrcoef(X[:, 9], y[:, d_i])[0, 1]
        print(f"    {d:5d} | {r_sst:+9.3f} | {r_ssh:+8.3f} | {r_doy:+11.3f}")
    print("    SSH should dominate at thermocline depths; SST near the surface.")


if __name__ == "__main__":
    main()
