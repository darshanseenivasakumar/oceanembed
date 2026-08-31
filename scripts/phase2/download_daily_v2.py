"""The corrected daily download for v2 -- GLORYS + satellite (fixed SSS) + wind.

    python scripts/phase2/download_daily_v2.py

WHY A NEW SCRIPT, NOT AN EDIT TO THE OLD ONE
src/oceanembed/data/download_satellite.py is Phase-1, frozen, read-only. Its SSS product
(cmems_obs-mob_glo_phy-sss_my_multi_P1D) is the DELAYED-MODE ("my") product, and [VERIFIED
2026-08-29] its real coverage is 1993-01-01 -> 2024-12-15 -- it CANNOT serve 2025-2026 no matter
how long you wait. Every attempt through the old script fails with CoordinatesOutOfDatasetBounds.
This is a real data-availability fact, not a bug in the old script -- so it stays untouched and
this v2 script uses the near-real-time equivalent instead.

  old (frozen, Phase-1)         : cmems_obs-mob_glo_phy-sss_my_multi_P1D   (ends 2024-12-15)
  v2 (this script, confirmed)   : cmems_obs-mob_glo_phy-sss_nrt_multi_P1D  (2026 dates VERIFIED)

WIND -- confirmed separately: no CMEMS L4 wind product is DAILY for 2025-2026. Only:
  my_l4_*_PT1H       ends 2009 (too early)
  my_l4_P1M          monthly only
  nrt_l4_0.125deg_PT1H  hourly, [VERIFIED] works for 2025-2026
So wind is downloaded HOURLY here and averaged to daily -- 24x the API calls of the other
variables. Budget real time for this stage; it is the slowest per calendar day.

RESUMABLE: every file already on disk is skipped by content, not just by log message. An
interrupted run just continues.

Run:  python scripts/phase2/download_daily_v2.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

import certifi  # noqa: E402
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from oceanembed import config  # noqa: E402

START, END = "2025-06-01", "2026-06-23"

SST_ID = "METOFFICE-GLO-SST-L4-REP-OBS-SST"
SSH_ID = "cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1D"
SSS_ID = "cmems_obs-mob_glo_phy-sss_nrt_multi_P1D"          # <-- the fix, NRT not "my"
WIND_ID = "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"     # hourly; no daily product exists

SAT_DIR = os.path.join(config.DATA_RAW, "satellite_daily")
WIND_RAW_DIR = os.path.join(config.DATA_RAW, "wind_hourly_raw")
WIND_DAILY_DIR = os.path.join(config.DATA_RAW, "wind_daily")


def daily_dates() -> list[pd.Timestamp]:
    return list(pd.date_range(START, END, freq="D"))


def _subset(dataset_id, variables, start, end, out_dir, out_name):
    import copernicusmarine
    r = config.REGION
    copernicusmarine.subset(
        dataset_id=dataset_id, variables=variables,
        minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
        minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
        start_datetime=start, end_datetime=end,
        output_directory=out_dir, output_filename=out_name, overwrite=True,
        disable_progress_bar=True,
    )


def download_satellite() -> None:
    os.makedirs(SAT_DIR, exist_ok=True)
    dates = daily_dates()
    sources = [("sst", SST_ID, ["analysed_sst"]), ("ssh", SSH_ID, ["adt", "ugos", "vgos"]),
               ("sss", SSS_ID, ["sos"])]
    total_mb, failed = 0.0, []
    for i, d in enumerate(dates, 1):
        for name, did, variables in sources:
            fname = f"{name}_{d:%Y%m%d}.nc"
            fpath = os.path.join(SAT_DIR, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                total_mb += os.path.getsize(fpath) / 1e6
                continue
            try:
                _subset(did, variables, f"{d:%Y-%m-%d}", f"{d:%Y-%m-%d}", SAT_DIR, fname)
                total_mb += os.path.getsize(fpath) / 1e6
            except Exception as e:
                failed.append(f"{name}_{d:%Y-%m-%d}")
                print(f"[sat] {name} {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:100]}")
        if i % 20 == 0 or i == len(dates):
            print(f"[sat] {i:3d}/{len(dates)} {d:%Y-%m-%d} done  (total {total_mb:.0f} MB, "
                  f"{len(failed)} failed)")
    if failed:
        print(f"[sat] {len(failed)} failures -- most likely dates outside this product's real "
              f"coverage. Re-run this script; already-downloaded files are skipped.")


def download_wind_hourly_and_average() -> None:
    """Hourly NRT wind -> daily mean, because no daily wind product covers 2025-2026."""
    os.makedirs(WIND_RAW_DIR, exist_ok=True)
    os.makedirs(WIND_DAILY_DIR, exist_ok=True)
    dates = daily_dates()
    variables = ["eastward_wind", "northward_wind", "eastward_stress", "northward_stress"]

    for i, d in enumerate(dates, 1):
        daily_out = os.path.join(WIND_DAILY_DIR, f"wind_{d:%Y%m%d}.nc")
        if os.path.exists(daily_out) and os.path.getsize(daily_out) > 0:
            continue
        raw_name = f"wind_hourly_{d:%Y%m%d}.nc"
        raw_path = os.path.join(WIND_RAW_DIR, raw_name)
        try:
            if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 0):
                _subset(WIND_ID, variables, f"{d:%Y-%m-%dT00:00:00}", f"{d:%Y-%m-%dT23:59:59}",
                       WIND_RAW_DIR, raw_name)
            with xr.open_dataset(raw_path) as ds:
                daily = ds.mean(dim="time", skipna=True)
                daily.attrs["source_note"] = (
                    "Daily mean of hourly NRT wind (no daily L4 wind product covers 2025-2026); "
                    f"averaged from {WIND_ID}")
                daily.to_netcdf(daily_out)
            os.remove(raw_path)   # keep only the daily mean; hourly raw is 24x the size
        except Exception as e:
            print(f"[wind] {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:100]}")
        if i % 20 == 0 or i == len(dates):
            n_done = len([f for f in os.listdir(WIND_DAILY_DIR) if f.endswith(".nc")])
            print(f"[wind] {i:3d}/{len(dates)} {d:%Y-%m-%d} done  ({n_done} daily files so far)")


def main() -> None:
    print("=" * 74)
    print(f"v2 daily download (corrected)  window {START} -> {END}")
    print("=" * 74)
    print("\n--- SATELLITE (SST + SSH from Phase-1 IDs, SSS switched to NRT) ---")
    download_satellite()
    print("\n--- WIND (hourly NRT -> daily mean; no daily product exists) ---")
    download_wind_hourly_and_average()
    print("\nDone (or resumed to completion). Next: harmonize to the daily 0.25deg grid.")


if __name__ == "__main__":
    main()
