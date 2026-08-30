"""Download DAILY wind (u, v) for the 2025-06..2026-06 daily bundle — PS requirement 8.

OWNER: Unit B (Darshan). PHASE-2 ONLY. Does not touch the frozen baseline.

WHY THIS PRODUCT  [VERIFIED 2026-08-30 by probing the CMEMS catalog from this machine]
Listing every `obs-wind` dataset showed exactly ONE gap-filled global L4 product covering our
window:
    cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H   time 2024-06-13 .. 2026-08-27, step 1 h
Every other global NRT wind dataset is L3 `-i` (instantaneous per-satellite ascending/descending
swaths: metopb/metopc ASCAT, oceansat3/scatsat1 OSCAT). Those are swath products with large daily
gaps over our box — not a field. There is NO daily (P1D) or monthly (P1M) L4 global variant; both
were probed by dataset_id and returned DatasetNotFound. So hourly L4 + our own daily mean is the
only honest route, not a preference.

The monthly sibling `download_wind.py` uses `cmems_obs-wind_glo_phy_my_l4_P1M` — a DIFFERENT
product for a DIFFERENT window (2019-2022). Do not mix their outputs.

THE GRID TRAP  [VERIFIED from the catalog's own coordinate metadata]
    wind latitude  -89.9375 .. 89.9375  step 0.125
    wind longitude -179.9375 .. 179.9375 step 0.125
Grid points sit at (k + 0.5) * 0.125, i.e. offset 0.0625 from every multiple of 0.125. There is
NO wind point at exactly 5.00 N or 45.00 E, so `config.LAT` / `config.LON` values do not appear in
this product at all. Assigning by array position would put every value ~7-14 km from where it is
claimed to be — the same class of bug that shifted 75.5% of Argo collocations (trap #4) and the
+0.125 deg offset already found in the monthly wind grid (trap #5).

We therefore regrid EXPLICITLY BY COORDINATE, never by position: each 0.25 deg target cell centred
on config.LAT[i]/config.LON[j] spans +/-0.125 deg and contains exactly 2 x 2 = 4 wind points. The
daily mean of those four is the cell value. That is an exact block average, not an interpolation,
and `regrid_to_config()` asserts the 2x2 structure instead of assuming it.

VARIABLES
    eastward_wind, northward_wind   m s-1   -> contract channels "wu", "wv"
Stress variables exist in this product but the frozen contract (docs/phase2/tscast_data_model.md)
names wind velocity, not stress. Downloading stress too would double the transfer for a channel no
reader indexes.

Run:  PYTHONPATH=src python -m phase2.data.download_wind_daily          # download, resumable
      PYTHONPATH=src python -m phase2.data.download_wind_daily --process  # + build the npz
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from oceanembed import config  # baseline config: IMPORTED, never modified

DATASET_ID = "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"
VARIABLES = ["eastward_wind", "northward_wind"]

# Same window as the daily GLORYS bundle (scripts/phase2/download_daily_2025_2026.py).
START, END = "2025-06-01", "2026-06-23"

OUT_DIR = os.path.join(config.DATA_RAW, "wind_daily")
NPZ_PATH = os.path.join(config.DATA_PROCESSED, "wind_daily.npz")

SRC_STEP = 0.125          # native wind grid spacing [VERIFIED from catalog]
TGT_STEP = 0.25           # config.REGION["step"]
BLOCK = int(round(TGT_STEP / SRC_STEP))   # 2 source cells per target cell, per axis


def _fix_ssl() -> None:
    """Windows: point SSL at certifi's CA bundle (same fix every downloader here uses)."""
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def request_bounds() -> dict[str, float]:
    """The lat/lon box to ASK CMEMS for, in source-grid terms.

    config.LAT[0]=5.00 is a CELL CENTRE, so its cell spans 4.875..5.125. We must request the full
    span of the outermost target cells, not their centres, or the edge cells lose half their
    source points. Half a target cell = TGT_STEP/2 = 0.125.
    """
    half = TGT_STEP / 2.0
    return {
        "minimum_latitude": float(config.LAT[0]) - half,
        "maximum_latitude": float(config.LAT[-1]) + half,
        "minimum_longitude": float(config.LON[0]) - half,
        "maximum_longitude": float(config.LON[-1]) + half,
    }


def month_starts(start: str = START, end: str = END) -> list[pd.Timestamp]:
    """One chunk per calendar month — small enough to retry, large enough to be efficient."""
    return list(pd.date_range(pd.Timestamp(start).normalize().replace(day=1),
                              pd.Timestamp(end), freq="MS"))


def download_months(months=None, out_dir: str = OUT_DIR) -> str:
    """One hourly NetCDF per month into data/raw/wind_daily/. Skips months already present."""
    _fix_ssl()
    import copernicusmarine

    months = [pd.Timestamp(m) for m in (months if months is not None else month_starts())]
    os.makedirs(out_dir, exist_ok=True)
    b = request_bounds()
    window_start, window_end = pd.Timestamp(START), pd.Timestamp(END)
    done, failed, mb = 0, [], 0.0

    for i, m in enumerate(months, 1):
        # Clip each month to the bundle window so we never fetch days GLORYS does not have.
        m0 = max(m, window_start)
        m1 = min(m + pd.offsets.MonthEnd(0), window_end)
        fname = f"wind_hourly_{m:%Y%m}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            mb += os.path.getsize(fpath) / 1e6
            done += 1
            print(f"[wind] {i:2d}/{len(months)} {m:%Y-%m} skip (present)", flush=True)
            continue
        try:
            copernicusmarine.subset(
                dataset_id=DATASET_ID, variables=VARIABLES,
                start_datetime=f"{m0:%Y-%m-%d}T00:00:00",
                end_datetime=f"{m1:%Y-%m-%d}T23:00:00",
                output_directory=out_dir, output_filename=fname, overwrite=True,
                **b,
            )
            mb += os.path.getsize(fpath) / 1e6
            done += 1
            print(f"[wind] {i:2d}/{len(months)} {m:%Y-%m} OK ({mb:.0f} MB total)", flush=True)
        except Exception as e:
            failed.append(f"{m:%Y-%m}")
            print(f"[wind] {i:2d}/{len(months)} {m:%Y-%m} FAILED: "
                  f"{type(e).__name__}: {str(e)[:80]}", flush=True)

    print(f"\n[wind] {done}/{len(months)} months, {mb:.0f} MB in {out_dir}")
    if failed:
        print(f"[wind] FAILED: {failed}  (re-run to retry only those)")
    return out_dir


# ---------------------------------------------------------------------------------------------
# hourly -> daily mean -> 0.125 deg -> 0.25 deg, by coordinate
# ---------------------------------------------------------------------------------------------

def _target_index(src_coord: np.ndarray, target: np.ndarray, axis_name: str) -> np.ndarray:
    """Map every SOURCE coordinate to the index of the target cell that CONTAINS it.

    By value, never by position. `floor((x - target[0]) / TGT_STEP + 0.5)` is the cell whose
    centre is nearest; we then prove the point really lies inside that cell.
    """
    idx = np.floor((src_coord - target[0]) / TGT_STEP + 0.5).astype(int)
    if idx.min() < 0 or idx.max() >= len(target):
        raise ValueError(
            f"{axis_name}: source range {src_coord.min():.4f}..{src_coord.max():.4f} falls outside "
            f"the target grid {target[0]:.4f}..{target[-1]:.4f}. Re-request with request_bounds()."
        )
    off = np.abs(src_coord - target[idx])
    if off.max() > TGT_STEP / 2 + 1e-6:
        raise ValueError(
            f"{axis_name}: a source point sits {off.max():.4f} deg from its assigned cell centre, "
            f"more than the {TGT_STEP / 2} deg half-width. The grids do not nest."
        )
    return idx


def regrid_to_config(src_lat: np.ndarray, src_lon: np.ndarray, field: np.ndarray) -> np.ndarray:
    """Block-average a (..., nlat_src, nlon_src) field onto config.LAT x config.LON.

    Returns (..., 100, 240). Raises if the source grid does not nest exactly BLOCK x BLOCK inside
    the target grid — we refuse rather than silently interpolate a grid we did not expect.
    """
    lat_i = _target_index(np.asarray(src_lat, dtype=np.float64), config.LAT, "latitude")
    lon_j = _target_index(np.asarray(src_lon, dtype=np.float64), config.LON, "longitude")

    # Every target cell must receive exactly BLOCK source points on each axis. A short count means
    # the request box was clipped; a long one means the source step is not what the catalog said.
    for idx, target, name in ((lat_i, config.LAT, "latitude"), (lon_j, config.LON, "longitude")):
        counts = np.bincount(idx, minlength=len(target))
        if not np.all(counts == BLOCK):
            bad = np.flatnonzero(counts != BLOCK)
            raise ValueError(
                f"{name}: {len(bad)} of {len(target)} target cells do not hold exactly {BLOCK} "
                f"source points (e.g. cell {bad[0]} at {target[bad[0]]:.3f} holds "
                f"{counts[bad[0]]}). Refusing to regrid a grid that does not nest."
            )

    # A correct COUNT is not a correct PLACEMENT: a grid shifted by less than half a cell still
    # puts BLOCK points in every cell, just off-centre, which would bias every value by that shift.
    # The invariant that actually pins the grid down is that each block's centroid IS the target
    # centre -- true for a nested grid by symmetry, false for any shift.
    for idx, src, target, name in ((lat_i, np.asarray(src_lat, dtype=np.float64), config.LAT, "latitude"),
                                   (lon_j, np.asarray(src_lon, dtype=np.float64), config.LON, "longitude")):
        centroid = np.bincount(idx, weights=src, minlength=len(target)) / BLOCK
        drift = np.abs(centroid - target)
        if drift.max() > 1e-4:
            k = int(np.argmax(drift))
            raise ValueError(
                f"{name}: cell {k} is centred on {target[k]:.5f} but its {BLOCK} source points "
                f"average {centroid[k]:.5f} -- a {drift.max() * 111:.1f} km offset. The source grid "
                f"is shifted relative to config; block-averaging it would misplace every value."
            )

    # Sorted + exact nesting means a plain reshape IS the block grouping. Assert it, don't assume.
    if not (np.all(np.diff(lat_i) >= 0) and np.all(np.diff(lon_j) >= 0)):
        raise ValueError("source coordinates are not monotonically increasing; sort before regrid")

    lead = field.shape[:-2]
    blocked = field.reshape(*lead, len(config.LAT), BLOCK, len(config.LON), BLOCK)
    with np.errstate(invalid="ignore"):
        out = np.nanmean(blocked, axis=(-3, -1))
    return out.astype(np.float32)


def build_daily_wind(raw_dir: str = OUT_DIR, out_path: str = NPZ_PATH) -> str:
    """Read the monthly hourly files, average each day, regrid, and write one npz.

    Output keys:
        dates  (T,) <U8   YYYYMMDD, sorted, one per day
        wu     (T, 100, 240) float32  eastward wind, m s-1, daily mean, on config.LAT/LON
        wv     (T, 100, 240) float32  northward wind, same
        lat, lon                      the target grid, written so readers can VERIFY it
    """
    import xarray as xr

    files = sorted(f for f in os.listdir(raw_dir) if f.startswith("wind_hourly_") and f.endswith(".nc"))
    if not files:
        raise FileNotFoundError(f"no wind_hourly_*.nc in {raw_dir} -- run download_months() first")

    dates: list[str] = []
    wu_all: list[np.ndarray] = []
    wv_all: list[np.ndarray] = []

    for k, f in enumerate(files, 1):
        ds = xr.open_dataset(os.path.join(raw_dir, f))
        try:
            # Coordinate names are asserted, not assumed -- a renamed axis must fail loudly.
            for c in ("latitude", "longitude", "time"):
                if c not in ds.coords:
                    raise KeyError(f"{f}: expected coordinate '{c}', found {list(ds.coords)}")
            daily = ds[VARIABLES].resample(time="1D").mean()
            src_lat = daily["latitude"].values
            src_lon = daily["longitude"].values
            for var, sink in (("eastward_wind", wu_all), ("northward_wind", wv_all)):
                arr = np.asarray(daily[var].values, dtype=np.float32)
                arr = np.squeeze(arr)                      # drop a singleton depth/height axis
                if arr.ndim != 3:
                    raise ValueError(f"{f}: {var} is {arr.shape} after squeeze, expected (T,lat,lon)")
                sink.append(regrid_to_config(src_lat, src_lon, arr))
            dates.extend(pd.to_datetime(daily["time"].values).strftime("%Y%m%d").tolist())
            print(f"[wind] {k:2d}/{len(files)} {f} -> {len(daily['time'])} days", flush=True)
        finally:
            ds.close()

    order = np.argsort(np.asarray(dates))
    d = np.asarray(dates, dtype="<U8")[order]
    wu = np.concatenate(wu_all, axis=0)[order]
    wv = np.concatenate(wv_all, axis=0)[order]
    if len(np.unique(d)) != len(d):
        raise ValueError(f"duplicate dates after concatenation: {len(d) - len(np.unique(d))} repeats")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.savez_compressed(out_path, dates=d, wu=wu, wv=wv, lat=config.LAT, lon=config.LON)
    nan = float(np.isnan(wu).mean())
    print(f"\n[wind] wrote {out_path}")
    print(f"       {len(d)} days {d[0]}..{d[-1]}, grid {wu.shape[1:]}, {nan:.1%} NaN (land)")
    print(f"       |wind| mean {float(np.nanmean(np.hypot(wu, wv))):.2f} m/s")
    return out_path


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true", help="also build the npz after downloading")
    ap.add_argument("--process-only", action="store_true", help="skip the download")
    ap.add_argument("--raw-dir", default=OUT_DIR)
    ap.add_argument("--out", default=NPZ_PATH)
    a = ap.parse_args()
    if not a.process_only:
        download_months(out_dir=a.raw_dir)
    if a.process or a.process_only:
        build_daily_wind(raw_dir=a.raw_dir, out_path=a.out)


if __name__ == "__main__":
    main()
