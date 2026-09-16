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
