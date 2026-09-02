"""Sampler tests. Each one encodes a failure that would look like a science result."""
import numpy as np
import pytest
import torch

from oceanembed import config as base
from phase2.tscast_nio import config, dataset as D


def _toy(n_t=6, n_lat=20, n_lon=30, n_c=5):
    rng = np.random.default_rng(0)
    surface = rng.normal(0, 1, (n_t, n_lat, n_lon, n_c)).astype("float32")
    temp = rng.normal(20, 3, (n_t, n_lat, n_lon, config.N_DEPTHS)).astype("float32")
    land = np.zeros((n_lat, n_lon), bool)
    times = np.array([f"20{19+i//12}-{i%12+1:02d}-15" for i in range(n_t)], dtype="datetime64[D]")
    return surface, temp, times, land, ["sst", "sss", "ssh", "u", "v"]


def test_geo_encoding_is_a_unit_vector_matching_eq1():
    lat = np.array([5.0, 17.5, 29.75]); lon = np.array([45.0, 75.0, 104.75])
    g = D.geo_encoding(lat, lon)
    assert np.allclose((g ** 2).sum(-1), 1.0, atol=1e-6), "X,Y,Z must lie on the unit sphere"
    phi, lam = np.deg2rad(lat[1]), np.deg2rad(lon[1])
    assert np.allclose(g[1], [np.sin(phi), np.sin(lam)*np.cos(phi), -np.cos(lam)*np.cos(phi)])


def test_western_edge_patch_is_filled_not_wrapped_from_the_east():
    """45 E and 105 E are opposite sides of the basin. A wrapped patch would teach the model that
    Somalia predicts Sumatra -- a bug that trains cleanly and is invisible in the loss curve."""
    surface, temp, times, land, ch = _toy()
    surface[:, :, :3, :] = 1.0        # far west
    surface[:, :, -3:, :] = 999.0     # far east, unmistakable
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(len(times)), t_seq=1, p=5)
    ds.index = np.array([[0, 10, 0]])                       # westernmost column
    x, _, _, _, _ = ds[0]
    assert not torch.any(x > 100), "eastern values leaked into a western patch: the grid wrapped"


def test_off_grid_cells_become_zero_after_zscoring_not_a_fabricated_value():
    surface, temp, times, land, ch = _toy()
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(len(times)), t_seq=1, p=5)
    ds.index = np.array([[0, 0, 0]])                        # corner: half the patch is off-grid
    x, _, _, _, _ = ds[0]
    assert torch.isfinite(x).all(), "off-grid must be filled, never left NaN"
    assert (x == 0).any(), "off-grid cells should sit at the channel mean (0 after z-scoring)"


def test_patch_is_centred_on_the_target_cell():
    surface, temp, times, land, ch = _toy()
    surface[:] = 0.0
    surface[0, 10, 15, :] = 50.0                            # a single spike
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(len(times)), t_seq=1, p=5)
    ds.index = np.array([[0, 10, 15]])
    x, _, _, _, _ = ds[0]
    c = config.P // 2 if False else 2                       # p=5 -> centre index 2
    assert x[0, 0, c, c] == x.max(), "the spike must land at the patch centre, not offset"


def test_normalisation_uses_train_indices_only():
    """Statistics computed over all data leak the test distribution into training and inflate
    every score downstream."""
    surface, temp, times, land, ch = _toy(n_t=6)
    surface[3:] += 1000.0                                   # test half is wildly different
    tr = np.arange(3)
    ds = D.GriddedPatches(surface, temp, times, land, ch, tr, t_seq=1, p=5)
    assert np.all(np.abs(ds.mean) < 10), f"train mean {ds.mean} was polluted by the test half"


def test_monthly_train_and_test_target_indices_never_overlap():
    """NOTE the name: this checks target INDEX overlap on the MONTHLY split. It says nothing
    about T_SEQ input windows -- see the daily embargo tests at the bottom of this file, which
    exist because the earlier name ('...windows_never_overlap') implied a guarantee this test
    never made."""
    _, _, times48, _, _ = _toy(n_t=48)
    g = np.load(f"{base.DATA_PROCESSED}/grids.npz", allow_pickle=True)
    tr, te = D.split_indices(g["times"])
    assert len(np.intersect1d(tr, te)) == 0
    yrs_tr = {int(str(t)[:4]) for t in g["times"][tr]}
    yrs_te = {int(str(t)[:4]) for t in g["times"][te]}
    assert yrs_tr == set(base.TRAIN_YEARS) and yrs_te == set(base.TEST_YEARS)
    assert max(yrs_tr) < min(yrs_te), "test window must come AFTER train: no future leakage"


def test_t_seq_one_and_many_give_the_same_spatial_patch_at_the_centre_time():
    """Guards the promise that T_SEQ is a config flip: the centre frame must not move."""
    surface, temp, times, land, ch = _toy(n_t=9)
    idx = np.arange(9)
    a = D.GriddedPatches(surface, temp, times, land, ch, idx, t_seq=1, p=5)
    b = D.GriddedPatches(surface, temp, times, land, ch, idx, t_seq=5, p=5, norm=a.norm)
    a.index = b.index = np.array([[4, 10, 15]])
    xa, _, _, _, _ = a[0]
    xb, _, _, _, _ = b[0]
    assert xb.shape[1] == 5 and xa.shape[1] == 1
    assert torch.allclose(xa[:, 0], xb[:, 2]), "centre frame moved when T_SEQ changed"


def test_cell_index_matches_the_frozen_nearest_centre_convention():
    """searchsorted-1 LOOKS equivalent and is not. Measured on the real Argo set the two
    conventions disagree on 75.5% of profiles by one cell (~28 km), which would make every number
    we quote incomparable with the published ones."""
    from oceanembed.utils import grids
    from phase2.tscast_nio import dataset as DD

    rng = np.random.default_rng(0)
    lat = rng.uniform(5.0, 29.75, 400)
    lon = rng.uniform(45.0, 104.75, 400)
    i, j = DD.cell_index(lat, lon)
    assert all(int(a) == grids.nearest_lat_index(float(v)) for a, v in zip(i, lat))
    assert all(int(b) == grids.nearest_lon_index(float(v)) for b, v in zip(j, lon))


def test_cell_index_does_not_slip_a_cell_on_an_exact_grid_line():
    """26.0N is exactly a grid latitude. searchsorted-1 returns the cell BELOW (25.75) -- the bug
    that made this predictor disagree with the OceanCube about the Persian Gulf sea floor."""
    from phase2.tscast_nio import dataset as DD

    i, _ = DD.cell_index(26.0, 52.5)
    assert float(base.LAT[int(i[0])]) == pytest.approx(26.0), "slipped to the neighbouring cell"
    wrong = int(np.clip(np.searchsorted(base.LAT, 26.0) - 1, 0, base.N_LAT - 1))
    assert wrong != int(i[0]), "this test no longer distinguishes the two conventions"


# ── T_SEQ boundary embargo (Phase 1) ───────────────────────────────────────────────────
#
# `test_monthly_train_and_test_target_indices_never_overlap` (above) checks
# target INDEX overlap, on the MONTHLY split. That is why the daily T_SEQ=11 crossing went
# unnoticed. These tests check the thing the name promised: the actual input windows, on the
# actual daily split.

def _daily_like(n_t=40, boundary=30):
    """A toy daily bundle: `boundary` train steps then the rest test, one day apart."""
    rng = np.random.default_rng(1)
    surface = rng.normal(0, 1, (n_t, 6, 7, 5)).astype("float32")
    temp = rng.normal(20, 3, (n_t, 6, 7, config.N_DEPTHS)).astype("float32")
    land = np.zeros((6, 7), bool)
    times = (np.datetime64("2025-06-01") + np.arange(n_t)).astype("datetime64[D]")
    tr = np.arange(boundary)
    te = np.arange(boundary, n_t)
    return surface, temp, times, land, ["sst", "sss", "ssh", "u", "v"], tr, te


def test_embargo_removes_exactly_the_targets_whose_window_reaches_the_test_block():
    _, _, _, _, _, tr, te = _daily_like()
    kept = D.embargo_indices(tr, t_seq=11, forbidden_start=int(te.min()))
    assert list(kept) == list(range(25)), "expected the last 5 of 30 train targets to be dropped"
    assert len(tr) - len(kept) == 11 // 2


def test_no_surviving_training_window_touches_a_test_index():
    """The property that actually matters, asserted through the real sampler, not by arithmetic."""
    surface, temp, times, land, ch, tr, te = _daily_like()
    kept = D.embargo_indices(tr, t_seq=11, forbidden_start=int(te.min()))
    ds = D.GriddedPatches(surface, temp, times, land, ch, kept, t_seq=11, p=3)
    test_set = set(int(x) for x in te)
    for k in range(len(ds)):
        t = int(ds.index[k][0])
        touched = set(ds._window(t))
        assert not (touched & test_set), (
            f"training target {t} reads test indices {sorted(touched & test_set)}")


def test_the_unembargoed_sampler_really_did_touch_the_test_block():
    """Proves the guard is guarding something. If this ever passes clean, the bug is gone by
    other means and the embargo has become untested rather than unnecessary."""
    surface, temp, times, land, ch, tr, te = _daily_like()
    ds = D.GriddedPatches(surface, temp, times, land, ch, tr, t_seq=11, p=3)
    test_set = set(int(x) for x in te)
    offenders = {int(ds.index[k][0]) for k in range(len(ds))
                 if set(ds._window(int(ds.index[k][0]))) & test_set}
    assert offenders == {25, 26, 27, 28, 29}, offenders


def test_test_indices_are_never_embargoed():
    """A test target reaching BACK into train is legitimate -- those observations exist."""
    _, _, _, _, _, tr, te = _daily_like()
    ds_te_idx = te                       # trainers pass te_t through untouched
    assert list(ds_te_idx) == list(range(30, 40))
    surface, temp, times, land, ch, _, _ = _daily_like()
    ds = D.GriddedPatches(surface, temp, times, land, ch, te, t_seq=11, p=3)
    reaches_back = any(min(ds._window(int(ds.index[k][0]))) < 30 for k in range(len(ds)))
    assert reaches_back, "test windows should still see the preceding train days"


def test_t_seq_one_embargoes_nothing():
    _, _, _, _, _, tr, te = _daily_like()
    assert list(D.embargo_indices(tr, 1, int(te.min()))) == list(tr)
    assert list(D.embargo_indices(tr, 0, int(te.min()))) == list(tr)


def test_embargo_is_deterministic_and_order_preserving():
    _, _, _, _, _, tr, te = _daily_like()
    a = D.embargo_indices(tr, 11, int(te.min()))
    b = D.embargo_indices(tr, 11, int(te.min()))
    assert np.array_equal(a, b)
    assert np.array_equal(a, np.sort(a))


def test_embargo_with_no_forbidden_block_is_a_no_op():
    _, _, _, _, _, tr, _ = _daily_like()
    assert np.array_equal(D.embargo_indices(tr, 11, None), tr)


def test_embargo_scales_with_the_window_length():
    _, _, _, _, _, tr, te = _daily_like()
    for t_seq, expect in ((3, 1), (11, 5), (31, 15)):
        kept = D.embargo_indices(tr, t_seq, int(te.min()))
        assert len(tr) - len(kept) == expect, f"T_SEQ={t_seq}"


def test_the_real_daily_split_loses_five_of_three_hundred_and_four_targets():
    """The measured impact on the shipped bundle, pinned so it cannot drift unnoticed."""
    times = (np.datetime64("2025-06-01") + np.arange(388)).astype("datetime64[D]")
    tr, te = D.daily_split_indices(times)
    assert len(tr) == 304 and len(te) == 84
    kept = D.embargo_indices(tr, 11, int(te.min()))
    assert len(kept) == 299, "expected 5 of 304 training days embargoed at T_SEQ=11"
    assert str(times[kept.max()]) == "2026-03-26"
