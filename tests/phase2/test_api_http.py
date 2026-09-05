"""The HTTP layer, over a fake predictor. Owner: Unit A (Arjhun).

`build_app(predictor_factory=...)` exists for exactly this: the routes are exercised in seconds on
any machine, with no checkpoint and no 485 MB bundle. A route test that needs the real model is a
route test that only runs on one laptop.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient          # noqa: E402

from phase2.api.app import build_app              # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIRST, LAST = "2025-06-01", "2026-06-23"


class _FakePredictor:
    def __init__(self):
        n = int((np.datetime64(LAST, "D") - np.datetime64(FIRST, "D")) / np.timedelta64(1, "D")) + 1
        self.data = {"times": np.arange(np.datetime64(FIRST, "D"),
                                        np.datetime64(FIRST, "D") + np.timedelta64(n, "D")),
                     "input_source": "satellite"}
        self.meta = {"bundle": "data/processed/daily_sat/v001", "encoder": "cnn3d", "T_SEQ": 11}
        self.checkpoint_path = None
        self.stage = 1

    def reconstruct(self, lat, lon, date):
        return {"depths_m": [0, 5], "temperature": [29.5, float("nan")],
                "provenance": {"input_date": date}}


@pytest.fixture(scope="module")
def client():
    return TestClient(build_app(predictor_factory=_FakePredictor))


def test_health_answers_without_touching_the_model(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["input_source"] == "satellite"
    for key in ("checkpoint_sha256", "code_commit", "bundle"):
        assert key in body


def test_coverage_states_what_can_be_answered(client):
    body = client.get("/coverage").json()
    assert body["first_date"] == FIRST and body["last_date"] == LAST
    assert body["cadence_days"] == 1.0
    assert "last_date_with_truth" in body


def test_an_out_of_bundle_date_is_422_not_200(client):
    """The single most important behaviour here. A 200 with the nearest day would be a wrong answer
    that looks exactly like a right one."""
    r = client.get("/profile", params={"lat": 15, "lon": 68, "date": "1850-01-01"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "date_out_of_range"
    assert body["first_date"] == FIRST and body["last_date"] == LAST


def test_the_field_endpoint_refuses_the_same_way(client):
    r = client.get("/field.nc", params={"date": "2030-01-01"})
    assert r.status_code == 422
    assert r.json()["last_date"] == LAST


def test_an_in_bundle_profile_is_served_with_nulls_not_nans(client):
    r = client.get("/profile", params={"lat": 15, "lon": 68, "date": "2026-05-15"})
    assert r.status_code == 200
    assert r.json()["temperature"] == [29.5, None]
    assert "NaN" not in r.text, "a bare NaN token would break JSON.parse in a browser"


def test_handlers_are_sync_so_they_cannot_block_the_event_loop():
    """A source guard, deliberately.

    An `async def` handler calling predict_field blocks the whole event loop for ~32 seconds
    (measured, artifacts/export_timing.json). It looks correct until two people load the page, which
    is precisely when a demo is being watched.

    Parsed with `ast`, not grepped: both modules DOCUMENT the rule in prose, and a text search finds
    the warning as readily as a violation. The guard has to look at code.
    """
    import ast

    for rel in ("src/phase2/api/app.py", "src/phase2/api/service.py"):
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        bad = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
        assert not bad, f"{rel} defines async handler(s): {bad}"


def test_every_predictor_call_is_inside_the_lock():
    """`predict_field` borrows `ds.index` and `reconstruct` overwrites it without restoring. Two
    concurrent requests corrupt each other and return plausible wrong answers rather than raising.
    """
    src = open(os.path.join(ROOT, "src/phase2/api/service.py"), encoding="utf-8").read()
    body = src.split('"""', 2)[-1]                    # past the module docstring
    n_calls = body.count("predictor.reconstruct(") + body.count("predict_field(predictor")
    assert n_calls >= 2, "expected the two predictor entry points"
    assert body.count("with _LOCK:") >= n_calls, "a predictor call is not inside the lock"
