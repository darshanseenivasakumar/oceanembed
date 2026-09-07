"""Marine heatwave DETECTION on a daily temperature series, one location+depth at a time.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config; modifies nothing.

WHY THIS FILE FINALLY EXISTS
`PHASE2_ARCHITECTURE_AUDIT.md` named a planned `events/heatwave.py` that was never built, and F7
(subsurface heatwave) was closed as BLOCKED because the Phase-1 event data was MONTHLY -- and a
marine heatwave is defined by DAILY persistence ("5 consecutive days"), which monthly fields cannot
resolve. With the 388 consecutive daily fields now on disk (2025-06-01..2026-06-23) plus a
multi-year daily baseline, the persistence test is finally mechanically possible, so the feature is
unblocked and this is its detection core.

THE DEFINITION -- Hobday et al. (2016), Prog. Oceanogr. 141, 227-238
    A marine heatwave is a period when temperature exceeds a seasonally-varying 90th-percentile
    THRESHOLD for at least 5 consecutive days; two events separated by a gap of 2 days or fewer are
    treated as one event (the gap days are folded into the event).

    threshold(doy) and climatology(doy) are day-of-year curves built elsewhere from a multi-year
    baseline (see scripts/phase2/build_mhw_baseline.py). This module does NOT build them -- it takes
    them as inputs, so the detection logic is a pure, testable function of three aligned series.

INTENSITY IS MEASURED FROM THE CLIMATOLOGY, NOT THE THRESHOLD
    intensity(t) = temperature(t) - climatology(doy(t))            [degC]
The threshold decides IF a day is in a heatwave; the climatology mean is the baseline the intensity
is measured ABOVE. Hobday's categories (2018) are multiples of the local (threshold - climatology)
gap: 1-2x Moderate, 2-3x Strong, 3-4x Severe, >=4x Extreme.

NaN IS NEVER A HEATWAVE
A NaN day (land, below seafloor, missing) is treated as "not exceeding" -- it can neither start nor
extend an event, and it breaks a run. So a masked cell yields zero events, never a spurious one.

WHY DETECTION, NOT PREDICTION
This flags heatwaves that ARE PRESENT in a temperature series -- whether that series is the GLORYS
truth or the model's reconstruction. It forecasts nothing. Feeding it the model's field and the
GLORYS field and comparing the two event sets is how we measure whether a satellite-driven model can
SEE a subsurface heatwave; that comparison lives in the validation layer, not here.
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

__all__ = [
    "MIN_DURATION_DAYS", "MAX_GAP_DAYS", "CATEGORY_NAMES",
    "exceedances", "detect_events", "category_at", "summarise",
]

#: Hobday et al. (2016): an event is >= 5 consecutive days above the threshold.
MIN_DURATION_DAYS = 5

#: Hobday et al. (2016): two events <= 2 days apart merge into one (gap days folded in).
MAX_GAP_DAYS = 2

#: Hobday et al. (2018) intensity categories, indexed by the integer multiple of
#: (threshold - climatology) reached at the event's peak. Index 1..4; 0 is unused.
CATEGORY_NAMES = {1: "Moderate", 2: "Strong", 3: "Severe", 4: "Extreme"}


# ------------------------------------------------------------------ exceedance

def exceedances(temp, thresh) -> np.ndarray:
    """Boolean series: True where temperature is strictly above the threshold and both are finite.

    NaN-strict: a NaN in either series is False (not a heatwave day), so land / below-seafloor /
    missing days can never open or extend an event. Pure; no persistence applied here.
    """
    t = np.asarray(temp, dtype="float64")
    x = np.asarray(thresh, dtype="float64")
    if t.shape != x.shape:
        raise ValueError(f"temp {t.shape} and thresh {x.shape} must be the same shape")
    with np.errstate(invalid="ignore"):
        return np.isfinite(t) & np.isfinite(x) & (t > x)


def _runs(mask) -> list[tuple[int, int]]:
    """Contiguous runs of True in a 1-D boolean array, as (start, end_inclusive) index pairs."""
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 1:
        raise ValueError(f"mask must be 1-D, got shape {m.shape}")
    if not m.any():
        return []
    # edges where the boolean flips, padded so runs touching either end are closed
    padded = np.concatenate(([False], m, [False]))
    diff = np.diff(padded.astype("int8"))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


# ------------------------------------------------------------------ categories

def category_at(temp_peak, clim_peak, thresh_peak) -> tuple[int, str]:
    """Hobday-2018 category from the values at the event's most intense day.

    level = (temp - clim) / (thresh - clim); category = floor(level), capped at 4 (Extreme).
    The peak of a real event is always above the threshold, so level >= 1 (Moderate) there. If the
    local (thresh - clim) gap is non-positive (a degenerate baseline), the category is undefined and
    returned as (0, "Undefined") rather than dividing by zero.
    """
    gap = float(thresh_peak) - float(clim_peak)
    if not np.isfinite(gap) or gap <= 0.0:
        return 0, "Undefined"
    level = (float(temp_peak) - float(clim_peak)) / gap
    cat = int(np.clip(np.floor(level), 1, 4))
    return cat, CATEGORY_NAMES[cat]


# ------------------------------------------------------------------ detection

def detect_events(temp, clim, thresh,
                  min_duration: int = MIN_DURATION_DAYS,
                  max_gap: int = MAX_GAP_DAYS) -> list[dict]:
    """Detect marine-heatwave events in one aligned daily series.

    temp / clim / thresh : 1-D arrays of the same length, aligned day-for-day. `clim` and `thresh`
                           are the day-of-year climatology mean and 90th-percentile threshold already
                           mapped onto each calendar day of `temp` (so the caller handles day-of-year
                           lookup; this function is pure index arithmetic).

    Returns a list of event dicts, earliest first, each with integer day INDICES into the series:
        start, end            inclusive index bounds of the event (gaps folded in)
        duration_days         end - start + 1
        peak_index            index of maximum intensity
        mean_intensity_c      mean of (temp - clim) over the event span      [degC]
        max_intensity_c       max  of (temp - clim) over the event span      [degC]
        cumulative_intensity  sum  of (temp - clim) over the event span      [degC*days]
        category, category_name

    Algorithm (Hobday 2016), in order: (1) mark days above threshold; (2) keep runs of >= min_duration
    consecutive such days as candidate events; (3) merge two candidates whose gap is <= max_gap days,
    folding the gap days into the event. A sub-min_duration run that is not inside such a gap is
    discarded -- it is warm, but not a heatwave.
    """
    t = np.asarray(temp, dtype="float64")
    c = np.asarray(clim, dtype="float64")
    x = np.asarray(thresh, dtype="float64")
    if not (t.shape == c.shape == x.shape) or t.ndim != 1:
        raise ValueError(f"temp/clim/thresh must be 1-D and identical shape; "
                         f"got {t.shape}, {c.shape}, {x.shape}")
    if min_duration < 1 or max_gap < 0:
        raise ValueError(f"min_duration>=1 and max_gap>=0 required; got {min_duration}, {max_gap}")

    runs = _runs(exceedances(t, x))
    qualified = [(s, e) for s, e in runs if (e - s + 1) >= min_duration]

    merged: list[list[int]] = []
    for s, e in qualified:
        if merged and (s - merged[-1][1] - 1) <= max_gap:
            merged[-1][1] = e            # fold this event and the gap days into the previous one
        else:
            merged.append([s, e])

    events: list[dict] = []
    for s, e in merged:
        anom = t[s:e + 1] - c[s:e + 1]
        if not np.isfinite(anom).any():
            continue                      # an all-NaN span cannot be scored; drop it rather than fake it
        k = int(np.nanargmax(anom))
        peak = s + k
        cat, cat_name = category_at(t[peak], c[peak], x[peak])
        events.append({
            "start": int(s),
            "end": int(e),
            "duration_days": int(e - s + 1),
            "peak_index": peak,
            "mean_intensity_c": float(np.nanmean(anom)),
            "max_intensity_c": float(np.nanmax(anom)),
            "cumulative_intensity": float(np.nansum(anom)),
            "category": cat,
            "category_name": cat_name,
        })
    return events


def summarise(events: list[dict]) -> dict:
    """Roll a list of events up into the numbers a panel or a per-cell record needs.

    Returns counts, total heatwave days, the single strongest event's peak intensity and category,
    and the max category reached. An empty list returns an all-zero / None summary, never NaN dressed
    up as a value -- 'no heatwave here' is a real answer and must read as one.
    """
    if not events:
        return {"n_events": 0, "total_mhw_days": 0, "max_intensity_c": 0.0,
                "max_category": 0, "max_category_name": "None",
                "longest_duration_days": 0}
    max_cat = max(e["category"] for e in events)
    strongest = max(events, key=lambda e: e["max_intensity_c"])
    return {
        "n_events": len(events),
        "total_mhw_days": int(sum(e["duration_days"] for e in events)),
        "max_intensity_c": float(strongest["max_intensity_c"]),
        "max_category": int(max_cat),
        "max_category_name": CATEGORY_NAMES.get(max_cat, "Undefined"),
        "longest_duration_days": int(max(e["duration_days"] for e in events)),
    }
