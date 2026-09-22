# SIH26066 — Jury Interrogation Database (OceanEmbed / TS-Cast-NIO)

> Built 2026-09-17 by reading the **actual** repo: `OceanEmbed_Research_Paper.md`,
> `PHASE2_STATUS.md`, `PROJECT_RECORD.md §16.6`, `src/phase2/tscast_nio/models/tscast.py`,
> `encoders.py`, `dataset.py`, and `artifacts/FREEZE_MANIFEST.json` / `frozen_manifest.json`.
> Every number here is traced to a file. This is an adversarial prep doc — it is meant to find
> where you break, not to flatter you.

**Format for each important question:** Q → Probability → What they're testing → Strong answer →
Short (10–20 s) answer → If they go deeper → Evidence (file).

**Legend:** 🔴 Very-High · 🟠 High · 🟡 Medium · 🟢 Low · 🔥 MUST-KNOW.

---

## THE HEADLINE NUMBERS (memorise these exactly — do not mix them up)

| What | Number | Protocol / caveat |
|---|---|---|
| **Deliverable — satellite input, SHIPPED** | **RMSE 0.9063 °C**, skill **+0.2379** (+0.1480 where climatology is real), bias **+0.1400 °C**, corr ≈ 0.88 | `seafloor_masked_v2`, 963 independent Argo profiles, n=12,727, seed 42 |
| **Honest "leak-free" version of that same model** | **≈ 0.97–0.98 °C** | epoch chosen without seeing test block; costs **+0.0725 °C**, 3 seeds, sign holds 3/3 |
| GLORYS-input stage-1 (comparator, NOT deliverable) | 0.8826 °C | reanalysis input |
| GLORYS-input stage-2 best accuracy (NOT deliverable) | 0.8548 °C | reanalysis input, `unmasked_v1` |
| Climatology baseline you beat | RMSE_clim ≈ 1.189 °C | the thing "skill" is measured against |

**The three-sentence honesty script (say this before they force it out of you):**
"Our shipped result is 0.9063 °C RMSE from satellite inputs against independent Argo. Two honesty
caveats we put in our own manifest: the checkpoint's epoch was selected on the test period, and a
leak-free protocol costs about 0.07 °C, so the defensible number is ~0.98 °C. And 0.8548 °C exists
in our project but it is fed reanalysis, not satellite, so it is a comparator, not our deliverable."

---

## PART 0 — HONEST AUDIT (read this first)

### What is genuinely strong (lean on these)
1. **Radical honesty discipline.** Every claim is tagged `[VERIFIED]`/`[INFERRED]`/`[UNKNOWN]`;
   retractions are kept on the record; negative results are published. A jury that tries to "catch"
   you will mostly find you already caught it. This is your biggest asset — *weaponise it*.
2. **The reanalysis-ceiling analysis.** You scored GLORYS itself against the same Argo floats and
   separated *inherited* error (thermocline) from *your* error (mixed layer). Almost no student team
   does this. It is the single most sophisticated thing in the project.
3. **Real engineering rigor.** Embargoed splits, byte-identity freeze manifest, a negative test that
   catches GLORYS injected into satellite channels, a pool-signature guard against silent
   architecture mismatch, β-NLL to stop variance collapse. This is real ML engineering.
4. **Compact + reproducible.** 548,582 params, 2.2 MB, ~9 min on a laptop GPU. Easy to defend on
   feasibility and cost.

### What WILL get attacked (your six danger zones — full answers in PART 13)
1. **Your ground truth is a model (GLORYS reanalysis), not observations.** The deepest conceptual
   attack. You are teaching a net to emulate GLORYS from satellite inputs.
2. **The selection leak.** The 0.9063 epoch was chosen on the test block. Honest number ≈ 0.98 °C.
3. **Single seed (n=1)** for the deliverable headline; multi-seed is listed as future work (A10).
4. **"Not novel" — you say it yourselves.** SIH rewards innovation; you must convert this into a
   system-level contribution story, crisply.
5. **Paper/PPT vs code mismatch on the decoder.** Your write-up calls the shipped model a
   "climatology-prior FiLM decoder"; the shipped checkpoint is `decoder="simple"` — a plain MLP head
   with **no** climatology prior. Reconcile this before the jury reads both.
6. **Scope sprawl.** 17 "features"/ports, but several are `TESTED` not `VALIDATED`, some `NOT STARTED`
   (spatial-CNN F3, sentinel F9, priority-v2 F10), one `BLOCKED` (F7), fronts unvalidated. Don't let
   a demo of a weak feature sink a strong core.

---

## PART 1 — PROBLEM STATEMENT

### Q1.1 🔴🔥 In one sentence, what problem does SIH26066 ask you to solve?
- **What they test:** Do you actually know your PS, or did you build something adjacent to it?
- **Strong answer:** "Reconstruct depth-wise subsurface ocean *temperature* at 15 standard depths
  from 0 to 1000 m, from **daily surface satellite observations** at 0.25° over the North Indian
  Ocean (5–30°N, 45–105°E), evaluated by RMSE, correlation and bias, with GLORYS reanalysis as the
  training target and independent Argo floats as validation."
- **Short:** "Turn what satellites see at the sea surface into the temperature profile underneath it,
  at 15 depths, across the North Indian Ocean."
- **If deeper:** Depths are 0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m; the
  grid is 100×240 = 24,000 cells at 0.25°.
- **Evidence:** `OceanEmbed_Research_Paper.md §1.1`; `src/oceanembed/config.py`.

### Q1.2 🔴🔥 Why does this problem matter? Who cares about the subsurface?
- **What they test:** Can you connect a technical task to national/human impact?
- **Strong answer:** "Satellites only see the skin of the ocean, but the subsurface is where the
  action is: tropical cyclones draw their energy from warm water down to ~100 m (ocean heat content,
  not just SST, controls rapid intensification); marine heatwaves persist below the surface; and the
  monsoon's heat is stored at depth. Argo floats measure the interior directly but there are only
  ~2,455 across ~15 million km² of the North Indian Ocean — far too sparse to map continuously. We
  fill the gap between sparse floats and continuous satellite coverage."
- **Short:** "Cyclones, marine heatwaves and the monsoon are all driven by heat *below* the surface,
  which satellites can't see and Argo floats are too sparse to map. We map it."
- **If deeper:** For India specifically — Bay of Bengal cyclone intensification (Amphan, Fani-class
  events) is strongly modulated by subsurface heat and barrier layers; INCOIS (who owns this PS) runs
  operational ocean forecasting.
- **Evidence:** `§1.2`; JURY_NOTES `01_Problem_Statement_and_Solution.pdf`.

### Q1.3 🟠 Are you solving the whole PS or a subset?
- **What they test:** Honesty about scope; whether you over-claim.
- **Strong answer:** "The core deliverable — temperature reconstruction with uncertainty, validated
  against Argo — is complete and is the satellite-input model at 0.9063 °C. Around it we built
  anomaly/event and observation-priority products. Some extension features (a spatial-only CNN
  variant, an operational 'sentinel', priority-v2) are prototyped or not started, and we label those
  honestly rather than claim them."
- **Short:** "Core PS: done and validated. Extensions: some are prototypes, and we say which."
- **Evidence:** `PHASE2_STATUS.md` feature table (status column).

### Q1.4 🟡 What happens if this problem is NOT solved / what do people do today?
- **Strong answer:** "Today operational centres rely on the Argo array plus full physical
  data-assimilation reanalyses like GLORYS, which are computationally heavy and run at big centres.
  A light, satellite-driven reconstruction is a fast, cheap complement that can run daily on modest
  hardware and flag where the sparse float network should be reinforced."
- **Evidence:** `§1.2`, `LITERATURE_MATRIX.md`.

---

## PART 2 — SOLUTION & ARCHITECTURE

### Q2.1 🔴🔥 Explain your solution in 30 seconds (technical jury).
- **Strong answer:** "We take an 11-day window of seven satellite surface fields — SST, sea-surface
  salinity, sea-surface height, two current components and two wind components — over a 17×17 patch
  around each point. A 3-D CNN encodes that space-time cube into a 128-dimensional latent. A small
  decoder head maps that latent to 15 temperatures from 0 to 1000 m, plus a per-depth predicted
  variance for uncertainty. It's trained on GLORYS reanalysis and validated on independent Argo
  floats, reaching 0.9063 °C RMSE."
- **Short:** "A 3-D CNN turns an 11-day stack of satellite surface maps into the temperature profile
  below, at 15 depths, with an uncertainty band."
- **Evidence:** `§4.1`, `tscast.py`, `encoders.py`.

### Q2.2 🔴🔥 Explain it to a non-technical person.
- **Strong answer:** "A weather satellite can only see the top skin of the sea. But ships, cyclones
  and fisheries care about the temperature tens and hundreds of metres down. We taught a computer the
  statistical link between what the surface looks like over the last week and what the water column
  underneath is doing — so from surface pictures alone it draws the temperature all the way down,
  and honestly tells you how confident it is."
- **Short:** "Satellites see only the surface; our model reads the surface and draws the temperature
  underneath, with a confidence band."

### Q2.3 🔴🔥 Walk the data through the system: input → output.
- **Strong answer:** "Input: for a target day and location, an 11-day × 17×17 × 7-channel satellite
  cube, plus 3 geo channels (a lat/lon unit vector). → CNN3D encoder: three 3-D residual blocks
  (widths 24, 48, 96) with Mish activations, GroupNorm and average-pooling, then adaptive pooling and
  a linear layer → a 128-dim latent. → 'simple' decoder head: Linear(128→256) → Mish →
  Linear(256→30), split into 15 temperature values (z-scored per depth) and 15 log-variances. →
  De-normalise per depth to get °C and a σ band. Everything below the seafloor is masked out, never
  scored."
- **Short:** "Satellite cube → 3-D CNN → 128-number summary → small head → 15 temperatures + 15
  uncertainties → de-normalise to °C."
- **Evidence:** `tscast.py` forward() lines 272–304; `encoders.py:63–83`.

### Q2.4 🟠🔥 Why a climatology prior — and does your SHIPPED model actually use one?
- **What they test:** Whether you know your own architecture vs. your write-up. **This is a trap you
  set for yourself (danger zone #5).**
- **Strong answer (the honest one):** "The paper we reimplemented, TS-Cast, uses a *climatology-prior*
  decoder: the network adjusts a physically grounded average profile instead of guessing from
  scratch. We built that (the FiLM-conditioned climatology U-Net) — but at our data scale we
  **measured** it to cost about 0.18 °C, so it is **not** what we ship. Our shipped checkpoint uses
  `decoder="simple"`: a plain MLP head on the latent, predicting per-depth temperature anomalies
  relative to the training-mean profile. So the climatology-prior is in our codebase and reported as
  a negative result, and I should not describe the shipped model as using it."
- **Short:** "The fancy climatology-prior decoder is built but measured to hurt accuracy, so we ship a
  simpler head. I won't overclaim the prior."
- **⚠ Action for you:** Check what your PPT architecture slide shows. If it shows the FiLM/climatology
  decoder as "our model," fix it — the shipped model is the simple head. Evidence:
  `artifacts/FREEZE_MANIFEST.json:15` (`"decoder": "simple"`) vs `OceanEmbed_Research_Paper.md`
  abstract ("climatology-prior decoder") and `§4.1`.

### Q2.5 🟠 Why an 11-day input window (T_SEQ=11)?
- **Strong answer:** "We ablated it. T_SEQ=1 gives 0.9096, T_SEQ=11 gives 0.8529, and the paper's
  31-day window gives 0.9267 — worst of the three at our data scale. A short window smooths sensor
  noise without diluting the signal; the paper used ±15 days but on 1/8° NW-Pacific data with ~155k
  in-situ profiles, far more than we have. We report this as a measured disagreement with the paper.
  (Caveat: those three legs predate our leakage-embargo fix and are tagged for re-measurement.)"
- **Short:** "We tested 1, 11 and 31 days; 11 won. The paper's 31 was worst for our smaller dataset."
- **Evidence:** `§6.1`.

### Q2.6 🟡 Why 17×17 spatial patches?
- **Strong answer:** "17 cells at 0.25° is ±2.0° around the point — enough spatial context for the
  CNN to use neighbouring surface structure (eddies, fronts) without exploding compute. The bake-off
  proved spatial context matters: a centre-cell-only MLP control scored 1.0566 vs the CNN's 0.9891
  on the same data."
- **Evidence:** `§4.2`, `architecture_feasibility.json`.

### Q2.7 🟠 Where is the bottleneck / where does computation happen?
- **Strong answer:** "Inference is a single forward pass of a 0.55 M-param CNN — milliseconds per
  profile on CPU, and a full 24,000-cell daily field in seconds on the laptop GPU. The real cost is
  *data ingestion*: downloading and regridding six daily satellite products. So the bottleneck is
  I/O and preprocessing, not the model."
- **Evidence:** `§4.2` (training ~9 min / 550.7 s); `data/` download scripts.

---

## PART 3 — THE AI/ML MODEL (deep)

### Q3.1 🔴🔥 Why a 3-D CNN? Why not U-Net / Transformer / LSTM / a pretrained model?
- **What they test:** Did you *choose* the architecture or copy it? (At least one juror knows ML.)
- **Strong answer:** "We ran a four-way bake-off, ranked on held-out **independent-Argo RMSE**, with
  the same decoding head bolted onto each encoder so only the encoder varied:
  CNN3D 0.9891, CNN+attention 1.0198, centre-cell MLP control 1.0566 (ViT also ran). CNN3D won.
  Why the others lose: attention and ViT are data-hungry and we have ~60k samples from only ~388
  days — not enough to learn global attention from scratch; the MLP control has no spatial context
  and proves context matters. We deliberately did **not** rank on the train/test gap, because a model
  too weak to fit anything has a tiny gap and would win wrongly. No pretrained model exists for this
  modality (7-channel ocean surface cubes over the NIO), so transfer learning has nothing to
  transfer."
- **Short:** "We bake-off tested MLP, CNN3D, CNN-attention and ViT on real Argo error. CNN3D won;
  transformers need far more data than 388 days give us."
- **If deeper — why not GNN?** "Our grid is a uniform 0.25° lat/lon lattice, not an irregular mesh or
  sensor network. Message passing on a regular grid reduces to convolution with extra machinery and
  no graph structure to exploit." (`architecture_feasibility.json` `gnn_excluded_because`.)
- **If deeper — why not U-Net for the *encoder*?** "A U-Net is a natural *decoder* over depth (we use
  a 1-D U-Net in the unshipped FiLM variant). For the *encoder* the job is space-time→vector
  compression, which a residual 3-D CNN does directly."
- **Evidence:** `§4.3`, `architecture_feasibility.json`, `encoders.py`.

### Q3.2 🔴🔥 Give the exact input and output tensor shapes.
- **Strong answer:** "Input `x`: (B, 7, 11, 17, 17) — batch, 7 satellite channels, 11 days, 17×17
  patch. Plus `x_geo`: (B, 3, 1, 17, 17), a lat/lon unit vector broadcast over time, concatenated to
  give 10 channels into the first conv. Climatology and month index are also passed but the shipped
  simple head ignores them. Output: `mu` (B, 15) and `logvar` (B, 15) — 15 depths, mean temperature
  and log-variance."
- **Short:** "In: (B,7,11,17,17) + 3 geo channels. Out: 15 means + 15 log-variances."
- **Evidence:** `encoders.py:23–26, 63–83`; `tscast.py:272–304`.

### Q3.3 🟠🔥 What loss function, and why not plain MSE or plain NLL?
- **What they test:** The single most technically impressive design decision you made.
- **Strong answer:** "β-NLL Gaussian, β=0.5 (Seitzer et al. 2022). Plain NLL is
  0.5·exp(−logvar)·(y−μ)² + 0.5·logvar. We **measured** that plain NLL collapses the variance: on the
  first real run, train NLL fell to −1.06 while held-out NLL rose to +0.67, and Argo RMSE was 1.186 —
  worse than the 0.989 the same encoder got under plain MSE. The reason: the squared-error gradient
  is scaled by 1/σ², so the cheapest way to cut the loss is to shrink σ instead of improving the
  mean. β-NLL multiplies each point's loss by a **stop-gradient** σ^(2β), cancelling that 1/σ²
  weighting — at β=1 the mean's gradient is exactly the MSE gradient while the variance head still
  trains; β=0.5 is the recommended middle. So we get calibrated-ish uncertainty **and** a mean that
  trains properly."
- **Short:** "β-NLL. Plain NLL made the model cheat by shrinking its uncertainty instead of learning;
  β-NLL fixes that, measured."
- **Evidence:** `tscast.py:307–345` (`gaussian_nll`, with the measured numbers in the docstring).

### Q3.4 🟠 Optimizer, learning rate, batch size, epochs, early stopping?
- **Strong answer:** "AdamW, lr 1e-3, weight decay 0.01, batch 256. 25 epochs requested, 9 run, best
  epoch 4, patience 5. 60,000 train / 12,000 test samples. ~9 minutes on one laptop GPU."
- **⚠ Follow-the-thread honesty:** "Early stopping selected the best epoch on the **test block** —
  that's our known selection leak; the leak-free protocol picks a different epoch and costs +0.07 °C."
- **Evidence:** `§4.2`; `PROJECT_RECORD.md §16.6`.

### Q3.5 🟠 How big is the model? Memory, FLOPs, latency, does it need a GPU?
- **Strong answer:** "548,582 parameters, 2.2 MB checkpoint. Trains in ~9 min on an RTX-3050 laptop
  GPU; inference is milliseconds per profile and runs fine on CPU. It does **not** need a GPU to run —
  only to train fast. That's a feasibility strength: a district office could run inference on a
  laptop."
- **Short:** "Half a million params, 2.2 MB, runs on a CPU. GPU only speeds up training."
- **Evidence:** `§4.1–4.2`, `FREEZE_MANIFEST.json`.

### Q3.6 🟠🔥 Does your predicted uncertainty actually mean anything? Is it calibrated?
- **What they test:** Whether "uncertainty" is real or decoration.
- **Strong answer:** "It's a predicted per-depth log-variance, trained with β-NLL. After per-depth
  scaling, ±2σ covers 91.2% of truth (nominal 95.4%) and ±1σ covers 63.9% (nominal 68.3%) — so it's
  **mildly overconfident**, and we label the band '±2σ', never '95%'. Honest caveat: in the shipped
  model the log-variance head reads only the climatology embedding, so predicted σ captures seasonal
  and depth-dependent spread but does **not** depend on the specific day's satellite image — that's
  the paper's design and we state it rather than hide it."
- **Short:** "Yes, but mildly overconfident — ±2σ covers 91% not 95%, and we label it ±2σ, not 95%."
- **⚠ Retraction to own proactively:** "An earlier 'uncertainty is 4–5× too narrow' finding was
  **retracted** — the calibration script had been fed the GLORYS bundle instead of the satellite one.
  We kept the wrong artifact, labelled invalid."
- **Evidence:** `§5.4`; `tscast.py:18–23, 162–164`.

### Q3.7 🟡 When does the model fail? What inputs give bad predictions?
- **Strong answer:** "Three known failure regions. (1) The **mixed layer, 20–50 m** — our genuine
  weak spot, +0.23 to +0.38 °C worse than the reanalysis, warm-biased (+0.66 °C at 50 m). (2) The
  **thermocline, ~100 m** — largest absolute error (1.22 °C), but mostly *inherited* from GLORYS, not
  ours. (3) The **Bay of Bengal freshwater plume** — the satellite salinity sensor floors at ~30.8
  psu where the true value near the Ganges/Meghna is ~6.4 psu, so the model is blind to the single
  most distinctive BoB feature. And at **1000 m** climatology actually beats us by 0.055 °C — 14 of
  15 depths win, not 15, and the dashboard labels that crossover."
- **Short:** "Mixed layer 20–50 m (ours), thermocline ~100 m (inherited from GLORYS), and the Bay of
  Bengal fresh plume (a salinity-sensor blind spot)."
- **Evidence:** `§5.2, §5.3, §3.4`.

### Q3.8 🟢 Can you explain a single prediction (interpretability)?
- **Strong answer:** "Two handles. First, the prediction is a departure from a per-depth mean profile,
  so we can show the anomaly the network added. Second, the channel ablation tells us *what it uses*:
  removing SSS costs 0.0245 °C (real, holds across 3 seeds), while removing currents or wind is within
  seed noise — so at basin scale SST and SSS carry the signal. Full per-pixel attribution
  (saliency) isn't shipped; it's future work."
- **Evidence:** `§6.2`, `channel_isolation.json`.

---

## PART 4 — DATA, TRAINING, VALIDATION, METRICS

### Q4.1 🔴🔥 Where does your data come from? Is any of it synthetic?
- **Strong answer:** "All real, no synthetic data and no imputation in the shipped pipeline. Inputs:
  388 consecutive days, 2025-06-01 to 2026-06-23, zero gaps. SST from OSTIA (UKMO), SSS from
  SMOS-blended CMEMS, SSH from DUACS altimetry, currents from CMEMS GLOBCURRENT, wind from CMEMS L4.
  Target: GLORYS12V1 reanalysis regridded to 0.25°. Independent validation: gridded Argo floats,
  never used in training. A day is included only if every satellite channel, a GLORYS target and wind
  all exist for it."
- **Short:** "All real satellite products for input, GLORYS reanalysis as target, Argo floats as
  independent check. 388 days, zero gaps, no synthetic data."
- **⚠ Own the historical footnote:** Early Phase-1 work used a synthetic GLORYS stand-in for scaffolding;
  a scientific sanity test *caught* it (salinity didn't increase with depth in the BoB), and the real
  bundle replaced it. Some regenerable local files (`X_train.npy`, LightGBM baseline) are still the old
  synthetic ones on disk — they're not in the shipped path. Evidence: `PHASE2_STATUS.md` F5/ASK-DARSHAN-6.
- **Evidence:** `§3.1–3.2`.

### Q4.2 🔴🔥 Your training target is GLORYS — but GLORYS is itself a model. So aren't you just
predicting another model, not the real ocean?
- **What they test:** The deepest conceptual weakness. (Full treatment: DANGER ZONE #1.)
- **Strong answer:** "Correct, and we treat it as a first-class limitation, not a footnote. GLORYS is
  a physics-based data-assimilation reanalysis that ingests Argo, satellites and more — it's the
  standard best-available gridded truth, but it is a model. So we did the thing that makes this
  honest: we scored **GLORYS itself** against the independent Argo floats. Result — at the thermocline
  (100 m) GLORYS is already 1.04 °C off Argo, and our model is 1.22 °C, so only **0.178 °C of that
  error is ours**; the rest is inherited from the target. In the mixed layer the gap is genuinely ours.
  And critically, our **final validation is against Argo, which is real in-situ observation and never
  touches training** — so the 0.9063 °C is measured against the real ocean, not against GLORYS."
- **Short:** "GLORYS is our teacher, but our *exam* is independent Argo floats — real observations. And
  we measured how much error we inherit from GLORYS vs. cause ourselves."
- **Evidence:** `§5.3`, `§2` (target vs validation), Feature 8 Validation Lab.

### Q4.3 🟠🔥 How did you split train/test? Is there data leakage?
- **Strong answer:** "Temporal embargoed split: train 2025-06-01…2026-03-26, test 2026-04-01…
  2026-06-23, protocol `embargoed_v2`. We found and fixed a real leak: the window sampler once
  clamped to array ends instead of the split boundary, letting 5 of 304 train days read test-period
  surface fields — every test passed while it happened, which is why we now embargo the window, not
  just the split. Every artifact from before that fix (commit 1d3c135) is marked INVALID and not
  quoted. Climatology is built from 2019–2021 only, disjoint from the 2025–26 daily period, so it
  can't leak into the split or the skill baseline."
- **Short:** "Temporal split with an embargo. We caught a window-clamping leak, fixed it, and voided
  every affected number."
- **⚠ The remaining leak to own:** "One leak we ship *knowingly* and label: epoch selection used the
  test block (the selection leak, +0.07 °C)."
- **Evidence:** `§4.2, §9`; `PHASE2_STATUS.md` SUPERSEDED box; `PROJECT_RECORD.md §16.6`.

### Q4.4 🟠 How many validation profiles? Is 963 enough?
- **Strong answer:** "963 independent Argo profiles giving 12,727 depth-level comparisons under the
  seafloor mask, collocated within ≤5 days. It's a modest but honest count — every profile is real
  in-situ data the model never saw. We strengthen confidence not by inflating n but by reporting
  per-depth breakdowns, three-seed sign-stability on effects, and the reanalysis ceiling. More Argo
  and multi-year validation is explicit future work."
- **Short:** "963 real floats, 12,727 depth comparisons, none seen in training. Modest but genuinely
  independent."
- **Evidence:** `§3.2, §5.1`.

### Q4.5 🟠🔥 What metrics, and what does 'skill +0.24' actually mean?
- **Strong answer:** "RMSE, bias (mean model−truth), correlation, and skill = 1 − RMSE/RMSE_clim, i.e.
  fractional improvement over just using the monthly climatological average. +0.2379 blended means
  ~24% better than climatology. But we report **two** skill numbers: +0.2379 blended mixes in cells
  where no real climatology exists (a basin-mean fill), so on the 896 profiles with a genuine
  climatology skill is **+0.1480**. We store both and never quote one beside the other as
  interchangeable. We also report Murphy skill (1 − MSE/MSE_clim) = +0.42."
- **Short:** "Skill = % better than the climatological average. ~24% blended, ~15% where the
  climatology is genuinely resolved — we report both honestly."
- **Evidence:** `§5.1`.

### Q4.6 🟡 Why is your climatology only 2019–2021 (3 years) for a 2025–26 prediction?
- **What they test:** A subtle, fair statistical challenge.
- **Strong answer:** "The climatology plays two roles — a prior and the skill baseline — and its only
  hard requirement is that it be **disjoint** from the daily train/test period so it can't leak. 2019–
  2021 satisfies that. It's a legitimate limitation that 3 years is short (a 30-year WOA climatology
  would be more stable and would capture less interannual noise), and any warming trend between 2020
  and 2025 makes the prior slightly cold — but the model predicts an *anomaly on top of it*, so a
  biased prior is corrected by the network, and our warm bias (+0.14 °C) is consistent with that
  rather than a cold one. Extending the climatology is cheap future work."
- **Short:** "It just has to be leakage-disjoint from the daily period. 3 years is short — a longer
  climatology is on the list — but the model corrects the prior anyway."
- **Evidence:** `§3.3`; `dataset.py:337–339`.

### Q4.7 🟡 Overfitting / underfitting — how do you know which you have?
- **Strong answer:** "We measured capacity directly. At the paper's widths the model is ~7.1 M params
  — 13× our ~100k samples — and overfits by epoch 3. So we shrank it: LATENT_DIM 128, U-Net channels
  (32,64,128), giving 548k params. The generalisation gap (train vs held-out GLORYS) for the shipped
  CNN3D is 0.0616 — small. We're near the sweet spot: the tiny MLP control underfits (worst Argo error,
  smallest gap), the 7 M model overfits, ours sits between."
- **Evidence:** `§4.1, §4.3`.

### Q4.8 🟠 Class/label balance, missing values, noisy data — how handled?
- **Strong answer:** "It's regression, not classification, so no class balance issue, but there's a
  spatial imbalance: ~24% of cells are below the seafloor and are **masked** in the loss — a masked
  level contributes nothing, not a zero. Missing values: a day is dropped entirely unless all channels
  exist, so no imputation. Noise: the 11-day window and per-depth z-scoring smooth sensor noise. Argo
  pressure (decibars) vs our depth (metres) was a real bug — we were sampling floats ~1% too shallow;
  fixed with the UNESCO-1983 conversion, which moved truth 0.05–0.06 °C colder at 100–150 m."
- **Evidence:** `tscast.py:334` (mask), `PHASE2_STATUS.md` truth-table change 2026-09-07.

---

## PART 5 — NOVELTY & COMPETITORS (they will push HARD here)

### Q5.1 🔴🔥 What is actually novel? Isn't this just an existing paper (TS-Cast) with a new UI?
- **What they test:** Your single biggest scoring risk at SIH. You *admit* it's not novel — so you
  must have a crisp, honest contribution story or you lose the innovation marks.
- **Strong answer:** "We're explicit: the *method* is not novel — AI reconstruction of subsurface
  temperature from surface fields is established, and our decoder/training recipe is reimplemented
  from TS-Cast (whose code was never released). Our contribution is **system-level and regional**:
  (1) the first end-to-end **North-Indian-Ocean-specific** reconstruct→quantify-uncertainty→
  validate-against-independent-Argo→prioritise pipeline; (2) a **reanalysis-ceiling diagnostic** that
  separates inherited from model error — we haven't seen this done for this task; (3) a
  **validation-and-provenance discipline** (embargoed splits, byte-identity freeze, an input-source
  assertion that stops a reanalysis-fed model masquerading as satellite-fed); and (4) a set of
  **measured disagreements with the paper** on real regional data — its 31-day window, its density
  loss, and a satellite/reanalysis gap all fail our three-seed test. Reproducing a method correctly on
  a new region and finding where it breaks *is* a contribution — it's just an engineering-and-science
  one, not a new-algorithm one."
- **Short:** "The algorithm isn't new and we say so. What's new is an integrated, validated,
  Indian-Ocean-specific system — and honest measurements of where the published method fails on our
  data."
- **If deeper — 'so which single part is yours?':** "The reanalysis-ceiling analysis and the
  provenance/leakage discipline are the parts I'd defend as genuinely ours."
- **Evidence:** `§2, §6`; `NOVELTY_MATRIX.md`.

### Q5.2 🟠 If we remove your AI model, what's left?
- **Strong answer:** "The validation and diagnostic layer still stands on its own — the collocation
  engine, the reanalysis-vs-Argo ceiling measurement, the physics products (mixed-layer depth,
  barrier layer, ocean heat content), and the observation-priority map. Those are useful even with a
  different reconstruction model plugged in. But the reconstruction *is* the core deliverable, so I
  won't pretend the model is optional."
- **Evidence:** `PHASE2_STATUS.md` features F1, F5, F8.

### Q5.3 🟠 Who else solves this? Why not just use GLORYS, or INCOIS products, directly?
- **Strong answer:** "GLORYS and operational reanalyses are the incumbents and they're excellent — but
  they're heavy physical assimilation systems run at major centres, not a light daily model you run on
  a laptop. Ours is a fast complement, not a replacement, and it's honest that GLORYS is our teacher.
  Academic ML analogues exist (TS-Cast for the NW Pacific; various global neural reconstructions), but
  we're not aware of a validated, NIO-specific, uncertainty-quantified, Argo-checked open pipeline —
  though I'd frame that as 'not aware of' rather than 'does not exist'."
- **⚠ Do NOT invent competitors or claim 'first' without hedging.** Say "to our knowledge."
- **Evidence:** `LITERATURE_MATRIX.md`, `NOVELTY_MATRIX.md`.

### Q5.4 🟢 Can any of this be patented?
- **Strong answer:** "I wouldn't claim patentability — the method is reimplemented from published work.
  The value is the validated system and the data discipline, which are contributions to reproducibility
  and operational usefulness, not IP."

---

## PART 6 — IMPLEMENTATION & CODE (do you understand your own code?)

### Q6.1 🔴🔥 What does the `FiLM` module do, and why is it initialised to *near*-identity, not zero?
- **What they test:** Whether you understand a genuinely subtle piece of your code.
- **Strong answer:** "FiLM (feature-wise linear modulation, the paper's eq. 2) lets the satellite
  latent modulate the decoder: it outputs a per-channel γ and β and applies (1+γ)·x + β. We init the
  output weights to a **small random** value, not exactly zero. Exact-zero would make FiLM the identity
  so training starts from the pure prior — attractive — but then dγ/dh is also exactly zero, so **no
  gradient reaches the encoder** on step one and the satellite embedding stays frozen at init. The
  bug would self-heal slowly and look like a slow start, not an error. So we take γ,β ≈ 0 (still
  effectively the prior) with a 1e-3 random weight so gradients flow immediately. A test,
  `test_gradients_reach_the_encoder`, guards it. (Note: this is in the FiLM decoder, which we don't
  ship — but it's real code and a fair question.)"
- **Short:** "FiLM lets the satellite signal reshape the decoder. Zero-init would freeze the encoder's
  gradient, so we use tiny-random-init — same starting behaviour, gradients flow. There's a test for it."
- **Evidence:** `tscast.py:76–106`.

### Q6.2 🟠🔥 What is the `temporal_pool_signature` / `assert_architecture_matches` guard for?
- **Strong answer:** "It catches a silent architecture bug. The CNN3D sizes its time-axis pooling from
  the `t_seq` passed at **construction**, not from the input. If you rebuild with the wrong t_seq,
  `load_state_dict` accepts it **without complaint** — conv weights don't encode temporal extent — and
  the model then predicts differently on identical input. That actually happened: two scorers rebuilt
  with the data window (T_SEQ) instead of the construction value, and one disagreed with a checkpoint's
  own recorded RMSE by 0.02 °C. The pool signature ([2,2,2] at t_seq=11 vs [1,1,1] at t_seq=1)
  distinguishes the two architectures where the state-dict can't, and we refuse to load on mismatch."
- **Short:** "A guard against loading a checkpoint into a subtly different architecture that PyTorch
  would accept silently. We learned it the hard way — it cost us 0.02 °C once."
- **Evidence:** `tscast.py:411–500`.

### Q6.3 🟠 Why is there an S_FLOOR = 0.0 clamp and a `last_n_clamped` counter in the density loss?
- **Strong answer:** "EOS-80 density has an S^1.5 term that's NaN below zero salinity, and one NaN
  poisons every gradient in the batch. An untrained salinity head *does* emit negatives in the first
  few hundred steps, so we clamp to 0 psu (the physical fresh-water floor). But the clamp isn't free —
  it zeroes the gradient through salinity exactly (measured: 0.0 vs 32.87 on a clamped batch) — so we
  **count** how many were clamped, because a density term training while its salinity input is pinned
  at the floor is doing nothing, and the counter is the only way to see it. (Stage-2 only.)"
- **Evidence:** `tscast.py:348–404`.

### Q6.4 🟡 What happens if an input day is missing a channel / the input is null?
- **Strong answer:** "It never reaches the model: the bundle builder includes a day only if all seven
  channels, the GLORYS target and wind exist, so there are no partial days in training. At inference,
  a missing channel means we can't form the cube for that day and we decline rather than impute — the
  provenance/freeze checks assert channel presence. NaNs from land/seafloor are masked, not zero-filled."
- **Evidence:** `§3.1`; `dataset.py` valid-sample logic (`:162`).

### Q6.5 🟡 Frontend/backend — what's the stack and how do they talk?
- **Strong answer:** "Backend is Python: PyTorch model, xarray/NumPy preprocessing, the products in
  `src/phase2/`. Frontend is **Streamlit** dashboards (one per feature, ports 8501–8517) plus an HTTP
  export service (`src/phase2/api/`) that serves NetCDF. The UI reads frozen artifacts and asserts
  every rendered number equals the metrics artifact to 4 decimals (`accept.py check_v2_ui`), so the
  page can't silently recompute or reformat a result."
- **Evidence:** `PHASE2_STATUS.md` F13; `src/phase2/api/`; `JURY_NOTES/README.md` (ports).

### Q6.6 🟠🔥 Did you write this, or did an AI generate it? Can you explain it without looking?
- **What they test:** Authorship and genuine understanding. (Be honest — see PART 10 & DANGER ZONE.)
- **Strong answer:** "This was built with heavy AI-assisted coding, and I won't pretend otherwise —
  it's a hackathon and that's a legitimate tool. What makes it *ours* is that every scientific claim
  was verified by us against real data under a rule that nothing is a fact until a command produced
  it, we caught and retracted our own errors (a data leak, a miscalibrated uncertainty script, a
  pressure-vs-depth bug), and we can explain every design decision and defend the numbers. Ask me any
  function and I'll walk you through what it does and *why* it's written that way." *(Then actually be
  able to do it — Q6.1–Q6.4 are your rehearsal.)*
- **Short:** "AI-assisted, yes — but the science, the verification and the error-catching are ours,
  and I can explain any line and why it's there."
- **Evidence:** `CLAUDE.md` evidence-tag discipline; the retractions in `§5.4, §6.4, §6.5`.

---

## PART 7 — DEMO & EDGE CASES

### Q7.1 🔴🔥 Show me the model checked against a real Argo float, live.
- **Prep:** Feature 8 (`08_Feature_07`/Argo overlay, port 8508). Rehearse: pick a float, show model
  profile + ±2σ band vs the float's measured profile, point out where they agree (surface, deep) and
  where they don't (mixed layer). **Owning the disagreement live is more convincing than hiding it.**
- **Evidence:** `PHASE2_STATUS.md` F8; JURY_NOTES `09_Feature_08_Argo_Overlay.pdf`.

### Q7.2 🟠 What if I click a land cell / the Persian Gulf floor / an inland point?
- **Strong answer:** "It **refuses** with a reason, not a NaN. An inland point returns
  `LAND_IN_GLORYS`; a query below the seafloor (e.g. 26°N 52.5°E reads to 30 m and raises at 1000 m)
  is a refusal, not a fabricated value. That's deliberate — a masked level must contribute nothing,
  never a zero."
- **Evidence:** `PHASE2_STATUS.md` F1/F2; `§4.4` seafloor mask.

### Q7.3 🟠 What if the internet/GPU goes down during the demo?
- **Strong answer:** "The demo runs on **frozen artifacts** on disk — no live download or GPU needed
  to present. The model runs on CPU. Live data ingestion is the only internet-dependent part and it's
  not on the demo path. We also have cached demo scenes labelled CACHED vs LIVE."
- **Evidence:** `CLAUDE.md` real-data/CACHED rule; `demo_scenes.json`; `main @ v1.0-demo-aug30` frozen.

### Q7.4 🟡 Change a parameter live — e.g. increase the input window, or feed noisy input.
- **Strong answer:** "The What-If sandbox lets us override model/formula inputs and show baseline vs
  what-if vs delta. For window size, we'd point to the ablation (11 beats 1 and 31). For noise, the
  11-day averaging is the built-in robustness; the cloud-dropout feature (F15) tested monsoon cloud
  gaps explicitly."
- **Evidence:** `src/oceanembed/whatif/`; JURY_NOTES `16_Feature_15_Cloud_Dropout.pdf`.

### Q7.5 🟡 Edge cases — extreme/rare events the model never saw (a strong cyclone cold wake)?
- **Strong answer:** "We have a case study: Feature 17 shows a cyclone cold wake the model was not
  explicitly taught, reconstructed from the surface signature. It's presented as a qualitative case,
  not a validated skill number — we don't have enough independent cyclone-time Argo to score it."
- **Evidence:** JURY_NOTES `18_Feature_17_Cyclone_Case_Study.pdf`.

---

## PART 8 — FEASIBILITY, COST, SECURITY, IMPACT

### Q8.1 🔴🔥 Can this actually be deployed? At national scale? In rural areas?
- **Strong answer:** "Yes, cheaply. Inference is a 2.2 MB model — a full 24,000-cell daily field runs
  in seconds on a laptop GPU and minutes on CPU. National scale is trivial for the *model*; the real
  cost is ingesting six daily satellite products, which is bandwidth and a scheduled job, not compute.
  It doesn't need to run in rural areas — it runs centrally (e.g. at INCOIS) and serves maps/NetCDF/an
  API to the edge, so a low-bandwidth user just pulls a small product. No GPU is required to *use* it."
- **Short:** "The model is 2.2 MB and runs on a CPU. Run it centrally, serve products out — national
  scale is a scheduling and bandwidth problem, not a compute one."
- **Evidence:** `§4.1–4.2`; `src/phase2/api/` export service.

### Q8.2 🟠 What would deployment cost? Recurring costs?
- **Strong answer:** "Order-of-magnitude, honestly labelled as an estimate: training is ~9 min on a
  laptop GPU, so retraining is negligible. Daily operation is one modest VM plus storage for the daily
  satellite bundle (the 388-day 7-channel bundle is ~0.5 GB, so ~0.5 GB/year of inputs at this
  resolution) — a single small cloud instance, on the order of a few thousand rupees a month, not a
  HPC cluster. The expensive incumbent (full GLORYS-class assimilation) is exactly what this is a
  light complement to. [Estimate — not separately benchmarked.]"
- **⚠ Flag it as an estimate.** Don't state a precise rupee figure as if measured.
- **Evidence:** `oceanembed_daily_bundle_7ch.zip` ≈ 520 MB on disk; `§4.2` timing.

### Q8.3 🟠 How often must it be retrained? Who maintains it?
- **Strong answer:** "Retraining is cheap (~9 min), so it can be re-fit whenever a new season of
  GLORYS and Argo lands — quarterly is comfortable. Maintenance is mostly keeping the six data feeds
  alive; the model itself is small and stable. Provenance and freeze scripts mean a maintainer can
  verify a shipped checkpoint byte-for-byte rather than trust a note."
- **Evidence:** `§9` freeze discipline.

### Q8.4 🟠 Security — data, API, adversarial inputs?
- **Strong answer:** "The data is public scientific product (no PII), so privacy isn't the main axis.
  For the export API: standard hardening (auth, rate-limiting, input validation on the requested
  region/date) — it serves read-only reconstructions, so the attack surface is small. Adversarial
  robustness: inputs are physical fields with known ranges, so out-of-range values are rejected by the
  provenance checks; we don't claim adversarial-ML robustness because it's not a threat model for a
  scientific product fed by curated satellite feeds. The most 'security-like' risk is a corrupted or
  wrong-source input — which is exactly what the input-source assertion and freeze checks defend."
- **Short:** "No PII; read-only API with normal hardening. The real 'attack' we defend is a
  wrong-source input, via provenance assertions."
- **Evidence:** `§9`; `FREEZE_MANIFEST.json` `input_source` assert.

### Q8.5 🔴🔥 Who benefits, how many, and could a wrong prediction cause harm?
- **What they test:** Social impact *and* responsible framing.
- **Strong answer:** "Beneficiaries: INCOIS/IMD operational forecasting, cyclone early-warning (ocean
  heat content is a rapid-intensification predictor), fisheries (subsurface thermal structure), naval
  and acoustic applications (sound-speed profiles), and marine-heatwave monitoring — coastal
  populations of the whole North Indian Ocean rim. On harm: yes, a confident wrong subsurface
  temperature could mislead a cyclone-intensity or fisheries decision, which is exactly why we ship
  **uncertainty** with every prediction, label it ±2σ (not 95%), name the mixed layer as our weak
  spot, and mark where climatology beats us. It's a decision-support complement to Argo and reanalysis,
  not a sole source of truth — and we'd deploy it framed that way."
- **Short:** "Cyclone warning, fisheries, navy, heatwave monitoring across the NIO rim. A wrong value
  could mislead, so every prediction ships with an honest uncertainty band and named weak spots."
- **Evidence:** `§1.2, §8`; JURY_NOTES cyclone-heat & acoustics features.

---

## PART 9 — TRAP / TRICK QUESTIONS (safe, honest, strong answers)

### Q9.1 🔴🔥 "Your accuracy is high because of data leakage, isn't it?"
- **Answer:** "Partly, and we've quantified exactly how much. The temporal embargo stops input
  leakage; we caught and voided an earlier window-clamp leak. The one remaining leak is **epoch
  selection on the test block** — we ship it labelled, and the leak-free number is ~0.98 °C, +0.07 °C
  worse over three seeds. So: not fabricated, fully disclosed, and even the honest number beats
  climatology. The *validation* itself — 963 Argo floats — has no leakage; those were never in
  training." **Never get defensive; you already documented this better than they can attack it.**

### Q9.2 🔴🔥 "Isn't this just TS-Cast with a UI?"
- **Answer:** See Q5.1. "The method is TS-Cast-derived and we say so. The system, the regional
  validation, the reanalysis-ceiling diagnostic, and the measured *disagreements* with the paper are
  ours."

### Q9.3 🟠 "Your dataset is too small — only 388 days / 963 floats."
- **Answer:** "It is small, and it shapes our choices: it's *why* the CNN beats the transformer, why
  the 11-day window beats 31, and why we shrank the model 13× to avoid overfitting. We don't hide the
  size; we designed around it, and we validate on every real float we have."

### Q9.4 🟠 "Why not a simpler solution — isn't a CNN overkill vs. regression?"
- **Answer:** "We tested the simpler solution. LightGBM and an MLP profile model are in the repo as
  baselines, and the centre-cell MLP control scored 1.0566 vs the CNN's 0.9891 on the same Argo — the
  spatial model earns its complexity by ~0.07 °C. But the model is still tiny (0.55 M params), so
  it's not gratuitously complex."

### Q9.5 🟠🔥 "What is the single biggest weakness of your project?"
- **Answer:** "Two, honestly. Scientifically, the **mixed-layer warm bias (20–50 m, +0.23 to
  +0.38 °C)** — genuinely ours, not inherited. Methodologically, that our **ground truth is a
  reanalysis, not observations**, which caps how good we can be at the thermocline. We measured both
  rather than hide them, and naming them is what makes the rest of our numbers credible." **Answering
  this crisply is a *strength* signal — teams that can't name their weakness look worse.**

### Q9.6 🟡 "Which part did YOU personally build?"
- **Answer:** (Be specific and true.) Point to your unit's files: e.g. Darshan — scaffold, config,
  data pipeline, `inference/predict.py`, the Streamlit app, the wind input, the provenance/freeze
  audit. See `CLAUDE.md` file-ownership block and PART 10.

### Q9.7 🟡 "What happens when your model is wrong — how would a user even know?"
- **Answer:** "Three signals ship with every prediction: the ±2σ uncertainty band; the per-depth
  error table that says the mixed layer and thermocline are the worst; and the climatology-crossover
  label that flags where you'd be better off with the average. So a user isn't handed a bare number —
  they're handed a number, a band, and a 'trust this less here' flag."

---

## PART 10 — TEAM

### Q10.1 🔴🔥 Who did what?
- **Prep (from `CLAUDE.md` ownership + paper authorship — confirm before the jury):**
  - **Darshan (Unit B):** scaffold, `config.py`, data pipeline (`data/`, `features/`),
    `inference/predict.py`, Streamlit app, the wind input (PS req 8), provenance audit + freeze, the
    What-If calculator backend.
  - **Arjhun (Unit A):** models/train/uncertainty, the satellite-input deliverable run, OceanCube 3-D,
    physics products, events, validation lab.
  - **Mitun & Niru (Unit C):** climatology, validation metrics, anomaly product, literature/novelty.
- **⚠ Reconcile:** the research paper lists four members across three units; make sure every present
  member can defend *their* files (Q6.1–Q6.4 style) for their area. Evidence: `CLAUDE.md` ownership,
  `OceanEmbed_Research_Paper.md` byline.

### Q10.2 🟠 What was the hardest technical problem and how did you solve it?
- **Strong answer options (pick one you own):** the variance-collapse under plain NLL → β-NLL; the
  silent t_seq/architecture mismatch → pool-signature guard; the window-clamp data leak → embargoed
  split; the pressure-vs-depth truth-axis bug → UNESCO-1983 conversion. Each is a real, documented
  war story with a measured before/after.

### Q10.3 🟡 If one teammate leaves, can the rest maintain it?
- **Answer:** "Yes — every contract (shapes, filenames, constants) is frozen in `docs/DATA_CONTRACT.md`
  and `MODEL_SPEC.md` and imported, not hardcoded; there's a `CLAUDE.md` operating constitution, a
  148-page `PROJECT_RECORD.md`, and ~10k lines of tests. Onboarding is reading four docs."

---

## PART 11 — "WHY NOT X?" RAPID-FIRE

| They ask | Your one-liner |
|---|---|
| Why not a Transformer/ViT? | "Bake-off: ViT/attention need far more than 388 days; CNN3D won on Argo RMSE." |
| Why not a GNN? | "Uniform 0.25° grid has no irregular graph — message passing = convolution + overhead." |
| Why not a pretrained/foundation model? | "None exists for 7-channel NIO surface cubes; nothing to transfer." |
| Why not plain MSE? | "MSE gives no uncertainty; and we need the variance head — β-NLL gives both." |
| Why not plain NLL (the paper's)? | "Measured: it collapses the variance, RMSE 1.19 vs 0.99. β-NLL fixes it." |
| Why not the 31-day window (paper)? | "Measured worst at our scale: 0.9267 vs 0.8529 at 11 days." |
| Why not the FiLM climatology decoder? | "Measured to cost ~0.18 °C at our data scale — shipped the simple head." |
| Why not the density loss (paper eq. 5)? | "Turning it ON cost accuracy (0.8593 vs 0.8548) and worsened bias." |
| Why not stage-2 (T+S+density) as the deliverable? | "On satellite input it doesn't improve T across 3 seeds — not promoted." |
| Why not OSCAR currents (the PS product)? | "No NASA Earthdata login; used CMEMS GLOBCURRENT — same quantity, same grid, documented." |
| Why GLORYS as target not Argo directly? | "Argo is too sparse to train a dense grid; GLORYS is dense — Argo is the independent *test*." |
| Why not more Argo for validation? | "We use every float we have (963); multi-year is future work." |
| Why cloud/central not edge? | "Model is tiny but data ingestion isn't; run central, serve products to the edge." |
| Why Python/PyTorch/Streamlit? | "Standard scientific-ML + oceanography stack (xarray, argopy, copernicusmarine); fast to build and demo." |

---

## PART 12 — NUMBERS CHEAT-SHEET (know these cold)

- **Region:** 5–30°N, 45–105°E, 0.25° → 100×240 = **24,000 cells**. **15 depths**, 0→1000 m.
- **Channels (7):** SST, SSS, SSH, u, v, wind-u, wind-v (+3 geo channels internally).
- **Data:** 388 days, 2025-06-01→2026-06-23, 0 gaps. Climatology 2019–2021.
- **Model:** CNN3D encoder (widths 24/48/96, Mish, GroupNorm) → 128 latent → simple head (128→256→30).
  **548,582 params, 2.2 MB.** β-NLL loss (β=0.5). AdamW lr 1e-3, batch 256. ~9 min train, seed 42.
- **Deliverable (satellite):** **RMSE 0.9063 °C**, skill **+0.2379** (+0.1480 real-clim), bias
  **+0.1400 °C**, corr ≈0.88. 963 Argo, n=12,727, `seafloor_masked_v2`.
- **Leak-free honest number:** **≈0.98 °C** (+0.0725, 3 seeds).
- **Comparators (NOT deliverable):** GLORYS-input stage-1 0.8826; stage-2 best 0.8548.
- **Per-depth error:** 0 m 0.40 · 50 m 1.19 (worst bias +0.66) · **100 m 1.22 (worst RMSE)** ·
  1000 m 0.31 (**climatology wins here by 0.055**).
- **Reanalysis ceiling @100 m:** GLORYS 1.04 vs ours 1.22 → **0.178 °C is ours**, rest inherited.
- **Mixed layer 20–50 m:** **+0.23 to +0.38 °C worse than GLORYS — genuinely ours.**
- **Uncertainty:** ±2σ covers **91.2%** (nominal 95.4%); ±1σ 63.9% (nominal 68.3%). Mildly overconfident.
- **Channel ablation (3-seed):** drop SSS +0.0245 (**holds**); drop currents/wind within seed noise.
- **Bake-off (Argo RMSE):** CNN3D **0.9891** < CNN-attn 1.0198 < MLP-control 1.0566.
- **Tests:** ~820 passed / 9 skipped; ~36k lines source, ~10k lines tests; ~273 commits / 12 days.

---

## PART 13 — DANGER ZONE (where you are exposed — fix or rehearse before the jury)

> These are ranked. Each says the risk, the honest answer, and what to *do*.

### DZ-1 🔴 Ground truth is a model (GLORYS), not observation.
- **Risk:** A sharp juror says "you're predicting a reanalysis, not the ocean — your whole ceiling is
  a model's ceiling." True and unavoidable.
- **Honest answer:** Own it, then pivot to the two things that rescue it: (a) **final validation is
  independent Argo** — real in-situ, never in training; (b) the **reanalysis-ceiling analysis**
  quantifies inherited vs own error. You are the rare team that *measured* this.
- **Do:** Have the GLORYS-vs-Argo numbers on a slide (100 m: GLORYS 1.04, ours 1.22). Lead with it,
  don't wait to be cornered.

### DZ-2 🔴 The selection leak (0.9063 → ~0.98 leak-free).
- **Risk:** If a juror finds `selection_protocol: test_period_v0` in your manifest and you *didn't*
  disclose it, you look like you hid it.
- **Do:** Put the honest triplet on a backup slide (0.9063 shipped / ~0.98 leak-free / still beats
  climatology). **Say it before they ask.** The fix is already in code (`cc8d672`); mention the
  shipped checkpoint predates it and you chose transparency over a re-run under deadline.
- **Evidence:** `PROJECT_RECORD.md §16.6`, `frozen_manifest.json:94–98`.

### DZ-3 🔴 Paper/PPT vs code decoder mismatch.
- **Risk:** Your abstract and §4.1 describe a "climatology-prior FiLM decoder" as the model; the
  shipped checkpoint is `decoder="simple"` (plain MLP head, no climatology prior). A juror reading
  both catches a contradiction, and it undermines your "we adjust a physical prior" story.
- **Do:** **Before the jury**, either (a) fix the PPT/abstract to describe the *shipped* model (CNN3D
  → simple MLP head predicting per-depth anomalies), and present the FiLM/climatology decoder
  explicitly as a *tested-but-not-shipped negative result*; or (b) if you actually want the
  climatology story, re-run and ship the FiLM decoder and re-measure. Option (a) is faster and
  honest. **Do not** show a climatology-prior architecture slide and quote the simple-head number.
- **Evidence:** `FREEZE_MANIFEST.json:15` vs paper abstract/§4.1.

### DZ-4 🟠 Single seed (n=1) for the deliverable.
- **Risk:** "One seed isn't a result." Fair.
- **Honest answer:** "The headline checkpoint is seed 42; but every *effect* we claim (ablations,
  selection-leak cost, satellite-vs-reanalysis gap) is tested across seeds 42/43/44 with a sign-
  stability rule. Multi-seed *headline* is listed as A10 future work; the three-seed cost of the
  selection fix (0.9970/0.9757/0.9567) shows the model is stable seed-to-seed at ~±0.02 °C."
- **Do:** If you have GPU time before the jury, run seeds 43/44 of the shipped satellite config and
  report the mean — it's ~9 min each and kills this question.

### DZ-5 🟠 "Not novel" vs SIH's innovation scoring.
- **Risk:** Innovation is a scored axis; honesty about non-novelty can cost marks with a juror who
  skims.
- **Do:** Never say "not novel" as a bare sentence. Always pair it: "the *algorithm* is published;
  our *contribution* is the validated regional system + the reanalysis-ceiling diagnostic + measured
  disagreements with the paper." Put "Our contribution" as its own slide with those 3 bullets.

### DZ-6 🟠 Scope sprawl / unfinished features.
- **Risk:** Demoing a `TESTED`-not-`VALIDATED` or `NOT STARTED` feature invites "so this doesn't
  work?" Fronts are explicitly unvalidated; F3/F9/F10 not started; F7 blocked.
- **Do:** Demo only the **validated** core path (model → click-map → Argo overlay → validation lab →
  cyclone heat). If asked about others, say "prototype" or "future work" plainly. Your own
  `PHASE2_STATUS.md` status column is your script — match your words to it.

### DZ-7 🟡 Currents deviation (GLOBCURRENT vs the PS's OSCAR).
- **Risk:** "You didn't use the product the PS named."
- **Answer:** "Same physical quantity (total surface currents), same 0.25° daily grid; we used CMEMS
  GLOBCURRENT because no NASA Earthdata login was available for OSCAR. It's documented in the bundle
  provenance and checked by the freeze script." Low risk if you disclose it first.

### DZ-8 🟡 Wind is retained but doesn't help (costs +0.0111 °C).
- **Risk:** "Why keep an input that hurts?"
- **Answer:** "The PS requires wind (req 8) and it's physically motivated (Ekman, mixing). At our data
  scale its measured effect is within seed noise and slightly negative, and we say so — we keep it for
  PS compliance and physical completeness, not because we measured it to help. It still removes ~15%
  of the warm bias." Honest and defensible.

---

## PART 14 — THE 50 QUESTIONS YOU MUST MASTER

*(Full answers above; this is your revision checklist. If you can't answer one from memory, go back.)*

**Problem/impact (1–6):** 1 State PS in one line. 2 Why subsurface matters. 3 Who benefits. 4 Scale
(24k cells, 15 depths). 5 What people do today (Argo+GLORYS). 6 Solving whole PS or subset?
**Solution/arch (7–15):** 7 30-s technical pitch. 8 Non-technical pitch. 9 Input→output walk. 10 Exact
tensor shapes. 11 Why CNN3D not Transformer/GNN. 12 Why 11-day window. 13 Why 17×17 patch. 14 What the
shipped decoder actually is (simple head, NOT climatology-prior). 15 Where compute happens / bottleneck.
**ML (16–27):** 16 Why β-NLL. 17 What plain-NLL variance collapse was. 18 Optimizer/lr/batch/epochs.
19 Model size/latency/GPU-needed? 20 Is uncertainty calibrated (91% ±2σ). 21 Why logvar head ignores
satellite image. 22 When the model fails (3 regions). 23 Overfit/underfit evidence (7M overfits, we
shrank 13×). 24 Bake-off results. 25 Residual/anomaly target. 26 Seafloor masking. 27 15↔64 depth
interp.
**Data/val (28–36):** 28 Real vs synthetic (all real; synthetic caught by a test historically). 29
GLORYS-is-a-model rebuttal. 30 Train/test embargo + the leak you fixed. 31 The selection leak you
ship. 32 963 floats, independence. 33 Skill definition + why two numbers. 34 Climatology 2019–21
justification. 35 Pressure-vs-depth bug. 36 Channel ablation (only SSS survives).
**Novelty/impl (37–45):** 37 What's novel (system-level). 38 "Just TS-Cast + UI?" rebuttal. 39 Remove
the model, what's left. 40 FiLM near-identity init. 41 pool-signature guard. 42 S_FLOOR clamp. 43
Missing-channel handling. 44 Frontend/backend + UI-equals-artifact assert. 45 AI-assisted authorship
answer.
**Deploy/impact/traps (46–50):** 46 Deployability + cost estimate (labelled estimate). 47 Retrain
cadence. 48 Harm from wrong predictions + uncertainty framing. 49 Biggest weakness (mixed layer +
GLORYS ceiling). 50 The honest 3-number headline script.

---

## PART 15 — THE 20 QUESTIONS MOST LIKELY TO DESTROY A WEAK PRESENTATION

1. "Your ground truth is GLORYS, a model — so you're not predicting the real ocean." (DZ-1)
2. "Your headline epoch was chosen on the test set — what's the honest number?" (DZ-2) **← if you
   fumble this, you lose the room.**
3. "Your slide shows a climatology-prior decoder but your checkpoint says `simple` — which is it?" (DZ-3)
4. "It's one seed. That's not a result." (DZ-4)
5. "What's genuinely novel here that isn't in TS-Cast?" (Q5.1)
6. "Show me, live, where the model disagrees with a real Argo float." (Q7.1)
7. "What is the biggest weakness of your project?" (Q9.5)
8. "Which of these 17 features actually work and are validated?" (DZ-6)
9. "Why should we trust 0.9063 when climatology is 1.19 and you admit inheriting most thermocline
   error?" (Q4.5, Q4.2)
10. "Did you write this or did an AI? Explain this function without looking." (Q6.6, Q6.1)
11. "Only 388 days and 963 floats — isn't that far too little?" (Q9.3)
12. "Your uncertainty — is it real, and is it calibrated?" (Q3.6)
13. "You kept wind even though it hurts accuracy. Why?" (DZ-8)
14. "You used GLOBCURRENT, not the OSCAR product the PS names." (DZ-7)
15. "Why not a simpler regression model — why a CNN at all?" (Q9.4)
16. "What exactly did *you* build versus your teammates?" (Q10.1)
17. "What happens in the Bay of Bengal fresh plume?" (Q3.7 — salinity blindness)
18. "At 1000 m climatology beats you — so what's the model for down there?" (Q3.7)
19. "Can the government actually deploy and afford this, and who maintains it?" (Q8.1–8.3)
20. "If a wrong subsurface temperature drives a bad cyclone/fisheries call, who's responsible?" (Q8.5)

---

## PART 16 — 10 QUESTIONS TO ASK YOURSELF BEFORE THE JURY DOES

1. Does my PPT's architecture slide match the **shipped** model (simple head), or the unshipped FiLM
   decoder? **(Fix DZ-3 tonight.)**
2. Is the honest 3-number headline (0.9063 / ~0.98 / comparators) on a slide, or only in my head?
3. Can I run seeds 43 & 44 of the satellite config before the jury (~20 min total) to kill "n=1"?
4. For every feature I plan to demo, is its `PHASE2_STATUS.md` status `VALIDATED`? If not, why am I
   showing it?
5. Can each present teammate explain *their* files at the Q6.1 level of detail?
6. Do I have the GLORYS-vs-Argo ceiling numbers memorised, so I can raise DZ-1 before they do?
7. Is my cost figure labelled as an estimate, or am I about to state a rupee number as if measured?
8. If the demo laptop loses internet/GPU, does everything still run from frozen artifacts? (Test it.)
9. Can I state my biggest weakness in one confident sentence without sounding defensive?
10. If they remove my most important component (the model), can I still articulate the system's value?

---

*End of interrogation database. Regenerate/extend from `PROJECT_RECORD.md`, `PHASE2_STATUS.md`,
`OceanEmbed_Research_Paper.md`, and `artifacts/frozen_manifest.json`. Every number here is traced to
one of those. Fix the three red danger zones (DZ-1 framing, DZ-2 disclosure slide, DZ-3 decoder
mismatch) before you present.*




