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
