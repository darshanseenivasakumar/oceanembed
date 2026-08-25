# EXPERIMENT_LOG.md  (Owner: Unit C — Mitun+Niru)  — append-only, newest on top

> One row per training/eval run. Never delete rows. Never cherry-pick.
> Template:
> ```
> ## <exp-id> <YYYY-MM-DD HH:MM>
> model: | dataset+version: | split: | seed: | hyperparams: | hardware: | git-commit:
> metrics: RMSE= MAE= R2= skill_vs_clim= rmse_by_depth=[...] | checkpoint: | notes:
> ```

(no runs yet — first entry expected on Day 3 after the MLP trains on real data)

## slice 2026-08-25 12:37
model: MLPProfile(128, 128) dropout=0.2 | dataset: SYNTHETIC (illustrative) | split: train[2019, 2020, 2021] test[2022] | seed: 42
metrics: RMSE=0.156 MAE=0.118 R2=0.999 skill_vs_clim=+0.369 | clim_RMSE=0.248 | checkpoint: artifacts/mlp_model.pt

## slice 2026-08-25 12:39
model: MLPProfile(128, 128) dropout=0.2 | dataset: SYNTHETIC (illustrative) | split: train[2019, 2020, 2021] test[2022] | seed: 42
metrics: RMSE=0.156 MAE=0.118 R2=0.999 skill_vs_clim=+0.369 | clim_RMSE=0.248 | checkpoint: artifacts/mlp_model.pt

## model-comparison 2026-08-25 15:09  [SYNTHETIC DATA -- NOT A RESULT]
> WARNING: provenance is 'synthetic'. SYNTHETIC-derived artifacts (data/raw/synthetic_glorys.nc present) These numbers describe the PIPELINE, not real ocean performance. Do not quote them.
models: climatology, lightgbm, mlp | dataset: SYNTHETIC-derived artifacts (data/raw/synthetic_glorys.nc present) | split: train[2019,2020,2021] test[2022] (by TIME) | seed: 42 | n_test: 47838
metrics[climatology]: RMSE=0.9806 MAE=0.7538 R2=0.9690 skill_vs_clim=+0.0000
metrics[lightgbm]: RMSE=0.1547 MAE=0.1146 R2=0.9992 skill_vs_clim=+0.8423
metrics[mlp]: RMSE=0.1569 MAE=0.1190 R2=0.9992 skill_vs_clim=+0.8400
VERDICT: lightgbm (not conclusive) -- TIE: MLP 0.1569 vs LightGBM 0.1547 degC differ by 1.4%, under the 2% noise margin. Ship the simpler model.

## model-comparison 2026-08-25 16:16  [SYNTHETIC DATA -- NOT A RESULT]
> WARNING: provenance is 'synthetic'. SYNTHETIC-derived artifacts (data/raw/synthetic_glorys.nc present) These numbers describe the PIPELINE, not real ocean performance. Do not quote them.
models: climatology, lightgbm | dataset: SYNTHETIC-derived artifacts (data/raw/synthetic_glorys.nc present) | split: train[2019,2020,2021] test[2022] (by TIME) | seed: 42 | n_test: 112836
metrics[climatology]: RMSE=1.7617 MAE=1.3791 R2=0.9281 skill_vs_clim=+0.0000
metrics[lightgbm]: RMSE=0.6561 MAE=0.4135 R2=0.9900 skill_vs_clim=+0.6275
VERDICT: lightgbm (not conclusive) -- only one model available -- train both for a real comparison

## model-comparison 2026-08-25 16:17
models: climatology, lightgbm, mlp | dataset: real GLORYS artifacts (provenance.json, built 2026-08-25T16:04:47) | split: train[2019,2020,2021] test[2022] (by TIME) | seed: 42 | n_test: 112836
metrics[climatology]: RMSE=1.7617 MAE=1.3791 R2=0.9281 skill_vs_clim=+0.0000
metrics[lightgbm]: RMSE=0.6561 MAE=0.4135 R2=0.9900 skill_vs_clim=+0.6275
metrics[mlp]: RMSE=0.6563 MAE=0.4275 R2=0.9900 skill_vs_clim=+0.6275
VERDICT: lightgbm (not conclusive) -- TIE: MLP 0.6563 vs LightGBM 0.6561 degC differ by 0.0%, under the 2% noise margin. Ship the simpler model.

## model-comparison 2026-08-25 18:07
models: climatology, lightgbm, mlp | dataset: real GLORYS artifacts (provenance.json, built 2026-08-25T17:56:42) | split: train[2019,2020,2021] test[2022] (by TIME) | seed: 42 | n_test: 107676
metrics[climatology]: RMSE=1.6921 MAE=1.3248 R2=0.9503 skill_vs_clim=+0.0000
metrics[lightgbm]: RMSE=0.6329 MAE=0.3947 R2=0.9930 skill_vs_clim=+0.6260
metrics[mlp]: RMSE=0.6323 MAE=0.4059 R2=0.9931 skill_vs_clim=+0.6263
VERDICT: lightgbm (not conclusive) -- TIE: MLP 0.6323 vs LightGBM 0.6329 degC differ by 0.1%, under the 2% noise margin. Ship the simpler model.
