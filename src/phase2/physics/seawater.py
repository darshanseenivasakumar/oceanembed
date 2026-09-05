"""One-atmosphere equation of state for seawater. Owner: Unit A (Arjhun).

WHY THIS EXISTS RATHER THAN A DEPENDENCY
----------------------------------------
`gsw` (TEOS-10) is the modern standard and would be the right choice for publication. It is not
installed, and `requirements.txt` belongs to Unit B, so adding a team-wide dependency is not
Unit A's call. Everything F5 needs is the ONE-ATMOSPHERE part of EOS-80 — potential density
anomaly sigma_theta — which is a closed-form polynomial in (S, theta) with no pressure terms.
That is ~20 lines, fully citable, and needs nothing installed.

  UNESCO (1983), *Algorithms for computation of fundamental properties of seawater*,
  UNESCO Technical Papers in Marine Science 44.
  Millero, F. J. & Poisson, A. (1981), "International one-atmosphere equation of state of
  seawater", Deep-Sea Research A 28(6), 625-629.
  Quoted standard error of the fit: 3.6e-3 kg m-3 over 0-40 degC, S 0.5-43.

VERIFIED, NOT ASSUMED
---------------------
Fifteen hand-entered coefficients are exactly how a plausible-but-wrong number enters a pipeline,
which is the failure mode this project has hit four times. So the coefficients are checked against
published values in `tests/phase2/test_physics.py`, all agreeing to < 1e-3 kg m-3:

    rho(S=0,  t=5 )  =  999.96675
    rho(S=35, t=25)  = 1023.34300      <- the classic UNESCO check value
    rho(S=35, t=0 )  = 1028.10600
    rho(S=0,  t=25)  =  997.04700

POTENTIAL TEMPERATURE — why no conversion is needed
---------------------------------------------------
sigma_theta is defined from POTENTIAL temperature. GLORYS' `thetao` is
`sea_water_potential_temperature` already, so it feeds straight in. Passing in-situ temperature
instead would bias density at depth; the docstring of every public function says which it wants.

DELIBERATE LIMITATION
---------------------
This is the one-atmosphere form. It gives sigma_theta (potential density anomaly referenced to the
surface), which is what the mixed-layer criterion of de Boyer Montegut et al. (2004) is defined on.
It is NOT in-situ density at 1000 dbar — for that the pressure-dependent secant bulk modulus is
required. `ohc` therefore documents which density it uses and why the error is small.
"""
from __future__ import annotations

import numpy as np

# Specific heat capacity of seawater at constant pressure, J kg-1 K-1.
# 3985 is the conventional value used in ocean heat content budgets (e.g. IPCC AR6, Levitus et al.).
# cp varies by roughly +-0.5% over the T/S range of the tropical North Indian Ocean, which is small
# beside our model error, but it is an assumption and is named here rather than buried.
CP_SEAWATER = 3985.0


def _density_core(S, t):
    """The EOS-80 polynomial itself, written ONCE.

    Uses only +, -, * and ** , which numpy arrays and torch tensors evaluate identically, so
    `density` (numpy, for analysis) and `density_torch` (autograd, for the eq. 5 loss) are the
    SAME fifteen coefficients rather than two transcriptions that could drift. A second hand-entry
    of these coefficients is exactly how a plausible-but-wrong number enters a pipeline, and
    `test_physics.py` pins the two backends to each other as well as to the published values.
    """
    # Pure-water density (Bigg 1967, as adopted by UNESCO 1983).
    rho_w = (999.842594
             + 6.793952e-2 * t
             - 9.095290e-3 * t ** 2
             + 1.001685e-4 * t ** 3
             - 1.120083e-6 * t ** 4
             + 6.536336e-9 * t ** 5)

    A = (8.24493e-1
         - 4.0899e-3 * t
         + 7.6438e-5 * t ** 2
         - 8.2467e-7 * t ** 3
         + 5.3875e-9 * t ** 4)
    B = (-5.72466e-3
         + 1.0227e-4 * t
         - 1.6546e-6 * t ** 2)
    C = 4.8314e-4

    # S**1.5 is NaN for negative S, which is the desired behaviour: negative salinity is
    # unphysical and must not silently produce a density.
    return rho_w + A * S + B * S ** 1.5 + C * S ** 2


def density(salinity, theta):
    """One-atmosphere seawater density, kg m-3. EOS-80 / UNESCO (1983).

    salinity : PSS-78 (practical salinity)
    theta    : POTENTIAL temperature, degC  (GLORYS `thetao` — do not pass in-situ T)

    Broadcasting, NaN-preserving. Land/no-water cells stay NaN rather than becoming a number.
    """
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    with np.errstate(invalid="ignore"):
        return _density_core(S, t)


def density_torch(salinity, theta):
    """The same EOS-80 density, differentiable, for TS-Cast eq. 5.

    salinity : PSS-78, torch tensor
    theta    : POTENTIAL temperature degC, torch tensor

    The paper computes density from the PREDICTED (T, S) and compares it to density from the
    truth, so gradients must flow back through the polynomial into both heads — which is the
    entire point of the constraint. A numpy round-trip would silently detach them and the term
    would train nothing.

    NEGATIVE SALINITY: `S ** 1.5` is NaN there under both backends, and a NaN loss poisons every
    gradient in the batch, not just its own element. Early in training the salinity head can and
    does emit negatives, so the caller must clamp before calling this. `density_nll` does.
    """
    return _density_core(salinity, theta)


def sigma_theta(salinity, theta):
    """Potential density anomaly, kg m-3: density(S, theta) - 1000.

    This is the quantity the de Boyer Montegut et al. (2004) density criterion for mixed-layer
    depth is defined on.
    """
    return density(salinity, theta) - 1000.0


# ----------------------------------------------------------------- sound speed

#: Mackenzie's stated validity envelope: 0-30 degC, 30-40 PSS-78, 0-8000 m.
#: The North Indian Ocean 0-1000 m sits inside it everywhere except the very coldest
#: deep water, which is ~4 degC and still in range. Named rather than silently assumed.
SOUND_SPEED_VALID = {"theta_c": (0.0, 30.0), "salinity": (30.0, 40.0), "depth_m": (0.0, 8000.0)}


def sound_speed(salinity, theta, depth_m):
    """Speed of sound in seawater, m s-1. Mackenzie (1981), the 9-term equation.

    salinity : PSS-78 (practical salinity)
    theta    : temperature, degC -- see the POTENTIAL TEMPERATURE note below
    depth_m  : depth, metres (Mackenzie is written in depth, NOT pressure)

    Argument order is (S, theta, z) to match `density` and `sigma_theta` in this module and
    `mixed_layer_depth` / `barrier_layer_thickness` in layers.py. Every public function in this
    package takes salinity first; a sound-speed function that took temperature first would be the
    one exception, and a caller who guessed from the formula's usual textbook ordering c(T,S,z)
    would get a plausible wrong number rather than an error. Verified: swapping the first two
    arguments at the canonical check point moves the answer by 10.7 m s-1 and raises no exception.

      Mackenzie, K. V. (1981), "Nine-term equation for sound speed in the oceans",
      J. Acoust. Soc. Am. 70(3), 807-812.

    VERIFIED, NOT ASSUMED
    ---------------------
    Nine hand-entered coefficients, the same failure mode the EOS-80 block above guards against.
    Pinned in tests/phase2/test_physics.py against the published check value:

        c(S=35, theta=25, z=1000) = 1550.744 m s-1     <- Mackenzie's own worked check

    POTENTIAL TEMPERATURE -- an approximation, stated
    -------------------------------------------------
    Mackenzie is defined on IN-SITU temperature. This project carries GLORYS `thetao`, which is
    POTENTIAL temperature, and no in-situ conversion exists here. Over 0-1000 m in the tropics the
    adiabatic difference is ~0.1 degC, and dc/dtheta is ~4.1 m s-1 per degC at depth, so this
    contributes ~0.4 m s-1 -- an order below the 1480-1545 m s-1 range the profile spans, but NOT
    zero. It is an approximation, and any panel quoting an absolute sound speed says so.

    Broadcasting, NaN-preserving: land and below-seafloor cells stay NaN rather than becoming a
    number. Outside SOUND_SPEED_VALID the polynomial extrapolates silently -- it does not raise --
    so a caller feeding it fresh water gets a number that is not seawater sound speed.
    """
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    z = np.asarray(depth_m, dtype="float64")
    ds = S - 35.0
    with np.errstate(invalid="ignore"):
        return (1448.96
                + 4.591 * t
                - 5.304e-2 * t ** 2
                + 2.374e-4 * t ** 3
                + 1.340 * ds
                + 1.630e-2 * z
                + 1.675e-7 * z ** 2
                - 1.025e-2 * t * ds
                - 7.139e-13 * t * z ** 3)


def sound_speed_in_range(salinity, theta, depth_m):
    """Boolean grid: True where Mackenzie's fit is quoted valid. Broadcasts like `sound_speed`.

    `sound_speed` itself returns a number everywhere -- it is a polynomial, and refusing would make
    it unusable across the head of the Bay of Bengal, which is exactly where cyclones form. So the
    envelope is a SEPARATE mask the caller renders as its own category rather than a silent
    extrapolation dressed as a measurement.

    MEASURED, NOT ASSUMED [2026-09-05, data/processed/daily_sat/v001, 2025-09-09 surface layer]:

        salinity     1.64 to 39.98 psu   ->  7.64% of surface cells below S = 30 (Ganges/Meghna)
        theta       19.85 to 35.34 degC  -> 10.35% of surface cells above T = 30

    So roughly a sixth of the surface is outside the envelope, concentrated in the fresh plume and
    the warm pool. theta never falls below 2 degC anywhere in the column, so the cold end is clean.
    """
    (t_lo, t_hi) = SOUND_SPEED_VALID["theta_c"]
    (s_lo, s_hi) = SOUND_SPEED_VALID["salinity"]
    (z_lo, z_hi) = SOUND_SPEED_VALID["depth_m"]
    S = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    z = np.asarray(depth_m, dtype="float64")
    with np.errstate(invalid="ignore"):
        return ((S >= s_lo) & (S <= s_hi) & (t >= t_lo) & (t <= t_hi)
                & (z >= z_lo) & (z <= z_hi))
