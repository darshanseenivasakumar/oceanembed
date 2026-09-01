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
