"""The frozen headline must stay byte-identical, and the manifest must not drift from it.

These tests are the regression half of `scripts/phase2/freeze_headline.py`. The failure they
exist to catch is mundane and has already happened once in this repo's history: a retrain writes
over `artifacts/tscast_*.pt`, the numbers quoted in docs/EXPERIMENT_LOG.md silently stop matching
the checkpoint on disk, and nobody notices until someone tries to reproduce a result.

They SKIP when the artifacts are absent, because `artifacts/*` is gitignored — a fresh clone
without the data bundle has nothing to check, and a skip there is honest where a pass would not be.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS = os.path.join(REPO, "artifacts")
MANIFEST = os.path.join(ARTIFACTS, "frozen_manifest.json")


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not os.path.exists(MANIFEST):
        pytest.skip("no artifacts/frozen_manifest.json — run scripts/phase2/freeze_headline.py")
    with open(MANIFEST) as f:
        return json.load(f)


def test_manifest_lists_both_legs_of_both_ablations(manifest):
    """A delta is only reproducible if the LOSING leg survives too. Freezing just the winner
    would leave the wind and physics claims unverifiable."""
    claims = manifest["claims"]
    for required in ("headline", "physics_control", "wind_on", "wind_off_control"):
        assert required in claims, f"{required} missing — an ablation leg is unprotected"


def test_every_frozen_artifact_is_still_byte_identical(manifest):
    """THE guard. If this fails, a retrain has overwritten a shipped artifact: either restore
    from artifacts/frozen/, or re-freeze deliberately and append to EXPERIMENT_LOG."""
    changed = []
    for fname, rec in manifest["files"].items():
        live = os.path.join(ARTIFACTS, fname)
        if not os.path.exists(live):
            pytest.skip(f"{fname} absent — artifacts are gitignored, nothing to verify")
        if _sha256(live) != rec["sha256"]:
            changed.append(fname)
    assert not changed, (
        f"{changed} differ from the frozen headline. The numbers in docs/EXPERIMENT_LOG.md were "
        f"produced by the FROZEN bytes, not by these. Restore or re-freeze deliberately."
    )


def test_manifest_numbers_match_the_metrics_files_they_name(manifest):
    """The manifest copies scores out of the metrics JSONs. If someone edits a metrics file by
    hand, the copy and the source diverge — and the manifest is what gets read in a hurry."""
    pairs = {
        "headline": "tscast_stage2_s2_nodensity_metrics.json",
        "physics_control": "tscast_stage2_s2_metrics.json",
        "wind_on": "tscast_stage1_7ch_metrics.json",
        "wind_off_control": "tscast_stage1_5ch_metrics.json",
    }
    for claim, fname in pairs.items():
        path = os.path.join(ARTIFACTS, fname)
        if not os.path.exists(path):
            pytest.skip(f"{fname} absent — artifacts are gitignored")
        with open(path) as f:
            overall = json.load(f)["metrics"]["overall"]
        stamped = manifest["claims"][claim]
        assert stamped["overall_rmse"] == pytest.approx(overall["rmse"], abs=1e-12), claim
        assert stamped["overall_n"] == overall["n"], claim


def test_the_headline_is_the_best_temperature_rmse_we_ship(manifest):
    """SCIENTIFIC sanity, not a shape check. Whatever we call the headline must actually be the
    lowest Argo temperature RMSE among the frozen legs — otherwise we are presenting a number we
    have already beaten. All legs are scored on the same 962 profiles (n identical), so they are
    directly comparable; that identity is asserted rather than assumed.
    """
    claims = manifest["claims"]
    ns = {k: v["overall_n"] for k, v in claims.items()}
    assert len(set(ns.values())) == 1, f"legs scored on different sample counts {ns} — not comparable"
    best = min(claims, key=lambda k: claims[k]["overall_rmse"])
    assert best == "headline", (
        f"'{best}' has a lower RMSE ({claims[best]['overall_rmse']:.4f}) than the declared "
        f"headline ({claims['headline']['overall_rmse']:.4f}). Promote it or explain why not."
    )
