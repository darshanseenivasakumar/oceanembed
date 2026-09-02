

## E-SAT-01  2026-09-02  — the first SATELLITE-INPUT result (A7)

**Status: VALIDATED against independent Argo. This is the PS's actual requirement.**

Trained on `data/processed/daily_sat/v001/` — 388 days, inputs from OSTIA SST (K->degC),
DUACS altimetry, SMOS-blended SSS, COPERNICUS-GLOBCURRENT total surface currents, and the wind
that was always observational. GLORYS remains the TARGET, which the PS names. The bundle passed
44 provenance + data-lineage checks and a negative test in which GLORYS injected into each of the
five satellite channels was caught every time.

Config identical to the GLORYS-input leg in every respect — cnn3d, simple decoder, beta-NLL 0.5,
T_SEQ=11, 60k/12k, lr 1e-3, batch 256, seed 42, embargoed_v2, 5 targets embargoed. **Only the
input source differs.**

| | GLORYS-input (comparator) | **SATELLITE-input** | delta |
|---|---|---|---|
| Argo RMSE °C | 0.8789 | **0.9078** | **+0.0289** |
| bias °C | +0.1263 | **+0.1003** | -0.0259 |
| correlation | 0.8942 | 0.8812 | -0.0130 |
| skill 1-RMSE/RMSEclim | +0.2831 | **+0.2595** | -0.0236 |
| skill Murphy | +0.4860 | +0.4517 | -0.0344 |
| climatology RMSE °C | 1.2259 | 1.2259 | 0.0000 |
| n / profiles | 12829 / 962 | 12829 / 962 | 0 / 0 |

`rmse_climatology` identical to 4 dp and n identical — both legs scored on the same points.

**READ THIS AS: reconstruction from real satellite observations costs +0.0289 °C against a
reanalysis-fed comparator, and still beats climatology by +0.2595.** That is the answer to "how
much does reconstruction depend on the surface input source?", measured rather than asserted.
The satellite leg retains 92% of the comparator's skill.

**Why the satellite leg is expected to be worse, physically — not a model failure:**
satellite SSS floors at 30.78 psu while Unit B measured 6.43 psu at 22.50N 91.25E, the
Meghna/Ganges plume. The satellite input is blind to the Bay of Bengal's defining feature. Bias
actually IMPROVED (+0.1003 vs +0.1263), so this is a variance cost, not a systematic offset.

**Not yet done:** per-basin split of this gap (A12 has the masks), multi-seed (n=1 here), and
INCOIS LAS validation (data layer down; argopy used, deviation documented).

checkpoint: `artifacts/tscast_stage1_sat_7ch_s42.pt`  code_commit `a67feea`
