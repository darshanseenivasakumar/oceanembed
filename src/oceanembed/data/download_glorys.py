"""Download GLORYS12 (CMEMS reanalysis) surface+subsurface fields for the NIO box.

OWNER: Unit B (Darshan).

Dataset id [VERIFIED 2026-08-25 via `copernicusmarine.describe(contains=['GLOBAL_MULTIYEAR_PHY_001_030'])`]:
  cmems_mod_glo_phy_my_0.083deg_P1D-m   <- GLORYS12V1 daily means
The catalog listing works WITHOUT login; `subset` DOES need a free CMEMS account:
    copernicusmarine login          (password input is HIDDEN as you type — that is normal)

MEASURED COST [VERIFIED 2026-08-25]: one day, all 5 variables, 0-520 m, full NIO box
  = 54.3 MB and ~127 s.  Full daily 2019-2022 would be ~79 GB / ~51 h -> NOT feasible.
=> We subsample DATES (default: one per month). 48 dates ~= 2.6 GB, ~100 min, and still yields
   ~1.15M training rows (each date contributes ~24k ocean cells x 15 depths).

Resumable: a date whose file already exists is skipped, so an interrupted run just continues.

Run:  python -m oceanembed.data.download_glorys
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
from oceanembed import config

DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
VARIABLES = ["thetao", "so", "zos", "uo", "vo"]
# Must BRACKET the deepest target level. GLORYS levels are discrete (..., 453.9, 541.1, 643.6,
# 763.3, 902.3, 1062.4, ...), so a cap of 520 m actually stopped the data at 453.9 m and every
# 500 m value was EXTRAPOLATED. 1100 m pulls in the 1062.4 m level so 1000 m is interpolated.
MIN_DEPTH, MAX_DEPTH = 0.0, 1100.0


def _fix_ssl() -> None:
    """Windows: point SSL at certifi's CA bundle (same fix as download_argo)."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def monthly_dates(years=None, day: int = 15) -> list[pd.Timestamp]:
    """One date per month across the train+test years (default the 15th)."""
    years = years or (list(config.TRAIN_YEARS) + list(config.TEST_YEARS))
    return [pd.Timestamp(year=y, month=m, day=day) for y in years for m in range(1, 13)]


def download_dates(dates=None, out_dir: str | None = None, dataset_id: str = DATASET_ID,
                   variables=VARIABLES) -> str:
    """Download one NetCDF per date into data/raw/. Skips dates already on disk (resumable)."""
    _fix_ssl()
    import copernicusmarine  # imported here so the repo imports without the package installed

    dates = list(dates) if dates is not None else monthly_dates()
    out_dir = out_dir or config.DATA_RAW
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION

    done, failed, total_mb = 0, [], 0.0
    for i, d in enumerate(dates, 1):
        d = pd.Timestamp(d)
        fname = f"glorys_{d:%Y%m%d}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            total_mb += os.path.getsize(fpath) / 1e6
            print(f"[glorys] {i:3d}/{len(dates)} {d:%Y-%m-%d} already present, skipping")
            done += 1
            continue
        try:
            copernicusmarine.subset(
                dataset_id=dataset_id, variables=variables,
                minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                minimum_depth=MIN_DEPTH, maximum_depth=MAX_DEPTH,
                start_datetime=f"{d:%Y-%m-%d}", end_datetime=f"{d:%Y-%m-%d}",
                output_directory=out_dir, output_filename=fname, overwrite=True,
            )
            mb = os.path.getsize(fpath) / 1e6
            total_mb += mb
            done += 1
            print(f"[glorys] {i:3d}/{len(dates)} {d:%Y-%m-%d} OK  {mb:.1f} MB  (total {total_mb/1000:.2f} GB)")
        except Exception as e:  # one bad date must not kill the run
            failed.append(str(d.date()))
            print(f"[glorys] {i:3d}/{len(dates)} {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:100]}")

    print(f"\n[glorys] done: {done}/{len(dates)} dates, {total_mb/1000:.2f} GB in {out_dir}")
    if failed:
        print(f"[glorys] FAILED dates ({len(failed)}): {failed}\n  re-run this command to retry only those.")
    print("NEXT: python scripts/prepare_dataset.py --real")
    return out_dir


# Back-compat alias
def download(*a, **k):
    return download_dates(*a, **k)


if __name__ == "__main__":
    download_dates()
