"""Tests for the derived heat-content products (TCHP / OHC / D26).

Pure functions on synthetic profiles — no model, no bundle, no network. The analytic cases pin the
integration and the unit factor; the edge cases pin the "NaN not zero" and "0 when cold" rules that
separate an honest product from a plausible-looking wrong one.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from phase2.derived import heat_content as hc

D = np.asarray(config.DEPTHS, dtype="float64")
NZ = config.N_DEPTHS
CP, RHO = hc.CP_TCHP, hc.RHO_TCHP


# --------------------------------------------------------------------------- analytic

def test_tchp_constant_warm_column_matches_closed_form():
    # A constant 30 C column to 1000 m: excess = 4 C, integral = 4 * 1000 = 4000 C·m exactly,
    # so TCHP has a closed form independent of the trapezoid details.
    temp = np.full(NZ, 30.0)
    expected = CP * RHO * 4.0 * 1000.0 / hc._KJ_CM2         # = 1641.6 kJ/cm^2
    got = hc.tchp_from_profile(temp, D)
    assert abs(got - expected) < 1e-6


def test_d26_interpolates_between_bracketing_levels():
    # 28 C at 75 m (index 6), 24 C at 100 m (index 7): 26 C sits exactly halfway -> 87.5 m.
    temp = np.array([30, 30, 30, 29, 29, 29, 28, 24, 20, 18, 15, 12, 8, 6, 4], dtype="float64")
    assert D[6] == 75.0 and D[7] == 100.0
    assert abs(hc.d26_from_profile(temp, D) - 87.5) < 1e-9


def test_ohc_0_700_is_finite_and_positive_for_a_full_warm_column():
    temp = np.full(NZ, 20.0)
    v = hc.ohc_from_profile(temp, D, z_ref=700.0)
    assert np.isfinite(v) and v > 0


# --------------------------------------------------------------------------- edge cases

def test_cold_surface_gives_zero_tchp_not_nan():
    temp = np.full(NZ, 25.0)                                # SST below 26 -> no warm layer
    assert hc.tchp_from_profile(temp, D) == 0.0
    assert np.isnan(hc.d26_from_profile(temp, D))


def test_all_nan_profile_gives_nan_not_zero():
    temp = np.full(NZ, np.nan)
    assert np.isnan(hc.tchp_from_profile(temp, D))          # NEVER 0 — 0 would read as "cold"
    assert np.isnan(hc.d26_from_profile(temp, D))


def test_ohc_returns_nan_when_column_does_not_reach_zref():
    temp = np.full(NZ, 20.0)
    temp[D > 300] = np.nan                                  # column stops at 300 m
    assert np.isnan(hc.ohc_from_profile(temp, D, z_ref=700.0))


def test_warm_layer_below_a_cold_layer_is_not_counted():
    # Surface warm to ~30 m, cold at 50 m, warm again deep. TCHP is the SURFACE-connected layer
    # only, so D26 is the first downward crossing (between 30 and 50 m), not the deep re-warming.
    temp = np.array([29, 29, 29, 28, 27, 24, 27, 28, 27, 26, 20, 15, 10, 8, 5], dtype="float64")
    d26 = hc.d26_from_profile(temp, D)
    assert D[4] <= d26 <= D[5]                              # crossing between 30 m and 50 m


# --------------------------------------------------------------------------- unit sanity

def test_realistic_tropical_profile_is_in_physical_range():
    # A plausible pre-monsoon Arabian Sea profile: warm mixed layer, 26 C near ~90 m.
    temp = np.array([29.5, 29.4, 29.2, 28.8, 28.3, 27.4, 26.6, 25.5, 24.0, 22.5,
                     19.0, 15.0, 11.0, 9.0, 5.0], dtype="float64")
    tchp = hc.tchp_from_profile(temp, D)
    assert 20.0 <= tchp <= 120.0, tchp                     # kJ/cm^2, not 1e6 (unit-bug guard)


# --------------------------------------------------------------------------- field

def test_field_preserves_the_land_mask():
    # (2, 2, 15): one land cell all-NaN, the rest a warm column. NaN must propagate to every product.
    temp = np.full((2, 2, NZ), 29.0)
    temp[0, 0, :] = np.nan
    out = hc.heat_content_field({"temperature": temp, "provenance": {}, "date": "2026-05-15"})
    for key in ("tchp", "ohc_0_zref", "d26"):
        assert np.isnan(out[key][0, 0]), key               # land stays NaN, never 0
        assert np.isfinite(out[key][1, 1]), key            # ocean is a real number


def test_field_values_equal_the_scalar_at_each_cell():
    # The field must not be a second implementation that can drift from the scalar.
    rng = np.random.default_rng(0)
    temp = 26.0 + rng.normal(2.0, 3.0, size=(3, 3, NZ))
    out = hc.heat_content_field({"temperature": temp, "provenance": {}})
    for i in range(3):
        for j in range(3):
            s = hc.tchp_from_profile(temp[i, j], D)
            f = out["tchp"][i, j]
            assert (np.isnan(s) and np.isnan(f)) or abs(s - f) < 1e-9


# --------------------------------------------------------------------------- uncertainty

def test_uncertainty_is_zero_when_sigma_is_zero():
    # No input spread -> no output spread, and the point estimate is untouched.
    mean = np.array([29.5, 29.4, 29.2, 28.8, 28.3, 27.4, 26.6, 25.5, 24.0, 22.5,
                     19.0, 15.0, 11.0, 9.0, 5.0], dtype="float64")
    u = hc.integrated_uncertainty(mean, np.zeros(NZ), D, rng=np.random.default_rng(0))
    assert u["tchp_std"] < 1e-9      # zero up to floating-point noise
    assert u["ohc_std"] < 1e-9


def test_uncertainty_grows_with_sigma():
    mean = np.full(NZ, 28.0)
    small = hc.integrated_uncertainty(mean, np.full(NZ, 0.2), D, rng=np.random.default_rng(1))
    large = hc.integrated_uncertainty(mean, np.full(NZ, 1.0), D, rng=np.random.default_rng(1))
    assert large["tchp_std"] > small["tchp_std"] > 0


def test_uncertainty_band_brackets_the_point_estimate():
    mean = np.array([29.5, 29.4, 29.2, 28.8, 28.3, 27.4, 26.6, 25.5, 24.0, 22.5,
                     19.0, 15.0, 11.0, 9.0, 5.0], dtype="float64")
    point = hc.tchp_from_profile(mean, D)
    u = hc.integrated_uncertainty(mean, np.full(NZ, 0.5), D, rng=np.random.default_rng(2))
    assert u["tchp_p10"] <= point <= u["tchp_p90"]


def test_uncertainty_carries_the_independence_caveat():
    # The lower-bound caveat must travel with the number, not live only in a docstring.
    u = hc.integrated_uncertainty(np.full(NZ, 28.0), np.full(NZ, 0.3), D,
                                  rng=np.random.default_rng(3))
    assert "lower bound" in u["assumption"].lower()


def test_uncertainty_all_nan_profile_is_nan_not_zero():
    u = hc.integrated_uncertainty(np.full(NZ, np.nan), np.full(NZ, 0.5), D,
                                  rng=np.random.default_rng(4))
    assert np.isnan(u["tchp_std"])
    assert u["n_samples"] == {"tchp": 0, "d26": 0, "ohc": 0}   # dict in every case, never a bare int


def test_nan_gap_does_not_invent_a_deep_warm_layer():
    # A NaN at 50 m with warm water above AND below must NOT push D26 to the deepest valid level and
    # let TCHP integrate a warm triangle across the gap (that produced 634 kJ/cm^2 before the fix).
    # D26 is bounded by the deepest depth we KNOW is warm (30 m here), not the seafloor.
    temp = np.full(NZ, 29.0)
    temp[5] = np.nan                                    # 50 m missing; 0–30 m warm, 75 m+ warm
    d26 = hc.d26_from_profile(temp, D)
    assert d26 == D[4], d26                             # 30 m — the deepest contiguous-warm level
    tchp = hc.tchp_from_profile(temp, D)
    assert 0.0 < tchp < 120.0, tchp                     # physical, not the 634 the gap used to give
