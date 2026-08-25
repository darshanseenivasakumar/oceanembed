# MODEL_SPEC.md  (Owner: Unit A — Arjhun)

Status: **Day 1 complete for the MLP.** Signatures below are FROZEN — B and C code against them.

## Tensor contract — Aug 30 MVP (per-column MLP, tabular)
- Input `X`: `[N, 11]` float32, columns in `config.FEATURES` order, **z-scored**.
- Target `Y`: `[N, 11]` float32, temperature (°C) at `config.DEPTHS`.
- Model output: `[N, 11]` in **real units** (un-normalized inside `predict_mlp`).
- **Assert** shapes/dtypes at every boundary. Never silently reshape.

### Per-component record
| | INPUT SHAPE | OUTPUT SHAPE | CHANNEL MEANING | DEPTH MEANING | NORMALIZATION | UNITS |
|---|---|---|---|---|---|---|
| `MLPProfile.forward` | `(N,11)` | `(N,11)` | `config.FEATURES` order | `config.DEPTHS` order | z-scored in, **z-scored out** | dimensionless |
| `MLPProfile.denormalize` | `(N,11)` z | `(N,11)` | — | `config.DEPTHS` | z → real | °C |
| `predict_mlp` | `(N,11)` z-scored | `(N,11)` | `config.FEATURES` | `config.DEPTHS` | z in, **real out** | °C |
| `mc_dropout_predict` *(Day 4)* | `(N,11)` z-scored | `mean(N,11)`, `std(N,11)` | — | `config.DEPTHS` | real out | °C |
| `observation_priority` *(Day 4)* | three `(100,240)` grids | `(100,240)` | — | — | each min-max normalized | [0,1] |

## Frozen public signatures (A implements; B/C consume)
```python
class MLPProfile(nn.Module): ...                    # 11 -> 128 -> 128 -> 11, dropout=0.2 (config.MLP)
def load_mlp(path) -> MLPProfile
def predict_mlp(model, X: np.ndarray) -> np.ndarray             # (N,11) real units
def mc_dropout_predict(model, X, n=30) -> tuple[np.ndarray, np.ndarray]   # mean(N,11), std(N,11)
def observation_priority(anomaly_grid, uncertainty_grid, sparsity_grid) -> np.ndarray  # (100,240) in [0,1]
```

## Normalization — the checkpoint is self-describing
`MLPProfile` registers four buffers: `feat_mean`, `feat_std` `(11,)` and `targ_mean`, `targ_std` `(11,)`.
They ride inside `state_dict()`, so `artifacts/mlp_model.pt` needs **no companion file** and
`torch.load(..., weights_only=True)` (the PyTorch ≥2.6 default) reads it safely — buffers are plain
tensors. `train_mlp.py` fills them from `artifacts/norm_stats.json` when Unit B ships it, else from
the **train split only**. Rationale: `docs/DECISIONS.md` D-007.

Defaults are identity (mean 0 / std 1), so an untrained model is a no-op rather than a silent scaler.
`set_norm_stats` clamps std to ≥1e-6 so a constant feature cannot produce `inf`.

### ⚠ Contract mismatch pending Unit B  `[UNKNOWN]`
`predict_mlp` expects **z-scored** `X`, but `artifacts/sample_X.npy` is **raw** — verified range
`[-1.000, 36.994]`, i.e. SST in °C next to sin/cos encodings in [-1,1]. `artifacts/norm_stats.json`
does not exist yet. **Unresolved:** will B's real `X_train.npy` ship pre-z-scored, or raw plus
`norm_stats.json`? Until B confirms, the caller must z-score. `predict_mlp` emits a `RuntimeWarning`
when the input looks raw (`|mean|>3` or `std>5`) — this failure is otherwise silent and would put
plausible-but-wrong temperatures straight into the demo.

## Verified behaviour  `[VERIFIED 2026-08-25, fixtures]`
- `pytest tests/test_model.py` — **11 passed**.
- `python -m oceanembed.train.train_mlp --fixtures` — val loss 0.896 → 0.064 (z-scored MSE), 0.8 s CPU.
- Reload → `predict_mlp` → `(500,11)` float32, 8.42–30.82 °C.
- **Anti-collapse:** model RMSE 0.214 °C vs predict-the-mean 1.503 °C (**+85.8 %**); per-depth spread
  tracks truth; profile cools monotonically 27.45 → 8.91 °C.
- These are **synthetic fixtures** — plumbing evidence only, never a reported result.

## Phase-2 grid contract (candidate — VERIFY axis order on a real tensor before use)
`X:[batch, time, channels, lat, lon]`, `Y:[batch, depth, lat, lon]`.

## Checkpoints
`artifacts/mlp_model.pt` (state_dict incl. norm buffers) + `artifacts/lgbm_model.pkl`.
Real-data runs get logged to `docs/EXPERIMENT_LOG.md` from Day 3.
