"""Download monthly L4 wind + wind stress for the NIO box — Phase 2, unblocks upwelling detection.

OWNER: Unit B (Darshan). PHASE-2 ONLY. Does not touch the frozen baseline.

WHY A SEPARATE DOWNLOAD
The baseline has no wind data at all, so F6 upwelling could not be attributed to wind — and the
Phase-2 spec explicitly forbids inferring wind-driven upwelling without it.

WHICH PRODUCT, AND WHY THIS ONE  [VERIFIED 2026-08-26 by probing the CMEMS catalog]
    cmems_obs-wind_glo_phy_my_l4_0.25deg_PT1H   covers 1994-2009  -> TOO EARLY for our 2019-2022
    cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H covers 2024-2026  -> TOO LATE
    cmems_obs-wind_glo_phy_my_l4_P1M            covers 2022       -> USABLE, and monthly matches
                                                                     our monthly GLORYS cadence
There is a genuine gap in CMEMS hourly L4 wind coverage across 2019-2022. The monthly climate
product is the honest choice: same cadence as everything else we hold, so no false implication of
sub-monthly resolution.

VARIABLES [VERIFIED by probe]
    eastward_wind, northward_wind        m s-1
    eastward_stress, northward_stress    N m-2   <- these drive Ekman pumping, not wind speed
    wind_speed, wind_stress_magnitude

Upwelling is driven by wind STRESS CURL (Ekman pumping) and by alongshore stress (coastal Ekman
transport). Downloading stress directly avoids re-deriving it from wind speed with a drag
coefficient we would have to assume.

Run:  python -m phase2.data.download_wind
"""
from __future__ import annotations
import os
import pandas as pd
from oceanembed import config          # baseline config: IMPORTED, never modified

DATASET_ID = "cmems_obs-wind_glo_phy_my_l4_P1M"
VARIABLES = ["eastward_wind", "northward_wind",
             "eastward_stress", "northward_stress",
             "wind_speed", "wind_stress_magnitude"]
OUT_DIR = os.path.join(config.DATA_RAW, "wind")


def _fix_ssl() -> None:
    """Windows: point SSL at certifi's CA bundle (same fix the baseline downloaders use)."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def monthly_dates(years=None) -> list[pd.Timestamp]:
    """First of each month across the baseline's train+test years (monthly product is month-stamped)."""
    years = years or (list(config.TRAIN_YEARS) + list(config.TEST_YEARS))
    return [pd.Timestamp(year=y, month=m, day=1) for y in years for m in range(1, 13)]


def download_dates(dates=None, out_dir: str = OUT_DIR) -> str:
    """One NetCDF per month into data/raw/wind/. Skips months already present (resumable)."""
    _fix_ssl()
    import copernicusmarine

    dates = [pd.Timestamp(d) for d in (dates if dates is not None else monthly_dates())]
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    done, failed, mb = 0, [], 0.0

    for i, d in enumerate(dates, 1):
        fname = f"wind_{d:%Y%m}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            mb += os.path.getsize(fpath) / 1e6
            done += 1
            continue
        try:
            copernicusmarine.subset(
                dataset_id=DATASET_ID, variables=VARIABLES,
                minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                start_datetime=f"{d:%Y-%m-%d}", end_datetime=f"{d:%Y-%m-%d}",
                output_directory=out_dir, output_filename=fname, overwrite=True,
            )
            mb += os.path.getsize(fpath) / 1e6
            done += 1
            print(f"[wind] {i:3d}/{len(dates)} {d:%Y-%m} OK ({mb:.0f} MB total)")
        except Exception as e:
            failed.append(f"{d:%Y-%m}")
            print(f"[wind] {i:3d}/{len(dates)} {d:%Y-%m} FAILED: {type(e).__name__}: {str(e)[:70]}")

    print(f"\n[wind] {done}/{len(dates)} months, {mb:.0f} MB in {out_dir}")
    if failed:
        print(f"[wind] FAILED: {failed}  (re-run to retry only those)")
    return out_dir


if __name__ == "__main__":
    download_dates()
