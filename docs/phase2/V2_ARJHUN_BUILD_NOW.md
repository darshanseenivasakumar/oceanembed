# V2 — ARJHUN's Claude: BUILD THE SKELETON NOW (no raw data yet)

Paste this whole file as your first message in a fresh session. Self-contained.

---

## THE SITUATION

You are building **OceanEmbed v2 = "TS-Cast for the North Indian Ocean"** for Smart India Hackathon
2026, problem **SIH26066**. You are the sole build agent.

**You do NOT have the raw daily data yet.** Darshan is downloading it on his laptop and will hand it
to you **tomorrow** — you will drop it into `data/raw/` and `data/processed/` and everything you
built will then train on it.

**So today's job is to build EVERYTHING that does not need the real data:** all the code, the model,
the harness, the metrics, the schemas — and prove each piece RUNS on fake tensors of the correct
shape. Tomorrow you plug the real data in and press train.

Repo: `D:\sih project\oceanembed`. Plan:
`C:\Users\Lenovo\.claude\plans\absolutely-based-on-everything-virtual-lerdorf.md` (read it).
Paper: `C:\Users\Lenovo\Downloads\Dharshan-SIH Reference Paper.pdf` (read methods, pages 3–7).

## GIT SAFETY RULE — non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Verify the branch and `git status` before changes. If anything could affect
> `main` or existing functionality, stop and ask first.

**ALL work on branch `phase2-tscast-nio`.** First command: `git rev-parse --abbrev-ref HEAD` — if it
is not `phase2-tscast-nio`, STOP and switch. Read-only, never edit: `src/oceanembed/`,
`app/streamlit_app.py`, `app/panels/`, the baseline `tests/`. Import from them; never modify.

## THE #1 RULE FOR TODAY — fake data proves it RUNS, never that it WORKS

Everything you build today is tested on **randomly generated tensors of the right shape**. That
proves the code executes and the shapes line up. It proves NOTHING about whether the science is
correct. We have literally had **130 tests pass while the model returned 52 °C from a 28 °C input**.

So:
- Mark every result from fake data clearly as `[SKELETON — fake data, not validated]`.
- Never say a model "works", "beats", or "is accurate" today. It cannot — there is no real data.
- Leave a single obvious "REAL DATA PLUGS IN HERE" comment at each spot where tomorrow's data feeds
  in, so wiring it up is a five-minute job, not a hunt.

## THE FIXED SHAPES — build every fake tensor to these (from config.py, do not invent)

- Grid: **100 lat × 240 lon**, 0.25°, North Indian Ocean (5–30°N, 45–105°E).
- Depths: **15 levels** exactly `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]`.
- Model input: **7 surface channels** in this fixed order
  `[sst, sss, ssh, u, v, wind_u, wind_v]`, each `(batch, 100, 240)` per day.
- Model target/output: temperature `(batch, 15, 100, 240)` + a per-depth uncertainty of the same
  shape.
- Import all of these from `src/oceanembed/config.py`. Never hardcode.

## WHAT TO BUILD TODAY, IN ORDER

Put new code under `src/phase2/tscast_nio/`. Build one piece, prove it runs on fake tensors, commit,
next piece.

1. **`docs/phase2/tscast_data_model.md`** — the input contract: the 7 channels above, shapes, units,
   daily cadence, plus the target and masks (`land_mask (100,240)`, `valid_mask (100,240,15)`).
   Post it to `docs/phase2/AGENT_SYNC.md`.
2. **`docs/phase2/tscast_output_schema.md`** — what the model returns → what the UI shows. Must have
   room for temperature + per-depth uncertainty NOW, and salinity + a density term LATER, without
   breaking.
3. **The metrics module** — correlation, bias, RMSE (per-depth and overall). Test on synthetic
   arrays where you know the answer by hand (e.g. feed identical arrays → correlation 1, bias 0).
   These are two SIH-required metrics the old build never had.
4. **The model architecture** (`src/phase2/tscast_nio/models/`):
   - a **satellite embedding encoder** — the "compact latent" the PS demands. Follow TS-Cast: 3-D
     residual conv blocks reducing the surface stack to a latent vector.
   - a **decoder** — latent → the 15 depth levels.
   - a **per-depth uncertainty head** — predicts a variance per depth (TS-Cast eq. 5 style), so the
     loss is a proper negative-log-likelihood, not plain MSE. This directly fixes our worst measured
     weakness (the old MC-dropout was 1.6×–3.5× too narrow).
   - **climatology prior + FiLM conditioning** — the model adjusts a climatology profile rather than
     guessing blind; the satellite latent modulates each layer via FiLM.
   Prove forward + backward pass runs on a fake batch and the output shape is exactly
   `(batch, 15, 100, 240)`.
5. **The bake-off harness** (`scripts/phase2/architecture_feasibility.py` already has a starter —
   finish it). It must be able to train and compare **four** candidates: MLP (control), 3-D CNN,
   CNN+attention, ViT. (No GNN — our grid is a uniform lat/lon grid, not an irregular mesh, so a GNN
   there is a CNN with extra machinery; state that plainly if asked.) Winner = smallest train/test
   gap. Wire it so that tomorrow it points at real data with a one-line change. Today, prove it runs
   one tiny epoch on fake tensors without crashing.
6. **The training script** — loads the daily grid, splits by time (train earlier months, test the
   latest months — no leakage), trains, checkpoints, logs seed + config. Today it runs on a fake
   dataset object; mark the real-data loader as the plug-in point.

## WHAT YOU CANNOT DO TODAY — do not fake these

- Do not report any RMSE / correlation / bias as a real result.
- Do not pick a bake-off winner (needs real training).
- Do not claim the model beats climatology or matches TS-Cast.
- Do not touch the UI results yet — the numbers it shows must be real, and they do not exist yet.

## HONESTY RULES

Tag claims `[VERIFIED]` (ran it, saw output) / `[INFERRED]` / `[UNKNOWN]`. Never fabricate a metric.
"It runs on fake data" is `[VERIFIED]` only as *runs*, never as *correct*. Nothing is "done" until it
trains on real data and the output is inspected — which is tomorrow, not today.

## TOMORROW — THE EXACT CHANGES TO MAKE WHEN THE REAL DATA ARRIVES

Build TODAY so that every item below is a **one-line swap or a single command**, never a rewrite.
Put each of these behind a clearly-labelled switch or a `# REAL DATA PLUGS IN HERE` comment, and
list every one of them in a file `docs/phase2/TOMORROW_CHECKLIST.md` as you create them, so Darshan
and you can run down the list without hunting.

Every plug-in point must be built today with BOTH paths present: a `USE_FAKE_DATA = True` flag (or
equivalent) at the top of each script, so flipping one boolean switches from fake tensors to the
real files. The exact changes tomorrow:

1. **Drop the data in.** Darshan gives you `data/raw/glorys_daily/` (388 daily GLORYS files),
   `data/raw/satellite_daily/` (SST/SSH/SSS daily), the daily wind, and the Argo file. They go into
   `data/raw/` exactly as named. Nothing in your code changes for this — the loaders already point
   at these paths.

2. **Flip the data flag.** In every script that has `USE_FAKE_DATA = True`, set it to `False`. That
   is the whole change — the fake-tensor generator is replaced by the real loader you already wrote
   and pointed at `data/raw/`. Grep the repo for `USE_FAKE_DATA` to find them all.

3. **Run the harmonize step** (one command) → produces the real daily 0.25° grid
   `data/processed/daily_grids.npz` with the 7 channels + target + masks. Your loader already reads
   this file; it simply did not exist until now.

4. **Run the bake-off for real** (one command) → it now trains the four candidates on the real grid
   instead of the fake batch, and writes the real winner to
   `artifacts/architecture_feasibility.json`. Today it ran one fake epoch; tomorrow it runs the full
   comparison. No code changes — same script, real data behind the flag.

5. **Train the winning model** (one command) → real checkpoint + real seed/config logged. The
   training loop is unchanged; only the dataset behind the flag is real now.

6. **Validate against independent Argo** (one command) → real RMSE, correlation, bias, per depth,
   plus skill vs climatology, written to an artifact. This is the first moment real numbers exist —
   until now every metric was `[SKELETON — fake]`.

7. **Wire the real numbers into the UI.** The UI you scaffolded reads its numbers from the artifact
   files above. Today those artifacts hold fake placeholders clearly labelled as such; tomorrow
   step 6 overwrites them with real values and the UI shows the truth. Remove every
   `[SKELETON — fake]` label only after the real number sits behind it.

**Acceptance for tomorrow:** `python scripts/phase2/accept.py` passes with real science checks — the
model beats climatology against held-out real Argo, correlation/bias/RMSE are real numbers, the
bake-off winner is recorded. Nothing is called "done" before that command is green on real data.

## FIRST REPLY

Do not code yet. Reply with: (1) confirm you are on `phase2-tscast-nio`, (2) your proposed
`tscast_data_model.md` and `tscast_output_schema.md` shapes, (3) your read of TS-Cast's
encoder/decoder/FiLM/loss from the PDF, (4) the exact list of what you will build today on fake data
and what you will leave as plug-in points for tomorrow.
