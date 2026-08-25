"""F5 physics tests. Owner: Unit A (Arjhun).

SCIENTIFIC tests dominate here on purpose. A layer depth is a single number that always looks
plausible, so shape tests prove almost nothing about it. These check against published constants,
known ocean structure, and cases where the answer is analytically forced.
"""
from __future__ import annotations

import numpy as np
import pytest

from oceanembed import config
from phase2.physics import layers, ohc as ohc_mod
from phase2.physics.seawater import CP_SEAWATER, density, sigma_theta

D = config.N_DEPTHS
DEPTHS = np.asarray(config.DEPTHS, dtype="float64")


def profile(mld=50.0, surface_t=29.0, deep_t=9.0, surface_s=35.0, deep_s=35.0,
            halocline=None):
    """A two-layer profile: uniform mixed layer, then a linear decline to 1000 m.

    halocline : if set, salinity is fresh above it and `deep_s` below — a barrier-layer setup.
    """
    t = np.empty(D)
    s = np.full(D, deep_s, dtype="float64")
    for k, z in enumerate(DEPTHS):
        if z <= mld:
            t[k] = surface_t
        else:
            frac = (z - mld) / (1000.0 - mld)
            t[k] = surface_t + frac * (deep_t - surface_t)
        if halocline is not None:
            s[k] = surface_s if z <= halocline else deep_s
    return s, t


# ============================================================ EOS — published check values
@pytest.mark.parametrize("S,t,expected", [
    (0.0, 5.0, 999.96675),
    (35.0, 25.0, 1023.34300),      # the classic UNESCO check value
    (35.0, 0.0, 1028.10600),
    (0.0, 25.0, 997.04700),
])
def test_density_matches_published_unesco_values(S, t, expected):
    """Fifteen hand-entered coefficients are how a plausible-but-wrong number gets in."""
    assert abs(float(density(S, t)) - expected) < 1e-3


def test_sigma_theta_is_density_minus_1000():
    assert float(sigma_theta(35.0, 25.0)) == pytest.approx(float(density(35.0, 25.0)) - 1000.0)


def test_fresher_water_is_lighter():
    """Meghna/Ganges plume water must be markedly less dense than open-ocean water."""
    assert float(density(6.43, 29.0)) < float(density(35.0, 29.0)) - 15.0


def test_warmer_water_is_lighter_in_the_tropical_range():
    assert float(density(35.0, 29.0)) < float(density(35.0, 20.0))


def test_negative_salinity_yields_nan_not_a_number():
    """Unphysical input must not silently produce a density."""
    assert np.isnan(float(density(-1.0, 25.0)))


def test_density_preserves_nan():
    out = density(np.array([35.0, np.nan]), np.array([25.0, 25.0]))
    assert np.isfinite(out[0]) and np.isnan(out[1])


# ============================================================ MLD / ILD — forced answers
def test_mld_finds_a_known_mixed_layer():
    s, t = profile(mld=50.0)
    got = float(layers.mixed_layer_depth(s, t))
    assert got in (75.0, 100.0), f"MLD {got} should be the first level below the 50 m base"


def test_deeper_mixing_gives_deeper_mld():
    shallow = float(layers.mixed_layer_depth(*profile(mld=30.0)))
    deep = float(layers.mixed_layer_depth(*profile(mld=150.0)))
    assert deep > shallow


def test_a_fully_uniform_column_returns_nan_not_the_deepest_level():
    """'Unresolved' and 'as deep as our deepest level' are different claims."""
    s = np.full(D, 35.0)
    t = np.full(D, 29.0)
    assert np.isnan(float(layers.mixed_layer_depth(s, t)))
    assert np.isnan(float(layers.isothermal_layer_depth(t)))


def test_ild_uses_temperature_only():
    """Adding a halocline must not move the ILD; that is what makes the comparison meaningful."""
    plain = float(layers.isothermal_layer_depth(profile(mld=80.0)[1]))
    salty = float(layers.isothermal_layer_depth(profile(mld=80.0, halocline=20.0,
                                                        surface_s=25.0)[1]))
    assert plain == salty


# ============================================================ BARRIER LAYER — the BoB case
def test_barrier_layer_detected_in_a_bay_of_bengal_style_profile():
    """THE scientific case for using density rather than temperature in this basin.

    A fresh lid (Ganges-Brahmaputra-Meghna) over an isothermal layer: temperature says the
    mixed layer is deep, density says it is shallow, and the difference is the barrier layer
    that lets the surface keep warming under a cyclone.
    """
    s, t = profile(mld=120.0, halocline=30.0, surface_s=25.0, deep_s=35.0)
    mld = float(layers.mixed_layer_depth(s, t))
    ild = float(layers.isothermal_layer_depth(t))
    blt = float(layers.barrier_layer_thickness(s, t))

    assert mld < ild, f"density MLD ({mld}) must be shallower than temperature ILD ({ild})"
    assert blt > 0, "a fresh lid over an isothermal layer is a barrier layer"
    assert blt == pytest.approx(ild - mld)


def test_no_barrier_layer_without_salinity_stratification():
    """No fresh lid -> the two criteria should agree, so no barrier layer."""
    s, t = profile(mld=80.0, surface_s=35.0, deep_s=35.0)
    assert float(layers.barrier_layer_thickness(s, t)) == pytest.approx(0.0, abs=1e-9)


def test_temperature_only_mld_would_be_too_deep_in_the_plume():
    """Quantifies the error a temperature-only MLD would make where it matters most."""
    s, t = profile(mld=120.0, halocline=30.0, surface_s=25.0, deep_s=35.0)
    error_m = float(layers.isothermal_layer_depth(t)) - float(layers.mixed_layer_depth(s, t))
    assert error_m >= 50.0, (
        f"expected a large overestimate from ignoring salinity, got {error_m} m"
    )


def test_barrier_layer_is_never_negative():
    s, t = profile(mld=60.0, halocline=200.0, surface_s=36.5, deep_s=34.0)   # compensated
    blt = layers.barrier_layer_thickness(s, t)
    assert np.isnan(blt) or float(blt) >= 0.0


# ============================================================ THERMOCLINE
def test_thermocline_sits_below_the_mixed_layer():
    s, t = profile(mld=50.0)
    th = layers.thermocline(t)
    assert th["depth"] > 50.0
    assert th["gradient"] > 0.0


def test_thermocline_gradient_reports_weakness_rather_than_hiding_it():
    """A near-uniform column still yields a depth; the gradient is how a caller rejects it."""
    t = np.linspace(29.0, 28.9, D)
    assert layers.thermocline(t)["gradient"] < 1e-2


def test_sharper_thermocline_gives_a_larger_gradient():
    sharp = layers.thermocline(profile(mld=50.0, deep_t=5.0)[1])["gradient"]
    weak = layers.thermocline(profile(mld=50.0, deep_t=25.0)[1])["gradient"]
    assert sharp > weak


# ============================================================ OHC
def test_ohc_matches_an_analytic_isothermal_column():
    """Uniform T and S -> OHC = rho*cp*T*z exactly. Catches an integration or units slip."""
    S, T, z = 35.0, 20.0, 300.0
    s = np.full(D, S)
    t = np.full(D, T)
    expected = float(density(S, T)) * CP_SEAWATER * T * z / 1e9
    assert float(ohc_mod.ohc(s, t, 300.0)) == pytest.approx(expected, rel=1e-6)


def test_ohc_is_in_a_physically_plausible_range():
    """Tropical 0-300 m should land in single-digit GJ m-2, not 1e9 or 1e-9."""
    s, t = profile(mld=50.0)
    v = float(ohc_mod.ohc(s, t, 300.0))
    assert 1.0 < v < 50.0, f"{v} GJ m-2 is outside any plausible tropical range"


def test_warmer_column_holds_more_heat():
    warm = float(ohc_mod.ohc(*profile(surface_t=31.0)[::-1][::-1], max_depth_m=300.0))
    cool = float(ohc_mod.ohc(*profile(surface_t=26.0)[::-1][::-1], max_depth_m=300.0))
    assert warm > cool


def test_deeper_integration_accumulates_more_heat():
    s, t = profile(mld=50.0)
    assert float(ohc_mod.ohc(s, t, 700.0)) > float(ohc_mod.ohc(s, t, 300.0))


def test_a_column_that_does_not_reach_depth_returns_nan_not_a_partial_integral():
    """The Phase-1 shelf-extrapolation failure in a different costume."""
    s, t = profile(mld=50.0)
    t[DEPTHS > 200.0] = np.nan      # shelf: no water below 200 m
    s[DEPTHS > 200.0] = np.nan
    assert np.isnan(float(ohc_mod.ohc(s, t, 700.0)))
    assert np.isfinite(float(ohc_mod.ohc(s, t, 200.0))), "it should still resolve to 200 m"


def test_ohc_rejects_a_depth_not_on_the_grid():
    s, t = profile()
    with pytest.raises(AssertionError, match="must be one of"):
        ohc_mod.ohc(s, t, 250.0)


def test_constant_density_assumption_error_is_largest_in_fresh_water():
    """Measures the claim rather than asserting it: the assumption costs most in the plume."""
    plume_s, plume_t = profile(surface_s=25.0, deep_s=34.0, halocline=30.0)
    open_s, open_t = profile(surface_s=35.0, deep_s=35.0)

    e_plume = ohc_mod.density_assumption_error(plume_s, plume_t, 300.0)
    e_open = ohc_mod.density_assumption_error(open_s, open_t, 300.0)
    assert e_plume["mean_rel_diff"] > e_open["mean_rel_diff"], (
        "constant density should be worse where the water is fresher"
    )


def test_density_assumption_error_is_small_but_not_zero_in_the_open_ocean():
    """It is a real correction, not a rounding artifact — and not a dramatic one either."""
    s, t = profile(surface_s=35.0, deep_s=35.0)
    e = ohc_mod.density_assumption_error(s, t, 300.0)
    assert 1e-5 < e["mean_rel_diff"] < 0.05


# ============================================================ GRID-WIDE
def test_functions_broadcast_over_a_full_grid():
    rng = np.random.default_rng(config.SEED)
    shape = (8, 12, D)
    t = np.linspace(29.0, 9.0, D) + rng.normal(0, 0.1, shape)
    s = np.full(shape, 35.0) + rng.normal(0, 0.1, shape)

    assert layers.mixed_layer_depth(s, t).shape == shape[:-1]
    assert layers.isothermal_layer_depth(t).shape == shape[:-1]
    assert layers.barrier_layer_thickness(s, t).shape == shape[:-1]
    assert layers.thermocline(t)["depth"].shape == shape[:-1]
    assert ohc_mod.ohc(s, t, 300.0).shape == shape[:-1]


def test_land_cells_stay_nan_across_every_product():
    shape = (4, 5, D)
    t = np.broadcast_to(np.linspace(29.0, 9.0, D), shape).copy()
    s = np.full(shape, 35.0)
    t[0, 0, :] = np.nan
    s[0, 0, :] = np.nan

    assert np.isnan(layers.mixed_layer_depth(s, t)[0, 0])
    assert np.isnan(layers.isothermal_layer_depth(t)[0, 0])
    assert np.isnan(layers.thermocline(t)["depth"][0, 0])
    assert np.isnan(ohc_mod.ohc(s, t, 300.0)[0, 0])


def test_mismatched_shapes_are_rejected():
    with pytest.raises(AssertionError):
        layers.mixed_layer_depth(np.zeros((3, D)), np.zeros((3, D - 1)))
