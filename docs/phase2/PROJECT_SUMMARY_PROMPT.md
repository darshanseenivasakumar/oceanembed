# PROMPT — ask a fresh Claude to summarise OceanEmbed: what is built, what is next

Paste this whole file as your first message in a new session. It is self-contained.

---

You are picking up **OceanEmbed**, my Smart India Hackathon 2026 project. I need you to produce a
clear, honest summary of **what we have built** and **what we are going to build**.

## RULES FOR THIS TASK

1. **Verify before you write.** Everything below is what I believe is true. Check it against the
   repo. If a number or file I state does not match what you find, **say so explicitly** rather than
   repeating my version. I would rather be corrected than flattered.
2. **Tag every claim**: `[VERIFIED]` you ran something and saw the output · `[INFERRED]` reasonable
   but untested · `[UNKNOWN]` not checked. Only VERIFIED claims may be stated as fact.
3. **Never fabricate** a metric, a citation, a benchmark, or a capability. If something is not
   measured, say it is not measured.
4. **Do not modify anything.** This is a read-and-summarise task. Do not edit code, do not commit,
   do not checkout branches, and above all **never touch `main` or `main1`**. Read only.
5. If you think our approach or a claim is wrong, **say so**. That is more useful than agreement.

## THE PROBLEM WE ARE SOLVING

**SIH26066**, Ministry of Earth Sciences. Reconstruct **depth-wise subsurface ocean temperature**
from **surface satellite observations**, at **0.25 degree** resolution, over the **North Indian
Ocean (5-30N, 45-105E)**.

Why it matters: satellites see only the ocean's skin. Argo floats measure the interior directly, but
about 2,455 floats across roughly 15 million square kilometres is extremely sparse. The interior is
where cyclone intensification, marine heatwaves and monsoon heat content actually live. So the task
is an **inverse problem**: infer the 3-D interior from the 2-D surface.

## WHERE THE CODE IS

Repo: `D:\sih project\oceanembed` (GitHub `darshanseenivasakumar/oceanembed`, private).
Team: Darshan (me), Arjhun, Mitun, Niru. Two Claude agents: mine and Arjhun's.

Read these first, in order:

- `CLAUDE.md` — the operating rules
- `PHASE2_STATUS.md` — the feature status table
- `docs/phase2/AGENT_SYNC.md` — the channel between the two agents; the LOG is newest-first
- `docs/phase2/ARJHUN_HANDOVER_PROMPT.md` — what Arjhun is building and the measured numbers
- `src/oceanembed/config.py` — the frozen constants everything imports

## PHASE 1 — BUILT, FROZEN, TAGGED

`main` is at commit `4995444`, tagged `v1.0-demo-aug30`. **142 tests passed at that tag.** It is
frozen: no Phase-2 work may touch it. This is what gets demonstrated at the Aug 30 gate.

What it does, end to end:

- **Data**: GLORYS12 reanalysis from CMEMS as training truth (regridded to 0.25 degrees, 48 monthly
  timesteps, 2019-2022), real Argo floats as **independent** validation, satellite L4 products for
  inference. Nothing synthetic.
- **Grid**: 100 latitudes x 240 longitudes x **15 depths**
  `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]` metres.
- **Features (11)**: `sst, sss, ssh, u, v, sin_lat, cos_lat, sin_lon, cos_lon, sin_doy, cos_doy`.
- **Models**: a per-column MLP (11 -> 128 -> 128 -> 15, about 19,983 parameters) as the lead, with
  LightGBM (15 boosters, one per depth) as a baseline and fallback, and monthly climatology as the
  floor everything must beat.
- **Split**: train 2019-2021, test 2022, seed 42. Temporal holdout, not a random split — adjacent
  cells and days would leak.
- **Uncertainty**: MC-dropout, 30 passes. **Measured as roughly 4x overconfident at the thermocline**
  (decision D-016). We report measured error instead, and say why.
- **UI**: a Streamlit app (`app/streamlit_app.py`) — map, vertical profile, baseline comparison,
  validation panel.

### The headline result — quote this one

Satellite-driven reconstruction against **879 independent Argo profiles** (never used in training):

| | RMSE (C) | skill vs climatology |
|---|---|---|
| **our model, satellite inputs** | **0.9638** | **+0.387** |
| our model, GLORYS inputs | 0.9736 | +0.381 |
| climatology baseline | 1.5725 | — |

**There is also a +0.626 number from the GLORYS holdout. Never conflate the two — quote +0.387**,
because Argo is an independent source and GLORYS is what we trained on.

Per-depth skill is **positive at all 15 depths**, from **+0.225 (1000 m)** to **+0.501 (500 m)**;
100 m is **+0.417**. Source: `artifacts/argo_error_by_depth.json`.

**Explain the 1000 m number correctly, it is counter-intuitive.** Low skill there is not weakness:
climatology RMSE at 1000 m is only 0.28 C because the deep ocean barely varies, so there is almost
nothing to beat. Our absolute RMSE there is **0.22 C, our best at any depth.** Low skill, excellent
prediction. Always show absolute RMSE beside skill or the story misleads.

**Trap:** the field `rmse_glorys` in that JSON is **our model fed GLORYS inputs**, NOT the GLORYS
reanalysis itself. It has been misread before.

## PHASE 2 — WHAT IS BUILT SO FAR

Branch `phase2-collocation`, currently at `0df4056`. **172 tests.** `main` untouched.

**F1 — multi-source collocation engine. DONE.**
`src/phase2/data/collocation.py`. `CollocationEngine.collocate(lat, lon, datetime)` takes one point
and returns every source at that point — GLORYS, satellite, subsurface, the nearest Argo float —
with the **measured** spatial and temporal offset of each match, a HIGH/MEDIUM/LOW/REJECT quality
derived from those measurements rather than invented thresholds, explanatory flags, and provenance.
Missing values are `None`, never `0.0`. Land and out-of-domain points are rejected with a reason.
Browser page at `app/phase2/collocation_page.py` (port 8502, separate from the frozen demo).

**A real finding, measured after F1.** `scripts/phase2/glorys_vs_argo.py` measures the **GLORYS
reanalysis itself** against independent floats — something nothing else in the repo did.
Results in `artifacts/glorys_vs_argo.json`:

- GLORYS disagrees with real floats most at **100 m (0.79 C mean absolute)** and least in the deep
  ocean (**0.22 C below 500 m**), and carries a systematic **~0.5 C warm bias at 75-125 m**.
- Tightening the match to <=25 km and <=3 days removes only **0.02 C** of that 100 m gap, so it is
  **real reanalysis error, not collocation mismatch**.
- With bootstrapped 95% intervals, our satellite-driven model is **indistinguishable from the
  reanalysis at 8 of 14 testable depths, better at 1 (1000 m), and worse at 5** — those 5 being
  **20, 30, 50, 75 and 300 m**, the mixed layer and upper thermocline.

**What that means, and it is the most important thing in the project:** our thermocline error is
largely **inherited from the training data, not created by the model** — a model cannot be more
right than what it was taught. Our genuine weak spot is the **mixed layer at 20-75 m**. Say both.

Caveat to state if pressed: the interval is bootstrapped on the reanalysis only, since per-profile
model residuals are not saved. A paired test would widen it and move verdicts *toward*
"indistinguishable", so the 20-75 m verdicts are safe and the 300 m and 1000 m ones are marginal.

**Data prepared for Phase 2** (all downloaded and verified, nothing synthetic):
`data/processed/grids.npz`, `data/processed/subsurface.npz` (salinity + currents),
`data/raw/wind/` (48 months including wind stress). Verify with
`python scripts/phase2/verify_data_bundle.py` — it checks files, contract, and **science**.

## PHASE 2 — WHAT WE ARE GOING TO BUILD

Ten features total. Ownership was reassigned: I am low on tokens, so **Arjhun builds and I test**.
The brief he is working from is `docs/phase2/ARJHUN_HANDOVER_PROMPT.md`.

| # | Feature | Status |
|---|---|---|
| F1 | Collocation engine | **DONE** |
| F2 | OceanCube — 3-D volume object, then 3-D view | next; split into F2a data layer, F2b rendering |
| F3 | Spatial CNN | not started; only 48 timesteps to train on |
| F4 | Calibrated uncertainty + out-of-distribution detection | not started; D-016 says MC-dropout is overconfident |
| F5 | Physics — thermocline depth, mixed-layer depth, ocean heat content | not started; unblocked, real density available |
| F6 | Event detection | partly unblocked; eddy **tracking** impossible at monthly cadence |
| F7 | Subsurface heatwave | **BLOCKED** — monthly sampling makes persistence uncomputable |
| F8 | Validation Lab | not started; highest credibility, needs no new data |
| F9 | Ocean Sentinel | not started |
| F10 | Observation Priority v2 | lowest value; v1 exists and the idea is not novel (JTECH 2023) |

Acceptance is one command: `python scripts/phase2/accept.py` — branch safety, full test suite, data
verification, then a per-feature **science** check.

## THE DEADLINE

Today is **26 August 2026**. The inter-college screening gate is **30 August** — four days away. The
gate demos the **frozen Phase-1 build**, not any Phase-2 feature. Remaining gate work is the PPT and
two full demo rehearsals. **Gate preparation outranks Phase-2 building.**

## WHAT I WANT YOU TO PRODUCE

A single clear summary document with these sections. Write for a **smart reader who does not know
oceanography** — my teammates and the judges both have to follow it.

1. **The problem in plain words** — what is broken about knowing the ocean's interior, and why it
   matters for India specifically (cyclones, monsoon, fisheries).
2. **What we built** — the Phase-1 system end to end, in plain language, with the real numbers.
3. **How good it actually is** — the honest verdict, including where it is weak. Include the
   inherited-error finding, it is our strongest scientific point.
4. **What is genuinely novel and what is not.** Be strict. "AI reconstructs subsurface temperature"
   is **not** novel — it is published work. Argue novelty only at the **system level** (an
   integrated, North-Indian-Ocean-specific reconstruct → uncertainty → validate → prioritise tool)
   and only if you actually believe it after looking.
5. **What we are building next**, with honest status and the two features that are blocked or
   de-scoped and why.
6. **The risks**, and what we do if each one bites.
7. **The three sentences I should say to a judge** if I only get thirty seconds.

Before writing, run these and use what you actually see:

```
git log --oneline -5
python -m pytest -q
python scripts/phase2/verify_data_bundle.py
python scripts/phase2/glorys_vs_argo.py
```

## THINGS NOT TO SAY

- Do not claim we invented subsurface reconstruction. We did not.
- Do not quote +0.626 as the headline. Quote **+0.387**.
- Do not describe MC-dropout spread as calibrated confidence. It is measured as overconfident.
- Do not say "the AI tells MoES where to deploy floats." Say "regions where additional in-situ
  observations may provide high scientific value."
- Do not present skill at 1000 m as a weakness without explaining that climatology is already
  near-perfect there.
- Do not hide the 20-75 m mixed-layer weakness. Naming it is what makes the rest credible.

Start by verifying, then write the summary.
