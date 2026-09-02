"""Live Argo overlay — "don't trust us, trust the float".

A DERIVED product on top of the frozen TS-Cast-NIO model. Given a point, it puts the model's
predicted profile (with its calibrated +/-2 sigma band) next to a REAL, independent Argo float from
near that location and date, and reports the per-depth error live. Nothing here retrains or touches
the checkpoint, the bundle, dataset.py, inference.py, or the split.

WHY IT REUSES, RATHER THAN REBUILDS
-----------------------------------
Two things already exist and are trusted, so this file calls them instead of growing a second copy:

  * The prediction comes from `TSCastPredictor.reconstruct` — the SAME frozen inference path the
    dashboard uses. `predict_at` is a thin wrapper; there is no second model-load path to drift.
  * The float match comes from F1's `CollocationEngine` — the validated 962-profile held-out table,
    matched offline (no network). `reconstruct` already attaches the nearest float as
    `record["argo_check"]`; the only thing this module adds on top is a top-k picker so a user can
    choose a different nearby float, and a compact RMSE/bias summary.

A CONVENIENCE, NAMED
--------------------
The offline Argo table is pre-binned to the project's 15 standard depths, so the float profile and
the model prediction already share one depth axis — there is no raw-pressure interpolation to do,
and a comparison is simply "where both have a value". `find_nearest_profiles` reads that table via
`engine._argo_table()`; that is a leading-underscore accessor, used deliberately so this whole
feature stays new-files-only and can be dropped as a unit. If the feature graduates permanently,
promote `_argo_table` to a public method and delete this note.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from phase2.tscast_nio import config

# Reuse F1's exact great-circle distance so ranking here can never disagree with the engine's.
from phase2.data.collocation import _haversine_km

DEPTHS = np.asarray(config.DEPTHS, dtype="float64")
DEFAULT_SEARCH_DAYS = 5.0


# --------------------------------------------------------------------------- pure helpers
# Everything in this block takes plain arrays/lists — no predictor, no engine, no network — so it
# unit-tests on a machine without the satellite bundle.

@dataclass
class Match:
    """One candidate float profile, already binned to the 15 standard depths."""
    latitude: float
    longitude: float
    datetime: str
    temperature_profile: list          # length-15, None where the float has no level
    spatial_offset_km: float
    temporal_offset_days: float         # signed: float date minus requested date
    n_levels: int

    def as_dict(self) -> dict:
        return asdict(self)


def rank_matches(matches: list[Match], k: int = 5) -> list[Match]:
    """Nearest-first, distance dominating with |time| as a deterministic tiebreak.

    Not a weighted distance+time score: there is no defensible kilometres-per-day exchange rate, so
    a lexicographic (distance, |days|) order is used instead of inventing one. This reproduces the
    engine's own "nearest in space within the time window" choice for the top result, and only adds
    a deterministic ordering for the rest. Ties beyond that fall back to (lat, lon, date) so the
    order is stable across runs.
    """
    return sorted(
        matches,
        key=lambda m: (round(float(m.spatial_offset_km), 6),
                       abs(float(m.temporal_offset_days)),
                       float(m.latitude), float(m.longitude), str(m.datetime)),
    )[:k]


def compare(depths, mean15, float_profile15) -> dict:
    """Per-depth error, RMSE and bias — ONLY where the float actually has a value.

    Never extrapolates past the float's deepest sampled level, and never invents a comparison where
    the float has no data: a depth is scored only when BOTH the prediction and the float are finite
    there. `per_depth` is length-15 and aligned to `depths`, with None off the overlap.
    """
    d = np.asarray(depths, dtype="float64")
    p = np.asarray([np.nan if v is None else v for v in mean15], dtype="float64")
    f = np.asarray([np.nan if v is None else v for v in float_profile15], dtype="float64")
    if not (d.shape == p.shape == f.shape):
        raise ValueError(f"depths {d.shape}, prediction {p.shape} and float {f.shape} must all be "
                         f"the {config.N_DEPTHS} standard depths")

    overlap = np.isfinite(p) & np.isfinite(f)
    err = np.where(overlap, p - f, np.nan)
    n = int(overlap.sum())
    rmse = float(np.sqrt(np.nanmean(err[overlap] ** 2))) if n else float("nan")
    bias = float(np.nanmean(err[overlap])) if n else float("nan")
    depth_range = (float(d[overlap].min()), float(d[overlap].max())) if n else None
    return {
        "per_depth_error": [None if not overlap[k] else round(float(err[k]), 4)
                            for k in range(len(d))],
        "rmse": None if not n else round(rmse, 4),
        "bias": None if not n else round(bias, 4),
        "n_levels_compared": n,
        "overlap_depth_range_m": depth_range,
    }


def two_sigma_band(mean15, sigma15) -> dict:
    """The +/-2 sigma envelope the plot shades. sigma is the CALIBRATED sigma_t from the record."""
    p = np.asarray([np.nan if v is None else v for v in mean15], dtype="float64")
    s = np.asarray([np.nan if v is None else v for v in sigma15], dtype="float64")
    lo = p - 2.0 * s
    hi = p + 2.0 * s
    finite = np.isfinite(p) & np.isfinite(s)
    to_list = lambda a: [None if not finite[k] else round(float(a[k]), 4) for k in range(len(a))]
    return {"lo": to_list(lo), "hi": to_list(hi)}


# --------------------------------------------------------------------------- float lookup (offline)

def _engine(engine=None):
    if engine is not None:
        return engine
    from phase2.data.collocation import CollocationEngine
    # The daily-period table is the one that covers the model's 2025-26 prediction window; the
    # legacy `argo_test` table is 2022 only and would match nothing here.
    return CollocationEngine(argo_table="argo_daily_period")


def find_nearest_profiles(lat: float, lon: float, when, k: int = 5,
                          search_deg: float = 1.0, search_days: float = DEFAULT_SEARCH_DAYS,
                          engine=None) -> list[Match]:
    """Top-k independent floats near (lat, lon, when), nearest first. Offline, no network.

    Ranking and profile-binning mirror F1's `_match_argo` exactly (same table, same haversine, same
    depth_idx binning); this only keeps k candidates instead of one so the UI can offer a picker.
    Returns [] when nothing good is in the window — the caller must show that honestly, never a
    fabricated profile.
    """
    import pandas as pd

    eng = _engine(engine)
    df = eng._argo_table()
    if df is None or len(df) == 0:
        return []
    when = pd.Timestamp(when)
    lo_d, hi_d = when - pd.Timedelta(days=search_days), when + pd.Timedelta(days=search_days)
    sub = df[(df["date"] >= lo_d) & (df["date"] <= hi_d)]
    sub = sub[(sub["lat"].sub(lat).abs() < search_deg) & (sub["lon"].sub(lon).abs() < search_deg)]
    if sub.empty:
        return []

    matches: list[Match] = []
    for (la, ln, dt), grp in sub.groupby(["lat", "lon", "date"]):
        prof: list = [None] * config.N_DEPTHS
        for kk, t in zip(grp["depth_idx"].to_numpy(), grp["temp"].to_numpy()):
            if 0 <= int(kk) < config.N_DEPTHS and np.isfinite(t):
                prof[int(kk)] = round(float(t), 4)
        n_levels = sum(p is not None for p in prof)
        if n_levels == 0:
            continue
        dt_ts = pd.Timestamp(dt)
        matches.append(Match(
            latitude=float(la), longitude=float(ln), datetime=str(dt_ts.date()),
            temperature_profile=prof,
            spatial_offset_km=round(_haversine_km(lat, lon, float(la), float(ln)), 3),
            temporal_offset_days=float((dt_ts.normalize() - when.normalize()).days),
            n_levels=int(n_levels)))
    return rank_matches(matches, k=k)


# --------------------------------------------------------------------------- prediction (frozen path)

def predict_at(lat: float, lon: float, date, predictor=None) -> dict:
    """Run the FROZEN model at one point and return everything the overlay needs.

    `predictor` is injectable so tests pass a fake and never load a checkpoint or bundle. In
    production it defaults to `TSCastPredictor()`, the same object the dashboard uses.
    """
    if predictor is None:
        from phase2.tscast_nio.inference import TSCastPredictor
        predictor = TSCastPredictor()
    rec = predictor.reconstruct(lat, lon, date)
    band = two_sigma_band(rec["temperature"], rec["sigma_t"])
    return {
        "depths_m": rec["depths_m"],
        "mean": rec["temperature"],
        "sigma_t": rec["sigma_t"],
        "band_2sigma": band,
        "calibration": rec.get("calibration"),
        "argo_check": rec.get("argo_check"),      # nearest float, already attached by reconstruct
        "forecast": rec.get("forecast", False),
        "provenance": rec.get("provenance"),
    }


def overlay(lat: float, lon: float, date, predictor=None, engine=None, k: int = 5) -> dict:
    """The whole product for one click: frozen prediction + top-k floats + a comparison to each.

    The prediction is computed once; each candidate float is compared against it on the shared 15
    standard depths. Returns the prediction, the ranked matches, and the per-match comparison, plus
    an explicit `has_float` so the UI can render an honest empty state.
    """
    pred = predict_at(lat, lon, date, predictor=predictor)
    matches = find_nearest_profiles(lat, lon, date, k=k, engine=engine)
    comparisons = [compare(pred["depths_m"], pred["mean"], m.temperature_profile) for m in matches]
    return {
        "prediction": pred,
        "matches": [m.as_dict() for m in matches],
        "comparisons": comparisons,
        "has_float": bool(matches),
    }
