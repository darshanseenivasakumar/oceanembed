"""Is there a real cyclone track inside the model's window? Owner: Unit A (Arjhun).

Feature 4 (3-D TCHP + cyclone case study) needs a storm track, and the repo has none. The build
spec suggested "Cyclone Biparjoy or Mocha -- pick one with a track that crosses your data window,
2025-06-01 to 2026-06-23". Both are 2023 storms and neither is in that window, which is exactly why
this script exists: the track comes from the archive, never from a name someone remembered.

SOURCE
  IBTrACS v04r01, NOAA NCEI -- the WMO-endorsed best-track archive.
  https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/

  The `last3years` CSV is used rather than the full North Indian basin file: 10.3 MB against
  27.9 MB, and it covers our window with room to spare. Basin `NI` is filtered here.

CAVEAT THAT MUST TRAVEL WITH ANY RESULT
  Recent seasons in IBTrACS are PROVISIONAL. `TRACK_TYPE` and the agency columns say how much of a
  storm is operational best-track versus post-season reanalysis, and a 2025-2026 storm is not the
  same evidential object as a 2015 one. The output records it per storm rather than flattening it.

    python scripts/phase2/probe_ibtracs.py            # download if absent, then report
    python scripts/phase2/probe_ibtracs.py --refresh  # re-download
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import time
import urllib.request

BASE = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-"
        "ibtracs/v04r01/access/csv/")
FILENAME = "ibtracs.last3years.list.v04r01.csv"
RAW_DIR = os.path.join("data", "raw", "ibtracs")
OUT = os.path.join("artifacts", "ibtracs_probe.json")

#: The model's reconstruction window and grid box. Imported rather than hardcoded would be better,
#: but the window is a property of the BUNDLE, not of config -- so it is stated and checked below.
WINDOW = ("2025-06-01", "2026-06-23")
BOX = dict(lat=(5.0, 30.0), lon=(45.0, 105.0))
UA = {"User-Agent": "OceanEmbed-SIH26066 (INCOIS/MoES student project) probe"}


def download(refresh: bool = False) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, FILENAME)
    if os.path.exists(path) and not refresh:
        return path
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(BASE + FILENAME, headers=UA),
                                timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())
    print(f"  downloaded {FILENAME}  {os.path.getsize(path) / 1e6:.1f} MB in {time.time() - t:.1f} s")
    return path


def storms(path: str, window=WINDOW, box=BOX) -> list[dict]:
    """Every NI-basin system with a track point inside the window, with its in-box point count."""
    w0, w1 = window
    by: dict[str, dict] = collections.OrderedDict()
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        next(rd)                                           # the units row, not data
        for r in rd:
            if r["BASIN"] != "NI":
                continue
            day = r["ISO_TIME"][:10]
            if not (w0 <= day <= w1):
                continue
            try:
                lat, lon = float(r["LAT"]), float(r["LON"])
            except ValueError:
                continue                                   # a track point with no position
            d = by.setdefault(r["SID"], dict(
                sid=r["SID"], name=r["NAME"].strip() or "UNNAMED", first=day, last=day,
                n_points=0, n_in_box=0, max_wind_kt=0.0, lat=[], lon=[], track_types=set()))
            d["last"] = day
            d["n_points"] += 1
            d["lat"].append(lat)
            d["lon"].append(lon)
            d["track_types"].add(r.get("TRACK_TYPE", "").strip())
            if box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]:
                d["n_in_box"] += 1
            for col in ("WMO_WIND", "USA_WIND"):
                try:
                    d["max_wind_kt"] = max(d["max_wind_kt"], float(r[col]))
                except (ValueError, KeyError):
                    pass                                   # a blank wind is missing, not zero

    out = []
    for d in by.values():
        d["lat_range"] = [min(d["lat"]), max(d["lat"])]
        d["lon_range"] = [min(d["lon"]), max(d["lon"])]
        d["track_types"] = sorted(t for t in d["track_types"] if t)
        del d["lat"], d["lon"]
        out.append(d)
    return sorted(out, key=lambda d: -d["max_wind_kt"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    print(f"IBTrACS probe -- NI basin, {WINDOW[0]} .. {WINDOW[1]}")
    path = download(a.refresh)
    found = storms(path)

    print(f"\n  {len(found)} system(s) with track points in the window\n")
    print("  %-14s %-10s %-11s %-11s %5s %6s %8s" %
          ("SID", "NAME", "FIRST", "LAST", "PTS", "INBOX", "MAXWIND"))
    for d in found:
        print("  %-14s %-10s %-11s %-11s %5d %6d %8.0f  %.1f-%.1fN %.1f-%.1fE" % (
            d["sid"], d["name"][:10], d["first"], d["last"], d["n_points"], d["n_in_box"],
            d["max_wind_kt"], *d["lat_range"], *d["lon_range"]))

    usable = [d for d in found if d["n_in_box"] >= 10 and d["max_wind_kt"] >= 34.0]
    os.makedirs("artifacts", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "what": "NI-basin best tracks inside the model's reconstruction window",
            "source": BASE + FILENAME,
            "source_note": ("IBTrACS v04r01, NOAA NCEI. Recent seasons are PROVISIONAL -- see "
                            "TRACK_TYPE per storm."),
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file_bytes": os.path.getsize(path),
            "window": list(WINDOW), "box": BOX,
            "n_systems": len(found), "systems": found,
            "usable_for_case_study": [d["sid"] for d in usable],
            "usable_criterion": ">=10 track points inside the grid box and >=34 kt (tropical storm)",
        }, f, indent=1)
    print(f"\n  wrote {OUT}")

    if not usable:
        print("\n  NO usable case study: nothing reaches tropical-storm strength inside the box.")
        print("  Feature 4 is BLOCKED -- say so in AGENT_SYNC; do not substitute a storm from "
              "outside the window.")
        return 1
    print(f"\n  {len(usable)} candidate(s) for the case study: {', '.join(d['name'] for d in usable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
