# OceanEmbed — where we stand. Paste this into a fresh Claude session.

Everything below is measured, not estimated. Verify anything you doubt before using it.

---

I'm building **OceanEmbed** for Smart India Hackathon 2026, problem **SIH26066** (Ministry of Earth
Sciences). Help me with what I ask next — this is the background.

## The problem

Satellites see only the ocean **surface**. The interior is where cyclones get their fuel, where
marine heatwaves live, and where monsoon heat is stored. Argo floats measure the interior directly,
but ~2,455 floats across ~15 million km² of the North Indian Ocean is very sparse.

**We reconstruct subsurface temperature at 15 depths (0–1000 m) from surface satellite data**, at
0.25° resolution, over 5–30°N, 45–105°E.

## What works — the good news

**The headline, measured against 879 independent Argo floats that were never used in training:**

| | RMSE (°C) | skill vs climatology |
|---|---|---|
| **our model, satellite inputs** | **0.964** | **+0.387** |
| climatology baseline | 1.573 | — |

- **Skill is positive at all 15 depths**, from +0.225 to +0.501. We beat the baseline everywhere.
- Trained on real GLORYS reanalysis. Real Argo for validation. **Nothing synthetic anywhere.**
- Seeded and reproducible. Every number regenerates from a command.

**The strongest result.** We measured the GLORYS reanalysis *itself* against the same floats —
nobody in the project had done that. With bootstrapped confidence intervals, our model is
**statistically indistinguishable from the reanalysis at 8 of 14 testable depths, better at 1000 m,
and worse at 5.**

A reanalysis is a physics supercomputer model that ingests floats, ships and satellites. We use
**surface data only** and match it at most depths.

**What that means, and it's our best line:** at 100–150 m our error is inside the reanalysis's own
error against the same floats. **Our thermocline error is inherited from the training data, not
created by our model.** We've hit the ceiling of what we were taught.

## What's weak — say these out loud, don't hide them

1. **The mixed layer, 20–50 m, is genuinely our weak spot.** Not inherited — ours. We're 0.3–0.4 °C
   worse than the reanalysis there. It shows up on three independent measures: accuracy, skill, and
   uncertainty calibration. Naming it is what makes everything else credible.
2. **Our uncertainty estimate is not trustworthy as an absolute number.** MC-dropout is
   overconfident at *every* depth — measured 1.6× to 3.5× too narrow, worst at 20 m. We show
   measured error instead and say so on screen.
3. **Satellite data covers only 24 of our 48 months.** The satellite-driven result rests on half the
   record.
4. **Argo validation is 2022 only.** One year.
5. **Monthly data killed two features.** Subsurface heatwaves need persistence and eddies need
   tracking; neither is computable at monthly cadence. We closed them rather than fake them.
6. **LightGBM is not shown as a baseline.** It was never scored against Argo, so showing it would be
   a fabricated comparison. The app states the omission on screen.
7. **This is not a novel method.** AI reconstruction of subsurface temperature is published work.
   Any novelty claim is **system-level** — an integrated, North-Indian-Ocean-specific
   reconstruct → uncertainty → validate → prioritise tool — and only if it survives scrutiny.

## Where the build actually is

**Phase 1 — the demo. DONE and FROZEN.** `main` @ `5c41958`, tagged `v1.0.1-demo-aug30`, 142 tests
pass. This is what gets shown. **To rehearse you must `git checkout main` first.**

**Phase 2 — 5 of 10 features built, on separate branches:**

| done | not done |
|---|---|
| F1 collocation · F5 physics · F6 events · F8 validation lab | F2 OceanCube · F3 CNN · F9 Sentinel — never started |
| | F4 uncertainty — code exists, never validated on real data |
| | F7 heatwave — closed permanently, data can't support it |
| | F10 priority v2 — skipped deliberately, not novel |

**Known problem:** those features sit on five diverged branches and **no single branch has all of
them**. Merging is real work and can break things.

**We have decided to stop building.** New features don't change what a judge sees.

## The deadline

Today is **26 August 2026**. The screening gate is **30 August** — four days.

Still to do: the **PPT (not started)** and **two full demo rehearsals (not started)**. That's it.

## How to work with me

- Tell me when I'm wrong. Being agreed with is not useful this close to a deadline.
- Don't invent numbers. If something isn't measured, say so.
- Never touch `main` without asking — it's the frozen demo.
- Simple language. I'm a beginner, and my teammates are too.
