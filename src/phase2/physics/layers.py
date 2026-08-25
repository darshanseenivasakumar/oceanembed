"""F5 — mixed layer, isothermal layer, barrier layer, thermocline. Owner: Unit A (Arjhun).

METHOD — threshold criteria from a 10 m reference (de Boyer Montegut et al. 2004)
---------------------------------------------------------------------------------
  de Boyer Montegut, Madec, Fischer, Lazar & Iudicone (2004), "Mixed layer depth over the global
  ocean: an examination of profile data and a profile-based climatology", JGR Oceans 109, C12003.
  https://doi.org/10.1029/2004JC002378

Two criteria, both from a near-surface reference at 10 m:

    MLD  — shallowest depth where  sigma_theta  exceeds  sigma_theta(10 m) + 0.03 kg m-3
    ILD  — shallowest depth where  |theta - theta(10 m)|  exceeds  0.2 degC

A 10 m reference is used rather than 0 m specifically to skip the diurnal skin layer.

WHY BOTH, AND WHY THAT MATTERS HERE MORE THAN ALMOST ANYWHERE
--------------------------------------------------------------
The two criteria disagree wherever SALINITY, not temperature, sets the stratification. Their
difference is the BARRIER LAYER:

    barrier layer thickness = ILD - MLD

A barrier layer is a salinity-stratified lid sitting inside an isothermal layer. It suppresses
the entrainment of cool water from below, so the surface keeps warming — which is why it is a
recognised control on cyclone intensification.

The northern Bay of Bengal has one of the strongest barrier layers in the world ocean, because of
Ganges-Brahmaputra-Meghna discharge. Unit B measured the signature directly in our own data:
[VERIFIED] minimum salinity **6.43 psu at 22.50 N, 91.25 E** (AGENT_SYNC 2026-08-26).

So a temperature-only MLD would be systematically too deep in exactly the region our
observation-priority map ranks highest (northern Bay of Bengal, 17.75-19.25 N / 85.75-93.75 E),
and in exactly the process — cyclone intensification — the project's impact story rests on.
Computing MLD from density rather than temperature is not a refinement here; it is the difference
between describing this basin and mis-describing it.

THERMOCLINE
-----------
Depth of maximum vertical temperature gradient |d(theta)/dz|, located on the discretised profile.
Reported with the gradient magnitude, because a "thermocline depth" from a weak, flat gradient is
not meaningful and the caller needs to be able to see that.

CONVENTIONS
-----------
Depths are positive-down metres from `config.DEPTHS`. Every function is NaN-safe: a cell with no
water at a level (bathymetry, `valid_mask`) stays NaN and is never filled. Profiles too shallow to
support a criterion return NaN rather than the deepest available level, because "the mixed layer
is at least this deep" and "the mixed layer is this deep" are different claims.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config
from phase2.physics.seawater import sigma_theta

# de Boyer Montegut et al. (2004) thresholds.
REF_DEPTH_M = 10.0
DENSITY_THRESHOLD = 0.03    # kg m-3
TEMP_THRESHOLD = 0.2        # degC

_DEPTHS = np.asarray(config.DEPTHS, dtype="float64")


def _ref_index() -> int:
    """Index of the 10 m reference level. Fails loudly if the depth axis ever changes."""
    hits = np.where(_DEPTHS == REF_DEPTH_M)[0]
    assert len(hits) == 1, (
        f"config.DEPTHS must contain exactly one {REF_DEPTH_M} m level for the de Boyer Montegut "
        f"reference; got {list(config.DEPTHS)}"
    )
    return int(hits[0])


def _first_crossing(exceeds: np.ndarray, ref_i: int) -> np.ndarray:
    """Depth of the first level below the reference where `exceeds` is True.

    exceeds : (..., n_depth) bool
    Returns (...,) float, NaN where the criterion is never met — which means "not resolved by
    this profile", not "as deep as the deepest level".
    """
    below = exceeds[..., ref_i + 1:]
    any_hit = below.any(axis=-1)
    first = np.argmax(below, axis=-1)                 # argmax of bool = first True
    depth = _DEPTHS[ref_i + 1:][first]
    return np.where(any_hit, depth, np.nan)


def mixed_layer_depth(salinity, theta) -> np.ndarray:
    """MLD, m — density criterion, sigma_theta(10 m) + 0.03 kg m-3.

    salinity : (..., 15) PSS-78
    theta    : (..., 15) POTENTIAL temperature, degC
    Returns  : (...,) metres, NaN where unresolved.

    Prefer this over `isothermal_layer_depth` wherever salinity stratification matters — which,
    in the Bay of Bengal, is most of the time.
    """
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    assert S.shape == t.shape, f"salinity {S.shape} and theta {t.shape} must match"
    assert S.shape[-1] == config.N_DEPTHS, f"last axis must be {config.N_DEPTHS} depths"

    ref_i = _ref_index()
    sig = sigma_theta(S, t)
    ref = sig[..., ref_i][..., None]
    with np.errstate(invalid="ignore"):
        exceeds = (sig - ref) > DENSITY_THRESHOLD
    exceeds &= np.isfinite(sig)                        # NaN must never count as a crossing
    return _first_crossing(exceeds, ref_i)


def isothermal_layer_depth(theta) -> np.ndarray:
    """ILD, m — temperature criterion, |theta - theta(10 m)| > 0.2 degC.

    Temperature only, so it ignores salinity stratification entirely. That is precisely why
    comparing it against the density MLD reveals the barrier layer.
    """
    t = np.asarray(theta, dtype="float64")
    assert t.shape[-1] == config.N_DEPTHS, f"last axis must be {config.N_DEPTHS} depths"

    ref_i = _ref_index()
    ref = t[..., ref_i][..., None]
    with np.errstate(invalid="ignore"):
        exceeds = np.abs(t - ref) > TEMP_THRESHOLD
    exceeds &= np.isfinite(t)
    return _first_crossing(exceeds, ref_i)


def barrier_layer_thickness(salinity, theta) -> np.ndarray:
    """ILD - MLD, m. Positive = a salinity-stratified barrier layer is present.

    Negative values are clipped to 0: a "negative barrier layer" is not a physical object, it
    means the density criterion outcropped deeper than the temperature one (compensated
    stratification), and reporting a negative thickness would invite it being plotted as if it
    meant something.
    """
    ild = isothermal_layer_depth(theta)
    mld = mixed_layer_depth(salinity, theta)
    with np.errstate(invalid="ignore"):
        return np.where(np.isfinite(ild) & np.isfinite(mld), np.maximum(ild - mld, 0.0), np.nan)


def thermocline(theta) -> dict:
    """Depth and strength of the maximum vertical temperature gradient.

    Returns {"depth": (...,) m, "gradient": (...,) degC m-1 as a POSITIVE magnitude}.

    The gradient is returned so a caller can reject a "thermocline" that is really a flat
    profile. A depth alone would look equally authoritative in both cases.
    """
    t = np.asarray(theta, dtype="float64")
    assert t.shape[-1] == config.N_DEPTHS, f"last axis must be {config.N_DEPTHS} depths"

    dt = np.diff(t, axis=-1)
    dz = np.diff(_DEPTHS)
    grad = np.abs(dt / dz)                              # (..., 14) at level midpoints
    mid = 0.5 * (_DEPTHS[:-1] + _DEPTHS[1:])

    all_nan = ~np.isfinite(grad).any(axis=-1)
    filled = np.where(np.isfinite(grad), grad, -np.inf)
    k = np.argmax(filled, axis=-1)

    depth = np.where(all_nan, np.nan, mid[k])
    strength = np.where(all_nan, np.nan, np.take_along_axis(grad, k[..., None], axis=-1)[..., 0])
    return {"depth": depth, "gradient": strength}
