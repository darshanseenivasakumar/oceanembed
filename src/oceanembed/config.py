"""OceanEmbed — single source of truth for frozen constants and paths.

Import from here; NEVER hardcode LAT/LON/DEPTHS/FEATURES anywhere else.
Owner: Unit B (Darshan). Changing the frozen scientific constants requires a team decision
(see docs/DECISIONS.md) — do not edit casually.
"""
from __future__ import annotations
import os
import numpy as np

# ----------------------------------------------------------------------------
# FROZEN scientific constants (region, grid, depths, features)
# ----------------------------------------------------------------------------
REGION = dict(lat_min=5.0, lat_max=30.0, lon_min=45.0, lon_max=105.0, step=0.25)

LAT = np.arange(REGION["lat_min"], REGION["lat_max"], REGION["step"]).astype("float32")   # 100
LON = np.arange(REGION["lon_min"], REGION["lon_max"], REGION["step"]).astype("float32")   # 240

# 15 levels to 1000 m — the Problem Statement depth requirement (docs/DECISIONS.md D-008).
# Spacing is fine near the surface (steep gradients / thermocline) and coarse below 500 m
# where the profile is smooth, so 15 levels resolve the structure that actually varies.
DEPTHS = [0, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 400, 500, 700, 1000]  # meters, 15 levels

FEATURES = [
    "sst", "sss", "ssh", "u", "v",
    "sin_lat", "cos_lat", "sin_lon", "cos_lon", "sin_doy", "cos_doy",
]  # 11 features, THIS order

N_LAT = len(LAT)          # 100
N_LON = len(LON)          # 240
N_DEPTHS = len(DEPTHS)    # 11
N_FEAT = len(FEATURES)    # 11

# ----------------------------------------------------------------------------
# Split (by TIME — never random-split adjacent cells/days)
# ----------------------------------------------------------------------------
TRAIN_YEARS = [2019, 2020, 2021]
TEST_YEARS = [2022]

# ----------------------------------------------------------------------------
# Reproducibility
# ----------------------------------------------------------------------------
SEED = 42

# ----------------------------------------------------------------------------
# Paths (relative to repo root)
# ----------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW = os.path.join(ROOT, "data", "raw")
DATA_PROCESSED = os.path.join(ROOT, "data", "processed")
ARTIFACTS = os.path.join(ROOT, "artifacts")

# Named artifact files (the shared "drop-box" — see docs/DATA_CONTRACT.md)
def art(name: str) -> str:
    return os.path.join(ARTIFACTS, name)

# ----------------------------------------------------------------------------
# Model hyperparameters (tunable; owned by Unit A but kept here for one source)
# ----------------------------------------------------------------------------
MLP = dict(hidden=(128, 128), dropout=0.2, lr=1e-3, epochs=100, batch_size=256, mc_passes=30)


def sanity_check() -> None:
    """Assert the frozen constants are internally consistent. Run at import time in tests."""
    assert N_LAT == 100, f"N_LAT={N_LAT}, expected 100"
    assert N_LON == 240, f"N_LON={N_LON}, expected 240"
    assert N_DEPTHS == 15, f"N_DEPTHS={N_DEPTHS}, expected 15"
    assert N_FEAT == 11, f"N_FEAT={N_FEAT}, expected 11"
    assert FEATURES[:5] == ["sst", "sss", "ssh", "u", "v"], "surface feature order changed"


if __name__ == "__main__":
    sanity_check()
    print(f"OceanEmbed config OK: grid {N_LAT}x{N_LON}, {N_DEPTHS} depths, {N_FEAT} features, seed {SEED}")
