"""Upwelling: a SIGNATURE always, wind ATTRIBUTION only when wind is actually supplied.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config and F5 physics; modifies nothing.

THE POINT OF THIS MODULE'S SHAPE
"Upwelling" as a word implies wind forcing. For most of this project's life we had no wind, and the
honest product was a *signature* -- cold surface water sitting over a shoaled thermocline -- which
is consistent with upwelling but does not demonstrate it. Wind has since landed, so attribution is
now possible. Rather than collapsing the two, they stay separate:

    upwelling_signature(...)              -> wind_attributed = False   (always available)
    upwelling_signature(..., ekman=...)   -> wind_attributed = True    (only with real stress)
    ekman_pumping(None, None)             -> raises MissingWindError

`wind_attributed` is returned as DATA inside the result, not written in a docstring, so a panel or
a Sentinel rule cannot lose the caveat by not reading the docs. There is no default wind, no
assumed drag coefficient, and no silent fallback.

THE WIND GRID IS OFFSET HALF A CELL -- see load_wind_stress
[VERIFIED 2026-08-26] the CMEMS monthly wind product is on cell CENTRES (5.125, 5.375, ...) while
the frozen baseline grid is on cell EDGES (5.000, 5.250, ...). Both are (100, 240) with 0.25 deg
spacing, so the shapes match, the value ranges are plausible, and every wind value still belongs
~14 km southwest of where a naive assignment would put it. Ekman pumping is a CURL -- a spatial
derivative -- and the upwelling we care about is COASTAL, so that half-cell shift moves water
across the land mask exactly where it does most damage. Assigning the raw array is forbidden;
`load_wind_stress` regrids and asserts.

MONTHLY MEANS ARE A LOWER BOUND
The curl of a monthly-mean stress is not the monthly mean of the curl. Averaging smooths out the
short, strong-curl events that drive much of the real pumping. These numbers are a reasonable
seasonal pattern and a LOWER BOUND on episodic upwelling. That is a property of the product, not
of this code, and it must travel with any number quoted from it.
"""
from __future__ import annotations

import glob
import os

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

from ..physics import layers, ohc  # F5: real seawater density and layer depths
from . import _metric

#: Default margin for "cold": SST this far below the latitude reference. A convention chosen for
#: this design, not a value taken from a paper.
SST_MARGIN_C = 0.5

#: Default definition of "shoaled": shallower than this percentile of the snapshot's own
#: distribution. Also a convention.
SHOAL_PERCENTILE = 25.0

WIND_DIR = os.path.join(config.DATA_RAW, "wind")

#: Equatorward of this, f -> 0 and Ekman pumping is undefined. Our domain starts at 5.0N, so this
#: guards the boundary rather than punching a hole in the middle.
MIN_ABS_LAT_DEG = 5.0


CLIMATOLOGY = os.path.join(config.ARTIFACTS, "climatology.npy")


def climatological_sst_reference(month: int) -> np.ndarray:
    """Monthly SST climatology as the reference for "cold", (n_lat, n_lon) in degC.

    PREFER THIS over the zonal-mean default. [VERIFIED 2026-08-26 on the 48-month record] the
    zonal default gets the Somali upwelling BACKWARDS: it flags the Somali box as "cold" 97.9% of
    the time in January and 88.3% in July, giving a SW/NE monsoon ratio of 0.88 -- the wrong
    direction for the best-known upwelling system in this basin. The cause is that a coastal
    upwelling box is colder than its own latitude band ALL YEAR, so "colder than the zonal mean"
    is nearly always true there and carries almost no information.

    Against the climatology the same box reads 42.7% (SW) vs 25.4% (NE), ratio 1.68 -- the right
    direction, because "colder than normal HERE for THIS month" is an anomaly rather than a
    geographic fact.

    Even so, `cold` remains the weak term of the signature (~40% baseline). The discrimination is
    carried by `shoaled_thermocline` (0% outside Jun-Aug, 15-25% within it). Said plainly so that
    nobody credits the SST term with work it is not doing.
    """
    if not (1 <= int(month) <= 12):
        raise ValueError(f"month must be 1-12, got {month}")
    if not os.path.exists(CLIMATOLOGY):
        raise FileNotFoundError(
            f"{CLIMATOLOGY} absent -- it is gitignored and ships in the data bundle. "
            "Without it, pass your own sst_reference; the zonal default is known to invert "
            "the Somali signal (see this function's docstring)."
        )
    clim = np.load(CLIMATOLOGY, mmap_mode="r")
    if clim.shape != (12, config.N_LAT, config.N_LON, config.N_DEPTHS):
        raise ValueError(f"unexpected climatology shape {clim.shape}")
    return np.asarray(clim[int(month) - 1, :, :, 0], dtype="float64")


class MissingWindError(RuntimeError):
    """Raised when a wind-attributed quantity is asked for without wind.

    Deliberately not a warning and deliberately not a NaN return: a caller who wanted Ekman
    pumping and got a silently-empty array would report "no upwelling" rather than "no wind".
    """


def load_wind_stress(month) -> dict:
    """Load one month of wind stress, REGRIDDED onto the frozen baseline grid.

    month : "YYYYMM", "YYYY-MM", or anything numpy can read as a datetime64.

    Returns {"eastward_stress", "northward_stress", "time", "path"} with the stress arrays on
    (config.N_LAT, config.N_LON) in N/m2.

    This is the only sanctioned way to get wind into F6. It interpolates from the product's
    cell-centre grid onto the baseline grid and ASSERTS the coordinates agree afterwards. Cells
    outside the product's coverage (the first row and column of the baseline grid, which sit
    0.125 deg outside it) come back NaN rather than extrapolated -- inventing wind past the edge
    of the product is the same class of error as inventing water below the sea floor.
    """
    import xarray as xr

    key = str(month).replace("-", "")[:6]
    if not (len(key) == 6 and key.isdigit()):
        raise ValueError(f"month must look like YYYYMM, got {month!r}")

    path = os.path.join(WIND_DIR, f"wind_{key}.nc")
    if not os.path.exists(path):
        have = sorted(os.path.basename(p) for p in glob.glob(os.path.join(WIND_DIR, "wind_*.nc")))
        raise MissingWindError(
            f"no wind file for {key} at {path}. "
            + (f"Present: {have[0]}..{have[-1]} ({len(have)} files)." if have else
               f"{WIND_DIR} is empty -- the wind product does not travel through git.")
        )

    with xr.open_dataset(path) as ds:
        for v in ("eastward_stress", "northward_stress"):
            if v not in ds:
                raise ValueError(f"{path} has no {v}; found {list(ds.data_vars)}")

        raw_lat = np.asarray(ds["latitude"].values, dtype="float64")
        offset = float(raw_lat[0] - float(config.LAT[0]))

        regridded = ds.interp(latitude=np.asarray(config.LAT, dtype="float64"),
                              longitude=np.asarray(config.LON, dtype="float64"),
                              method="linear")

        out = {}
        for v in ("eastward_stress", "northward_stress"):
            a = np.asarray(regridded[v].values, dtype="float64")
            out[v] = a[0] if a.ndim == 3 else a          # drop the length-1 time axis
        time = np.asarray(ds["time"].values).astype("datetime64[D]")[0]

    # The assertion §2.1 of the spec demands. If the product ever changes grid, this fires here
    # rather than showing up as a wind field that is subtly in the wrong place.
    got_lat = np.asarray(regridded["latitude"].values, dtype="float64")
    got_lon = np.asarray(regridded["longitude"].values, dtype="float64")
    if not (np.allclose(got_lat, np.asarray(config.LAT, dtype="float64"), atol=1e-6)
            and np.allclose(got_lon, np.asarray(config.LON, dtype="float64"), atol=1e-6)):
        raise AssertionError("regridded wind coordinates do not match config.LAT/LON")

    for v in ("eastward_stress", "northward_stress"):
        if out[v].shape != (config.N_LAT, config.N_LON):
            raise AssertionError(f"{v} is {out[v].shape}, expected {(config.N_LAT, config.N_LON)}")

    return {**out, "time": time, "path": path, "raw_grid_offset_deg": offset}


def ekman_pumping(eastward_stress, northward_stress, *, rho: float = None) -> np.ndarray:
    """Vertical Ekman velocity from wind-stress curl. Positive is UPWARD (upwelling).

        w_E = (1/rho) * [ d/dx (tau_y / f) - d/dy (tau_x / f) ]

    f is kept INSIDE the derivative, so the beta effect (f varying with latitude) is included
    rather than dropped -- at 5N, where f is small and changing fastest, dropping it is not a
    small correction.

    Returns m/s on the frozen grid. NaN equatorward of 5 deg, at the domain edges, and wherever
    the stress is NaN.

    Raises MissingWindError if either field is None. There is no assumed wind.
    """
    if eastward_stress is None or northward_stress is None:
        raise MissingWindError(
            "ekman_pumping needs real wind stress; it will not assume a wind field or a drag "
            "coefficient. Load it with load_wind_stress('YYYYMM'), which regrids the product "
            "onto the baseline grid (the raw grid is offset half a cell)."
        )

    taux = _metric._check_grid(eastward_stress)
    tauy = _metric._check_grid(northward_stress)
    rho = float(ohc.REFERENCE_DENSITY if rho is None else rho)

    f = _metric.coriolis()[:, None]                       # (n_lat, 1), broadcasts over lon
    lat = np.asarray(config.LAT, dtype="float64")[:, None]
    undefined = np.abs(lat) < MIN_ABS_LAT_DEG
    f = np.where(undefined, np.nan, f)

    w = (_metric.ddx(tauy / f) - _metric.ddy(taux / f)) / rho
    return np.where(np.broadcast_to(undefined, w.shape), np.nan, w)


def upwelling_signature(sst, theta, salinity, *, ekman=None, sst_reference=None,
                        sst_margin: float = SST_MARGIN_C,
                        shoal_percentile: float = SHOAL_PERCENTILE) -> dict:
    """Cold surface water over a shoaled thermocline, for ONE snapshot.

    sst      : (n_lat, n_lon) degC
    theta    : (n_lat, n_lon, n_depths) degC
    salinity : (n_lat, n_lon, n_depths) PSS-78
    ekman    : optional (n_lat, n_lon) vertical Ekman velocity from `ekman_pumping`.
               Supplying it is what turns a signature into an attribution.

    Both conditions must hold for a cell to be flagged:
      cold    -- SST at least `sst_margin` below the reference. The default reference is the
                 ZONAL MEAN at that latitude in this snapshot, not a domain mean: this basin spans
                 25 degrees of latitude and a domain mean would mark the whole north as "cold".
      shoaled -- MLD (density criterion, F5) and thermocline depth BOTH shallower than the
                 `shoal_percentile` of their own valid-cell distribution in this snapshot.

    Returns the mask, its two components, and `wind_attributed` as data.
    """
    sst = np.asarray(sst, dtype="float64")
    theta = np.asarray(theta, dtype="float64")
    salinity = np.asarray(salinity, dtype="float64")
    if sst.ndim != 2:
        raise ValueError(f"upwelling_signature takes ONE snapshot; sst is {sst.shape}")
    if theta.shape[:2] != sst.shape or theta.shape[-1] != config.N_DEPTHS:
        raise ValueError(
            f"theta must be {(*sst.shape, config.N_DEPTHS)}, got {theta.shape}")
    if salinity.shape != theta.shape:
        raise ValueError(f"salinity {salinity.shape} must match theta {theta.shape}")

    # --- cold surface -------------------------------------------------------------------
    # The default is a FALLBACK, not a recommendation. See climatological_sst_reference: the
    # zonal mean inverts the Somali seasonal signal, so a caller with the climatology available
    # should pass it. Which one was used is recorded in the result.
    if sst_reference is None:
        with np.errstate(invalid="ignore"):
            zonal = np.nanmean(sst, axis=1, keepdims=True)   # (n_lat, 1)
        sst_reference = np.broadcast_to(zonal, sst.shape)
        reference_kind = "zonal-mean (FALLBACK: inverts the Somali signal; prefer climatology)"
    else:
        reference_kind = "caller-supplied"
    sst_reference = np.asarray(sst_reference, dtype="float64")
    cold = np.isfinite(sst) & (sst <= sst_reference - sst_margin)

    # --- shoaled thermocline ------------------------------------------------------------
    mld = layers.mixed_layer_depth(salinity, theta)
    th = layers.thermocline(theta)["depth"]
    ok = np.isfinite(mld) & np.isfinite(th)
    if not ok.any():
        raise ValueError("no valid MLD/thermocline anywhere -- check theta and salinity.")
    mld_cut = float(np.percentile(mld[ok], shoal_percentile))
    th_cut = float(np.percentile(th[ok], shoal_percentile))
    shoaled = ok & (mld < mld_cut) & (th < th_cut)

    signature = cold & shoaled
    wind_attributed = ekman is not None
    if wind_attributed:
        e = _metric._check_grid(ekman)
        signature = signature & np.isfinite(e) & (e > 0)

    return {
        "signature": signature,
        "cold_surface": cold,
        "shoaled_thermocline": shoaled,
        "mld": mld,
        "thermocline_depth": th,
        "mld_threshold_m": mld_cut,
        "thermocline_threshold_m": th_cut,
        "sst_margin_c": float(sst_margin),
        "sst_reference_kind": reference_kind,
        "n_cells": int(signature.sum()),
        # Measured on the 48-month record: `cold` runs ~40-90% baseline and discriminates weakly;
        # `shoaled` is 0% outside Jun-Aug. Do not credit the SST term with the seasonality.
        "limiting_term": "shoaled_thermocline",
        # Carried as DATA so a downstream consumer cannot lose it.
        "wind_attributed": bool(wind_attributed),
        "method": "signature+ekman" if wind_attributed else "signature-only",
        "caveat": ("Ekman pumping from MONTHLY-MEAN stress: a lower bound on episodic upwelling."
                   if wind_attributed else
                   "Consistent with upwelling; NOT demonstrated. No wind was supplied, so no "
                   "forcing is attributed."),
    }
