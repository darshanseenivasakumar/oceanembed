# V2 PROMPT — ARJHUN's Claude (Unit A: the model)

Paste this as your first message in a fresh session. Self-contained.

---

## WHAT WE ARE DOING

We are building **OceanEmbed v2 = "TS-Cast for the North Indian Ocean"** for Smart India Hackathon
2026, problem **SIH26066**. Our old build (`main`) meets only 8 of 14 PS requirements — its biggest
miss is that it has **no satellite embedding**: it uses a plain MLP. v2 fixes this by rebuilding the
model from the published paper **TS-Cast** (Chae et al., Ocean Sci. 2026) for our region.

Repo: `D:\sih project\oceanembed`. Full plan:
`C:\Users\Lenovo\.claude\plans\absolutely-based-on-everything-virtual-lerdorf.md` — read it.
The TS-Cast paper is at `C:\Users\Lenovo\Downloads\Dharshan-SIH Reference Paper.pdf` — read its
methods (pages 3–7): the 3D-CNN satellite encoder, U-Net decoder, FiLM conditioning, and the
uncertainty-aware loss (their equations 2, 5, 6). **Reimplement from the description — do not copy
code; their code is not released.**

**You are Unit A: the model — the embedding encoder, decoder, training.**
Darshan's Claude is Unit B: data pipeline, metrics, and the UI. Do not build his parts.

## GIT SAFETY RULE — non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Verify the branch and `git status` before changes. If anything could affect
> `main` or existing functionality, stop and ask me first.

Branch for all v2 work: **`phase2-tscast-nio`**. `main` is frozen — never touch it.
Your code lives in `src/phase2/tscast_nio/models/` and `src/phase2/tscast_nio/train/`.
Do NOT edit `src/oceanembed/`, the frozen app, or Darshan's `data/` — import, never modify.

## HONESTY RULES

- Tag claims `[VERIFIED]` / `[INFERRED]` / `[UNKNOWN]`. Never fabricate a metric or an uncertainty.
- A model "improves" only if the comparison actually ran on held-out real data.
- Nothing is "done" until it trains, validates against independent Argo, and the numbers are logged.

## THE MODEL — TS-Cast-NIO

Pipeline: **daily surface fields → embedding encoder → latent vector → decoder → 15-depth
temperature + per-depth uncertainty**, with monthly climatology injected as a physical prior.

- **Inputs:** 7 daily 0.25° surface channels — SST, SSS, SSH/SLA, current U, current V, wind U,
  wind V — plus position/time encoding. Consume exactly what Darshan's
  `docs/phase2/tscast_data_model.md` defines. Do not start until that schema is posted.
- **Target:** GLORYS daily gridded subsurface temperature (the PS's named training target).
- **Depths:** exactly `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]` from `config.py`.

## YOUR TASKS, IN ORDER

1. **Architecture bake-off (do this FIRST — it decides everything).** Train, on the real daily data,
   these candidates for the embedding encoder: CNN (weight-shared), ViT (patch + global attention),
   Autoencoder, GNN (message passing), CNN+attention hybrid. Same task, same split, same epochs.
   Winner = smallest train/test gap at comparable train loss. Record it to
   `artifacts/architecture_feasibility.json`. **This is how we answer a jury's "why not a
   transformer?" with a measured number, not an opinion.** A starter script may already exist at
   `scripts/phase2/architecture_feasibility.py` (Darshan's session began one) — finish/verify it.
2. The **winning embedding encoder**.
3. The **decoder** → 15 depths.
4. **Climatology prior + FiLM conditioning** (TS-Cast) — the model adjusts the average, not guesses.
5. **Uncertainty-aware loss** — predict per-depth variance (TS-Cast eq. 5). Real calibrated error
   bars, replacing the old MC-dropout (which we measured as 1.6–3.5× overconfident).
6. **Temporal sequence input** — a daily window around each date (TS-Cast uses ±15 d).
7. **Train**, checkpoint, log seed+config for reproducibility. Hand the predictions + per-depth
   metrics arrays to Darshan's UI via the agreed `tscast_output_schema.md`.

## SPLIT (no leakage)

Train 2025-06 → 2026-03, test 2026-04 → 2026-06 (temporal holdout). The honest skill check is
**RMSE / correlation / bias vs independent Argo** in the test window, plus skill vs climatology,
per depth. Compare to TS-Cast's published RMSE (generally <1 °C, worst at the thermocline).

## HOW DARSHAN TESTS YOU

`python scripts/phase2/accept.py` — add a v2 model science check (e.g. the bake-off ran, the model
beats climatology at held-out Argo, uncertainty is not wildly miscalibrated). A check that only
proves a module imported is worse than none.

## FIRST REPLY

Do not code yet. Reply with: (1) your read of TS-Cast's encoder/decoder/FiLM from the PDF, (2) your
bake-off design (candidates, split, metric), (3) anything in the plan you think is wrong. Wait for
Darshan's `tscast_data_model.md` before building against the data.
