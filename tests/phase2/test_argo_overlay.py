"""Tests for the Live Argo overlay (derived product on the frozen model).

Everything here runs WITHOUT the satellite bundle and WITHOUT the network: the pure functions take
plain arrays, the predictor is a hand-made fake, and the Argo table is a synthetic DataFrame. That
is deliberate — the machine these are written on does not carry data/processed/daily_sat/v001, so a
test that needed it would be a test that never ran here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oceanembed import config
from phase2.validation import argo_overlay as ao
from phase2.validation.argo_overlay import Match

D = config.DEPTHS
NZ = config.N_DEPTHS


# --------------------------------------------------------------------------- rank_matches

def _m(km, days, lat=15.0, lon=65.0, dt="2026-05-15"):
    return Match(latitude=lat, longitude=lon, datetime=dt, temperature_profile=[20.0] * NZ,
                 spatial_offset_km=km, temporal_offset_days=days, n_levels=NZ)


def test_rank_matches_nearest_first_by_distance():
    ranked = ao.rank_matches([_m(50, 0), _m(10, 4), _m(30, 1)])
    assert [round(m.spatial_offset_km) for m in ranked] == [10, 30, 50]


def test_rank_matches_time_breaks_distance_ties_deterministically():
    # identical distance -> smaller |days| wins; and the order is stable across runs
    ranked = ao.rank_matches([_m(10, 3, dt="2026-05-18"), _m(10, -1, dt="2026-05-14")])
    assert [m.temporal_offset_days for m in ranked] == [-1, 3]
    # re-ranking the reversed input gives the same order (determinism)
    again = ao.rank_matches(list(reversed(ranked)))
    assert [m.datetime for m in again] == [m.datetime for m in ranked]


def test_rank_matches_truncates_to_k():
    assert len(ao.rank_matches([_m(i, 0) for i in range(10)], k=3)) == 3


# --------------------------------------------------------------------------- compare

def test_compare_rmse_and_bias_on_a_hand_made_pair():
    mean = [20.0] * NZ
    flt = [21.0] * NZ                      # prediction is 1 degC colder everywhere
    out = ao.compare(D, mean, flt)
    assert out["n_levels_compared"] == NZ
    assert out["rmse"] == 1.0
    assert out["bias"] == -1.0             # pred - float
    assert out["overlap_depth_range_m"] == (0.0, 1000.0)


def test_compare_only_scores_where_the_float_has_data_no_extrapolation():
    mean = [20.0] * NZ
    # float stops at index 10 (200 m); deeper levels are None, as a shallow float would be
    flt = [21.0] * 11 + [None] * (NZ - 11)
    out = ao.compare(D, mean, flt)
    assert out["n_levels_compared"] == 11
    # nothing is scored past the float's deepest sampled level
    assert out["per_depth_error"][11:] == [None] * (NZ - 11)
    assert out["overlap_depth_range_m"] == (0.0, float(D[10]))


def test_compare_skips_depths_where_the_prediction_is_none():
    mean = [None] * 5 + [20.0] * (NZ - 5)   # e.g. below-seafloor cells masked out
    flt = [21.0] * NZ
    out = ao.compare(D, mean, flt)
    assert out["n_levels_compared"] == NZ - 5
    assert out["per_depth_error"][:5] == [None] * 5


def test_compare_no_overlap_returns_nan_summary_not_zero():
    out = ao.compare(D, [None] * NZ, [21.0] * NZ)
    assert out["n_levels_compared"] == 0
    assert out["rmse"] is None and out["bias"] is None
    assert out["overlap_depth_range_m"] is None


# --------------------------------------------------------------------------- two_sigma_band

def test_two_sigma_band_is_mean_plus_minus_two_sigma():
    band = ao.two_sigma_band([20.0] * NZ, [0.5] * NZ)
    assert band["lo"][0] == 19.0 and band["hi"][0] == 21.0


def test_two_sigma_band_is_none_where_prediction_is_none():
    band = ao.two_sigma_band([None] + [20.0] * (NZ - 1), [0.5] * NZ)
    assert band["lo"][0] is None and band["hi"][0] is None


# --------------------------------------------------------------------------- predict_at (mocked)

class _FakePredictor:
    """Stands in for TSCastPredictor: records the call, returns a minimal reconstruct() record."""
    def __init__(self):
        self.calls = []

    def reconstruct(self, lat, lon, date, argo_check=None):
        self.calls.append((lat, lon, str(date)))
        return {
            "depths_m": list(D),
            "temperature": [20.0] * NZ,
            "sigma_t": [0.5] * NZ,
            "calibration": {"applied": True},
            "argo_check": {"profile_id": "x", "distance_km": 13.0, "days_offset": 2},
            "forecast": False,
            "provenance": {"input_source": "satellite"},
        }


def test_predict_at_goes_through_the_injected_predictor_and_builds_the_band():
    fake = _FakePredictor()
    out = ao.predict_at(15.0, 68.0, "2026-05-15", predictor=fake)
    assert fake.calls == [(15.0, 68.0, "2026-05-15")]      # frozen path was called, once
    assert out["band_2sigma"]["lo"][0] == 19.0 and out["band_2sigma"]["hi"][0] == 21.0
    assert out["argo_check"]["distance_km"] == 13.0        # nearest float carried through
    assert out["provenance"]["input_source"] == "satellite"


# --------------------------------------------------------------------------- find_nearest_profiles (fake table)

class _FakeEngine:
    """Exposes _argo_table() like CollocationEngine, backed by a synthetic frame."""
    def __init__(self, df):
        self._df = df

    def _argo_table(self):
        return self._df


def _rows(lat, lon, date, temps):
    return pd.DataFrame({
        "date": [pd.Timestamp(date)] * len(temps),
        "lat": [lat] * len(temps), "lon": [lon] * len(temps),
        "depth_idx": list(range(len(temps))), "temp": temps,
    })


def test_find_nearest_profiles_ranks_and_bins_like_the_engine():
    near = _rows(15.05, 65.05, "2026-05-15", [20.0] * NZ)    # ~7 km away
    far = _rows(15.8, 65.8, "2026-05-15", [19.0] * NZ)       # ~100+ km away
    eng = _FakeEngine(pd.concat([far, near], ignore_index=True))
    got = ao.find_nearest_profiles(15.0, 65.0, "2026-05-15", k=5, engine=eng)
    assert len(got) == 2
    assert got[0].spatial_offset_km < got[1].spatial_offset_km   # nearest first
    assert got[0].n_levels == NZ
    assert got[0].temperature_profile[0] == 20.0


def test_find_nearest_profiles_empty_window_returns_empty_not_fake():
    df = _rows(15.0, 65.0, "2026-01-01", [20.0] * NZ)            # months from the query date
    got = ao.find_nearest_profiles(15.0, 65.0, "2026-05-15", engine=_FakeEngine(df))
    assert got == []


def test_find_nearest_profiles_drops_profiles_with_no_good_levels():
    empty = _rows(15.05, 65.05, "2026-05-15", [np.nan] * NZ)     # all levels missing
    got = ao.find_nearest_profiles(15.0, 65.0, "2026-05-15", engine=_FakeEngine(empty))
    assert got == []
