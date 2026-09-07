"""The manifest must name the right deliverable and stay byte-identical to what it claims.

These tests are the regression half of `scripts/phase2/freeze_headline.py`. The failure they
exist to catch is mundane and has already happened in this repo: a retrain writes over
`artifacts/tscast_*.pt`, the numbers quoted in the docs silently stop matching the checkpoint on
disk, and nobody notices until someone tries to reproduce a result.

REWRITTEN 2026-09-04, and the reason is itself the lesson. These tests were written in Phase 1
against a manifest whose headline was the GLORYS stage-2 run (0.8548). When the manifest was
corrected to name the SATELLITE run (`sat_7ch_s42`, 0.9078) as the PS deliverable, the schema
changed with it -- `claims["headline"]` became `claims["deliverable_satellite"]`, and the separate
`files` block folded into each claim as `checkpoint_sha256`. The old tests broke, and the break was
only caught when the branch was merged and the FULL suite run. Updated to the current contract;
one of them (see the last test) had its premise inverted by the science and was replaced rather
than renamed.

Skips are honest here: `artifacts/*` is gitignored, so a fresh clone has nothing to check, and a
checkpoint that lives on another machine is recorded as pending rather than failed.
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
        pytest.skip("no artifacts/frozen_manifest.json - run scripts/phase2/freeze_headline.py")
    with open(MANIFEST) as f:
        return json.load(f)


def test_the_manifest_names_exactly_one_deliverable(manifest):
    """A manifest that names two deliverables, or none, cannot be quoted from."""
    claims = manifest["claims"]
    flagged = [k for k, v in claims.items() if v.get("deliverable")]
    assert len(flagged) == 1, f"expected exactly one deliverable, found {flagged}"
    assert manifest["deliverable_key"] == flagged[0], (
        f"deliverable_key {manifest['deliverable_key']!r} disagrees with the flagged claim "
        f"{flagged[0]!r} - the pointer and the flag must not drift apart"
    )


def test_the_comparators_survive_alongside_the_deliverable(manifest):
    """A delta is only reproducible if the losing leg survives too. Keeping only the deliverable
    would leave the GLORYS-vs-satellite comparison unverifiable."""
    claims = manifest["claims"]
    comparators = [k for k, v in claims.items() if not v.get("deliverable")]
    assert len(comparators) >= 2, (
        f"only {len(comparators)} comparator(s) kept - the deliverable's context is gone"
    )
    assert any(v.get("input_source") == "glorys" for v in claims.values()), (
        "no GLORYS-input comparator retained; the satellite-vs-reanalysis contrast is the point"
    )


def test_every_frozen_checkpoint_is_still_byte_identical(manifest):
    """THE guard. If this fails, a retrain overwrote a shipped artifact: restore from
    artifacts/frozen/, or re-freeze deliberately and update PHASE2_STATUS.md.

    A claim whose checkpoint was never frozen here (it lives on the training machine) carries a
    null checksum and is skipped -- pending is not the same as changed.

    THE MIRROR OF THAT, added 2026-09-04: a claim frozen on the OTHER machine carries a real
    checksum and no local file. That is not a changed artifact either -- it is one this disk
    cannot re-verify. Neither machine holds all four runs (the stage-2 GLORYS comparators exist
    only on Darshan's, the satellite deliverable and embargoed comparator only on Arjhun's), so
    reading "checksum recorded + file absent" as CHANGED made the guard fail on both machines for
    a state that is simply how the project is distributed. It is skipped and counted, so a genuine
    deletion is still visible in the count rather than passing silently.
    """
    changed, checked, elsewhere = [], 0, []
    for key, rec in manifest["claims"].items():
        recorded = rec.get("checkpoint_sha256")
        if recorded is None:
            continue                                   # pending: not on this machine
        live = os.path.join(ARTIFACTS, rec["checkpoint"])
        if not os.path.exists(live):
            if rec.get("checkpoint_frozen_elsewhere"):
                elsewhere.append(key)                  # frozen on the other machine, not verifiable here
            else:
                changed.append(f"{key}: {rec['checkpoint']} was frozen HERE but is now MISSING")
            continue
        checked += 1
        if _sha256(live) != recorded:
            changed.append(f"{key}: {rec['checkpoint']} CHANGED")
    if checked == 0 and not changed:
        pytest.skip(f"no frozen checkpoints present on this machine - nothing to verify "
                    f"({len(elsewhere)} frozen elsewhere)")
    assert not changed, (
        f"{changed} - the numbers in the manifest were produced by the FROZEN bytes, not these."
    )


def test_manifest_numbers_match_the_metrics_files_they_name(manifest):
    """The manifest copies scores out of each run's metrics JSON. If someone edits a metrics file
    by hand, the copy and the source diverge -- and the manifest is what gets read in a hurry.

    The pairing is taken from the claim's OWN `metrics_file` field rather than a hardcoded map, so
    this test cannot go stale the way the Phase-1 version did.
    """
    checked = 0
    for key, rec in manifest["claims"].items():
        path = os.path.join(ARTIFACTS, rec["metrics_file"])
        if not os.path.exists(path):
            continue                                   # gitignored / on another machine
        with open(path) as f:
            overall = json.load(f)["metrics"]["overall"]
        assert rec["overall_rmse"] == pytest.approx(overall["rmse"], abs=1e-12), key
        assert rec["overall_n"] == overall["n"], key
        checked += 1
    if checked == 0:
        pytest.skip("no metrics files present on this machine")


def test_a_better_scoring_glorys_comparator_is_not_the_deliverable(manifest):
    """REPLACES `test_the_headline_is_the_best_temperature_rmse_we_ship`, whose premise the
    science inverted.

    That test asserted the declared headline must have the LOWEST RMSE of every frozen leg. That
    was true while the headline was a GLORYS-input run. It is now actively wrong, and dangerously
    so: the PS requires satellite-only inputs, so the deliverable is `sat_7ch_s42` at 0.9078 degC
    while the GLORYS stage-2 comparator scores BETTER at 0.8548. Left as written, the old test
    would fail on the correct manifest and its failure message would instruct the reader to
    "promote it" -- i.e. to re-label the reanalysis-fed run as the deliverable, which is exactly
    the mistake the manifest fix existed to undo.

    The real invariant is the one that survives: the deliverable is chosen by INPUT SOURCE, not by
    score, and a better-scoring GLORYS run must never displace it.
    """
    claims = manifest["claims"]
    deliverable = claims[manifest["deliverable_key"]]
    assert deliverable["input_source"] == "satellite", (
        f"the deliverable is fed by {deliverable['input_source']!r}; the PS requires satellite-only "
        f"inputs, so a reanalysis-fed run cannot be the deliverable however well it scores"
    )
    # A GLORYS comparator scoring better is EXPECTED here, and must not promote it.
    better = [k for k, v in claims.items()
              if not v.get("deliverable")
              and v.get("overall_rmse") is not None
              and deliverable.get("overall_rmse") is not None
              and v["overall_rmse"] < deliverable["overall_rmse"]]
    for k in better:
        assert claims[k]["input_source"] != "satellite", (
            f"{k} is satellite-fed and scores better than the declared deliverable - that one "
            f"SHOULD be promoted, unlike a GLORYS comparator"
        )


def test_all_legs_are_scored_on_the_same_argo_set(manifest):
    """Cross-leg comparison is only meaningful on identical sample counts. If a leg was scored on
    a different Argo set, its RMSE is not comparable to the others and the manifest would be
    inviting an apples-to-oranges read.

    Since 2026-09-07 the manifest can hold legs under two SCORING PROTOCOLS: the deliverable and
    the embargoed comparator are re-scored under seafloor_masked_v1 (n 12,736), while the stage-2
    GLORYS comparators live on another machine and are carried forward under unmasked_v1
    (n 12,829). Identical n is required WITHIN a protocol; a leg under a different protocol from
    the deliverable must carry a note saying it is not directly comparable."""
    by_proto: dict = {}
    for k, v in manifest["claims"].items():
        if v.get("overall_n"):
            by_proto.setdefault(v.get("scoring_protocol", "unmasked_v1"), {})[k] = v["overall_n"]
    if sum(len(g) for g in by_proto.values()) < 2:
        pytest.skip("fewer than two scored legs present")
    for proto, ns in by_proto.items():
        assert len(set(ns.values())) == 1, (
            f"legs under {proto} scored on different sample counts: {ns}")
    deliverable_proto = manifest["claims"][manifest["deliverable_key"]].get(
        "scoring_protocol", "unmasked_v1")
    for k, v in manifest["claims"].items():
        if v.get("overall_n") and v.get("scoring_protocol", "unmasked_v1") != deliverable_proto:
            assert v.get("comparability_note"), (
                f"{k} is scored under a different protocol from the deliverable and carries no "
                f"comparability note -- a reader would compare its RMSE straight across")


# ── --verify on a manifest that spans two machines (audit 2026-09-06) ───────────────────
#
# The manifest carries checksums frozen on the OTHER machine, labelled `checkpoint_frozen_elsewhere`.
# `do_verify` treated them as "MISSING (was frozen, now gone)" and exited 1 on the training
# machine -- the very machine jury note 08 tells the presenter to run the check on, live.


def _load_freeze_headline():
    import importlib.util

    path = os.path.join(REPO, "scripts", "phase2", "freeze_headline.py")
    spec = importlib.util.spec_from_file_location("freeze_headline_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _point_at(fh, monkeypatch, tmp_path, claims):
    art = tmp_path / "artifacts"
    art.mkdir(exist_ok=True)
    mp = art / "frozen_manifest.json"
    mp.write_text(json.dumps({"frozen_at": "test", "claims": claims}), encoding="utf-8")
    monkeypatch.setattr(fh, "REPO", str(tmp_path))
    monkeypatch.setattr(fh, "ARTIFACTS", str(art))
    monkeypatch.setattr(fh, "MANIFEST", str(mp))
    return art


def test_verify_treats_a_checkpoint_frozen_elsewhere_as_pending_not_missing(tmp_path, monkeypatch, capsys):
    fh = _load_freeze_headline()
    art = tmp_path / "artifacts"
    art.mkdir()
    here = art / "here.pt"
    here.write_bytes(b"weights that live on this machine")
    _point_at(fh, monkeypatch, tmp_path, {
        "here": {"checkpoint": "here.pt", "checkpoint_present": True,
                 "checkpoint_sha256": _sha256(str(here))},
        "elsewhere": {"checkpoint": "there.pt", "checkpoint_present": False,
                      "checkpoint_sha256": "ab" * 32, "checkpoint_frozen_elsewhere": True},
        "never": {"checkpoint": "never.pt", "checkpoint_present": False,
                  "checkpoint_sha256": None},
    })
    rc = fh.do_verify()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "MISSING" not in out, "a checksum carried from the other machine is not a vanished file"
    assert "[pend]" in out and "elsewhere" in out


def test_verify_still_fails_when_a_checkpoint_frozen_here_is_gone_or_changed(tmp_path, monkeypatch, capsys):
    """The guard must not become vacuous: a checksum recorded on THIS machine whose file has
    vanished or changed is exactly the overwrite the verifier exists to catch."""
    fh = _load_freeze_headline()
    art = tmp_path / "artifacts"
    art.mkdir()
    changed = art / "changed.pt"
    changed.write_bytes(b"retrained")
    _point_at(fh, monkeypatch, tmp_path, {
        "gone": {"checkpoint": "gone.pt", "checkpoint_present": True, "checkpoint_sha256": "cd" * 32},
        "changed": {"checkpoint": "changed.pt", "checkpoint_present": True,
                    "checkpoint_sha256": "ef" * 32},
    })
    rc = fh.do_verify()
    out = capsys.readouterr().out
    assert rc == 1
    assert "MISSING" in out and "CHANGED" in out
