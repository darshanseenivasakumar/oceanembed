"""The guard for a bug that cost most of a day and produced plausible numbers throughout.

`cnn3d` sizes its `AvgPool3d` from the `t_seq` passed at CONSTRUCTION. Rebuilding a checkpoint with
`ck["T_SEQ"]` (the DATA window) instead of `built_t_seq` (the construction value) yields a
structurally different network. `load_state_dict` ACCEPTS it -- conv weights do not encode temporal
extent, so nothing raises -- and the model then predicts differently on identical input.

It bit twice: `score_by_basin` disagreed with a checkpoint's own recorded RMSE by 0.02 degC, and
`calibrate_uncertainty` fitted every per-depth sigma scale through a model the project does not
ship. Neither failed loudly. Suggested by Darshan, AGENT_SYNC 2026-09-02.
"""
import pytest
import torch

from phase2.tscast_nio.models import TSCastNIO
from phase2.tscast_nio.models.tscast import (assert_architecture_matches,
                                             temporal_pool_signature)


def _model(t_seq):
    return TSCastNIO("cnn3d", c_in=7, t_seq=t_seq, p=17, latent=128,
                     decoder="simple", stage=1)


def test_the_pool_signature_separates_the_two_architectures():
    """t_seq=1 does no temporal pooling; t_seq=11 halves it three times."""
    assert temporal_pool_signature(_model(1)) == [1, 1, 1]
    assert temporal_pool_signature(_model(11)) == [2, 2, 2]


def test_the_signature_alone_cannot_separate_11_from_31():
    """Documents WHY the exact built_t_seq check exists. Both pool [2,2,2], so a signature-only
    guard would wave through an 11-vs-31 mismatch."""
    assert temporal_pool_signature(_model(11)) == temporal_pool_signature(_model(31))


def test_the_exact_check_catches_what_the_signature_cannot():
    ck = {"built_t_seq": 31, "T_SEQ": 31, "pool_signature": [2, 2, 2]}
    with pytest.raises(ValueError, match="architecture mismatch"):
        assert_architecture_matches(_model(11), ck, "test")


def test_the_real_bug_is_refused():
    """Exactly what happened: built with T_SEQ=11 against a checkpoint constructed at t_seq=1."""
    ck = {"built_t_seq": 1, "T_SEQ": 11, "pool_signature": [1, 1, 1]}
    with pytest.raises(ValueError) as e:
        assert_architecture_matches(_model(11), ck, "test")
    msg = str(e.value)
    assert "built_t_seq" in msg and "T_SEQ" in msg, "the error must name both, since confusing " \
                                                    "them IS the bug"


def test_the_correct_rebuild_is_accepted():
    ck = {"built_t_seq": 1, "T_SEQ": 11, "pool_signature": [1, 1, 1]}
    assert_architecture_matches(_model(1), ck, "test")


def test_a_checkpoint_without_the_field_is_not_second_guessed():
    """Checkpoints written before 2026-09-02 carry neither field. Passing is honest: inventing a
    constraint from nothing would hide that they cannot be checked."""
    assert_architecture_matches(_model(11), {"T_SEQ": 11}, "test")


def test_load_state_dict_really_does_accept_the_mismatch():
    """The premise of the whole guard, asserted rather than believed. If torch ever started
    rejecting this on its own, the guard would be redundant -- and this test would say so."""
    good, bad = _model(1), _model(11)
    bad.load_state_dict(good.state_dict())          # must NOT raise
    x = torch.zeros(1, 7, 11, 17, 17)
    g = torch.zeros(1, 3, 1, 17, 17)
    clim = torch.zeros(1, 12, 15)
    mo = torch.zeros(1, dtype=torch.long)
    with torch.no_grad():
        a, _ = good(x, g, clim, mo)
        b, _ = bad(x, g, clim, mo)
    assert not torch.allclose(a, b), (
        "the two architectures produced identical output on identical input; if that is now true, "
        "this whole class of bug is gone and the guard can be reconsidered")


def test_every_checkpoint_consumer_calls_the_guard():
    """A consumer that rebuilds a model and skips the guard is how this recurs."""
    import os
    for path in ("src/phase2/tscast_nio/inference.py",
                 "scripts/phase2/score_by_basin.py",
                 "scripts/phase2/calibrate_uncertainty.py"):
        src = open(path, encoding="utf-8").read()
        assert "assert_architecture_matches" in src, f"{os.path.basename(path)} rebuilds a model " \
                                                     f"from a checkpoint without the guard"
