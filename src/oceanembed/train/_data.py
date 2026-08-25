"""Single source of truth for how Unit A loads train/test data.

OWNER: Unit A (Arjhun).

WHY THIS MODULE EXISTS -- a real bug, twice:
`train_lgbm` and `compare_models` each had their own fixture loader. One z-scored X, the other
did not, so a model trained on one scale was evaluated on the other. First it made the MLP look
broken (RMSE 36 degC), then it made LightGBM look broken (RMSE 2.5 degC, worse than climatology).
Neither model was broken; the CALLER was, both times.

"Trees are scale-invariant" means trees do not NEED scaling -- not that you may change the scale
between fit and predict. A booster's split thresholds are learned in the units it was trained on.

So training and evaluation now share these loaders. If the preparation is wrong it is wrong
identically everywhere, which is a bug you can see instead of a silent 20x error.

CONVENTION (matches Unit B's build_samples): X is ALWAYS z-scored, y is ALWAYS real degC.
"""
from __future__ import annotations

import json
import os

import numpy as np

from oceanembed import config
from oceanembed.utils import io

REQUIRED_REAL = ("X_train.npy", "y_train.npy", "X_test.npy", "y_test.npy")

_PIPELINE_BROKEN_HINT = (
    "Run `python scripts/prepare_dataset.py` first.\n"
    "NOTE: that script is currently BROKEN on a fresh clone -- .gitignore excludes\n"
    "src/oceanembed/data/, so preprocess.py was never committed. See docs/HANDOFF.md.\n"
    "Use --fixtures to verify the harness in the meantime."
)


def artifact_provenance() -> tuple[str, str]:
    """(status, label) for what the artifacts were actually built from.

    status is one of "synthetic" | "real" | "unverified".

    D-018 RESOLVED: `build_samples` now stamps `artifacts/provenance.json`, so provenance is READ
    FROM THE ARTIFACTS rather than inferred from `data/raw/` (which is gitignored and vanishes when
    artifacts are copied to another machine). The old inference is kept only as a fallback for
    artifacts built before the stamp existed, and it still never upgrades absence of evidence
    into a claim of "real".
    """
    stamp = config.art("provenance.json")
    if os.path.exists(stamp):
        try:
            with open(stamp, "r", encoding="utf-8") as fh:
                p = json.load(fh)
            src = p.get("source")
            built = p.get("built", "?")
            if src == "real-glorys":
                return "real", f"real GLORYS artifacts (provenance.json, built {built})"
            if src == "synthetic":
                return "synthetic", f"SYNTHETIC artifacts (provenance.json, built {built})"
        except Exception:
            pass

    # Fallback: pre-stamp artifacts.
    raw = config.DATA_RAW
    if os.path.exists(os.path.join(raw, "synthetic_glorys.nc")):
        return "synthetic", "SYNTHETIC-derived artifacts (data/raw/synthetic_glorys.nc present)"

    return "unverified", (
        "artifacts with UNVERIFIED provenance -- no artifacts/provenance.json. "
        "Rebuild with scripts/prepare_dataset.py. Could be synthetic. Do not report as real."
    )


def load_real() -> dict:
    """Unit B's artifacts. X_train/X_test are ALREADY z-scored by build_samples."""
    missing = [n for n in REQUIRED_REAL if not os.path.exists(config.art(n))]
    if missing:
        raise SystemExit("Missing artifacts: " + ", ".join(missing) + "\n" + _PIPELINE_BROKEN_HINT)

    status, label = artifact_provenance()
    return dict(
        X_train=io.load_npy(config.art("X_train.npy")).astype("float32"),
        y_train=io.load_npy(config.art("y_train.npy")).astype("float32"),
        X_test=io.load_npy(config.art("X_test.npy")).astype("float32"),
        y_test=io.load_npy(config.art("y_test.npy")).astype("float32"),
        split="train[2019,2020,2021] test[2022] (by TIME)",
        dataset=label,
        provenance=status,
    )


def load_fixtures(test_frac: float = 0.2) -> dict:
    """Fixtures, z-scored with TRAIN-SPLIT stats so they match the real convention exactly.

    `sample_X.npy` ships RAW, but `X_train.npy` is z-scored, so the fixture path must z-score
    or every model trained here sees a different scale than the real path. Stats come from the
    train rows only -- using test rows would leak.
    """
    X = io.load_npy(config.art("sample_X.npy")).astype("float32")
    y = io.load_npy(config.art("sample_y.npy")).astype("float32")

    rng = np.random.default_rng(config.SEED)
    idx = rng.permutation(len(X))
    n_te = max(1, int(len(X) * test_frac))
    te, tr = idx[:n_te], idx[n_te:]

    feat_mean = X[tr].mean(axis=0)
    feat_std = X[tr].std(axis=0) + 1e-6
    Xz = ((X - feat_mean) / feat_std).astype("float32")

    return dict(
        X_train=Xz[tr], y_train=y[tr], X_test=Xz[te], y_test=y[te],
        feat_mean=feat_mean, feat_std=feat_std,
        split="random row split of fixtures (NOT a time split)",
        dataset="FIXTURES (synthetic, z-scored to match the real convention)",
    )


def load(fixtures: bool = False) -> dict:
    return load_fixtures() if fixtures else load_real()
