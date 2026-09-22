"""Day-of-year as geo channels (E-INV-00 leg L1): the model can see the season.

Routed through the geo/coordinate channels, not c_in, so the input-width guard is untouched.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from phase2.tscast_nio import config
from oceanembed import config as ocfg
from phase2.tscast_nio.models.tscast import TSCastNIO, assert_architecture_matches
from phase2.tscast_nio import dataset as D
from phase2.tscast_nio import time_encoding as TE

C, P, DEP = 7, config.P, ocfg.N_DEPTHS


def test_default_model_still_takes_three_geo_channels():
    m = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple")
    assert m.n_geo == 3 and m.doy_channels is False
    mu, _ = m(torch.randn(2, C, 1, P, P), torch.randn(2, 3, 1, P, P),
              torch.randn(2, 12, DEP), torch.randint(0, 12, (2,)))
    assert mu.shape == (2, DEP)


def test_doy_model_takes_five_geo_channels():
    m = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple", doy_channels=True)
    assert m.n_geo == 5 and m.doy_channels is True
    mu, _ = m(torch.randn(2, C, 1, P, P), torch.randn(2, 5, 1, P, P),
              torch.randn(2, 12, DEP), torch.randint(0, 12, (2,)))
    assert mu.shape == (2, DEP)


def test_doy_model_rejects_three_geo_channels_loudly():
    m = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple", doy_channels=True)
    with pytest.raises(RuntimeError):
        m(torch.randn(2, C, 1, P, P), torch.randn(2, 3, 1, P, P),
          torch.randn(2, 12, DEP), torch.randint(0, 12, (2,)))


def test_architecture_guard_catches_doy_mismatch_both_ways():
    doy = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple", doy_channels=True)
    plain = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple")
    with pytest.raises(ValueError, match="doy|geo"):
        assert_architecture_matches(plain, {"channels": ["a"] * C, "doy_channels": True})
    with pytest.raises(ValueError, match="doy|geo"):
        assert_architecture_matches(doy, {"channels": ["a"] * C, "doy_channels": False})


def test_guard_silent_when_checkpoint_predates_doy_field():
    plain = TSCastNIO("cnn3d", C, t_seq=1, p=P, latent=32, decoder="simple")
    assert_architecture_matches(plain, {"channels": ["a"] * C})   # no doy_channels key: no constraint


def _tiny_bundle(n=6):
    rng = np.random.default_rng(0)
    surface = rng.normal(size=(n, 8, 8, C)).astype("float32")
    temp = rng.normal(size=(n, 8, 8, DEP)).astype("float32")
    times = np.arange("2025-01-01", "2025-01-01", dtype="datetime64[D]")
    times = (np.datetime64("2025-01-01") + np.arange(n)).astype("datetime64[D]")
    land = np.zeros((8, 8), dtype=bool)
    ch = ["sst", "sss", "ssh", "u", "v", "wu", "wv"]
    return surface, temp, times, land, ch


def test_dataset_appends_two_doy_channels_matching_the_target_day():
    surface, temp, times, land, ch = _tiny_bundle()
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(len(times)),
                          t_seq=1, p=5, doy_channels=True)
    x, g, *_ = ds[0]
    assert tuple(g.shape) == (5, 1, 5, 5)
    t0 = times[int(ds.index[0][0])]
    want = TE.doy_encoding(t0)
    # the doy channels are constant across the patch; compare the corner
    assert g[3, 0, 0, 0].item() == pytest.approx(float(want[0]), abs=1e-6)
    assert g[4, 0, 0, 0].item() == pytest.approx(float(want[1]), abs=1e-6)


def test_dataset_default_is_three_geo_channels_unchanged():
    surface, temp, times, land, ch = _tiny_bundle()
    ds = D.GriddedPatches(surface, temp, times, land, ch, np.arange(len(times)), t_seq=1, p=5)
    _, g, *_ = ds[0]
    assert tuple(g.shape) == (3, 1, 5, 5)
