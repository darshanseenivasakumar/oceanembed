"""Every API decision, with no web framework imported. (Unit A / Arjhun.)

WHY THE LOGIC IS SEPARATED FROM THE FRAMEWORK
FastAPI is used for one reason -- its generated `/docs` page is a genuine asset in front of a jury.
But Streamlit pins `starlette<2,>=0.46.0`, and Streamlit IS the demo. If FastAPI and that pin ever
conflict, this module does not change: `app.py` becomes a starlette adapter and everything below
keeps working. Handlers return `(status_code, payload)` so they can be tested with no HTTP at all.

TWO THINGS THAT WILL BREAK THIS IF THEY ARE "SIMPLIFIED"

1. THE LOCK IS NOT OPTIONAL. `predict_field` borrows `predictor.ds.index` and restores it in a
   `finally` (field.py), and `reconstruct` OVERWRITES the same attribute and never restores it
   (inference.py). Two requests sharing one predictor therefore corrupt each other: a `/profile`
   arriving during a `/field.nc` shrinks the index from 11,832 rows to 1 mid-iteration. It does not
   reliably raise -- it returns a plausible wrong answer. Both frameworks run sync handlers in a
   threadpool, so this is reachable with a single worker.

2. HANDLERS MUST BE `def`, NEVER `async def`. A sync handler runs in the threadpool; an async one
   calling `predict_field` blocks the whole event loop for ~32 seconds. It looks fine until two
   people open the page.

REFUSAL, AND WHY IT IS NOT THE SAME AS FORECAST
`_time()` is `argmin(|times - t|)` with no bound: ask for 1850-01-01 and you get bundle index 0 and
a complete, plausible field. Out-of-bundle is REFUSED here, and the refusal names the valid range --
an error that does not say what IS valid cannot be acted on.

A date inside the bundle but past `LAST_GLORYS` is a different thing: it is SERVED, flagged
`forecast: true`, with no accuracy claim, per output-schema §4. Collapsing the two would either
refuse legitimate forecasts or serve nonsense. They stay separate.
"""
from __future__ import annotations

import threading

import numpy as np

#: Held across every predictor call. RLock so a handler that calls two predictor paths cannot
#: deadlock against itself.
_LOCK = threading.RLock()


def bundle_window(predictor) -> tuple[str, str, int]:
    t = np.asarray(predictor.data["times"]).astype("datetime64[D]")
    return str(t.min()), str(t.max()), int(t.size)


def date_within_bundle(predictor, date: str) -> tuple[bool, dict]:
    """Is this date servable? Returns (ok, detail). Detail always names the valid range."""
    lo, hi, n = bundle_window(predictor)
    try:
        want = np.datetime64(str(date), "D")
    except ValueError:
        return False, {"error": "bad_date", "detail": f"{date!r} is not a YYYY-MM-DD date",
                       "first_date": lo, "last_date": hi}
    if not (np.datetime64(lo) <= want <= np.datetime64(hi)):
        return False, {
            "error": "date_out_of_range",
            "detail": (f"{date} is outside the reconstruction bundle. Refusing rather than "
                       f"returning the nearest available day, which would look like an answer."),
            "requested": str(date), "first_date": lo, "last_date": hi, "n_steps": n,
            "see": "/coverage",
        }
    return True, {"first_date": lo, "last_date": hi, "n_steps": n}


def health(predictor) -> tuple[int, dict]:
    """Provenance without running inference -- the cheap call a monitor can make."""
    lo, hi, n = bundle_window(predictor)
    meta = getattr(predictor, "meta", {}) or {}
    from phase2.tscast_nio import provenance as P
    return 200, {
        "status": "ok",
        "model": f"tscast-nio-stage{int(getattr(predictor, 'stage', 1))}",
        "checkpoint_sha256": P.checkpoint_sha256(getattr(predictor, "checkpoint_path", None)),
        "code_commit": P.code_commit(),
        "code_dirty": P.code_dirty(),
        "bundle": meta.get("bundle"),
        "input_source": (getattr(predictor, "data", {}) or {}).get("input_source"),
        "encoder": meta.get("encoder"),
        "T_SEQ": meta.get("T_SEQ"),
        "first_date": lo, "last_date": hi, "n_steps": n,
    }


def coverage(predictor) -> tuple[int, dict]:
    """What this deployment can answer for. This is what makes a 422 actionable."""
    from phase2.tscast_nio.inference import LAST_ARGO, LAST_GLORYS
    lo, hi, n = bundle_window(predictor)
    t = np.asarray(predictor.data["times"]).astype("datetime64[D]")
    steps = np.diff(t).astype("timedelta64[D]").astype(int) if t.size > 1 else np.array([0])
    # Read from the predictor when it derived them from its own bundle and table (TSCastPredictor
    # does); the typed module constants are only the fallback for a stub that carries no bundle.
    last_truth = getattr(predictor, "last_truth_day", None)
    last_argo = getattr(predictor, "last_argo_day", None)
    return 200, {
        "first_date": lo, "last_date": hi, "n_steps": n,
        "cadence_days": float(np.median(steps)),
        "input_source": (getattr(predictor, "data", {}) or {}).get("input_source"),
        "bundle": (getattr(predictor, "meta", {}) or {}).get("bundle"),
        # Past this there is no ground truth, so a prediction there is a forecast and carries no
        # accuracy claim. It is still served -- see the module docstring.
        "last_date_with_truth": str(last_truth if last_truth is not None else LAST_GLORYS),
        "last_argo": str(last_argo if last_argo is not None else LAST_ARGO),
        "note": ("dates after last_date_with_truth are served with forecast=true and no accuracy "
                 "claim; dates outside [first_date, last_date] are refused"),
    }


def profile(predictor, lat, lon, date) -> tuple[int, dict]:
    """One reconstructed profile, as the output-schema record."""
    ok, detail = date_within_bundle(predictor, date)
    if not ok:
        return 422, detail
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return 422, {"error": "bad_point", "detail": "lat and lon must be numbers"}
    # Refused HERE, before the lock and before the model runs. The predictor raises the same
    # ValueError, but a refusal a client can act on needs the domain spelled out beside it.
    from oceanembed import config as _cfg
    from phase2.tscast_nio.inference import assert_point_in_domain
    try:
        assert_point_in_domain(lat, lon)
    except ValueError as e:
        r = _cfg.REGION
        return 422, {"error": "point_out_of_domain", "detail": str(e),
                     "domain": {k: float(r[k]) for k in ("lat_min", "lat_max", "lon_min", "lon_max")},
                     "see": "/coverage"}
    with _LOCK:
        rec = predictor.reconstruct(lat, lon, str(date))
    return 200, _json_safe(rec)


def field_netcdf_bytes(predictor, date) -> tuple[int, object]:
    """The whole field as NetCDF bytes, or a refusal dict."""
    ok, detail = date_within_bundle(predictor, date)
    if not ok:
        return 422, detail
    from phase2.export import netcdf as X
    from phase2.tscast_nio.field import predict_field
    with _LOCK:
        field = predict_field(predictor, str(date))
    return 200, X.to_bytes(X.field_to_xarray(field))


def _json_safe(o):
    """NaN/Inf -> None, recursively.

    The same trap `train_stage1._json_safe` names: Python emits a bare `NaN` token that `json.load`
    accepts and `JSON.parse` rejects, so a browser client would fail on exactly the records that
    contain a below-seafloor depth. Serialise with `allow_nan=False` to make a miss loud.
    """
    import math
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (np.integer, int)) and not isinstance(o, bool):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _json_safe(o.tolist())
    return o
