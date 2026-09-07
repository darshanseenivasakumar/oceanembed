"""Download the multi-year daily GLORYS baseline for marine-heatwave thresholds.

OWNER: Unit A (Arjhun / MHW feature). Reuses the EXACT copernicusmarine.subset() call proven in
src/oceanembed/data/download_glorys.py [VERIFIED 2026-08-25], changed only to:
  - pull TEMPERATURE ONLY (`thetao`) -- the 90th-percentile threshold is temperature-only, so
    salinity/currents are not downloaded here (halves the transfer). The Benthic Decoupling Index
    uses salinity from the DETECTION-period bundle, which already exists on disk.
  - fetch a whole YEAR per request (one .nc per year) instead of one file per day. A single subset
    call streams the full date range server-side; 3 requests beat ~1000 per-day requests by a mile.

Resumable: a year whose file already exists and is non-empty is skipped, so an interrupted run
continues where it stopped.

WHY THESE YEARS: the pilot baseline is 2019-2021 -- the same reference period the project's existing
monthly climatology uses (`config.TRAIN_YEARS`), so the pilot is consistent with the rest of the
repo, and it is DISJOINT from the 2025-2026 detection window (a heatwave must be measured against a
period it did not occur in). A 3-year baseline is a PILOT: enough to validate the pipeline, not the
30-year climatological standard. Extend --start/--end for the full baseline later.

Run:  PYTHONPATH=src python scripts/phase2/download_mhw_baseline.py            # 2019-2021, thetao
      PYTHONPATH=src python scripts/phase2/download_mhw_baseline.py --start 2011 --end 2020
"""
from __future__ import annotations

import argparse
import os

from oceanembed import config

DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"   # GLORYS12V1 daily means (same as the repo)
VARIABLES = ["thetao"]                                # temperature only -- threshold is T-only
MIN_DEPTH, MAX_DEPTH = 0.0, 1100.0                    # bracket 1000 m (GLORYS level 1062.4 m)


def _fix_ssl() -> None:
    """Windows: point SSL at certifi's CA bundle (same fix the other downloaders use)."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def download_years(start: int = 2019, end: int = 2021, out_dir: str | None = None) -> str:
    """One NetCDF per calendar year of daily `thetao` over the NIO box. Resumable by year."""
    _fix_ssl()
    import copernicusmarine  # imported here so the repo imports without the package installed

    out_dir = out_dir or os.path.join(config.DATA_RAW, "glorys_mhw_baseline")
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    years = list(range(start, end + 1))

    done, failed, total_gb = 0, [], 0.0
    for i, y in enumerate(years, 1):
        fname = f"glorys_thetao_{y}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            total_gb += os.path.getsize(fpath) / 1e9
            print(f"[mhw-baseline] {i}/{len(years)} {y} already present, skipping", flush=True)
            done += 1
            continue
        try:
            print(f"[mhw-baseline] {i}/{len(years)} {y} downloading daily thetao ...", flush=True)
            copernicusmarine.subset(
                dataset_id=DATASET_ID, variables=VARIABLES,
                minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                minimum_depth=MIN_DEPTH, maximum_depth=MAX_DEPTH,
                start_datetime=f"{y}-01-01T00:00:00", end_datetime=f"{y}-12-31T23:59:59",
                output_directory=out_dir, output_filename=fname, overwrite=True,
            )
            gb = os.path.getsize(fpath) / 1e9
            total_gb += gb
            done += 1
            print(f"[mhw-baseline] {i}/{len(years)} {y} OK  {gb:.2f} GB  (total {total_gb:.2f} GB)",
                  flush=True)
        except Exception as e:
            failed.append(str(y))
            print(f"[mhw-baseline] {i}/{len(years)} {y} FAILED: {type(e).__name__}: {str(e)[:120]}",
                  flush=True)

    print(f"\n[mhw-baseline] done: {done}/{len(years)} years, {total_gb:.2f} GB in {out_dir}",
          flush=True)
    if failed:
        print(f"[mhw-baseline] FAILED years: {failed} -- re-run to retry only those.", flush=True)
    return out_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2019)
    ap.add_argument("--end", type=int, default=2021)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    download_years(a.start, a.end, a.out_dir)
