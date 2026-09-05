"""Sensor dropout: what happens when the satellite cannot see. Owner: Unit A (Arjhun).

During the monsoon, thick cloud blinds infrared SST retrieval for days at a time over large parts
of this basin. The shipped model takes SST as its first channel and was trained on a bundle whose
`missing_data_policy` is "No imputation anywhere". So the honest question is not whether the model
degrades under cloud -- it is how fast, and whether SSH and wind carry enough signal to soften it.

THE ONE MISTAKE THAT WOULD MAKE THIS WHOLE EXPERIMENT MEANINGLESS
------------------------------------------------------------------
Masking AFTER normalisation, or masking to 0. In z-space 0.0 IS the channel mean, so a "masked"
pixel would arrive at the encoder as a perfectly plausible average-temperature pixel, RMSE would
barely move, and the result would read "the model is robust to 60% cloud cover". It would be
robust to nothing; the mask would never have reached it.

So masking happens HERE, in physical units, on the raw bundle array, before `GriddedPatches` ever
z-scores it.

AND THE THING THAT MAKES THAT SUBTLE: THE MODEL CANNOT TELL THE TWO APART ANYWAY
--------------------------------------------------------------------------------
`dataset.py:150-158` z-scores the patch and then does `np.where(finite, patch, 0.0)`. So a NaN
pixel becomes 0.0 -- the channel mean -- and a pixel that genuinely sits at the channel mean
becomes 0.0 as well. The encoder receives the same number for "I have no idea" and "average
water", and it has no companion mask to tell them apart: `dataset.py:156` computes a `finite` array
and line 157 immediately discards it, despite the module docstring promising it is kept "so a model
can learn to distrust those cells".

That is the baseline this experiment measures against, and it should be stated plainly rather than
discovered by a reader: the model is not degrading gracefully under missing data, it is being told
nothing and treating every gap as climatologically average water. `masking_is_indistinguishable_
from_mean_fill` asserts exactly that equivalence so the claim cannot rot.

WHY MASK THE TEST INPUT AND NOT THE TRAINING DATA
--------------------------------------------------
The normalisation must stay the one the checkpoint was trained under, or the experiment measures
two changes at once. Callers build the TRAIN dataset from the pristine array to recover `norm`,
and only the TEST dataset from the masked one -- which is also what cloud actually does: it arrives
at inference time, long after the weights were fitted.
"""
from __future__ import annotations

import numpy as np

#: The channel infrared cloud actually blinds. SSS is microwave (SMOS) and SSH is altimetry;
#: neither is stopped by cloud, and pretending otherwise would overstate the scenario.
DEFAULT_CHANNEL = "sst"


def channel_index(channels, name: str = DEFAULT_CHANNEL) -> int:
    """Position of a named channel, raising rather than defaulting to 0.

    Silently masking channel 0 when the bundle's channel order changed would blind the model to
    something other than SST and label the result "cloud cover".
    """
    names = [str(c) for c in channels]
    if name not in names:
        raise KeyError(f"no {name!r} channel in {names}")
    return names.index(name)


def cloud_mask(n_times: int, land_mask, fraction: float, *, rng) -> np.ndarray:
    """A (n_times, n_lat, n_lon) boolean: True where the sensor sees nothing.

    Drawn independently per time step, because cloud on consecutive days is a different field --
    a single mask reused across the T_SEQ window would model a permanently blind pixel rather than
    weather, and would understate how much the 11-day window can recover.

    LAND IS NEVER "MASKED". It carries no SST to lose, so counting it would let a 70% request mask
    only 23% of the actual ocean and report the wrong x-axis. `fraction` is a fraction of OCEAN.
    """
    if not 0.0 <= float(fraction) <= 1.0:
        raise ValueError(f"fraction={fraction}, expected 0..1")
    land = np.asarray(land_mask, dtype=bool)
    ocean = ~land
    out = np.zeros((int(n_times),) + land.shape, dtype=bool)
    n_ocean = int(ocean.sum())
    n_pick = int(round(float(fraction) * n_ocean))
    if n_pick == 0:
        return out
    idx = np.argwhere(ocean)
    for t in range(int(n_times)):
        chosen = idx[rng.choice(n_ocean, size=n_pick, replace=False)]
        out[t, chosen[:, 0], chosen[:, 1]] = True
    return out


def apply_cloud(surface, channels, fraction: float, *, land_mask, rng,
                channel: str = DEFAULT_CHANNEL) -> dict:
    """Return a COPY of the bundle's surface array with `fraction` of ocean SST blanked to NaN.

    surface : (n_times, n_lat, n_lon, n_channels) in PHYSICAL units, straight from `load_daily`.

    NaN, not zero and not the mean -- see the module docstring. The copy is deliberate: the caller
    needs the pristine array to build the training normalisation the checkpoint was fitted under.

    Returns {"surface", "mask", "n_masked", "n_ocean_cells", "fraction_requested",
             "fraction_achieved", "channel", "channel_index"} so the achieved fraction can be
    reported rather than assumed -- rounding to whole cells makes them differ at small fractions.
    """
    s = np.array(surface, dtype="float32", copy=True)
    if s.ndim != 4:
        raise ValueError(f"surface is {s.shape}, expected (n_times, n_lat, n_lon, n_channels)")
    k = channel_index(channels, channel)
    land = np.asarray(land_mask, dtype=bool)
    if s.shape[1:3] != land.shape:
        raise ValueError(f"surface grid {s.shape[1:3]} against land_mask {land.shape}")

    mask = cloud_mask(s.shape[0], land, fraction, rng=rng)
    before = np.isfinite(s[..., k])
    s[..., k][mask] = np.nan
    after = np.isfinite(s[..., k])
    lost = int((before & ~after).sum())
    n_ocean = int((~land).sum()) * s.shape[0]
    # TWO fractions, because they differ and only reporting one invites a wrong reading. The
    # bundle's own edge policy already leaves ~2% of ocean SST NaN (first lat row, first lon
    # column), so a 100% request can only newly blank ~97.6% -- while the fraction now MISSING is
    # the full 100%. `achieved` is what this run took away; `now_missing` is what the model sees.
    return {
        "surface": s, "mask": mask, "n_masked": lost, "n_ocean_cells": n_ocean,
        "fraction_requested": float(fraction),
        "fraction_achieved": (lost / n_ocean) if n_ocean else float("nan"),
        "fraction_now_missing": (int((~after & ~land[None]).sum()) / n_ocean) if n_ocean
                                else float("nan"),
        "already_missing": int((~before & ~land[None]).sum()),
        "channel": channel, "channel_index": k,
    }


def masking_is_indistinguishable_from_mean_fill(patch, mean, std) -> bool:
    """Does a NaN pixel reach the encoder as the same number as a mean-valued pixel? -> bool.

    It does, in the shipped `dataset.__getitem__`, and that is the finding this experiment rests
    on rather than a bug to fix here. A caller can assert it so the claim cannot quietly stop being
    true if the dataset ever gains real missing-data handling.
    """
    p = np.asarray(patch, dtype="float64")
    z = (p - np.asarray(mean, dtype="float64")) / np.asarray(std, dtype="float64")
    as_nan = np.where(np.isfinite(z), z, 0.0)

    filled = np.where(np.isfinite(p), p, np.asarray(mean, dtype="float64"))
    zf = (filled - np.asarray(mean, dtype="float64")) / np.asarray(std, dtype="float64")
    as_mean = np.where(np.isfinite(zf), zf, 0.0)
    return bool(np.allclose(as_nan, as_mean, equal_nan=True))
