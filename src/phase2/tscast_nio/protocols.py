"""The names of the scoring protocols, and the fingerprint of the truth table they score against.

Kept torch-free on purpose: `freeze_headline.py`, the tests and any future reader can import a
protocol NAME without loading the model stack. `eval_argo` re-exports everything here, so scorers
keep reaching these as `EA.<name>`.

A record under one name is never compared with a record under another. That rule is what has kept
the three generations below from being read as one number:

  unmasked_v1         raw output vs Argo at every depth the float sampled -- including depths the
                      product itself refuses to serve (93 of 12,829 on the shipped run). Truth
                      axis: PRES in decibars read as metres.
  seafloor_masked_v1  below-seafloor comparisons declined and counted. Same truth axis as above.
  seafloor_masked_v2  the same mask, scored against an Argo table interpolated on DEPTH in metres
                      (UNESCO 1983; audit #8, phase2.data.argo_depth). Reading pressure as depth
                      had sampled every float ~1% too shallow -- 0.6 m at 100 m, 8 m at 1000 m.
"""
from __future__ import annotations

import hashlib
import os

#: Which comparisons the scorer declines to make, and what axis the truth is on. Stamped into
#: every artifact beside the score.
SCORING_PROTOCOL = "seafloor_masked_v2"
#: v1 of the mask, against the pressure-as-depth table (argo_daily_period_pres_as_depth_v1.parquet).
SEAFLOOR_MASKED_V1 = "seafloor_masked_v1"
#: What every artifact before 2026-09-07 was scored under.
UNMASKED_PROTOCOL = "unmasked_v1"
#: How the Argo truth table's levels were placed.
TRUTH_AXIS = "depth_m_unesco1983"
LEGACY_TRUTH_AXIS = "pressure_dbar_read_as_metres"

#: The held-out winter (E-INV-00 / D-020). Same mask and depth axis as seafloor_masked_v2, but a
#: DIFFERENT period (2024-12-01..2025-02-28) and a different truth table. A record under this name
#: is never compared with a seafloor_masked_v2 headline number -- different water, different days.
WINTER_HOLDOUT_PROTOCOL = "winter_holdout_v1"
WINTER_TEST_START = "2024-12-01"
WINTER_TEST_END = "2025-02-28"
WINTER_BUNDLE_START = "2024-11-20"
WINTER_BUNDLE_END = "2025-03-10"

PROTOCOL_HISTORY = {
    UNMASKED_PROTOCOL: {"mask": "none", "truth_axis": LEGACY_TRUTH_AXIS,
                        "argo_table": "argo_daily_period_pres_as_depth_v1.parquet"},
    SEAFLOOR_MASKED_V1: {"mask": "below-seafloor comparisons declined and counted",
                         "truth_axis": LEGACY_TRUTH_AXIS,
                         "argo_table": "argo_daily_period_pres_as_depth_v1.parquet"},
    SCORING_PROTOCOL: {"mask": "below-seafloor comparisons declined and counted",
                       "truth_axis": TRUTH_AXIS,
                       "argo_table": "argo_daily_period.parquet (regenerated 2026-09-07)"},
    WINTER_HOLDOUT_PROTOCOL: {"mask": "below-seafloor comparisons declined and counted",
                              "truth_axis": TRUTH_AXIS,
                              "period": f"{WINTER_TEST_START}..{WINTER_TEST_END} (held out; never trained)",
                              "argo_table": "argo_winter2425.parquet",
                              "note": ("A DIFFERENT period from the deliverable, on a separate "
                                       "evaluation-only bundle. Never compared with a "
                                       "seafloor_masked_v2 headline number. See D-020, E-INV-00.")},
}


def argo_table_provenance(path) -> dict:
    """The identity of the truth table a score was made against.

    A protocol NAME says which rules were applied; this says which FILE they were applied to, so
    two records that share a name but not a table cannot be read as the same measurement.
    """
    import pandas as pd  # local: keep the module import free of anything heavy
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    keys = pd.read_parquet(path, columns=["lat", "lon", "date"])
    return {"file": os.path.basename(path), "sha256": h.hexdigest(), "rows": int(len(keys)),
            "profiles": int(keys.drop_duplicates().shape[0]), "truth_axis": TRUTH_AXIS}
