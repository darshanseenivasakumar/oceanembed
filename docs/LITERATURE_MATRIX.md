# LITERATURE_MATRIX.md  (Owner: Unit C — Mitun+Niru)  [seeded by B from the paper corpus]

Relevant papers only. **Ignore** the 178 land-remote-sensing PDFs in `all research papers/ScienceDirect_articles_*`
(crops/glaciers/minerals — irrelevant). Abstracts of the four starred papers were read → tagged [VERIFIED]; extend the
rest by reading the PDFs.

| Paper | Year | Region | Inputs | Target | Depth | Res | Model | Physics | Uncertainty | Validation | Main result | Limitation / overlap with us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Meng et al., JGR Oceans** ⭐ | 2021 | global/basins | satellite only (SST/SSH/SSS) | T & S 3D | 0–2000 m (26) | **0.25°** | CNN-type DL | no | no | Argo | 3D T/S from satellite only, anomalies, geostrophic flow | ~= our exact deliverable already; can't claim 0.25° 3D as novel |
| **TS-Cast (Chae et al.)** ⭐ | 2026 | NW Pacific | SST/SSS/ADT, 31-day seq | T & S profile | ≤500 m focus | 1/8° | climatology-prior DNN | prior | **MC/uncertainty** | moorings + Argo | RMSE<1°C, honest skill-limit analysis | uncertainty+prior+rigorous-validation already done |
| **FFPG-net (Zhao et al.)** ⭐ | 2025 | South China Sea | SST/SSS/SSH + currents | T & S | ≤1200 m | point | ResNet+attention | **EOF vertical modes** | no | in-situ | physics guidance + currents help | physics-guidance already done |
| **DORS (Su et al.)** ⭐ | 2022 | global | multisource + Argo | T | 0–2000 m | grid | **ConvLSTM** | no | no | Argo/EN4 | beats LightGBM; long product | ConvLSTM/spatiotemporal already done |
| Wang et al., Mathematics | 2021 | W Pacific | SST/SSS/SSH/SSW | T | 0–2000 m | monthly | MLP | no | no | test set | RMSE 0.55°C; beats RF/MLR/XGB | MLP baseline is standard |
| Chen et al., Remote Sens. | 2022 | — | + SST gradient | T profile | >200 m gain | grid | NN | fronts | no | Argo | SST-gradient input helps below 200 m | feature idea to reuse |
| NeSPReSO (Miranda et al.) | 2025 | Gulf of Mexico | satellite | synthetic T/S profiles | — | — | DL | — | — | — | synthetic profiles for assimilation | assimilation angle taken |

TODO (C): fill blank cells by reading each PDF; add exact RMSE numbers with page refs; tag each [VERIFIED] once read.
