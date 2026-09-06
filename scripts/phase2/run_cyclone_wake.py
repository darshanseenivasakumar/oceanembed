"""Precompute the cyclone cold-wake case studies. Owner: Unit A (Arjhun).

    .venv/Scripts/python.exe scripts/phase2/run_cyclone_wake.py            # all usable storms
    .venv/Scripts/python.exe scripts/phase2/run_cyclone_wake.py --sid 2025275N22068

WHY THIS IS A SCRIPT AND NOT A PAGE
A passage-relative wake needs one whole-basin reconstruction per storm-day either side. Measured
at 32.09 s on CPU (artifacts/export_timing.json), SHAKHTI at stride 4 is 14 dates -- and the live
page is worse than that: it unions the peak date to 15, and app/phase2/_fields.py caps its cache
at 6 entries, so the three case-study panels re-reconstruct two evicted dates. About 17 fields,
nine minutes, in front of a judge.

So it is computed ONCE here, written to an artifact, and the dashboard renders the artifact behind
a CACHED chip. That is what the project's real-data rule permits: a cached result is allowed
precisely when the real model produced it and the UI says so.

THIS SCRIPT ONLY READS THE MODEL. It loads the frozen checkpoint through the ordinary predictor
and writes nothing under artifacts/ except its own cyclone_wake_* outputs.

WHAT COMES OUT
  artifacts/cyclone_wake_<sid>.json   the verdict, every track point, and the naive contrast
  artifacts/cyclone_wake_<sid>.npz    the three TCHP maps the case-study panels draw

THE NAIVE CONTRAST IS NOT OPTIONAL
`naive_wake` measures the same storm against ONE fixed before/after pair -- what a reader would
compute by default. On SHAKHTI it returns -0.18 kJ/cm2 and 58% cooling against the passage-relative
-4.26 and 92%. Shipping the wake without it would be shipping the answer without the reason the
answer is interesting.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                       # noqa: E402
from phase2.data import ibtracs as IB                       # noqa: E402
from phase2.derived import cyclone as CY                    # noqa: E402
from phase2.derived.heat_content import heat_content_field  # noqa: E402
from phase2.tscast_nio import field_cache as FC             # noqa: E402

#: Same criterion the probe used, restated here so the script does not depend on the probe having
#: been run: enough track points inside the grid box to sample, and at least tropical-storm force.
MIN_POINTS_IN_BOX = 10
MIN_WIND_KT = 34.0

DEFAULT_STRIDE = 4


def usable_storms() -> list[dict]:
    """Storms the model can actually answer for: in the box, strong enough, and IN THE WINDOW.

    The window filter is not a nicety. IBTrACS' last-3-years file covers 2023 onward, so without
    it this returns MICHAUNG, MIDHILI, FENGAL and ASNA -- 2023 and 2024 storms the bundle has no
    fields for at all. Every one of their dates would skip, and the feature would render a storm
    with no evaluable track points and call it a null wake.
    """
    dates = FC.available_dates(stage=1)
    window = (dates[0], dates[-1])
    tracks = IB.load_tracks(window=window)
    # in_box wants (min, max) BOUNDS, not the grid arrays. Passing the arrays returns all-False
    # and the script silently reports "no usable storm" on a repo that has four.
    lat_b = (float(np.min(base.LAT)), float(np.max(base.LAT)))
    lon_b = (float(np.min(base.LON)), float(np.max(base.LON)))
    out = []
    for sid, s in tracks.items():
        inbox = IB.in_box(s, lat=lat_b, lon=lon_b)
        w = s.get("max_wind_kt")
        if int(np.asarray(inbox).sum()) >= MIN_POINTS_IN_BOX and w and w >= MIN_WIND_KT:
            out.append(s)
    return sorted(out, key=lambda s: -(s.get("max_wind_kt") or 0.0))


def tchp_for(dates, device, stride_note) -> tuple[dict, list]:
    """One TCHP map per date. The expensive half; everything else is arithmetic."""
    pred = FC.get_predictor(stage=1)
    by_date, missing = {}, []
    for k, d in enumerate(dates, 1):
        t0 = time.time()
        try:
            f = FC.field_for(d, stage=1, device=device, predictor=pred)
        except Exception as e:
            # A date outside the bundle is a REAL answer -- the storm ran past the window -- and
            # cold_wake already skips and counts it. Never substitute a neighbouring day.
            missing.append({"date": d, "why": f"{type(e).__name__}: {e}"})
            print(f"  [{k:2}/{len(dates)}] {d}  SKIPPED -- {type(e).__name__}")
            continue
        by_date[d] = np.asarray(heat_content_field(f)["tchp"], dtype="float64")
        print(f"  [{k:2}/{len(dates)}] {d}  {time.time() - t0:5.1f} s")
    return by_date, missing


def run_one(storm: dict, *, stride: int, device: str | None) -> dict:
    sid, name = storm["sid"], storm.get("name") or "UNNAMED"
    print(f"\n{name} ({sid})  {storm['first']} -> {storm['last']}  "
          f"{storm['n_points']} track points")

    dates = CY.dates_needed(storm, stride=stride)
    cs = IB.case_study_dates(storm)
    # The three case-study panels need their own dates, and the "during" date is NOT guaranteed to
    # be in dates_needed -- it is the peak, not a passage +/- offset. Union it in, or the page
    # draws a panel from a field that was never reconstructed.
    panel_dates = [cs["before"], cs["during"], cs["after"]]
    want = sorted(set(dates) | {d for d in panel_dates if d})
    print(f"  {len(dates)} wake dates + {len(want) - len(dates)} panel date(s) = "
          f"{len(want)} reconstructions")

    t0 = time.time()
    by_date, missing = tchp_for(want, device, stride)
    secs = time.time() - t0

    rel = CY.cold_wake(storm, by_date, stride=stride)
    naive = CY.naive_wake(storm, by_date, cs["before"], cs["after"], stride=stride)

    out = {
        "what": "TCHP change along a real cyclone track, each point against its OWN passage time",
        "sid": sid, "name": name,
        "first": storm["first"], "last": storm["last"],
        "n_track_points": int(storm["n_points"]),
        "category": storm.get("category"),
        # Both agency winds, always. WMO and USA disagree by 14 kt on SHAKHTI, which spans a
        # category boundary -- a page that quotes one number is quoting a choice it did not make.
        "max_wind_kt": storm.get("max_wind_kt"),
        "max_wind_kt_wmo": storm.get("max_wind_kt_wmo"),
        "max_wind_kt_usa": storm.get("max_wind_kt_usa"),
        "agencies_disagree_kt": storm.get("agencies_disagree_kt"),
        "track_types": storm.get("track_types"),
        "stride": int(stride),
        "case_study": cs,
        "dates_reconstructed": sorted(by_date),
        "dates_missing": missing,
        "n_reconstructions": len(by_date),
        "seconds": round(secs, 1),
        "device": device or "cpu",
        "checkpoint": os.path.basename(FC.checkpoint_for(1)),
        "cache_version": FC.cache_version(1),
        "passage_relative": rel,
        "naive_fixed_pair": naive,
        "source": "IBTrACS v04r01, NOAA NCEI -- data/raw/ibtracs/",
        "note": ("passage_relative measures each track point against its own passage time; "
                 "naive_fixed_pair measures every point against ONE before/after pair. The gap "
                 "between them is the finding, not a discrepancy."),
    }

    js = base.art(f"cyclone_wake_{sid}.json")
    os.makedirs(os.path.dirname(js), exist_ok=True)
    with open(js, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    # Maps go to npz, not JSON: three 100x240 float arrays are ~576 KB of numerals and would make
    # the summary unreadable and slow to parse in the page.
    maps = {k: by_date[d] for k, d in zip(("before", "during", "after"), panel_dates)
            if d in by_date}
    np.savez_compressed(base.art(f"cyclone_wake_{sid}.npz"),
                        lat=np.asarray(base.LAT), lon=np.asarray(base.LON), **maps)

    v = rel.get("verdict", "?")
    print(f"  -> {v}")
    if rel.get("n_points"):
        print(f"     passage-relative  mean {rel['mean_change']:+.2f} kJ/cm2   "
              f"{rel['n_cooled']} of {rel['n_points']} cooled "
              f"({rel['fraction_cooled']:.0%})")
    if naive.get("n_points"):
        print(f"     one fixed pair    mean {naive['mean_change']:+.2f} kJ/cm2   "
              f"{naive['n_cooled']} of {naive['n_points']} cooled "
              f"({naive['fraction_cooled']:.0%})")
    print(f"     wrote {os.path.basename(js)} and .npz in {secs / 60:.1f} min")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sid", default=None, help="one storm id; default is every usable storm")
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    ap.add_argument("--device", default=None, help="cuda to use the GPU (about 4x faster)")
    a = ap.parse_args()

    storms = usable_storms()
    if a.sid:
        storms = [s for s in storms if s["sid"] == a.sid]
        if not storms:
            raise SystemExit(f"no usable storm with sid {a.sid}")
    if not storms:
        raise SystemExit("no storm meets the usable criterion -- nothing to compute, and a "
                         "fabricated track is not an option")

    print(f"{len(storms)} storm(s), stride {a.stride}, device {a.device or 'cpu'}")
    for s in storms:
        run_one(s, stride=a.stride, device=a.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
