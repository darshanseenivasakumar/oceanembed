# The Bay's upside-down winter — barrier layer & temperature inversions

Owner: Unit B (Darshan). Branch `phase2-bob-inversion`. Started 2026-09-14. Definitions: D-020.
Pre-registration: E-INV-00. Literature: `docs/LITERATURE_MATRIX.md` §"Barrier layer & temperature inversion".

## In one paragraph
River water makes the northern Bay of Bengal's surface light and fresh. That fresh lid (the barrier
layer) stops winter cooling from mixing downward, so the surface gets colder than the water 20–80 m
below it: a temperature inversion. A model that has learned "warm surface ⇒ warm below" draws that
profile backwards. This feature (1) measures the inversion in the truth data, (2) measures whether
the shipped satellite-input model reproduces it on a winter it has never seen, (3) tries five cheap
fixes under a rule written down first, and (4) puts the map in the instrument with its skill number
and every caveat.

## Status
| Phase | What | State |
|---|---|---|
| 0 | literature section, novelty row, D-020, E-INV-00 | done 2026-09-14 |
| 1 | `derived/inversion.py`, `inversion_skill.py`, `tscast_nio/time_encoding.py` + tests; truth-side maps on the data already here | — |
| 2 | satellite bundle rebuilt here; winter 2024–25 bundles (satellite + GLORYS-input); Argo winter table | — |
| 3 | `winter_holdout_v1` scoring of the control → H1 verdict (E-INV-01) | — |
| 4 | fix ladder L1–L6, 3 seeds each → H2 verdict | — |
| 5 | promote-or-record, `app/ui/features/inversion.py`, records, PR | — |

## Units
| unit | file | depends on |
|---|---|---|
| inversion engine | `src/phase2/derived/inversion.py` | numpy; `physics/layers.py` wrapped, never edited |
| skill + decision rule | `src/phase2/derived/inversion_skill.py` | `derived/mhw_field.compare_detection` |
| day-of-year input | `src/phase2/tscast_nio/time_encoding.py` | — |
| winter data | `scripts/phase2/download_winter_holdout.py`, `build_winter_bundles.py` | existing downloaders and pipelines, given `--start/--end/--*-dir` |
| study | `scripts/phase2/run_inversion_study.py` → `artifacts/inversion_study.json` | `eval_argo`, `field.predict_field` on GPU |
| ladder | `scripts/phase2/run_inversion_ladder.py` | `train_stage1` flags (Unit A files; additive, default-off, `--tag`-guarded) |
| UI | `app/ui/features/inversion.py` | `app/ui/data.py`, `viz_explainer` |

## What this feature refuses to do
- Quote a winter number against the 0.9063 °C headline (different protocol, D-020 §3).
- Show a model-side barrier layer (needs salinity the satellite leg does not predict).
- Declare any leg better on fewer than three seeds.
- Cite an inversion threshold from a paper we have not read.
