"""Fetch REAL Argo profiles covering the DAILY period (2025-06-01 .. 2026-06-23).

Why this is needed: artifacts/argo_test.parquet is 2022 ONLY. The daily bundle is 2025-2026, so
the daily model currently has no independent validation source at all -- only held-out GLORYS,
which is our training truth. Every headline number this project quotes (0.9638, 0.9672) is against
independent floats, and the daily model cannot have an equivalent without these.

Reuses oceanembed.data.download_argo.download(), which already does the month-by-month fetch, the
QC filter (flags 1 and 2 only) and the interpolation onto config.DEPTHS.

WRITES TO SEPARATE FILES. download()'s default output is artifacts/argo_test, which is the 2022 set
the published validation rests on; overwriting it would destroy the only independent check we have
for the monthly model and there would be no way to notice from the numbers.

Run:  PYTHONPATH=src python scripts/phase2/fetch_argo_daily_period.py
"""
from __future__ import annotations

import os

import pandas as pd

from oceanembed import config
from oceanembed.data import download_argo
from oceanembed.utils import io

START, END = pd.Timestamp("2025-06-01"), pd.Timestamp("2026-06-23")
OUT = config.art("argo_daily_period")


def main() -> None:
    guard = config.art("argo_test.parquet")
    before = os.path.getmtime(guard) if os.path.exists(guard) else None

    frames = []
    for year in (2025, 2026):
        path = config.art(f"argo_{year}")
        print(f"\n=== Argo {year} ===", flush=True)
        try:
            written = download_argo.download(year=year, out_noext=path)
            frames.append(pd.read_parquet(written))
        except Exception as e:
            print(f"[argo] {year} FAILED: {type(e).__name__}: {e}")

    if not frames:
        raise SystemExit("no Argo data fetched -- nothing written")

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    n_all = len(df)
    df = df[(df["date"] >= START) & (df["date"] <= END)]
    path = io.save_table(df, OUT)

    prof = df.groupby(["lat", "lon", "date"]).ngroups
    print(f"\n{n_all} rows fetched -> {len(df)} inside {START.date()}..{END.date()}")
    print(f"~{prof} profiles, {df['date'].min()} .. {df['date'].max()}")
    print(f"wrote {path}")

    # The 2022 set underwrites every published number. Prove we did not touch it.
    after = os.path.getmtime(guard) if os.path.exists(guard) else None
    assert before == after, "argo_test.parquet (2022) was modified -- the published validation set"
    print("artifacts/argo_test.parquet (2022) untouched, as required")


if __name__ == "__main__":
    main()
