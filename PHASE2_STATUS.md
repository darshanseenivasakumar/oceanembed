# PHASE2_STATUS.md

Status vocabulary: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `TESTED` · `VALIDATED` · `DEMO READY`

**A feature is never marked VALIDATED because unit tests pass.** TESTED means the code does what the
code intends. VALIDATED means the *science* was checked against an independent source or a
documented physical expectation.

| # | Feature | Owner | Branch | Status | Backend | Frontend | Tests | Sci. validation | Known limitation |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Repository audit | Darshan | phase2 | **IMPLEMENTED** | n/a | n/a | n/a | n/a | — |
| 1 | Collocation engine | Darshan | phase2-collocation | **VALIDATED** | ☑ | ☑ | ☑ 29 | ☑ | satellite covers 24 of 48 dates; monthly grids force a 7-day median Argo offset |
| 2 | OceanCube 3-D | Darshan | phase2/ocean-cube | NOT STARTED | ☐ | ☐ | ☐ | ☐ | 24% of cells < 1000 m deep |
| 3 | Spatial CNN | Arjhun | phase2/spatial-ai | NOT STARTED | ☐ | ☐ | ☐ | ☐ | only 48 timesteps to train on |
| 4 | Calibrated uncertainty + OOD | Arjhun | phase2/reliability | NOT STARTED | ☐ | ☐ | ☐ | ☐ | D-016: MC-dropout overconfident |
| 5 | Physics (thermocline/MLD/OHC) | Arjhun | phase2-physics | NOT STARTED | ☐ | ☐ | ☐ | ☐ | UNBLOCKED: subsurface salinity extracted, real density available |
| 6 | Event detection | Arjhun | phase2-events | NOT STARTED | ☐ | ☐ | ☐ | ☐ | UNBLOCKED for upwelling (wind stress downloaded); eddy TRACKING still impossible at monthly cadence |
| 7 | Subsurface heatwave | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **monthly sampling -> persistence uncomputable** |
| 8 | Validation Lab | Darshan | phase2/validation | NOT STARTED | ☐ | ☐ | ☐ | ☐ | Argo is 2022 only |
| 9 | Ocean Sentinel | Arjhun | phase2/sentinel | NOT STARTED | ☐ | ☐ | ☐ | ☐ | thresholds must be configurable |
| 10 | Observation Priority v2 | Darshan | phase2/observation-priority | NOT STARTED | ☐ | ☐ | ☐ | ☐ | v1 heuristic already exists; not novel (JTECH 2023) |

## F1 validation evidence

Marked VALIDATED on 2026-08-26. What justifies it, so nobody has to take the tick on trust:

- **Physical expectations** checked by `python scripts/phase2/accept.py` on real data: an exact grid
  hit reports 0.00 km offset; the profile returns 15 levels and cools 27.5 -> 9.0 C with depth;
  inland 15N 75E is REJECTED and says why (`LAND_IN_GLORYS`).
- **Against an independent source**: the same collocation logic drove
  `scripts/phase2/glorys_vs_argo.py` across 2,455 real Argo profiles, reproducing the known
  physical structure of the basin (reanalysis error peaking at the thermocline, near-zero in the
  deep ocean) rather than noise. Argo is never used in training.
- **UI matches the engine** to four decimals (SST 27.4946/26.9589, SSS 36.8145/36.1656, Argo
  53 km / +5 d / 14 levels), so the page is not recomputing or reformatting anything.

Not claimed: F1 has not been validated for satellite-driven queries on the 24 dates lacking
satellite coverage, and the 7-day median Argo offset is a limit of monthly grids, not a bug.

## Baseline protection
`main` @ `v1.0-demo-aug30` is frozen. 142 tests pass. No Phase-2 change may touch it.

## Blockers
1. §4 of the audit — download subsurface salinity + wind (~3 h), or formally de-scope F5 OHC-density,
   F6 upwelling attribution and F7 persistence.
2. Confirm the two-agent ownership split.
