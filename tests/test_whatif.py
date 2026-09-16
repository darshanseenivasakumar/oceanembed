"""Tests for the What-If Calculator backend (src/oceanembed/whatif)."""
from __future__ import annotations

import pytest

from oceanembed.whatif import registry as R


def _demo_spec():
    return R.FormulaSpec(
        id="demo", label="Demo", scope="point",
        inputs=(
            R.InputSpec("sst", "SST", "float", None, -2.0, 40.0, "degC"),
            R.InputSpec("k", "k", "float", 2.0, 0.5, 5.0, "sigma"),
            R.InputSpec("robust", "Robust", "bool", True),
        ),
        function=lambda ctx, inputs: inputs,
        outputs="echo",
    )


def test_resolve_fills_defaults_and_baseline():
    got = R.resolve_inputs(_demo_spec(), {}, {"sst": 10.0})
    assert got == {"sst": 10.0, "k": 2.0, "robust": True}


def test_resolve_applies_override():
    got = R.resolve_inputs(_demo_spec(), {"sst": 10.2, "k": 3.0}, {"sst": 10.0})
    assert got["sst"] == 10.2 and got["k"] == 3.0 and got["robust"] is True


def test_unknown_key_raises():
    with pytest.raises(ValueError):
        R.resolve_inputs(_demo_spec(), {"nope": 1}, {"sst": 10.0})


def test_wrong_kind_raises():
    with pytest.raises(ValueError):        # a float where a bool is expected
        R.resolve_inputs(_demo_spec(), {"robust": 1.0}, {"sst": 10.0})
    with pytest.raises(ValueError):        # a bool where a float is expected
        R.resolve_inputs(_demo_spec(), {"sst": True}, {"sst": 10.0})


def test_missing_value_raises():
    with pytest.raises(ValueError):        # sst has default None and no baseline value
        R.resolve_inputs(_demo_spec(), {}, {})


def test_get_missing_formula_raises():
    with pytest.raises(KeyError):
        R.get("does-not-exist")


# --------------------------------------------------------------------------- real-data smoke
import os                                                       # noqa: E402
import numpy as np                                              # noqa: E402
from oceanembed import config                                   # noqa: E402
from oceanembed.whatif import compute, engine                   # noqa: E402


def _artifacts_ready() -> bool:
    from oceanembed.inference import predict as P
    model = os.path.exists(config.art("mlp_model.pt"))
    grids = P.source_available("satellite") or P.source_available("glorys")
    return model and grids


def _source() -> str:
    from oceanembed.inference import predict as P
    return "satellite" if P.source_available("satellite") else "glorys"


def _last_date():
    from oceanembed.inference import predict as P
    P.set_source(_source())
    return P.available_dates()[-1]


needs_data = pytest.mark.skipif(not _artifacts_ready(), reason="needs built artifacts (model + grids)")

# An ocean point (central Arabian Sea) and a land point (central India) inside the bbox.
OCEAN = (15.0, 65.0)
LAND = (23.0, 80.0)


@needs_data
def test_baseline_reads_real_surface_and_profile():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    assert ctx.is_land is False
    assert set(ctx.surface) == {"sst", "sss", "ssh", "u", "v"}
    assert ctx.profile_mean is not None and len(ctx.profile_mean) == config.N_DEPTHS
    assert 1 <= ctx.month <= 12


@needs_data
def test_baseline_land_guard():
    ctx = engine.baseline(*LAND, _last_date(), _source())
    assert ctx.is_land is True
    assert ctx.surface is None


@needs_data
def test_baseline_grid_shapes():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    g = ctx.grid()
    assert g["temp"].shape == (config.N_LAT, config.N_LON, config.N_DEPTHS)
    assert g["a2d"].shape == (config.N_LAT, config.N_LON)


# --------------------------------------------------------------------------- subsurface_profile
SURF = ("sst", "sss", "ssh", "u", "v")


@needs_data
def test_profile_handler_is_deterministic():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    base_inputs = {k: ctx.surface[k] for k in SURF}
    a = compute.compute_profile(ctx, base_inputs)
    b = compute.compute_profile(ctx, base_inputs)
    assert a["available"] is True
    np.testing.assert_allclose(a["profile_mean"], b["profile_mean"], atol=1e-6)
    assert len(a["profile_mean"]) == config.N_DEPTHS


@needs_data
def test_profile_baseline_matches_reconstruct():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    out = compute.compute_profile(ctx, {k: ctx.surface[k] for k in SURF})
    got = np.nan_to_num(np.array(out["profile_mean"], dtype="float32"))
    base = np.nan_to_num(np.asarray(ctx.profile_mean, dtype="float32"))
    np.testing.assert_allclose(got, base, atol=1e-2)   # same inputs+seed reproduce reconstruct


@needs_data
def test_profile_responds_to_sst_override():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    base = compute.compute_profile(ctx, {k: ctx.surface[k] for k in SURF})
    warm = compute.compute_profile(ctx, {**{k: ctx.surface[k] for k in SURF},
                                         "sst": ctx.surface["sst"] + 0.5})
    d = np.array(warm["profile_mean"]) - np.array(base["profile_mean"])
    assert np.nanmax(np.abs(d)) > 0.0


@needs_data
def test_profile_on_land_not_available():
    ctx = engine.baseline(*LAND, _last_date(), _source())
    out = compute.compute_profile(ctx, {k: 10.0 for k in SURF})
    assert out["available"] is False


def test_profile_registered():
    from oceanembed.whatif import registry as R
    spec = R.get("subsurface_profile")
    assert spec.scope == "point"
    assert tuple(i.name for i in spec.inputs) == SURF
    assert all(i.default is None for i in spec.inputs)


# --------------------------------------------------------------------------- anomaly_extremes
@needs_data
def test_anomaly_extremes_z_is_k_independent_and_counts_monotone():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    lo = compute.compute_anomaly_extremes(ctx, {"k": 1.0})
    hi = compute.compute_anomaly_extremes(ctx, {"k": 3.0})
    if not lo["available"]:
        pytest.skip("no climatology artifact")
    np.testing.assert_allclose(lo["point_standardized_anomaly"],
                               hi["point_standardized_anomaly"], atol=1e-6)
    assert sum(hi["n_extreme_by_depth"]) <= sum(lo["n_extreme_by_depth"])
    assert len(lo["point_is_extreme"]) == config.N_DEPTHS


def test_anomaly_extremes_registered():
    from oceanembed.whatif import registry as R
    from oceanembed.products.anomaly import DEFAULT_K
    spec = R.get("anomaly_extremes")
    assert spec.scope == "grid"
    (k_in,) = spec.inputs
    assert k_in.name == "k" and k_in.kind == "float" and k_in.default == DEFAULT_K


# --------------------------------------------------------------------------- observation_priority
def _prio_inputs(wa, wu, ws, robust=True):
    return {"w_anomaly": wa, "w_uncertainty": wu, "w_sparsity": ws, "robust": robust}


@needs_data
def test_priority_weights_change_the_map():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    a = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 1.0, 1.0))
    b = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 0.0, 0.0))
    assert a["grid_priority"].shape == (config.N_LAT, config.N_LON)
    assert not np.allclose(np.nan_to_num(a["grid_priority"]),
                           np.nan_to_num(b["grid_priority"]))


@needs_data
def test_priority_robust_toggle_runs():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    out = compute.compute_observation_priority(ctx, _prio_inputs(1.0, 1.0, 1.0, robust=False))
    assert out["available"] is True
    assert out["valid_cells"] >= 0


def test_priority_registered():
    from oceanembed.whatif import registry as R
    spec = R.get("observation_priority")
    assert spec.scope == "grid"
    names = tuple(i.name for i in spec.inputs)
    assert names == ("w_anomaly", "w_uncertainty", "w_sparsity", "robust")
    assert spec.inputs[-1].kind == "bool" and spec.inputs[-1].default is True


# --------------------------------------------------------------------------- engine.apply
def test_list_formulas_has_the_three_ids():
    ids = {s.id for s in engine.list_formulas()}
    assert {"subsurface_profile", "anomaly_extremes", "observation_priority"} <= ids


@needs_data
def test_apply_identity_gives_zero_delta():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    res = engine.apply("subsurface_profile", {}, ctx)
    assert res["hypothetical"] is True
    assert res["formula"] == "subsurface_profile"
    assert max(abs(x) for x in res["delta"]["profile_mean"]) < 1e-3


@needs_data
def test_apply_sst_override_moves_profile_and_records_input():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    new_sst = ctx.surface["sst"] + 0.5
    res = engine.apply("subsurface_profile", {"sst": new_sst}, ctx)
    assert res["inputs"]["whatif"]["sst"] == new_sst
    assert res["inputs"]["baseline"]["sst"] == ctx.surface["sst"]
    assert max(abs(x) for x in res["delta"]["profile_mean"]) > 0.0


@needs_data
def test_apply_unknown_formula_raises():
    ctx = engine.baseline(*OCEAN, _last_date(), _source())
    with pytest.raises(KeyError):
        engine.apply("nope", {}, ctx)


def test_package_exports():
    import oceanembed.whatif as W
    for name in ("baseline", "apply", "list_formulas", "get", "REGISTRY",
                 "InputSpec", "FormulaSpec", "WhatIfContext", "resolve_inputs"):
        assert hasattr(W, name), name
