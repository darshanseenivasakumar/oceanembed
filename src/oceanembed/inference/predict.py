"""THE integration seam: reconstruct() ties A's model + A's uncertainty + C's climatology/anomaly + A's priority.

OWNER: Unit B (Darshan).

DESIGN NOTE — graceful degradation: optional products (anomaly, observation-priority) are imported lazily and
wrapped in try/except. The seam works TODAY with just the model + climatology, and automatically lights up when
Unit A implements observation_priority() and Unit C implements anomaly(). Nobody is blocked.
"""
from __future__ import annotations
import functools
import os
import warnings
import numpy as np
import pandas as pd
from oceanembed import config
from oceanembed.utils import io, grids


# ----------------------------------------------------------------------------- surface source
# The model is TRAINED on GLORYS surface fields. It can be RUN on either those or on real satellite
# L4 fields (SIH26066 asks for "surface satellite observations"). Switching source changes only
# where the 11 input features come from -- the model, climatology and products are unchanged.
_SOURCES = {
    "glorys": "grids.npz",              # GLORYS surface fields (same source as training)
    "satellite": "satellite_grids.npz",  # real OSTIA / DUACS / Multiobs L4  <- domain shift
}
_source = "glorys"


def set_source(source: str) -> str:
    """Switch the surface-field source. Returns the active source."""
    global _source
    if source not in _SOURCES:
        raise ValueError(f"source must be one of {sorted(_SOURCES)}, got {source!r}")
    if source != _source:
        _source = source
        _grids.cache_clear()          # the grids differ; stale cache would silently mix sources
    return _source


def current_source() -> str:
    return _source


def source_available(source: str) -> bool:
    return os.path.exists(os.path.join(config.DATA_PROCESSED, _SOURCES[source]))


# ----------------------------------------------------------------------------- cached loaders
@functools.lru_cache(maxsize=1)
def _grids():
    """Surface (and, for GLORYS, subsurface) grids for the ACTIVE source."""
    p = os.path.join(config.DATA_PROCESSED, _SOURCES[_source])
    if not os.path.exists(p):
        hint = ("run `python scripts/prepare_dataset.py`" if _source == "glorys"
                else "run `python -m oceanembed.data.download_satellite` then "
                     "`python -m oceanembed.data.preprocess_satellite`")
        raise FileNotFoundError(f"{p} missing — {hint} first.")
    g = dict(np.load(p, allow_pickle=False))
    g["times"] = g["times"].astype("datetime64[D]")
    return g


@functools.lru_cache(maxsize=1)
def _model():
    from oceanembed.models.mlp_profile import load_mlp
    return load_mlp(config.art("mlp_model.pt"))


@functools.lru_cache(maxsize=1)
def provenance() -> dict:
    """Read the provenance stamp written by build_samples (D-018).

    Read from the ARTIFACTS, never inferred from data/raw/ -- artifacts/ is portable and
    data/raw/ is gitignored, so inference would silently read "real" on a demo laptop.
    """
    p = config.art("provenance.json")
    if os.path.exists(p):
        d = dict(io.load_json(p))
        d["inference_source"] = _source          # what the CURRENT run is reading surface fields from
        return d
    return {"source": "unknown", "built": None,
            "note": "artifacts/provenance.json missing -- rebuild with scripts/prepare_dataset.py"}


@functools.lru_cache(maxsize=1)
def _climatology():
    p = config.art("climatology.npy")
    return io.load_npy(p) if os.path.exists(p) else None


def available_dates() -> list:
    """Dates present in the processed grids (what the UI may offer)."""
    return [pd.Timestamp(t).date() for t in _grids()["times"]]


# ----------------------------------------------------------------------------- feature assembly
def _nearest_time_index(date) -> int:
    times = _grids()["times"].astype("datetime64[D]")
    target = np.datetime64(pd.Timestamp(date).date(), "D")
    return int(np.argmin(np.abs((times - target).astype("timedelta64[D]").astype(int))))


def _features_at(i_lat: int, i_lon: int, t_idx: int) -> np.ndarray:
    g = _grids()
    la, lo = float(config.LAT[i_lat]), float(config.LON[i_lon])
    sl, cl, so, co = grids.latlon_features(la, lo)
    doy = pd.Timestamp(g["times"][t_idx]).dayofyear
    sd, cd = grids.day_of_year_features(doy)
    return np.array([g["sst"][t_idx, i_lat, i_lon], g["sss"][t_idx, i_lat, i_lon],
                     g["ssh"][t_idx, i_lat, i_lon], g["u"][t_idx, i_lat, i_lon],
                     g["v"][t_idx, i_lat, i_lon], sl, cl, so, co, sd, cd], dtype="float32")


def _reliability(std: np.ndarray) -> list[str]:
    """Map MC-dropout std to a coarse label. Thresholds are calibrated on the test set — see
    VALIDATION_PROTOCOL.md. Never invent confidence numbers beyond what the spread supports."""
    out = []
    for s in std:
        out.append("HIGH" if s < 0.25 else ("MEDIUM" if s < 0.6 else "LOW"))
    return out


# ----------------------------------------------------------------------------- public API
def reconstruct(lat: float, lon: float, date) -> dict:
    """Single-point reconstruction.

    Returns {lat, lon, date, depths[15], surface{...}, profile_mean[15], profile_std[15],
             reliability[15], climatology[15]|None, anomaly[15]|None, is_land}
    """
    from oceanembed.inference.uncertainty import mc_dropout_predict

    i, j = grids.nearest_lat_index(lat), grids.nearest_lon_index(lon)
    t = _nearest_time_index(date)
    g = _grids()

    if bool(g["land_mask"][i, j]) or np.isnan(g["sst"][t, i, j]):
        return dict(lat=float(config.LAT[i]), lon=float(config.LON[j]),
                    date=pd.Timestamp(g["times"][t]).date(), is_land=True,
                    depths=config.DEPTHS, profile_mean=None, profile_std=None,
                    reliability=None, climatology=None, anomaly=None, surface=None)

    # RAW features straight through: the model normalizes internally (D-009).
    Xraw = _features_at(i, j, t)[None, :]
    mean, std = mc_dropout_predict(_model(), Xraw)
    mean, std = mean[0], std[0]

    clim = _climatology()
    month = pd.Timestamp(g["times"][t]).month
    clim_prof = clim[month - 1, i, j] if clim is not None else None

    anom = None
    if clim_prof is not None:
        try:  # Unit C's anomaly() when available; else the plain definition
            from oceanembed.products.anomaly import anomaly as _anom
            anom = _anom(mean[None, None, :], clim, month)[0, 0]
        except (NotImplementedError, ImportError, Exception):
            anom = (mean - clim_prof).astype("float32")

    return dict(
        lat=float(config.LAT[i]), lon=float(config.LON[j]),
        date=pd.Timestamp(g["times"][t]).date(), is_land=False,
        depths=list(config.DEPTHS),
        surface={k: float(g[k][t, i, j]) for k in ["sst", "sss", "ssh", "u", "v"]},
        profile_mean=mean.astype("float32"), profile_std=std.astype("float32"),
        reliability=_reliability(std), climatology=clim_prof, anomaly=anom,
    )


def reconstruct_grid(date, with_uncertainty: bool = True) -> dict:
    """Whole-grid reconstruction for maps.

    Returns {date, temp(100,240,15), uncertainty(100,240,15)|None, anomaly(100,240,15)|None,
             priority(100,240)|None, land_mask(100,240)}
    """
    from oceanembed.models.mlp_profile import predict_mlp
    from oceanembed.inference.uncertainty import mc_dropout_predict

    t = _nearest_time_index(date)
    g = _grids()
    ocean = ~g["land_mask"] & ~np.isnan(g["sst"][t])
    ii, jj = np.where(ocean)

    X = np.stack([_features_at(int(i), int(j), t) for i, j in zip(ii, jj)])  # RAW (D-009)

    shape = (config.N_LAT, config.N_LON, config.N_DEPTHS)
    temp = np.full(shape, np.nan, dtype="float32")
    unc = np.full(shape, np.nan, dtype="float32") if with_uncertainty else None

    if with_uncertainty:
        mean, std = mc_dropout_predict(_model(), X)
        temp[ii, jj] = mean
        unc[ii, jj] = std
    else:
        temp[ii, jj] = predict_mlp(_model(), X)

    month = pd.Timestamp(g["times"][t]).month
    clim = _climatology()
    anom = None
    if clim is not None:
        anom = (temp - clim[month - 1]).astype("float32")

    # Observation-priority: Unit A's module when implemented; otherwise None (UI hides the panel).
    priority = None
    if anom is not None and unc is not None:
        try:
            from oceanembed.products.observation_priority import observation_priority
            sparsity = _argo_sparsity()
            with warnings.catch_warnings():  # land columns are all-NaN by design
                warnings.simplefilter("ignore", RuntimeWarning)
                a2d = np.nanmean(np.abs(anom), axis=2)
                u2d = np.nanmean(unc, axis=2)
            priority = observation_priority(a2d, u2d, sparsity)
        except Exception:
            priority = None  # not implemented yet — expected before Unit A lands it

    return dict(date=pd.Timestamp(g["times"][t]).date(), temp=temp, uncertainty=unc,
                anomaly=anom, priority=priority, land_mask=g["land_mask"])


def _argo_sparsity() -> np.ndarray:
    """Distance (in grid cells) to the nearest Argo observation; uniform if no Argo file yet."""
    try:
        df = io.load_table(config.art("argo_test"))
        from scipy.ndimage import distance_transform_edt
        has = np.zeros((config.N_LAT, config.N_LON), dtype=bool)
        for la, lo in zip(df["lat"], df["lon"]):
            has[grids.nearest_lat_index(la), grids.nearest_lon_index(lo)] = True
        return distance_transform_edt(~has).astype("float32")
    except Exception:
        return np.ones((config.N_LAT, config.N_LON), dtype="float32")
