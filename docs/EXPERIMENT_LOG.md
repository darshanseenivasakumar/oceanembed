

## E-ABL-01  2026-09-02  — A10, satellite-bundle feature ablations, 3 seeds

**Status: VALIDATED. One of three effects is real; two are not.**

Twelve runs on `data/processed/daily_sat/v001` — 4 legs x seeds 42/43/44. Identical bundle, split,
embargo (`embargoed_v2`, 5 targets), architecture, T_SEQ=11, 60k/12k, optimiser and schedule. Only
the seed varies within a leg, only the dropped channels between legs.

**`rmse_climatology` is 1.2258696057 in all twelve runs** — every leg scored on the same 962
profiles and 12,829 depth comparisons. That is what makes these deltas comparable at all.

| leg | ch | RMSE mean | sd | delta vs full | per-seed deltas | sign holds |
|---|---|---|---|---|---|---|
| full | 7 | 0.9070 | 0.0020 | (reference) | — | — |
| **noSSS** | 6 | 0.9315 | 0.0165 | **+0.0245** | +0.0047, +0.0375, +0.0314 | **YES 3/3** |
| noCUR | 5 | 0.9171 | 0.0192 | +0.0101 | -0.0072, +0.0080, +0.0297 | **NO — flips** |
| noWIND | 5 | 0.9110 | 0.0204 | +0.0041 | -0.0174, +0.0068, +0.0228 | **NO — flips** |

### What may be quoted

**SSS earns its place: +0.0245 °C when removed, sign held on all three seeds, twelve times the
0.0020 noise floor.** The model is genuinely using satellite salinity — notable given that same
product is blind to the Meghna/Ganges plume (floors at 30.78 psu vs the real 6.43).

### What may NOT be quoted

**Currents and wind both FLIP SIGN across seeds.** noCUR reads -0.0072, +0.0080, +0.0297; noWIND reads
-0.0174, +0.0068, +0.0228. At n=1 either could have been written up as a finding in whichever direction that
seed happened to fall — and `noCUR s42` (0.9005) and `noWIND s42` (0.8904) both came in BETTER than
full, which at one seed would have read as "dropping currents helps".

This **retires the old wind claim for good**. `EXPERIMENT_LOG` once recorded wind at −0.0149
(helps); it later flipped to +0.0111 on a single retrain. Now measured properly: **wind's effect is
not separable from seed noise on the satellite bundle at n=3.** Not "wind does not help" — *we
cannot tell*, which is a different and weaker statement, and the correct one.

### The finding neither the mean nor the delta shows

**Removing any channel destabilises training far more than it shifts the mean.** Full-leg seed
spread is sd 0.0020; every reduced leg scatters at
0.0165–0.0204,
eight to ten times higher. The 7-channel input is not merely more accurate, it is more
*reproducible*. Only a multi-seed design can see this, and it is arguably the strongest argument
in the ablation for keeping all seven.

**Limitations:** 3 seeds, one architecture, one bundle version, temperature only. Non-flipping is
not proof of no effect — a real effect below ~0.02 °C would not be resolvable here.

artifact: `artifacts/sat_ablation.json`
