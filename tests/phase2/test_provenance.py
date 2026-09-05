"""The output schema's §5 provenance contract, tested. Owner: Unit A (Arjhun).

WHY THIS FILE EXISTS
`docs/phase2/tscast_output_schema.md` §5 is marked `Status: CONTRACT` and lists ten required keys.
Until 2026-09-05 **nothing tested it**, and neither producer satisfied it -- the point path omitted
`checkpoint_sha256` and `code_commit`, the field path omitted those plus `P`, `input_date` and
`clim_train_years`. A contract nobody checks is a comment.

The second half of this file is the part that matters longest: a source-text guard that the doc
still names every key the code builds. Without it, someone edits §5, the code keeps emitting the old
set, and both look correct in isolation.
"""
from __future__ import annotations

import os

import pytest

from phase2.tscast_nio import provenance as P

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCHEMA = os.path.join(ROOT, "docs", "phase2", "tscast_output_schema.md")


class _StubPredictor:
    """Just enough predictor to assemble a block. No torch, no checkpoint, no bundle."""

    def __init__(self, **meta):
        self.meta = {"seed": 42, "T_SEQ": 11, "P": 17, "encoder": "cnn3d",
                     "clim_train_years": [2019, 2020, 2021], **meta}
        self.data = {"input_source": "satellite"}
        self.checkpoint_path = None
        self.stage = 1


# --------------------------------------------------------------------------- the contract itself


@pytest.mark.parametrize("key", P.SCHEMA_V5_KEYS)
def test_every_schema_v5_key_is_present(key):
    """Parametrised so a missing key names ITSELF in the failure, rather than one test reporting
    'a key is missing' and leaving you to find out which."""
    block = P.provenance_block(_StubPredictor(), input_date="2026-05-15")
    assert key in block


def test_the_doc_still_names_every_key_the_code_builds():
    """Doc and code cannot drift apart silently.

    Source-text, deliberately: parsing the markdown into a structure would be a second
    implementation of the contract, and the bug would then live in the parser.
    """
    src = open(SCHEMA, encoding="utf-8").read()
    assert "## 5. `provenance`" in src, "§5 has moved or been renamed"
    for key in P.SCHEMA_V5_KEYS:
        assert f'"{key}"' in src, f"§5 no longer names {key!r} -- doc and code have diverged"


def test_an_unknown_is_named_not_invented():
    """START_HERE rule 8. A checkpoint that cannot be read yields the token, never a plausible hash
    and never a silently absent key."""
    block = P.provenance_block(_StubPredictor(), input_date="2026-05-15")
    assert block["checkpoint_sha256"] == P.UNKNOWN
    assert P.checkpoint_sha256(None) == P.UNKNOWN
    assert P.checkpoint_sha256("does_not_exist.pt") == P.UNKNOWN
    assert len(P.UNKNOWN) != 64, "the unknown token must not look like a sha256"


def test_extra_cannot_silently_drop_a_contract_key():
    """`extra` merges last, so a careless caller could overwrite a §5 key with nothing. The
    assertion inside provenance_block is what stops that, and this pins it."""
    block = P.provenance_block(_StubPredictor(), input_date="2026-05-15",
                               extra={"bundle": "data/processed/daily_sat/v001"})
    assert block["bundle"] == "data/processed/daily_sat/v001"
    for key in P.SCHEMA_V5_KEYS:
        assert key in block


def test_stage_2_is_named_in_the_model_field():
    block = P.provenance_block(_StubPredictor(stage=2), input_date="2026-05-15")
    assert block["model"] == "tscast-nio-stage2"
    assert block["stage"] == 2


# --------------------------------------------------------------------------- netcdf flattening


def test_no_key_can_vanish_when_flattened():
    """THE failure this function exists to prevent, and one it committed against itself.

    NetCDF attrs cannot hold None, nested dicts or bools. The obvious implementation drops a None --
    which turns "not recorded" into "no such concept" in the one artifact that leaves the building.
    An EMPTY dict was doing exactly that until the smoke test on 2026-09-05: recursing into it added
    nothing, so the key disappeared.
    """
    prov = {"a": None, "b": True, "c": False, "d": [2019, 2020], "e": {}, "f": [],
            "g": {"nested": None}, "h": 3.5, "i": "text"}
    flat = P.as_netcdf_attrs(prov)
    for key in prov:
        assert any(k == key or k.startswith(key + ".") for k in flat), f"{key} vanished"


def test_flattened_values_are_netcdf_legal():
    flat = P.as_netcdf_attrs({"a": None, "b": True, "c": [1, 2], "d": {"x": 1}})
    for k, v in flat.items():
        assert isinstance(v, (int, float, str)), f"{k} is {type(v)}, which NetCDF cannot hold"
        assert not isinstance(v, bool), f"{k} is a bool; it must be a string so it cannot read as 1"


def test_a_none_is_distinguishable_from_a_real_value():
    flat = P.as_netcdf_attrs({"checkpoint_sha256": None})
    assert flat["checkpoint_sha256"] == P.NOT_RECORDED
    assert len(flat["checkpoint_sha256"]) != 64


def test_code_commit_returns_a_string_even_when_git_is_unavailable(monkeypatch):
    """Provenance must never be the thing that takes down a reconstruction."""
    import subprocess as sp

    def boom(*a, **k):
        raise sp.SubprocessError("no git here")

    monkeypatch.setattr(sp, "check_output", boom)
    assert P.code_commit() == P.UNKNOWN
    assert P.code_dirty() is None            # unknown, NOT False -- absence is not "clean"
