"""Satellite bundle tests. Each encodes a way this pipeline could produce a plausible-looking
bundle that is quietly wrong -- which is the only kind of bug that reaches a jury.
"""
import json

import numpy as np
import pytest
import xarray as xr

from oceanembed import config as base
from phase2.tscast_nio import config, sat_daily_pipeline as S


def _da(lat, lon, values=None):
    """A DataArray on an arbitrary (possibly offset) native grid."""
    v = values if values is not None else np.add.outer(lat, np.zeros_like(lon))
    return xr.DataArray(np.asarray(v, "float64"), dims=("latitude", "longitude"),
                        coords={"latitude": lat, "longitude": lon})


def test_regrid_lands_exactly_on_the_frozen_grid():
    lat = np.arange(5.0625, 30.0, 0.125)      # the real SSH/SSS offset
    lon = np.arange(45.0625, 105.0, 0.125)
    out = S._regrid(_da(lat, lon))
    assert out.shape == (len(base.LAT), len(base.LON))


def test_regrid_corrects_a_half_cell_offset_rather_than_ignoring_it():
    """The currents grid is centred on 5.125, 5.375 ... -- half a cell off ours. Interpolating a
    known linear field must return the TARGET coordinate's value, not the nearest native one. A
    half-cell error here is ~14 km, the same class of bug as the 28 km cell-lookup mistake."""
    lat = np.arange(5.125, 30.0, 0.25)        # the real currents grid
    lon = np.arange(45.125, 105.0, 0.25)
    # field = latitude, so the correct value at each target cell IS that cell's latitude.
    # Edges are excluded on both axes: see the edge test below for why they are NaN.
    out = S._regrid(_da(lat, lon))
    inner = out[1:-1, 1:-1]
    expected = np.broadcast_to(base.LAT[1:-1, None], inner.shape)
    assert np.allclose(inner, expected, atol=1e-4), (
        "regridding did not shift the half-cell offset: values are still on the native centres")


def test_the_domain_edge_is_nan_rather_than_extrapolated():
    """EVERY satellite grid starts inboard of our domain edge -- sst at 45.025, ssh/sss at 45.0625,
    currents at 45.125 -- because the CMEMS request box was cut at exactly 45.0/5.0. So the first
    row and column have no native data outside them and bilinear cannot fill them.

    NaN is the correct answer: the alternative is extrapolating a coastline we did not observe.
    This costs ~1.4% of cells (1 row of 100 + 1 col of 240) and is recorded here so it is a known
    property of the bundle rather than a surprise in a validation plot."""
    lat = np.arange(5.125, 30.0, 0.25)
    lon = np.arange(45.125, 105.0, 0.25)
    out = S._regrid(_da(lat, lon))
    assert np.all(np.isnan(out[:, 0])), "western edge should be NaN, not extrapolated"
    assert np.all(np.isnan(out[0, :])), "southern edge should be NaN, not extrapolated"
    lost = np.isnan(out).sum() / out.size
    assert lost < 0.02, f"edge loss {lost:.3f} is larger than the expected ~1.4%"


def test_regrid_sorts_a_descending_axis_instead_of_returning_nan():
    """xarray.interp on a descending coordinate silently returns all-NaN. Several satellite
    products ship latitude descending."""
    lat = np.arange(5.0625, 30.0, 0.125)[::-1]
    lon = np.arange(45.0625, 105.0, 0.125)
    out = S._regrid(_da(lat, lon))
    assert np.isfinite(out).any(), "descending latitude produced an all-NaN field"


@pytest.mark.parametrize("name,bad,why", [
    ("sst", 300.0, "Kelvin that was never converted"),
    ("sss", 0.035, "salinity read as the literal '0.001' CF unit -- a 1000x error"),
    ("u", 99.0, "a fill value read as data"),
])
def test_the_physical_gate_refuses_a_unit_error(name, bad, why):
    field = np.full((4, 4), bad, "float32")
    with pytest.raises(ValueError, match="outside the physical gate"):
        S._check_range(name, field, "20250601")


def test_the_physical_gate_refuses_an_all_nan_field():
    with pytest.raises(ValueError, match="every value is NaN"):
        S._check_range("sst", np.full((4, 4), np.nan, "float32"), "20250601")


def test_every_contract_channel_carries_provenance():
    """A channel with no provenance is a channel we cannot defend the origin of."""
    for name in config.CHANNELS:
        meta = S.PROVENANCE_CHANNELS[name]
        if meta is None:                      # v mirrors u, wv mirrors wu -- resolved at build time
            meta = S.PROVENANCE_CHANNELS["u" if name == "v" else "wu"]
        for key in ("product", "provider", "data_class", "native_units", "processed_units"):
            assert meta.get(key), f"{name} provenance is missing {key}"


def test_salinity_is_not_described_as_pure_satellite():
    """The SSS product is SMOS blended WITH IN-SITU (Buongiorno Nardelli 2016). Calling it a pure
    satellite retrieval would be a false provenance claim in front of the sponsor."""
    assert S.PROVENANCE_CHANNELS["sss"]["data_class"] == "SATELLITE + INSITU_BLEND"


def test_the_currents_deviation_from_the_ps_is_recorded_not_hidden():
    meta = S.PROVENANCE_CHANNELS["u"]
    assert "OSCAR" in meta["note"], "the PS's named product must be named in the deviation note"
    assert "DEVIATION" in meta["note"].upper()


def test_sources_and_ranges_cover_exactly_the_satellite_channels():
    """Drift between SAT_SOURCES, RANGES and the frozen channel list is how a channel ends up
    unvalidated or unwritten."""
    src = [name for name, *_ in S.SAT_SOURCES]
    assert src == [c for c in config.CHANNELS if c in src], "source order must follow the contract"
    assert set(src) == set(S.RANGES), "every satellite channel needs a physical gate"
    assert set(config.CHANNELS) - set(src) == {"wu", "wv"}, "only wind is passed through"


def test_the_output_namespace_is_not_the_glorys_one():
    """data/processed/daily/ is canonical GLORYS input and is not ours to overwrite."""
    assert S.OUT_DIR != S.GLORYS_DIR
    assert "daily_sat" in S.OUT_DIR


def test_valid_mask_is_passed_through_not_time_indexed():
    """REGRESSION. valid_mask is (lat, lon, depth) -- static, no time axis. It was selected with
    `vm[gi] if vm.ndim > 2 else vm`, which inferred "has a time axis" from a dimension COUNT and
    so indexed LATITUDE with day numbers. The build died 200 days in with `index 100 is out of
    bounds for axis 0 with size 100`. Cheap to catch, expensive to hit at the end of a long run."""
    vm = np.zeros((len(base.LAT), len(base.LON), config.N_DEPTHS), bool)
    out = S._static_valid_mask({"valid_mask": vm})
    assert out.shape == vm.shape, "a static mask must come through unchanged"


def test_a_valid_mask_that_grew_a_time_axis_is_refused_not_reshaped():
    """If the GLORYS bundle ever starts writing a time axis, that is a decision about which days
    to carry -- not something to silently slice."""
    vm = np.zeros((5, len(base.LAT), len(base.LON), config.N_DEPTHS), bool)
    with pytest.raises(ValueError, match="expected"):
        S._static_valid_mask({"valid_mask": vm})
