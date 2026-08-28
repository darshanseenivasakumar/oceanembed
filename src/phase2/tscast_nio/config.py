"""TS-Cast-NIO tunable configuration.

Frozen SCIENTIFIC constants (grid, depths, region, seed) are NOT redefined here -- they are
imported from `oceanembed.config`, which is the single source of truth. This module holds only
what is genuinely a modelling choice.

The two that matter most:

    T_SEQ -- length of the daily input window. The paper uses 31 (+/-15 d).
             T_SEQ=1 collapses the temporal encoder and runs the whole stack on the existing
             48-month archive, so the model can be built and tested BEFORE the daily download
             finishes. Going daily is then a config change, not a rewrite.

    P     -- patch width in grid cells. 17 at 0.25 deg = +/-2.0 deg, matching the mesoscale-eddy
             extent the paper states (100-300 km). See tscast_data_model.md section 4 for why we
             match their stated physics rather than their cell count.
"""
from __future__ import annotations

from oceanembed import config as _base

# ---- re-exported frozen constants (import, never redefine) ------------------
DEPTHS = _base.DEPTHS
N_DEPTHS = _base.N_DEPTHS
LAT, LON = _base.LAT, _base.LON
N_LAT, N_LON = _base.N_LAT, _base.N_LON
REGION = _base.REGION
SEED = _base.SEED

# ---- input contract (tscast_data_model.md section 2) ------------------------
CHANNELS = ["sst", "sss", "ssh", "u", "v", "wu", "wv"]
CHANNEL_UNITS = ["degC", "psu", "m", "m s-1", "m s-1", "m s-1", "m s-1"]
N_CHANNELS = len(CHANNELS)

# ---- sampling window -------------------------------------------------------
T_SEQ = 31   # set to 1 to run on the monthly archive
P = 17       # patch width in cells; must be odd so the target cell is the centre

# ---- decoder ---------------------------------------------------------------
# The paper's 1-D U-Net does four stride-2 downsamples, which needs 128 levels. Our output
# contract is frozen at 15 depths, which cannot carry that. So the decoder works on an internal
# evenly-spaced grid and resamples to the 15 contract depths at the output head.
INTERNAL_LEVELS = 64
INTERNAL_DEPTH_RANGE = (0.0, 1000.0)
LATENT_DIM = 512      # h, as in the paper
UNET_CHANNELS = (64, 128, 256, 512)

# ---- training --------------------------------------------------------------
TRAIN = dict(epochs=250, lr=1e-5, batch_size=512, optimizer="adamw", val_fraction=0.2, n_ensemble=3)

# ---- stage gate ------------------------------------------------------------
# Stage 1 = temperature + log-variance. Stage 2 adds salinity + the EOS-80 density constraint.
# Stage 2 is not enabled until stage 1 is validated against real Argo.
STAGE = 1


def sanity_check() -> None:
    assert P % 2 == 1, f"P={P} must be odd so the target cell is the patch centre"
    assert T_SEQ >= 1, f"T_SEQ={T_SEQ} must be >= 1"
    assert len(CHANNELS) == len(CHANNEL_UNITS), "channel/unit lists disagree"
    assert N_DEPTHS == 15, f"N_DEPTHS={N_DEPTHS}; the output contract is frozen at 15"
    assert INTERNAL_LEVELS >= N_DEPTHS, "internal grid must be finer than the output contract"
    assert STAGE in (1, 2)


if __name__ == "__main__":
    sanity_check()
    print(f"tscast_nio config OK: {N_CHANNELS} channels, T_SEQ={T_SEQ}, P={P} "
          f"(+/-{(P//2)*REGION['step']:.2f} deg), {N_DEPTHS} output depths, stage {STAGE}")
