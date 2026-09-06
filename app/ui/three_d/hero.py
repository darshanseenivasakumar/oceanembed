"""The WebGL hero: payload preparation and the Streamlit bridge.

OWNER: Unit A (Arjhun). NOT a page.

WHY THE DATA IS QUANTISED AND NOT SENT AS JSON
The volume is 100 x 240 x 15 = 360,000 values. As JSON numbers that is roughly 4 MB of text and
several seconds of parsing, which hangs the tab. Each value is instead quantised to one byte and
the whole stack is sent as a single base64 string -- 360 KB raw, ~480 KB encoded -- and the
colour map is applied in a FRAGMENT SHADER from a 256-entry lookup texture. Switching field or
palette re-sends nothing.

ZERO IS THE SENTINEL, NOT A TEMPERATURE. Real values occupy 1..255; 0 means "no water here" and
the shader DISCARDS that fragment. The sea floor is therefore a hole in the geometry rather than
a cold-coloured cell, which is the same discipline the numpy layer already enforces. Quantisation
costs (vmax-vmin)/254 -- about 0.1 degC over a 26 degC basin -- which is a tenth of the model's
own error and is stated on screen rather than hidden.

THE 26 degC LAYER IS A HEIGHTMAP, NOT AN ISOSURFACE
Exactly one depth per lat/lon, which is what heat_content_field already returns as `d26`. A
marching-cubes mesh through 15 unevenly spaced levels would interpolate far more than it measures
and would invent geometry wherever a column crosses 26 degC twice. scikit-image is also not
installed on this machine, so the isosurface route has no backend here anyway.

THE BRIDGE IS HAND-WRITTEN
st.components.v1.html renders a bare iframe with no way to send a value back, so a click could
never reach Python. declare_component(path=...) gives a bidirectional iframe, and the postMessage
protocol it speaks is implemented directly in index.html rather than pulling in the npm component
library -- three messages in each direction, and no build step.
"""
from __future__ import annotations

import base64
import os

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND = os.path.join(_DIR, "frontend")

#: Declared once per process. A second declare_component with the same name raises.
_impl = None


def _component():
    global _impl
    if _impl is None:
        _impl = components.declare_component("oceanembed_hero", path=_FRONTEND)
    return _impl


def vendored_bytes() -> int:
    """Size of the local three.js copy, or 0 if it is missing.

    Reported on screen: a hall with no Wi-Fi must not silently lose the best feature, and the
    only way to know the fallback is real is to check the file is actually there.
    """
    p = os.path.join(_FRONTEND, "vendor", "three.min.js")
    return os.path.getsize(p) if os.path.exists(p) else 0


# --------------------------------------------------------------------------- colour maps
#: Anchor stops, sampled to a 256-entry LUT and uploaded as a 1-D texture. Kept here rather than
#: imported from plotly so the shader path has no dependency on a plotting library at all.
RAMPS = {
    "thermal": [(0.00, (3, 35, 51)), (0.25, (32, 76, 128)), (0.50, (110, 96, 148)),
                (0.75, (200, 116, 106)), (0.90, (243, 168, 74)), (1.00, (232, 250, 91))],
    "magma": [(0.00, (0, 0, 4)), (0.25, (81, 18, 124)), (0.50, (183, 55, 121)),
              (0.75, (252, 137, 97)), (1.00, (252, 253, 191))],
    "diverging": [(0.00, (8, 48, 107)), (0.25, (66, 146, 198)), (0.50, (247, 247, 247)),
                  (0.75, (140, 107, 177)), (1.00, (74, 20, 134))],
}


def _lut(name: str) -> str:
    stops = RAMPS.get(name, RAMPS["thermal"])
    xs = np.array([s[0] for s in stops], dtype="float64")
    cols = np.array([s[1] for s in stops], dtype="float64")
    t = np.linspace(0.0, 1.0, 256)
    out = np.stack([np.interp(t, xs, cols[:, c]) for c in range(3)], axis=1)
    return base64.b64encode(np.clip(out, 0, 255).astype("uint8").tobytes()).decode("ascii")


# --------------------------------------------------------------------------- quantisation
def _quantise(a: np.ndarray) -> tuple[str, float, float]:
    """Float array -> base64 uint8 with 0 reserved for "no data". Returns (b64, vmin, vmax)."""
    x = np.asarray(a, dtype="float64")
    ok = np.isfinite(x)
    if not ok.any():
        return base64.b64encode(np.zeros(x.shape, "uint8").tobytes()).decode("ascii"), 0.0, 1.0
    vmin, vmax = float(np.nanmin(x[ok])), float(np.nanmax(x[ok]))
    span = (vmax - vmin) or 1.0
    q = np.zeros(x.shape, dtype="uint8")
    q[ok] = 1 + np.clip(np.round((x[ok] - vmin) / span * 254.0), 0, 254).astype("uint8")
    return base64.b64encode(q.tobytes()).decode("ascii"), vmin, vmax


@st.cache_data(show_spinner=False, max_entries=4)
def build_payload(date_str: str, version: str, what: str, device: str | None,
                  show_floats: bool) -> dict:
    """Everything the scene needs, quantised and cached on the same key the field is.

    Cached because quantising 360,000 cells and base64-encoding them is real work that must not
    repeat every time a slider moves. Field switch, exaggeration and rotation all happen entirely
    in the browser and re-enter this function not at all.
    """
    from app.ui import data as D
    from phase2.derived.heat_content import heat_content_field

    f = D.field(date_str, 1, version, device=device)
    lat = np.asarray(D.base.LAT, dtype="float64")
    lon = np.asarray(D.base.LON, dtype="float64")
    depths = np.asarray(D.base.DEPTHS, dtype="float64")

    temp = np.asarray(f["temperature"], dtype="float64")
    sigma = np.asarray(f["sigma"], dtype="float64")
    valid = np.asarray(f["valid_mask"], dtype=bool)
    landm = np.asarray(f["land_mask"], dtype=bool)

    # NaN out everything that is not water, so the sentinel does the masking for us.
    def masked(v):
        v = np.where(valid, v, np.nan)
        return np.where(landm[:, :, None], np.nan, v)

    fields = {}
    for name, arr, ramp in (("temperature", masked(temp), "thermal"),
                            ("uncertainty", masked(sigma), "magma")):
        # (lat, lon, depth) -> (depth, lat, lon) so each depth slice is contiguous in the buffer
        b64, vmin, vmax = _quantise(np.ascontiguousarray(np.moveaxis(arr, 2, 0)))
        fields[name] = {"data": b64, "vmin": vmin, "vmax": vmax, "ramp": ramp,
                        "units": "°C" if name == "temperature" else "°C (1σ)"}

    hc = heat_content_field(f)
    d26 = np.asarray(hc["d26"], dtype="float64")
    d26_b64, d26_min, d26_max = _quantise(d26)

    floats = []
    if show_floats:
        floats = _floats_for(date_str)

    n_water = int(np.isfinite(masked(temp)).sum())
    payload = {
        "nx": int(lon.size), "ny": int(lat.size), "nz": int(depths.size),
        "lon0": float(lon[0]), "lon1": float(lon[-1]),
        "lat0": float(lat[0]), "lat1": float(lat[-1]),
        "depths": [float(z) for z in depths],
        "fields": fields,
        "d26": {"data": d26_b64, "vmin": d26_min, "vmax": d26_max},
        "land": base64.b64encode(landm.astype("uint8").tobytes()).decode("ascii"),
        "luts": {k: _lut(k) for k in RAMPS},
        "floats": floats,
        "date": str(f.get("date", date_str)),
        "n_water": n_water,
        "n_seafloor": int(temp.size - n_water - int(landm.sum()) * len(depths)),
        "quant_step_c": (fields["temperature"]["vmax"] - fields["temperature"]["vmin"]) / 254.0,
    }
    payload["bytes"] = _approx_bytes(payload)
    return payload


def _approx_bytes(p: dict) -> int:
    n = len(p["land"]) + len(p["d26"]["data"])
    n += sum(len(v["data"]) for v in p["fields"].values())
    n += sum(len(v) for v in p["luts"].values())
    return n


def _floats_for(date_str: str, window_days: int = 5) -> list:
    """Real Argo positions within a few days of the date. [] if the table is unavailable.

    Positions only -- this draws where independent observations exist, it does not compare
    against them. The comparison lives in the Validation feature, where it can be scored.
    """
    try:
        import pandas as pd

        from oceanembed import config as base
        p = base.art("argo_daily_period.parquet")
        if not os.path.exists(p):
            return []
        df = pd.read_parquet(p, columns=["lat", "lon", "date"])
        want = np.datetime64(str(date_str)[:10])
        d = pd.to_datetime(df["date"]).values.astype("datetime64[D]")
        keep = np.abs((d - want).astype("timedelta64[D]").astype(int)) <= window_days
        sub = df[keep].drop_duplicates(subset=["lat", "lon"])
        return [[float(a), float(b)] for a, b in zip(sub["lat"], sub["lon"])][:400]
    except Exception:
        return []


def render(payload: dict, *, key: str, height: int = 620, exaggeration: float = 40.0,
           field: str = "temperature", show_floats: bool = True, autorotate: bool = True):
    """Mount the scene. Returns whatever the scene last sent back, or None.

    The return value is {"lat": ..., "lon": ...} after a click on the water, which is what turns
    the picture into an instrument.
    """
    return _component()(
        payload=payload, exaggeration=float(exaggeration), field=field,
        showFloats=bool(show_floats), autorotate=bool(autorotate),
        height=int(height), key=key, default=None)
