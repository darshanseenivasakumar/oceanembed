# JURY_NOTES — the SIH26066 presentation pack

Nineteen standalone PDFs. One to set up the problem, seventeen for the seventeen built
features (one per port, 8501–8517), one to close with limits and viva prep.

Every number in these notes is transcribed from `PROJECT_RECORD.md`, `docs/`, an artifact
on disk, or a commit message. Nothing is estimated. Claims that were never verified carry
`[INFERRED]` or `[UNKNOWN]` in the text, per `CLAUDE.md`.

## The pack

| # | File | Port | What it covers |
|---|---|---|---|
| 01 | `01_Problem_Statement_and_Solution.pdf` | — | What SIH26066 asks, what we produce, the impact, who it is for |
| 02 | `02_Feature_01_Phase1_App.pdf` | 8501 | The first working system, frozen read-only |
| 03 | `03_Feature_02_Collocation.pdf` | 8502 | One point, every source, with measured offsets |
| 04 | `04_Feature_03_Validation_Lab.pdf` | 8503 | Separating inherited error from ours |
| 05 | `05_Feature_04_Cube_3D.pdf` | 8504 | The reconstruction as a rotatable volume |
| 06 | `06_Feature_05_Physics.pdf` | 8505 | Mixed layer, barrier layer, thermocline, heat content |
| 07 | `07_Feature_06_Events.pdf` | 8506 | Eddies, fronts, upwelling |
| 08 | `08_Feature_07_TSCast_v2.pdf` | 8507 | **The deliverable itself** |
| 09 | `09_Feature_08_Argo_Overlay.pdf` | 8508 | The model checked against a real float, live |
| 10 | `10_Feature_09_Cyclone_Heat.pdf` | 8509 | TCHP / D26 / OHC — the national-relevance feature |
| 11 | `11_Feature_10_Transect.pdf` | 8510 | Depth-vs-distance cross-sections |
| 12 | `12_Feature_11_Export_API.pdf` | 8511 | NetCDF export and the HTTP service |
| 13 | `13_Feature_12_Click_Map.pdf` | 8512 | Click any of 24,000 cells |
| 14 | `14_Feature_13_Uncertainty.pdf` | 8513 | Where the model does not know |
| 15 | `15_Feature_14_Acoustics.pdf` | 8514 | Sound speed, sonic layer, SOFAR |
| 16 | `16_Feature_15_Cloud_Dropout.pdf` | 8515 | Monsoon cloud robustness — and what it actually found |
| 17 | `17_Feature_16_Priority_v2.pdf` | 8516 | Where another observation is worth most |
| 18 | `18_Feature_17_Cyclone_Case_Study.pdf` | 8517 | The cold wake nobody taught it |
| 19 | `19_Conclusion_Limitations_Viva.pdf` | — | Conclusion, flaws, missing novelty, ~30 viva Q&A |

## Every feature note has the same nine sections

1. What it is, in plain words · 2. What you see on screen · 3. How to run it, step by step ·
4. Why the PS needs it · 5. The measured numbers · 6. Impact and who it is for ·
7. Say this to the jury · 8. Questions they will ask · 9. The honest limit

A presenter who has rehearsed one note has rehearsed all seventeen.

## Suggested ten-minute demo order

8507 (the model) → 8512 (let them click) → 8508 (check it against a float) →
8503 (show the worst numbers) → 8509 (why it matters to India) → 8517 (the cold wake).

## Rebuilding

```bash
cd JURY_NOTES/_build && ../../.venv/Scripts/python.exe build_all.py
```

Needs `reportlab` and `pymupdf` in the project venv, and the Segoe UI / Consolas / Georgia
system fonts. Content lives in `note_01_problem.py`, `features_01_06.py`,
`features_07_12.py`, `features_13_17.py` and `note_19_conclusion.py`; layout lives in
`engine.py` and `common.py`.
