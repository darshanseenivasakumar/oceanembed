"""F1 — Multi-source collocation engine.

OWNER: Unit B (Darshan). PHASE-2 ONLY. Baseline is imported, never modified.

WHAT IT DOES
Given (latitude, longitude, datetime), return ONE record saying what every source reports at that
point — satellite, GLORYS, OceanEmbed's reconstruction, the subsurface fields, wind, and Argo if a
float was nearby — together with HOW FAR each match actually was in space and time.

WHY IT IS FIRST
Every later feature asks the same question ("what did each source say here?"). Answering it once,
consistently, is what stops the OceanCube, the Validation Lab and the Sentinel each inventing their
own slightly different matching rules.

────────────────────────────────────────────────────────────────────────────
THE DESIGN IS FORCED BY THE DATA. Measured 2026-08-26, not assumed:

SPATIAL — easy.
    An Argo float sits a median 10.8 km from the nearest grid centre (95th pct 16.1 km, max 19.0).
    A 0.25 deg cell is ~27 km wide, so nearest-neighbour is ALWAYS inside half a cell.
    Bilinear is offered as a refinement, not a necessity.

TEMPORAL — the real scientific decision, and it is uncomfortable.
    Our grids are MONTHLY (the 15th). Argo profiles are irregular. So a random float is a median
    7 days from the nearest gridded date. Measured, over 2,455 profiles:

        +/- 1 day    232 profiles ( 9.5%)
        +/- 3 days   554         (22.6%)
        +/- 5 days   897         (36.5%)
        +/- 7 days  1235         (50.3%)
        +/-15 days  2447         (99.7%)

    Tighter matching means less data; more data means looser matching. There is no free choice.
    Rather than pick one silently, this engine records the ACTUAL offset on every record and
    derives quality from it, so a reader can always see how good a match was instead of trusting
    a label. The tolerance is configurable and its default is stated below.

COVERAGE — satellite exists for only 24 of the 48 GLORYS dates. A record with satellite=None is a
    normal outcome, not an error.
────────────────────────────────────────────────────────────────────────────

RULES THIS MODULE OBEYS
  * Never overwrite a source value. Each source keeps its own numbers, verbatim.
  * Never silently substitute one source for another.
  * Absence is reported as None with a flag, never as zero or as a neighbour's value.
  * Every record carries provenance: which files, which grid cell, which offsets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd

from oceanembed import config                 # baseline: IMPORTED, never modified
from oceanembed.utils import grids, io        # baseline helpers

# ── Quality thresholds ──────────────────────────────────────────────────────
# Stated here, configurable, never invented at the call site. Chosen from the measured
# distribution above: 2 days keeps only genuinely near-simultaneous matches; 5 days is the
# working default used by the baseline's Argo evaluation; beyond 10 days a "match" against a
# monthly field is not defensible.
TEMPORAL_HIGH_D = 2.0
TEMPORAL_MED_D = 5.0
TEMPORAL_LOW_D = 10.0
DEFAULT_TOLERANCE_D = 10.0      # beyond this the record is REJECTed outright

# A float further than this from a grid centre cannot be in that cell at all (half-diagonal
# of a 0.25 deg cell at the equator is ~19.6 km).
SPATIAL_MAX_KM = 20.0

#: The two eras this engine can collocate over. `era` selects the GRIDDED sources; the Argo table
#: follows from it unless the caller overrides. Added 2026-09-03 -- before that the engine could
#: only see the Phase-1 monthly record, so the F1 explorer showed 2019-2022 while every other v2
#: surface showed 2025-2026.
#:
#:   phase1 -- 48 MONTHLY fields, 2019-2022, from the standalone npz files. Every published F1
#:             number was measured here, so this stays the default and its behaviour is unchanged.
#:   daily  -- 388 DAILY fields, 2025-06-01..2026-06-23, read from the v2 bundles. "glorys" is the
#:             reanalysis bundle and "satellite" is daily_sat/v001, the genuine observations.
ERAS = ("phase1", "daily")
ERA_ARGO_TABLE = {"phase1": "argo_test", "daily": "argo_daily_period"}
DAILY_BUNDLES = {"grids.npz": os.path.join("daily"),
                 "satellite_grids.npz": os.path.join("daily_sat", "v001"),
                 "subsurface.npz": os.path.join("daily")}

EARTH_R_KM = 6371.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance. Used rather than a flat approximation so the number is honest
    at the northern edge of the domain, where a degree of longitude is ~13% shorter."""
    p1, p2 = np.deg2rad(lat1), np.deg2rad(lat2)
    dp, dl = p2 - p1, np.deg2rad(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * EARTH_R_KM * np.arcsin(np.sqrt(a)))


@dataclass
class Collocation:
    """One unified ocean-state record. Sources are kept separate on purpose."""
    requested: dict
    matched: dict
    offsets: dict
    sources: dict = field(default_factory=dict)
    quality: str = "UNKNOWN"
    flags: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class CollocationEngine:
    """Matches a (lat, lon, time) query against every available source.

    Files are opened once and cached; a query is then pure indexing.
    """

    def __init__(self, tolerance_days: float = DEFAULT_TOLERANCE_D,
                 spatial_method: str = "nearest", argo_table: str | None = None,
                 era: str = "phase1"):
        """
        era
            Which gridded record to collocate over -- see `ERAS`. Default `"phase1"` keeps the
            2019-2022 monthly behaviour every published F1 number was measured on.

        argo_table
            Which independent-Argo table to match against, WITHOUT the extension.
            `"argo_test"` is 2022 only; `"argo_daily_period"` covers 2025-06..2026-06. Passing
            the wrong one for the era is silent: it returns "no float within range" for every
            point, which is INDISTINGUISHABLE FROM GENUINELY UNSAMPLED OCEAN. That is exactly
            what the F1 explorer displayed on 36 of its 48 dates until 2026-09-03 -- it offered
            2019-2021 dates against a 2022-only table and blamed the empty result on float
            sparsity.

            So the default now follows `era` (`ERA_ARGO_TABLE`) rather than being fixed. That is
            not "guessing from the date", which this docstring has always warned against and
            still forbids -- the era is a deliberate choice the caller states, and an explicit
            `argo_table` still overrides it. Use `argo_coverage()` to report what the chosen
            table actually spans instead of asserting it.
        """
        if spatial_method not in ("nearest", "bilinear"):
            raise ValueError(f"spatial_method must be 'nearest' or 'bilinear', got {spatial_method!r}")
        if era not in ERAS:
            raise ValueError(f"era must be one of {ERAS}, got {era!r}")
        self.tolerance_days = float(tolerance_days)
        self.spatial_method = spatial_method
        self.era = str(era)
        self.argo_table = str(argo_table) if argo_table else ERA_ARGO_TABLE[self.era]
        self._cache: dict[str, Any] = {}
        self._argo: pd.DataFrame | None = None

    # ── source loading ─────────────────────────────────────────────────────
    def _npz(self, name: str):
        """One gridded source, ALWAYS in the Phase-1 key layout.

        The daily bundles store surface variables stacked in one `surface` array indexed by a
        `channels` list, not as separate `sst`/`sss`/... keys. Presenting them here in the older
        layout means `collocate()` needs no branch of its own: one code path produces both eras,
        so they cannot drift into computing different things.
        """
        if name not in self._cache:
            if self.era == "daily":
                self._cache[name] = self._daily_source(name)
            else:
                p = os.path.join(config.DATA_PROCESSED, name)
                self._cache[name] = (dict(np.load(p, allow_pickle=False))
                                     if os.path.exists(p) else None)
        return self._cache[name]

    def _daily_bundle(self, rel: str):
        """The raw daily bundle for one directory, loaded at most once per engine."""
        key = f"__bundle:{rel}"
        if key not in self._cache:
            d = os.path.join(config.DATA_PROCESSED, rel)
            if not os.path.isdir(d):
                self._cache[key] = None
            else:
                from phase2.tscast_nio import dataset as _D
                self._cache[key] = _D.load_daily(d)
        return self._cache[key]

    def _daily_source(self, name: str):
        """A daily bundle, re-keyed to look like the Phase-1 npz it stands in for.

        The view differs by which file it substitutes: `grids.npz` and `satellite_grids.npz` want
        SURFACE u/v (time, lat, lon), while `subsurface.npz` wants u/v PROFILES
        (time, lat, lon, depth). Handing back the surface arrays under the profile keys would let
        `_val` index a 3-D array with four indices -- which happens to return None, but by
        accident rather than by decision, and would break the moment `_val` stopped swallowing
        IndexError.
        """
        rel = DAILY_BUNDLES.get(name)
        if rel is None:
            return None
        b = self._daily_bundle(rel)
        if b is None:
            return None

        ch = [str(c) for c in b["channels"]]
        out = {"times": np.asarray(b["times"]).astype("datetime64[D]"),
               "land_mask": np.asarray(b["land_mask"], bool),
               "temp": np.asarray(b["temp"]),
               "salinity": np.asarray(b["salinity"])}

        if name == "subsurface.npz":
            # The daily bundles carry NO subsurface currents -- temperature and salinity only.
            # NaN makes `_val` return None per level, which is the truthful answer; `collocate`
            # raises SUBSURFACE_CURRENTS_UNAVAILABLE so the absence is attributed to the bundle
            # rather than read as an unsampled ocean.
            nan = np.full(out["temp"].shape, np.nan, dtype="float32")
            out["u"], out["v"] = nan, nan
        else:
            out.update({v: np.asarray(b["surface"][:, :, :, ch.index(v)])
                        for v in ("sst", "sss", "ssh", "u", "v")})
        return out

    def argo_coverage(self) -> dict | None:
        """What the Argo table in use ACTUALLY spans -- so a caller can tell "no float nearby"
        from "this table holds nothing for that year".

        The F1 explorer asserted the first explanation on dates where only the second was true.
        A UI that wants to explain an empty match should read this rather than describe the
        ocean from memory.
        """
        df = self._argo_table()
        if df is None:
            return None
        d = pd.to_datetime(df["date"])
        return {"table": self.argo_table,
                "start": str(d.min().date()), "end": str(d.max().date()),
                "years": sorted({int(y) for y in d.dt.year.unique()}),
                "n_rows": int(len(df))}

    def argo_table_covers(self, when) -> bool:
        """Whether the table has ANY profile in the requested year. False means an empty match
        says nothing about the ocean."""
        cov = self.argo_coverage()
        return bool(cov) and pd.Timestamp(when).year in cov["years"]

    def _argo_table(self) -> pd.DataFrame | None:
        if self._argo is None:
            try:
                df = io.load_table(config.art(self.argo_table))
                df["date"] = pd.to_datetime(df["date"])
                self._argo = df
            except Exception:
                self._argo = pd.DataFrame()
        return None if self._argo.empty else self._argo

    # ── matching ───────────────────────────────────────────────────────────
    @staticmethod
    def _nearest_time(times: np.ndarray, when) -> tuple[int, float]:
        t = times.astype("datetime64[D]")
        target = np.datetime64(pd.Timestamp(when).date(), "D")
        d = (t - target).astype("timedelta64[D]").astype(int)
        k = int(np.argmin(np.abs(d)))
        return k, float(d[k])           # signed: positive = grid date is AFTER the request

    def _grid_cell(self, lat: float, lon: float) -> tuple[int, int, float]:
        i, j = grids.nearest_lat_index(lat), grids.nearest_lon_index(lon)
        km = _haversine_km(lat, lon, float(config.LAT[i]), float(config.LON[j]))
        return i, j, km

    @staticmethod
    def _val(arr, *idx):
        """Extract one value, converting NaN to None so 'no data' is never mistaken for zero."""
        try:
            v = float(arr[idx])
        except Exception:
            return None
        return None if not np.isfinite(v) else round(v, 4)

    # ── the public call ────────────────────────────────────────────────────
    def collocate(self, latitude: float, longitude: float, datetime, *,
                  include_profile: bool = True) -> Collocation:
        """Return every source's view of one point. Missing sources come back as None."""
        req_dt = pd.Timestamp(datetime)
        flags: list[str] = []

        in_domain = (config.LAT.min() <= latitude <= config.LAT.max()
                     and config.LON.min() <= longitude <= config.LON.max())
        if not in_domain:
            flags.append("OUTSIDE_DOMAIN")

        i, j, km = self._grid_cell(latitude, longitude)
        if km > SPATIAL_MAX_KM:
            flags.append("SPATIAL_OFFSET_EXCEEDS_CELL")

        g = self._npz("grids.npz")
        if g is None:
            raise FileNotFoundError(
                "data/processed/grids.npz missing — run scripts/prepare_dataset.py --real first.")

        t_idx, t_off = self._nearest_time(g["times"], req_dt)
        if abs(t_off) > self.tolerance_days:
            flags.append("TEMPORAL_OFFSET_EXCEEDS_TOLERANCE")

        # "LAND" alone is ambiguous — WHOSE land? The two products disagree about the coastline
        # in 464 cells (179 ocean in satellite only, 285 in GLORYS only), concentrated in the
        # Persian Gulf, Gulf of Thailand and Red Sea. At 29.5N 48.25E GLORYS masks the shallow
        # head of the Persian Gulf while the satellite product resolves it and reports
        # 19.3 degC / 39.55 psu — winter-cool and hypersaline, which is physically correct.
        # Saying only "LAND" there would misrepresent real satellite data as absent.
        is_land = bool(g["land_mask"][i, j])
        if is_land:
            flags.append("LAND_IN_GLORYS")

        sources: dict[str, Any] = {}

        # GLORYS — the reference/reanalysis. Surface + full temperature profile.
        gl: dict[str, Any] = {k: self._val(g[k], t_idx, i, j) for k in ("sst", "sss", "ssh", "u", "v")}
        if include_profile:
            gl["temperature_profile"] = [self._val(g["temp"], t_idx, i, j, k)
                                         for k in range(config.N_DEPTHS)]
        gl["datetime"] = str(pd.Timestamp(g["times"][t_idx]).date())
        sources["glorys"] = gl

        # Subsurface salinity / currents (Phase-2 extraction).
        sub = self._npz("subsurface.npz")
        if sub is not None:
            s_idx, s_off = self._nearest_time(sub["times"], req_dt)
            sources["subsurface"] = {
                "salinity_profile": [self._val(sub["salinity"], s_idx, i, j, k)
                                     for k in range(config.N_DEPTHS)],
                "u_profile": [self._val(sub["u"], s_idx, i, j, k) for k in range(config.N_DEPTHS)],
                "v_profile": [self._val(sub["v"], s_idx, i, j, k) for k in range(config.N_DEPTHS)],
                "datetime": str(pd.Timestamp(sub["times"][s_idx]).date()),
                "temporal_offset_days": s_off,
            }
            if self.era == "daily":
                # Named so an all-None u/v profile is attributed to the bundle, not to the ocean.
                flags.append("SUBSURFACE_CURRENTS_UNAVAILABLE")
        else:
            sources["subsurface"] = None
            flags.append("SUBSURFACE_UNAVAILABLE")

        # Satellite — genuinely absent on half our dates. That is normal, not an error.
        sat = self._npz("satellite_grids.npz")
        if sat is not None:
            k_idx, k_off = self._nearest_time(sat["times"], req_dt)
            if abs(k_off) <= self.tolerance_days:
                sources["satellite"] = {
                    **{v: self._val(sat[v], k_idx, i, j) for v in ("sst", "sss", "ssh", "u", "v")},
                    "datetime": str(pd.Timestamp(sat["times"][k_idx]).date()),
                    "temporal_offset_days": k_off,
                }
            else:
                sources["satellite"] = None
                flags.append("SATELLITE_OUTSIDE_TOLERANCE")
        else:
            sources["satellite"] = None
            flags.append("SATELLITE_UNAVAILABLE")

        # Coastline disagreement is itself a finding, and F9 Sentinel consumes it.
        sat_grid = self._npz("satellite_grids.npz")
        if sat_grid is not None:
            sat_is_ocean = not bool(sat_grid["land_mask"][i, j])
            if is_land and sat_is_ocean:
                flags.append("COASTLINE_DISAGREEMENT_SATELLITE_SAYS_OCEAN")
            elif (not is_land) and (not sat_is_ocean):
                flags.append("COASTLINE_DISAGREEMENT_SATELLITE_SAYS_LAND")

        # Argo — independent instrument. Nearest profile within tolerance, or None.
        sources["argo"] = self._match_argo(latitude, longitude, req_dt)
        if sources["argo"] is None:
            flags.append("NO_ARGO_NEARBY")

        record = Collocation(
            requested={"latitude": float(latitude), "longitude": float(longitude),
                       "datetime": str(req_dt)},
            matched={"latitude": float(config.LAT[i]), "longitude": float(config.LON[j]),
                     "datetime": str(pd.Timestamp(g["times"][t_idx]).date()),
                     "grid_i": int(i), "grid_j": int(j), "time_index": int(t_idx),
                     "cell_id": int(grids.latlon_to_cell_id(latitude, longitude))},
            offsets={"spatial_km": round(km, 3), "temporal_days": t_off,
                     "spatial_method": self.spatial_method},
            sources=sources,
            flags=flags,
            provenance={
                # Derived from the class, never hardcoded: the literal string here used to say
                # "phase2.collocation.CollocationEngine", a path that does not import. Provenance
                # that cannot be followed back to real code is worse than none.
                "engine": f"{type(self).__module__}.{type(self).__qualname__}",
                "tolerance_days": self.tolerance_days,
                "grid": f"{config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}",
                "depths_m": list(config.DEPTHS),
                "era": self.era,
                "argo_table": self.argo_table,
                # De-duplicated because in the daily era `grids.npz` and `subsurface.npz` are both
                # served from the SAME bundle directory, and listing it twice reads like two
                # independent sources when there is one.
                "files": sorted({(DAILY_BUNDLES[f].replace(os.sep, "/") if self.era == "daily"
                                  else f)
                                 for f in ("grids.npz", "satellite_grids.npz", "subsurface.npz")
                                 if self._npz(f) is not None}),
            },
        )
        record.quality = self._quality(record)
        return record

    def match_argo(self, lat: float, lon: float, when) -> dict | None:
        """Public entry to the SAME Argo matcher `collocate()` uses.

        Exposed so v2 can reuse F1's validated matching instead of growing a second one that would
        drift from it. Behaviour is byte-identical -- this only makes the call reachable.
        """
        return self._match_argo(float(lat), float(lon), pd.Timestamp(when))

    def _match_argo(self, lat: float, lon: float, when: pd.Timestamp) -> dict | None:
        """Nearest Argo profile in space AND time, or None. Never the nearest in one alone."""
        df = self._argo_table()
        if df is None:
            return None
        lo, hi = when - pd.Timedelta(days=self.tolerance_days), when + pd.Timedelta(days=self.tolerance_days)
        sub = df[(df["date"] >= lo) & (df["date"] <= hi)]
        if sub.empty:
            return None
        # cheap bounding box first, then exact distance on the survivors
        box = sub[(sub["lat"].sub(lat).abs() < 1.0) & (sub["lon"].sub(lon).abs() < 1.0)]
        if box.empty:
            return None
        best, best_km = None, np.inf
        for (la, ln, dt), grp in box.groupby(["lat", "lon", "date"]):
            d = _haversine_km(lat, lon, float(la), float(ln))
            if d < best_km:
                best_km, best = d, (float(la), float(ln), pd.Timestamp(dt), grp)
        if best is None:
            return None
        la, ln, dt, grp = best
        prof: list = [None] * config.N_DEPTHS
        for k, t in zip(grp["depth_idx"].to_numpy(), grp["temp"].to_numpy()):
            if 0 <= int(k) < config.N_DEPTHS and np.isfinite(t):
                prof[int(k)] = round(float(t), 4)
        return {
            "latitude": la, "longitude": ln, "datetime": str(dt.date()),
            "temperature_profile": prof,
            "spatial_offset_km": round(best_km, 3),
            "temporal_offset_days": float((dt.normalize() - when.normalize()).days),
            "n_levels": int(sum(p is not None for p in prof)),
            "note": "INDEPENDENT observation — never used for training",
        }

    def _quality(self, r: Collocation) -> str:
        """Quality is derived from MEASURED offsets, never asserted."""
        if "LAND_IN_GLORYS" in r.flags or "OUTSIDE_DOMAIN" in r.flags:
            return "REJECT"
        if "TEMPORAL_OFFSET_EXCEEDS_TOLERANCE" in r.flags or "SPATIAL_OFFSET_EXCEEDS_CELL" in r.flags:
            return "REJECT"
        dt = abs(r.offsets["temporal_days"])
        if dt <= TEMPORAL_HIGH_D:
            return "HIGH"
        if dt <= TEMPORAL_MED_D:
            return "MEDIUM"
        if dt <= TEMPORAL_LOW_D:
            return "LOW"
        return "REJECT"


# module-level convenience
_ENGINE: CollocationEngine | None = None


def collocate(latitude: float, longitude: float, datetime, **kw) -> dict:
    """One-shot collocation using a shared cached engine."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CollocationEngine()
    return _ENGINE.collocate(latitude, longitude, datetime, **kw).to_dict()
