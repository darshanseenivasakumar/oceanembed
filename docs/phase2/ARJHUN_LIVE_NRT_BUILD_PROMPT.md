# PROMPT FOR ARJHUN'S CLAUDE — live NRT ingestion + on-demand prediction

Paste this whole file as your first message. It is self-contained; assume you know nothing else.
Read `CLAUDE.md` and `docs/phase2/AGENT_SYNC.md` after it, then start.

This is a **separate, single-feature** build. It does not supersede
`docs/phase2/ARJHUN_NOVELTY_AND_VIZ_SPEC.md` — that document's 9 features still stand. This one adds
a 10th, on its own branch and its own port, and it does not touch anything in that spec.

---

## WHO YOU ARE, WHAT THIS IS, AND THE ONE NUMBER THAT MATTERS

You are the ML/engineering agent on **OceanEmbed**, SIH26066 (Ministry of Earth Sciences):
reconstruct depth-wise subsurface ocean **temperature** from surface satellite observations at
0.25° over the North Indian Ocean (5–30 N, 45–105 E), 15 depths 0–1000 m.

**[VERIFIED] The deliverable is `deliverable_satellite`** in `artifacts/frozen_manifest.json`:
stage-1, satellite inputs, seed 42, `cnn3d` encoder, 128-dim latent.
**RMSE 0.9078 °C, corr 0.8812, bias +0.1003**, against 962 independent Argo profiles (n=12,829).
**0.8548 °C is a GLORYS-input comparator, NOT the deliverable.** Never quote it as the headline.

---

## ⚠ BLOCKING SIDE-ASK — DO THIS FIRST, BEFORE ANY CODE

**`tscast_stage1_sat_7ch_s42.pt` does not exist on Darshan's machine.** Verified by a full-disk
search of `D:\` on 2026-09-06: only `tscast_stage1_sat_7ch_s42_metrics.json` is there. Every `.pt`
present on his side (`tscast_stage1_5ch.pt`, `tscast_stage1_7ch.pt`, `tscast_stage2_s2.pt`, and the
`artifacts/frozen/` copies) is **GLORYS-fed**. `data/processed/daily_sat/v001/` does not exist there
and `data/raw/satellite_nrt/` is empty.

So the whole satellite leg — raw NRT files, the processed bundle, and the trained weights — exists
**only on your machine**. This is why `artifacts/frozen_manifest.json` records
`"checkpoint_present": false` and `"checkpoint_sha256": null` for the project's headline claim.

**Before you build anything, do these three things and report the results:**

1. Confirm `artifacts/tscast_stage1_sat_7ch_s42.pt` exists on your machine. Print its size.
2. Compute and print its **SHA256**.
3. Get the file to Darshan (git-lfs, a shared drive, or whatever transfer you two already use), and
   post the SHA256 in `docs/phase2/AGENT_SYNC.md` so the frozen manifest can finally be completed.

If the checkpoint does **not** exist on your machine either, **stop and say so immediately** — that
is a much bigger problem than this feature, because it means the project's headline number has no
reproducible weights anywhere, and Darshan needs to know today, not after you have built a UI.

---

## THE DEADLINE STANCE

Darshan's instruction, unchanged from the novelty spec: **every feature lives on its own branch and
never touches anything shared until it is built and tested.** Build what you can. This feature
proves itself independently before it goes anywhere near `phase2-tscast-nio` or `main`.

## THE BRANCH-BASE CORRECTION

**[VERIFIED] `main` is a STALE Phase-1 snapshot** — `origin/main` is ~186 commits behind
`phase2-tscast-nio` and is missing nine feature subsystems. `src/phase2/` exists on `main` in some
checkouts, which makes this easy to miss.

**This branch forks from `phase2-tscast-nio`, never from `main`.**

```
git fetch origin
git checkout phase2-tscast-nio && git pull
git checkout -b phase2-live-nrt
```

Branch names use a **HYPHEN**. Git refuses `phase2/anything` while a branch named `phase2` exists.

## THE GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

Read-only, no exceptions: `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, the baseline
`tests/`. **Import from them. Never edit them.**

## OWNERSHIP

You own `src/phase2/` and **new files you add** to `app/phase2/` and `tests/phase2/`.

**Off limits (Darshan's F1, read + import only):** `src/phase2/data/collocation.py`,
`app/phase2/collocation_page.py`. Post an ASK in AGENT_SYNC if either needs a fix.

**Do not edit** `src/phase2/data/download_satellite_daily.py` or
`src/phase2/tscast_nio/sat_daily_pipeline.py` in place. They are the frozen provenance path for the
headline bundle. **Import their functions.** If one genuinely needs a change, post an ASK first.

---

## WHAT DARSHAN ASKED FOR, AND WHAT IT ACTUALLY MEANS

His words: *"I want to get live data from all the satellite observation producers and provide live
prediction."*

Two corrections were established while scoping this, and the design already reflects them. Do not
re-litigate them:

**1. "All producers" is one API.** Every input channel already comes from **Copernicus Marine
(CMEMS)**, and the project is already on the **NRT** product lines:

| Channel | Dataset ID | Variables |
|---|---|---|
| SST | `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | `analysed_sst` (KELVIN — convert) |
| SSH + currents | `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` | `adt`, `ugos`, `vgos` |
| SSS | `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` | `sos` |
| Wind | `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | u/v, hourly → daily mean |

These IDs are in `src/phase2/data/download_satellite_daily.py:53-55` and
`src/phase2/data/download_wind_daily.py:50`. **Reuse them by import. Do not retype them** — a typo
here silently changes the product line and invalidates every comparison to the headline.

**2. "Live" cannot mean "today."** From the project's own catalogue probe on 2026-08-31:

| Channel | Coverage ended | Lag |
|---|---|---|
| SSH | 2026-09-01 | ~0 d |
| SST | 2026-08-30 | ~1 d |
| **SSS** | **2026-08-25** | **~6 d — binding constraint** |

The model needs **T_SEQ = 11 consecutive days** of all 7 channels. One slow channel gates the whole
window. So the freshest honest prediction is roughly **today − 6**, and the UI must say so.

**Darshan's chosen mode, decided:** *pick any date on demand.* The user selects a date; the system
checks the 11-day window, downloads whatever is missing, and predicts. This is deliberately not a
scheduled auto-run — it demos offline from cache and never depends on a cron job surviving until
judging.

---

## RESOLVE THESE TWO BEFORE WRITING THE HARNESS — only your machine can answer them

Write the answers into the branch's first commit message and into AGENT_SYNC. They are open
questions, not assumptions.

1. **Is NRT coverage still within ~6 days today?** The lag table above is from 2026-08-31. Re-probe
   with the existing `--probe` path (`python -m phase2.data.download_satellite_daily --probe`) and
   record today's real per-channel end dates. If SSS has slipped to 10+ days, say so — it changes
   what the UI should default to, and it is a finding worth a slide either way.
2. **Does climatology cover the requested month?** The model predicts a **residual on top of monthly
   climatology**, so a date whose month has no climatology cannot be predicted at all. Find where
   the daily/monthly climatology is built (`scripts/phase2/build_daily_climatology.py`) and
   determine its month coverage. If a requested date falls outside it, the page must refuse with
   that exact reason — never silently substitute a neighbouring month.

---

## WHAT ALREADY EXISTS — the reuse table. Do not rebuild any of this.

```python
# Downloading NRT days (already resumable, already the right product line)
from phase2.data.download_satellite_daily import ...   # SST/SSH/SSS, dataset IDs at :51-55
from phase2.data.download_wind_daily import DATASET_ID, regrid_to_config

# Building a 0.25 deg bundle from raw satellite files (bilinear regrid, provenance stamping)
from phase2.tscast_nio.sat_daily_pipeline import ...   # writes data/processed/daily_sat/v001/

# Inference — BOTH of these already accept an injected bundle
from phase2.tscast_nio.inference import TSCastPredictor
from phase2.tscast_nio.field import predict_field

p = TSCastPredictor(checkpoint="artifacts/tscast_stage1_sat_7ch_s42.pt", data=<your live bundle>)
out = predict_field(p, date)
# out: temperature (100,240,15) degC, sigma (100,240,15) CALIBRATED,
#      valid_mask, land_mask, provenance
```

**`TSCastPredictor.__init__` already takes `data=`** (`inference.py:34`). That is the whole reason
this feature is small: you are not writing a new inference path, you are handing the existing one a
freshly-downloaded bundle instead of an archived one.

**Two guards already exist and must stay live — do not bypass either:**

- `TSCastPredictor._refuse_on_cadence_mismatch()` (`inference.py:161`) reads the median time step and
  refuses if a daily checkpoint is fed monthly data, or the reverse. Your live bundle must have a
  proper `times` array or this will fire — correctly.
- The satellite-vs-reanalysis check in `scripts/phase2/audit_ps.py:99-102`: every channel's
  `provenance.channels[<k>].data_class` must contain the string `SATELLITE`. `sat_daily_pipeline.py`
  already stamps `SATELLITE_DERIVED` / `SATELLITE + INSITU_BLEND`. **Reuse that exact check.**

Also reuse: the click-any-pixel pattern, the `st.expander` *"Formula & How to Read This"* footer
convention from `app/phase2/validation_page.py`, and the port-registry pattern in `.claude/launch.json`.

---

## WHAT DOES NOT EXIST — build it, and test it, never assume it works

- A **window planner**: given a target date, compute the 11 days needed, and report per channel which
  of those days are present on disk vs missing vs unavailable upstream.
- An **incremental fetcher**: download only the missing days, into `data/raw/satellite_nrt/`.
- A **live bundle assembler**: turn those 11 days into the in-memory dict `TSCastPredictor(data=…)`
  expects, with a correct `times` axis and full provenance stamped per channel.
- The **page** itself.

---

## THE FEATURE

### `phase2-live-nrt` — port **8518** — on-demand live NRT prediction

Ports 8501–8510 are registered in `.claude/launch.json`; 8511–8517 are claimed by the nine features
in `ARJHUN_NOVELTY_AND_VIZ_SPEC.md`. **8518 is this one.** Register it in `.claude/launch.json` the
same way the existing ten are registered.

**Goal:** prove the system is not a museum piece running on a frozen 388-day archive — it ingests
current observations and reconstructs the subsurface from them on request.

**Build, in this order. Each step is testable on its own; do not skip ahead to the UI.**

**Step 1 — window planner + coverage report.** A pure function: `date → plan`. For each of the 7
channels and each of the 11 days, classify as `on_disk` / `downloadable` / `unavailable_upstream`.
No network calls beyond the catalogue probe. **Test this first, with a fake disk state** — it is the
piece everything else depends on and the easiest to get subtly wrong at window edges.

**Step 2 — incremental fetcher.** Download only `downloadable` days. Resumable: interrupt it and
re-run, and it must not re-download what it already has. Cache into `data/raw/satellite_nrt/`.
**Cache is not an optimisation here, it is the demo-day safety net** — a repeated date must work
with the network unplugged.

**Step 3 — bundle assembler.** Raw files → the bundle dict, via the existing
`sat_daily_pipeline` regrid path (bilinear onto `config.LAT/LON`; every satellite grid is offset,
including the 0.25° currents which sit half a cell — ~14 km — off, so "already 0.25°, no regrid
needed" is FALSE). Stamp provenance per channel with the same `data_class` strings the frozen
pipeline uses. Assert the `SATELLITE` check passes before returning; **raise, do not warn**, if a
channel is not satellite-class.

**Step 4 — the page.** Date picker → plan → fetch → predict → display.

**Must be on screen, not buried in a log:**

- The **date being predicted**, large and unambiguous.
- **Per-channel lag in days**, as a small table: channel · product ID · NRT/REP line · newest day
  available · days behind today.
- A clear **incomplete-window state**: if any channel cannot fill all 11 days, show exactly which
  channel and which days are missing, and **refuse to predict**. Do not partially fill. Do not
  substitute climatology for a missing day on this page — that is feature 8's cloud-dropout
  experiment, deliberately scoped elsewhere, and mixing them would make both dishonest.
- The reconstructed **0.25° temperature map** for the chosen date, depth-selectable.
- **Click any pixel → its 15-depth profile with the calibrated σ band.**
- A **provenance block**: checkpoint filename + SHA256, every dataset ID used, and the
  `data_class` of each channel — so a judge can see the inputs really were satellite.

**Honesty rules for this page, non-negotiable:**

- **Never display or imply "today"** unless the data genuinely reaches today. Say
  *"reconstruction for 2026-08-31 · freshest complete window · 6 days behind real time"*.
- State that these are **NRT** products, and that Phase 1's satellite headline (0.9638) was measured
  on the **REP/delayed-mode** line. **Numbers from the two lines are not directly comparable**, and
  the page must say so wherever both could be read together.
- The σ shown is **measured-calibrated**, and coverage is ~91% against a 95.4% nominal target. Label
  it as measured coverage. **Never label it "95% confidence."**
- No accuracy claim on this page. The 0.9078 °C headline was measured against 962 independent Argo
  profiles over a fixed test window. **A live date has no Argo ground truth yet**, so this page
  shows a reconstruction, not a validated score. Say that in the footer.
- End the page with the standard **"Formula & How to Read This"** `st.expander`, same shape as the
  other pages.

---

## WORKFLOW PER STEP

1. `git checkout phase2-tscast-nio && git pull && git checkout -b phase2-live-nrt` (once).
2. Write the test first. Steps 1–3 are all pure-enough to test without the network — mock the disk
   state and the catalogue response.
3. Implement. Run the tests. Run the existing suite to prove you broke nothing.
4. Commit with a message that states what was verified and how.
5. Post progress in `docs/phase2/AGENT_SYNC.md`, including the two resolved open questions above.
6. **Do not merge.** Report back; Darshan decides integration.

## TRAPS THAT HAVE ALREADY COST THIS PROJECT HOURS

- **`analysed_sst` is Kelvin**, GLORYS `thetao` is °C. Silent if missed.
- **Currents are geostrophic** (`ugos`/`vgos` from altimetry); GLORYS `uo`/`vo` include ageostrophic
  Ekman flow. A real physical difference, not a units bug.
- **`adt` ≠ `zos`** — absolute dynamic topography on a mean geoid vs SSH above geoid. Close
  analogues that can carry a constant offset.
- **Every satellite grid is offset** from `config.LAT/LON`, currents by half a cell (~14 km). This
  project has already been bitten once by a ~28 km cell-lookup error.
- **CMEMS reports time bounds in seconds for some datasets and milliseconds for others** — the
  existing probe code at `download_satellite_daily.py:76` already handles this. Reuse it.
- **The default bundle path is the GLORYS one.** A satellite-trained network was once fed GLORYS
  reanalysis because `D.load_daily()` defaults to `data/processed/daily`. Always pass `data=`
  explicitly.

## HONESTY RULES

- Tag every claim **[VERIFIED]** (you ran it), **[INFERRED]**, or **[UNKNOWN]**. Never state a
  result you did not measure.
- Real data only. No synthetic fills, no placeholder numbers, no "approximately correct" maps.
- If a step does not work, report it as a negative result and leave it visible. This project already
  ships a physics-loss term that was tested, hurt, and was left off — negative results are normal
  here, not failures.

## FIRST REPLY — do not write code yet

Reply with:

1. Does `tscast_stage1_sat_7ch_s42.pt` exist on your machine? Size and **SHA256**.
2. Today's real per-channel NRT coverage end dates, from a live `--probe`.
3. The climatology's month coverage, and whether a today-minus-6 date falls inside it.
4. Your build order, if it differs from steps 1–4 above, and why.

Then stop and wait for Darshan.
