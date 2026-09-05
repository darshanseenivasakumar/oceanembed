"""Cyclone best tracks from IBTrACS. Owner: Unit A (Arjhun).

The archive is the only acceptable source for a track. The build spec for this feature suggested
"Cyclone Biparjoy or Mocha"; both are 2023 storms and neither appears anywhere in the model's
2025-06-01 .. 2026-06-23 window, so hardcoding either would have drawn a track over a field from a
different year -- the same class of error as the GLORYS-2022 era bug. `probe_ibtracs.py` found what
is actually in the window; this module loads it.

    IBTrACS v04r01, NOAA NCEI -- the WMO-endorsed best-track archive.
    data/raw/ibtracs/ibtracs.last3years.list.v04r01.csv, fetched 2026-09-05.

TWO THINGS THE CSV WILL DO TO YOU IF YOU LET IT
-----------------------------------------------
ROW 1 IS UNITS, NOT DATA. `SEASON` reads "Year" and `LAT` reads "degrees_north". Parsed as a track
point it becomes a storm at latitude NaN that silently disappears, or worse, a coordinate of 0.

A BLANK WIND IS MISSING, NOT ZERO. `WMO_WIND` is empty for storms no WMO agency rated, and
`float("")` raises while `int(x or 0)` quietly returns a calm cyclone. Every intensity here is
None when absent, and `max_wind_kt` is None rather than 0 when a storm has no rating at all.

PROVISIONAL DATA
Recent seasons are provisional: `track_type` and the agency columns record how much of a track is
operational best-track versus post-season reanalysis. A 2025 storm is not the same evidential
object as a 2015 one, and that field travels with every track rather than being flattened away.
"""
from __future__ import annotations

import csv
import os

import numpy as np

DEFAULT_PATH = os.path.join("data", "raw", "ibtracs", "ibtracs.last3years.list.v04r01.csv")
SOURCE_URL = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-"
              "stewardship-ibtracs/v04r01/access/csv/ibtracs.last3years.list.v04r01.csv")

#: North Indian, the basin this project covers.
BASIN = "NI"

#: Saffir-Simpson-ish thresholds in knots, for a label a reader recognises. `None` in means
#: "unrated", which is a different thing from "weak" and is labelled as such.
_CATEGORIES = ((137, "Cat 5"), (113, "Cat 4"), (96, "Cat 3"), (83, "Cat 2"), (64, "Cat 1"),
               (34, "tropical storm"), (0, "depression"))


def _num(row: dict, key: str):
    """A float, or None. Never 0.0 for a blank -- a missing wind is not a calm storm."""
    v = (row.get(key) or "").strip()
    if v in ("", " ", "NOT_NAMED"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def category(max_wind_kt) -> str:
    if max_wind_kt is None:
        return "unrated"
    for thr, name in _CATEGORIES:
        if max_wind_kt >= thr:
            return name
    return "depression"


def load_tracks(path: str = DEFAULT_PATH, *, basin: str = BASIN,
                window: tuple[str, str] | None = None) -> dict[str, dict]:
    """Every storm in `basin`, keyed by SID. `window` filters to tracks with a point inside it.

    Each value: sid, name, first, last, track_types, n_points, max_wind_kt (None if unrated), and
    the point arrays time/lat/lon/wind_kt/pres_mb -- all the same length, ordered in time.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Fetch it with scripts/phase2/probe_ibtracs.py, which downloads "
            f"from {SOURCE_URL} and reports what is inside the model's window.")

    storms: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        next(rd)                                       # the units row -- see the module docstring
        for r in rd:
            if r.get("BASIN") != basin:
                continue
            lat, lon = _num(r, "LAT"), _num(r, "LON")
            if lat is None or lon is None:
                continue                               # a track point with no position
            sid = r["SID"]
            s = storms.setdefault(sid, {
                "sid": sid, "name": (r.get("NAME") or "").strip() or "UNNAMED",
                "time": [], "lat": [], "lon": [], "wind_kt": [], "pres_mb": [],
                "wind_kt_wmo": [], "wind_kt_usa": [], "track_types": set()})
            s["time"].append(r["ISO_TIME"])
            s["lat"].append(lat)
            s["lon"].append(lon)
            # BOTH agencies are kept, because they DISAGREE. [MEASURED on SHAKHTI: WMO peaks at
            # 60 kt over 41 rated points, the US agency at 74 kt over 29 -- a 14 kt gap, which is
            # the difference between a tropical storm and a Category 1.] Reporting one silently, or
            # the max across both, presents a choice between two estimates as a single fact.
            # `wind_kt` prefers WMO because it is the WMO-endorsed archive; `wind_kt_usa` travels
            # beside it so a page can show the disagreement rather than hide it.
            w = _num(r, "WMO_WIND")
            uw = _num(r, "USA_WIND")
            s["wind_kt"].append(w if w is not None else uw)
            s["wind_kt_wmo"].append(w)
            s["wind_kt_usa"].append(uw)
            p = _num(r, "WMO_PRES")
            s["pres_mb"].append(p if p is not None else _num(r, "USA_PRES"))
            tt = (r.get("TRACK_TYPE") or "").strip()
            if tt:
                s["track_types"].add(tt)

    out = {}
    for sid, s in storms.items():
        days = [t[:10] for t in s["time"]]
        if window and not any(window[0] <= d <= window[1] for d in days):
            continue
        def _peak(key):
            vals = [w for w in s[key] if w is not None]
            return max(vals) if vals else None

        s.update(first=min(days), last=max(days), n_points=len(days),
                 track_types=sorted(s["track_types"]),
                 max_wind_kt=_peak("wind_kt"),
                 max_wind_kt_wmo=_peak("wind_kt_wmo"),
                 max_wind_kt_usa=_peak("wind_kt_usa"))
        s["category"] = category(s["max_wind_kt"])
        w, u = s["max_wind_kt_wmo"], s["max_wind_kt_usa"]
        s["agencies_disagree_kt"] = (abs(w - u) if (w is not None and u is not None) else None)
        for k in ("lat", "lon"):
            s[k] = np.asarray(s[k], dtype="float64")
        out[sid] = s
    return out


def in_box(storm: dict, *, lat: tuple[float, float], lon: tuple[float, float]) -> np.ndarray:
    """Boolean per track point: is it inside the model grid? Used, never used to CLIP.

    A track clipped to the box would draw a storm that stops at 105 E, which is a statement about
    the grid rendered as a statement about the cyclone.
    """
    return ((storm["lat"] >= lat[0]) & (storm["lat"] <= lat[1])
            & (storm["lon"] >= lon[0]) & (storm["lon"] <= lon[1]))


def peak_index(storm: dict) -> int | None:
    """Index of maximum intensity, or None when the storm carries no wind rating at all.

    None rather than 0: index 0 is genesis, and silently calling that the peak would put the
    "during" panel of a case study at the wrong end of the storm.
    """
    winds = storm["wind_kt"]
    rated = [(w, i) for i, w in enumerate(winds) if w is not None]
    return max(rated)[1] if rated else None


def case_study_dates(storm: dict, *, before_days: int = 3, after_days: int = 5) -> dict:
    """before / during / after dates bracketing peak intensity, as YYYY-MM-DD.

    "During" is the peak, not the midpoint: the cold wake a case study looks for is cut by the
    strongest winds, and averaging over the storm's life would blur exactly the signal.

    `after` is deliberately further out than `before`. A wake takes days to reach its full depth
    and is still visible for a week or more, while the ocean ahead of the storm is undisturbed the
    day before it arrives.
    """
    k = peak_index(storm)
    if k is None:
        return {"peak_index": None, "reason": "the storm carries no wind rating, so it has no peak"}
    peak = np.datetime64(storm["time"][k][:10])
    return {
        "peak_index": k,
        "peak_time": storm["time"][k],
        "peak_wind_kt": storm["wind_kt"][k],
        "peak_lat": float(storm["lat"][k]), "peak_lon": float(storm["lon"][k]),
        "before": str(peak - np.timedelta64(int(before_days), "D")),
        "during": str(peak),
        "after": str(peak + np.timedelta64(int(after_days), "D")),
    }
