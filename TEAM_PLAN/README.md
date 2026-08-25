# OceanEmbed — Team Plan (SIH26066)

This folder tells each teammate **exactly what to build, in what order, and how**, so that three different
Claude accounts can work in parallel and **merge with zero conflict**.

## Read this first (everyone)

- **Project in one line:** Reconstruct subsurface ocean **temperature** (multiple depths) from **surface** ocean
  variables at **0.25°** over the **North Indian Ocean (5–30°N, 45–105°E)**. Then add uncertainty, anomaly, and an
  "observation-priority" (where-to-measure-next) layer on top.
- **Deadline:** working demo on **Aug 30** (inter-college gate). This is a **5-day sprint** (Aug 25→29 build, Aug 30 demo).
- **We win on the SYSTEM, not the reconstruction.** Reconstructing temperature with AI is already published many times
  (Meng 2021, TS-Cast 2026, FFPG-net 2025, DORS 2022). Our honest edge = North-Indian-Ocean focus + the decision layer.
  **Never claim we invented AI subsurface reconstruction.**

## The 3 units (Mitun + Niru share ONE Claude account = ONE unit)

| Unit | Person(s) | Account | File |
|---|---|---|---|
| **A** | Arjhun | Claude **Max** | [UNIT_A_ARJHUN.md](UNIT_A_ARJHUN.md) — the Model Brain |
| **B** | Darshan | Claude Pro | [UNIT_B_DARSHAN.md](UNIT_B_DARSHAN.md) — Backbone + Integration |
| **C** | Mitun + Niru | Claude Pro (shared) | [UNIT_C_MITUN_NIRU.md](UNIT_C_MITUN_NIRU.md) — Science + Validation + UI panels |

Also read: **[SHARED_BRIEF.md](SHARED_BRIEF.md)** — the rules everyone's Claude must follow. Paste it into your Claude
session *before* your own unit file.

## The 5 golden rules that prevent merge conflicts

1. **You edit ONLY your own files.** Every file has one owner (listed in your unit file). Never touch another unit's files.
2. **Shapes and filenames are frozen** in `docs/DATA_CONTRACT.md` and `docs/MODEL_SPEC.md`. Never invent them. If you need
   a change, edit the contract first and tell the group in your WhatsApp/Discord.
3. **Talk through files, not code.** You hand off work by writing a named file into `artifacts/` (e.g. `X_train.npy`).
   Others read your file. Nobody imports another unit's half-finished code.
4. **Day 1 uses fake "fixture" files** so everyone can start immediately. Real data swaps in later with the same shapes,
   so no rework.
5. **Order of work:** Darshan (B) builds the skeleton first → then Arjhun (A) and Mitun+Niru (C) work in parallel →
   Darshan integrates everything at the end.

## Order to start
1. **Darshan** does Day-1 scaffold first (creates the repo + contracts + fixtures) and pushes to GitHub.
2. Everyone else pulls, then starts their own Day-1 tasks against the fixtures.

## What "done" means (for every task, everyone)
Code exists **+** it was actually run **+** it ran on real (or fixture) data **+** you looked at the output **+** it's
committed **+** you updated `docs/HANDOFF.md`. "It should work" is NOT done. Never paste fake numbers.
