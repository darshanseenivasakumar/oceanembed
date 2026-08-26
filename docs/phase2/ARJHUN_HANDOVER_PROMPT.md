# PROMPT FOR ARJHUN'S CLAUDE — taking over Darshan's Phase-2 features

Paste this whole file as your first message. It is self-contained; assume you know nothing else.

---

## WHO YOU ARE AND WHAT THIS IS

You are the ML/engineering agent on **OceanEmbed**, Smart India Hackathon 2026, problem statement
**SIH26066** (Ministry of Earth Sciences): reconstruct depth-wise subsurface ocean temperature from
surface satellite observations at 0.25 deg over the North Indian Ocean (5-30N, 45-105E).

Repo: `D:\sih project\oceanembed` (GitHub `darshanseenivasakumar/oceanembed`, private).
Team: Arjhun (you), Darshan, Mitun, Niru. Two Claude agents only: yours and Darshan's.

**Phase 1 is COMPLETE and FROZEN.** `main` is tagged `v1.0-demo-aug30`. 142 tests pass.
Headline, reproducible and seeded: satellite-driven reconstruction vs **879 independent Argo
profiles** gives **RMSE 0.9638 C, skill +0.387** against climatology. There is also a +0.626 number
on the GLORYS holdout. **Never conflate the two. Quote +0.387** — it is the honest one, because Argo
is an independent source and GLORYS is our training truth.

## THE GIT SAFETY RULE — from Darshan, verbatim, non-negotiable

> Work only on the current feature branch. Never modify, checkout, reset, merge, rebase, or push to
> `main` or `main1`. Before making changes, verify the current branch and `git status`. Implement
> only the requested feature, keep existing functionality untouched, and commit changes only after
> testing passes. If anything could affect `main`/`main1` or existing functionality, stop and ask
> me first.

Also read-only, no exceptions: `src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, and the
baseline `tests/`. Import from them. Never edit them. If you need different behaviour, write an
adapter under `src/phase2/`.

## OWNERSHIP HAS CHANGED — you now own Darshan's areas too

Darshan is low on tokens, so he is handing you the build and keeping the testing. `CLAUDE.md` and
`docs/phase2/AGENT_SYNC.md` previously said you must not touch his files. **That restriction is
lifted for the areas below, and only these.** The transfer is logged in AGENT_SYNC.

You now own, in addition to your own areas:
`src/phase2/cube/`, `src/phase2/validation/`, `src/phase2/priority/`, and **new files you add** to
`app/phase2/`.

**F1 STAYS DARSHAN'S — BOTH HALVES.** Do not edit either of these:
- `src/phase2/data/` — the collocation engine
- `app/phase2/collocation_page.py` — the collocation page

You may **read** and **import** from both, and you should. But if F1 needs a fix, **post an ASK in
AGENT_SYNC and let Darshan fix it.** He is keeping F1 himself. Add your own pages to `app/phase2/`
as new files (e.g. `cube_page.py`, `validation_page.py`); never modify his.

Darshan will not edit your directories while you hold them. Still off limits to both of us:
everything in `src/oceanembed/` and the frozen app.

## WHAT ALREADY EXISTS — do not rebuild any of this

**F1 collocation is DONE**, on branch `phase2-collocation`, commit `c2bffd9`. 171 tests pass.

- `src/phase2/data/collocation.py` — `CollocationEngine.collocate(lat, lon, datetime)` returns a
  `Collocation` dataclass with `requested` / `matched` / `offsets` / `sources` / `quality` /
  `flags` / `provenance`. Quality is HIGH/MEDIUM/LOW/REJECT derived from **measured** offsets, not
  invented thresholds. NaN becomes `None`, never `0.0`.
- `app/phase2/collocation_page.py` — Streamlit page on port 8502, separate from the frozen demo.
- **This is the entry point for everything else. F2/F8/F10 consume the record it returns.**

**Data already downloaded and verified — do NOT re-download anything:**

- `data/processed/grids.npz` — 48 months, surface vars, `temp` (48,100,240,15), `land_mask`,
  `valid_mask` (bathymetry; 24% of ocean cells are shallower than 1000 m and MUST stay masked)
- `data/processed/subsurface.npz` — salinity + currents, (48,100,240,15)
- `data/raw/wind/` — 48 months including eastward/northward stress
- `artifacts/` — `mlp_model.pt`, `lgbm_model.pkl`, `climatology.npy`, `argo_test.parquet`,
  `argo_error_by_depth.json`, `norm_stats.json`, `provenance.json`, `satellite_bias.json`

Run `python scripts/phase2/verify_data_bundle.py` once before you start. It checks FILES, CONTRACT
and SCIENCE. If check 3 fails, stop and report — do not build on data that failed the science check.

Frozen constants live in `src/oceanembed/config.py`. **Import them. Never hardcode.**
15 depths: `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]`.

---

## YOUR TASK: THREE FEATURES, IN THIS ORDER

Build **one at a time**. Branch, build, test, push, report. Never several at once. Darshan tests each
one before you start the next.

Branch names use a **HYPHEN**: `phase2-ocean-cube`. Git refuses `phase2/anything` while a branch
named `phase2` exists — it fails with `cannot lock ref`. This is not style, it is a hard failure.

### PRIORITY 1 — F2 OceanCube, but SPLIT IT

Branch `phase2-ocean-cube`, code in `src/phase2/cube/`.

Build the **data layer first, the 3-D rendering last.** The cube schema is what your own F5/F6/F9
code against, so the schema unblocks you; the pretty rendering does not.

**F2a — the cube object (do this first):**

A single object holding a reconstructed 3-D volume for one timestamp: temperature over
(lat, lon, depth), plus the `valid_mask`, plus per-cell uncertainty if available, plus provenance
saying which model and which inputs produced it. It must:

- import grid/depth constants from `config.py`
- carry `valid_mask` with it and refuse to return values where the sea floor is shallower than the
  requested depth (24% of cells — the Persian Gulf at ~20 m must never appear at 1000 m)
- expose slicing: a depth level, a vertical section along a lat or lon line, a single profile
- record provenance on every extraction
- write the schema to `docs/phase2/data-model.md` — **this file is shared, and Darshan codes F8/F10
  against it.** Post the schema to AGENT_SYNC before you rely on it.

**F2b — 3-D visualisation (only if F2a is done, tested and pushed):**

A Streamlit page in `app/phase2/`. Plotly volume or isosurface. It must degrade gracefully: if the
render is slow or fails, fall back to a 2-D depth-slice view rather than showing a broken page.

### PRIORITY 2 — F8 Validation Lab

Branch `phase2-validation`, code in `src/phase2/validation/`, page in `app/phase2/`.

This is the highest-credibility feature for a judge and needs **no new data and no training** — it
reads artifacts that already exist. It shows, honestly, where the model is good and where it is not.

Must show:

- **Per-depth RMSE and skill vs climatology** from `argo_error_by_depth.json`. [VERIFIED] Skill is
  **positive at all 15 depths**, from **+0.225 (1000 m)** to **+0.501 (500 m)**; 100 m is **+0.417**.
  **Read `rmse_glorys` in that file correctly: it is OUR MODEL FED GLORYS INPUTS, not the GLORYS
  reanalysis.** Mislabelling it in the UI would be a serious error.
  **The counter-intuitive bit you must explain, not hide:** skill is *lowest* at 1000 m, and that is
  not a weakness. Climatology RMSE at 1000 m is only 0.28 C because the deep ocean barely varies, so
  there is almost nothing to beat. Our absolute RMSE there is **0.22 C — our best number at any
  depth.** Low skill, excellent prediction. Show absolute RMSE next to skill or the panel misleads.
- **The GLORYS-vs-Argo gap — now measured properly, use these numbers.**
  Run `python scripts/phase2/glorys_vs_argo.py`; it writes `artifacts/glorys_vs_argo.json`. This
  measures the **reanalysis itself** against independent floats, which nothing else in the repo did.
  [VERIFIED] across 2,455 profiles / 11,761 depth comparisons at the same <=5-day filter:
  - GLORYS is worst at **100 m: 0.79 C** mean absolute, and only **0.22 C below 500 m**.
  - It carries a systematic **warm bias of about -0.5 C at 75-125 m** (floats are colder than the
    reanalysis). Consistent, not noise.
  - Tightening collocation to <=25 km and <=3 days removes only **0.02 C** of that 100 m gap, so it
    is **real reanalysis error, not collocation mismatch.** That is the finding.
  - So our thermocline error is largely **inherited**: at 100 m we are at 1.16 C against the
    reanalysis's own 1.14 C. We have hit the ceiling of our training truth.
  - **With bootstrapped 95% intervals** (the script does this; do not compare bare RMSEs, a 0.02 C
    gap over a few hundred floats is noise): of 14 testable depths our satellite-driven model is
    **indistinguishable from the reanalysis at 8**, **better at 1 (1000 m)**, and **worse at 5**.
    The 5 are **20, 30, 50, 75 and 300 m** — the mixed layer and upper thermocline. **That is our
    genuine weak spot, and the panel must say so.** The 0 m level has too few floats to compare;
    report it as such rather than comparing on 32 samples.
  - The interval is bootstrapped on the reanalysis only (per-profile model residuals are not saved).
    A paired test would widen it and move verdicts TOWARD "indistinguishable", so the 20-75 m
    verdicts are safe while the 300 m and 1000 m ones are the marginal ones. State this if asked.
  Do NOT quote the old single-point "1.83 C at 15N 65E" figure. That was one profile on one date and
  the basin-wide number is 0.79 C.
- **Model vs baselines** — climatology and LightGBM, on the same held-out set.
- **The known weaknesses, stated plainly.** MC-dropout is roughly 4x overconfident at the
  thermocline (decision D-016). Satellite covers 24 of our 48 dates. Argo is 2022 only.

A judge trusts a team that shows its worst number. Do not hide the thermocline.

### PRIORITY 3 — F10 Observation Priority v2 — BUILD LAST, AND ONLY IF TIME REMAINS

Branch `phase2-priority-v2`, code in `src/phase2/priority/`.

Be honest with Darshan about this one: a v1 heuristic already exists, and the idea is **not novel** —
optimal-observation placement is published (JTECH 2023). It is the weakest of the three for a judge.
If Aug 30 prep is competing for time, **skip it and say so.** Do not build it to look busy.

If you do build it: score = weighted combination of normalised absolute anomaly, model uncertainty,
and sparsity (distance to nearest recent Argo). Weights documented and configurable, never
hardcoded. Restrict ranking to cells that pass `valid_mask` — v1 ranked the Persian Gulf at ~20 m
depth as top priority, which is a bug, not a finding. Frame the output strictly as *"regions where
additional in-situ observations may provide high scientific value"* — never "the AI tells MoES where
to deploy floats."

---

## THE AUG 30 STOP-LINE — read this before you plan

Today is **26 August 2026**. The inter-college gate is **30 August**, four days out. What gets
demoed is the **frozen Phase-1 build**, not these features. You are also drafting the PPT and there
are two full demo rehearsals to run.

Therefore: **gate preparation beats Phase-2 features.** If you reach a point where continuing to
build would cut into PPT or rehearsal time, **stop building, say so, and switch.** Landing F2a and
F8 cleanly is a better outcome than three half-finished features and a shaky demo. If you can only
finish one, finish **F8** — it is the one that makes the existing demo more convincing.

Tell Darshan honestly what you did not get to. Do not quietly de-scope.

## WORKFLOW PER FEATURE — follow every step

1. `git status` and confirm the branch. Confirm `main` is untouched.
2. `git checkout phase2-collocation && git pull` then branch from it — F1 is the dependency.
3. Research first. Use Context7 for current library docs (plotly, streamlit, xarray, torch) before
   coding against them — your training data may be stale.
4. Build the smallest working version.
5. Write real tests under `tests/phase2/`. **Do NOT create `tests/phase2/__init__.py`** — it shadows
   the `src/phase2` package and breaks imports under pytest only. This has bitten us on three
   separate branches. If it exists, delete it.
6. Run the FULL suite: `PYTHONPATH=src python -m pytest -q`. All 171+ must pass, not just yours.
7. Run a real-data smoke test and **inspect the actual numbers**. Passing tests do not mean correct
   science — we once had 130 tests green while the model returned 52 C from a 28 C input.
8. Extend `scripts/phase2/accept.py` with a check for your feature (see below). This is required.
9. Commit only after tests pass. Push the feature branch. Never push main.
10. Append to `docs/phase2/AGENT_SYNC.md` at the top of the LOG, tagged `[ARJHUN]`, with evidence
    tags, and say exactly how Darshan should test it.

## HOW DARSHAN TESTS — you must make this cheap

Darshan is short on tokens. He should not have to work out how to test your feature. There is one
command:

```
python scripts/phase2/accept.py
```

It verifies the branch is safe, runs the full suite, runs the data verifier, then runs a
feature-specific check for whatever is on the current branch. **Every feature you build must add its
own check function to that script**, asserting real science, not just that the module imported. Then
tell Darshan in AGENT_SYNC: the branch name, the one command, and what he should see on screen.

## HONESTY RULES — these are what make the project defensible

Tag every claim: **[VERIFIED]** you ran it and saw the output, **[INFERRED]** reasonable but
untested, **[UNKNOWN]** say so. Never claim code works unless you executed it. Never fabricate a
metric, an uncertainty, or a citation. Never invent a threshold and describe it as calibrated — we
already had to tear out fabricated HIGH/MEDIUM/LOW reliability labels once. If a number is measured,
say what measured it and against what.

If Darshan's spec here looks wrong to you, say so before building. His check on your F5 physics was
wrong once and your code was right — being challenged is the point of having two agents.

## TRAPS THAT HAVE ALREADY COST US HOURS

- `tests/phase2/__init__.py` breaks imports under pytest. Never create it.
- Branch `phase2/x` fails while branch `phase2` exists. Use `phase2-x`.
- Backticks in a `git commit -m` message get command-substituted by bash and silently delete text.
  Use `git commit -F -` with a quoted heredoc.
- `st.cache_data` silently excludes any argument whose name starts with an underscore. Naming every
  argument `_lat, _lon, ...` pins the first result forever and it looks like a science bug.
- On Windows, Streamlit runs as `python.exe`, so `ps | grep streamlit` finds nothing and you will
  believe a stale server is dead when it is still serving old code. Use
  `netstat -ano | grep :PORT` then `taskkill //PID <pid> //F`.
- Seed AFTER the model is constructed. `MLPProfile()` weight-init consumes the RNG, so seeding
  before it still drifts.
- Never let a bare expression sit in Streamlit code — magic renders its return value, which is how
  a stray `None` badge appeared in the UI.

## FIRST REPLY

Do not write code yet. Reply with:

1. Which feature you are starting (F2a unless you disagree) and why.
2. Your read on the Aug-30 time budget — can F2a and F8 land without hurting the demo? Say no if no.
3. Anything in this spec you think is wrong.
