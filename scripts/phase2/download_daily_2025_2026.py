"""Download the DAILY 2025-06 -> 2026-06 data bundle for OceanEmbed v2 (TS-Cast-NIO).

    python scripts/phase2/download_daily_2025_2026.py

Runs in the background overnight. RESUMABLE: any file already on disk is skipped, so an interrupted
run (or a college network drop) just continues where it stopped. CMEMS login is already saved
(~/.copernicusmarine-credentials) -- no password is entered or stored here.

Order is by size: GLORYS (the ~13 h bottleneck) first, then the three satellite L4 products.
Wind (NRT daily) and Argo are small/fast and handled by their own scripts -- not this overnight job.

Everything lands in data/raw/*_daily/ (gitignored). Progress is printed with a running total so
`tail -f data/raw/download_daily.log` shows how far along it is.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

import certifi  # noqa: E402
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import pandas as pd  # noqa: E402

from oceanembed import config  # noqa: E402
from oceanembed.data import download_glorys, download_satellite  # noqa: E402

START, END = "2025-06-01", "2026-06-23"   # daily window; GLORYS my product covers to 2026-06-23


def daily_dates() -> list[pd.Timestamp]:
    return list(pd.date_range(START, END, freq="D"))


def main() -> None:
    dates = daily_dates()
    print(f"[daily] window {START} -> {END}  =  {len(dates)} days")
    print(f"[daily] region {config.REGION}")
    print("[daily] resumable: existing files are skipped\n")

    # 1) GLORYS daily -- surface fields + subsurface temperature target, 0-1100 m.
    glorys_dir = os.path.join(config.DATA_RAW, "glorys_daily")
    print(f"[daily] === GLORYS daily -> {glorys_dir} ===")
    download_glorys.download_dates(dates=dates, out_dir=glorys_dir)

    # 2) Satellite L4 daily -- SST, SSH (adt+geostrophic currents), SSS.
    sat_dir = os.path.join(config.DATA_RAW, "satellite_daily")
    print(f"\n[daily] === Satellite L4 daily -> {sat_dir} ===")
    download_satellite.download_dates(dates=dates, out_dir=sat_dir)

    print("\n[daily] DONE (or resumed to completion). Next: wind (NRT daily) + Argo, via their own "
          "scripts. Then Darshan preprocesses to 0.25 deg daily.")


if __name__ == "__main__":
    main()
