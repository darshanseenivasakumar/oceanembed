"""Grid-wide marine-heatwave flags and a model-vs-truth detection comparison.

OWNER: Unit A (Arjhun / MHW feature). PHASE-2 ONLY. Imports config; modifies nothing.

WHAT THIS ADDS OVER events.heatwave
`events.heatwave.detect_events` works on ONE cell's daily series. This applies it across the whole
grid and, crucially, answers the question the project actually cares about:

    Can the SATELLITE-DRIVEN model see the same subsurface heatwaves the GLORYS truth shows?

WHY THE COMPARISON IS ROBUST TO THE BASELINE, WHERE A RAW COUNT IS NOT
A heatwave count depends on the baseline: measured against a baseline a few years older than the
detection window, ocean warming alone pushes almost every cell "above normal", inflating counts
(measured: a 2019-2022 pilot baseline flags ~40% of the basin in 2025-2026 -- the trend, not
events). But the model and the truth are scored against the SAME threshold, so that bias is common
to both and CANCELS in the contingency table below. "Does the model agree with the truth about where
and when a heatwave is?" stays valid even while the absolute count is inflated. So this comparison is
the honest headline; the raw per-cell count is a supporting map with its baseline stated.

CONTINGENCY SKILL (standard detection verification, per depth)
    hit  = model says MHW and truth says MHW        miss = truth says MHW, model does not
    FA   = model says MHW, truth does not (false alarm)   CN = neither
    POD  = hits / (hits + misses)          probability of detection (1 = catches every real event)
    FAR  = FA   / (hits + FA)              false-alarm ratio        (0 = never cries wolf)
    CSI  = hits / (hits + misses + FA)     critical success index   (overall, penalises both errors)
    bias = (hits + FA) / (hits + misses)   frequency bias           (>1 over-flags, <1 under-flags)
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

from ..events import heatwave

__all__ = ["event_mask", "mhw_day_flags_grid", "compare_detection"]


def event_mask(temp, clim, thresh,
               min_duration: int = heatwave.MIN_DURATION_DAYS,
               max_gap: int = heatwave.MAX_GAP_DAYS) -> np.ndarray:
    """Boolean series: True on each day that falls INSIDE a detected heatwave event.

    Wraps `detect_events` and paints each event's [start, end] span True, so downstream code can ask
    "is this cell in a heatwave on day t?" without re-deriving events. Pure and testable.
    """
    n = np.asarray(temp).shape[0]
    mask = np.zeros(n, dtype=bool)
    for e in heatwave.detect_events(temp, clim, thresh, min_duration, max_gap):
        mask[e["start"]:e["end"] + 1] = True
    return mask


def mhw_day_flags_grid(temp_stack, clim_series, thresh_series, land_mask,
                       min_duration: int = heatwave.MIN_DURATION_DAYS,
                       max_gap: int = heatwave.MAX_GAP_DAYS) -> np.ndarray:
    """Apply `event_mask` at every ocean cell of ONE depth slice.

    temp_stack / clim_series / thresh_series : (N, n_lat, n_lon), aligned day-for-day.
    land_mask : (n_lat, n_lon) bool, True over land -- those cells stay all-False (never a heatwave).
    Returns (N, n_lat, n_lon) bool: was this cell inside a heatwave on this day. Loops cells because
    the persistence rule is inherently sequential in time; ~24k ocean cells run in a few seconds.
    """
    temp = np.asarray(temp_stack, dtype="float64")
    clim = np.asarray(clim_series, dtype="float64")
    thr = np.asarray(thresh_series, dtype="float64")
    land = np.asarray(land_mask, dtype=bool)
    if not (temp.shape == clim.shape == thr.shape) or temp.ndim != 3:
        raise ValueError(f"temp/clim/thresh must be 3-D (N,lat,lon) and identical; got "
                         f"{temp.shape}, {clim.shape}, {thr.shape}")
    n, nlat, nlon = temp.shape
    out = np.zeros((n, nlat, nlon), dtype=bool)
    for i in range(nlat):
        for j in range(nlon):
            if land[i, j]:
                continue
            out[:, i, j] = event_mask(temp[:, i, j], clim[:, i, j], thr[:, i, j],
                                      min_duration, max_gap)
    return out


def compare_detection(model_flags, truth_flags, valid=None) -> dict:
    """Contingency-table skill of model heatwave flags against truth flags (same shape).

    valid : optional boolean array broadcastable to the flags -- only cells/days where valid is True
            are counted (e.g. a (n_lat, n_lon) ocean mask, or a (N,lat,lon) below-seafloor mask).
    Returns hits/misses/false_alarms/correct_negatives plus POD, FAR, CSI and frequency bias. A rate
    whose denominator is zero is returned as None (never a fabricated 0 or 1).
    """
    m = np.asarray(model_flags, dtype=bool)
    t = np.asarray(truth_flags, dtype=bool)
    if m.shape != t.shape:
        raise ValueError(f"model {m.shape} and truth {t.shape} flags must match")
    if valid is not None:
        keep = np.broadcast_to(np.asarray(valid, dtype=bool), m.shape)
        m, t = m[keep], t[keep]
    hits = int(np.sum(m & t))
    misses = int(np.sum(~m & t))
    fa = int(np.sum(m & ~t))
    cn = int(np.sum(~m & ~t))

    def _ratio(num, den):
        return float(num) / float(den) if den > 0 else None

    return {
        "hits": hits, "misses": misses, "false_alarms": fa, "correct_negatives": cn,
        "pod": _ratio(hits, hits + misses),
        "far": _ratio(fa, hits + fa),
        "csi": _ratio(hits, hits + misses + fa),
        "frequency_bias": _ratio(hits + fa, hits + misses),
        "n_truth_mhw_days": hits + misses,
        "n_model_mhw_days": hits + fa,
    }
