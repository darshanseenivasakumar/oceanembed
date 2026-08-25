"""F5 — ocean heat content. Owner: Unit A (Arjhun).

    OHC(0 -> z) = integral_0^z  rho(S, theta) * cp * theta  dz        [J m-2]

Reported in GJ m-2 (1e9 J m-2), which puts tropical upper-ocean values in a readable 0-2 range
instead of ~1e9.

WHY THIS IS NOW HONEST, WHERE IT WOULD NOT HAVE BEEN
-----------------------------------------------------
The Phase-2 audit recorded OHC as computable "only under an assumed constant seawater density",
because subsurface salinity was believed missing. Unit B established that it was never missing —
the raw GLORYS files always carried `so` at 36 levels; Phase 1 simply took index 0
(AGENT_SYNC 2026-08-26). So rho is computed from real T and S.

That is not a cosmetic upgrade. Unit B measured a minimum salinity of **6.43 psu at
22.50 N, 91.25 E** — Meghna/Ganges discharge. Density there is roughly 20 kg m-3 lower than the
35-psu open-ocean value, about 2%. A constant-rho OHC would therefore have carried its LARGEST
error in the northern Bay of Bengal: the cyclone genesis region, and the exact cell the
observation-priority map already ranks first. The headline product would have been least accurate
under the headline location.

`ohc_constant_density` is kept for exactly one purpose: measuring that difference, so the claim
above is a number we produced rather than an assertion. It is not the default and never should be.

ASSUMPTIONS, NAMED
------------------
1. **cp = 3985 J kg-1 K-1**, constant. Conventional in OHC budgets; varies ~+-0.5% across our T/S
   range, small beside model error, but it is an assumption.
2. **theta is used both as the temperature in `rho` and as the temperature in `cp*theta`.** Strictly
   the heat content integrand uses temperature relative to a reference; a 0 degC reference is the
   usual convention and is what is used here, so values are absolute heat content, not anomalies.
   Differences between two OHC fields are unaffected by the choice.
3. **One-atmosphere density** (sigma_theta), not in-situ. Pressure raises in-situ density by
   roughly 0.4-0.5% at 1000 dbar, so integrating to 1000 m with surface-referenced density
   understates OHC by well under 1%. Documented rather than silently absorbed; TEOS-10 with a
   pressure term is the upgrade path if that matters.
4. **Trapezoidal integration on 15 non-uniform levels.** Resolution is finest where the gradient is
   steepest, which is the right place for it, but the thermocline is still only coarsely sampled.

BATHYMETRY
----------
Integration stops at the last level with real water. A profile that never reaches the requested
depth returns NaN — never a partial integral silently labelled as a full one, which is the
Phase-1 shelf-extrapolation failure in a different costume.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config
from phase2.physics.seawater import CP_SEAWATER, density

_DEPTHS = np.asarray(config.DEPTHS, dtype="float64")
J_PER_GJ = 1e9

# Open-ocean reference density, only for the constant-rho comparison.
REFERENCE_DENSITY = 1025.0


def _depth_index(max_depth_m: float) -> int:
    hits = np.where(_DEPTHS == float(max_depth_m))[0]
    assert len(hits) == 1, (
        f"max_depth_m must be one of {list(config.DEPTHS)}; got {max_depth_m}. Interpolating to an "
        "arbitrary depth would invent a level the data does not have."
    )
    return int(hits[0])


def _integrate(integrand: np.ndarray, k: int) -> np.ndarray:
    """Trapezoidal integral of `integrand` (..., 15) from the surface to level index k.

    NaN anywhere in 0..k means the column does not reach that depth -> NaN, not a partial sum.
    """
    seg = integrand[..., : k + 1]
    incomplete = ~np.isfinite(seg).all(axis=-1)
    total = np.trapezoid(np.nan_to_num(seg), x=_DEPTHS[: k + 1], axis=-1)
    return np.where(incomplete, np.nan, total)


def ohc(salinity, theta, max_depth_m: float = 300.0) -> np.ndarray:
    """Ocean heat content, GJ m-2, surface to `max_depth_m`, using real rho(S, theta).

    salinity : (..., 15) PSS-78
    theta    : (..., 15) POTENTIAL temperature, degC
    Returns  : (...,) GJ m-2, NaN where the column does not reach that depth.

    Default 300 m: deep enough to contain the tropical thermocline and the heat a cyclone can
    actually entrain, shallow enough that most of the domain resolves it. 700 m is the
    conventional climate-budget depth and is available by argument.
    """
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    assert S.shape == t.shape, f"salinity {S.shape} and theta {t.shape} must match"
    assert S.shape[-1] == config.N_DEPTHS, f"last axis must be {config.N_DEPTHS} depths"

    k = _depth_index(max_depth_m)
    with np.errstate(invalid="ignore"):
        integrand = density(S, t) * CP_SEAWATER * t
    return _integrate(integrand, k) / J_PER_GJ


def ohc_constant_density(theta, max_depth_m: float = 300.0,
                         rho: float = REFERENCE_DENSITY) -> np.ndarray:
    """OHC under an assumed constant density — the pre-salinity approximation.

    NOT the default. It exists so `density_assumption_error` can measure what assuming constant
    rho actually costs, rather than us asserting it matters.
    """
    t = np.asarray(theta, dtype="float64")
    assert t.shape[-1] == config.N_DEPTHS, f"last axis must be {config.N_DEPTHS} depths"

    k = _depth_index(max_depth_m)
    return _integrate(float(rho) * CP_SEAWATER * t, k) / J_PER_GJ


def density_assumption_error(salinity, theta, max_depth_m: float = 300.0,
                             rho: float = REFERENCE_DENSITY) -> dict:
    """How much a constant-density assumption would have cost, as a measured number.

    Returns absolute (GJ m-2) and relative (fraction) differences plus their spatial statistics,
    so the claim "this matters most in the freshwater-influenced Bay of Bengal" can be checked
    instead of believed.
    """
    real = ohc(salinity, theta, max_depth_m)
    approx = ohc_constant_density(theta, max_depth_m, rho)
    diff = approx - real
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = diff / real

    finite = np.isfinite(diff)
    return {
        "max_depth_m": float(max_depth_m),
        "assumed_density": float(rho),
        "abs_diff_GJ_m2": diff,
        "rel_diff": rel,
        "n_valid": int(finite.sum()),
        "mean_abs_diff": float(np.nanmean(np.abs(diff))) if finite.any() else float("nan"),
        "max_abs_diff": float(np.nanmax(np.abs(diff))) if finite.any() else float("nan"),
        "mean_rel_diff": float(np.nanmean(np.abs(rel))) if finite.any() else float("nan"),
        "max_rel_diff": float(np.nanmax(np.abs(rel))) if finite.any() else float("nan"),
    }
