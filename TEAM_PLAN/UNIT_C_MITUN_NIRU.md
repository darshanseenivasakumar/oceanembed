# UNIT C — MITUN + NIRU — Science, Validation & UI Panels

> You two **share ONE Claude account and ONE git branch** — work as one unit. Split the humans' effort like this:
> **Mitun** → climatology, anomaly, UI panels. **Niru** → metrics, Argo validation, and **red-team** (trying to break
> our own results). But everything goes through the single shared account/branch. Read `SHARED_BRIEF.md` first.

## Your charter
Everything that turns a raw prediction into trustworthy science and a visible product: the climatology baseline, error
metrics, independent Argo validation, the anomaly product, and the four Streamlit panels the judge actually sees. Plus
you are the project's honesty check.

## Files you OWN (only you edit these)
```
src/oceanembed/climatology.py
src/oceanembed/validation/metrics.py        src/oceanembed/validation/validate_argo.py
src/oceanembed/products/anomaly.py
app/panels/profile_panel.py  map_panel.py  priority_panel.py  validation_panel.py
docs/VALIDATION_PROTOCOL.md   docs/LITERATURE_MATRIX.md   docs/NOVELTY_MATRIX.md   docs/EXPERIMENT_LOG.md
tests/test_metrics.py
```
**Do NOT touch:** `models/`, `train/`, `inference/`, `data/`, `features/`, `app/streamlit_app.py`, `config/`,
`products/observation_priority.py`. You consume those via files/functions, you don't edit them.

## What you consume / produce
Consume: `y_train.npy`, `meta_train.parquet`, `argo_test.parquet` (from Darshan); the model predictions (via Darshan's
`reconstruct()` or A's model). Produce: `artifacts/climatology.npy (12,100,240,11)`, metrics tables, and the panels.
Signatures you expose:
```python
def build_climatology(y_train, meta_train) -> np.ndarray        # (12,100,240,11)
def climatology_predict(meta) -> np.ndarray                     # (N,11) baseline
def compute_metrics(y_true, y_pred) -> dict   # {rmse, mae, r2, rmse_by_depth[11], skill_vs_clim}
def anomaly(pred_grid, climatology, month) -> np.ndarray        # (100,240,11)
# each app/panels/*.py exposes:  def render(recon_output: dict, argo_df=None) -> None
```

## Your phases

### Day 1 (Aug 25) — after Darshan's fixtures land
1. Write `docs/VALIDATION_PROTOCOL.md`: split = train 2019–21 / test 2022 by TIME; Argo is a separate independent
   source; **never random-split adjacent cells/days**. List the 6 validation levels (sanity → unit tests → baseline →
   holdout → Argo → event).
2. `validation/metrics.py` (`compute_metrics`) + `climatology.py` skeleton, tested on `artifacts/sample_*`.
3. Start `docs/LITERATURE_MATRIX.md` — one row per relevant paper in "all research papers/" (Meng 2021, TS-Cast 2026,
   FFPG-net 2025, DORS 2022, Wang 2021, Chen 2022, NeSPReSO). Columns: region/inputs/target/depth/resolution/model/
   physics/uncertainty/validation/result/limitation/overlap-with-us. **Ignore the 178 land-remote-sensing PDFs** in the
   `ScienceDirect_articles_*` folders — they are irrelevant (crops, glaciers, minerals).

### Day 2 (Aug 26) — climatology baseline + anomaly
1. `build_climatology` → real `climatology.npy` from Darshan's train data; `climatology_predict` = the mandatory baseline.
2. `products/anomaly.py`: `anomaly = reconstruction − climatology(month, cell, depth)`, z-scored per depth (threshold =
   k·σ, document k). Write `docs/NOVELTY_MATRIX.md` (ALREADY DONE / PARTIAL / UNDEREXPLORED / POTENTIAL / NOT novel).

### Day 3 (Aug 27) — independent validation + start panels
1. `validation/validate_argo.py`: load `argo_test.parquet`, get predictions at Argo points, run `compute_metrics`
   per depth. Report real numbers — including where the model is **weak at depth**. That honesty is a strength.
2. Start the panels against the **fixture recon dict** (its shape is frozen, so panels work before the real model exists).

### Day 4 (Aug 28) — finish the four panels
- `profile_panel.render` — vertical temperature profile + uncertainty band + nearest-Argo overlay + per-depth error.
- `map_panel.render` — NIO map of SST / anomaly grid.
- `priority_panel.render` — observation-priority heatmap + top-K "measure here" pins.
- `validation_panel.render` — metrics table + depth-error chart + skill-vs-climatology.
Each is a `render(recon_output, argo_df)` function Darshan's shell calls. Keep copy honest ("regions where more
observations may add value" — never "the AI tells MoES where to deploy Argo").

### Day 5 (Aug 29) — polish + RED TEAM (Niru leads)
Act as a hostile reviewer trying to **break** our own project. Hunt for: data leakage, unit/coordinate errors, temporal
leakage, overfitting, weak baselines, misleading charts, fake confidence, unsupported novelty claims. Write findings in
`docs/HANDOFF.md`. The reviewer's job is to find problems, not to praise. Fix what you find before the demo.

## Copy-paste block for your Claude (after SHARED_BRIEF)
```
We are UNIT C (Mitun + Niru, ONE shared Claude Pro account, ONE branch). We own: src/oceanembed/climatology.py,
src/oceanembed/validation/*, src/oceanembed/products/anomaly.py, app/panels/*, docs/VALIDATION_PROTOCOL.md,
docs/LITERATURE_MATRIX.md, docs/NOVELTY_MATRIX.md, docs/EXPERIMENT_LOG.md, tests/test_metrics.py. We must NOT touch
models/, train/, inference/, data/, features/, app/streamlit_app.py, config/, products/observation_priority.py. We
develop against artifacts/sample_*.npy and the frozen recon-output dict until real data/model land. Deliverables:
climatology baseline + metrics + independent Argo validation + anomaly product + the four Streamlit panels
(render(recon_output, argo_df)). Niru also red-teams the whole project before the demo. Real numbers only — never fake.
```
