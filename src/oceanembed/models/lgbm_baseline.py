"""LightGBM baseline: 11 boosters (one per depth) + quantile uncertainty.

OWNER: Unit A (Arjhun). Produces artifacts/lgbm_model.pkl (and artifacts/lgbm_quantiles.pkl).

WHY THIS EXISTS: it is the model the MLP has to beat. Gradient-boosted trees are the strong
classical baseline for tabular regression, so "our MLP beats climatology" is a weak claim until
it also beats LightGBM. If the MLP does NOT win, we say so and ship LightGBM -- that is an
honest result, not a failure (see TEAM_PLAN/UNIT_A_ARJHUN.md Day 3).

One booster per depth rather than one multi-output model: LightGBM is single-output, and the
depths have genuinely different error scales (surface ~2 degC spread, 500 m ~0.3 degC), so
per-depth models let each fit its own scale.

Boosters predict y in REAL degC directly -- no normalization round-trip on the target, and
therefore no dependency on norm_stats.json.

CAREFUL about the input side. Trees do not NEED feature scaling, but that is NOT the same as
being safe under a change of scale: a booster's split thresholds are learned in the units it was
trained on, so training on raw X and predicting on z-scored X (or vice versa) silently produces
garbage. It cost two debugging rounds here -- see docs/DECISIONS.md D-014. Always load data
through `oceanembed.train._data` so training and evaluation cannot disagree.
"""
from __future__ import annotations

import pickle
import warnings

import numpy as np

from oceanembed import config

# Conservative, CPU-friendly defaults. Not tuned -- tuning happens on REAL data (Day 3),
# because tuning against synthetic data optimizes for the wrong thing.
LGBM_PARAMS = dict(
    objective="regression",
    metric="l2",
    learning_rate=0.05,
    num_leaves=31,
    min_data_in_leaf=20,
    feature_fraction=0.9,
    bagging_fraction=0.8,
    bagging_freq=1,
    verbose=-1,
    seed=config.SEED,
    deterministic=True,
    force_row_wise=True,   # silences the row/col-wise autodetect warning on small data
)

NUM_BOOST_ROUND = 500
STOPPING_ROUNDS = 30

# For a Gaussian, q90 - q10 = 2 * 1.2816 * sigma. Dividing by this makes the quantile spread
# directly comparable to the MC-dropout std that inference/uncertainty.py reports.
Q90_Q10_TO_SIGMA = 2.5631


def _lgb():
    import lightgbm as lgb  # imported lazily so the repo imports without lightgbm installed
    return lgb


def train_boosters(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    alpha: float | None = None,
    params: dict | None = None,
    num_boost_round: int = NUM_BOOST_ROUND,
    stopping_rounds: int = STOPPING_ROUNDS,
    verbose: bool = False,
) -> list:
    """Train one booster per depth. alpha=None -> L2 regression; alpha=0.1/0.9 -> quantile.

    Returns a list of `config.N_DEPTHS` Boosters, index-aligned with `config.DEPTHS`.
    """
    lgb = _lgb()
    X_train = np.asarray(X_train, dtype="float32")
    y_train = np.asarray(y_train, dtype="float32")
    assert X_train.shape[1] == config.N_FEAT, f"X must have {config.N_FEAT} features"
    assert y_train.shape[1] == config.N_DEPTHS, f"y must have {config.N_DEPTHS} depths"

    p = dict(params or LGBM_PARAMS)
    if alpha is not None:
        p = {**p, "objective": "quantile", "alpha": float(alpha), "metric": "quantile"}

    boosters = []
    for d in range(config.N_DEPTHS):
        dtrain = lgb.Dataset(X_train, label=y_train[:, d], feature_name=list(config.FEATURES))
        dval = lgb.Dataset(X_val, label=np.asarray(y_val, dtype="float32")[:, d], reference=dtrain)
        # LightGBM >=4: early stopping is a CALLBACK, not an early_stopping_rounds argument.
        callbacks = [lgb.early_stopping(stopping_rounds=stopping_rounds, verbose=False)]
        if verbose:
            callbacks.append(lgb.log_evaluation(period=100))
        boosters.append(
            lgb.train(p, dtrain, num_boost_round=num_boost_round, valid_sets=[dval], callbacks=callbacks)
        )
    return boosters


def predict_lgbm(models: list, X: np.ndarray) -> np.ndarray:
    """X:(N,11) features -> (N,15) temperature in REAL degC. Mirrors predict_mlp's output contract."""
    X = np.asarray(X, dtype="float32")
    assert X.ndim == 2 and X.shape[1] == config.N_FEAT, f"X must be (N,{config.N_FEAT}), got {X.shape}"
    assert len(models) == config.N_DEPTHS, f"expected {config.N_DEPTHS} boosters, got {len(models)}"

    out = np.empty((len(X), config.N_DEPTHS), dtype="float32")
    for d, booster in enumerate(models):
        out[:, d] = booster.predict(X, num_iteration=getattr(booster, "best_iteration", None))
    return out


def quantile_uncertainty(q10_models: list, q90_models: list, X: np.ndarray) -> np.ndarray:
    """(N,11) sigma-equivalent spread from the 10th/90th percentile boosters.

    Backup uncertainty source if MC-dropout proves unreliable on real data. Converted to a
    sigma equivalent so it is directly comparable with inference/uncertainty.py.
    """
    lo = predict_lgbm(q10_models, X)
    hi = predict_lgbm(q90_models, X)

    crossed = int((hi < lo).sum())
    if crossed:
        # Quantile crossing is a known artefact of fitting quantiles independently.
        warnings.warn(
            f"{crossed} of {lo.size} predictions have q90 < q10 (quantile crossing). "
            "Clamping to zero spread; do not report those cells as confident.",
            RuntimeWarning,
            stacklevel=2,
        )
    return (np.maximum(hi - lo, 0.0) / Q90_Q10_TO_SIGMA).astype("float32")


def save_lgbm(models: list, path: str) -> str:
    with open(path, "wb") as fh:
        pickle.dump(models, fh)
    return path


def load_lgbm(path: str | None = None) -> list:
    """Load artifacts/lgbm_model.pkl -> list of 11 boosters (DATA_CONTRACT)."""
    path = path or config.art("lgbm_model.pkl")
    with open(path, "rb") as fh:
        models = pickle.load(fh)
    assert len(models) == config.N_DEPTHS, f"expected {config.N_DEPTHS} boosters, got {len(models)}"
    return models


def load_quantiles(path: str | None = None) -> dict:
    """Load artifacts/lgbm_quantiles.pkl -> {'q10': [...11], 'q90': [...11]}."""
    path = path or config.art("lgbm_quantiles.pkl")
    with open(path, "rb") as fh:
        return pickle.load(fh)
