"""The encoder must be able to tell a data gap from average water (audit finding #13).

`GriddedPatches` zero-fills NaN AFTER z-scoring, so a missing value and a value equal to the
channel mean look identical to the network. The module docstring promised a companion mask; until
2026-09-07 it was computed and discarded. These tests pin the mask that is now appended behind
`mask_channels=True`, prove the default path is untouched, and measure the size of the gap on the
shipped bundle so the finding is a number rather than a worry.
"""
import os

import numpy as np
import pytest
import torch

from phase2.tscast_nio import config, dataset as D
from phase2.tscast_nio.models.tscast import TSCastNIO, assert_architecture_matches


def _toy(n_t=6, n_lat=20, n_lon=30, n_c=5):
    rng = np.random.default_rng(0)
    surface = rng.normal(0, 1, (n_t, n_lat, n_lon, n_c)).astype("float32")
    temp = rng.normal(20, 3, (n_t, n_lat, n_lon, config.N_DEPTHS)).astype("float32")
    land = np.zeros((n_lat, n_lon), bool)
    times = np.array([f"20{19 + i // 12}-{i % 12 + 1:02d}-15" for i in range(n_t)],
                     dtype="datetime64[D]")
    return surface, temp, times, land, ["sst", "sss", "ssh", "u", "v"]


def _sample(ds, t, i, j):
    ds.index = np.array([[t, i, j]])
    return ds[0][0]                                  # x only


# ---------------------------------------------------------------- the default is untouched


def test_the_default_path_is_byte_identical_to_before():
    """The shipped checkpoint was trained without the mask. Off must mean off."""
    surface, temp, times, land, ch = _toy()
    surface[2, 10, 15, 1] = np.nan
    a = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5)
    b = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5,
                         mask_channels=False)
    xa, xb = _sample(a, 2, 10, 15), _sample(b, 2, 10, 15)
    assert xa.shape[0] == len(ch) and a.C_in == len(ch)
    assert torch.equal(xa, xb)


# ---------------------------------------------------------------- the mask


def test_a_missing_value_is_marked_and_a_mean_value_is_not():
    """The whole point: after z-scoring, a gap and a value at the channel mean are both 0.0. Only
    the mask separates them."""
    surface, temp, times, land, ch = _toy()
    surface[2, 10, 15, 1] = np.nan                       # a gap
    ref = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5)
    # a genuine observation exactly at the channel mean, so its z-score is 0.0 like the gap.
    # The sampler pads a COPY of the array at construction, so the value is written first and
    # the normalisation is pinned to `ref`'s, which makes the z-score exactly zero.
    surface[2, 10, 16, 1] = float(ref.mean[..., 1].squeeze())
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5,
                          norm=ref.norm, mask_channels=True)
    x = _sample(ds, 2, 10, 15)                           # patch centred on the gap
    C = len(ch)
    assert x.shape[0] == 2 * C and ds.C_in == 2 * C
    val, msk = x[:C], x[C:]
    centre = (0, 2, 2)                                   # (t, row, col) inside a 5x5 patch, T=1
    assert val[1][centre] == 0.0 and msk[1][centre] == 0.0, "the gap: filled AND marked"
    right = (0, 2, 3)
    assert abs(val[1][right]) < 1e-5 and msk[1][right] == 1.0, (
        "an observation at the mean: same value as the gap, but marked PRESENT")
    assert msk[0][centre] == 1.0, "the other channels at the gap cell were observed"


def test_land_and_off_grid_cells_are_marked_absent():
    surface, temp, times, land, ch = _toy()
    land[0:3, :] = True                                  # a coastline along the top
    surface[:, 0:3, :, :] = np.nan
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5,
                          mask_channels=True)
    x = _sample(ds, 1, 3, 0)                             # first ocean row, western edge
    C = len(ch)
    msk = x[C:]
    assert (msk[:, 0, :2, :] == 0.0).all(), "land rows inside the patch must read absent"
    assert (msk[:, 0, :, :2] == 0.0).all(), "off-grid padding west of 45E must read absent"
    assert (msk[:, 0, 2:, 2:] == 1.0).all(), "the ocean quadrant is present"


def test_the_mask_is_appended_not_interleaved():
    """Channel c's mask is channel C + c. A consumer that only reads the first C channels sees
    exactly what it saw before."""
    surface, temp, times, land, ch = _toy()
    plain = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5)
    masked = D.GriddedPatches(surface, temp, times, land, ch, np.arange(6), t_seq=1, p=5,
                              mask_channels=True)
    xp, xm = _sample(plain, 3, 8, 8), _sample(masked, 3, 8, 8)
    assert torch.equal(xp, xm[:len(ch)])


def test_input_channels_helper():
    assert D.input_channels(["a", "b", "c"], False) == 3
    assert D.input_channels(["a", "b", "c"], True) == 6


# ---------------------------------------------------------------- the guard on load


def test_a_masked_checkpoint_cannot_be_rebuilt_without_the_mask():
    """The old failure mode: build for len(channels), load a 2C checkpoint, get a shape error that
    names a tensor rather than the cause. The guard names the cause, before load."""
    chans = ["sst", "sss", "ssh", "u", "v", "wu", "wv"]
    narrow = TSCastNIO("cnn3d", 7, t_seq=1, p=config.P, latent=32, decoder="simple")
    wide = TSCastNIO("cnn3d", 14, t_seq=1, p=config.P, latent=32, decoder="simple")
    ck_masked = {"channels": chans, "mask_channels": True, "built_t_seq": 1}
    ck_plain = {"channels": chans, "built_t_seq": 1}
    with pytest.raises(ValueError, match="presence mask"):
        assert_architecture_matches(narrow, ck_masked, "test")
    with pytest.raises(ValueError, match="input channels"):
        assert_architecture_matches(wide, ck_plain, "test")
    assert_architecture_matches(wide, ck_masked, "test")
    assert_architecture_matches(narrow, ck_plain, "test")


def test_a_legacy_checkpoint_without_the_field_still_loads():
    """Checkpoints before 2026-09-07 carry no `mask_channels`. Absent means off, not unknown."""
    narrow = TSCastNIO("cnn3d", 7, t_seq=1, p=config.P, latent=32, decoder="simple")
    assert_architecture_matches(narrow, {"channels": list("abcdefg"), "built_t_seq": 1}, "test")


# ---------------------------------------------------------------- how big the gap is


@pytest.mark.skipif(not os.path.isdir("data/processed/daily_sat/v001"),
                    reason="the satellite bundle is not on this machine")
def test_how_much_average_water_the_shipped_encoder_was_fed():
    """Pinned so the size of the finding is written down: a fixed product coastline, present on
    every day of the bundle, not weather."""
    d = D.load_daily("data/processed/daily_sat/v001")
    S, land = d["surface"], np.asarray(d["land_mask"], bool)
    _tr, te = D.daily_split_indices(d["times"])
    nan = np.isnan(S[te][:, ~land, :])                    # (T_test, n_ocean, C)
    any_missing = nan.any(axis=2).mean()
    assert 0.054 < any_missing < 0.057, f"{any_missing:.4f}: expected ~5.5% of ocean cells"
    static = np.isnan(S).all(axis=0) & ~land[..., None]
    ever = np.isnan(S).any(axis=0) & ~land[..., None]
    for c in (0, 1, 2):                                   # sst, sss, ssh never vary by day
        assert static[..., c].sum() == ever[..., c].sum()
    water = np.asarray(d["valid_mask"])[..., 0]
    served_but_blind = int((ever.any(axis=-1) & ~land & water).sum())
    assert served_but_blind == 798, (
        f"{served_but_blind} cells where GLORYS has water but a satellite channel is absent")
