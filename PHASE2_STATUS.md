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
| 4 | Calibrated uncertainty + OOD | Arjhun | `phase2-reliability` | **TESTED** | ☑ | ☐ | ☑ 40 | ☐ | **method tested, science UNVERIFIED — `argo_error_by_depth.json` absent (gitignored, Unit-B machine only)** |
| 5 | Physics (thermocline/MLD/OHC) | Arjhun | phase2/physics | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **no subsurface salinity -> OHC needs assumed density** |
| 6 | Event detection | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **no wind data -> no upwelling attribution; monthly -> no eddy tracking** |
| 7 | Subsurface heatwave | Arjhun | phase2/events | **BLOCKED** | ☐ | ☐ | ☐ | ☐ | **monthly sampling -> persistence uncomputable** |
| 8 | Validation Lab | Darshan | phase2/validation | NOT STARTED | ☐ | ☐ | ☐ | ☐ | Argo is 2022 only |
| 9 | Ocean Sentinel | Arjhun | phase2/sentinel | NOT STARTED | ☐ | ☐ | ☐ | ☐ | thresholds must be configurable |
| 10 | Observation Priority v2 | Darshan | phase2/observation-priority | NOT STARTED | ☐ | ☐ | ☐ | ☐ | v1 heuristic already exists; not novel (JTECH 2023) |


## F4 — detail (Arjhun, `phase2-reliability`)

Full write-up: `docs/phase2/f4-reliability.md`.

**Built.** `src/phase2/reliability/calibration.py` (variance/std scaling, Levi et al. 2022; ENCE)
and `ood.py` (Mahalanobis, Lee et al. 2018). 40 tests pass; full suite **182 passed, 10 skipped**.
Baseline diff vs `origin/phase2` is **empty** — `src/oceanembed/`, `app/`, `scripts/`,
`pyproject.toml`, baseline `tests/test_*.py` all untouched. `main` never checked out.

**Scientifically tested** — not shape tests:
- recovers a known 4x overconfidence factor to within 10%
- resolves depth-VARYING miscalibration (a single global factor would over-correct the surface)
- **ENCE improves out of sample**, on rows the factors were not fitted on
- reproduces the D-016 thermocline case: sigma 0.30 -> corrected lands on the measured 1.22 degC
- leaves already-calibrated uncertainty alone (alpha ~ 1)
- OOD flags a state that is inside every marginal range but violates the SST/SSH correlation —
  the property a per-feature z-score cannot have, and the whole reason for Mahalanobis
- OOD false-positive rate matches the chosen percentile (~1% at p99, measured 0.93% on held-out)

**NOT VALIDATED, and why.** `artifacts/argo_error_by_depth.json` is gitignored and lives only on
the machine that ran the real Argo evaluation. Every number F4 can currently produce comes from
synthetic artifacts (`provenance.json -> "synthetic"`). The method is exercised; the science is not.

### Two asks for Unit B
1. **Whitelist the error file.** ~15 numbers, and it is a *result* rather than raw data — results
   are the evidence. One line: `!/artifacts/argo_error_by_depth.json`.
2. **Persist per-sample residuals**, to unlock the rigorous path. The JSON stores *aggregate*
   per-depth RMSE, which supports only moment-matching — and moment-matching **cannot be held
   out**, so its factors are fitted on exactly the numbers they would be scored against.
   `is_validated` returns False for that path by design. Adding
   `[lat, lon, date, depth_idx, residual, sigma]` per matched profile to
   `scripts/eval_satellite_vs_argo.py` would let F4 report a genuine out-of-sample ENCE.
   Unit-B script, so: requested, not changed.

### Two scaffold notes
- **`tests/phase2/__init__.py` deleted.** It made pytest import tests as `phase2.test_*`, shadowing
  `src/phase2` so that `phase2.reliability` was unimportable. Latent until now only because
  `test_subsurface.py` imports just `oceanembed` and skips. Baseline `tests/` has no `__init__.py`
  anywhere; `main` has no `tests/phase2` at all, so this cannot reach it.
- **Branch naming.** `git checkout -b phase2/reliability` is impossible: `phase2` already exists as
  a branch and a git ref cannot be both a branch and a directory. Using **`phase2-reliability`**.
  `phase2/collocation` will hit the same wall.

### Held per instruction
F5 OHC, F6 upwelling, F7 persistence not started — audit section 4 gaps (no subsurface salinity,
no wind, monthly sampling) are still open pending Unit B's decision.

## Baseline protection
`main` @ `v1.0-demo-aug30` is frozen. 142 tests pass. No Phase-2 change may touch it.

## Blockers
1. §4 of the audit — download subsurface salinity + wind (~3 h), or formally de-scope F5 OHC-density,
   F6 upwelling attribution and F7 persistence.
2. Confirm the two-agent ownership split.
