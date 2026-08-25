# MODEL_SPEC.md  (Owner: Unit A — Arjhun)  [seeded by B; Arjhun fills the rest]

## Tensor contract — Aug 30 MVP (per-column MLP, tabular)
- Input `X`: `[N, 11]` float32, columns in `config.FEATURES` order, **z-scored** with `norm_stats.json`.
- Target `Y`: `[N, 11]` float32, temperature (°C) at `config.DEPTHS`.
- Model output: `[N, 11]` in **real units** (un-normalize inside `predict_mlp`).
- **Assert** shapes/dtypes at every boundary. Never silently reshape.

## Frozen public signatures (A implements; B/C consume)
```python
class MLPProfile(nn.Module): ...                    # 11 -> 128 -> 128 -> 11, dropout=0.2 (config.MLP)
def load_mlp(path) -> MLPProfile
def predict_mlp(model, X: np.ndarray) -> np.ndarray             # (N,11) real units
def mc_dropout_predict(model, X, n=30) -> tuple[np.ndarray, np.ndarray]   # mean(N,11), std(N,11)
def observation_priority(anomaly_grid, uncertainty_grid, sparsity_grid) -> np.ndarray  # (100,240) in [0,1]
```
Per component record: INPUT SHAPE / OUTPUT SHAPE / CHANNEL MEANING / DEPTH MEANING / NORMALIZATION / UNITS.

## Phase-2 grid contract (candidate — VERIFY axis order on a real tensor before use)
`X:[batch, time, channels, lat, lon]`, `Y:[batch, depth, lat, lon]`.

## Checkpoints
`artifacts/mlp_model.pt` (state_dict) + `artifacts/lgbm_model.pkl`. Log run to `docs/EXPERIMENT_LOG.md`.
