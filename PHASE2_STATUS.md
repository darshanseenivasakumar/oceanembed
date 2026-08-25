# PHASE2_STATUS.md

Status vocabulary: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `TESTED` · `VALIDATED` · `DEMO READY`

**A feature is never marked VALIDATED because unit tests pass.** TESTED means the code does what the
code intends. VALIDATED means the *science* was checked against an independent source or a
documented physical expectation.

| # | Feature | Owner | Branch | Status | Backend | Frontend | Tests | Sci. validation | Known limitation |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Repository audit | Darshan | phase2 | **IMPLEMENTED** | n/a | n/a | n/a | n/a | — |
| 1 | Collocation engine | Darshan | phase2/collocation | NOT STARTED | ☐ | ☐ | ☐ | ☐ | satellite covers 24 of 48 dates |
| 2 | OceanCube 3-D | Darshan | phase2/ocean-cube | NOT STARTED | ☐ | ☐ | ☐ | ☐ | 24% of cells < 1000 m deep |
| 3 | Spatial CNN | Arjhun | phase2/spatial-ai | NOT STARTED | ☐ | ☐ | ☐ | ☐ | only 48 timesteps to train on |
| 4 | Calibrated uncertainty + OOD | Arjhun | phase2/reliability | NOT STARTED | ☐ | ☐ | ☐ | ☐ | D-016: MC-dropout overconfident |
| 5 | Physics (thermocline/MLD/OHC) | Arjhun | phase2/physics | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **no subsurface salinity -> OHC needs assumed density** |
| 6 | Event detection | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **no wind data -> no upwelling attribution; monthly -> no eddy tracking** |
| 7 | Subsurface heatwave | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **monthly sampling -> persistence uncomputable** |
| 8 | Validation Lab | Darshan | phase2/validation | NOT STARTED | ☐ | ☐ | ☐ | ☐ | Argo is 2022 only |
| 9 | Ocean Sentinel | Arjhun | phase2/sentinel | NOT STARTED | ☐ | ☐ | ☐ | ☐ | thresholds must be configurable |
| 10 | Observation Priority v2 | Darshan | phase2/observation-priority | NOT STARTED | ☐ | ☐ | ☐ | ☐ | v1 heuristic already exists; not novel (JTECH 2023) |

## Baseline protection
`main` @ `v1.0-demo-aug30` is frozen. 142 tests pass. No Phase-2 change may touch it.

## Blockers
1. §4 of the audit — download subsurface salinity + wind (~3 h), or formally de-scope F5 OHC-density,
   F6 upwelling attribution and F7 persistence.
2. Confirm the two-agent ownership split.
