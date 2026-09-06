"""Phase 3: the checkpoint must describe itself, and the predictor must believe it.

Before this, `TSCastPredictor` guessed `film`, guessed monthly, and died with
`Missing key(s) ... decoder.*` on the only checkpoint we had. These tests pin the round-trip so a
checkpoint can never again be unloadable by the code that wrote it.
"""
from __future__ import annotations

import os

import numpy as np
import pytest
import torch

from oceanembed import config as base
from phase2.data.collocation import CollocationEngine

CKPT = base.art("tscast_stage1.pt")
has_ckpt = pytest.mark.skipif(not os.path.exists(CKPT), reason="no checkpoint on this machine")
has_daily_argo = pytest.mark.skipif(
    not os.path.exists(base.art("argo_daily_period.parquet")),
    reason="daily-period Argo table absent")


# -- the checkpoint carries every choice needed to rebuild the network ------------------

@has_ckpt
def test_checkpoint_records_the_choices_the_predictor_must_reproduce():
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    for k in ("decoder", "loss", "data", "T_SEQ", "built_t_seq", "trained_on",
              "train_period", "test_period", "encoder", "channels"):
        assert k in ck, f"checkpoint is missing {k!r} -- the predictor would have to guess it"
    assert ck["decoder"] in ("film", "simple")
    assert ck["data"] in ("monthly", "daily")


@has_ckpt
def test_trained_on_is_derived_from_the_run_not_boilerplate():
    """The old string said "monthly archive, T_SEQ=1" on every daily run. It must move with the run."""
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    assert ck["data"] in ck["trained_on"], ck["trained_on"]
    assert f"T_SEQ={ck['T_SEQ']}" in ck["trained_on"], ck["trained_on"]
    assert ck["train_period"][0] in ck["trained_on"]
    a, b = ck["train_period"]
    c, d = ck["test_period"]
    assert a < b <= c < d, f"train {a}..{b} must end before held-out {c}..{d} begins"


@has_ckpt
def test_built_t_seq_is_recorded_separately_from_the_data_window():
    """The model is CONSTRUCTED at 1 while T_SEQ is the data window; only cnn3d hides the gap."""
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    assert ck["built_t_seq"] == 1
    if ck["T_SEQ"] != 1:
        assert ck["built_t_seq"] != ck["T_SEQ"], (
            "these two coincide, so a reader cannot tell which one to build with")


# -- the predictor rebuilds what the checkpoint names -----------------------------------

@has_ckpt
def test_predictor_builds_the_decoder_the_checkpoint_names():
    from phase2.tscast_nio.inference import TSCastPredictor

    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    p = TSCastPredictor()
    assert p.decoder_name == ck["decoder"]
    assert p.model.decoder_name == ck["decoder"], "the network built is not the one recorded"


@has_ckpt
def test_predictor_loads_the_bundle_the_checkpoint_was_trained_on():
    from phase2.tscast_nio.inference import TSCastPredictor

    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    p = TSCastPredictor()
    assert p.trained_data == ck["data"]
    t = np.asarray(p.data["times"], dtype="datetime64[D]")
    step = int(np.median(np.diff(t).astype(int)))
    assert (step <= 3) == (ck["data"] == "daily"), (
        f"loaded a bundle with a {step}-day cadence for a {ck['data']} checkpoint")


@has_ckpt
def test_predictor_refuses_a_bundle_at_the_wrong_cadence():
    """The failure with no symptom: a daily model fed monthly steps returns plausible numbers."""
    from phase2.tscast_nio.inference import TSCastPredictor

    p = TSCastPredictor()
    n = len(p.data["times"])
    freq = 30 if p.trained_data == "daily" else 1      # the WRONG cadence for this checkpoint
    fake = dict(p.data)
    start = np.datetime64("2019-01-15")
    fake["times"] = (start + np.arange(n) * freq).astype("datetime64[D]")
    with pytest.raises(ValueError, match="cadence|median step"):
        TSCastPredictor(data=fake)


@has_ckpt
def test_predictor_refuses_a_channel_mismatch():
    from phase2.tscast_nio.inference import TSCastPredictor

    p = TSCastPredictor()
    fake = dict(p.data)
    fake["channels"] = list(p.data["channels"])[::-1]
    with pytest.raises(ValueError, match="channels"):
        TSCastPredictor(data=fake)


@has_ckpt
def test_predictor_refuses_weights_that_do_not_fit_and_says_why(tmp_path):
    """A load must never be made to succeed by dropping or inventing weights."""
    from phase2.tscast_nio.inference import TSCastPredictor

    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    ck["decoder"] = "film" if ck["decoder"] == "simple" else "simple"
    bad = tmp_path / "mislabelled.pt"
    torch.save(ck, bad)
    with pytest.raises(RuntimeError, match="does not fit the network described by its own metadata"):
        TSCastPredictor(checkpoint=str(bad))


# -- the record itself ------------------------------------------------------------------

@has_ckpt
def test_one_real_record_is_schema_complete():
    from phase2.tscast_nio.inference import TSCastPredictor

    r = TSCastPredictor().reconstruct(15.0, 68.0, "2026-05-15")
    for k in ("depths_m", "temperature", "sigma_t", "log_var_t", "valid", "reasons",
              "argo_check", "forecast", "provenance", "seafloor_depth_m", "salinity"):
        assert k in r, f"record is missing {k!r}"
    n = len(base.DEPTHS)
    for k in ("depths_m", "temperature", "sigma_t", "valid", "reasons"):
        assert len(r[k]) == n, f"{k} has {len(r[k])} entries, expected {n}"
    # sigma, not log-variance, is what a reader is shown as the error bar
    finite = [s for s in r["sigma_t"] if s is not None]
    assert finite and all(s > 0 for s in finite), "sigma_t must be a positive spread in degC"
    assert r["provenance"]["clim_train_years"] == list(base.TRAIN_YEARS)
    assert r["provenance"]["decoder"] in ("film", "simple")
    assert r["forecast"] is False, "2026-05-15 is inside the GLORYS truth window"


@has_ckpt
def test_a_forecast_date_is_flagged_and_carries_no_ground_truth():
    from phase2.tscast_nio.inference import TSCastPredictor

    r = TSCastPredictor().reconstruct(15.0, 68.0, "2026-08-01")   # past LAST_GLORYS 2026-06-23
    assert r["forecast"] is True
    assert r["argo_check"] is None, "a forecast has no truth to check against"


# -- D1: the Argo table must cover the period being predicted ---------------------------

def test_collocation_default_table_is_unchanged():
    """F1's published numbers rest on argo_test. The default must stay byte-identical."""
    assert CollocationEngine().argo_table == "argo_test"


@has_ckpt
def test_v2_uses_the_daily_period_argo_table():
    from phase2.tscast_nio.inference import TSCastPredictor

    p = TSCastPredictor()
    if p.trained_data == "daily":
        assert p.argo_table == "argo_daily_period"
        assert p.engine.argo_table == "argo_daily_period"


@has_daily_argo
def test_a_2026_date_finds_a_real_float():
    """The D1 ask: against argo_test this matched ZERO floats for every v2 prediction."""
    m = CollocationEngine(argo_table="argo_daily_period").match_argo(15.0, 68.0, "2026-05-15")
    assert m is not None, "no float near 15N 68E in May 2026 -- the v2 table is not being read"
    assert m["spatial_offset_km"] < 100
    assert "2026" in m["datetime"]
    assert CollocationEngine(argo_table="argo_test").match_argo(15.0, 68.0, "2026-05-15") is None, (
        "argo_test is 2022 only; if it now matches a 2026 date the tables have been crossed")


@has_ckpt
@has_daily_argo
def test_a_2026_prediction_carries_a_non_null_argo_check():
    from phase2.tscast_nio.inference import TSCastPredictor

    r = TSCastPredictor().reconstruct(15.0, 68.0, "2026-05-15")
    ac = r["argo_check"]
    assert ac is not None, ("every v2 prediction returned a null argo_check -- structurally correct "
                            "and scientifically empty (AGENT_SYNC ASK D1)")
    assert ac["quality"] in ("HIGH", "MEDIUM", "LOW", "REJECT")
    assert ac["distance_km"] >= 0 and ac["days_offset"] >= 0


# -- the serving path refuses what it cannot honestly answer (audit 2026-09-06) ---------
#
# `D.cell_index` is argmin with no bound and `_time` is argmin with no lower bound. Measured on
# the shipped predictor: (45N, 120E) snapped to the domain corner, lat=NaN snapped to the first
# grid cell and returned a complete profile with an error bar, and a 2020-01-01 request was
# served from 2025-06-01 inputs with forecast=False and days_from_requested=1978. Every one of
# those is a well-formed record about a place or a time the model was never asked about.

def test_points_outside_the_domain_or_non_finite_are_refused():
    from phase2.tscast_nio.inference import assert_point_in_domain

    for la, lo in [(45.0, 120.0), (-10.0, 30.0), (15.0, 120.0), (31.0, 70.0)]:
        with pytest.raises(ValueError, match="outside"):
            assert_point_in_domain(la, lo)
    for la, lo in [(float("nan"), 68.0), (15.0, float("nan")), (float("inf"), 68.0)]:
        with pytest.raises(ValueError, match="finite"):
            assert_point_in_domain(la, lo)
    # the requested box itself, edges included, is answerable
    for la, lo in [(15.0, 68.0), (5.0, 45.0), (30.0, 105.0), (29.9, 104.9)]:
        assert_point_in_domain(la, lo)


@has_ckpt
def test_reconstruct_refuses_out_of_domain_nan_and_pre_bundle_requests():
    from phase2.tscast_nio.inference import TSCastPredictor

    p = TSCastPredictor()
    with pytest.raises(ValueError, match="outside"):
        p.reconstruct(45.0, 120.0, "2026-05-15")
    with pytest.raises(ValueError, match="finite"):
        p.reconstruct(float("nan"), 68.0, "2026-05-15")
    with pytest.raises(ValueError, match="precedes"):
        p.reconstruct(15.0, 68.0, "2020-01-01")
    with pytest.raises(ValueError, match="precedes"):
        p._time("2025-05-31")
    # a date past the bundle is still a labelled forecast -- that contract is unchanged
    assert p.reconstruct(15.0, 68.0, "2026-08-01")["forecast"] is True


@has_ckpt
@has_daily_argo
def test_truth_and_argo_limits_are_read_from_the_data_not_typed():
    """`LAST_ARGO` was typed as 2026-08-24 while the table the predictor checks against ends
    2026-06-22, and the forecast note repeated the typed date. Both limits now come from the
    loaded bundle and the loaded table."""
    import pandas as pd
    from phase2.tscast_nio.inference import TSCastPredictor

    p = TSCastPredictor()
    t = np.asarray(p.data["times"], dtype="datetime64[D]")
    assert p.last_truth_day == t.max()
    table = pd.read_parquet(base.art("argo_daily_period.parquet"), columns=["date"])
    assert p.last_argo_day == np.datetime64(pd.to_datetime(table["date"]).max().date())
    r = p.reconstruct(15.0, 68.0, "2026-08-01")
    assert str(p.last_truth_day) in r["forecast_note"]
    assert str(p.last_argo_day) in r["forecast_note"]
    assert "2026-08-24" not in r["forecast_note"]
