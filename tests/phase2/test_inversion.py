"""Temperature-inversion engine (D-020) -- verified on synthetic profiles and fields.

No bundle, no download. NO tests/phase2/__init__.py.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from phase2.derived import inversion as INV
from phase2.derived import profile_features as PF

DEPTHS = np.asarray(config.DEPTHS, dtype="float64")


def _bob_winter_profile():
    # 0,5,10 m at 26.0 (cold fresh surface), warming to 26.8 at 50 m, thermocline below.
    return np.array([26.0, 26.0, 26.0, 26.3, 26.6, 26.8, 26.2, 25.0, 23.0, 21.5,
                     19.0, 15.0, 11.0, 8.0, 5.0])


def test_definition_constants_match_d020():
    assert INV.MAX_DEPTH_M == 150.0
    assert INV.THRESHOLD_DEGC == 0.2
    assert INV.SENSITIVITY_THRESHOLDS == (0.1, 0.2, 0.5)
    assert INV.NBOB_LAT == 15.0


def test_bay_of_bengal_winter_profile_is_detected_with_amplitude_and_depths():
    r = INV.inversion_amplitude(_bob_winter_profile(), DEPTHS)
    assert r["amplitude"] == pytest.approx(0.8)
    assert r["depth_max"] == 50.0
    assert r["depth_top"] == 0.0            # the FIRST level holding the shallower minimum
    assert r["thickness"] == 50.0
    assert r["reason"] == PF.OK


def test_monotone_cooling_profile_has_zero_amplitude_and_no_depths():
    t = np.linspace(29.0, 5.0, 15)
    r = INV.inversion_amplitude(t, DEPTHS)
    assert r["amplitude"] == 0.0
    assert np.isnan(r["depth_max"]) and np.isnan(r["depth_top"]) and np.isnan(r["thickness"])
    assert r["reason"] == PF.OK


def test_present_applies_the_threshold_and_treats_nan_as_absent():
    amp = np.array([0.8, 0.1, 0.2, np.nan, 0.0])
    assert INV.present(amp).tolist() == [True, False, True, False, False]
    assert INV.present(amp, threshold=0.1).tolist() == [True, True, True, False, False]
    assert INV.present(amp, threshold=0.5).tolist() == [True, False, False, False, False]


def test_nan_below_seafloor_does_not_stop_the_scan():
    t = _bob_winter_profile()
    t[7:] = np.nan                           # seafloor at ~90 m
    r = INV.inversion_amplitude(t, DEPTHS)
    assert r["amplitude"] == pytest.approx(0.8)
    assert r["depth_max"] == 50.0


def test_an_inversion_below_the_search_window_is_ignored():
    t = np.linspace(29.0, 5.0, 15)
    t[11] = t[10] + 0.6                      # warming at 300 m only
    assert INV.inversion_amplitude(t, DEPTHS)["amplitude"] == 0.0
    assert INV.inversion_amplitude(t, DEPTHS, max_depth_m=1000.0)["amplitude"] == pytest.approx(0.6)


def test_the_larger_of_two_inversions_wins_and_its_own_minimum_is_the_top():
    z = np.array([0.0, 5.0, 10.0, 20.0, 30.0, 50.0, 75.0])
    t = np.array([27.0, 26.5, 26.8, 26.0, 25.9, 26.5, 26.5])
    r = INV.inversion_amplitude(t, z)
    assert r["amplitude"] == pytest.approx(0.6)   # 26.5 at 50 m minus 25.9 at 30 m, not the 0.3 bump
    assert r["depth_max"] == 50.0
    assert r["depth_top"] == 30.0
    assert r["thickness"] == 20.0


def test_full_resolution_argo_axis_gives_the_same_amplitude():
    z = np.arange(0.0, 152.0, 2.0)
    t = np.where(z < 40, 26.0, np.where(z <= 60, 26.7, 26.7 - 0.1 * (z - 60)))
    r = INV.inversion_amplitude(t, z)
    assert r["amplitude"] == pytest.approx(0.7)
    assert r["depth_max"] == 40.0
    assert r["depth_top"] == 0.0


def test_too_few_levels_and_no_data_are_reported_not_scored():
    one = np.full(15, np.nan); one[0] = 26.0
    r = INV.inversion_amplitude(one, DEPTHS)
    assert np.isnan(r["amplitude"]) and r["reason"] == PF.TOO_FEW_LEVELS
    r = INV.inversion_amplitude(np.full(15, np.nan), DEPTHS)
    assert np.isnan(r["amplitude"]) and r["reason"] == PF.NO_DATA


def test_value_and_depth_length_mismatch_is_an_error():
    with pytest.raises(ValueError):
        INV.inversion_amplitude(np.zeros(14), DEPTHS)


def _random_field(rng, shape):
    base = 29.0 - 0.02 * DEPTHS                            # gentle cooling
    f = base + rng.normal(0.0, 0.4, size=shape + (15,))
    f[rng.random(shape + (15,)) < 0.15] = np.nan             # holes and seafloor
    f[..., -3:] = np.where(rng.random(shape + (3,)) < 0.5, np.nan, f[..., -3:])
    return f


def test_field_matches_the_reference_scan_column_by_column():
    rng = np.random.default_rng(0)
    f = _random_field(rng, (4, 5))
    out = INV.inversion_field(f, DEPTHS)
    for i in range(4):
        for j in range(5):
            ref = INV.inversion_amplitude(f[i, j], DEPTHS)
            for k in ("amplitude", "depth_max", "depth_top", "thickness"):
                a, b = out[k][i, j], ref[k]
                assert (np.isnan(a) and np.isnan(b)) or a == pytest.approx(b), (k, i, j, a, b)


def test_field_keeps_the_leading_shape_and_uses_config_depths_by_default():
    rng = np.random.default_rng(1)
    f = _random_field(rng, (3, 4, 5))
    out = INV.inversion_field(f)
    assert out["amplitude"].shape == (3, 4, 5)
    assert out["depth_max"].shape == (3, 4, 5)


def test_a_higher_threshold_never_finds_more_inversions():
    rng = np.random.default_rng(2)
    amp = INV.inversion_field(_random_field(rng, (20, 20)), DEPTHS)["amplitude"]
    counts = [INV.present(amp, threshold=th).sum() for th in INV.SENSITIVITY_THRESHOLDS]
    assert counts[0] >= counts[1] >= counts[2]


def test_region_labels_split_the_bay_at_15n_and_keep_the_basin_rules():
    lat = np.array([20.0, 10.0, 15.0, 15.0, 10.0])
    lon = np.array([90.0, 90.0, 90.0, 65.0, 79.0])
    assert INV.region_labels(lat, lon).tolist() == [
        INV.NORTH_BOB, INV.SOUTH_BOB, INV.NORTH_BOB, INV.ARABIAN_SEA, INV.UNASSIGNED]
    assert INV.REGIONS == (INV.NORTH_BOB, INV.SOUTH_BOB, INV.ARABIAN_SEA)
