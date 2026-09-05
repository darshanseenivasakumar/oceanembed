"""The shared field loader. Owner: Unit A (Arjhun).

A fake predictor throughout, so these run on a machine with no checkpoint and no 485 MB bundle --
a test that only runs on one laptop is a test nobody runs. The one thing that cannot be faked is
the lock, so that is tested with real threads.
"""
from __future__ import annotations

import ast
import os
import threading
import time

import numpy as np
import pytest

from phase2.tscast_nio import field_cache as FC

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIRST, LAST = "2025-06-01", "2026-06-23"


class _FakePredictor:
    """Shaped like TSCastPredictor where field_cache touches it, and nowhere else.

    Every entry point records (event, thread) so an overlap between two callers is visible.
    """

    def __init__(self, hold: float = 0.0):
        n = int((np.datetime64(LAST, "D") - np.datetime64(FIRST, "D")) / np.timedelta64(1, "D")) + 1
        self.data = {"times": np.arange(np.datetime64(FIRST, "D"),
                                        np.datetime64(FIRST, "D") + np.timedelta64(n, "D"))}
        self.meta = {"bundle": "data/processed/daily_sat/v001"}
        self.stage = 1
        self.hold = hold
        self.events: list[tuple[str, str]] = []
        self._elog = threading.Lock()

    def _mark(self, tag):
        with self._elog:
            self.events.append((tag, threading.current_thread().name))

    def reconstruct(self, lat, lon, date):
        self._mark("point:enter")
        time.sleep(self.hold)
        self._mark("point:exit")
        return {"depths_m": [0, 5], "temperature": [29.5, 28.0], "provenance": {}}


def _fake_field(predictor, date, device=None, **kw):
    predictor._mark("field:enter")
    time.sleep(predictor.hold)
    predictor._mark("field:exit")
    shape = (4, 3, 15)
    return {"date": str(date), "stage": 1,
            "temperature": np.zeros(shape), "sigma": np.ones(shape),
            "valid_mask": np.ones(shape, bool), "land_mask": np.zeros(shape[:2], bool),
            "salinity": None, "sigma_s": None, "density": None,
            "provenance": {"bundle": "b", "input_date": str(date)}}


@pytest.fixture
def fake(monkeypatch):
    p = _FakePredictor()
    monkeypatch.setattr("phase2.tscast_nio.field.predict_field", _fake_field)
    monkeypatch.setattr(FC, "get_predictor", lambda stage=1, **kw: p)
    return p


# ==================================================== the cache key: one definition, per stage

def test_the_stage1_key_is_the_existing_function_not_a_new_transcription():
    """`field.v2_cache_version()` was factored out after being pasted into three pages. A second
    definition here would be the fifth copy and the first one free to drift."""
    from phase2.tscast_nio import field

    assert FC.cache_version(1) == field.v2_cache_version()


def test_stage2_gets_its_own_key_because_the_stage1_key_never_moves_when_stage2_does():
    """The bug `physics_page._v2s2_version` was written to dodge: the stage-1 key hashes the
    stage-1 checkpoint, so a stage-2 page keyed on it would cache forever across stage-2 retrains.
    """
    assert FC.cache_version(2) != FC.cache_version(1)
    assert FC.checkpoint_for(1) != FC.checkpoint_for(2)
    assert FC.checkpoint_for(2).endswith(FC.STAGE2_CHECKPOINT)


def test_the_key_moves_when_the_checkpoint_does(tmp_path, monkeypatch):
    ck = tmp_path / "tscast_stage2_sat_s2.pt"
    ck.write_bytes(b"x" * 10)
    monkeypatch.setattr(FC, "checkpoint_for", lambda stage=1: str(ck))
    before = FC.cache_version(2)
    time.sleep(0.01)
    ck.write_bytes(b"y" * 4096)                     # different size and mtime
    assert FC.cache_version(2) != before


# ==================================================== the lock

def test_two_callers_never_share_the_predictor_at_the_same_time(monkeypatch):
    """The real failure, with real threads.

    `inference.reconstruct` overwrites `predictor.ds.index` and never restores it (inference.py:203)
    while `predict_field` borrows and restores the same attribute (field.py:124-144). A point lookup
    landing inside a field reconstruction shrinks the index from ~11,832 rows to 1 mid-iteration and
    the answer comes back plausible and wrong -- it does not raise. Four app pages hold the
    predictor in `st.cache_resource`, which is shared across browser tabs.

    So: run both paths concurrently and assert the event log never shows one open inside the other.
    """
    p = _FakePredictor(hold=0.05)
    monkeypatch.setattr("phase2.tscast_nio.field.predict_field", _fake_field)
    monkeypatch.setattr(FC, "get_predictor", lambda stage=1, **kw: p)

    threads = [threading.Thread(target=FC.field_for, args=("2026-05-15",), name="A"),
               threading.Thread(target=FC.reconstruct_point, args=(15.0, 68.0, "2026-05-15"),
                                name="B"),
               threading.Thread(target=FC.field_for, args=("2026-05-16",), name="C")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    depth = 0
    for tag, _ in p.events:
        depth += 1 if tag.endswith(":enter") else -1
        assert depth in (0, 1), f"two predictor calls overlapped: {p.events}"
    assert depth == 0
    assert len(p.events) == 6, p.events


def test_the_lock_is_reentrant_so_a_locked_path_can_call_another(fake):
    """RLock, not Lock. A caller already holding it must not deadlock against itself."""
    with FC._LOCK:
        out = FC.field_for("2026-05-15")
        pt = FC.reconstruct_point(15.0, 68.0, "2026-05-15")
    assert out["date"] == "2026-05-15" and pt["temperature"][0] == 29.5


def test_every_predictor_call_in_this_module_sits_inside_the_lock():
    """A source guard, parsed rather than grepped: the module DOCUMENTS the rule at length, so a
    text search finds the explanation as readily as a violation."""
    src = open(os.path.join(ROOT, "src/phase2/tscast_nio/field_cache.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines()

    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        if name in ("predict_field", "reconstruct"):
            calls.append(node.lineno)
    assert len(calls) >= 2, f"expected both predictor entry points, found {calls}"

    for ln in calls:
        # the enclosing `with _LOCK:` is the nearest preceding line at a shallower indent
        indent = len(lines[ln - 1]) - len(lines[ln - 1].lstrip())
        guarded = any("with _LOCK:" in lines[k]
                      and (len(lines[k]) - len(lines[k].lstrip())) < indent
                      for k in range(ln - 2, max(ln - 8, -1), -1))
        assert guarded, f"line {ln} calls the predictor outside the lock: {lines[ln - 1].strip()}"


# ==================================================== keep, dates, provenance

def test_keep_trims_the_field_so_a_cache_entry_is_not_12_megabytes(fake):
    small = FC.field_for("2026-05-15", keep=("date", "temperature"))
    assert set(small) == {"date", "temperature"}
    assert "sigma" not in small and "salinity" not in small


def test_asking_to_keep_something_predict_field_does_not_return_raises(fake):
    with pytest.raises(KeyError, match="thermocline"):
        FC.field_for("2026-05-15", keep=("date", "thermocline"))


def test_the_default_keep_always_carries_provenance():
    """A field with no provenance is a picture with no source."""
    assert "provenance" in FC.DEFAULT_KEEP
    assert set(FC.DEFAULT_KEEP).issubset(set(FC.ALL_KEYS))


def test_the_device_that_produced_the_numbers_is_recorded(fake, monkeypatch):
    monkeypatch.delenv("OCEANEMBED_DEVICE", raising=False)
    assert FC.field_for("2026-05-15")["provenance"]["device"] == "cpu"
    assert FC.field_for("2026-05-15", device="cuda")["provenance"]["device"] == "cuda"


def test_the_device_default_is_opt_in_and_never_changes_on_its_own(monkeypatch):
    """field.py protects the CPU default with a stated reason -- an exported file must not differ
    from the page beside it. So CUDA is an environment decision, never a code change."""
    monkeypatch.delenv("OCEANEMBED_DEVICE", raising=False)
    assert FC.device_default() is None
    monkeypatch.setenv("OCEANEMBED_DEVICE", "cuda")
    assert FC.device_default() == "cuda"


def test_available_dates_are_the_models_own_calendar(fake):
    d = FC.available_dates(1)
    assert d[0] == FIRST and d[-1] == LAST
    assert len(d) == 388
    assert all(len(x) == 10 for x in d)


def test_reset_drops_the_cached_predictors():
    FC._PREDICTORS[(99, None)] = object()
    FC.reset()
    assert FC._PREDICTORS == {}


# ==================================================== the streamlit wrapper

def test_no_cached_streamlit_function_takes_an_underscore_argument():
    """`st.cache_data` SILENTLY drops any argument whose name starts with `_`. A `_version`
    parameter therefore becomes no cache key at all, and the page serves a stale field with no
    error -- the 8 degC failure of 2026-09-02. Checked structurally so it holds for functions
    nobody has written yet.
    """
    pytest.importorskip("streamlit")
    path = os.path.join(ROOT, "app/phase2/_fields.py")
    tree = ast.parse(open(path, encoding="utf-8").read())

    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorated = any("cache" in ast.dump(d) for d in node.decorator_list)
        if not decorated:
            continue
        checked += 1
        bad = [a.arg for a in node.args.args if a.arg.startswith("_")]
        assert not bad, f"{node.name} takes {bad}, which streamlit drops from the cache key"
    assert checked >= 3, f"expected several cached functions, found {checked}"


def test_the_streamlit_wrapper_imports_and_delegates_every_decision_downwards():
    """The helper must add plumbing only. If a science decision migrates up into the page layer it
    stops being testable without a browser."""
    pytest.importorskip("streamlit")
    src = open(os.path.join(ROOT, "app/phase2/_fields.py"), encoding="utf-8").read()
    assert "predict_field" not in src, "the wrapper must go through field_cache, not around it"
    assert "_LOCK" not in src, "the lock belongs in src/, where scripts and the API also take it"
    assert "TSCastPredictor" not in src
