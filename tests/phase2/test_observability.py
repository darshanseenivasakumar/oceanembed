"""The observability field. Owner: Unit A (Arjhun).

Offline: a real TSCastNIO with random weights and a fake context, so nothing here needs the
bundle, the checkpoint or the network.

The failure this file exists to catch is a diagnostic that looks meaningful and measures an
artifact. Two of them are pinned below: an "information depth" that silently reports level 0 for a
profile with no signal at all, and a pooled above/below-floor error ratio that is really a
statement about depth rather than about observability.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from phase2.reliability import observability as OB
from phase2.tscast_nio import config as c2
from phase2.tscast_nio.models.tscast import TSCastNIO

CHANNELS = ["sst", "sss", "ssh", "u", "v", "wu", "wv"]


class FakeCtx:
    """Everything `jacobian` touches, and nothing else."""

    def __init__(self, n=8, seed=0, model=None):
        torch.manual_seed(seed)
        self.model = model or TSCastNIO("cnn3d", len(CHANNELS), t_seq=1, p=c2.P,
                                        latent=c2.LATENT_DIM, decoder="simple", stage=1)
        self.model.eval()
        self.device = "cpu"
        self.channels = list(CHANNELS)
        self.y_std = np.linspace(2.0, 1.0, c2.N_DEPTHS)
        self.argo_idx = np.zeros((n, 3), int)
        g = torch.randn(n, 3, 1, c2.P, c2.P)
        self.x = torch.randn(n, len(CHANNELS), 3, c2.P, c2.P)
        self.g = g
        self.cp = torch.zeros(n, 12, c2.N_DEPTHS)
        self.mo = torch.zeros(n, dtype=torch.long)

    def loader(self, index, batch_size=512):
        n = len(index)
        for a in range(0, n, batch_size):
            b = slice(a, min(a + batch_size, n))
            yield (self.x[b], self.g[b], None, None, None, self.cp[b], self.mo[b])

    def _unpack(self, batch):
        x, g, _, _, _, cp, mo = batch
        return x, g, cp, mo


# ==================================================== the Jacobian

def test_jacobian_shapes_and_channels():
    ctx = FakeCtx(n=6)
    J = OB.jacobian(ctx, batch_size=3)
    assert J["coherent"].shape == (6, c2.N_DEPTHS, len(CHANNELS))
    assert J["absolute"].shape == J["coherent"].shape
    assert J["l2"].shape == J["coherent"].shape
    assert J["channels"] == CHANNELS
    assert "1 s.d." in J["units"]


def test_absolute_sensitivity_bounds_the_coherent_one():
    """|sum of gradients| <= sum of |gradients|, always. If this ever fails the two are not being
    computed from the same gradient and one of them is describing a different network."""
    J = OB.jacobian(FakeCtx(n=6), batch_size=6)
    assert np.all(np.abs(J["coherent"]) <= J["absolute"] + 1e-6)
    assert np.all(J["l2"] <= J["absolute"] + 1e-6)


def test_a_dead_head_has_zero_sensitivity():
    """The sanity anchor. Zero the output head and the model cannot depend on its input at all;
    any non-zero sensitivity then would be numerical noise being reported as information."""
    ctx = FakeCtx(n=4)
    with torch.no_grad():
        for p in ctx.model.simple_head.parameters():
            p.zero_()
    J = OB.jacobian(ctx, batch_size=4)
    assert np.allclose(J["absolute"], 0.0, atol=1e-9)


def test_sensitivity_scales_with_the_output_denormalisation():
    """The Jacobian is reported in degC, so doubling the temperature standard deviation must
    double it. A missing y_std would leave the whole field in z-units while being labelled degC."""
    a = FakeCtx(n=4, seed=1)
    J1 = OB.jacobian(a, batch_size=4)
    a.y_std = a.y_std * 2.0
    J2 = OB.jacobian(a, batch_size=4)
    assert np.allclose(J2["coherent"], 2.0 * J1["coherent"], rtol=1e-5)


# ==================================================== aggregation

def test_aggregate_modes_order_as_they_must():
    J = np.array([[[3.0, 4.0]]])                       # one profile, one depth, two channels
    assert OB.aggregate(J, "max")[0, 0] == 4.0
    assert OB.aggregate(J, "l2")[0, 0] == pytest.approx(5.0)
    assert OB.aggregate(J, "sum")[0, 0] == pytest.approx(7.0)


def test_aggregate_uses_magnitude_so_opposing_channels_do_not_cancel_under_l2():
    """Two channels that oppose still carry information. Under 'sum' they cancel -- which is why
    'sum' is offered and 'l2' is the default."""
    J = np.array([[[3.0, -4.0]]])
    assert OB.aggregate(J, "l2")[0, 0] == pytest.approx(5.0)
    assert OB.aggregate(J, "sum")[0, 0] == pytest.approx(7.0)


def test_aggregate_rejects_an_unknown_mode():
    with pytest.raises(ValueError):
        OB.aggregate(np.zeros((1, 1, 2)), "average")


# ==================================================== information depth

def test_information_depth_finds_the_deepest_level_above_threshold():
    s = np.zeros((1, c2.N_DEPTHS))
    s[0, :6] = 1.0
    s[0, 6] = 0.5                                       # 75 m, index 6
    got = OB.information_depth(s, tau=0.4)
    assert got["depth_m"][0] == 75.0
    assert got["level_index"][0] == 6


def test_a_higher_threshold_can_never_report_a_deeper_floor():
    rng = np.random.default_rng(0)
    s = np.abs(rng.normal(size=(40, c2.N_DEPTHS)))
    prev = OB.information_depth(s, tau=0.05)["depth_m"]
    for tau in (0.1, 0.2, 0.4, 0.8):
        cur = OB.information_depth(s, tau=tau)["depth_m"]
        assert np.all(np.nan_to_num(cur, nan=-1) <= np.nan_to_num(prev, nan=-1) + 1e-9)
        prev = cur


def test_a_profile_with_no_signal_is_flagged_not_given_level_zero():
    """START_HERE rule 8. An all-zero sensitivity profile means "nothing here informs anything";
    returning level 0 would read as "informed at the surface only", which is a different and much
    more encouraging claim."""
    s = np.zeros((2, c2.N_DEPTHS))
    s[1, 3] = 1.0
    got = OB.information_depth(s)
    assert got["n_without_signal"] == 1
    assert got["level_index"][0] == -1
    assert np.isnan(got["depth_m"][0])
    assert got["level_index"][1] == 3


def test_information_depth_rejects_an_impossible_threshold():
    for tau in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            OB.information_depth(np.ones((1, c2.N_DEPTHS)), tau=tau)


def test_information_depth_says_in_words_that_it_is_not_a_bound():
    """The wording is the claim. If this string ever loses 'NOT', the module has started asserting
    an information-theoretic result it never computed."""
    got = OB.information_depth(np.ones((1, c2.N_DEPTHS)))
    assert "NOT an information-theoretic bound" in got["definition"]


# ==================================================== the join, and its confound

def _join_case(above_err, below_err, n=100):
    """TWO populations with DIFFERENT floors, which is what makes the join testable at all.

    If every profile shared one floor, then at any given depth all profiles would sit on the same
    side of it and no depth could compare the two groups -- the case the 'untestable' branch
    exists for. Half the profiles here have a shallow floor and half a deep one, so the depths
    between them carry both groups.
    """
    floors = np.concatenate([np.full(n, 100.0), np.full(n, 500.0)])
    E = np.where(OB.DEPTHS[None, :] > floors[:, None], below_err, above_err)
    return OB.residual_vs_information(E, floors)


def test_join_reports_supported_only_when_error_is_larger_below_the_floor():
    got = _join_case(above_err=0.5, below_err=1.5)
    assert got["supported"] is True
    assert got["verdict"].startswith("SUPPORTED")


def test_join_reports_refuted_when_the_effect_runs_the_other_way():
    """This is the real measured outcome on the shipped model, and the module must be able to say
    so. A diagnostic that can only confirm its own hypothesis is not a diagnostic."""
    got = _join_case(above_err=1.5, below_err=0.5)
    assert got["supported"] is False
    assert "REFUTED" in got["verdict"]


def test_the_pooled_ratio_is_marked_as_confounded():
    """Sensitivity and natural variability both fall with depth, so "below the floor" is mostly
    "deep". The pooled number must never be presented as the test."""
    got = _join_case(0.5, 1.5)
    assert got["pooled_ratio_is_confounded_by_depth"] is True
    assert got["n_testable_depths"] >= 1


def test_join_is_untestable_when_no_depth_has_both_groups():
    """Every profile sharing one floor at the bottom means no depth has profiles on both sides.
    That is 'we could not test this', which must not be reported as a pass or a failure."""
    n = 50
    E = np.ones((n, c2.N_DEPTHS))
    got = OB.residual_vs_information(E, np.full(n, 1000.0))
    assert got["supported"] is None
    assert "UNTESTABLE" in got["verdict"]
