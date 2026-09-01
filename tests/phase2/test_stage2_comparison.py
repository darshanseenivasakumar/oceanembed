"""Stage 2 must READ stage 1's score, never carry it as a literal.

THE BUG THIS LOCKS DOWN. `train_stage2.py` used to hold `"stage1_rmse": 0.8612` and
`"stage1_skill_rmse_ratio": 0.2975` as float literals in the `compare_against` block it writes
into every stage-2 metrics artifact. When the leakage embargo (`a5cdd3a`) retrained stage 1 to
0.8793 / +0.2827, the literals did not move. Every stage-2 run after that stamped a superseded
number into a fresh artifact under the name of a current one — the quiet failure mode, because
the file looks authoritative and nothing errors.

The `which` field had always named the artifact the numbers should have come from. The fix was to
read it. These tests keep it read.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from phase2.tscast_nio.train.train_stage2 import _stage1_comparison

SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                   "src", "phase2", "tscast_nio", "train", "train_stage2.py")
ARTIFACTS = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")


def test_no_scored_metric_survives_as_a_float_literal():
    """REGRESSION, and the one that matters. Any `"stage1_...": <number>` in the source means the
    literal is back. Prose mentioning the historical 0.8612 is fine and deliberate — what must
    never return is a *scored value assigned to a key*."""
    with open(SRC, encoding="utf-8") as f:
        src = f.read()
    offenders = re.findall(r'"stage1_(?:rmse|skill_rmse_ratio|n)"\s*:\s*[0-9]', src)
    assert not offenders, (
        f"a scored stage-1 value is hardcoded again ({offenders}). It must be read from "
        f"artifacts/tscast_stage1_<tag>_metrics.json at runtime, or it will go stale the next "
        f"time stage 1 is retrained — which is exactly what happened on 2026-08-31."
    )


def test_comparison_matches_the_artifact_it_names():
    """The block must agree with the file its own `which` field points at."""
    block = _stage1_comparison()
    path = os.path.join(ARTIFACTS, "tscast_stage1_7ch_metrics.json")
    if not os.path.exists(path):
        pytest.skip("stage-1 7ch metrics absent — artifacts are gitignored")
    with open(path, encoding="utf-8") as f:
        overall = json.load(f)["metrics"]["overall"]
    assert block["stage1_rmse"] == pytest.approx(overall["rmse"], abs=1e-12)
    assert block["stage1_skill_rmse_ratio"] == pytest.approx(overall["skill_rmse_ratio"], abs=1e-12)
    assert block["stage1_n"] == overall["n"]
    assert block["read_at_runtime"] is True
    assert "tscast_stage1_7ch_metrics.json" in block["which"]


def test_a_missing_artifact_reports_missing_rather_than_inventing_a_number():
    """The failure path, exercised. A comparison that cannot be made must say so — silently
    substituting a remembered value is the failure this whole test file exists to prevent."""
    block = _stage1_comparison("no_such_tag")
    assert block["stage1_rmse"] is None
    assert block["stage1_skill_rmse_ratio"] is None
    assert block["stage1_n"] is None
    assert "not invented" in block["note"]


def test_the_comparison_is_not_frozen_to_one_tag():
    """It must be able to score against the matched control too. Post-embargo the 5ch leg is the
    better model, so a future stage-2 run may legitimately want to compare against it."""
    path = os.path.join(ARTIFACTS, "tscast_stage1_5ch_metrics.json")
    if not os.path.exists(path):
        pytest.skip("stage-1 5ch metrics absent — artifacts are gitignored")
    block = _stage1_comparison("5ch")
    with open(path, encoding="utf-8") as f:
        overall = json.load(f)["metrics"]["overall"]
    assert block["stage1_rmse"] == pytest.approx(overall["rmse"], abs=1e-12)
    assert "5ch" in block["which"]
