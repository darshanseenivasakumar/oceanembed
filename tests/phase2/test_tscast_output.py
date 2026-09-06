"""Output-record tests: the two standing rules must be structurally impossible to skip."""
import numpy as np
import pytest

from phase2.tscast_nio import config, output

DEP = config.N_DEPTHS


def _rec(**kw):
    kw.setdefault("temperature", np.linspace(28, 4, DEP))
    kw.setdefault("log_var_t", np.full(DEP, np.log(0.5 ** 2)))
    kw.setdefault("valid", np.ones(DEP, bool))
    kw.setdefault("seafloor_depth_m", 2000.0)
    kw.setdefault("provenance", {"model": "test"})
    return output.build_record(**kw)


def test_every_depth_carries_a_reason():
    r = _rec()
    assert len(r["reasons"]) == DEP
    assert all(isinstance(s, str) and len(s) > 20 for s in r["reasons"])


def test_a_reason_says_why_not_merely_what():
    """A reason that just restates the number explains nothing."""
    r = _rec()
    for s in r["reasons"]:
        assert any(w in s for w in ("measured", "sea floor", "unmeasured", "not been measured")), s


def test_below_seafloor_depths_report_the_floor_not_a_number():
    valid = np.ones(DEP, bool)
    valid[-3:] = False
    r = _rec(valid=valid, seafloor_depth_m=30.0)
    assert r["temperature"][-1] is None and r["sigma_t"][-1] is None
    assert "sea floor here is at 30 m" in r["reasons"][-1]
    assert r["temperature"][0] is not None


def test_stage2_keys_exist_and_are_none_so_stage2_is_not_a_migration():
    r = _rec()
    for k in ("salinity", "log_var_s", "density", "log_var_rho"):
        assert k in r and r[k] is None


def test_sigma_is_derived_from_log_variance_correctly():
    r = _rec(log_var_t=np.full(DEP, np.log(4.0)))
    assert all(abs(s - 2.0) < 1e-6 for s in r["sigma_t"])


def test_wrong_depth_count_is_refused_not_reshaped():
    with pytest.raises(ValueError, match="frozen"):
        output.build_record(np.zeros(11), np.zeros(11), np.ones(11, bool), 100.0, {})


def test_argo_check_carries_the_signed_difference_beside_the_prediction():
    pred = np.linspace(28, 4, DEP)
    argo = pred + 0.5                                    # floats are warmer -> model reads cold
    chk = output.build_argo_check(argo, pred, "float-1", 12.0, 2)
    assert all(abs(d + 0.5) < 1e-6 for d in chk["difference"])
    assert chk["quality"] == "HIGH"
    assert "12 km and 2 days" in chk["quality_reason"]


def test_argo_quality_label_always_carries_its_own_reason():
    for km, days in [(12, 2), (40, 4), (80, 8), (500, 30)]:
        chk = output.build_argo_check(np.zeros(DEP), np.zeros(DEP), "f", km, days)
        assert chk["quality"] in ("HIGH", "MEDIUM", "LOW", "REJECT")
        assert str(int(km)) in chk["quality_reason"] and len(chk["quality_reason"]) > 15


def test_argo_check_keeps_none_where_the_float_did_not_sample():
    argo = np.full(DEP, np.nan)
    argo[:5] = 20.0
    chk = output.build_argo_check(argo, np.full(DEP, 20.0), "f", 10.0, 1)
    assert chk["difference"][0] == 0.0
    assert chk["difference"][-1] is None, "a depth the float missed must be None, never 0.0"


def test_a_forecast_cannot_carry_a_ground_truth_check():
    """2027 output has no truth to check against. Attaching one would be fabricated validation."""
    chk = output.build_argo_check(np.zeros(DEP), np.zeros(DEP), "f", 10.0, 1)
    with pytest.raises(ValueError, match="forecast cannot carry"):
        _rec(forecast=True, argo_check=chk)


def test_forecast_records_label_themselves():
    r = _rec(forecast=True)
    assert r["forecast"] is True
    assert "FORECAST" in r["forecast_note"] and "No accuracy number" in r["forecast_note"]
    r2 = _rec()
    assert r2["forecast"] is False and r2["forecast_note"] is None


def test_reasons_come_from_a_measured_artifact_not_from_adjectives():
    """If nothing has been measured, the reason must say so rather than assert a confidence."""
    rmse = [np.nan] * DEP
    lines = output.build_reasons(np.full(DEP, 0.5), np.ones(DEP, bool), 2000.0, rmse=rmse)
    assert all("no error measurement" in s for s in lines)

    real = list(np.linspace(0.4, 1.4, DEP))
    real[4] = 3.0                                        # make 30 m the worst by measurement
    lines = output.build_reasons(np.full(DEP, 0.5), np.ones(DEP, bool), 2000.0, rmse=real)
    assert "weakest depth" in lines[4], "the worst depth must be named from the numbers"
    assert sum("weakest depth" in s for s in lines) == 1


# ----------------------------------------------------- Phase 6: calibrated sigma

def _cal(t_seq=31, channels=("sst", "sss", "ssh", "u", "v"), scale=2.0):
    from phase2.tscast_nio import config as c
    return {"T_SEQ": t_seq, "channels": list(channels), "method_used": "coverage",
            "checkpoint": "test.pt", "n_fit_profiles": 3423,
            "summary_after": {"cov1_mean": 0.72},
            "scales": {str(int(d)): scale for d in c.DEPTHS}}


def test_calibration_scales_sigma_when_the_model_matches():
    cal = _cal()
    r = _rec(provenance={"model": "x", "T_SEQ": 31, "channels": list(cal["channels"])},
             calibration=cal)
    assert r["calibration"]["applied"] is True
    assert r["sigma_t"][5] == pytest.approx(r["sigma_t_raw"][5] * 2.0, rel=1e-6)


def test_calibration_is_REFUSED_when_it_was_fitted_on_a_different_model():
    """Scales come from one checkpoint's residuals. Applying a 5-channel model's scales to a
    7-channel one rescales the error bar by a factor from a different error distribution, and it
    looks completely normal in the output. So it must refuse, not silently apply."""
    cal = _cal(t_seq=31, channels=("sst", "sss", "ssh", "u", "v"))
    r = _rec(provenance={"model": "x", "T_SEQ": 11,
                         "channels": ["sst", "sss", "ssh", "u", "v", "wu", "wv"]},
             calibration=cal)
    assert r["calibration"]["applied"] is False
    assert "T_SEQ=31" in r["calibration"]["why"]
    assert r["sigma_t"] == r["sigma_t_raw"], "sigma must be left RAW on a mismatch"


def test_a_channel_count_mismatch_alone_is_enough_to_refuse():
    cal = _cal(t_seq=11, channels=("sst", "sss", "ssh", "u", "v"))
    r = _rec(provenance={"model": "x", "T_SEQ": 11,
                         "channels": ["sst", "sss", "ssh", "u", "v", "wu", "wv"]},
             calibration=cal)
    assert r["calibration"]["applied"] is False and "channels" in r["calibration"]["why"]


def test_no_calibration_artifact_leaves_sigma_raw_and_says_so():
    r = _rec()
    assert r["calibration"]["applied"] is False
    assert r["sigma_t"] == r["sigma_t_raw"]


def test_a_record_that_cannot_identify_its_model_is_not_calibrated():
    """Provenance without T_SEQ/channels cannot be matched, so it must not be given scales."""
    r = _rec(provenance={"model": "mystery"}, calibration=_cal())
    assert r["calibration"]["applied"] is False
    assert "does not say which model" in r["calibration"]["why"]


def test_the_reason_strings_quote_the_CALIBRATED_sigma_not_the_raw_one():
    """The UI shows sigma_t; if `reasons` quoted the raw value the two would disagree on screen."""
    r = _rec(provenance={"model": "x", "T_SEQ": 31,
                         "channels": ["sst", "sss", "ssh", "u", "v"]},
             calibration=_cal(scale=3.0))
    assert r["calibration"]["applied"] is True
    shown = r["sigma_t"][5]
    assert f"{shown:.2f}" in r["reasons"][5], (r["reasons"][5], shown)


def test_forecast_note_names_the_limits_it_was_given_and_types_none_of_its_own():
    """The note used to carry two typed dates ('GLORYS to 2026-06-23, Argo to 2026-08-24'); the
    second was already wrong for the table the predictor checks against (it ends 2026-06-22).
    The limits come from the caller, which reads them from the loaded data."""
    r = _rec(forecast=True, last_truth_date="2026-06-23", last_argo_date="2026-06-22")
    assert "2026-06-23" in r["forecast_note"] and "2026-06-22" in r["forecast_note"]
    assert "2026-08-24" not in r["forecast_note"]
    r2 = _rec(forecast=True)
    assert "unknown" in r2["forecast_note"], "an absent limit is said to be absent, not typed"
    assert "2026-08-24" not in r2["forecast_note"]
