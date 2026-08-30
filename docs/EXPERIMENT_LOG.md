# EXPERIMENT_LOG.md  (Owner: Unit C — Mitun+Niru)  — append-only, newest on top

> One row per training/eval run. Never delete rows. Never cherry-pick.
> Template:
> ```
> ## <exp-id> <YYYY-MM-DD HH:MM>
> model: | dataset+version: | split: | seed: | hyperparams: | hardware: | git-commit:
> metrics: RMSE= MAE= R2= skill_vs_clim= rmse_by_depth=[...] | checkpoint: | notes:
> ```

(no runs yet — first entry expected on Day 3 after the MLP trains on real data)

---

# v2 — TS-Cast-NIO (Phase 2). Backfilled 2026-08-30 by Darshan's Claude.

> These runs happened between 2026-08-28 and 2026-08-30 and were recorded in
> `docs/phase2/AGENT_SYNC.md` and in `artifacts/*.json` but never here, which the Definition of
> DONE requires. Every number below is copied from the named artifact, not retyped from a summary.
> Ordering note: the 2026-08-25 Phase-1 block further down runs oldest-first, against this file's
> own "newest on top" header. Left as found — reordering another unit's rows is not a backfill.

## v2-bakeoff  2026-08-28  — which encoder, PS req 9
model: TSCastNIO stage-1, four encoders, capacity levelled 369,807–543,383 params (1.47×)
dataset: monthly archive, 5 of 7 channels [sst,sss,ssh,u,v] — wind had not landed | P=17, T_SEQ=1
split: train 36 months (2019–2021), held-out GLORYS 12 months (2022) | seed: 42 | optimizer adamw, lr 1e-3, 15 epochs, 40,000 train / 12,000 held-out samples
scored on: 897 INDEPENDENT Argo profiles, ±5 day collocation

| encoder | params | Argo RMSE °C | corr (mean per depth) | bias °C | skill 1−RMSE/RMSEclim |
|---|---|---|---|---|---|
| **cnn3d** | 543,383 | **0.9891** | 0.9038 | 0.1050 | +0.3824 |
| vit | 399,119 | 1.0071 | 0.8986 | 0.1170 | +0.3712 |
| cnn_attention | 457,039 | 1.0198 | 0.8981 | 0.1383 | +0.3633 |
| mlp_control (blind) | 369,807 | 1.0566 | 0.8990 | 0.2616 | +0.3403 |

verdict: **cnn3d**. Ranked on independent-Argo RMSE, NOT on the train/held-out gap — the gap
criterion would have crowned `mlp_control`, which cannot see its neighbours at all and is there
purely as a control. GNN was excluded with a stated reason rather than dropped silently.
artifact: `artifacts/architecture_feasibility.json` | git-commit: f9238b4

## v2-decoder-loss  2026-08-29  — decoder and loss varied INDEPENDENTLY
model: cnn3d encoder + {film, simple} decoder × {nll, mse} loss
dataset/split/seed: identical to v2-bakeoff (monthly, 897 Argo, seed 42)

| decoder + loss | Argo RMSE °C | skill |
|---|---|---|
| **simple + NLL** | **0.9672** | **+0.3961** |
| simple + MSE | 0.9891 | — |
| film + MSE | 1.1598 | — |
| film + NLL | 1.1618 | — |

verdict: the paper's FiLM/climatology U-Net decoder costs **~0.18 °C at our data scale under either
loss**; the β-NLL loss costs nothing. Shipped stage-1 is cnn3d + simple + β-NLL. The FiLM path stays
reachable as `--decoder film` with its result recorded, and the paper's own Fig. 5 found the
climatological prior gives "only modest gains" in accuracy — so rejecting it is defensible with the
paper's own finding rather than against it.
uncertainty: β-NLL at **β=0.5**. Plain β=0 (the paper's eq. 3) was MEASURED collapsing its variance:
train NLL −1.0610 vs held-out +0.6732, Argo RMSE 1.1861 against 0.9891 for the same encoder under MSE.
source: `docs/phase2/AGENT_SYNC.md` 2026-08-29 §1 — **the leg artifact was overwritten by the next
run, so AGENT_SYNC is the only record**. Recorded here as `declared`, not `measured`.

## v2-tseq  2026-08-29 → 2026-08-30  — how many days of surface context, PS req 9
model: cnn3d + simple + β-NLL(0.5) | dataset: **daily** bundle, 5 of 7 channels, 388 days
split: train 2025-06-01..2026-03-31, held-out GLORYS 2026-04-01..2026-06-23 | seed: 42
hyperparams: 15 epochs, 40,000 train / 12,000 held-out samples — identical across all three legs
scored on: **962** INDEPENDENT Argo profiles (±5 d, median offset 0 days)

| T_SEQ | window | Argo RMSE °C | bias °C | corr | skill | best epoch | provenance |
|---|---|---|---|---|---|---|---|
| 1 | single day | 0.9096 | +0.170 | 0.894 | +0.258 | 7 | declared (AGENT_SYNC §5) |
| **11** | **±5 days** | **0.8529** | **+0.036** | 0.889 | **+0.304** | 2 | declared (AGENT_SYNC §5) |
| 31 | ±15 days (the paper's) | 0.9267 | +0.2515 | 0.8824 | +0.2441 | 4 | measured |

verdict: **T_SEQ=11**, ahead of T_SEQ=1 by 0.0567 °C — clear of the 0.02 °C tie-break, so it wins
outright and no shorter-window preference is invoked. **The paper's ±15-day window is the worst of
the three at our data scale.** Cost: T=31 is 13.8× T=1 (~10 min/epoch at 40k samples on CPU).
artifact: `artifacts/tseq_ablation.json` (each leg labelled `measured` or `declared`; the T=1 and
T=11 logs were not kept, and writing console-shaped text for them would have been manufacturing
evidence) | git-commit: 4585acd
checkpoint: **none survives.** Each leg overwrote `artifacts/tscast_stage1.pt`; the surviving copy
on Arjhun's machine is the T=31 leg, saved as `tscast_stage1_tseq31.pt`, and it never left that
laptop. The winning T_SEQ=11 checkpoint does not exist anywhere.

## v2-loadpath-fixture  2026-08-30  — NOT A RESULT, do not quote
model: cnn3d + simple + β-NLL(0.5), daily, T_SEQ=11 | seed 42 | **1 epoch, 600 train / 200 held-out samples**
metrics: RMSE=1.8246 corr=0.6095 bias=−0.4214 skill=−0.4884 | calibration ratio 0.65–1.45
purpose: the ONLY v2 checkpoint on Darshan's machine was absent, so the Phase-3 inference tests had
nothing real to load. This run exists to prove the checkpoint round-trip, and nothing else. It is
logged because it wrote `artifacts/tscast_stage1.pt` and `..._metrics.json`, and an unlogged
artifact that later gets quoted is exactly how a fixture becomes a claim. The v2 UI shows a red
banner over every number sourced from it, driven by `train_samples`.
git-commit: e707962


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
