

## E-CAL-01  2026-09-02  — uncertainty refitted against the shipped satellite model

**Status: IMPROVED, NOT CALIBRATED. Must be labelled as a limitation wherever sigma is shown.**

The previous `uncertainty_calibration.json` was INVALID: `calibrate_uncertainty.py:76` rebuilt the
model with `t_seq=ck["T_SEQ"]` instead of `built_t_seq`, producing a structurally different encoder
that `load_state_dict` accepts silently. Every scale in it was fitted on predictions the shipped
model does not make. It also targeted `tscast_stage1_tseq31.pt` — a 5-channel T_SEQ=31 checkpoint
that was never the shipped model (`is_shipped_model: false`). Preserved as
`uncertainty_calibration_INVALID_pre_built_tseq.json`, never to be applied.

Refitted against the canonical promoted artifact (tscast_stage1.pt, T_SEQ 11,
7 channels, `is_shipped_model: true`), method `coverage`,
fitted on 3423 TRAIN-window Argo profiles and evaluated on 908
TEST-window ones.

| | before | after | target |
|---|---|---|---|
| ±1σ coverage | 0.2735 | **0.6053** | 0.683 |
| ±2σ coverage | 0.4643 | **0.9650** | 0.954 |
| PIT uniform deviation | 0.1051 | **0.0709** | 0 |

### Read this honestly

**±2σ is now good. ±1σ is not.** 0.605 against a 0.683 target means the band is still too narrow:
roughly 6 floats in 10 land inside ±1σ where 7 should. The model remains **overconfident after
calibration**, and no product may describe this as "calibrated uncertainty" or show a confidence
percentage derived from it.

**The scales themselves are the finding.** To reach even this, sigma had to be multiplied by

    50 m 3.24 · 75 m 5.13 · 100 m 5.41 · 125 m 4.95 · 150 m 4.78 · 200 m 4.45 · 300 m 4.13

The raw head is **4-5x too narrow through the entire thermocline** — worse than the MC-dropout it
replaced was at its worst (1.6-3.5x). The uncertainty head is not merely imprecise there; it is
confidently wrong in exactly the depth range the reconstruction is hardest and users care most
about. That is a result about the model, not a tuning nuisance.

**Surface has n=20** — far too few profiles to fit a scale on. The 0 m entry should be treated as
unfitted regardless of what the file says.

Limitations: one seed, temperature only, and the scales are fitted on the train window and applied
to the test window, so they carry that period's error structure.
