"""The shared experiment loader. Owner: Unit A (Arjhun).

Offline: nothing here loads the bundle or a checkpoint.

Two failures this file exists to catch. First, a second Argo pivot that quietly disagrees with the
project's existing one -- three experiments would then be scored against a different truth from
every other number in the repo. Second, a borrowed dataset index that is not given back, which
silently changes what every later caller reads; `predict_field` already had that bug once.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.reliability import harness as H


def an_argo_table(n_profiles=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_profiles):
        lat, lon = 10.0 + k * 0.25, 70.0 + k * 0.25
        date = pd.Timestamp("2026-05-01") + pd.offsets.Day(k)
        for d in range(base.N_DEPTHS):
            if d == 13 and k % 2:                       # a float that stopped short
                continue
            rows.append({"lat": lat, "lon": lon, "date": date, "depth_idx": d,
                         "temp": 28.0 - 0.02 * d * d + rng.normal(0, 0.05),
                         "psal": 34.5 + 0.01 * d})
    return pd.DataFrame(rows)


# ==================================================== one definition of the truth

def test_the_temperature_pivot_is_identical_to_the_projects_own():
    """A second implementation that disagreed would only tell us the copy was wrong. This one is
    allowed to exist solely because it also returns salinity."""
    df = an_argo_table()
    keys_ref, t_ref = VA.pivot_profiles(df)
    keys, t, _s = H._pivot_ts(df)
    assert list(keys.columns) == list(keys_ref.columns)
    pd.testing.assert_frame_equal(keys, keys_ref)
    assert np.array_equal(np.isnan(t), np.isnan(t_ref))
    assert np.allclose(t, t_ref, equal_nan=True)


def test_salinity_rows_line_up_with_temperature_rows():
    """The pivot is done twice, once per variable. If the two came back in different row orders
    every density in the stability experiment would pair the wrong T with the wrong S -- and would
    still look like seawater."""
    df = an_argo_table(seed=2)
    keys, t, s = H._pivot_ts(df)
    assert s is not None and s.shape == t.shape
    for i, row in keys.iterrows():
        sub = df[(df.lat == row.lat) & (df.lon == row.lon) & (df.date == row.date)]
        for _, r in sub.iterrows():
            assert t[i, int(r.depth_idx)] == pytest.approx(r.temp, abs=1e-5)
            assert s[i, int(r.depth_idx)] == pytest.approx(r.psal, abs=1e-5)


def test_a_level_the_float_never_reached_stays_nan_in_both_variables():
    df = an_argo_table()
    _keys, t, s = H._pivot_ts(df)
    gaps = np.isnan(t)
    assert gaps.any(), "the fixture must contain a short profile or this proves nothing"
    assert np.array_equal(gaps, np.isnan(s))


def test_a_table_without_salinity_returns_none_rather_than_a_nan_grid():
    """An all-NaN salinity array asserts 'this table has salinity, missing everywhere' -- a
    different and false claim, and the one the NetCDF export already refuses to make."""
    df = an_argo_table().drop(columns=["psal"])
    _keys, _t, s = H._pivot_ts(df)
    assert s is None


# ==================================================== borrow and return

class _FakeDS:
    def __init__(self, n=5):
        self.index = np.arange(n).reshape(-1, 1).repeat(3, axis=1)

    def __len__(self):
        return len(self.index)

    def __getitem__(self, k):
        import torch
        return tuple(torch.zeros(1) for _ in range(7))


def _ctx_with(ds):
    return H.Context(model=None, ck={}, ckpt_path="x.pt", stage=1, device="cpu",
                     bundle={}, clim=None, ds_tr=None, ds_te=ds,
                     keys=pd.DataFrame({"lat": [], "lon": [], "date": []}),
                     truth_t=np.zeros((0, base.N_DEPTHS)), truth_s=None,
                     argo_idx=np.zeros((0, 3), int),
                     clim_at=np.zeros((0, base.N_DEPTHS)))


def test_the_loader_gives_the_dataset_index_back():
    ds = _FakeDS()
    ctx = _ctx_with(ds)
    saved = ds.index.copy()
    list(ctx.loader(np.array([[1, 2, 3], [4, 5, 6]]), batch_size=1))
    assert np.array_equal(ds.index, saved)


def test_the_index_is_restored_even_when_the_caller_stops_early():
    """A generator abandoned half way must still run its finally. Without this, a page that breaks
    out of a loop leaves the shared dataset pointing somewhere else."""
    ds = _FakeDS()
    ctx = _ctx_with(ds)
    saved = ds.index.copy()
    gen = ctx.loader(np.array([[1, 2, 3], [4, 5, 6]]), batch_size=1)
    next(gen)
    gen.close()
    assert np.array_equal(ds.index, saved)


# ==================================================== the control's own honesty

def test_a_missing_metrics_file_reports_none_not_a_pass():
    """'We could not check' and 'we checked and it agreed' must never be the same value. `agrees`
    is None here, and the scripts test `is not True` rather than falsiness for that reason."""
    ctx = _ctx_with(_FakeDS())
    ctx._cache["control"] = {"rmse": 0.9, "recorded_rmse": None, "agrees": None}
    got = ctx.control_rmse()
    assert got["agrees"] is None
    assert got["agrees"] is not True


def test_the_control_tolerance_is_the_repos_quoted_precision():
    assert H.CONTROL_TOL == 1e-4
