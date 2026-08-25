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
| 5 | Physics (thermocline/MLD/OHC) | Arjhun | `phase2-physics` | **TESTED** | ☑ | ☐ | ☑ 31 | ☐ | **UNBLOCKED by Unit B's subsurface extraction — real rho(S,T), no density assumption. Science unverified: subsurface.npz absent here, ran on synthetic** |
| 6 | Event detection | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **no wind data -> no upwelling attribution; monthly -> no eddy tracking** |
| 7 | Subsurface heatwave | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **monthly sampling -> persistence uncomputable** |
| 8 | Validation Lab | Darshan | phase2/validation | NOT STARTED | ☐ | ☐ | ☐ | ☐ | Argo is 2022 only |
| 9 | Ocean Sentinel | Arjhun | phase2/sentinel | NOT STARTED | ☐ | ☐ | ☐ | ☐ | thresholds must be configurable |
| 10 | Observation Priority v2 | Darshan | phase2/observation-priority | NOT STARTED | ☐ | ☐ | ☐ | ☐ | v1 heuristic already exists; not novel (JTECH 2023) |


## F5 — detail (Arjhun, `phase2-physics`)

Full write-up: `docs/phase2/f5-physics.md`.

**Unblocked by Unit B.** The audit called OHC blocked on missing subsurface salinity; he showed the
cause was wrong — GLORYS always carried `so` at 36 levels, Phase 1 just took index 0. So density is
real rho(S, theta) and the constant-density caveat is gone rather than documented.

**Built.** `src/phase2/physics/seawater.py` (one-atmosphere EOS-80), `layers.py` (MLD, ILD, barrier
layer, thermocline), `ohc.py`. 31 tests pass.

**EOS coefficients verified before building on them** — 15 hand-entered constants are how a
plausible-but-wrong number enters a pipeline. All four published UNESCO check values agree to
< 1e-3 kg/m3, including the classic rho(35, 25) = 1023.343.

**The scientific point, and it is the strongest thing in F5.** MLD uses the DENSITY criterion
(de Boyer Montegut et al. 2004, 0.03 kg/m3 from 10 m), not temperature. The two disagree wherever
salinity sets the stratification, and their difference IS the barrier layer. Unit B measured
minimum salinity **6.43 psu at 22.50N, 91.25E** (Meghna/Ganges). So a temperature-only MLD would be
systematically TOO DEEP in exactly the region our priority map ranks first (17.75-19.25N,
85.75-93.75E) and in exactly the process our impact story rests on — cyclone intensification, which
barrier layers are a recognised control on. A test measures that error at >= 50 m on a realistic
plume profile.

**NOT VALIDATED.** `subsurface.npz` is gitignored and absent here, so it was regenerated from
`synthetic_glorys.nc`; provenance reads `synthetic`.

One grid-run number looked like a failure and was not — worth recording because the checking is the
point. "Thermocline below MLD in only 11.6% of cells" is a property of the SYNTHETIC data:
`make_synthetic_glorys.py` builds temperature as `exp(-z/250)` from the surface, so there is no
mixed layer and the steepest gradient sits at the top by construction. Verified by printing one
profile rather than assuming either way. Salinity spans 0.28 psu across the column, so no barrier
layer exists to find and the constant-density error is correspondingly tiny (0.028%). All three
should change qualitatively on real GLORYS — that is the validation.

**Unit B's sanity test caught the synthetic data, exactly as designed.** With my locally
regenerated `subsurface.npz` in place, `test_salinity_generally_increases_with_depth_in_the_bay_of_bengal` FAILS: 34.60 psu at the surface vs 34.58 at depth at 18N/88E — noise, where the
real Bay of Bengal has a fresh cap over saltier water. His test rejected data with the right
shape, dtype, units and plausible magnitudes but no ocean structure. That is the Phase-1
failure mode, caught by a scientific test rather than a shape test. It fails only locally
(the file is gitignored and his test skips when absent). **No code was changed in response —
adjusting a sanity test to accommodate synthetic data would be exactly backwards.**

### >>> ASK DARSHAN (3): a copy of `data/processed/subsurface.npz`
Or the raw `glorys_*.nc`. Then F5 produces real numbers and the barrier-layer claim above becomes
measured rather than argued. Same shape as asks (1) and (2): the code is ready, the data is on
your machine only.

### Scaffold bug reproduced independently
`tests/phase2/__init__.py` had to be deleted again on this branch — it came back with
`origin/phase2` and broke `phase2.physics` imports exactly as it broke `phase2.reliability`. That is
two independent reproductions. It will hit your next branch too.

## Baseline protection
`main` @ `v1.0-demo-aug30` is frozen. 142 tests pass. No Phase-2 change may touch it.

## Blockers
1. §4 of the audit — download subsurface salinity + wind (~3 h), or formally de-scope F5 OHC-density,
   F6 upwelling attribution and F7 persistence.
2. Confirm the two-agent ownership split.
