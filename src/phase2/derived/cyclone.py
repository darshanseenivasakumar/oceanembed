"""Did the ocean cool where the cyclone went? Owner: Unit A (Arjhun).

A tropical cyclone mixes and upwells cold water, leaving a COLD WAKE that is visible for a week or
more. If a reconstruction driven only by surface satellite fields shows that wake, it is
reproducing a process nobody taught it -- which is a far stronger statement than any RMSE.

THE METHODOLOGICAL POINT, AND IT IS THE WHOLE FEATURE
-----------------------------------------------------
A single before / during / after triple, applied to the whole track, gives a NULL result. Measured
on Cyclone SHAKHTI (2025-10-01..07, Arabian Sea) with before = 2025-10-02 and after = 2025-10-10:

    mean change along the track   -0.2 kJ/cm2      7 of 12 points cooled

That is not because there is no wake. It is because a storm takes days to cross a basin, so one
pair of dates asks the wrong question at every point but one. Water at 68 E was hit on day 1 and
had eight days to recover by the "after" date -- it warmed. Water at 60 E was hit on day 6 and its
wake was three days old -- it cooled hard. Averaging the two gives nothing.

Measuring each point against ITS OWN passage time gives the signal cleanly:

    mean change   -4.26 kJ/cm2   median -4.27   cooled at 11 of 12 points (92%)

Same storm, same reconstruction, same TCHP code. Only the question changed.

WHY THE WINDOW IS ASYMMETRIC
`before_days=3` and `after_days=5`. The ocean ahead of a storm is undisturbed the day before it
arrives, so a short lead is enough; a wake deepens over several days and persists for a week or
more, so a longer lag catches it near its full extent. Symmetric windows would sample the wake
before it had formed.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config as base
from phase2.derived.transect import bilinear_at

DEFAULT_BEFORE_DAYS = 3
DEFAULT_AFTER_DAYS = 5


def dates_needed(storm: dict, *, before_days: int = DEFAULT_BEFORE_DAYS,
                 after_days: int = DEFAULT_AFTER_DAYS, stride: int = 1) -> list[str]:
    """Every date a passage-relative wake needs, sorted. Ask once, reconstruct once.

    A caller that reconstructed per track point would build the same field dozens of times: a
    storm sampled 6-hourly revisits the same day four times over.

    `stride` MUST match the stride passed to `cold_wake`, or the caller reconstructs days it never
    samples -- at ~30 s a field on CPU that is minutes of a demo spent on fields nobody sees.
    """
    step = max(1, int(stride))
    days = {storm["time"][i][:10] for i in range(0, len(storm["time"]), step)}
    out = set()
    for d in days:
        base_d = np.datetime64(d)
        out.add(str(base_d - np.timedelta64(int(before_days), "D")))
        out.add(str(base_d + np.timedelta64(int(after_days), "D")))
    return sorted(out)


def cold_wake(storm: dict, tchp_by_date: dict, *, before_days: int = DEFAULT_BEFORE_DAYS,
              after_days: int = DEFAULT_AFTER_DAYS, stride: int = 1,
              lat=None, lon=None) -> dict:
    """TCHP before and after the storm passed, AT EACH TRACK POINT'S OWN PASSAGE TIME.

    storm         : an `ibtracs.load_tracks` entry.
    tchp_by_date  : {"YYYY-MM-DD": (n_lat, n_lon) TCHP}, covering `dates_needed`.
    stride        : take every nth track point. IBTrACS is 3- or 6-hourly and consecutive points
                    fall inside one grid cell, so a stride keeps the sample from being dominated
                    by repeats of the same water.

    Returns per-point rows plus a summary. A point whose before OR after date is missing from
    `tchp_by_date`, or whose TCHP is NaN at either end, is SKIPPED and counted -- never filled,
    and never scored as zero change, which would read as "the storm did nothing here".
    """
    lat_g = np.asarray(base.LAT if lat is None else lat, dtype="float64")
    lon_g = np.asarray(base.LON if lon is None else lon, dtype="float64")

    rows, skipped = [], {"no_field": 0, "not_finite": 0}
    for i in range(0, len(storm["time"]), max(1, int(stride))):
        passage = np.datetime64(storm["time"][i][:10])
        d_before = str(passage - np.timedelta64(int(before_days), "D"))
        d_after = str(passage + np.timedelta64(int(after_days), "D"))
        if d_before not in tchp_by_date or d_after not in tchp_by_date:
            skipped["no_field"] += 1
            continue
        la, lo = float(storm["lat"][i]), float(storm["lon"][i])
        b = bilinear_at(tchp_by_date[d_before], la, lo, lat_g, lon_g)
        a = bilinear_at(tchp_by_date[d_after], la, lo, lat_g, lon_g)
        if not (np.isfinite(a) and np.isfinite(b)):
            skipped["not_finite"] += 1
            continue
        rows.append({
            "index": i, "time": storm["time"][i], "lat": la, "lon": lo,
            "wind_kt": storm["wind_kt"][i],
            "date_before": d_before, "date_after": d_after,
            "tchp_before": float(b), "tchp_after": float(a), "change": float(a - b),
        })

    if not rows:
        return {"points": [], "n_points": 0, "skipped": skipped,
                "verdict": "no track point could be evaluated",
                "before_days": before_days, "after_days": after_days}

    ch = np.array([r["change"] for r in rows], dtype="float64")
    n_cool = int((ch < 0).sum())
    return {
        "points": rows, "n_points": len(rows), "skipped": skipped,
        "before_days": before_days, "after_days": after_days,
        "mean_change": float(ch.mean()), "median_change": float(np.median(ch)),
        "n_cooled": n_cool, "fraction_cooled": n_cool / len(rows),
        "largest_cooling": float(ch.min()), "largest_warming": float(ch.max()),
        # A verdict, not a number, so a caller cannot render "-0.2" as a wake. The threshold is
        # deliberately explicit: a wake is a majority of points cooling AND a mean that is not a
        # rounding error against the 10-150 kJ/cm2 range TCHP spans in this basin.
        "verdict": ("cold wake resolved" if (n_cool / len(rows) >= 0.7 and ch.mean() <= -1.0)
                    else "no clear cold wake in this reconstruction"),
    }


def naive_wake(storm: dict, tchp_by_date: dict, before: str, after: str, *,
               stride: int = 1, lat=None, lon=None) -> dict:
    """The SAME measurement against one fixed pair of dates, for comparison.

    Kept because the contrast is the point: this is what a reader would compute by default, and on
    SHAKHTI it returns a null result from data that clearly contains a wake. A page that showed
    only the passage-relative number would be asking to be trusted; showing both shows the work.
    """
    lat_g = np.asarray(base.LAT if lat is None else lat, dtype="float64")
    lon_g = np.asarray(base.LON if lon is None else lon, dtype="float64")
    if before not in tchp_by_date or after not in tchp_by_date:
        return {"points": [], "n_points": 0, "before": before, "after": after,
                "verdict": "the two fixed dates were not reconstructed"}

    rows = []
    for i in range(0, len(storm["time"]), max(1, int(stride))):
        la, lo = float(storm["lat"][i]), float(storm["lon"][i])
        b = bilinear_at(tchp_by_date[before], la, lo, lat_g, lon_g)
        a = bilinear_at(tchp_by_date[after], la, lo, lat_g, lon_g)
        if np.isfinite(a) and np.isfinite(b):
            rows.append({"index": i, "lat": la, "lon": lo, "change": float(a - b)})
    if not rows:
        return {"points": [], "n_points": 0, "before": before, "after": after,
                "verdict": "no track point could be evaluated"}
    ch = np.array([r["change"] for r in rows], dtype="float64")
    n_cool = int((ch < 0).sum())
    return {"points": rows, "n_points": len(rows), "before": before, "after": after,
            "mean_change": float(ch.mean()), "n_cooled": n_cool,
            "fraction_cooled": n_cool / len(rows)}
