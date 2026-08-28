"""Encoder tests.

The two that matter most are the pair asserting the CONTROL is blind and the spatial encoders are
not. Without them the bake-off could compare four models that all see the same information, and
"spatial embedding helps" would be unfalsifiable.
"""
import warnings

import pytest
import torch

warnings.filterwarnings("ignore", message=".*enable_nested_tensor.*")

from phase2.tscast_nio import config, encoders as E

C, P, DEP = 5, 17, config.N_DEPTHS
ALL = sorted(E.ENCODERS)


@pytest.mark.parametrize("name", ALL)
def test_every_candidate_returns_the_15_contract_depths(name):
    m = E.build(name, C, 1, P, DEP)
    out = m(torch.randn(3, C, 1, P, P), torch.randn(3, 3, 1, P, P))
    assert out.shape == (3, DEP)


@pytest.mark.parametrize("name", ALL)
def test_every_candidate_survives_the_t_seq_flip(name):
    """The whole build-now-retrain-later plan rests on T_SEQ=31 needing no code change."""
    m = E.build(name, C, 31, P, DEP)
    out = m(torch.randn(2, C, 31, P, P), torch.randn(2, 3, 1, P, P))
    assert out.shape == (2, DEP)


def test_mlp_control_is_genuinely_blind_to_its_neighbours():
    """The control must lose on INFORMATION. If it can see neighbours, it is not a control and the
    bake-off proves nothing."""
    m = E.build("mlp_control", C, 1, P, DEP).eval()
    x = torch.randn(1, C, 1, P, P)
    g = torch.randn(1, 3, 1, P, P)
    with torch.no_grad():
        before = m(x, g)
        x2 = x.clone()
        x2[0, :, 0, 0, 0] = 999.0          # a corner cell, far from the centre
        after = m(x2, g)
    assert torch.allclose(before, after), "the control read a neighbour: it is not a control"


@pytest.mark.parametrize("name", ["cnn3d", "cnn_attention", "vit"])
def test_spatial_encoders_actually_use_their_neighbours(name):
    """Mirror image of the control test. A spatial encoder that ignores context would score like
    the control and we would wrongly conclude the embedding does not help."""
    m = E.build(name, C, 1, P, DEP).eval()
    x = torch.randn(1, C, 1, P, P)
    g = torch.randn(1, 3, 1, P, P)
    with torch.no_grad():
        before = m(x, g)
        x2 = x.clone()
        x2[0, :, 0, 0, 0] = 999.0
        after = m(x2, g)
    assert not torch.allclose(before, after), f"{name} ignored a neighbouring cell"


def test_capacity_is_levelled_so_the_encoder_is_the_only_variable():
    """If one candidate is 5x larger, a win is 'bigger helps', not 'this architecture helps'."""
    n = {k: E.n_params(E.build(k, C, 1, P, DEP)) for k in ALL}
    assert max(n.values()) / min(n.values()) < 1.6, f"capacity not levelled: {n}"


def test_all_candidates_share_the_identical_decoding_head():
    heads = [E.n_params(E.build(k, C, 1, P, DEP).head) for k in ALL]
    assert len(set(heads)) == 1, f"heads differ: {heads}; the encoder is no longer the only variable"


def test_gnn_is_deliberately_absent_not_forgotten():
    """Documents the decision in code: a uniform lat/lon lattice has no irregular graph."""
    assert "gnn" not in E.ENCODERS
    assert set(E.ENCODERS) == {"mlp_control", "cnn3d", "cnn_attention", "vit"}
    assert "GNN is deliberately absent" in E.__doc__


def test_unknown_encoder_raises_rather_than_silently_substituting():
    with pytest.raises(KeyError, match="unknown encoder"):
        E.build("transformer_xl", C, 1, P, DEP)
