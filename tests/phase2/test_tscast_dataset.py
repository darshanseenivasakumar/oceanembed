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


def test_train_and_test_windows_never_overlap():
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


# ---------------------------------------------------------------------------
# A1 -- temporal leakage through the INPUT WINDOW (not the split).
# ---------------------------------------------------------------------------

def _daily_calendar():
    """The real v2 calendar: 2025-06-01 .. 2026-06-23, 388 days (verified identical to the bundle)."""
    return np.arange(np.datetime64("2025-06-01"),
                     np.datetime64("2026-06-24"), dtype="datetime64[D]")


def _daily_ds(t_indices, t_seq=11):
    times = _daily_calendar()
    n_t, n_lat, n_lon = len(times), 6, 6
    surface = np.zeros((n_t, n_lat, n_lon, 5), "float32")
    temp = np.zeros((n_t, n_lat, n_lon, config.N_DEPTHS), "float32")
    land = np.zeros((n_lat, n_lon), bool)
    return D.GriddedPatches(surface, temp, times, land,
                            ["sst", "sss", "ssh", "u", "v"], t_indices, t_seq=t_seq, p=3)


def test_train_context_window_never_reaches_into_the_test_period():
    """`daily_split_indices` asserts the INDICES are disjoint and ordered. It says nothing about
    the INPUT WINDOW. At T_SEQ=11 a train sample centred within 5 days of the boundary reads
    test-period surface fields -- future information -- and every other test in this suite still
    passes while it happens. That is what made the leak survive so long.

    Measured on the real calendar before the fix: 5 of 304 train days (2026-03-27..31) = 1.64%."""
    times = _daily_calendar()
    tr, te = D.daily_split_indices(times)
    ds = _daily_ds(tr, t_seq=11)
    test_ix = set(int(k) for k in te)
    crossing = sorted({int(t) for t in tr if test_ix.intersection(ds._window(int(t)))})
    detail = ""
    if crossing:
        detail = (f" -- {len(crossing)} of {len(tr)} train days "
                  f"({100.0 * len(crossing) / len(tr):.2f}%), "
                  f"{times[crossing[0]]}..{times[crossing[-1]]}")
    assert crossing == [], "train input windows reach into the test period" + detail


def test_test_context_window_stays_inside_its_own_block():
    """The conservative half of the same rule. A test-period window reaching back into train is
    not future-leakage, but clamping both sides keeps ONE rule instead of two and cannot be
    argued with. It costs the first 5 test days a repeated frame, which makes the score harder,
    never easier -- the safe direction."""
    times = _daily_calendar()
    tr, te = D.daily_split_indices(times)
    ds = _daily_ds(te, t_seq=11)
    train_ix = set(int(k) for k in tr)
    crossing = sorted({int(t) for t in te if train_ix.intersection(ds._window(int(t)))})
    assert crossing == [], f"{len(crossing)} test windows reach back into the train block"


def test_the_window_keeps_its_full_length_after_clamping():
    """Clamping must repeat edge frames, never return a short window: a ragged T would change the
    input tensor shape and break the encoder rather than fail loudly here."""
    times = _daily_calendar()
    tr, _ = D.daily_split_indices(times)
    ds = _daily_ds(tr, t_seq=11)
    for t in (int(tr[0]), int(tr[len(tr) // 2]), int(tr[-1])):
        w = ds._window(t)
        assert len(w) == 11, f"window at t={t} has length {len(w)}, expected T_SEQ=11"


def test_inference_over_the_full_range_is_not_clamped_away():
    """Inference passes np.arange(n_t) -- the whole record is legitimately available then, so the
    clamp must widen to the full array and not silently shorten an operational context window."""
    times = _daily_calendar()
    ds = _daily_ds(np.arange(len(times)), t_seq=11)
    mid = len(times) // 2
    assert ds._window(mid) == list(range(mid - 5, mid + 6))
