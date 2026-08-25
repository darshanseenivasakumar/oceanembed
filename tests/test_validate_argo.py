"""Unit C tests for independent Argo validation. Owner: Mitun + Niru.

The honesty gates are tested as hard as the arithmetic, because they are the part that keeps a
meaningless number off a slide.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oceanembed import config
from oceanembed.validation import validate_argo as va

D = config.N_DEPTHS
RNG = np.random.default_rng(config.SEED)


def make_argo(n_profiles=40, missing_surface=True) -> pd.DataFrame:
    """Long-format Argo rows matching DATA_CONTRACT: [lat, lon, date, depth_idx, temp]."""
    rows = []
    for p in range(n_profiles):
        lat = float(config.LAT[RNG.integers(5, config.N_LAT - 5)])
        lon = float(config.LON[RNG.integers(5, config.N_LON - 5)])
        date = "2022-06-15" if p % 2 == 0 else "2022-07-15"
        for k in range(D):
            # Mirror the real data: floats rarely sample at exactly 0 m.
            if missing_surface and k == 0 and p % 10 != 0:
                continue
            rows.append({"lat": lat, "lon": lon, "date": date, "depth_idx": k,
                         "temp": float(np.linspace(29.0, 12.2, D)[k] + RNG.normal(0, 0.3))})
    return pd.DataFrame(rows)


def fake_grid(offset=0.0):
    """Stand-in for reconstruct_grid: a plausible field, offset degC from the Argo profile."""
    def _f(date, with_uncertainty=False):
        temp = np.broadcast_to(
            np.linspace(29.0, 12.2, D)[None, None, :],
            (config.N_LAT, config.N_LON, D)).astype("float32") + offset
        return {"date": date, "temp": temp.copy()}
    return _f


# --- honesty gate 1: synthetic-trained models --------------------------------
def test_refuses_to_validate_a_synthetic_trained_model(monkeypatch):
    """Synthetic model vs real Argo = numbers that look like a result and mean nothing."""
    monkeypatch.setattr(va, "model_provenance", lambda: ("synthetic", "model trained on SYNTHETIC GLORYS"))
    with pytest.raises(SystemExit, match="REFUSING"):
        va.validate_against_argo(make_argo(), reconstruct_grid=fake_grid())


def test_refuses_when_provenance_is_merely_unverified(monkeypatch):
    """Absence of evidence must not be promoted into 'real'."""
    monkeypatch.setattr(va, "model_provenance", lambda: ("unverified", "UNVERIFIED"))
    with pytest.raises(SystemExit):
        va.validate_against_argo(make_argo(), reconstruct_grid=fake_grid())


def test_allow_unverified_runs_but_marks_the_output(monkeypatch):
    monkeypatch.setattr(va, "model_provenance", lambda: ("synthetic", "model trained on SYNTHETIC GLORYS"))
    res = va.validate_against_argo(make_argo(), allow_unverified=True, reconstruct_grid=fake_grid())
    assert res["is_publishable"] is False
    assert res["provenance"] == "synthetic"
    assert "NOT a result" in va.report(res) or "NOT A RESULT" in va.report(res)


def test_a_real_trained_model_is_publishable(monkeypatch):
    monkeypatch.setattr(va, "model_provenance", lambda: ("real", "model trained on real GLORYS"))
    res = va.validate_against_argo(make_argo(), reconstruct_grid=fake_grid())
    assert res["is_publishable"] is True
    assert "NOT A RESULT" not in va.report(res)


# --- honesty gate 2: n per depth --------------------------------------------
@pytest.fixture
def real_result(monkeypatch):
    monkeypatch.setattr(va, "model_provenance", lambda: ("real", "model trained on real GLORYS"))
    return va.validate_against_argo(make_argo(n_profiles=60), reconstruct_grid=fake_grid())


def test_reports_n_for_every_depth(real_result):
    assert len(real_result["n_per_depth"]) == D
    assert all(isinstance(v, int) for v in real_result["n_per_depth"])


def test_sparse_surface_level_is_flagged_not_hidden(real_result):
    """0 m has far fewer obs than the rest; an unflagged RMSE there reads as equally solid."""
    assert real_result["n_per_depth"][0] < real_result["n_per_depth"][5]
    assert 0 in real_result["unreliable_depths"]
    assert "too few obs" in va.report(real_result)


def test_report_leads_with_the_surface_caveat(real_result):
    text = va.report(real_result)
    assert "extrapolate" in text.lower()


# --- arithmetic --------------------------------------------------------------
def test_a_perfect_model_scores_near_zero(monkeypatch):
    monkeypatch.setattr(va, "model_provenance", lambda: ("real", "real"))
    argo = make_argo(n_profiles=30, missing_surface=False)
    # Grid returns exactly the noiseless profile; Argo has +/-0.3 noise around it.
    res = va.validate_against_argo(argo, reconstruct_grid=fake_grid())
    assert res["rmse_overall"] < 0.6


def test_a_constant_offset_shows_up_as_bias(monkeypatch):
    monkeypatch.setattr(va, "model_provenance", lambda: ("real", "real"))
    res = va.validate_against_argo(make_argo(n_profiles=30, missing_surface=False),
                                   reconstruct_grid=fake_grid(offset=2.0))
    assert np.allclose(res["bias_by_depth"], 2.0, atol=0.3), "a +2 degC offset must appear as bias"


def test_unsampled_cells_are_excluded_not_imputed():
    """A depth a float never sampled must not silently become a zero-error match."""
    argo = make_argo(n_profiles=20)
    keys, y_true = va.pivot_profiles(argo)
    assert np.isnan(y_true[:, 0]).sum() > 0, "unsampled surface cells must stay NaN"
    assert len(keys) == len(y_true)


def test_pivot_gives_one_row_per_profile():
    argo = make_argo(n_profiles=25, missing_surface=False)
    keys, y_true = va.pivot_profiles(argo)
    assert y_true.shape == (len(keys), D)
    assert len(keys) == len(argo[["lat", "lon", "date"]].drop_duplicates())


def test_pivot_rejects_an_out_of_range_depth_index():
    bad = make_argo(n_profiles=5)
    bad.loc[0, "depth_idx"] = D + 3
    with pytest.raises(AssertionError):
        va.pivot_profiles(bad)


def test_a_failing_date_is_skipped_not_fatal(monkeypatch):
    """One bad date must not abort validation of every other date."""
    monkeypatch.setattr(va, "model_provenance", lambda: ("real", "real"))
    good = fake_grid()

    def flaky(date, with_uncertainty=False):
        if str(date) == "2022-07-15":
            raise ValueError("date outside model range")
        return good(date, with_uncertainty)

    res = va.validate_against_argo(make_argo(n_profiles=20), reconstruct_grid=flaky)
    assert res["n_matched_total"] > 0, "the surviving date should still be validated"


def test_load_argo_rejects_a_table_missing_contract_columns(tmp_path, monkeypatch):
    bad = tmp_path / "argo_test.csv"
    pd.DataFrame({"lat": [10.0], "lon": [80.0]}).to_csv(bad, index=False)
    monkeypatch.setattr(va.io, "load_table", lambda _p: pd.read_csv(bad))
    with pytest.raises(AssertionError, match="missing columns"):
        va.load_argo(str(tmp_path / "argo_test"))
