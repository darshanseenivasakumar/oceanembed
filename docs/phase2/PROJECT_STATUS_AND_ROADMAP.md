# OceanEmbed — full status and roadmap. Paste this into any fresh Claude session.

Everything below is either measured, or clearly marked as not yet done. This file answers two
questions: **what is happening right now**, and **what comes after**.

---

## 1. THE PROJECT, IN ONE PARAGRAPH

**OceanEmbed** reconstructs subsurface ocean temperature — down to 1000 m — from surface satellite
data alone, for the North Indian Ocean. Smart India Hackathon 2026, problem **SIH26066**, Ministry
of Earth Sciences. Team: Darshan, Arjhun, Mitun, Niru. Two Claude agents build it: Darshan's and
Arjhun's, on separate laptops, coordinating through git and `docs/phase2/AGENT_SYNC.md`.

## 2. TWO THINGS EXIST RIGHT NOW — do not confuse them

**A. The old build (`main`) — finished, frozen, working.**
Tag `v1.0.2-demo-aug30`. 142 tests pass. A simple AI model (MLP) trained on monthly data.
Headline: RMSE 0.964 °C, skill +0.387 vs climatology, checked against 879 real Argo floats.
**This still works today and can be demoed any time.** Nobody is allowed to edit `main` while
building anything else — it is the safety net.

**B. The new build ("v2" / TS-Cast-NIO) — in progress, on branch `phase2-tscast-nio`.**
A full rebuild using the architecture of a published paper, **TS-Cast**, adapted for our region,
built to satisfy every requirement the problem statement actually asks for — which the old build
only partly does.

## 3. WHY WE ARE REBUILDING — the honest gap

We checked the old build line by line against the problem statement. It meets about half of what
is actually asked:

| Missing from the old build | Status in v2 |
|---|---|
| Daily data (we had monthly) | in progress — see §5 |
| Wind as a model input | in progress — see §5 |
| A satellite "embedding" via deep learning (the PS's core ask) | **built and chosen — see §4** |
| Correlation and Bias as reported metrics | **built** |
| Independent validation against INCOIS's named Argo product | not started |

## 4. WHAT IS BUILT IN v2 RIGHT NOW — verified

- **355 tests pass.** `main` confirmed untouched.
- **Both data contracts** (what the pipeline produces, what the model returns) — written and agreed.
- **Metrics module**: RMSE, correlation, bias — the two previously-missing PS requirements.
- **The architecture bake-off** — four AI designs were actually trained and compared on real data,
  not chosen by guesswork:

  | Model | RMSE vs 897 real Argo floats |
  |---|---|
  | **cnn3d — WINNER** | **0.9891 °C** |
  | ViT (transformer) | 1.0071 °C |
  | CNN + attention | 1.0198 °C |
  | plain MLP (old-style, control) | 1.0566 °C |

  **A judgement call worth knowing about:** the original instruction was to rank by "smallest gap
  between training and test score." Ranked that way, the weakest model (the plain MLP) would have
  won — a model too simple to learn anything cannot overfit, so it trivially has the smallest gap.
  That would have produced the false conclusion "no embedding is needed," while being measurably
  worse on real floats. The ranking was corrected to use real Argo accuracy instead. Both numbers
  are recorded, not hidden.

- **The TS-Cast model itself**: the winning CNN encoder, a "FiLM" mechanism that lets the satellite
  data adjust a climatology baseline rather than guessing from nothing, and a per-depth uncertainty
  output (replacing the old build's uncertainty method, which was measured as 1.6–3.5× too
  confident).
- **Stage-1 training is running now** (temperature + uncertainty only; salinity comes later).

## 5. WHAT IS GENUINELY NOT DONE — stated plainly, not softened

- **Daily data**: your laptop has finished downloading it — **GLORYS 388/388 days**, satellite data
  still downloading (184+ files so far). Arjhun's laptop has **no login set up and no download
  running at all** — his "daily" numbers do not exist yet. He needs your data handed to him, or his
  own login and ~16 hours.
- **Wind as a model input**: not started. Blocked by the same daily-data gap.
- **The "31-day history" version of the model** (looking at a month of context, not just one day,
  which is what the paper actually does): needs a GPU. On a normal laptop CPU this takes 2–5 days
  per attempt; on a free Google Colab GPU it is fast. His code already has the switch for this
  (`--device cuda`) — it just needs a GPU to run on.
- **Two real bugs were found and fixed before they caused wrong numbers:**
  1. A location-lookup bug in the new pipeline was wrong on 75% of real float comparisons (~28 km
     off). **Checked — this does not affect the old build's F1 feature**, which uses a different,
     correct method.
  2. The training code was saving the *last* training round instead of the *best* one — the model
     had already started getting worse before training stopped, and the worst version was nearly
     shipped. Fixed: now keeps the best checkpoint and stops early.
- **Salinity + the physics density constraint** (stage 2 of the model): not started, waiting on
  stage 1 finishing training first.
- **The UI page for v2**: not started.
- **INCOIS's specific named Argo product**: never verified as available; only generic Argo data has
  been used so far.

## 6. FEATURES ALREADY BUILT ON OLD BRANCHES — kept, not deleted

These exist, are tested, and are **not being thrown away** — they get reconnected to the new v2
model once it exists, instead of the old one:

| Feature | What it does | Proof it is real |
|---|---|---|
| F1 Collocation | Click any point, see what every data source says there | 171 tests |
| F5 Physics | Finds the mixed layer and the thermocline | Matches known physics in 526,066 real cells |
| F6 Events | Detects ocean eddies | Found the real "Great Whirl" seasonal pattern without being told to look for it |
| F8 Validation Lab | Shows honestly where the model is right and wrong | Built on real Argo comparisons |
| F2 OceanCube | 3-D view of the reconstructed ocean | Has a working page |

## 7. THINGS DECIDED NOT TO BUILD — and why, stated honestly

- **F7 Subsurface heatwave** — impossible with monthly-or-slower data; a heatwave needs to be
  tracked over days, which the data cannot support. Closed, not faked.
- **F9 Ocean Sentinel** — never started, no current plan to.
- **F10 Observation Priority v2** — a basic version already exists; a fancier one was judged not
  worth building because the underlying idea is already published research elsewhere, not because
  it is broken.

None of these were ever built, so none of them were deleted — there was nothing to delete.

## 8. WHO OWNS WHAT RIGHT NOW

Darshan's Claude ran out of most of its weekly budget, so the split changed: **Arjhun's Claude is
building everything** — data pipeline, model, metrics, UI. Darshan's Claude tests, checks, and
plans. All new work happens on `phase2-tscast-nio`; `main` stays frozen throughout.

## 9. THE IMMEDIATE NEXT STEPS, IN ORDER

1. **Hand Arjhun the daily data** (or get his own CMEMS login running) — this unblocks daily
   resolution and wind, the two biggest remaining gaps.
2. **Get GPU access** (free Google Colab is enough) for the 31-day-history version of the model.
3. **Finish stage-1 training**, validate it honestly against real, independent Argo floats.
4. **Stage 2**: add salinity and the physics-based density constraint from the TS-Cast paper.
5. **Build the v2 UI page** — every output explained in plain words next to the number, real
   benchmarks shown clearly, and the model's prediction shown beside the real Argo reading it is
   being checked against, live, on screen.
6. **Reconnect F1/F2/F5/F6/F8** to read from the new v2 model instead of the old one.
7. Re-test everything with `python scripts/phase2/accept.py` before any of it is called finished.

## 10. FUTURE SCOPE — beyond the immediate next steps

- **Extend the daily window** beyond the current one-year pilot, once the pipeline is proven, to
  give the model more to learn from.
- **Verify and add INCOIS's specific named Argo product** alongside the general Argo data already
  used, so validation matches exactly what the problem statement names.
- **Revisit F9 (Sentinel) and a proper F10** only if time allows after everything above is solid —
  neither is required by the problem statement.
- **A live demo mode** that pulls the freshest available real data (Argo is available almost to the
  present day) so the reconstruction can be shown for "yesterday," not just historical dates.
- **Forecasting forward** (e.g. into 2027) framed honestly as a forecast with no ground truth yet —
  never presented as a validated result, since nothing can be validated against data that does not
  exist yet.

## 11. THE RULES THAT DO NOT CHANGE, NO MATTER WHAT PHASE THIS IS IN

- `main` is never edited, checked out for changes, merged into, or pushed to, by anyone, for any
  reason, without stopping to ask first.
- No metric, uncertainty, or result is ever stated unless it was actually measured on real data.
  Code that only runs on fake/synthetic data proves the code executes — nothing about whether it is
  scientifically correct.
- Every weakness found gets stated plainly, not hidden — this is what makes every number in this
  project defensible under questioning.
