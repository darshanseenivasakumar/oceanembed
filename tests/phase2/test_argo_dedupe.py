"""ERDDAP returns at least one Arabian Sea float twice, on every one of its ~10-day cycles.

In artifacts/argo_daily_period_ts.parquet that was 40 profiles / 559 keys / 1118 rows, byte
identical in both temp and psal. No published number was ever wrong -- validate_argo.pivot_profiles
aggregates with mean, and mean(x, x) = x -- but the profile count was inflated by 0.9% and any
future consumer that does not pivot would weight that float twice.

The guard that matters is the second one: dropping rows that AGREE is safe, and quietly dropping
rows that DISAGREE would be choosing a measurement without saying so.
"""
from __future__ import annotations

import pandas as pd

from oceanembed.data.download_argo import _dedupe_rows

KEY = ["lat", "lon", "date", "depth_idx"]


def _rows(*vals) -> pd.DataFrame:
    return pd.DataFrame(list(vals), columns=KEY + ["temp"])


def test_exact_duplicates_are_removed():
    df = _rows((13.1, 69.1, "2026-01-15", 1, 27.7),
               (13.1, 69.1, "2026-01-15", 1, 27.7),
               (13.1, 69.1, "2026-01-15", 2, 27.6))
    out = _dedupe_rows(df)
    assert len(out) == 2
    assert out.duplicated(subset=KEY).sum() == 0


def test_distinct_rows_are_untouched():
    df = _rows((13.1, 69.1, "2026-01-15", 1, 27.7),
               (14.2, 68.1, "2026-01-15", 1, 27.7),   # same temp, different place
               (13.1, 69.1, "2026-01-16", 1, 27.7))   # same place, different day
    assert len(_dedupe_rows(df)) == 3


def test_a_conflicting_key_is_kept_and_reported(capsys):
    """Two rows on one key that DISAGREE are not redundant. pivot_profiles would average them
    into a single value, so the run must say so rather than pick one."""
    df = _rows((13.1, 69.1, "2026-01-15", 1, 27.7),
               (13.1, 69.1, "2026-01-15", 1, 28.9))
    out = _dedupe_rows(df)
    assert len(out) == 2, "a genuine disagreement must never be silently collapsed"
    assert "DISAGREE" in capsys.readouterr().out


def test_a_wholly_duplicated_profile_collapses_to_one():
    """The real shape of the bug: every level of one profile delivered twice."""
    prof = [(14.29, 68.13, "2025-06-04", d, 30.0 - d) for d in range(15)]
    out = _dedupe_rows(pd.DataFrame(prof + prof, columns=KEY + ["temp"]))
    assert len(out) == 15
    assert out.groupby(["lat", "lon", "date"]).ngroups == 1


def test_salinity_is_carried_through_and_considered():
    """psal must take part in the comparison: two rows equal in temp but differing in salinity
    are different measurements."""
    df = pd.DataFrame([(13.1, 69.1, "2026-01-15", 1, 27.7, 36.3),
                       (13.1, 69.1, "2026-01-15", 1, 27.7, 36.3),
                       (13.1, 69.1, "2026-01-15", 2, 27.7, 35.1)],
                      columns=KEY + ["temp", "psal"])
    out = _dedupe_rows(df)
    assert len(out) == 2
    assert "psal" in out.columns
