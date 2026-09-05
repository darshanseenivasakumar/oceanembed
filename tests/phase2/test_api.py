"""The API's decisions, tested without HTTP and without the model. Owner: Unit A (Arjhun).

`service.py` imports no web framework and returns `(status, payload)`, so everything that matters --
what is refused, what is served, what the errors say -- is testable as plain function calls. The HTTP
layer is covered separately in test_api_http.py.

A fake predictor throughout: these must run on a machine with no checkpoint and no 485 MB bundle,
because a test that only runs on one laptop is a test nobody runs.
"""
from __future__ import annotations

import numpy as np
import pytest

from phase2.api import service

FIRST, LAST = "2025-06-01", "2026-06-23"


class _FakePredictor:
    """Shaped like TSCastPredictor where the service touches it, and nowhere else."""

    def __init__(self, first=FIRST, last=LAST):
        n = int((np.datetime64(last, "D") - np.datetime64(first, "D")) / np.timedelta64(1, "D")) + 1
        self.data = {"times": np.arange(np.datetime64(first, "D"),
                                        np.datetime64(first, "D") + np.timedelta64(n, "D")),
                     "input_source": "satellite"}
        self.meta = {"bundle": "data/processed/daily_sat/v001", "encoder": "cnn3d", "T_SEQ": 11}
        self.checkpoint_path = None
        self.stage = 1
        self.calls = []

    def reconstruct(self, lat, lon, date):
        self.calls.append((lat, lon, date))
        return {"depths_m": [0, 5], "temperature": [29.5, float("nan")], "provenance": {}}


# --------------------------------------------------------------------------- refusal


@pytest.mark.parametrize("bad", ["1850-01-01", "2019-07-15", "2030-01-01", "2026-06-24"])
def test_a_date_outside_the_bundle_is_refused(bad):
    """`_time()` is argmin with no bound: out-of-range returns the nearest day and a complete,
    plausible field. The whole point of the API layer is that this cannot happen silently."""
    ok, detail = service.date_within_bundle(_FakePredictor(), bad)
    assert not ok
    assert detail["error"] == "date_out_of_range"


def test_the_refusal_names_the_valid_range():
    """An error that does not say what IS valid cannot be acted on."""
    _, detail = service.date_within_bundle(_FakePredictor(), "1850-01-01")
    assert detail["first_date"] == FIRST
    assert detail["last_date"] == LAST
    assert "1850-01-01" in str(detail["requested"])


def test_a_malformed_date_is_refused_and_still_names_the_range():
    ok, detail = service.date_within_bundle(_FakePredictor(), "not-a-date")
    assert not ok and detail["error"] == "bad_date"
    assert detail["first_date"] == FIRST and detail["last_date"] == LAST


@pytest.mark.parametrize("good", [FIRST, LAST, "2026-01-15"])
def test_a_date_inside_the_bundle_is_accepted(good):
    ok, _ = service.date_within_bundle(_FakePredictor(), good)
    assert ok


def test_profile_refuses_with_422_and_never_reaches_the_model():
    p = _FakePredictor()
    status, payload = service.profile(p, 15.0, 68.0, "1850-01-01")
    assert status == 422
    assert p.calls == [], "the model was called for a date that should have been refused"


def test_profile_serves_an_in_bundle_date():
    p = _FakePredictor()
    status, payload = service.profile(p, 15.0, 68.0, "2026-05-15")
    assert status == 200 and p.calls == [(15.0, 68.0, "2026-05-15")]
    assert payload["temperature"][1] is None, "NaN must serialise as null, not as a NaN token"


# --------------------------------------------------------------------------- forecast != refusal


def test_a_date_past_last_truth_is_still_INSIDE_the_bundle():
    """Output-schema §4: past LAST_GLORYS a prediction is SERVED as a forecast with no accuracy
    claim. That is a different concept from out-of-bundle, and collapsing the two would either
    refuse legitimate forecasts or serve nonsense. This pins them apart.
    """
    from phase2.tscast_nio.inference import LAST_GLORYS

    p = _FakePredictor()
    past_truth = str(np.datetime64(str(LAST_GLORYS), "D") + np.timedelta64(1, "D"))
    if np.datetime64(past_truth) <= np.datetime64(LAST):
        ok, _ = service.date_within_bundle(p, past_truth)
        assert ok, "a post-truth date inside the bundle must be served, not refused"

    cov = service.coverage(p)[1]
    assert cov["last_date_with_truth"] == str(LAST_GLORYS)
    assert cov["last_date"] == LAST
    assert "forecast" in cov["note"]


# --------------------------------------------------------------------------- the cheap calls


def test_health_reports_provenance_without_running_inference():
    p = _FakePredictor()
    status, h = service.health(p)
    assert status == 200
    for key in ("checkpoint_sha256", "code_commit", "bundle", "input_source", "first_date"):
        assert key in h
    assert p.calls == [], "health must not run the model"


def test_coverage_reports_the_real_window_and_cadence():
    status, c = service.coverage(_FakePredictor())
    assert status == 200
    assert (c["first_date"], c["last_date"]) == (FIRST, LAST)
    assert c["cadence_days"] == 1.0, "the daily bundle must not read as monthly"


# --------------------------------------------------------------------------- json safety


def test_nan_becomes_null_not_a_nan_token():
    """Python emits a bare NaN that json.load accepts and JSON.parse rejects -- so a browser would
    fail on exactly the records containing a below-seafloor depth."""
    import json

    out = service._json_safe({"a": float("nan"), "b": [1.0, float("inf")], "c": np.float32("nan")})
    assert out == {"a": None, "b": [1.0, None], "c": None}
    json.dumps(out, allow_nan=False)          # raises if a NaN survived
