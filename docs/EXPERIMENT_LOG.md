

## E-CAL-02  2026-09-02  — E-CAL-01 was measured through the wrong bundle; refitted

**Status: E-CAL-01 IS RETRACTED. The "4-5x too narrow thermocline" finding was an artifact.**

`calibrate_uncertainty.py:64` called `D.load_daily()` with no argument, defaulting to
`data/processed/daily` -- the GLORYS bundle -- while the shipped model trains on
`data/processed/daily_sat/v001`. The identical defect `inference.py` had. So every per-depth sigma
scale in E-CAL-01 was fitted on the errors a satellite-trained model makes when fed reanalysis,
which are not the errors it makes.

| | E-CAL-01 (GLORYS-fed, WRONG) | refitted (satellite-fed) |
|---|---|---|
| ±1σ coverage after | 0.6053 | **0.6387** (target 0.683) |
| ±2σ coverage after | 0.9650 | **0.9119** (target 0.954) |
| scale at 50 m | 3.24 | **1.19** |
| scale at 75 m | 5.13 | **1.28** |
| scale at 100 m | 5.41 | **1.46** |
| scale at 150 m | 4.78 | **1.15** |
| scale at 300 m | 4.13 | **1.01** |

**The uncertainty head was never 4-5x miscalibrated. The diagnostic was.** Real scales span
0.89-1.46. I reported that miscalibration as "a result about the model, not a
tuning detail" and it was neither -- it was a bug in the measuring instrument.

### What is true now

Both bands run SLIGHTLY NARROW, not wildly so: ±2σ covers 91.2% where a Gaussian of that width
gives 95.4%, and ±1σ covers 63.9% against 68.3%. So the model remains mildly overconfident and
the ±2σ band must NOT be labelled "95%" -- the nominal is not the measured figure.

Note the direction reversed as well: under the wrong bundle ±2σ OVER-covered (0.965 > 0.954); it
now UNDER-covers (0.912 < 0.954). Every conclusion drawn from E-CAL-01 pointed the wrong way.

### UI corrected in the same commit

`tscast_page.py` and `ui_tables.py` carried the retracted figures in a caption, a docstring, a
chart title, a tooltip and a column label -- "±2σ (95%)" and "5.4x at 100 m". All now read the
measured values. The band label is "±2σ", never "95%".

**Superseded artifact kept:** `uncertainty_calibration_INVALID_glorys_fed.json`.
