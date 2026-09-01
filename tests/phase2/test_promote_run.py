"""Promotion tests. The guard here exists because this project already shipped a leaky number once.

Tagged files are experiments; the unsuffixed name is the SHIPPED model. The gap between those two
is what blanked the dashboard and left `accept.py::check_v2_ui` returning pass-with-a-skip.
"""
import importlib.util
import json
import os

import pytest

from oceanembed import config

_SPEC = importlib.util.spec_from_file_location(
    "promote_run",
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "phase2", "promote_run.py"))
promote_run = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(promote_run)

# A real commit from this repo's history that predates the A1 embargo fix (1d3c135).
PRE_EMBARGO_COMMIT = "6c83006"


def _fake_run(tmp_path, tag, code_commit, stage="stage1"):
    """Minimal on-disk run: a checkpoint and a metrics JSON, nothing else."""
    ck = tmp_path / f"tscast_{stage}_{tag}.pt"
    ck.write_bytes(b"not-a-real-checkpoint-but-hashable")
    m = tmp_path / f"tscast_{stage}_{tag}_metrics.json"
    payload = {"metrics": {"overall": {"rmse": 0.8645}}}
    if code_commit is not None:
        payload["code_commit"] = code_commit
    m.write_text(json.dumps(payload), encoding="utf-8")
    return ck, m


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """Redirect config.ARTIFACTS so nothing here can touch the real artifacts/ directory."""
    monkeypatch.setattr(config, "ARTIFACTS", str(tmp_path))
    return tmp_path


def test_a_pre_embargo_run_is_refused(artifacts):
    """The whole point. 6c83006 does not contain the fix, so everything it trained read
    test-period surface fields on 5 of 304 train days."""
    _fake_run(artifacts, "leaky", PRE_EMBARGO_COMMIT)
    with pytest.raises(SystemExit) as e:
        promote_run.promote("leaky")
    assert "REFUSING" in str(e.value)
    assert not (artifacts / "tscast_stage1.pt").exists(), "a refused run must not be copied"


def test_a_run_with_no_recorded_commit_is_refused(artifacts):
    """Fail closed. An unknown lineage is not the same as a good one, and the cost of guessing
    wrong is a leaky number back on the dashboard."""
    _fake_run(artifacts, "anon", None)
    with pytest.raises(SystemExit) as e:
        promote_run.promote("anon")
    assert "no code_commit" in str(e.value)


def test_a_post_embargo_run_is_promoted_and_stamped(artifacts):
    """HEAD contains the fix, so this one is allowed -- and promotion must record WHICH experiment
    it came from, which tscast_output_schema.md:117-129 requires and nothing previously supplied."""
    _fake_run(artifacts, "good", "HEAD")
    promote_run.promote("good")

    assert (artifacts / "tscast_stage1.pt").exists()
    m = json.loads((artifacts / "tscast_stage1_metrics.json").read_text(encoding="utf-8"))
    assert m["promoted_from"] == "good"
    assert len(m["checkpoint_sha256"]) == 64
    assert "promoted_at" in m
    assert "promotion_warning" not in m, "a clean promotion must not carry a warning"


def test_force_promotes_a_leaky_run_but_records_that_it_did(artifacts):
    """An escape hatch that leaves fingerprints. Silent force is how this happens twice."""
    _fake_run(artifacts, "leaky", PRE_EMBARGO_COMMIT)
    promote_run.promote("leaky", force=True)
    m = json.loads((artifacts / "tscast_stage1_metrics.json").read_text(encoding="utf-8"))
    assert "promotion_warning" in m
    assert PRE_EMBARGO_COMMIT in m["promotion_warning"]


def test_promoting_a_tag_that_does_not_exist_names_what_is_available(artifacts):
    _fake_run(artifacts, "real", "HEAD")
    with pytest.raises(SystemExit) as e:
        promote_run.promote("typo")
    assert "real" in str(e.value), "the error should list what the user could have meant"


def test_accept_no_longer_reports_pass_when_the_ui_check_cannot_run():
    """A skip that returns True is the most dangerous kind of green: `check_v2_ui` asserts every
    number the UI renders equals its artifact, and when the artifact is absent that guarantee is
    untestable -- not satisfied."""
    src = open(os.path.join("scripts", "phase2", "accept.py"), encoding="utf-8").read()
    i = src.index('mpath = config.art("tscast_stage1_metrics.json")')
    # Exactly the missing-artifact branch: from the path lookup to where the file is opened.
    # Comments are stripped first -- the branch documents the old `return True` behaviour on
    # purpose, and an assertion that cannot tell code from prose would forbid explaining the bug.
    branch = src[i:src.index("with open(mpath", i)]
    code = "\n".join(ln for ln in branch.splitlines() if not ln.strip().startswith("#"))
    assert "return False" in code, "the missing-artifact branch must FAIL, never skip-pass"
    assert "return True" not in code, "returning True here is the skip-that-passes, again"
