"""Sensor dropout. Owner: Unit A (Arjhun).

The failure this file exists to catch would not raise and would not look wrong. Mask after
normalisation, or mask to 0, and every "masked" pixel arrives at the encoder as the channel mean --
a perfectly plausible average-temperature pixel. RMSE barely moves, and the experiment reports "the
model is robust to 60% cloud cover" while having tested nothing at all.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.validation import dropout as DO

CHANNELS = ["sst", "sss", "ssh", "u", "v", "wu", "wv"]
ART = base.art("cloud_dropout.json")


def a_bundle(n_times=4, n_lat=10, n_lon=12):
    """A small bundle in PHYSICAL units, with a land block whose SST is already NaN."""
    rng = np.random.default_rng(0)
    s = rng.normal(28.0, 1.0, (n_times, n_lat, n_lon, len(CHANNELS))).astype("float32")
    land = np.zeros((n_lat, n_lon), bool)
    land[:3, :] = True
    s[:, land, 0] = np.nan
    return s, land


# ==================================================== masking is physical, and it lands

def test_masking_writes_nan_into_the_raw_array_not_zero():
    """0.0 in PHYSICAL units is 0 degC -- cold but real water. 0.0 in Z-space is the channel mean.
    Either would be a number the encoder happily believes. NaN is the only value that survives
    `__getitem__`'s `np.where(finite, ...)` as a deliberate gap."""
    s, land = a_bundle()
    out = DO.apply_cloud(s, CHANNELS, 0.5, land_mask=land, rng=np.random.default_rng(1))
    masked = out["surface"][..., 0]
    assert np.isnan(masked).any()
    assert not (masked == 0.0).any(), "a masked pixel was written as 0 degC, not as missing"


def test_only_the_named_channel_loses_data():
    """Cloud blinds infrared SST. SSS is microwave and SSH is altimetry; masking them would model
    a different failure and label it cloud."""
    s, land = a_bundle()
    out = DO.apply_cloud(s, CHANNELS, 0.9, land_mask=land, rng=np.random.default_rng(2))
    for k in range(1, len(CHANNELS)):
        assert np.array_equal(out["surface"][..., k], s[..., k], equal_nan=True), CHANNELS[k]


def test_the_input_array_is_not_mutated():
    """The caller needs the pristine array to rebuild the training normalisation."""
    s, land = a_bundle()
    before = s.copy()
    DO.apply_cloud(s, CHANNELS, 0.7, land_mask=land, rng=np.random.default_rng(3))
    assert np.array_equal(s, before, equal_nan=True)


def test_the_fraction_is_a_fraction_of_OCEAN_not_of_the_grid():
    """Counting land would let a 70% request blank far less than 70% of the water and plot the
    wrong x-axis -- the whole curve would be shifted and nothing would say so."""
    s, land = a_bundle()
    out = DO.apply_cloud(s, CHANNELS, 0.5, land_mask=land, rng=np.random.default_rng(4))
    n_ocean_per_step = int((~land).sum())
    assert out["n_masked"] == pytest.approx(0.5 * n_ocean_per_step * s.shape[0], rel=0.02)
    assert 0.45 < out["fraction_achieved"] < 0.55


def test_land_is_never_reported_as_masked():
    s, land = a_bundle()
    out = DO.apply_cloud(s, CHANNELS, 1.0, land_mask=land, rng=np.random.default_rng(5))
    assert not out["mask"][:, land].any(), "land has no SST to lose"


def test_both_fractions_are_reported_because_they_differ():
    """A bundle can already carry missing SST -- the real one NaNs its first row and column. So
    "what this run blanked" and "what is now missing" are different numbers, and reporting one as
    the other misstates the x-axis at the top end."""
    s, land = a_bundle()
    s[:, 5, :, 0] = np.nan                                   # a pre-existing gap in the ocean
    out = DO.apply_cloud(s, CHANNELS, 1.0, land_mask=land, rng=np.random.default_rng(6))
    assert out["already_missing"] > 0
    assert out["fraction_achieved"] < out["fraction_now_missing"]
    assert out["fraction_now_missing"] == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_an_impossible_fraction_raises(bad):
    s, land = a_bundle()
    with pytest.raises(ValueError):
        DO.apply_cloud(s, CHANNELS, bad, land_mask=land, rng=np.random.default_rng(7))


def test_an_unknown_channel_raises_rather_than_defaulting_to_the_first():
    """Silently masking channel 0 when the bundle order changed would blind the model to something
    other than SST and still call the result cloud cover."""
    s, land = a_bundle()
    with pytest.raises(KeyError, match="chlorophyll"):
        DO.apply_cloud(s, CHANNELS, 0.5, land_mask=land, rng=np.random.default_rng(8),
                       channel="chlorophyll")
    assert DO.channel_index(CHANNELS, "ssh") == 2


def test_a_different_mask_seed_gives_a_different_mask_but_the_same_count():
    """The spread across draws is the noise floor a degradation has to beat."""
    s, land = a_bundle()
    a = DO.apply_cloud(s, CHANNELS, 0.5, land_mask=land, rng=np.random.default_rng(11))
    b = DO.apply_cloud(s, CHANNELS, 0.5, land_mask=land, rng=np.random.default_rng(12))
    assert a["n_masked"] == b["n_masked"]
    assert not np.array_equal(a["mask"], b["mask"])


def test_cloud_is_drawn_independently_per_time_step():
    """One mask reused across the 11-day window would model a permanently blind pixel rather than
    weather, and would understate how much the window can recover."""
    s, land = a_bundle(n_times=6)
    out = DO.apply_cloud(s, CHANNELS, 0.4, land_mask=land, rng=np.random.default_rng(13))
    assert not np.array_equal(out["mask"][0], out["mask"][1])


# ==================================================== the finding the experiment rests on

def test_the_encoder_cannot_tell_a_gap_from_average_water():
    """`dataset.__getitem__` z-scores then replaces every non-finite value with 0.0, which IS the
    channel mean. So "no data" and "exactly average" arrive as the same number, and the `finite`
    companion mask the dataset computes is discarded on the very next line.

    This is the baseline the whole experiment measures against, so it is pinned: if the dataset
    ever gains real missing-data handling this fails and the page's framing must be rewritten.
    """
    mean, std = 28.0, 1.5
    patch = np.array([[27.0, np.nan], [mean, 29.5]])
    assert DO.masking_is_indistinguishable_from_mean_fill(patch, mean, std)

    # and the claim is about the SHIPPED dataset, not just this helper
    import ast
    src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                            "src/phase2/tscast_nio/dataset.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "finite" in names, "the dataset no longer computes a finite mask -- re-read this test"
    getitem = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "__getitem__")
    returned = [n for n in ast.walk(getitem) if isinstance(n, ast.Return)]
    assert returned and not any("finite" in ast.dump(n) for n in returned), (
        "the dataset now RETURNS its finite mask -- the model may be able to see gaps, so this "
        "experiment's central caveat is out of date")


# ==================================================== the recorded sweep

@pytest.mark.skipif(not os.path.exists(ART), reason="run scripts/phase2/run_cloud_dropout.py first")
def test_the_control_reproduces_the_checkpoints_own_recorded_rmse():
    """Without this, every degradation number is harness error rather than cloud."""
    with open(ART, encoding="utf-8") as f:
        r = json.load(f)
    assert r["control_agrees"] is True
    assert abs(r["control_rmse"] - r["recorded_rmse"]) < r["control_tolerance"]
    assert abs(r["control_rmse"] - 0.9078) < 1e-3, "the control is not the frozen deliverable"


@pytest.mark.skipif(not os.path.exists(ART), reason="run scripts/phase2/run_cloud_dropout.py first")
def test_masking_the_whole_sst_channel_materially_degrades_the_model():
    """THE test that the mask actually reached the model. A flat curve would mean it never did."""
    with open(ART, encoding="utf-8") as f:
        r = json.load(f)
    worst = r["by_fraction"][max(r["by_fraction"], key=float)]
    assert worst["delta_vs_control"] > 0.3, (
        f"blanking all SST costs only {worst['delta_vs_control']:+.4f} degC -- the mask is "
        f"probably not reaching the encoder")


@pytest.mark.skipif(not os.path.exists(ART), reason="run scripts/phase2/run_cloud_dropout.py first")
def test_the_curve_is_monotone_beyond_its_minimum():
    """It is NOT monotone overall -- light masking improves the score by cancelling a warm bias --
    so asserting monotonicity everywhere would fail on a real effect. Past the minimum it must
    rise, or the degradation is not a degradation."""
    with open(ART, encoding="utf-8") as f:
        r = json.load(f)
    xs = sorted(float(k) for k in r["by_fraction"])
    ys = [r["by_fraction"][f"{x:g}"]["mean_rmse"] for x in xs]
    start = xs.index(r["analysis"]["rmse_minimising_fraction"])
    tail = ys[start:]
    assert all(b >= a - 1e-9 for a, b in zip(tail, tail[1:])), tail


@pytest.mark.skipif(not os.path.exists(ART), reason="run scripts/phase2/run_cloud_dropout.py first")
def test_the_improvement_at_light_masking_is_real_and_is_explained_as_a_bias_cancellation():
    """Two things at once. The improvement must be bigger than the spread across mask draws, or it
    is noise and the page should not discuss it. And the explanation must hold: the model runs
    warm, and the RMSE minimum must sit near where the bias crosses zero. If those ever come apart
    the page's framing is wrong and needs rewriting, not relaxing.
    """
    with open(ART, encoding="utf-8") as f:
        r = json.load(f)
    a = r["analysis"]
    assert a["improvement_vs_control"] > 5 * a["seed_spread_at_minimum"], (
        "the dip is within the noise across mask draws -- do not explain it, drop it")
    assert a["control_bias"] > 0.05, "the warm bias the explanation depends on is not there"
    assert a["bias_zero_crossing_fraction"] is not None
    assert abs(a["bias_zero_crossing_fraction"] - a["rmse_minimising_fraction"]) < 0.15, (
        "the RMSE minimum and the bias zero-crossing have come apart; the cancellation story no "
        "longer explains the dip")
