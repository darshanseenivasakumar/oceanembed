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
