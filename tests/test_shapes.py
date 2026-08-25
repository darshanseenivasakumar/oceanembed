"""Guardian test: the frozen config is consistent and fixtures match the DATA_CONTRACT.

This is the anti-collision check. If it is GREEN, files from all three units fit together.
Owner: Unit B (Darshan).  Run:  pytest -q
"""
from __future__ import annotations
import os
import numpy as np
import pytest

from oceanembed import config
from oceanembed.utils import io


def test_config_constants():
    config.sanity_check()
    assert config.N_LAT == 100 and config.N_LON == 240
    assert config.N_DEPTHS == 11 and config.N_FEAT == 11
    assert len(config.FEATURES) == config.N_FEAT
    assert len(config.DEPTHS) == config.N_DEPTHS


def _fixtures_exist() -> bool:
    return os.path.exists(config.art("sample_X.npy"))


@pytest.mark.skipif(not _fixtures_exist(), reason="run scripts/make_fixtures.py first")
def test_fixture_shapes():
    X = io.load_npy(config.art("sample_X.npy"))
    y = io.load_npy(config.art("sample_y.npy"))
    meta = io.load_table(config.art("sample_meta"))

    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X cols must be {config.N_FEAT}"
    assert y.ndim == 2 and y.shape[1] == config.N_DEPTHS, f"y cols must be {config.N_DEPTHS}"
    assert X.shape[0] == y.shape[0] == len(meta), "X, y, meta must be row-aligned"
    assert X.dtype == np.float32 and y.dtype == np.float32
    for col in ["lat", "lon", "date", "month", "cell_id"]:
        assert col in meta.columns, f"meta missing column '{col}'"


@pytest.mark.skipif(not _fixtures_exist(), reason="run scripts/make_fixtures.py first")
def test_grid_roundtrip():
    from oceanembed.utils import grids
    cid = grids.latlon_to_cell_id(12.3, 78.7)
    la, lo = grids.cell_id_to_latlon(cid)
    assert 5.0 <= la < 30.0 and 45.0 <= lo < 105.0
