# CLAUDE.md — OceanEmbed operating constitution

Every Claude session on this repo reads this file **first**, then `docs/HANDOFF.md`, then the doc for its task.
Keep this file short; deep detail lives in `docs/`.

## What this project is
Reconstruct subsurface ocean **temperature** at 15 depths (0–1000 m) from surface variables (SST, SSS, SSH, u, v) at
**0.25°** over the **North Indian Ocean (5–30°N, 45–105°E)**, plus uncertainty + anomaly + observation-priority.
Full scope: `docs/MASTER_SPEC.md`. Team + ownership: `TEAM_PLAN/`.

## Evidence tags (use on every claim)
- **[VERIFIED]** — you actually ran the code / inspected the data / read the source. Only these are facts.
- **[INFERRED]** — a reasonable guess, not yet tested. Must be labelled.
- **[UNKNOWN]** — not verified. Say so; never dress it up as fact.

## The 15 "never assume" rules
Never claim (1) code works unless executed, (2) a dataset has a variable unless inspected, (3) a model improves unless
the comparison ran. Never fabricate (4) metrics, (5) uncertainty, (6) citations, (7) novelty without a literature check.
(8) Never invent missing requirements. Never assume (9) tensor dims, (10) units, (11) coordinate order, (12) temporal
alignment, (13) missing-value handling, (14) a valid train/test split. (15) If uncertain, say it's unverified.

## Engineering loop (every task)
UNDERSTAND → INSPECT repo → read the relevant doc → PLAN → IMPLEMENT smallest working version → run TESTS →
run a real-data smoke test → inspect output → DOCUMENT (update `docs/HANDOFF.md`) → git COMMIT. No request→giant-impl jumps.

## Definition of DONE
Code exists **+** tests pass **+** ran on real/fixture data **+** output inspected **+** reproducible (seed + config saved)
**+** docs updated **+** committed. For ML also: training done, validation done, metrics + checkpoint + seed + config
logged to `docs/EXPERIMENT_LOG.md`. "It should work" is NOT done.

## File ownership (never edit another unit's files)
- **Unit A (Arjhun/Max):** `src/oceanembed/models/`, `train/`, `inference/uncertainty.py`,
  `products/observation_priority.py`, `docs/{ARCHITECTURE,MODEL_SPEC,DECISIONS}.md`, `tests/test_model.py`.
- **Unit B (Darshan):** scaffold, `config.py`, `config/`, `utils/`, `data/`, `features/`, `inference/predict.py`,
  `app/streamlit_app.py`, `docs/{MASTER_SPEC,DATA_CONTRACT,DEMO_SPEC}.md`, `tests/test_shapes.py`, `CLAUDE.md`.
- **Unit C (Mitun+Niru/shared):** `climatology.py`, `validation/`, `products/anomaly.py`, `app/panels/`,
  `docs/{VALIDATION_PROTOCOL,LITERATURE_MATRIX,NOVELTY_MATRIX,EXPERIMENT_LOG}.md`, `tests/test_metrics.py`.
- `docs/HANDOFF.md` — appended by everyone.

## Contract-first rule
Shapes/filenames/signatures are frozen in `docs/DATA_CONTRACT.md` and `docs/MODEL_SPEC.md`, and constants live in
`src/oceanembed/config.py`. Import them — never hardcode. To change a contract: edit the contract file first, then tell
the team, then code.

## Real-data-only rule
No fabricated metrics, uncertainty, or citations. Cached demo results are allowed **only if the real model generated
them**, and the UI must label them CACHED vs LIVE.

## Libraries
Before coding against any library (copernicusmarine, argopy, xarray, streamlit, torch, lightgbm), fetch its **current**
docs via Context7 — training data may be stale.

## After every task
Report the exact files you changed and paste the real command output. Update `docs/HANDOFF.md`. Commit.
