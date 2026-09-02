"""The basin definition must partition the ocean, and must put real places in the right basin.

Shape checks alone would pass on a definition that puts the Bay of Bengal in Africa. So the
partition tests below are followed by NAMED-PLACE tests and one oceanographic test: the Bay of
Bengal must come out fresher at the surface than the Arabian Sea, which is the physical fact that
distinguishes these two basins and the reason we report them separately at all.
"""
from __future__ import annotations

import os
import warnings

import numpy as np
import pytest

from oceanembed import config
from phase2 import basins

ART = config.ARTIFACTS


@pytest.fixture(scope="module")
def land_mask():
    p = config.art("land_mask.npy")
    if not os.path.exists(p):
        pytest.skip("land_mask.npy absent - artifacts are gitignored")
    return np.load(p)


@pytest.fixture(scope="module")
def masks(land_mask):
    return basins.grid_masks(land_mask)


# ---------------------------------------------------------------- partition

def test_the_three_masks_never_overlap(masks):
    a, b, u = masks["arabian_sea"], masks["bay_of_bengal"], masks["unassigned"]
    assert not (a & b).any(), "a cell is in BOTH basins"
    assert not (a & u).any() and not (b & u).any(), "a cell is both assigned and unassigned"


def test_every_ocean_cell_is_covered_exactly_once(masks, land_mask):
    ocean = ~np.asarray(land_mask, dtype=bool)
    total = masks["arabian_sea"] | masks["bay_of_bengal"] | masks["unassigned"]
    assert (total == ocean).all(), (
        "the three masks do not reproduce the ocean exactly - either a wet cell was dropped or a "
        "dry one was claimed"
    )


def test_no_basin_claims_land(masks, land_mask):
    land = np.asarray(land_mask, dtype=bool)
    for name in ("arabian_sea", "bay_of_bengal"):
        assert not (masks[name] & land).any(), f"{name} contains land cells"


def test_neither_basin_is_empty_or_absurdly_small(masks):
    """A typo in a meridian is most likely to produce an empty or near-empty basin."""
    for name in ("arabian_sea", "bay_of_bengal"):
        n = int(masks[name].sum())
        assert n > 1000, f"{name} has only {n} cells - a boundary is probably wrong"


# ---------------------------------------------------------- named places

@pytest.mark.parametrize("lat,lon,expected,place", [
    (15.0, 65.0, "arabian_sea", "open Arabian Sea"),
    (12.0, 47.0, "arabian_sea", "Gulf of Aden"),
    (25.2, 56.9, "arabian_sea", "Gulf of Oman, outside Hormuz"),
    (15.0, 88.0, "bay_of_bengal", "open Bay of Bengal"),
    (18.0, 89.0, "bay_of_bengal", "northern BoB cyclone genesis region"),
    (12.0, 95.0, "bay_of_bengal", "Andaman Sea"),
    (26.0, 52.5, "unassigned", "Persian Gulf"),
    (6.0, 79.0, "unassigned", "south of Sri Lanka"),
    (8.0, 102.0, "unassigned", "Gulf of Thailand, Pacific side"),
])
def test_real_places_land_in_the_right_basin(lat, lon, expected, place):
    got = basins.classify_points([lat], [lon])[0]
    assert got == expected, f"{place} ({lat}N {lon}E) classified as {got}, expected {expected}"


def test_the_gulf_of_oman_is_arabian_sea_not_persian_gulf():
    """REGRESSION. The Persian Gulf box first used lon <= 57.0 E, which reached past the Strait of
    Hormuz and stranded four real Argo profiles at 25.2 N / 56.9 E as `unassigned`. The eastern
    limit is the strait, not a round number."""
    lat = [25.17, 25.18, 25.19, 25.24]
    lon = [56.91, 56.96, 56.91, 56.94]
    got = basins.classify_points(lat, lon)
    assert set(got) == {"arabian_sea"}, f"Gulf of Oman floats classified as {set(got)}"


# ------------------------------------------------------- real observations

def test_every_argo_profile_gets_a_basin():
    """The point of the definition. If floats fall through, the per-basin numbers will not
    reconcile with the overall one and nobody will know why."""
    import pandas as pd
    from oceanembed.validation import validate_argo as VA
    p = config.art("argo_daily_period.parquet")
    if not os.path.exists(p):
        pytest.skip("argo_daily_period.parquet absent - artifacts are gitignored")
    keys, _ = VA.pivot_profiles(pd.read_parquet(p))
    lab = basins.classify_points(keys["lat"].values, keys["lon"].values)
    n_un = int((lab == "unassigned").sum())
    assert n_un == 0, f"{n_un} Argo profiles fall outside both basins"
    for name in ("arabian_sea", "bay_of_bengal"):
        assert int((lab == name).sum()) > 100, f"{name} has too few profiles to report on"


def test_the_bay_of_bengal_is_fresher_at_the_surface_than_the_arabian_sea():
    """SCIENTIFIC sanity, and the reason the two basins are reported separately at all.

    The Bay of Bengal carries a freshwater cap from the Ganges/Brahmaputra/Meghna and the monsoon;
    the Arabian Sea is among the saltiest open ocean anywhere. If a definition ever comes back
    with the Bay saltier, the masks are swapped or a meridian is wrong - and every per-basin
    number built on them would be quietly mislabelled.
    """
    # subsurface.npz lives beside the processed data, not in artifacts/. It ships in the data
    # bundle and is gitignored, so this test skips on a fresh clone.
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "subsurface.npz")
    if not os.path.exists(p):
        pytest.skip("data/processed/subsurface.npz absent - not in the checkout")
    with np.load(p) as z:
        if "salinity" not in z:
            pytest.skip(f"no salinity field in subsurface.npz (has {list(z.keys())})")
        sal = z["salinity"]                       # (time, lat, lon, depth)
    # Land cells are all-NaN across time, so nanmean warns on them harmlessly; we only read basin
    # (ocean) cells afterwards, where every cell is finite. Suppress the land-cell warning.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        surf = np.nanmean(sal[..., 0], axis=0)    # surface level, averaged over time -> (lat, lon)

    m = basins.grid_masks()
    a = float(np.nanmean(surf[m["arabian_sea"]]))
    b = float(np.nanmean(surf[m["bay_of_bengal"]]))
    assert b < a, (
        f"Bay of Bengal surface salinity {b:.2f} psu is not fresher than the Arabian Sea "
        f"{a:.2f} psu - the basin masks are likely swapped or a meridian is wrong"
    )
