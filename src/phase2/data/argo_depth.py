"""Argo reports PRESSURE in decibars. config.DEPTHS is in METRES. They are not the same axis.

THE BUG THIS EXISTS FOR (audit finding #8)
`oceanembed.data.download_argo._profiles_to_rows` interpolated each float's temperature onto
config.DEPTHS with `np.interp(config.DEPTHS, p, t)` where `p` was PRES in dbar. Reading pressure
as depth overstates depth by about 1% plus a latitude term: on this grid, at 15 N, the level
labelled 1000 m was really being read at 991.8 m, 500 m at 496.5 m, 200 m at 198.7 m, 100 m at
99.4 m. In the thermocline, where dT/dz reaches 0.1 degC/m, a 0.6 m shift is a tenth of a degree
charged to the model that the model did not get wrong. Every Argo table this project scores
against -- artifacts/argo_test.parquet (2022), argo_daily_period.parquet (2025-26) and its
salinity twin -- was built that way.

THE FIX
Convert pressure to depth BEFORE interpolating, with the UNESCO 1983 formula (Fofonoff and
Millard, UNESCO Technical Papers in Marine Science 44, eq. 25). It is the same relation the
`seawater` package ships as `dpth` and TEOS-10's `gsw.z_from_p` reduces to at zero geopotential
anomaly; the difference between them is millimetres over this grid. No new dependency.

CHECK VALUE (from the paper): p = 10000 dbar at 30 N -> 9712.653 m. Asserted in
tests/phase2/test_argo_depth.py, so the constants cannot drift silently.
"""
from __future__ import annotations

import numpy as np

# UNESCO 1983 eq. 25 constants
_C1, _C2, _C3, _C4 = 9.72659, -2.2512e-5, 2.279e-10, -1.82e-15
_GAMMA_HALF = 1.092e-6           # 0.5 * gamma', the pressure dependence of gravity


def depth_from_pressure(p_dbar, lat_deg):
    """Depth in metres (positive down) from sea pressure in decibars at a latitude in degrees.

    Vectorised over `p_dbar`; `lat_deg` may be a scalar or broadcastable array. Negative pressures
    are not meaningful and are returned as NaN rather than extrapolated.
    """
    p = np.asarray(p_dbar, dtype=float)
    lat = np.asarray(lat_deg, dtype=float)
    x = np.sin(np.deg2rad(np.abs(lat))) ** 2
    g = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * x) * x) + _GAMMA_HALF * p
    z = (((_C4 * p + _C3) * p + _C2) * p + _C1) * p / g
    return np.where(p < 0, np.nan, z)


def pressure_read_as_depth_error_m(depths_m, lat_deg):
    """How far off each nominal level was when pressure was read as depth: depth - z(p=depth).

    Positive means the old interpolation sampled the float SHALLOWER than the level it labelled,
    which is the direction of the error everywhere in the water column.
    """
    d = np.asarray(depths_m, dtype=float)
    return d - depth_from_pressure(d, lat_deg)
