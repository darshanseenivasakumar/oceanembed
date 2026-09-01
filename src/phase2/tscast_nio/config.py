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
# MEASURED, not chosen. The daily T_SEQ ablation (artifacts/tseq_ablation.json):
#     T_SEQ= 1  Argo RMSE 0.9096
#     T_SEQ=11  Argo RMSE 0.8529   <- winner, by 0.0567 over 1 and 0.0738 over 31
#     T_SEQ=31  Argo RMSE 0.9267   (the paper's window; worst at our data scale)
# This constant read 31 while every real run passed --t-seq 11 on the command line, so anything
# reading the default silently built a 31-day model that no experiment supports.
#
# CAVEAT [INFERRED, needs re-measuring]: all three legs predate the A1 embargo fix (1d3c135) and
# are leaky. Leakage scales with the window -- 0/304 train days at T_SEQ=1, 5 at 11, 15 at 31 --
# so the longer windows were the more flattered, and 31 still lost. Removing the leak should widen
# 11's lead over 31 and narrow it over 1. 11's margin over 1 (0.0567) is an order of magnitude
# larger than the leak effect measured so far, so the winner is expected to stand -- but that is a
# prediction, not a result, until the ablation is re-run.
T_SEQ = 11   # set to 1 to run on the monthly archive
P = 17       # patch width in cells; must be odd so the target cell is the centre

# ---- decoder ---------------------------------------------------------------
# The paper's 1-D U-Net does four stride-2 downsamples, which needs 128 levels. Our output
# contract is frozen at 15 depths, which cannot carry that. So the decoder works on an internal
# evenly-spaced grid and resamples to the 15 contract depths at the output head.
INTERNAL_LEVELS = 64
INTERNAL_DEPTH_RANGE = (0.0, 1000.0)

# SIZED FOR OUR DATA, NOT THE PAPER'S. The paper uses a 512-wide latent and a (64,128,256,512)
# U-Net, but it trains on 155,030 profiles spanning 27 years at 128 depth levels. We have 36
# MONTHLY timesteps and 15 levels.
#
# MEASURED: at the paper's widths the model is 7,118,474 parameters -- 519k encoder and 6.6M
# decoder, of which 3.0M is FiLM alone -- against 543,383 for the encoder+head the bake-off
# actually validated at 0.9891 degC. That is 13.1x the capacity on the same 100k samples, and it
# overfits by epoch 3 no matter what the loss does: beta-NLL removed the variance collapse (train
# NLL -1.0610 -> -0.2025) and the best epoch stayed at 3.
#
# So these are cut to roughly encoder scale. Restore the paper's widths when the daily bundle
# lands and there is data to justify them.
LATENT_DIM = 128
UNET_CHANNELS = (32, 64, 128)
PAPER_UNET_CHANNELS = (64, 128, 256, 512)   # kept for the record, and for the daily rerun

# ---- training --------------------------------------------------------------
# There is deliberately no TRAIN dict here. One used to sit at this line reading
# epochs=250, lr=1e-5, batch_size=512 -- values NOTHING in the codebase ever read, and which
# matched no run ever performed (the real defaults are 25 / 1e-3 / 256, in train_stage1.py's
# argparse). A "frozen constant" that no code imports and no experiment used is worse than an
# absent one: it reads as the contract while the CLI quietly decides. Training hyperparameters
# live in the training script's argparse and are recorded per-run in the metrics JSON.

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
