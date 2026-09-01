"""Fetch Argo TEMPERATURE **AND SALINITY** for the daily period — TS-Cast stage 2.

WHY THIS EXISTS
`artifacts/argo_daily_period.parquet` carries temperature only. argopy was already downloading
PSAL all along; `_profiles_to_rows` simply dropped it. Without salinity in an INDEPENDENT table,
stage 2's salinity head could only ever be scored against held-out GLORYS -- which is the very
reanalysis it was trained on. Every headline this project quotes is against independent floats,
and the salinity half of stage 2 must be held to the same standard or it is not comparable.

WRITES TO NEW FILES, DELIBERATELY
    artifacts/argo_ts_2025.parquet, argo_ts_2026.parquet, argo_daily_period_ts.parquet
The stage-1 headline (0.8612 degC on 962 profiles) is anchored to argo_daily_period.parquet. A
re-fetch can legitimately return a different profile set as floats are delayed-mode reprocessed,
and silently replacing that file would make a published number irreproducible with nothing to see.
So this writes beside it, and asserts BOTH pre-existing tables are untouched.

It then CHECKS the new table's temperature against the old one on the profiles they share, and
prints the disagreement. If temperature has drifted, that is worth knowing before any stage-2
number is compared with a stage-1 one.

Run:  PYTHONPATH=src python scripts/phase2/fetch_argo_ts_daily_period.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from oceanembed import config
from oceanembed.data import download_argo
from oceanembed.utils import io

START, END = pd.Timestamp("2025-06-01"), pd.Timestamp("2026-06-23")
OUT = config.art("argo_daily_period_ts")
GUARDS = ("argo_test.parquet", "argo_daily_period.parquet")


def main() -> None:
    before = {g: (os.path.getmtime(config.art(g)) if os.path.exists(config.art(g)) else None)
              for g in GUARDS}

    frames = []
    for year in (2025, 2026):
        print(f"\n=== Argo T+S {year} ===", flush=True)
        try:
            written = download_argo.download(year=year, out_noext=config.art(f"argo_ts_{year}"),
                                             with_salinity=True)
            frames.append(pd.read_parquet(written))
        except Exception as e:
            print(f"[argo] {year} FAILED: {type(e).__name__}: {e}")

    if not frames:
        raise SystemExit("no Argo data fetched -- nothing written")

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= START) & (df["date"] <= END)]
    # Defence in depth: download() now dedupes, but a per-year parquet cached before that fix
    # still carries the duplicated float, and this script reads whatever is on disk.
    df = download_argo._dedupe_rows(df)
    if "psal" not in df.columns:
        raise SystemExit("fetched table has no psal column -- refusing to write a 'T+S' file "
                         "that contains no salinity")

    path = io.save_table(df, OUT)
    prof = df.groupby(["lat", "lon", "date"]).ngroups
    with_s = int(df["psal"].notna().sum())
    print(f"\n{len(df)} rows inside {START.date()}..{END.date()}, ~{prof} profiles")
    print(f"  temperature rows {len(df)}, salinity rows {with_s} ({with_s / max(len(df), 1):.1%})")
    print(f"  wrote {path}")

    for g, was in before.items():
        now = os.path.getmtime(config.art(g)) if os.path.exists(config.art(g)) else None
        assert was == now, f"{g} was modified -- it underwrites published numbers"
    print(f"  {', '.join(GUARDS)} untouched, as required")

    # Did temperature itself drift between the two fetches?
    old_path = config.art("argo_daily_period.parquet")
    if os.path.exists(old_path):
        old = pd.read_parquet(old_path)
        old["date"] = pd.to_datetime(old["date"])
        key = ["lat", "lon", "date", "depth_idx"]
        # Both sides must be unique on the key or the merge fans out: a duplicated float once
        # made this print "60717 rows of 59599", an overlap larger than the table it merged
        # into, which looks like corruption and is not. Compare distinct measurements only.
        old_u = old.drop_duplicates(subset=key)
        new_u = df.drop_duplicates(subset=key)
        if len(old_u) != len(old):
            print()
            print(f"  note: the stage-1 table holds {len(old) - len(old_u)} duplicate-key rows "
                  f"(it predates the dedupe and is frozen, so it is left as it is). "
                  f"pivot_profiles averages them, and they are byte-identical, so no published "
                  f"number moves.")
        j = old_u.merge(new_u[key + ["temp"]], on=key, suffixes=("_old", "_new"))
        if len(j):
            d = (j["temp_new"] - j["temp_old"]).abs()
            print(f"\n  overlap with the stage-1 table: {len(j)} rows of {len(old_u)} distinct")
            print(f"  temperature max |difference| {d.max():.6f} degC, mean {d.mean():.6f}")
            if d.max() > 1e-6:
                print("  NOTE: temperature has CHANGED between fetches. Stage-1 numbers stay "
                      "anchored to the old table; say so if the two are ever compared.")
            else:
                print("  temperature is identical where they overlap -- the two tables are "
                      "comparable and stage-2 salinity sits on the same profiles.")
        else:
            print("\n  WARNING: no overlapping rows with the stage-1 table at all.")


if __name__ == "__main__":
    main()
