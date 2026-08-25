"""Tests for the Phase-2 subsurface extraction.

These are SCIENTIFIC sanity tests, not only shape tests. Phase 1 taught us repeatedly that an
array can have the right shape, plausible values, and still be wrong data.
"""
from __future__ import annotations
import os
import numpy as np
import pytest

from oceanembed import config

SUB = os.path.join(config.DATA_PROCESSED, "subsurface.npz")
pytestmark = pytest.mark.skipif(
    not os.path.exists(SUB),
    reason="run `python -m phase2.data.extract_subsurface` first",
)


@pytest.fixture(scope="module")
def sub():
    with np.load(SUB, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


# --- contract -------------------------------------------------------------
def test_shapes_match_the_frozen_grid(sub):
    for k in ("salinity", "u", "v"):
        assert sub[k].ndim == 4, k
        assert sub[k].shape[1:] == (config.N_LAT, config.N_LON, config.N_DEPTHS), k
    assert sub["valid_mask"].shape == (config.N_LAT, config.N_LON, config.N_DEPTHS)
    assert sub["salinity"].dtype == np.float32


def test_times_are_chronological_and_match_glorys(sub):
    t = sub["times"].astype("datetime64[D]")
    assert (np.diff(t).astype(int) > 0).all(), "times must be strictly increasing"
    grids = os.path.join(config.DATA_PROCESSED, "grids.npz")
    if os.path.exists(grids):
        with np.load(grids, allow_pickle=False) as z:
            assert (t == z["times"].astype("datetime64[D]")).all(), \
                "subsurface times must align with the baseline grids, or collocation breaks"


def test_provenance_is_stamped(sub):
    assert str(sub["source"]) == "real-glorys-subsurface"


# --- science --------------------------------------------------------------
def test_salinity_is_physically_possible(sub):
    s = sub["salinity"][np.isfinite(sub["salinity"])]
    assert s.min() >= 0.0, "negative salinity is unphysical"
    assert s.max() <= 42.0, "salinity above 42 psu is not credible in this basin"


def test_very_fresh_water_is_confined_to_the_bay_of_bengal_north(sub):
    """The freshest water must sit where the rivers are, not scattered at random.

    GLORYS' minimum here is ~1-6 psu near the Meghna/Ganges mouth. If a unit slip or a bad
    interpolation ever produced low salinity in the open Arabian Sea, this catches it.
    """
    s0 = sub["salinity"][:, :, :, 0]
    with np.errstate(all="ignore"):   # land columns are all-NaN by design
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore", RuntimeWarning)
            fresh = np.nanmin(s0, axis=0) < 25.0
    if not fresh.any():
        pytest.skip("no very fresh cells in this subset")
    ii, jj = np.where(fresh)
    lats, lons = config.LAT[ii], config.LON[jj]
    # Northern Bay of Bengal river-influenced corner
    assert (lons > 78.0).mean() > 0.8, "fresh water should be east of 78E (Bay of Bengal)"
    assert (lats > 10.0).mean() > 0.8, "fresh water should be north of 10N"


def test_salinity_generally_increases_with_depth_in_the_bay_of_bengal(sub):
    """Physical expectation: a fresh surface cap over saltier water below."""
    i = int(np.argmin(np.abs(config.LAT - 18.0)))
    j = int(np.argmin(np.abs(config.LON - 88.0)))
    prof = np.nanmean(sub["salinity"][:, i, j, :], axis=0)
    if np.isnan(prof).all():
        pytest.skip("cell has no water")
    assert prof[-1] > prof[0], "Bay of Bengal should be saltier at depth than at the surface"


def test_currents_are_not_absurd(sub):
    for k in ("u", "v"):
        a = sub[k][np.isfinite(sub[k])]
        assert np.abs(a).max() <= 5.0, f"{k} exceeds 5 m/s, which no NIO current does"


def test_bathymetry_agrees_with_the_baseline(sub):
    """Subsurface validity must match the baseline's valid_mask, or the two cubes disagree
    about where the ocean floor is."""
    grids = os.path.join(config.DATA_PROCESSED, "grids.npz")
    if not os.path.exists(grids):
        pytest.skip("baseline grids absent")
    with np.load(grids, allow_pickle=False) as z:
        if "valid_mask" not in z.files:
            pytest.skip("baseline has no valid_mask")
        base = z["valid_mask"]
    agree = (base == sub["valid_mask"]).mean()
    assert agree > 0.99, f"bathymetry disagrees with the baseline in {(1-agree)*100:.2f}% of cells"


def test_no_all_nan_depth_level(sub):
    for k in range(config.N_DEPTHS):
        assert np.isfinite(sub["salinity"][:, :, :, k]).any(), \
            f"salinity is entirely NaN at {config.DEPTHS[k]} m"
