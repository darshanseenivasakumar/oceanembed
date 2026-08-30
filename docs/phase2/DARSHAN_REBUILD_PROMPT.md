# DARSHAN_REBUILD_PROMPT.md — the 24-hour build window (Sun Aug 30 → Mon Aug 31, 16:30 IST)

**Written by Arjhun's Claude, 2026-08-30, from a full audit of the repo, the TS-Cast paper (all 17
pages), and both agents' logs. Every number in this file is [VERIFIED] from a named source unless
tagged otherwise.**

---

## HOW TO USE THIS FILE (read this first, Darshan)

Your Claude builds solo until **Monday 16:30 IST**, when Arjhun's weekly limit refreshes and his
Claude takes back Unit A. You have **$90 of usage credits**. Spend them like this:

**Chat protocol — one chat per phase, tiny opening message.** After `git pull`, this file is in the
repo, so a new chat needs only this (do NOT paste the whole file):

```
Read CLAUDE.md, then docs/phase2/DARSHAN_REBUILD_PROMPT.md in full.
Execute PHASE <N>. Report the checklist at the end of the phase card when done.
```

Start a new chat when a phase ends or when the current chat gets slow/long — a long chat re-sends
its whole history with every message, and that is what drained your tokens before.

**Model strategy.** Default to **Opus 5** with extended thinking for every build phase (or Fable 5
if your plan offers it and credits allow — it is stronger per token on debugging, pricier per
token). Switch to **Sonnet 5** for Phase W2's babysitting (watching a download), Phase 6's doc
backfill, and any purely mechanical work. Do **not** use ultracode / multi-agent workflows for
building — they multiply token burn ~5–10× and this plan is already decomposed. If more than ~$25
remains after Phase 5, one `/code-review` of the branch before handback is a good spend.

**Long jobs never run inside the chat loop.** Downloads and training go in a separate terminal (or
`run_in_background`); Claude checks the log every so often. Paying Opus to watch a progress bar is
the one guaranteed way to waste $90.

**Checkpoints for you (the human):**
- Sun ~22:00 — wind download finished? T_SEQ=31 leg finished? If either failed, apply that phase's
  fallback and move on; do not let a download block the UI work.
- Mon ~09:00 — final retrain finished overnight? If not, ship the T_SEQ=11 checkpoint's numbers.
- Mon 15:30 — STOP building. Phase 6 (commit, push, sync, handback) runs no matter what state
  anything is in. An unpushed branch at 16:30 is the only true failure mode.

---

## PROMPT FOR DARSHAN'S CLAUDE — STANDING CONTEXT

You are **Darshan's Claude (Unit B)** on the OceanEmbed repo (SIH26066, Smart India Hackathon
2026 — reconstruct subsurface ocean temperature at 15 depths, 0–1000 m, from surface variables at
0.25° over the North Indian Ocean, 5–30°N / 45–105°E). `CLAUDE.md` is the constitution: evidence
tags ([VERIFIED]/[INFERRED]/[UNKNOWN]) on every claim, the 15 never-assume rules, real-data-only,
contract-first. Follow it exactly.

**TEMPORARY OWNERSHIP TRANSFER, until Mon Aug 31 16:30 IST:** Arjhun's Claude is out of tokens.
You hold BOTH units — you may edit Unit A's v2 areas (`src/phase2/tscast_nio/`, `scripts/phase2/`)
in addition to your own. Still absolutely read-only: `main` (frozen demo, tag `v1.0-demo-aug30`),
`src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, baseline `tests/test_*.py`. Work on the
existing branch **`phase2-tscast-nio`** (do not cut a new one — single writer until Monday), commit
small and often, push to origin, and post to `docs/phase2/AGENT_SYNC.md` (append at TOP, tag
`[DARSHAN]`) at the end of every phase. At 16:30 Monday Arjhun's Claude pulls and resumes from
whatever you pushed.

### The mission in one paragraph

We are rebuilding OceanEmbed as **"TS-Cast for the North Indian Ocean"** — a faithful adaptation of
Chae, Donohue & Park 2026 (*Ocean Sci.* 22, 2161–2177) — while keeping the parts of our own build
that are better than the paper. The scope triage (agreed by the team):

| BUILD (from the paper) | state | KEEP (ours, better than the paper) | CUT — do not build |
|---|---|---|---|
| CNN encoder = the embedding | **DONE** — `cnn3d` won a 4-way bake-off | Data pipeline + verifiers | F7 heatwave (data can't support it) |
| Climatology prior | **DONE & measured** (see §"prior" below) | Independent-Argo validation | F9 Sentinel |
| Uncertainty-aware NLL loss | **DONE** — beats MC-dropout | Honesty system (evidence tags, refusals, CACHED vs LIVE) | F10 priority v2 |
| Daily data + wind | daily **DONE**, **wind 0% ← you** | "Explain every output" UI | F6 events / anomaly maps |

**Do not rebuild what is built.** The v2 model already exists, trained, measured, on this branch.
Your job: wind, the T_SEQ decision, the final retrain, the broken inference path, the UI, and the
docs — in that order of dependency, per the phase cards below.

### State of the world — verified numbers you must not re-derive

- **v1 frozen headline** (`main`): satellite-driven RMSE **0.9638 °C**, skill **+0.387** vs
  climatology 1.5725, against 879 independent Argo profiles. GLORYS-driven incumbent: **0.9736 /
  +0.3809** (the only fair comparator for GLORYS-input models).
- **Encoder bake-off** (monthly, 897 independent 2022-Argo profiles, capacity levelled 370k–543k
  params): **cnn3d 0.9891** < vit 1.0071 < cnn_attention 1.0198 < blind mlp_control 1.0566.
  Ranked on independent-Argo RMSE; the gap criterion is banned (it would have crowned the blind
  control). `artifacts/architecture_feasibility.json`.
- **Decoder/loss 2×2** (monthly, same 897): simple+NLL **0.9672 / +0.3961** (winner) · simple+MSE
  0.9891 · film+MSE 1.1598 · film+NLL 1.1618. **The paper's FiLM/climatology U-Net decoder costs
  ~0.18 °C at our data scale under either loss; the NLL loss costs nothing.** Recorded ONLY in
  AGENT_SYNC 2026-08-29 §1 — the artifact was overwritten since.
- **Uncertainty**: β-NLL, **β=0.5** (plain β=0 measured collapsing variance: train NLL −1.0610 vs
  held-out +0.6732, Argo RMSE 1.1861). Calibration of predicted σ: **0.74–1.82×** (monthly),
  **0.59–1.61×** (daily) — replaces MC-dropout's measured **1.56–3.54×** overconfidence (D-016).
- **Daily bundle**: 388 GLORYS12V1 days, 2025-06-01..2026-06-23, 0 missing, verified by
  `verify_daily_bundle.py --full`. Split: train 2025-06..2026-03, test 2026-04..2026-06-23.
  5 of the contract's 7 channels — **no wind**.
- **Climatology prior = the 2019–2021 monthly climatology** (disjoint from 2025–26 → zero leakage;
  staleness measured: −0.025 °C surface, worst +0.45 °C at 100 m). NEVER rebuild it from the daily
  train period (no April/May in train; 388 days is not a climatology). Tracked copy:
  `artifacts/clim_daily.npz`.
- **Independent Argo for the daily period**: 4,331 profiles fetched (`argo_daily_period.parquet`,
  git-tracked); **962 matched at scoring** (±5 d of daily fields, median offset **0 days**; the
  commit message's 908 is the strict-window count — different filter, both true).
- **T_SEQ ablation** (daily, 962 profiles, identical everything): T=1 → 0.9096, bias +0.170;
  **T=11 → 0.8529, bias +0.036, skill +0.304** (= the current checkpoint,
  `artifacts/tscast_stage1.pt`, gitignored); **T=31 never completed — no result exists anywhere**.
  Cost: T31 = 13.8× T1 (~10 min/epoch at 40k samples on CPU).
- **370 tests pass** on this branch (86 of them tscast/daily). `scripts/phase2/accept.py` is the
  acceptance gate.

### The climatology-prior question — settled, do not relitigate

The paper's own ablation (their Fig. 5) found the climatological prior gives "only modest gains" in
accuracy — its real value is training stability. Our 2×2 measured the same thing more sharply: at
our data scale the FiLM/climatology decoder actively hurts (~0.18 °C). So the shipped stage-1 model
is **cnn3d encoder + simple head + β-NLL**, and the "climatology prior" requirement is satisfied
honestly: the prior is the skill baseline every number is scored against, the anomaly reference,
and a measured architecture option we can defend rejecting **with the paper's own finding**. The
FiLM path stays in the code (`--decoder film`) with its result recorded. An optional re-test of
FiLM at paper widths on daily data is Phase 5-STRETCH, nothing more.

### Traps that have already cost hours — do not rediscover them

1. `tests/phase2/__init__.py` shadows `src/phase2` under pytest → delete it if it ever reappears.
2. Branch names: `phase2-foo`, never `phase2/foo` (git refuses while branch `phase2` exists).
3. Every command from the repo root with `PYTHONPATH=src` (Windows venv: `.venv\Scripts\python`).
4. **Cell lookup**: `np.searchsorted(LAT,x)-1` disagrees with the frozen `grids.nearest_*` on
   75.5% of Argo profiles (~28 km). Route ALL lookups through `dataset.cell_index()` /
   the frozen helpers. If you write a new one, you have written a bug.
5. **The wind grid trap (yours, and now it matters)**: the monthly wind grid is offset **+0.125°
   in both axes** vs `config.LAT/LON` — same shape, plausible values, every value ~14 km off.
   VERIFY the NRT product's coordinates against config and regrid explicitly; never assign by
   position.
6. NetCDF global attributes are stale template junk (`field_date 2021-06-30` on a 2025 file).
   Assert the internal time COORDINATE matches the filename — `verify_daily_bundle.py` does.
7. SST bounds are 11.0–38.0 °C because the **Persian Gulf** sets both extremes (36.34 / 13.34 °C
   measured). A whole field at ~270–310 is Kelvin. Only negative salinity is unphysical (real
   Meghna estuary water reads 6.43 psu).
8. `download_argo.download()` overwrites `artifacts/argo_test.parquet` — the 2022 file every
   published number rests on. Never call it. Period fetches use `fetch_argo_daily_period.py`,
   which writes elsewhere and asserts that file's mtime unchanged.
9. **Never score against the wrong Argo period** — the trainer refuses zero-match scoring and
   prints the matched count + median offset every run. Keep that behaviour.
10. `argopy` needs **`erddapy<3`** (pinned in requirements.txt). pip "upgrading" it breaks all
    three fetchers.
11. Trainer quirk: the model is built at `t_seq=1` regardless of `--t-seq`
    (`train_stage1.py:156`) — harmless ONLY for `cnn3d` (time-agnostic pooling). Don't switch
    encoders on daily runs without fixing that line.
12. The metrics JSON's `trained_on` string is stale boilerplate; trust its `data` / `T_SEQ`
    fields. (Phase 3 fixes this.)
13. Comparison hygiene: never present daily-period 0.8529 (2026 Argo) vs monthly 0.9672 (2022
    Argo) as an improvement — different test sets. Never quote pooled correlation (0.99 — it
    mostly measures that deep water is cold); quote mean per-depth (0.889). Two skill definitions
    exist (`skill_rmse_ratio` ~0.30 vs Murphy ~0.52) — name which one, never mix.
14. Checkpoint the BEST held-out epoch, never the last (held-out loss bottoms at epoch ~2–7 and
    rises). Already implemented — keep it.
15. Below-seafloor = refusal, not NaN. `valid_mask` travels with the data; a 1000 m map covers
    75.8% of ocean cells and must say so.

### Data checklist — VERIFY FIRST, download only what is missing

Your machine is where the daily GLORYS was downloaded, so most of this should already exist.
Run the checks in Phase 0; use this table when something is absent.

| data | check | if missing |
|---|---|---|
| `data/raw/daily/` 388× `glorys_YYYYMMDD.nc` (~24.4 GB) | `PYTHONPATH=src python scripts/phase2/verify_daily_bundle.py --dir data/raw/daily --full` | re-download ~16 h via `oceanembed.data.download_glorys.download_dates(pd.date_range('2025-06-01','2026-06-23'), out_dir='data/raw/daily')` — resumable; AVOID unless truly lost |
| `data/processed/daily/{2025,2026}.npz` | exists + provenance mentions verify_daily_bundle | `PYTHONPATH=src python -m phase2.tscast_nio.daily_pipeline` (~1–2 h) |
| `artifacts/climatology.npy` (the prior; trainer hard-loads it) | `python -c "import numpy;print(numpy.load('artifacts/climatology.npy').shape)"` → (12,100,240,15) | unzip the git-tracked `oceanembed_artifacts.zip` into the repo root (restores the real Phase-1 artifact set), or reconstruct from tracked `artifacts/clim_daily.npz` (`clim_t`) |
| `artifacts/argo_daily_period.parquet` | git-tracked — comes with the pull | `PYTHONPATH=src python scripts/phase2/fetch_argo_daily_period.py` (~min, no credentials) |
| `artifacts/argo_test.parquet` (2022 — protect it) | exists | inside `oceanembed_artifacts.zip` |
| Phase-1 set (`grids.npz`, `mlp_model.pt`, `norm_stats.json`, …) | `python scripts/phase2/verify_data_bundle.py` | unzip `oceanembed_artifacts.zip`; `grids.npz` needs your Phase-2 data zip |
| **Wind 2025-06..2026-06** | — | **does not exist anywhere. Phase 1 creates it.** |
| CMEMS login | `.copernicusmarine` dir in your home, or run a 1-file test fetch | `.venv\Scripts\copernicusmarine.exe login` (your CMEMS account) |

`data/raw/satellite_daily/` (SST+SSH, Jun–Sep 2025 only, no SSS) is an orphan — nothing references
it. Ignore it; do not "complete" it.

---

## PHASE CARDS

Priority = the order below. If the clock or the credits run out, everything already done is safe
because every phase ends with commit + push + AGENT_SYNC. **Never leave a phase uncommitted.**

### PHASE 0 — Sync, environment, data audit (≤1 h, Sun evening)

1. `git fetch origin && git checkout phase2-tscast-nio && git pull origin phase2-tscast-nio`.
   This should fast-forward cleanly: your own five v2-kickoff commits were merged into Arjhun's
   line before this push, so both machines' work is already on one branch. You should see the two
   v2 contracts (`docs/phase2/tscast_data_model.md`, `tscast_output_schema.md`),
   `src/phase2/tscast_nio/`, and `scripts/phase2/pick_tseq_and_retrain.py`. If that last file is
   missing, STOP and post an ASK — the push from Arjhun's machine failed.
   Note two files resolved to Arjhun's side in that merge: `accept.py` (both machines wrote the
   same origin/main-ancestor safety check independently — yours was the idea, his was already
   implemented) and `architecture_feasibility.py` (his ran the recorded bake-off with the
   corrected cell lookup). Nothing of yours was dropped; check `git log` if you want to see it.
2. `rm -f tests/phase2/__init__.py` (trap #1). `pip install -r requirements.txt` if the venv is stale.
3. Run the data checklist above. Fix gaps per its third column.
   **Expect one gap specifically:** the raw daily `.nc` files were downloaded on YOUR machine, but
   `data/processed/daily/{2025,2026}.npz` was built on Arjhun's and is gitignored, so it is
   probably absent here. If so, start
   `PYTHONPATH=src python -m phase2.tscast_nio.daily_pipeline` **in a background terminal now**
   (~1–2 h) — Phases 2 and 4 cannot train without it. Kick off the Phase 1 wind download in
   parallel; the two do not touch the same files.
4. `PYTHONPATH=src python -m pytest tests/phase2 -q` → expect ~227 passed, and
   `python scripts/phase2/accept.py`.
5. Post `[DARSHAN] PHASE 0` to AGENT_SYNC: what existed, what you had to restore, test count.

**DONE =** tests pass + daily bundle verified (or its rebuild running) + climatology.npy present +
AGENT_SYNC posted.

**If a DONE criterion cannot be met** (here or in any phase): do not stall and do not silently
skip. Post an AGENT_SYNC entry naming what failed, what you tried, and which downstream phase it
blocks — then move to the next phase that does not depend on it. A recorded blocker is a result;
a half-finished phase nobody knew about is not.

### PHASE 1 — WIND: the one thing only your machine can do (start immediately; download runs in background)

PS requirement 8 is at 0% and it is the single blocker named in the last AGENT_SYNC entry.
Product: `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` (hourly NRT, 0.125°) — the only product
covering 2025–26. ~7.2 GB, 3–4 h. GLORYS is ocean-only; there is no wind in the daily bundle.

1. Write `src/phase2/data/download_wind_daily.py` (your area): subset 5–30N/45–105E,
   2025-06-01..2026-06-23, variables eastward/northward wind; download via `copernicusmarine`
   (fetch current API docs via Context7 first — the CLI/API changes). Chunk by month; resumable;
   start it in a background terminal NOW and continue to Phase 2 while it runs.
   **Two things already exist — copy their patterns, do not reinvent:**
   `src/phase2/data/download_wind.py` (the monthly fetch, including the CMEMS call shape) and
   `scripts/phase2/download_daily_2025_2026.py` (your own overnight launcher: resumable,
   skip-if-present, certifi `SSL_CERT_FILE` setup, running-total logging). That launcher's
   docstring records that your CMEMS credentials are already saved on this machine, so no login
   should be needed — verify with a one-file fetch before starting the 7 GB job.
2. Write the processing step: hourly → daily mean → regrid 0.125°→0.25° onto `config.LAT/LON`.
   **Trap #5: verify the source grid's coordinates first** — print them against config; write a
   test asserting the regridded output is on config.LAT/LON exactly and that a coordinate
   comparison, not shape, proved it.
3. Extend `phase2.tscast_nio.daily_pipeline` to merge `wu`, `wv` as channels 6–7 (contract order
   `["sst","sss","ssh","u","v","wu","wv"]`, frozen in `tscast_data_model.md`). Rebuild
   `data/processed/daily/*.npz`. The npz carries its channel list — readers must keep indexing by
   name, never position-assume.
4. Re-run `verify_daily_bundle.py --full` equivalent checks + a new wind sanity test (monsoon
   check: JJA wind speed over the western Arabian Sea should visibly exceed the winter mean —
   measure across months, trap: one-date checks invert seasonal signals).
5. Commit + AGENT_SYNC (include measured download size/time and the grid-offset verdict).

**Fallback:** if CMEMS refuses or the download can't finish by ~Sun 22:00, proceed on 5 channels
and state "5 of 7 channels, wind absent" beside every result — a real limitation, not a footnote.
Do not let wind block Phases 2–5.

**DONE =** 7-channel daily bundle rebuilt + verified + tests + committed, OR the fallback recorded.

### PHASE 2 — Close the T_SEQ question (runs while wind downloads; ~2.5 h CPU)

The ablation is 2/3 done; T_SEQ=31 was killed mid-run and **no result was ever recorded**.

1. Run the missing leg on the **5-channel** bundle, so it is comparable to the two recorded legs
   (they ran without wind; a 7-channel T=31 would not be the same experiment):
   `PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 --data daily --t-seq 31
   --decoder simple --loss nll --epochs 15 --train-samples 40000 --test-samples 12000`
   — tee the console to `tseq_ablation.log`, and echo `===== T_SEQ=31 =====` into that file
   before the run so the parser can find the section. **Copy `artifacts/tscast_stage1.pt` and
   `tscast_stage1_metrics.json` aside first** — every leg overwrites them, and the T=11 copy is
   currently the only surviving artifact of the best model.
2. Apply the selection rule. **Do NOT hand-write log sections for the T=1 and T=11 legs.** Their
   logs were not kept, and typing recorded numbers into a file that looks like console output is
   manufacturing evidence — the one thing this project never does. The script now takes them as
   declared inputs instead, and labels every row `measured` or `declared` in its own output:

   ```
   PYTHONPATH=src python scripts/phase2/pick_tseq_and_retrain.py --log tseq_ablation.log \
       --recorded "1=0.9096,11=0.8529" --dry-run
   ```

   The frozen rule it applies: **rank on independent-Argo RMSE; prefer the SHORTER window when
   the margin < 0.02 °C.** It refuses a partial sweep, and refuses if a leg is both measured and
   declared. Post the winner, the margin, and which rows were declared to AGENT_SYNC — if you
   quote the ranking anywhere, that provenance travels with it.
3. Do NOT start the full retrain yet if wind is still downloading — Phase 4 wants 7 channels.

**DONE =** T_SEQ=31 row exists with the same columns as the table in AGENT_SYNC 2026-08-29 §5,
winner declared by the rule, committed (log + a JSON copy of the three rows in `artifacts/`).

### PHASE 3 — Fix the inference path (it is BROKEN against the best model; ~1–2 h, Sun evening)

`phase2.tscast_nio.inference.TSCastPredictor` currently raises
`RuntimeError: Missing key(s) ... decoder.*` on the shipped checkpoint: the trainer never saves
the `--decoder`/`--loss` choice, and the predictor unconditionally builds the FiLM decoder; it
also defaults to monthly data while the checkpoint is daily/T_SEQ=11. Until this is fixed, NO
output record (and therefore no UI, no demo) can come from the best model.

1. `train_stage1.py`: save `decoder`, `loss`, `data`, `t_seq`, and the true trained-on period into
   the checkpoint dict; fix the stale `trained_on` string in the metrics JSON (trap #12).
2. `inference.py`: build the decoder the checkpoint names; load daily bundles when the checkpoint
   says daily; refuse loudly on mismatch (say what was found vs expected — refusal with a reason
   is our house style).
3. Produce ONE real prediction record end-to-end and inspect it against
   `docs/phase2/tscast_output_schema.md`: 15 depths, `sigma_t` (not log_var) as the error bar,
   per-depth `reasons` strings generated from measured quantities, `argo_check` via the F1
   collocation engine (never a second matcher), `forecast` flag correct
   (GLORYS truth ends 2026-06-23), full provenance incl. `clim_train_years=[2019,2020,2021]`.
4. Tests: checkpoint round-trip (train saves → predictor builds the right decoder), mismatch
   refusal, one output-record schema test. Commit + AGENT_SYNC.

**DONE =** a real record from the real checkpoint prints, schema-complete, tests pass, committed.

### PHASE 4 — The final stage-1 model (kick off Sun night, runs overnight)

Entry: Phase 1 (or its fallback) + Phase 2 + Phase 3 done.

1. Retrain at the chosen T_SEQ on the final bundle via
   `pick_tseq_and_retrain.py --log tseq_ablation.log` (it launches
   `--epochs 25 --patience 5` with samples matched to window cost: 100k/60k/40k for T=1/11/31).
   On 7 channels this is the first-ever wind-inclusive result — if T=11 wins, ~2 h; T=31, ~4 h.
2. Score = the trainer's built-in: 962-profile independent Argo, per-depth RMSE/corr/bias/skill
   (PS req 12–14), calibration ratio per depth measured the same way `mc_calibration.json` did
   (like-for-like vs MC-dropout's 1.56–3.54).
3. Record honestly: compare against T=11/5-channel 0.8529 (same test set — a fair delta, state
   it); never against monthly numbers. If wind did NOT land, this phase is just the full-scale
   retrain at the chosen T_SEQ (60k samples beats the ablation's 40k) — still worth it.
4. Copy the checkpoint + metrics to dated names (they are gitignored — the numbers must ALSO land
   in AGENT_SYNC and EXPERIMENT_LOG or they exist on one laptop only). Commit + AGENT_SYNC.

**DONE =** final checkpoint + metrics JSON + calibration table + AGENT_SYNC entry with the full
per-depth table and an explicit 5-vs-7-channel statement.

### PHASE 5 — The UI: explain-every-output, v2 (Mon morning, ~3–4 h — your home turf)

New pages under `app/phase2/` (never touch the frozen app). Port 8503+. Streamlit + altair
(plotly is NOT in the venv — trap #20). Everything renders FROM the prediction record — the UI
computes nothing scientific itself.

1. **Profile page** (the demo centrepiece): pick (lat, lon, date) → the record → temperature
   profile with ±σ band, per-depth `reasons` on hover/expander, `argo_check` panel showing
   prediction | nearest independent float | signed difference | distance/days/quality — "never a
   number without its ground-truth check beside it". Below-seafloor depths render as refusals
   with the seafloor depth, not blanks. `forecast=True` dates are labelled FORECAST and carry no
   accuracy claims (GLORYS truth ends 2026-06-23, Argo 2026-08-24).
2. **Benchmark tiles**: the aggregate metrics record per depth — RMSE / corr / bias / both skill
   definitions labelled, `rmse_climatology` ALWAYS beside skill (the 1000 m skill-vs-absolute
   story), n per depth, test window, CACHED vs LIVE badge (cached = the real model's saved
   metrics JSON; live = computed this session).
3. **Calibration panel — the thing the paper itself never shows**: per-depth ratio
   RMSE/RMS(σ) for v2 beside MC-dropout's 1.56–3.54, plus a coverage bar (% of independent Argo
   within ±1σ and ±2σ per depth). This is our beat-the-paper artifact; the paper contains no
   calibration/coverage figure at all [VERIFIED from the full text].
4. **Honesty page**: the 5-vs-7-channel state, the mixed-layer weakness (worse than reanalysis at
   20–75 m; inherited elsewhere — `glorys_vs_argo.json`), what CUT and why, evidence-tag legend.
5. A `check_v2_ui` entry in `accept.py` CHECKS asserting real rendered numbers match the metrics
   JSON to 4 decimals (the F1 pattern). Commit + AGENT_SYNC.

**STRETCH (only if Phases 0–5 are done and >$20 remains, in this order):** (a) stage-2 salinity —
the daily bundle already carries salinity targets, the schema has the keys as `None`, F5's EOS-80
`seawater.py` provides density for the paper's eq. 5 loss; even a first training run posted to
AGENT_SYNC is valuable. (b) FiLM at paper widths on daily data (config.py note: "restore when the
daily bundle lands") — one run, record the verdict either way.

**DONE =** pages run against the real checkpoint's records, accept.py check passes, screenshots
in the AGENT_SYNC entry.

### PHASE 6 — Handback (Mon 15:30–16:30, NON-NEGOTIABLE, run even if mid-phase)

1. Backfill `docs/EXPERIMENT_LOG.md` — it has **zero v2 entries** (CLAUDE.md's Definition of DONE
   requires metrics + checkpoint + seed + config there): bake-off, 2×2, T_SEQ legs incl. yours,
   final retrain. Every number with its source artifact. Update `docs/HANDOFF.md` (zero "tscast"
   mentions today) and `PHASE2_STATUS.md`.
2. Full `pytest` + `accept.py`; fix or honestly record failures.
3. Commit everything; `git push origin phase2-tscast-nio`.
4. Final AGENT_SYNC entry `[DARSHAN] HANDBACK`: state of every phase (done / fallback / not
   reached), the final model's numbers, what you'd do next, open `>>> ASK ARJHUN` items.

**DONE =** pushed branch + that entry. This is the only phase that may never be skipped.

---

## WHAT NOT TO DO (the CUT list, verbatim from the team decision)

F7 heatwave (monthly→daily helps but persistence still needs the full pipeline — dead for this
round) · F9 Sentinel (never built, not now) · F10 priority v2 (not in the PS, not novel) ·
F6 events/anomaly maps (built, validated, KEEP the code, but build NOTHING new on it) ·
satellite_daily completion · any GLORYS re-download that isn't a proven loss · any new
climatology · touching `main` · ultracode workflows · re-litigating settled decisions (the
decisions live in this file's standing context and `docs/DECISIONS.md` — read before disagreeing,
and if you still disagree, post the ASK rather than acting).
