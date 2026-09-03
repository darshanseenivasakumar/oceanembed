"""Tropical Cyclone Heat Potential (TCHP), Ocean Heat Content (OHC), and the 26 °C isotherm depth.

A DERIVED product on the FROZEN TS-Cast-NIO temperature field. TCHP is the single most operationally
important ocean variable for cyclone-intensification forecasting: the heat stored above the 26 °C
isotherm. Producing it daily over the Bay of Bengal and Arabian Sea from satellite-only inputs — no
in-situ floats — is the nationally-relevant headline for this Disaster-Management PS under INCOIS.

Nothing here retrains or touches the checkpoint, the bundle, dataset.py, inference.py, or the split.

THE SCIENCE (implemented exactly as specified)
  TCHP = (cp*rho/1e7) * integral_0^D26 (T(z) - 26) dz ,  for T(z) >= 26 C     [kJ/cm^2]
  OHC  = (cp*rho)     * integral_0^z_ref  T(z) dz                              [J/m^2 -> GJ/m^2]
  D26  = depth of the 26 C isotherm, LINEARLY interpolated between bracketing levels   [m]

Trapezoidal integration across the 15 NON-UNIFORM standard depths, with a final partial layer from
the deepest level still >= 26 C down to D26 (where the excess T-26 reaches 0).

CONSTANTS — and a named difference from the physics module
  TCHP here uses the TCHP-literature convention cp=4000 J/(kg C), rho=1026 kg/m^3 (Leipper &
  Volgenau 1972). The project's OHC budget module `phase2.physics.ohc` uses cp=3985, rho=1025 (the
  climate-budget convention). Both are defensible; they differ by ~0.4% and are kept as each field's
  own convention rather than silently unified. The OHC_0-700 product below REUSES
  `ohc_constant_density` (temperature-only, since the shipped satellite model predicts no salinity),
  so it carries the physics module's constants, not TCHP's.

UNIT FACTOR
  cp[J/(kg C)] * rho[kg/m^3] * integral[C m] = J/m^2.  1 J/m^2 = 1e-3 kJ / 1e4 cm^2 = 1e-7 kJ/cm^2,
  hence the /1e7. A realistic tropical column lands ~20-120 kJ/cm^2; anything near 1e6 is a unit bug.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config as base
from phase2.tscast_nio import config
from phase2.physics.ohc import ohc_constant_density   # reuse: temp-only OHC, GJ/m^2

DEPTHS = np.asarray(config.DEPTHS, dtype="float64")
ISO_C = 26.0                       # the tropical-cyclone threshold isotherm
CP_TCHP = 4000.0                   # J/(kg C), TCHP convention (see module docstring)
RHO_TCHP = 1026.0                  # kg/m^3, TCHP convention
_KJ_CM2 = 1e7                      # J/m^2 -> kJ/cm^2 divisor


def _valid(temp_1d):
    t = np.asarray(temp_1d, dtype="float64")
    if t.shape != (config.N_DEPTHS,):
        raise ValueError(f"expected {config.N_DEPTHS} depths, got {t.shape}")
    return t, np.isfinite(t)


def d26_from_profile(temp_1d, depths=DEPTHS) -> float:
    """Depth of the 26 C isotherm (m), by linear interpolation on the first DOWNWARD crossing.

    Returns:
      * nan            if the surface is below 26 C (no warm layer) or the column is all-NaN;
      * deepest depth  if the whole valid column is >= 26 C (flag this upstream — physically rare
                       in the NIO and a data smell), because there is no crossing to interpolate;
      * else           the interpolated depth where T first drops through 26 C going down.
    """
    t, ok = _valid(temp_1d)
    z = np.asarray(depths, dtype="float64")
    if not ok.any() or not ok[0] or t[0] < ISO_C:
        return float("nan")
    # Surface-connected warm layer: cumulative-AND of (T>=26) from the surface. The first level
    # that breaks it is the crossing. Levels below a cold layer that warm again are NOT counted —
    # TCHP is the surface-connected warm layer only.
    warm = ok & (t >= ISO_C)
    contig = np.cumprod(warm.astype(int)).astype(bool)      # True until the first non-warm level
    n_warm = int(contig.sum())
    last = n_warm - 1                                        # last contiguous warm level
    # Is there a valid, colder level immediately below to interpolate against?
    if n_warm < config.N_DEPTHS and ok[n_warm]:
        t_hi, t_lo = t[last], t[n_warm]                     # t_hi >= 26 > t_lo
        frac = (t_hi - ISO_C) / (t_hi - t_lo)               # 0..1 between the two levels
        return float(z[last] + frac * (z[n_warm] - z[last]))
    # Whole valid column is warm: no crossing. Report the deepest valid level (a flagged case).
    return float(z[np.nonzero(ok)[0].max()])


def tchp_from_profile(temp_1d, depths=DEPTHS, rho: float = RHO_TCHP, cp: float = CP_TCHP) -> float:
    """Tropical Cyclone Heat Potential, kJ/cm^2.

    0.0        when the surface is below 26 C (no warm layer);
    nan        when the profile is all-NaN (land / no ocean) — never 0, which would read as "cold";
    otherwise  (cp*rho/1e7) * integral_0^D26 (T-26) dz, trapezoid over the warm levels plus the
               partial triangle from the last warm level down to D26.
    """
    t, ok = _valid(temp_1d)
    z = np.asarray(depths, dtype="float64")
    if not ok.any():
        return float("nan")
    if not ok[0] or t[0] < ISO_C:
        return 0.0

    d26 = d26_from_profile(t, z)
    if not np.isfinite(d26):
        return 0.0

    warm = ok & (t >= ISO_C)
    contig = np.cumprod(warm.astype(int)).astype(bool)
    idx = np.nonzero(contig)[0]                             # contiguous warm levels from surface
    excess = t[idx] - ISO_C                                 # T - 26 at those levels, all >= 0

    # Full trapezoids between consecutive warm levels (only within the warm layer).
    integral = float(np.trapezoid(excess, x=z[idx])) if idx.size >= 2 else 0.0
    # Partial triangle from the deepest warm level down to D26, where (T-26) goes to 0.
    last = int(idx[-1])
    if d26 > z[last]:
        integral += 0.5 * float(excess[-1]) * (d26 - z[last])

    return cp * rho * integral / _KJ_CM2


def ohc_from_profile(temp_1d, depths=DEPTHS, z_ref: float = 700.0) -> float:
    """Ocean heat content 0 -> z_ref, GJ/m^2. Reuses the physics module's temperature-only OHC.

    nan if the column does not reach z_ref (never a partial integral labelled as full — the Phase-1
    shelf-extrapolation failure this project already fixed once).
    """
    t, _ = _valid(temp_1d)
    return float(ohc_constant_density(t, max_depth_m=z_ref))


# --------------------------------------------------------------------------- uncertainty (point)

def integrated_uncertainty(mean_1d, sigma_1d, depths=DEPTHS, z_ref: float = 700.0,
                           n_samples: int = 200, rho: float = RHO_TCHP, cp: float = CP_TCHP,
                           rng=None) -> dict:
    """Monte Carlo spread of TCHP, D26 and OHC under the model's per-depth uncertainty.

    WHY MONTE CARLO, NOT AN ANALYTIC FORMULA
    TCHP and D26 are not smooth functions of the profile — the 26 C crossing and the partial-layer
    term make an analytic (delta-method) propagation awkward to get right across every edge case
    (SST<26, whole-column-warm, land). Sampling candidate profiles and evaluating the SAME tested
    scalar functions on each sample is simpler to verify and cannot silently mishandle an edge case
    the closed-form derivative would need to special-case separately.

    THE ASSUMPTION, NAMED, AND WHY IT MAKES THIS A LOWER BOUND
    The model provides a per-depth VARIANCE with no cross-depth covariance term, so each sampled
    profile draws every depth INDEPENDENTLY: `T_k ~ Normal(mean_k, sigma_k)`. This is the same
    situation `tscast.py` already documents for T/S -> density ("the paper is explicit that T/S
    error covariance is non-negligible, so propagating the two variances analytically would
    understate the density error") — except here it is cross-DEPTH rather than cross-variable
    covariance that is missing. Adjacent-depth errors are physically likely to be correlated (a
    warm bias at 50 m usually accompanies one at 75 m), which independent sampling cannot capture.
    So **this spread is a measured lower bound on the true uncertainty, not the true uncertainty**
    — exactly the caveat this project already applies to sigma_rho instead of a propagated one.
    There is no learned joint-uncertainty head for these derived quantities to fall back on instead
    (unlike density), because nothing was trained to predict them jointly.

    THE POINT ESTIMATE IS UNCHANGED
    The reported `tchp_std` etc. is the spread of samples AROUND the existing, already-verified
    point estimate (`tchp_from_profile(mean_1d)` and `d26_from_profile(mean_1d)`) — this function
    adds a spread alongside those numbers and never recomputes or replaces them.

    Returns
        tchp_std, tchp_p10, tchp_p90   kJ/cm^2 -- spread of TCHP across samples
        d26_std                        m       -- spread of D26 across samples (nan if no crossing
                                                   in enough samples to compute a spread)
        ohc_std                        GJ/m^2  -- spread of OHC_0-z_ref across samples
        n_samples                      how many of the draws were finite for each quantity
        assumption                     the caveat above, as a string, so it travels with the number
    """
    mean = np.asarray(mean_1d, dtype="float64")
    sigma = np.asarray(sigma_1d, dtype="float64")
    if mean.shape != (config.N_DEPTHS,) or sigma.shape != (config.N_DEPTHS,):
        raise ValueError(f"expected {config.N_DEPTHS} depths, got mean {mean.shape} / "
                         f"sigma {sigma.shape}")
    rng = rng or np.random.default_rng()
    z = np.asarray(depths, dtype="float64")
    valid = np.isfinite(mean)

    if not valid.any():
        nan = float("nan")
        return {"tchp_std": nan, "tchp_p10": nan, "tchp_p90": nan, "d26_std": nan, "ohc_std": nan,
                "n_samples": 0, "assumption": _INDEPENDENCE_NOTE}

    # One batch of independent per-depth draws, (n_samples, 15). Invalid depths stay NaN in every
    # draw so a masked cell can never contribute a fabricated sample.
    draws = rng.normal(mean[None, :], sigma[None, :], size=(n_samples, config.N_DEPTHS))
    draws = np.where(valid[None, :], draws, np.nan)

    tchp_samples = np.array([tchp_from_profile(draws[k], z, rho, cp) for k in range(n_samples)])
    d26_samples = np.array([d26_from_profile(draws[k], z) for k in range(n_samples)])
    # ohc_constant_density is already vectorised over leading dims -- one call, not a loop.
    ohc_samples = ohc_constant_density(draws, max_depth_m=z_ref)

    def _spread(samples):
        fin = np.isfinite(samples)
        if not fin.any():
            return float("nan"), float("nan"), float("nan"), 0
        s = samples[fin]
        return float(np.std(s)), float(np.percentile(s, 10)), float(np.percentile(s, 90)), int(fin.sum())

    t_std, t_p10, t_p90, t_n = _spread(tchp_samples)
    d_std, _, _, d_n = _spread(d26_samples)
    o_std, _, _, o_n = _spread(ohc_samples)

    return {
        "tchp_std": t_std, "tchp_p10": t_p10, "tchp_p90": t_p90,
        "d26_std": d_std, "ohc_std": o_std,
        "n_samples": {"tchp": t_n, "d26": d_n, "ohc": o_n},
        "assumption": _INDEPENDENCE_NOTE,
    }


_INDEPENDENCE_NOTE = (
    "Sampled assuming INDEPENDENT per-depth error (the model gives no cross-depth covariance). "
    "Adjacent depths are physically likely to be correlated, so this spread is a measured LOWER "
    "BOUND on the true uncertainty, not the true uncertainty -- the same caveat this project "
    "already applies to density instead of propagating T/S variance analytically."
)


# --------------------------------------------------------------------------- field (whole grid)

def heat_content_field(field: dict, z_ref: float = 700.0,
                       rho: float = RHO_TCHP, cp: float = CP_TCHP) -> dict:
    """TCHP / OHC / D26 as 2-D (lat, lon) fields from a `predict_field` result.

    `field` is the numpy dict from phase2.tscast_nio.field.predict_field: temperature (100,240,15),
    valid_mask, land_mask, provenance. The land/seafloor mask is preserved — NaN in, NaN out — so a
    masked cell can never be read as 0 heat.

    The per-cell TCHP and D26 apply the SAME scalar functions unit-tested above, mapped across the
    depth axis, so a field value equals the scalar value at that cell by construction (one
    definition, never two — the drift-safety rule field.py itself follows). OHC is a direct
    vectorised call, no mapping needed.
    """
    temp = np.asarray(field["temperature"], dtype="float64")     # (100, 240, 15), NaN off-ocean
    if temp.shape[-1] != config.N_DEPTHS:
        raise ValueError(f"temperature last axis must be {config.N_DEPTHS} depths, got {temp.shape}")

    tchp = np.apply_along_axis(lambda c: tchp_from_profile(c, DEPTHS, rho, cp), -1, temp)
    d26 = np.apply_along_axis(lambda c: d26_from_profile(c, DEPTHS), -1, temp)
    ohc = ohc_constant_density(temp, max_depth_m=z_ref)          # (100, 240) GJ/m^2, vectorised

    # A wholly-NaN column (land / below the shallowest seafloor) must stay NaN in every product,
    # including TCHP where the scalar returns nan for all-NaN input.
    return {
        "date": field.get("date"),
        "tchp": tchp,                 # kJ/cm^2
        "ohc_0_zref": ohc,            # GJ/m^2
        "d26": d26,                   # m
        "z_ref_m": float(z_ref),
        "constants": {"rho_tchp": float(rho), "cp_tchp": float(cp), "iso_C": ISO_C,
                      "unit_factor_kJ_cm2": _KJ_CM2},
        "provenance": field.get("provenance"),
    }


def to_xarray(hc: dict):
    """Wrap a `heat_content_field` result as a CF-style xarray Dataset for NetCDF output."""
    import xarray as xr

    lat = np.asarray(base.LAT, dtype="float64")
    lon = np.asarray(base.LON, dtype="float64")
    coords = {"lat": ("lat", lat), "lon": ("lon", lon)}
    ds = xr.Dataset(
        {
            "tchp": (("lat", "lon"), hc["tchp"],
                     {"long_name": "tropical cyclone heat potential", "units": "kJ cm-2",
                      "isotherm_degC": ISO_C}),
            "ohc_0_zref": (("lat", "lon"), hc["ohc_0_zref"],
                           {"long_name": f"ocean heat content 0-{hc['z_ref_m']:.0f} m",
                            "units": "GJ m-2"}),
            "d26": (("lat", "lon"), hc["d26"],
                    {"long_name": "depth of the 26 degC isotherm", "units": "m"}),
        },
        coords=coords,
        attrs={
            "title": "OceanEmbed derived heat-content products (TCHP / OHC / D26)",
            "source": "TS-Cast-NIO frozen satellite model; derived by phase2.derived.heat_content",
            "date": str(hc.get("date")),
            "cp_J_per_kg_C": hc["constants"]["cp_tchp"],
            "rho_kg_per_m3": hc["constants"]["rho_tchp"],
            "tchp_unit_factor": hc["constants"]["unit_factor_kJ_cm2"],
            "note": ("TCHP uses cp=4000, rho=1026 (TCHP convention); OHC reuses the physics "
                     "module's temperature-only constant-density OHC (cp=3985, rho=1025). The "
                     "shipped model predicts temperature only, so density is not from salinity."),
        },
    )
    return ds
