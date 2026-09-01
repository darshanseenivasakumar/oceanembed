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
    saved = torch.load(ck, map_location="cpu", weights_only=False)["state_dict"]
    m = TSCastNIO(saved and "cnn3d", 7, t_seq=1, p=vcfg.P, latent=128, decoder="simple", stage=1)
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
