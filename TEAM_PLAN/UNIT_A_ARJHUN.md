# UNIT A — ARJHUN — The Model Brain

> You have the strongest account (Claude **Max**), so you own the hardest reasoning: the models, uncertainty, and the
> observation-priority math. You develop on Darshan's **fixtures from Day 1**, then swap to real data on Day 3.
> Read `SHARED_BRIEF.md` first, then this file.

## Your charter
Build the machine-learning core: the baselines, the lead model (per-column MLP), the uncertainty method (MC-dropout),
and the observation-priority score. Your job is accuracy that is **honestly measured**, never inflated.

## Files you OWN (only you edit these)
```
src/oceanembed/models/mlp_profile.py        src/oceanembed/models/lgbm_baseline.py
src/oceanembed/train/train_mlp.py           src/oceanembed/train/train_lgbm.py
src/oceanembed/inference/uncertainty.py
src/oceanembed/products/observation_priority.py
docs/ARCHITECTURE.md   docs/MODEL_SPEC.md   docs/DECISIONS.md
tests/test_model.py
```
**Do NOT touch:** `data/`, `features/`, `inference/predict.py`, `app/`, `climatology.py`, `validation/`,
`products/anomaly.py`, `config/`. You consume those via files, you don't edit them.

## What you consume / produce
Consume: `X_train/y_train/X_test/y_test.npy`, `norm_stats.json` (from Darshan). Produce: `artifacts/mlp_model.pt`,
`artifacts/lgbm_model.pkl`. Function signatures you must expose (write them into `docs/MODEL_SPEC.md`):
```python
class MLPProfile(nn.Module): ...                 # 11 -> 128 -> 128 -> 11, dropout=0.2
def load_mlp(path) -> MLPProfile
def predict_mlp(model, X) -> np.ndarray           # (N,11), real units out
def mc_dropout_predict(model, X, n=30) -> (mean(N,11), std(N,11))
def observation_priority(anomaly_grid, uncertainty_grid, sparsity_grid) -> np.ndarray  # (100,240) in [0,1]
```

## Your phases

### Day 1 (Aug 25) — after Darshan's fixtures land
1. Write `docs/MODEL_SPEC.md` with the **tensor contract**: `X:[N,11]` (FEATURES order), `Y:[N,11]` (temp at DEPTHS),
   units °C, normalized-in/real-out. Mark anything not yet verified against real data as `[INFERRED]`.
2. `models/mlp_profile.py` (`MLPProfile`, `load_mlp`, `predict_mlp`) + `train/train_mlp.py` skeleton that trains on
   `artifacts/sample_*`. Confirm it runs end-to-end on fixtures (loss goes down). → Context7 for current `torch` API.

### Day 2 (Aug 26) — baselines + full training loop (still on fixtures)
1. `models/lgbm_baseline.py` + `train/train_lgbm.py`: 11 LightGBM regressors (one per depth). Add a quantile-regression
   option (10th/90th percentile) as a **backup** uncertainty source.
2. Finish the MLP training loop: fixed **random seed**, early stopping, save `mlp_model.pt`/`lgbm_model.pkl`.
3. `tests/test_model.py`: forward-pass shape test, checkpoint save/load test.

### Day 3 (Aug 27) — train for real; beat the baseline
1. Pull Darshan's real `X_train/y_train` (same shapes as fixtures → no code change). Train for real.
2. Compute **skill vs climatology** on the 2022 test set (Mitun+Niru give you `compute_metrics`). Tune until
   `skill_vs_clim > 0`. If MLP can't beat LightGBM, **say so** and we ship LightGBM — that's an honest result.
3. Log every run to `docs/EXPERIMENT_LOG.md` (seed, config, metrics, checkpoint path). Record model choice in `DECISIONS.md`.

### Day 4 (Aug 28) — uncertainty + observation-priority
1. `inference/uncertainty.py`: `mc_dropout_predict` (keep dropout ON at inference, N=30 passes → per-depth mean & std).
   Sanity check: uncertainty should generally **increase with depth**. If it doesn't, investigate — don't fake it.
2. `products/observation_priority.py`: `priority = norm(|anomaly|)*norm(uncertainty)*norm(sparsity)` where sparsity =
   distance to nearest recent Argo. Output a `(100,240)` map in [0,1]. Document inputs/limits in `ARCHITECTURE.md`.

### Day 5 (Aug 29) — support integration
Help Darshan wire `predict.py`; freeze final weights; help generate the cached demo tensors. Be available for red-team fixes.

## Copy-paste block for your Claude (after SHARED_BRIEF)
```
I am UNIT A (Arjhun, Claude Max). I own: src/oceanembed/models/*, src/oceanembed/train/*,
src/oceanembed/inference/uncertainty.py, src/oceanembed/products/observation_priority.py, docs/ARCHITECTURE.md,
docs/MODEL_SPEC.md, docs/DECISIONS.md, tests/test_model.py. I must NOT touch data/, features/, inference/predict.py,
app/, climatology.py, validation/, products/anomaly.py, config/. I develop against artifacts/sample_*.npy until real
data lands (same shapes). My deliverables: MLPProfile + training, LightGBM baseline, MC-dropout uncertainty,
observation_priority(), producing artifacts/mlp_model.pt and lgbm_model.pkl. Target: skill_vs_clim > 0 on the 2022
test set, honestly measured. Signatures I expose are frozen in docs/MODEL_SPEC.md.
```
