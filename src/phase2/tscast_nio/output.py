"""Build the prediction record of docs/phase2/tscast_output_schema.md.

Two of Darshan's standing rules are enforced HERE, in the model output, rather than left to the
UI -- because a rule the UI can forget is a rule that will eventually be forgotten:

  * every value explains itself, in place  -> `reasons`, one plain-language string per depth
  * never a number without its ground-truth check beside it -> `argo_check` travels with the record

The reason strings are generated from MEASURED per-depth error, read from an artifact, never from
adjectives chosen by hand. "the mixed layer is our weak spot" is only allowed to appear because
artifacts/*_metrics.json says so in numbers; if the artifact is absent the reason says the error
is unmeasured rather than inventing a confidence level.
"""
from __future__ import annotations

import json
import os

import numpy as np

from oceanembed import config as base
from phase2.tscast_nio import config

# Sources of MEASURED per-depth error, best first. Never a hardcoded table.
ERROR_SOURCES = ("tscast_stage1_metrics.json", "tscast_baseline_metrics.json")


def measured_rmse_by_depth() -> tuple[list | None, str]:
    """Per-depth RMSE actually measured against Argo, plus where it came from."""
    for name in ERROR_SOURCES:
        p = base.art(name)
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        rmse = d.get("metrics", d).get("rmse")
        if rmse and len(rmse) == config.N_DEPTHS:
            return list(rmse), name
    return None, "unmeasured"


def _depth_context(depth_m: int, rmse: list | None) -> str:
    """One clause about WHY this depth behaves as it does, from measured error only."""
    if rmse is None:
        return "per-depth error has not been measured for this model yet"
    arr = np.array(rmse, dtype="float64")
    k = config.DEPTHS.index(depth_m)
    if not np.isfinite(arr[k]):
        return "no error measurement at this depth"
    worst = int(np.nanargmax(arr))
    best = int(np.nanargmin(arr))
    if k == worst:
        return (f"the weakest depth we have, measured {arr[k]:.2f} degC error against "
                f"independent floats")
    if k == best:
        return f"our most accurate depth, measured {arr[k]:.2f} degC against independent floats"
    return f"measured {arr[k]:.2f} degC error against independent floats"


def build_reasons(sigma, valid, seafloor_depth_m, rmse=None) -> list[str]:
    """One self-explaining string per depth. Never a restatement of the number."""
    if rmse is None:
        rmse, _ = measured_rmse_by_depth()
    out = []
    for k, depth in enumerate(config.DEPTHS):
        if not bool(valid[k]):
            out.append(f"no value: the sea floor here is at {seafloor_depth_m:.0f} m, "
                       f"shallower than this {depth} m level")
            continue
        s = float(sigma[k]) if sigma is not None and np.isfinite(sigma[k]) else float("nan")
        if np.isnan(s):
            out.append(f"{depth} m: no uncertainty predicted; "
                       f"{_depth_context(depth, rmse)}")
        else:
            out.append(f"{s:.2f} degC error bar at {depth} m -- {_depth_context(depth, rmse)}")
    return out


def build_argo_check(argo_temperature, temperature, profile_id, distance_km, days_offset,
                     source="argopy") -> dict:
    """Prediction, the nearest independent float, and the signed difference -- together."""
    a = np.asarray(argo_temperature, dtype="float64")
    p = np.asarray(temperature, dtype="float64")
    diff = np.where(np.isfinite(a) & np.isfinite(p), p - a, np.nan)

    # Quality from MEASURED offsets, never invented thresholds: these mirror the F1 collocation
    # engine's bands so the two cannot drift apart.
    if distance_km <= 25 and days_offset <= 3:
        q, why = "HIGH", f"{distance_km:.0f} km and {days_offset} days away - close in both"
    elif distance_km <= 50 and days_offset <= 5:
        q, why = "MEDIUM", f"{distance_km:.0f} km and {days_offset} days away"
    elif distance_km <= 100 and days_offset <= 10:
        q, why = "LOW", (f"{distance_km:.0f} km and {days_offset} days away - far enough that the "
                         f"ocean may have moved between the two")
    else:
        q, why = "REJECT", (f"{distance_km:.0f} km and {days_offset} days away - too far to be "
                            f"the same water")
    return {
        "argo_temperature": [None if not np.isfinite(v) else round(float(v), 4) for v in a],
        "difference": [None if not np.isfinite(v) else round(float(v), 4) for v in diff],
        "profile_id": str(profile_id),
        "distance_km": round(float(distance_km), 2),
        "days_offset": int(days_offset),
        "quality": q,
        "quality_reason": why,
        "source": source,
    }


def _masked(values, valid):
    """A 15-long list with None wherever the column is invalid, or None if there is nothing."""
    if values is None:
        return None
    a = np.asarray(values, dtype="float64")
    if a.shape != (config.N_DEPTHS,):
        raise ValueError(f"expected {config.N_DEPTHS} depths, got {a.shape}; the output contract "
                         "is frozen and reshaping here would misalign every depth label")
    return [None if not valid[k] else round(float(a[k]), 4) for k in range(config.N_DEPTHS)]


def _plain(values):
    """Log-variances are diagnostics and are reported at every depth, valid or not, like log_var_t."""
    if values is None:
        return None
    a = np.asarray(values, dtype="float64")
    if a.shape != (config.N_DEPTHS,):
        raise ValueError(f"expected {config.N_DEPTHS} depths, got {a.shape}")
    return [round(float(x), 4) for x in a]


CALIBRATION_FILE = "uncertainty_calibration.json"


def load_calibration(path: str | None = None) -> dict | None:
    """Per-depth sigma scale factors from Phase 6, or None if calibration was never run.

    Returning None is a valid state, not a failure: an uncalibrated sigma is still the model's
    honest output. What must never happen is applying it silently.
    """
    p = path or base.art(CALIBRATION_FILE)
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def _calibration_applies_to(cal: dict, provenance: dict) -> tuple[bool, str]:
    """Do these scales belong to THIS model?

    Scales are fitted to one checkpoint's residuals. Applying a T_SEQ=31 5-channel model's scales
    to a T_SEQ=11 7-channel one would rescale a sigma by a factor derived from a different error
    distribution -- and it would look completely normal in the output. So the match is checked, and
    a mismatch leaves sigma RAW with the reason recorded, rather than being quietly applied or
    quietly dropped.
    """
    want_t, got_t = cal.get("T_SEQ"), provenance.get("T_SEQ")
    want_c = [str(c) for c in cal.get("channels", [])]
    got_c = [str(c) for c in provenance.get("channels", [])]
    if got_t is None and not got_c:
        return False, "record provenance does not say which model produced it"
    if want_t != got_t:
        return False, f"calibration was fitted on T_SEQ={want_t}, this record is T_SEQ={got_t}"
    if want_c and got_c and want_c != got_c:
        return False, (f"calibration was fitted on {len(want_c)} channels {want_c}, "
                       f"this record has {len(got_c)} {got_c}")
    return True, f"fitted on {cal.get('n_fit_profiles')} train-window Argo profiles"


def build_record(temperature, log_var_t, valid, seafloor_depth_m, provenance,
                 argo_check=None, forecast=False, salinity=None, log_var_s=None,
                 density=None, log_var_rho=None, calibration=None) -> dict:
    """The full record. Stage-2 keys are present and None so stage 2 is a fill-in, not a migration."""
    t = np.asarray(temperature, dtype="float64")
    lv = np.asarray(log_var_t, dtype="float64")
    v = np.asarray(valid, dtype=bool)
    if not (t.shape == lv.shape == v.shape == (config.N_DEPTHS,)):
        raise ValueError(
            f"expected {config.N_DEPTHS} depths, got {t.shape}/{lv.shape}/{v.shape}. "
            "The output contract is frozen; reshaping here would misalign every depth label.")

    sigma_raw = np.sqrt(np.exp(lv))
    sigma = sigma_raw
    cal_block = {"applied": False, "why": "no calibration artifact found", "scales": None}
    if calibration is not None:
        ok, why = _calibration_applies_to(calibration, dict(provenance))
        cal_block = {"applied": bool(ok), "why": why,
                     "method": calibration.get("method_used"),
                     "fitted_on": calibration.get("checkpoint"),
                     "coverage_after": (calibration.get("summary_after") or {}).get("cov1_mean"),
                     "scales": calibration.get("scales") if ok else None}
        if ok:
            sc = calibration.get("scales") or {}
            sigma = sigma_raw.copy()
            for k, dep in enumerate(config.DEPTHS):
                s = sc.get(str(int(dep)), sc.get(int(dep)))
                if s is not None:
                    sigma[k] *= float(s)
    t_out = [None if not v[k] else round(float(t[k]), 4) for k in range(config.N_DEPTHS)]
    s_out = [None if not v[k] else round(float(sigma[k]), 4) for k in range(config.N_DEPTHS)]

    # Stage 2. The same validity mask governs salinity and density: below the sea floor there is
    # no water, so there is no salinity there either, and a number would be a fabrication rather
    # than a rounding artefact.
    sal_out = _masked(salinity, v)
    lvs_out = _plain(log_var_s)
    rho_out = _masked(density, v)
    lvr_out = _plain(log_var_rho)
    sig_s = _masked(np.sqrt(np.exp(np.asarray(log_var_s, dtype="float64"))), v)         if log_var_s is not None else None
    sig_rho = _masked(np.sqrt(np.exp(np.asarray(log_var_rho, dtype="float64"))), v)         if log_var_rho is not None else None

    if forecast and argo_check is not None:
        raise ValueError("a forecast cannot carry an argo_check: no ground truth exists past the "
                         "last observed date. See tscast_output_schema.md section 4.")

    return {
        "depths_m": list(config.DEPTHS),
        "temperature": t_out,
        "log_var_t": [round(float(x), 4) for x in lv],
        # sigma_t is the number a reader should use. sigma_t_raw is the network's uncalibrated
        # output, kept so the two are never confused and so a calibrated run stays auditable.
        "sigma_t": s_out,
        "sigma_t_raw": [None if not v[k] else round(float(sigma_raw[k]), 4)
                        for k in range(config.N_DEPTHS)],
        "calibration": cal_block,
        "valid": [bool(x) for x in v],
        "seafloor_depth_m": float(seafloor_depth_m),
        # stage 2 -- None at stage 1, populated by a stage-2 checkpoint
        "salinity": sal_out,
        "log_var_s": lvs_out,
        "sigma_s": sig_s,
        "density": rho_out,
        "log_var_rho": lvr_out,
        "sigma_rho": sig_rho,
        "reasons": build_reasons(sigma, v, seafloor_depth_m),
        "argo_check": argo_check,
        "forecast": bool(forecast),
        "forecast_note": (
            "FORECAST -- this date is beyond the last date with ground truth (GLORYS to "
            "2026-06-23, Argo to 2026-08-24). No accuracy number can be attached to it."
        ) if forecast else None,
        "provenance": dict(provenance),
    }
