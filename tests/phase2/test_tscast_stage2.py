"""Stage 2: salinity head + the paper's eq. 5 density constraint.

The two things these tests exist to stop:
  1. Stage 1 quietly changing. The shipped 0.8612 degC rests on that architecture, so stage 2 must
     be additive -- a stage-1 model built today has to be identical to one built before stage 2.
  2. The density term being fed z-scores. EOS-80 is a polynomial in degC and PSS-78; hand it
     z-scored inputs and it returns a number with no physical meaning that back-propagates
     perfectly happily. Nothing crashes, and the "physics" term is then noise.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from oceanembed import config as base
from phase2.physics import seawater as sw
from phase2.tscast_nio import config as vcfg
from phase2.tscast_nio import dataset as D
from phase2.tscast_nio.models.tscast import TSCastNIO, density_nll


# ── the equation of state has ONE definition, used by two backends ─────────────────────

def test_torch_density_is_the_same_polynomial_as_numpy():
    rng = np.random.default_rng(0)
    S = rng.uniform(30.0, 38.0, 500)
    T = rng.uniform(2.0, 32.0, 500)
    npy = sw.density(S, T)
    tor = sw.density_torch(torch.tensor(S, dtype=torch.float64),
                           torch.tensor(T, dtype=torch.float64)).numpy()
    assert np.max(np.abs(npy - tor)) == 0.0, (
        "the two backends have drifted; they must share _density_core, not two transcriptions")


def test_torch_density_still_reproduces_the_published_unesco_value():
    """1023.343 kg m-3 at S=35, t=25 is the classic UNESCO (1983) check value."""
    v = float(sw.density_torch(torch.tensor(35.0, dtype=torch.float64),
                               torch.tensor(25.0, dtype=torch.float64)))
    assert abs(v - 1023.343) < 1e-3, v


def test_density_gradients_reach_both_inputs():
    """eq. 5 only constrains anything if gradients flow back into BOTH heads."""
    S = torch.tensor([35.0], dtype=torch.float64, requires_grad=True)
    T = torch.tensor([25.0], dtype=torch.float64, requires_grad=True)
    sw.density_torch(S, T).sum().backward()
    assert S.grad is not None and abs(float(S.grad)) > 1e-6
    assert T.grad is not None and abs(float(T.grad)) > 1e-6


def test_negative_salinity_is_nan_not_a_number():
    """S**1.5 must not silently produce a density for unphysical salinity."""
    assert np.isnan(float(sw.density_torch(torch.tensor(-1.0, dtype=torch.float64),
                                           torch.tensor(20.0, dtype=torch.float64))))


# ── stage 1 must be untouched ──────────────────────────────────────────────────────────

def _stage1():
    return TSCastNIO("cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="simple", stage=1)


def test_stage1_is_the_default_and_returns_two_outputs():
    m = _stage1()
    assert m.stage == 1
    assert TSCastNIO("cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="simple").stage == 1
    out = m(torch.zeros(2, 7, 1, vcfg.P, vcfg.P), torch.zeros(2, 3, 1, vcfg.P, vcfg.P),
            torch.zeros(2, 12, base.N_DEPTHS), torch.zeros(2, dtype=torch.long))
    assert len(out) == 2


def test_stage1_head_width_is_unchanged():
    """2 * 15 outputs. If this grew, every stage-1 checkpoint stops loading."""
    m = _stage1()
    assert m.simple_head[-1].out_features == 2 * base.N_DEPTHS


def test_the_shipped_stage1_checkpoint_still_loads():
    import os

    ck = base.art("tscast_stage1.pt")
    if not os.path.exists(ck):
        pytest.skip("no stage-1 checkpoint on this machine")
    blob = torch.load(ck, map_location="cpu", weights_only=False)
    saved = blob["state_dict"]

    # Channel count and latent width come from the CHECKPOINT, not from a literal. Hardcoding 7
    # made this fail on any 5-channel stage-1 run for a reason that has nothing to do with what
    # the test is for -- and a backward-compatibility check that fails for the wrong reason gets
    # deleted or skipped, which is how it stopped running in the first place.
    c_in = len(blob["channels"])
    latent = int(blob.get("latent", 128))
    m = TSCastNIO("cnn3d", c_in, t_seq=1, p=int(blob.get("P", vcfg.P)), latent=latent,
                  decoder="simple", stage=1)
    m.load_state_dict(saved)          # raises if stage 2 changed stage 1's parameter shapes


# ── stage 2 heads ──────────────────────────────────────────────────────────────────────

def _stage2():
    return TSCastNIO("cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="simple", stage=2)


def test_stage2_returns_five_heads_of_fifteen_depths():
    out = _stage2()(torch.zeros(2, 7, 1, vcfg.P, vcfg.P), torch.zeros(2, 3, 1, vcfg.P, vcfg.P),
                    torch.zeros(2, 12, base.N_DEPTHS), torch.zeros(2, dtype=torch.long))
    assert len(out) == 5, "expect mu_T, logvar_T, mu_S, logvar_S, logvar_rho"
    for o in out:
        assert o.shape == (2, base.N_DEPTHS)


def test_density_variance_is_its_own_head_not_derived():
    """The paper is explicit (2.3.4): T/S error covariance is non-negligible, so sigma_rho is
    predicted, not propagated. A derived sigma_rho would be a deterministic function of the other
    two; this shows it is free to differ."""
    m = _stage2()
    torch.manual_seed(0)
    x = torch.randn(8, 7, 1, vcfg.P, vcfg.P)
    _, lv_t, _, lv_s, lv_rho = m(x, torch.zeros(8, 3, 1, vcfg.P, vcfg.P),
                                 torch.zeros(8, 12, base.N_DEPTHS), torch.zeros(8, dtype=torch.long))
    assert not torch.allclose(lv_rho, lv_t) and not torch.allclose(lv_rho, lv_s)


def test_stage2_refuses_the_film_decoder_rather_than_shipping_an_untested_path():
    with pytest.raises(NotImplementedError, match="simple"):
        TSCastNIO("cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="film", stage=2)


def test_an_invalid_stage_is_refused():
    with pytest.raises(ValueError, match="stage must be 1 or 2"):
        TSCastNIO("cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="simple", stage=3)


# ── eq. 5 itself ───────────────────────────────────────────────────────────────────────

def _norm():
    n = base.N_DEPTHS
    return (torch.full((n,), 20.0), torch.full((n,), 6.0),      # y_mean, y_std   (degC)
            torch.full((n,), 35.0), torch.full((n,), 0.5))      # s_mean, s_std   (psu)


def test_a_perfect_prediction_costs_only_the_log_variance_term():
    n = base.N_DEPTHS
    ym, ys, sm, ss = _norm()
    z = torch.zeros(4, n)
    L = density_nll(z, z, torch.zeros(4, n), z, z, torch.ones(4, n, dtype=torch.bool),
                    ym, ys, sm, ss, beta=0.0)
    assert abs(float(L)) < 1e-6, "rho_pred == rho_true, and 0.5*logvar is 0 at logvar=0"


def test_a_wrong_prediction_costs_more_than_a_right_one():
    n = base.N_DEPTHS
    ym, ys, sm, ss = _norm()
    z, lv, mk = torch.zeros(4, n), torch.zeros(4, n), torch.ones(4, n, dtype=torch.bool)
    good = float(density_nll(z, z, lv, z, z, mk, ym, ys, sm, ss))
    warm = float(density_nll(torch.full((4, n), 0.5), z, lv, z, z, mk, ym, ys, sm, ss))
    salty = float(density_nll(z, torch.full((4, n), 0.5), lv, z, z, mk, ym, ys, sm, ss))
    assert warm > good and salty > good


def test_the_density_term_uses_physical_units_not_z_scores():
    """The bug with no symptom. Feeding z-scores to EOS-80 returns a finite, differentiable number.

    Scaling y_std/s_std changes what the same z-scored error MEANS in degC and psu, so a term that
    truly de-normalises must respond to that. One that skipped it would return the same loss.
    """
    n = base.N_DEPTHS
    z, lv, mk = torch.zeros(4, n), torch.zeros(4, n), torch.ones(4, n, dtype=torch.bool)
    err = torch.full((4, n), 0.5)
    ym, sm = torch.full((n,), 20.0), torch.full((n,), 35.0)

    narrow = float(density_nll(err, z, lv, z, z, mk, ym, torch.full((n,), 1.0), sm,
                               torch.full((n,), 0.5)))
    wide = float(density_nll(err, z, lv, z, z, mk, ym, torch.full((n,), 6.0), sm,
                             torch.full((n,), 0.5)))
    assert wide > narrow * 2, (
        f"the same z-scored error gave {narrow:.4f} at y_std=1 and {wide:.4f} at y_std=6. "
        "If these were close, the term is being evaluated on z-scores and is not physics.")


def test_masked_levels_contribute_nothing_not_zero():
    n = base.N_DEPTHS
    ym, ys, sm, ss = _norm()
    z, lv = torch.zeros(4, n), torch.zeros(4, n)
    err = torch.full((4, n), 0.5)
    full = torch.ones(4, n, dtype=torch.bool)
    half = full.clone()
    half[:, n // 2:] = False
    # masking out half the levels must not halve the MEAN -- the denominator moves too
    assert abs(float(density_nll(err, z, lv, z, z, full, ym, ys, sm, ss))
               - float(density_nll(err, z, lv, z, z, half, ym, ys, sm, ss))) < 1e-5


def test_a_negative_salinity_prediction_does_not_poison_the_batch():
    """An untrained salinity head emits negatives. S**1.5 is NaN there, and one NaN destroys every
    gradient in the batch, not just its own element."""
    n = base.N_DEPTHS
    ym, ys, sm, ss = _norm()
    very_negative = torch.full((4, n), -200.0, requires_grad=True)   # ~ -65 psu before the clamp
    L = density_nll(torch.zeros(4, n), very_negative, torch.zeros(4, n),
                    torch.zeros(4, n), torch.zeros(4, n), torch.ones(4, n, dtype=torch.bool),
                    ym, ys, sm, ss)
    assert torch.isfinite(L), "eq. 5 returned NaN for a negative salinity prediction"
    L.backward()
    assert torch.isfinite(very_negative.grad).all()


# ── the dataset's salinity target ──────────────────────────────────────────────────────

def _fake_bundle(n_t=6):
    rng = np.random.default_rng(0)
    nlat, nlon, nd = 8, 9, base.N_DEPTHS
    surface = rng.normal(size=(n_t, nlat, nlon, 5)).astype("float32")
    temp = rng.normal(20.0, 5.0, (n_t, nlat, nlon, nd)).astype("float32")
    sal = rng.normal(35.0, 0.6, (n_t, nlat, nlon, nd)).astype("float32")
    times = np.arange(np.datetime64("2025-06-01"), np.datetime64("2025-06-01") + n_t,
                      dtype="datetime64[D]")
    land = np.zeros((nlat, nlon), dtype=bool)
    clim = rng.normal(20.0, 5.0, (12, nlat, nlon, nd)).astype("float32")
    return surface, temp, sal, times, land, clim


def test_dataset_returns_salinity_only_when_asked():
    surface, temp, sal, times, land, clim = _fake_bundle()
    kw = dict(t_indices=np.arange(len(times)), t_seq=1, p=3, clim=clim, return_clim=True)
    plain = D.GriddedPatches(surface, temp, times, land, list("abcde"), **kw)
    assert len(plain[0]) == 7, "the stage-1 tuple must not grow"

    with_s = D.GriddedPatches(surface, temp, times, land, list("abcde"),
                              salinity=sal, return_salinity=True, **kw)
    sample = with_s[0]
    assert len(sample) == 9, "salinity and its validity mask are appended, in that order"
    assert sample[7].shape == (base.N_DEPTHS,) and sample[8].dtype == torch.bool


def test_salinity_is_z_scored_with_its_own_statistics():
    """Sharing temperature's mean/std would be a silent ~20x error of the D-014 kind."""
    surface, temp, sal, times, land, clim = _fake_bundle()
    ds = D.GriddedPatches(surface, temp, times, land, list("abcde"),
                          t_indices=np.arange(len(times)), t_seq=1, p=3, clim=clim,
                          return_clim=True, salinity=sal, return_salinity=True)
    assert len(ds.norm) == 6
    assert 30.0 < float(np.mean(ds.s_mean)) < 40.0, "s_mean is not in psu"
    assert not np.allclose(ds.s_mean, ds.y_mean)
    s_z = ds[0][7].numpy()
    assert abs(float(np.mean(s_z))) < 6.0, "z-scored salinity should be O(1), not O(35)"


def test_returning_salinity_without_a_salinity_array_is_refused():
    surface, temp, sal, times, land, clim = _fake_bundle()
    with pytest.raises(ValueError, match="refusing to train a salinity head"):
        D.GriddedPatches(surface, temp, times, land, list("abcde"),
                         t_indices=np.arange(len(times)), t_seq=1, p=3, clim=clim,
                         return_clim=True, return_salinity=True)


def test_a_stage1_norm_tuple_cannot_be_used_to_scale_salinity():
    surface, temp, sal, times, land, clim = _fake_bundle()
    stage1_norm = D.GriddedPatches(surface, temp, times, land, list("abcde"),
                                   t_indices=np.arange(len(times)), t_seq=1, p=3,
                                   clim=clim, return_clim=True).norm
    assert len(stage1_norm) == 4
    with pytest.raises(ValueError, match="4-entry stage-1 tuple|20x"):
        D.GriddedPatches(surface, temp, times, land, list("abcde"),
                         t_indices=np.arange(len(times)), norm=stage1_norm, t_seq=1, p=3,
                         clim=clim, return_clim=True, salinity=sal, return_salinity=True)


def test_a_stage1_norm_tuple_still_works_for_stage1():
    """Stage-1 checkpoints carry a 4-entry norm and must keep loading."""
    surface, temp, sal, times, land, clim = _fake_bundle()
    n4 = D.GriddedPatches(surface, temp, times, land, list("abcde"),
                          t_indices=np.arange(len(times)), t_seq=1, p=3,
                          clim=clim, return_clim=True).norm
    ds = D.GriddedPatches(surface, temp, times, land, list("abcde"),
                          t_indices=np.arange(len(times)), norm=n4, t_seq=1, p=3,
                          clim=clim, return_clim=True)
    assert len(ds[0]) == 7 and ds.s_mean is None


# ── the trained stage-2 model, if one exists on this machine ───────────────────────────

def _stage2_record():
    import os

    ck = base.art("tscast_stage2_s2.pt")
    if not os.path.exists(ck):
        pytest.skip("no stage-2 checkpoint on this machine")
    from phase2.tscast_nio.inference import TSCastPredictor

    return TSCastPredictor(checkpoint=ck).reconstruct(15.0, 68.0, "2026-05-15")


def test_a_stage2_record_carries_salinity_and_density():
    r = _stage2_record()
    for k in ("salinity", "log_var_s", "sigma_s", "density", "log_var_rho", "sigma_rho"):
        assert r[k] is not None, f"{k} is still None on a stage-2 checkpoint"
        assert len(r[k]) == base.N_DEPTHS
    assert r["provenance"]["stage"] == 2
    assert "EOS-80" in r["provenance"]["eos"]


def test_predicted_density_increases_with_depth_below_the_mixed_layer():
    """Stable stratification, tested where stratification actually exists.

    Nothing in the loss guarantees monotonic density, so this is a real check that the T and S
    heads agree with each other rather than a tautology.

    But it is deliberately NOT applied in the top 50 m. The mixed layer is by definition
    near-uniform in density -- de Boyer Montegut et al. (2004) define its base as the depth where
    density has changed by only 0.03 kg m-3 -- so ordering within it is not physically meaningful.
    MEASURED across five profiles: every inversion this model produces sits at 5 or 10 m and is at
    most 0.068 kg m-3, against a predicted sigma_rho of ~0.17 kg m-3 at those depths. That is
    inside its own stated uncertainty, and the surface test below holds it to exactly that.
    """
    r = _stage2_record()
    depths = r["depths_m"]
    deep = [(d, v) for d, v in zip(depths, r["density"]) if v is not None and d >= 50]
    assert len(deep) >= 8, "not enough depths below the mixed layer to test stratification"
    vals = [v for _, v in deep]
    diffs = np.diff(vals)
    assert (diffs >= -1e-6).all(), (
        f"density inverts BELOW the mixed layer, at {deep[int(np.argmin(diffs))][0]} m: {vals}. "
        f"Below 50 m the water column is stratified, so this means the temperature and salinity "
        f"predictions genuinely disagree with each other there.")


def test_any_near_surface_density_inversion_stays_inside_the_models_own_error_bar():
    """The mixed layer may invert slightly; it may not invert by more than the model admits to."""
    r = _stage2_record()
    depths, rho, sig = r["depths_m"], r["density"], r["sigma_rho"]
    for k in range(1, len(depths)):
        if depths[k] > 50 or rho[k] is None or rho[k - 1] is None:
            continue
        step = rho[k] - rho[k - 1]
        if step >= 0:
            continue
        tol = max(sig[k] or 0.0, sig[k - 1] or 0.0)
        assert abs(step) <= tol + 1e-9, (
            f"density falls {abs(step):.4f} kg m-3 between {depths[k - 1]} and {depths[k]} m, "
            f"more than the predicted sigma_rho of {tol:.4f} there. An inversion the model does "
            f"not admit to is a real inconsistency between the T and S heads.")


def test_predicted_density_is_in_the_right_physical_range():
    r = _stage2_record()
    rho = [v for v in r["density"] if v is not None]
    assert 1015.0 < min(rho) < 1030.0, f"surface density {min(rho)} is not seawater"
    assert 1020.0 < max(rho) < 1035.0, f"deep density {max(rho)} is not seawater"


def test_density_is_exactly_eos80_of_the_reported_t_and_s():
    """Density must never be an independent third opinion -- it is a function of the other two."""
    r = _stage2_record()
    for k in range(base.N_DEPTHS):
        t, s, rho = r["temperature"][k], r["salinity"][k], r["density"][k]
        if t is None or s is None or rho is None:
            continue
        assert abs(float(sw.density(s, t)) - rho) < 5e-3, (
            f"at {r['depths_m'][k]} m the reported density {rho} is not EOS-80({s}, {t})")


# ===================================================================================
# eq. 5 tests that actually exercise eq. 5.
#
# The density tests above all pass logvar = zeros and beta = 0. At logvar=0,
# 0.5*exp(-logvar) == 0.5 and 0.5*logvar == 0 -- so DELETING the 0.5*log(sigma^2) term,
# DELETING the 1/(2 sigma^2) weighting, or breaking the beta path leaves every one of them
# green. These use non-uniform nonzero logvar so each piece of the formula is load-bearing.
# ===================================================================================

def _eq5_reference(mu_t, mu_s, lv, y_t, y_s, mask, y_mean, y_std, s_mean, s_std, beta=0.0):
    """Independent hand-written eq. 5, from the paper rather than from the implementation."""
    from phase2.physics import seawater as sw
    tp = mu_t.double() * y_std + y_mean
    sp = np.clip((mu_s.double() * s_std + s_mean).numpy(), 1e-3, None)
    tt = y_t.double() * y_std + y_mean
    st = np.clip((y_s.double() * s_std + s_mean).numpy(), 1e-3, None)
    rp = sw.density(sp, tp.numpy())
    rt = sw.density(st, tt.numpy())
    lvd = lv.double().numpy()
    per = 0.5 * np.exp(-lvd) * (rt - rp) ** 2 + 0.5 * lvd
    if beta:
        per = per * (np.exp(lvd) ** beta)
    m = mask.double().numpy()
    return float((per * m).sum() / max(m.sum(), 1.0))


@pytest.mark.parametrize("beta", [0.0, 0.5, 1.0])
def test_density_nll_matches_a_hand_written_eq5_with_NONZERO_logvar(beta):
    """Every term live: non-uniform logvar, a real residual, and each beta setting."""
    torch.manual_seed(3)
    n = vcfg.N_DEPTHS
    # float64 throughout: the reference is computed in double, and comparing it against a float32
    # forward pass leaves a 3e-5 relative gap that is precision, not a formula error. Matching the
    # dtype makes the assertion about eq. 5 rather than about rounding.
    mu_t = (torch.randn(4, n) * 0.3).double()
    mu_s = (torch.randn(4, n) * 0.3).double()
    y_t = mu_t + torch.randn(4, n).double() * 0.2   # nonzero residual, so the weighting matters
    y_s = mu_s + torch.randn(4, n).double() * 0.2
    lv = torch.linspace(-1.5, 1.5, n).repeat(4, 1).double()   # NON-UNIFORM and nonzero
    mask = torch.ones(4, n, dtype=torch.bool)
    y_mean, y_std, s_mean, s_std = 20.0, 5.0, 35.0, 1.5

    got = float(density_nll(mu_t, mu_s, lv, y_t, y_s, mask,
                              y_mean, y_std, s_mean, s_std, beta=beta))
    want = _eq5_reference(mu_t, mu_s, lv, y_t, y_s, mask,
                          y_mean, y_std, s_mean, s_std, beta=beta)
    assert got == pytest.approx(want, rel=1e-9), f"beta={beta}: {got} vs {want}"


def test_the_half_log_sigma_squared_term_is_actually_present():
    """A perfect prediction should cost EXACTLY mean(0.5*logvar), not zero. The existing test
    asserts |L| < 1e-6 at logvar=0, which a density_nll with the log term deleted also returns."""
    n = vcfg.N_DEPTHS
    mu_t = torch.randn(2, n) * 0.2
    mu_s = torch.randn(2, n) * 0.2
    lv = torch.full((2, n), 1.4)                  # sigma^2 = e^1.4, so the term is 0.7
    mask = torch.ones(2, n, dtype=torch.bool)
    L = float(density_nll(mu_t, mu_s, lv, mu_t, mu_s, mask, 20.0, 5.0, 35.0, 1.5))
    assert L == pytest.approx(0.7, abs=1e-4), (
        f"zero-residual loss is {L}, expected mean(0.5*logvar)=0.7. A missing log term gives 0.0.")


def test_the_inverse_variance_weighting_is_actually_present():
    """Doubling sigma^2 must QUARTER the squared-error contribution. Invisible at logvar=0."""
    n = vcfg.N_DEPTHS
    mu_t = torch.zeros(2, n)
    mu_s = torch.zeros(2, n)
    y_t = torch.full((2, n), 0.4)                 # a real residual
    y_s = torch.zeros(2, n)
    mask = torch.ones(2, n, dtype=torch.bool)
    args = (20.0, 5.0, 35.0, 1.5)

    lo = torch.zeros(2, n)
    hi = torch.full((2, n), float(np.log(4.0)))   # sigma^2 x4
    L_lo = float(density_nll(mu_t, mu_s, lo, y_t, y_s, mask, *args)) - 0.0
    L_hi = float(density_nll(mu_t, mu_s, hi, y_t, y_s, mask, *args)) - 0.5 * float(np.log(4.0))
    assert L_hi == pytest.approx(L_lo / 4.0, rel=1e-4), (
        f"error term {L_hi} is not a quarter of {L_lo}; the 1/(2 sigma^2) weighting is missing")


def test_the_beta_weight_equals_exp_logvar_to_the_beta():
    """beta must multiply by a DETACHED sigma^(2 beta), not by anything else."""
    n = vcfg.N_DEPTHS
    mu_t = torch.randn(3, n) * 0.2
    mu_s = torch.randn(3, n) * 0.2
    y_t = mu_t + 0.3
    y_s = mu_s + 0.1
    mask = torch.ones(3, n, dtype=torch.bool)
    args = (20.0, 5.0, 35.0, 1.5)
    lv = torch.full((3, n), 0.8)                  # uniform, so the weight factors out exactly

    base_L = float(density_nll(mu_t, mu_s, lv, y_t, y_s, mask, *args, beta=0.0))
    for b in (0.5, 1.0):
        got = float(density_nll(mu_t, mu_s, lv, y_t, y_s, mask, *args, beta=b))
        assert got == pytest.approx(base_L * float(np.exp(0.8)) ** b, rel=1e-5), f"beta={b}"


def test_sigma_rho_is_not_any_analytic_propagation_of_sigma_T_and_sigma_S():
    """The existing test asserts only non-equality on a random init -- an analytic propagation
    would also be unequal and pass. This pins the stronger property: sigma_rho responds to its
    OWN slice of the head and is unmoved when only the T and S variance slices change."""
    torch.manual_seed(11)
    m = TSCastNIO("cnn3d", 5, t_seq=1, p=vcfg.P, latent=64, decoder="simple", stage=2).eval()
    x = torch.randn(2, 5, 1, vcfg.P, vcfg.P)
    g = torch.randn(2, 3, 1, vcfg.P, vcfg.P)
    cp = torch.randn(2, 12, vcfg.N_DEPTHS)
    mo = torch.randint(0, 12, (2,))

    with torch.no_grad():
        out = m(x, g, cp, mo)
        lv_rho_before = out[4].clone()
        # perturb ONLY the rows of the head that produce log_var_t and log_var_s
        w = m.simple_head[-1].weight
        n = vcfg.N_DEPTHS
        w[2 * n:4 * n] += torch.randn_like(w[2 * n:4 * n])
        lv_rho_after = m(x, g, cp, mo)[4]

    assert torch.allclose(lv_rho_before, lv_rho_after, atol=1e-6), (
        "log_var_rho moved when only the T/S variance rows changed -- it is not its own head")


# ── ported from the deleted eos.py suite: end-member range, float32, clamp reporting ──

def test_density_torch_matches_numpy_across_the_BASIN_END_MEMBERS():
    """The shipped test pins S 30-38, T 2-32. This basin goes well outside that: the Ganges /
    Meghna plume reaches 0.50 psu and the Persian Gulf 40.17 -- both MEASURED in the daily
    bundle, not assumed. A polynomial agreeing on the open ocean and diverging in a river plume
    would never be caught by a mid-range test."""
    s = np.linspace(0.5, 40.2, 60)
    t = np.linspace(1.0, 36.4, 60)
    S, T_ = np.meshgrid(s, t)
    ref = sw.density(S, T_)
    got = sw.density_torch(torch.tensor(S), torch.tensor(T_)).numpy()
    err = np.abs(got - ref).max()
    assert err < 1e-9, f"backends diverge by {err:.3e} kg m-3 at the basin end members"


def test_density_torch_in_float32_stays_inside_the_EOS80_fit_error():
    """The model runs in float32, so eq. 5 computes density in float32. A constraint term only
    means something if its own numerical error is small beside the physics it enforces: EOS-80's
    published standard error is 3.6e-3 kg m-3 (UNESCO 1983)."""
    s = np.linspace(0.5, 40.2, 40)
    t = np.linspace(1.0, 36.4, 40)
    S, T_ = np.meshgrid(s, t)
    ref = sw.density(S, T_)
    got32 = sw.density_torch(torch.tensor(S, dtype=torch.float32),
                             torch.tensor(T_, dtype=torch.float32)).double().numpy()
    err = np.abs(got32 - ref).max()
    assert err < 3.6e-3, f"float32 error {err:.2e} exceeds EOS-80's own fit error"


def test_negative_predicted_salinity_is_COUNTED_not_silently_clamped():
    """The clamp is necessary (S**1.5 on a negative base is NaN) but not free: it zeroes the
    gradient exactly, so L_rho cannot push a negative salinity back into range -- only L_S can.
    A density term training against a pinned input is doing nothing, and the count is the only
    way to see it."""
    n = vcfg.N_DEPTHS
    mask = torch.ones(2, n, dtype=torch.bool)
    lv = torch.zeros(2, n)

    ok = torch.zeros(2, n)                                   # s = s_mean = 35 psu, all fine
    density_nll(torch.zeros(2, n), ok, lv, torch.zeros(2, n), ok, mask, 20.0, 5.0, 35.0, 1.5)
    assert density_nll.last_n_clamped == 0

    bad = torch.full((2, n), -40.0)                          # 35 + (-40 * 1.5) < 0 everywhere
    density_nll(torch.zeros(2, n), bad, lv, torch.zeros(2, n), ok, mask, 20.0, 5.0, 35.0, 1.5)
    assert density_nll.last_n_clamped == 2 * n, density_nll.last_n_clamped


def test_the_clamp_really_does_kill_the_salinity_gradient():
    """Pins the measured behaviour the counter exists to warn about."""
    n = vcfg.N_DEPTHS
    mask = torch.ones(1, n, dtype=torch.bool)
    mu_t = torch.zeros(1, n, requires_grad=True)
    mu_s = torch.full((1, n), -40.0, requires_grad=True)     # clamped everywhere
    L = density_nll(mu_t, mu_s, torch.zeros(1, n), torch.zeros(1, n), torch.zeros(1, n),
                    mask, 20.0, 5.0, 35.0, 1.5)
    L.backward()
    assert float(mu_s.grad.abs().sum()) == 0.0, "clamped salinity should carry no gradient"
    assert float(mu_t.grad.abs().sum()) > 0.0, "temperature must still receive one"
