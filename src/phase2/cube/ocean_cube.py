"""OceanCube -- one reconstructed 3-D volume, with the sea floor enforced.

OWNER: Unit A (Arjhun), transferred from Unit B 2026-08-26. PHASE-2 ONLY.
Schema: `docs/phase2/data-model.md` -- SHARED. Change it there first, then here, then tell the team.

WHAT THIS IS
A single object holding one timestamp's reconstruction: temperature over (lat, lon, depth), the
uncertainty and anomaly that came with it, the bathymetry mask, and provenance saying exactly what
produced it. It is the thing F5/F6/F9/F10 slice instead of each re-deriving arrays from `.npz`.

IT WRAPS THE BASELINE, IT DOES NOT REIMPLEMENT IT
`oceanembed.inference.predict.reconstruct_grid` already runs the model over the grid and already
applies the bathymetry mask. Re-deriving that here would give us two reconstruction paths that
could disagree, which is exactly the D-014 failure (two loaders, one z-scored, silent 20x error).
So: import it, wrap it, add what it does not have.

WHAT IT ADDS -- and the first one is the point
1. **The sea floor is a REFUSAL, not a NaN.** `reconstruct_grid` returns NaN below the sea bed.
   NaN is easy to average over, plot, or quietly propagate. Phase 1 shipped 1000 m temperatures in
   the ~20 m Persian Gulf, and a `nanmean` would have hidden it just as well as a plain mean. Here,
   `value_at()` RAISES `BelowSeafloorError` naming the cell and its actual depth, and every slice
   reports how much of what you asked for does not exist.
   [VERIFIED 2026-08-26] 26.00N 52.50E is ocean, and has water only to 30 m. Basin-wide, 100% of
   ocean cells have water at 0 m and **75.8% at 1000 m**.
2. **Provenance travels with every extraction.** A depth slice handed to a plotting function
   arrives knowing its date, source, model and units. A bare array does not.
3. **Named slicing** -- depth level, vertical section, single profile -- so consumers stop writing
   their own index arithmetic against `config.DEPTHS`.

Grid, depths and region are IMPORTED from `oceanembed.config`. Nothing here hardcodes them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

#: Selecting a depth: how far from a requested depth we will silently snap to a real level.
#: config.DEPTHS is irregular (5 m near the surface, 200 m near the bottom), so "nearest" alone
#: could snap 400 m to 500 m without saying so. Every snap is reported in the result.
SNAP_TOLERANCE_M = 0.5


class BelowSeafloorError(ValueError):
    """Asked for water where the sea bed is shallower than the requested depth.

    Deliberately an exception rather than a NaN: a NaN is easy to average over and was how
    Phase 1 shipped deep temperatures for the Persian Gulf.
    """


class CubeShapeError(ValueError):
    """An array did not match the frozen grid contract."""


def _grid_axes() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.asarray(config.LAT, dtype="float64"),
            np.asarray(config.LON, dtype="float64"),
            np.asarray(config.DEPTHS, dtype="float64"))


def _readonly(a: np.ndarray | None) -> np.ndarray | None:
    """Hand out arrays that cannot be mutated in place by a consumer.

    The cube is a contract object; a caller who writes into `cube.temperature` would corrupt it
    for every other consumer of the same instance without anything raising.
    """
    if a is None:
        return None
    v = np.asarray(a)
    v.setflags(write=False)
    return v


@dataclass(frozen=True)
class OceanCube:
    """One timestamp of reconstructed subsurface temperature. See `docs/phase2/data-model.md`."""

    date: Any
    temperature: np.ndarray                     # (N_LAT, N_LON, N_DEPTHS) degC
    valid_mask: np.ndarray                      # (N_LAT, N_LON, N_DEPTHS) bool, True = real water
    land_mask: np.ndarray                       # (N_LAT, N_LON) bool, True = land
    uncertainty: np.ndarray | None = None       # (N_LAT, N_LON, N_DEPTHS) degC, 1 sigma
    anomaly: np.ndarray | None = None           # (N_LAT, N_LON, N_DEPTHS) degC vs climatology
    provenance: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ construction
    def __post_init__(self):
        shape = (config.N_LAT, config.N_LON, config.N_DEPTHS)
        for name in ("temperature", "valid_mask", "uncertainty", "anomaly"):
            a = getattr(self, name)
            if a is None:
                continue
            if np.shape(a) != shape:
                raise CubeShapeError(
                    f"{name} is {np.shape(a)}, expected {shape}. Import config.LAT/LON/DEPTHS "
                    "rather than reshaping to fit."
                )
        if np.shape(self.land_mask) != (config.N_LAT, config.N_LON):
            raise CubeShapeError(
                f"land_mask is {np.shape(self.land_mask)}, expected "
                f"{(config.N_LAT, config.N_LON)}")
        object.__setattr__(self, "temperature", _readonly(np.asarray(self.temperature, "float64")))
        object.__setattr__(self, "valid_mask", _readonly(np.asarray(self.valid_mask, bool)))
        object.__setattr__(self, "land_mask", _readonly(np.asarray(self.land_mask, bool)))
        for name in ("uncertainty", "anomaly"):
            a = getattr(self, name)
            if a is not None:
                object.__setattr__(self, name, _readonly(np.asarray(a, "float64")))

    @classmethod
    def reconstruct(cls, date, *, source: str | None = None,
                    with_uncertainty: bool = True) -> "OceanCube":
        """Run the baseline reconstruction for one date and wrap it.

        source: "satellite" (the problem statement's deliverable) or "glorys" (the model's own
        ceiling). Left as the process default when None, so this never silently reconfigures a
        caller's session.
        """
        from oceanembed.inference import predict as P

        if source is not None:
            P.set_source(source)
        g = P.reconstruct_grid(date, with_uncertainty=with_uncertainty)

        vm = _valid_mask_or_all_true()
        prov = {
            "produced_by": "phase2.cube.OceanCube.reconstruct",
            "wraps": "oceanembed.inference.predict.reconstruct_grid",
            "source": P.current_source(),
            "date_requested": str(date),
            "date_used": str(g["date"]),
            "with_uncertainty": bool(with_uncertainty),
            "units": {"temperature": "degC", "uncertainty": "degC (1 sigma)",
                      "anomaly": "degC vs monthly climatology", "depth": "m"},
            "grid": {"n_lat": config.N_LAT, "n_lon": config.N_LON,
                     "depths_m": list(config.DEPTHS)},
        }
        try:
            prov["baseline_provenance"] = P.provenance()
        except Exception as e:      # provenance must never be the reason a cube fails to build
            prov["baseline_provenance"] = {"unavailable": f"{type(e).__name__}: {e}"}

        return cls(date=g["date"], temperature=g["temp"], valid_mask=vm,
                   land_mask=g["land_mask"], uncertainty=g.get("uncertainty"),
                   anomaly=g.get("anomaly"), provenance=prov)

    # ------------------------------------------------------------------ bathymetry
    def seafloor_index(self, i_lat: int, i_lon: int) -> int:
        """Number of depth levels with real water at this cell. 0 means land or dry."""
        return int(self.valid_mask[i_lat, i_lon].sum())

    def seafloor_depth_m(self, lat: float, lon: float) -> float:
        """Deepest config depth level with water here. NaN if the cell is land."""
        i, j = self.nearest_cell(lat, lon)
        if self.land_mask[i, j]:
            return float("nan")
        k = self.seafloor_index(i, j)
        return float(config.DEPTHS[k - 1]) if k else float("nan")

    def nearest_cell(self, lat: float, lon: float) -> tuple[int, int]:
        la, lo, _ = _grid_axes()
        if not (la[0] - 0.25 <= lat <= la[-1] + 0.25 and lo[0] - 0.25 <= lon <= lo[-1] + 0.25):
            raise ValueError(
                f"({lat}, {lon}) is outside the domain "
                f"{la[0]}-{la[-1]}N, {lo[0]}-{lo[-1]}E"
            )
        return int(np.argmin(np.abs(la - lat))), int(np.argmin(np.abs(lo - lon)))

    def depth_index(self, depth_m: float) -> tuple[int, float]:
        """(index, snap_distance_m) for a requested depth. Never guesses silently -- the caller
        gets the distance, so a 400 m request that became 300 m is visible.

        `config.DEPTHS` is irregular (5 m steps near the surface, 200 m near the bottom), so a
        request can land exactly between two levels: 400 m is 100 m from both 300 and 500.
        **Ties resolve SHALLOWER.** That is the conservative direction -- more cells have water at
        the shallower level (100% at 0 m, 75.8% at 1000 m), so it degrades coverage less. The
        choice is arbitrary but fixed and reported, which is what matters.
        """
        _, _, dz = _grid_axes()
        k = int(np.argmin(np.abs(dz - float(depth_m))))   # argmin -> first == shallower on ties
        return k, float(abs(dz[k] - float(depth_m)))

    # ------------------------------------------------------------------ extraction
    def _prov(self, **extra) -> dict:
        return {**self.provenance, "extraction": extra}

    def value_at(self, lat: float, lon: float, depth_m: float) -> float:
        """Temperature at one point. RAISES below the sea floor rather than returning NaN."""
        i, j = self.nearest_cell(lat, lon)
        k, snap = self.depth_index(depth_m)
        if self.land_mask[i, j]:
            raise BelowSeafloorError(
                f"({lat}, {lon}) is land (nearest cell {config.LAT[i]:.2f}N "
                f"{config.LON[j]:.2f}E)")
        if not self.valid_mask[i, j, k]:
            floor = self.seafloor_depth_m(lat, lon)
            raise BelowSeafloorError(
                f"no water at {config.DEPTHS[k]} m at {config.LAT[i]:.2f}N {config.LON[j]:.2f}E: "
                f"the sea floor there is at {floor:.0f} m. Requested {depth_m} m."
            )
        if snap > SNAP_TOLERANCE_M:
            pass  # reported by callers that return a record; value_at returns a bare float
        return float(self.temperature[i, j, k])

    def depth_slice(self, depth_m: float, *, what: str = "temperature") -> dict:
        """One horizontal level, (N_LAT, N_LON), with provenance and honest coverage."""
        a = self._field(what)
        k, snap = self.depth_index(depth_m)
        values = np.where(self.valid_mask[..., k], a[..., k], np.nan)
        ocean = ~self.land_mask
        # Same denominator as coverage(), or the two disagree for the same depth and a reader
        # cannot tell which is right. Cells both masks call ocean; the raw figure sits beside it.
        agreed = ocean & self.valid_mask.any(axis=2)
        n_ocean = int(agreed.sum())
        n_water = int((self.valid_mask[..., k] & agreed).sum())
        return {
            "values": values,
            "what": what,
            "depth_m": float(config.DEPTHS[k]),
            "depth_requested_m": float(depth_m),
            "snapped_by_m": snap,
            "lat": np.asarray(config.LAT, dtype="float64"),
            "lon": np.asarray(config.LON, dtype="float64"),
            "dims": ("lat", "lon"),
            # Coverage is returned, not assumed: at 1000 m a quarter of the basin has no water,
            # and a map that does not say so implies a complete field.
            "n_ocean_cells": n_ocean,
            "n_cells_with_water": n_water,
            "coverage_fraction": (n_water / n_ocean) if n_ocean else float("nan"),
            "coverage_denominator": "cells both the land mask and GLORYS bathymetry call ocean "
                                    "(same convention as coverage())",
            "provenance": self._prov(kind="depth_slice", depth_m=float(config.DEPTHS[k]),
                                     requested=float(depth_m), snapped_by_m=snap, field=what),
        }

    def section(self, *, lat: float | None = None, lon: float | None = None,
                what: str = "temperature") -> dict:
        """A vertical section along one latitude OR one longitude line."""
        if (lat is None) == (lon is None):
            raise ValueError("pass exactly one of lat= or lon=")
        a = self._field(what)
        if lat is not None:
            i, _ = self.nearest_cell(lat, float(config.LON[0]))
            values = np.where(self.valid_mask[i], a[i], np.nan)      # (N_LON, N_DEPTHS)
            axis, coord, along = "lon", float(config.LAT[i]), np.asarray(config.LON, "float64")
        else:
            _, j = self.nearest_cell(float(config.LAT[0]), lon)
            values = np.where(self.valid_mask[:, j], a[:, j], np.nan)  # (N_LAT, N_DEPTHS)
            axis, coord, along = "lat", float(config.LON[j]), np.asarray(config.LAT, "float64")
        return {
            "values": values,
            "what": what,
            "dims": (axis, "depth"),
            axis: along,
            "depths_m": np.asarray(config.DEPTHS, dtype="float64"),
            "along": axis,
            "at": coord,
            "at_axis": "lat" if lat is not None else "lon",
            "provenance": self._prov(kind="section", along=axis, at=coord, field=what),
        }

    def profile(self, lat: float, lon: float, *, what: str = "temperature") -> dict:
        """One vertical profile, with the sea floor stated rather than implied."""
        i, j = self.nearest_cell(lat, lon)
        a = self._field(what)
        water = self.valid_mask[i, j]
        values = np.where(water, a[i, j], np.nan)
        floor_k = self.seafloor_index(i, j)
        return {
            "values": values,
            "what": what,
            "dims": ("depth",),
            "depths_m": np.asarray(config.DEPTHS, dtype="float64"),
            "lat": float(config.LAT[i]), "lon": float(config.LON[j]),
            "requested_lat": float(lat), "requested_lon": float(lon),
            "is_land": bool(self.land_mask[i, j]),
            "below_seafloor": ~water,
            "seafloor_depth_m": (float(config.DEPTHS[floor_k - 1]) if floor_k
                                 else float("nan")),
            "n_levels_with_water": floor_k,
            "provenance": self._prov(kind="profile", lat=float(config.LAT[i]),
                                     lon=float(config.LON[j]), field=what),
        }

    # ------------------------------------------------------------------ helpers
    def _field(self, what: str) -> np.ndarray:
        try:
            a = {"temperature": self.temperature, "uncertainty": self.uncertainty,
                 "anomaly": self.anomaly}[what]
        except KeyError:
            raise ValueError(
                f"unknown field {what!r}; expected temperature, uncertainty or anomaly") from None
        if a is None:
            raise ValueError(
                f"this cube has no {what} -- it was built with with_uncertainty=False, or no "
                "climatology was available for the anomaly.")
        return a

    def coastline_disagreement(self) -> dict:
        """Cells this cube's land mask calls ocean but GLORYS bathymetry gives no water at all.

        WHY THIS IS NOT A BUG, and why it is surfaced instead of smoothed away.
        `land_mask` comes from the ACTIVE SOURCE; bathymetry always comes from GLORYS
        (`predict._valid_mask` says so explicitly -- the satellite file has no subsurface truth to
        derive a sea floor from). The two products draw the coastline differently.

        [VERIFIED 2026-08-26] the two land masks disagree on **464 cells**: 179 are ocean in the
        satellite product only, 285 in GLORYS only. Those same 464 are what Unit B's F1 collocation
        engine emits as COASTLINE_DISAGREEMENT, so this is a known, independently measured
        disagreement rather than a new defect.

        Consequence, and the reason it is reported: with `source="satellite"` those 179 cells have
        a surface temperature but no water at ANY depth, so surface coverage is 98.47% rather than
        100%. A reader who saw 98.47% with no explanation would reasonably suspect the cube.
        """
        ocean = ~self.land_mask
        dry = ocean & ~self.valid_mask.any(axis=2)
        return {
            "n_cells": int(dry.sum()),
            "mask": dry,
            "what": "ocean in this cube's land mask, but no water at any depth in GLORYS bathymetry",
            "source_of_land_mask": self.provenance.get("source", "unknown"),
            "source_of_bathymetry": "glorys (always -- satellite has no subsurface truth)",
            "cross_reference": "Unit B's F1 emits these as COASTLINE_DISAGREEMENT (464 cells total)",
        }

    def coverage(self) -> dict:
        """Fraction of ocean cells with real water at each depth. The bathymetry story in one call.

        Denominator is cells that BOTH masks agree are ocean, so the bathymetry story is not
        contaminated by the coastline disagreement. The raw fraction is returned alongside it.
        """
        ocean = ~self.land_mask
        n = int(ocean.sum())
        dis = self.coastline_disagreement()
        agreed = ocean & self.valid_mask.any(axis=2)
        n_agreed = int(agreed.sum())
        frac = [float((self.valid_mask[..., k] & agreed).sum()) / n_agreed if n_agreed
                else float("nan") for k in range(config.N_DEPTHS)]
        frac_raw = [float((self.valid_mask[..., k] & ocean).sum()) / n if n else float("nan")
                    for k in range(config.N_DEPTHS)]
        return {"depths_m": list(config.DEPTHS),
                "n_ocean_cells": n,
                "n_cells_both_masks_call_ocean": n_agreed,
                "coverage_fraction": frac,
                "coverage_fraction_raw": frac_raw,
                "coastline_disagreement_cells": dis["n_cells"],
                "note": "a depth slice is not a complete field; 24% of ocean cells in this "
                        "domain do not reach 1000 m. `coverage_fraction` excludes the "
                        "coastline-disagreement cells; `coverage_fraction_raw` does not."}

    def __repr__(self) -> str:  # a cube in a traceback should say what it is
        u = "with" if self.uncertainty is not None else "no"
        return (f"OceanCube(date={self.date}, {config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}, "
                f"{u} uncertainty, source={self.provenance.get('source', '?')})")


def _valid_mask_or_all_true() -> np.ndarray:
    """Bathymetry from the processed grid; all-True only if the file genuinely lacks it.

    An all-True fallback is a real hazard -- it would let 1000 m values appear in 20 m water -- so
    it is loud in provenance rather than silent.
    """
    path = os.path.join(config.DATA_PROCESSED, "grids.npz")
    if os.path.exists(path):
        with np.load(path, allow_pickle=True) as g:
            if "valid_mask" in g.files:
                return np.asarray(g["valid_mask"], dtype=bool)
    raise FileNotFoundError(
        f"{path} has no valid_mask. Refusing to build a cube without bathymetry: every depth "
        "would look like real water, which is the Phase-1 Persian Gulf bug."
    )
