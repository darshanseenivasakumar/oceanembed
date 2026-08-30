# V2 PROMPT — DARSHAN's Claude (Unit B: data, pipeline, UX)

Paste this as your first message in a fresh session. Self-contained.

---

## WHAT WE ARE DOING

We are building **OceanEmbed v2 = "TS-Cast for the North Indian Ocean"** for Smart India Hackathon
2026, problem **SIH26066**. An honest audit of our old build (`main`) showed it meets only **8 of 14**
PS requirements. v2 fixes that and meets **all 14**, using the architecture from the published paper
**TS-Cast** (Chae et al., Ocean Sci. 2026), rebuilt for our region.

Repo: `D:\sih project\oceanembed`. Full plan:
`C:\Users\Lenovo\.claude\plans\absolutely-based-on-everything-virtual-lerdorf.md` — read it.

**You are Unit B: data pipeline, preprocessing, metrics, and the whole UI/UX.**
Arjhun's Claude is Unit A: the model (encoder-decoder embedding, training). Do not build his parts.

## GIT SAFETY RULE — non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Verify the branch and `git status` before changes. If anything could affect
> `main` or existing functionality, stop and ask me first.

Branch for all v2 work: **`phase2-tscast-nio`** (already created off `phase2-collocation`).
`main` is frozen at `v1.0.2-demo-aug30` — never touch it.

## HONESTY RULES

- Tag claims `[VERIFIED]` (you ran it) / `[INFERRED]` / `[UNKNOWN]`.
- Never fabricate a metric. Every number is measured on real data before it is shown.
- 2027 is a **forward forecast** (no truth exists yet), never a validated result.
- Nothing is "done" until it runs end-to-end on real data and is inspected.

## STATE RIGHT NOW

- **The daily download is already running in the background** (started by Darshan's Claude). It
  pulls 2025-06-01 → 2026-06-23 daily data into `data/raw/` — GLORYS, satellite (SST/SSH/SSS), wind,
  Argo. ~40 GB, ~20 h, resumable (existing files skipped). CMEMS login is already saved, no password
  needed. **First thing: check it is still progressing** — `ls data/raw/glorys_daily/ | wc -l` should
  grow. If it died, restart it (see the launcher script the session left in `scripts/phase2/`).

## YOUR TASKS, IN ORDER

Build one at a time. Test each before the next. All code under `src/phase2/tscast_nio/data/` and
`app/phase2/`. **Do NOT edit `src/oceanembed/`, `app/streamlit_app.py`, or `app/panels/`** — import
from them, never modify.

1. **Preprocess + harmonize** all downloaded sources to a single **0.25° daily** grid. Output a
   daily version of the grids file. Reuse the existing regrid/mask logic from
   `src/oceanembed/data/preprocess.py` — do not reinvent it.
2. **Add wind** as two input channels (wind U, wind V). Old build had none.
3. **INCOIS gridded Argo** downloader (server: `las.incois.gov.in`, OPeNDAP, use the `certifi` SSL
   fix — the same one in `download_argo.py`) PLUS keep raw Argo via `argopy`. Both are validation
   sets, shown side by side.
4. **Metrics module** with **correlation, bias, RMSE** (per-depth + overall). The old metrics.py has
   RMSE/MAE/skill but NOT correlation or bias — the PS names both. Add them.
5. **Shared contract** `docs/phase2/tscast_data_model.md` — the exact shape/names/units the pipeline
   produces and the model consumes. Write this FIRST and post it to `AGENT_SYNC.md` so Arjhun codes
   against it. Also agree `docs/phase2/tscast_output_schema.md` (what the model returns → what the UI
   shows) with Arjhun before building the UI.
6. **The UI/UX** (`app/phase2/tscast_page.py`, new file). Requirements, all from Darshan:
   - a **plain-language summary under every output** — what it is + how it works, simple but
     professional, with the real keywords (thermocline, mixed layer, embedding, steric).
   - **benchmark tiles**: RMSE / correlation / bias / skill, large, compared to TS-Cast's published
     numbers and to climatology.
   - **live "model vs actual Argo" on every panel** — prediction, nearest real Argo reading, and the
     difference. Never a number without its ground-truth check.
   - the embedding/quality explained **where the number appears**, not in a separate doc.
7. **Port the honesty layer + provenance** from the old build into v2.

## HOW YOU TEST

`python scripts/phase2/accept.py` (extend it with a v2 data check). Plus a
`verify_daily_bundle.py`: files present, 0.25° daily grid, all 7 input channels, GLORYS target
aligned, wind present, Argo covers the 2026 test window, monsoon reversal + BoB fresh-cap science
checks. Run the app and click through on real data.

## FIRST REPLY

Do not code yet. Reply with: (1) confirm the download is progressing, (2) the exact
`tscast_data_model.md` schema you propose (shapes, channel order, units, daily cadence), (3) anything
in the plan you think is wrong.
