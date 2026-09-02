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

## v2-embargoed  2026-09-01  — the post-embargo re-score, and the wind result reverses

> **This entry supersedes the wind conclusion in `v2-final` below. No row below is edited or
> deleted** — this file is append-only, and a superseded result is evidence, not clutter. Read
> `v2-final` as the pre-embargo record it is.

**What happened.** Commit `a5cdd3a` embargoed the training targets whose `T_SEQ=11` window reached
into the test block — a real leakage fix. The stage-1 legs were then retrained on 2026-08-31
(`retrain_v2.log`), writing `artifacts/tscast_stage1_{7ch,5ch}.pt`. Those runs were never logged
here, so this file still carried the pre-embargo numbers while the artifacts on disk carried
different ones. Found during the Phase-1 provenance audit.

model: TSCastNIO — cnn3d encoder + simple decoder + β-NLL(β=0.5), residual, latent 128, P=17
dataset: daily bundle, 388 days | 7ch `[sst,sss,ssh,u,v,wu,wv]` vs 5ch `[sst,sss,ssh,u,v]`
split: train 2025-06-01..2026-03-26 / held-out GLORYS 2026-04-01..2026-06-23
seed: 42 | T_SEQ=11, 25 epochs max, patience 5, 60,000 train / 12,000 held-out, adamw lr 1e-3,
        batch 256 | hardware: CUDA | protocol: `embargoed_v2`, 5 of 304 targets dropped in BOTH legs
scored on: **962 INDEPENDENT Argo profiles**, ±5 day collocation, 12,829 depth comparisons
git-commit: `a5cdd3a` | checkpoints: `artifacts/tscast_stage1_{7ch,5ch}.pt`
        (byte identity stamped in `artifacts/frozen_manifest.json`)

| | **7 ch (wind ON)** | 5 ch (matched control) | delta |
|---|---|---|---|
| Argo RMSE °C | 0.8793 | **0.8682** | **+0.0111 (worse with wind)** |
| bias °C | **+0.1296** | +0.1518 | **−0.0222 (better with wind)** |
| correlation (mean per depth) | 0.8942 | 0.8971 | −0.0029 |
| skill 1−RMSE/RMSEclim | +0.2827 | **+0.2918** | −0.0091 |
| climatology RMSE °C | 1.2259 | 1.2259 | 0.0000 |
| n (depth comparisons) | 12,829 | 12,829 | — |

**The legs are MATCHED.** Identical seed, T_SEQ, sample counts, epochs, patience, decoder, loss,
encoder, embargo and Argo set; the only difference is whether channels 6–7 exist. `rmse_climatology`
comes out **identical to 4 dp (1.2259) in both**, which is the check that they really were scored on
the same points — the same check `v2-final` used.

**The wind conclusion reverses, and the honest reading is split.** `v2-final` reported wind worth
**−0.0149 °C** and **41%** of the warm bias. Post-embargo, wind **costs 0.0111 °C of RMSE** and
**still removes 14.6% of the warm bias** (+0.1518 → +0.1296). So wind is no longer a free win: it
buys bias and pays in RMSE. That the earlier gain shrank and flipped when leaked targets were
removed is what a leakage fix is supposed to do; the pre-embargo delta was measured on a training
set that could see the test block.

**Independently confirmed before this entry was written.** Both numbers were reproduced by
`scripts/phase2/rescore_checkpoint.py`, which reloads the saved checkpoint from disk and re-runs the
same split/embargo/normalisation/collocation rather than trusting the training run's own printout.
Largest gap on either leg: **0.00e+00** across rmse, bias, correlation and skill, n identical.
A retrain was deliberately NOT used as the check — it would have proved the pipeline reproduces,
not that *these shipped checkpoints* produce their recorded numbers.

**Not comparable to** the monthly 0.9638/0.9672 Phase-1 headlines (different test set, and those are
the SATELLITE-driven path) or to any pre-embargo v2 figure. The only fair delta in this table is
7ch vs 5ch.

**Open, and not claimed either way:** whether the RMSE cost of wind survives a second seed. The
delta (0.0111 °C) is small enough that one seed cannot settle it — see the multi-seed rule in
`OceanEmbed_SIH26066_Master_Build_Plan_FINAL.docx` §8. Stated as a limitation, not a finding.


## v2-final  2026-08-30  — the shipped stage-1 model, and the wind ablation that pays for it

> ⚠ **SUPERSEDED 2026-09-01 by `v2-embargoed` above — read this as the PRE-EMBARGO record.**
> Every number below was correct for commit `6e6ba9a` and is preserved unedited: this file is
> append-only and a superseded result is evidence, not clutter. What changed is the *data*, not the
> arithmetic — commit `a5cdd3a` embargoed training targets whose `T_SEQ` window reached into the test
> block, the legs were retrained, and the comparison moved. Specifically **the wind conclusion in this
> entry no longer holds**: 7ch 0.8612 vs 5ch 0.8760 (wind helps −0.0149) became 7ch 0.8793 vs 5ch
> 0.8682 (wind costs +0.0111), with wind still removing 14.6% rather than 41% of the warm bias. The
> title's claim that the ablation “pays for it” is therefore superseded too. Do not quote this entry's
> figures as current; quote `v2-embargoed`, or the stage-2 headline 0.8548 °C.

model: TSCastNIO — cnn3d encoder + simple decoder + β-NLL(β=0.5), residual, latent 128, P=17
dataset: daily bundle, 388 days 2025-06-01..2026-06-23 | **7 of 7 contract channels**
        `["sst","sss","ssh","u","v","wu","wv"]` — wind from
        `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H`, hourly → daily mean, block-averaged
        0.125°→0.25° by coordinate
split: train 2025-06-01..2026-03-31 (304 d) / held-out GLORYS 2026-04-01..2026-06-23 (84 d)
seed: 42 | hyperparams: T_SEQ=11, 25 epochs max, patience 5, 60,000 train / 12,000 held-out
        samples, adamw lr 1e-3, weight-decay 1e-2, batch 256 | hardware: CPU
scored on: **962 INDEPENDENT Argo profiles**, ±5 day collocation, 12,829 depth comparisons
git-commit: 6e6ba9a | checkpoints: `artifacts/tscast_stage1_{7ch,5ch}.pt` (gitignored — the numbers
below and in AGENT_SYNC are the durable record)

**Both legs are MATCHED.** Identical seed, T_SEQ, samples, epochs, patience, decoder, loss, encoder
and Argo set; the only difference is whether channels 6–7 exist. `rmse_climatology` comes out
**identical to 4 dp (1.2259) in both**, which is the check that they really were scored on the same
points. The brief's suggested comparison — 7-channel against the recorded 0.8529 — would have
compared 60k/25ep against 40k/15ep and credited wind for three changes.

> ## ⚠ SUPERSEDED RESULTS — read before quoting any number below
>
> **Every trained artifact produced before commit `1d3c135` (2026-09-02) came from a leaky
> sampler.** `dataset._window()` clamped the input window to the array ends instead of to the
> train/test split, so **5 of 304 train days (2026-03-27..31, 1.64%) read test-period surface
> fields.** The split assert was correct; the input window was not, which is why every test
> passed while it happened.
>
> Affected and **INVALID — do not quote**: `tscast_stage1_withUV_s42` (0.8612 / 0.8611),
> `tscast_stage1_noUV_s42` (0.9024), `tscast_stage1_metrics_tseq31` (0.9267), and the wind
> comparison derived from the first two.
>
> **The numbers are preserved verbatim as historical record and are not edited.** A matched
> re-run under the embargo is the replacement; until it lands, this project has no quotable
> headline.
>
> **The wind conclusion below (−0.0149 °C) rests on both legs of this comparison, and both are leaky. Its SIGN is not established.** The same effect already flipped (−0.0149 -> +0.0111) under one retrain, so it must be re-measured across ≥3 seeds under the embargo before it is stated anywhere.

| | **7 ch (shipped)** | 5 ch (matched control) | delta |
|---|---|---|---|
| Argo RMSE °C | **0.8612** | 0.8760 | **−0.0149** |
| bias °C | **+0.1247** | +0.2124 | **−0.0878** |
| correlation (mean per depth) | 0.8893 | 0.8923 | −0.0030 |
| skill 1−RMSE/RMSEclim | **+0.2975** | +0.2854 | +0.0121 |
| skill Murphy | +0.5065 | +0.4893 | +0.0172 |
| climatology RMSE °C | 1.2259 | 1.2259 | 0.0000 |
| best epoch / run | 3 / 8 | 4 / 9 | — |
| params | 548,582 | 547,238 | — |
| train seconds | 4,932 | 5,531 | — |

**Wind helps, and the bias story is larger than the RMSE story.** ⚠ _[SUPERSEDED 2026-09-01: post-embargo this reverses — wind COSTS +0.0111 °C RMSE and removes 14.6%, not 41%, of the bias. Sentence preserved verbatim as the pre-embargo record; see `v2-embargoed`.]_ RMSE improves at 11 of 15 depths;
the overall warm bias falls **41%**. The gain concentrates at 100–200 m, exactly where wind-driven
mixing and upwelling set the thermocline in this basin: bias at 125 m goes +0.506 → +0.190, at
150 m +0.436 → +0.203, at 200 m +0.272 → +0.067 with RMSE −0.100. Wind *hurts* at 50 m (+0.102)
and at the surface (0 m +0.034, 5 m +0.009). Correlation is fractionally worse; stated, not hidden.

### per-depth, 7-channel shipped model

| depth m | n | RMSE °C | clim °C | corr | bias °C | skill | ratio RMSE/σ | ±1σ | ±2σ |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 21 | 0.3972 | 0.7500 | 0.7974 | −0.0223 | +0.4703 | — | — | — |
| 5 | 959 | 0.4325 | 1.0035 | 0.9488 | −0.1065 | +0.5690 | 1.335 | 0.541 | 0.861 |
| 10 | 960 | 0.4588 | 0.9944 | 0.9402 | −0.0125 | +0.5386 | 1.375 | 0.610 | 0.905 |
| 20 | 959 | 0.7299 | 1.1287 | 0.8893 | +0.1762 | +0.3533 | 1.535 | 0.551 | 0.845 |
| 30 | 959 | 0.9513 | 1.3080 | 0.8827 | +0.4159 | +0.2727 | 1.487 | 0.463 | 0.745 |
| 50 | 958 | 1.1038 | 1.2950 | 0.8640 | +0.5185 | +0.1476 | 1.424 | 0.437 | 0.777 |
| 75 | 958 | 0.9883 | 1.3198 | 0.8443 | +0.1773 | +0.2512 | 1.283 | 0.611 | 0.894 |
| 100 | 958 | 1.1780 | 1.5501 | 0.7871 | +0.1461 | +0.2401 | 1.505 | 0.529 | 0.837 |
| 125 | 958 | 1.1874 | 1.6282 | 0.8286 | +0.1896 | +0.2707 | 1.490 | 0.507 | 0.826 |
| 150 | 950 | 1.0781 | 1.5300 | 0.8747 | +0.2033 | +0.2954 | 1.409 | 0.543 | 0.879 |
| 200 | 872 | 0.9335 | 1.5917 | 0.9287 | +0.0666 | +0.4135 | 1.432 | 0.623 | 0.923 |
| 300 | 854 | 0.8949 | 1.2678 | 0.9097 | −0.0884 | +0.2941 | 1.850 | 0.673 | 0.930 |
| 500 | 833 | 0.5588 | 0.6425 | 0.9204 | +0.0009 | +0.1302 | 1.857 | 0.725 | 0.936 |
| 700 | 827 | 0.3776 | 0.4319 | 0.9518 | −0.0179 | +0.1258 | 1.183 | 0.774 | 0.960 |
| 1000 | 803 | 0.2267 | 0.2928 | 0.9720 | −0.0045 | +0.2259 | 0.702 | 0.824 | 0.989 |

**Skill is positive at all 15 depths** (PS req 12–14 all satisfied: RMSE, correlation and bias are
each reported per depth). Correlation ≥ 0.787 everywhere. The 1000 m paradox is visible in one row:
the *best* absolute RMSE (0.2267) sits with a modest skill (+0.2259), because climatology is already
excellent there.

**Calibration, measured the way `mc_calibration.json` measured it so the comparison is like-for-like:**
ratio **0.70–1.86** against MC-dropout's **1.56–3.54** (D-016). Coverage — which the paper reports
nowhere — is **0.437–0.824 within ±1σ** (Gaussian target 0.683) and **0.745–0.989 within ±2σ**
(target 0.954). Read together with the ratios, the σ band is **too narrow through the mixed layer
and thermocline** (ratios 1.28–1.54, coverage well under target at 30–125 m) and **too wide at
1000 m** (ratio 0.702, coverage 0.824/0.989 — above target). Neither is "calibrated"; both are far
better than MC-dropout, and the direction now has a number attached at every depth.

**Not comparable to** the monthly 0.9672 (2022 Argo, different test set) or to the T_SEQ legs'
0.8529 (40k samples, 15 epochs). The only fair delta in this table is 7ch vs 5ch.


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

## v2-stage2  2026-08-31  — salinity + the paper's eq. 5 density constraint
model: TSCastNIO stage 2 — cnn3d encoder + simple decoder + 5 heads (mu_T, logvar_T, mu_S, logvar_S, logvar_rho), 560,147 params
dataset: daily bundle, **7 of 7 channels** [sst,sss,ssh,u,v,wu,wv] | P=17, T_SEQ=11
split: train 2025-06-01..2026-03-31, held-out GLORYS 2026-04-01..2026-06-23 | seed: 42
hyperparams: AdamW lr 1e-3, wd 1e-2, batch 256, 60,000 train / 12,000 held-out samples, up to 25 epochs, patience 5, beta-NLL 0.5
loss: eq. 6, L_total = L_T + L_S + L_rho, unweighted (the predicted variances are the weighting — the paper's own justification)
eos: EOS-80 / UNESCO (1983), Fofonoff & Millard — the reference the paper cites
scored on: **962 INDEPENDENT Argo profiles**, +/-5 d, from `artifacts/argo_daily_period_ts.parquet` (T **and** PSAL)

| run | eq. 5 | T RMSE degC | T skill | S RMSE psu | rho RMSE kg m-3 | predicted sigma_rho | ratio | epochs (best) |
|---|---|---|---|---|---|---|---|---|
| stage 1 (T only) | — | **0.861152** | +0.297518 | — | — | — | — | 8 (3) |
| stage 2 | ON, w=1.0 | 0.886585 | +0.276771 | 0.250354 | 0.2809 | 0.1952 | 1.439 | 9 (4) |
| stage 2 ablation | **OFF, w=0** | 0.861245 | +0.297441 | **0.243339** | **0.2796** | 1.0016 | 0.279 | 13 (8) |

**Finding 1 — salinity is essentially free.** stage 1 vs stage-2-without-eq.5 differ by
**0.000093 degC** on temperature. A whole salinity head cost nothing measurable and returned
0.2433 psu at correlation 0.968, bias -0.0003 psu.

**Finding 2 — eq. 5 does not pay for itself at this data scale.** Enabling it costs 0.0253 degC
and 0.0070 psu, and leaves density 0.0013 kg m-3 WORSE — the quantity it optimises. Its only
benefit is a density uncertainty that exists at all: with the term off, `logvar_rho` receives no
gradient and sits at its initialisation (sigma 1.0016), so the 0.279 ratio is an artefact, not a
measurement.
LIMITATION: one seed; the constrained run early-stopped at 9 epochs (best 4) against 13 (best 8),
same patience. Consistent with a constraint converging faster to a worse optimum, but a
longer-patience or 3-seed run would settle it.

per-depth salinity RMSE (psu): 0 m 0.333 · 50 m 0.312 · 100 m 0.221 · 200 m 0.219 · 500 m 0.077 ·
700 m 0.066 · 1000 m **0.052**; correlation 0.95-0.99 at every level. The surface-hard /
deep-easy gradient is what the North Indian Ocean should give (monsoon rain, Bay of Bengal river
plumes above; near-uniform deep water below).

checkpoints: `artifacts/tscast_stage2_s2.pt` (eq. 5 on, SHIPPED) ·
`artifacts/tscast_stage2_s2_nodensity.pt` (ablation). Both gitignored — the numbers live here.
artifacts: `tscast_stage2_s2_metrics.json`, `tscast_stage2_s2_nodensity_metrics.json`
reproduce:
```
PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage2     --t-seq 11 --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5     --w-density 1.0 --tag s2
```
(`--w-density 0.0 --tag s2_nodensity` for the ablation; `--beta 0` reproduces the paper's plain NLL)
git-commit: b5214ae (implementation), numbers measured at 0116bd1

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


## E-EMBARGO-01  2026-09-02  — first headline measured under the temporal embargo

**Status: VALIDATED (engineering + independent Argo) — but see the confound below.**

The matched re-run of `tscast_stage1_withUV_s42` after the A1 leakage fix (`1d3c135`). Identical
config: cnn3d / simple decoder / NLL beta=0.5 / T_SEQ=11 / 60k train / 12k held-out / seed 42 /
lr 1e-3 / batch 256 / patience 5 / latent 128 / 7 channels, daily bundle, same split.

| | leaky (INVALID) | **embargoed** | delta |
|---|---|---|---|
| Argo RMSE °C | 0.8611 | **0.8645** | **+0.0033** |
| bias °C | +0.1247 | **+0.1105** | -0.0142 |
| correlation (mean per depth) | 0.8893 | 0.8873 | -0.0021 |
| skill 1−RMSE/RMSEclim | +0.2975 | +0.2948 | -0.0027 |
| skill Murphy | +0.5065 | +0.5027 | -0.0038 |
| climatology RMSE °C | 1.2259 | 1.2259 | 0.0000 |
| n / profiles | 12829 / 962 | 12829 / 962 | 0 / 0 |

`rmse_climatology` identical to 4 dp and n identical — that is the check that both legs were
scored on **the same points**, so the delta is a real comparison and not a change of population.

**The headline moved and it moved the right way: worse.** Removing an optimistic leak should cost
accuracy, and it did. Best epoch 3, 8 epochs run — identical training dynamics to the leaky leg.

**CONFOUND, stated plainly: two things changed, not one.** The leaky leg ran on CPU, this one on
CUDA. Same seed, but CPU and GPU kernels are not bitwise identical, so **+0.0033 °C confounds
the embargo with numerical nondeterminism.** The delta also sits inside the ±0.02 °C band this
project has already shown effects can move within (wind flipped −0.0149 -> +0.0111 on one retrain).

So: **the fix is proven structurally** — 0 train/test window crossings at T_SEQ 1/11/31 on the real
388-day bundle, by a test that failed with exactly 5 crossings beforehand. **The magnitude of the
leak's cost is NOT established at n=1**, and must not be quoted as "the leak cost 0.003 °C".
Multi-seed characterisation is A10.

**This is still a GLORYS-INPUT model.** Five of seven channels are reanalysis. It is the
comparator for A9, **not** the PS-compliant satellite model, and must never be labelled one.

checkpoint: `artifacts/tscast_stage1_embargo_withUV_s42.pt` (seed 42, code_commit `8338d14`)
metrics:    `artifacts/tscast_stage1_embargo_withUV_s42_metrics.json`
train:      507.1 s on RTX 4050 (CUDA) vs 5147.5 s on CPU — **10.1x**, not the
            4.4x my 1024-sample micro-benchmark predicted. Darshan's ~9x was closer to right than
            my number was; the micro-benchmark was dominated by fixed startup cost. [VERIFIED]
