# DECISIONS.md — Architecture Decision Records  (Owner: Unit A — Arjhun; seeded by B)

> Format per decision: DECISION / DATE / REASON / ALTERNATIVES / WHY REJECTED / CONSEQUENCES.
> Prevents future sessions from re-litigating settled choices.

## D-001 — Training truth = GLORYS12; validation = independent Argo
DATE 2026-08-25. REASON: complete gridded surface+subsurface fields buildable in 5 days; Argo gives an honest,
independent check. ALTERNATIVES: train directly on Argo. REJECTED: Argo too sparse in NIO for a 0.25° gridded demo.
CONSEQUENCES: clean train/validation separation; must download both via copernicusmarine + argopy.

## D-002 — Lead model = per-column MLP; baselines = climatology + LightGBM
DATE 2026-08-25. REASON: CPU-friendly, robust, beginner-safe, fits 5 days; MC-dropout gives honest uncertainty.
ALTERNATIVES: CNN/ConvLSTM/U-Net/Transformer. REJECTED for MVP: GPU + time + debugging risk. CONSEQUENCES: CNN etc.
deferred to Phase 2; a later model ships only if it beats the previous on the 2022 holdout.

## D-003 — Uncertainty = MC-dropout (LightGBM quantiles as backup)
DATE 2026-08-25. REASON: simplest defensible method; no fabricated confidence. ALTERNATIVES: deep ensembles,
heteroscedastic. REJECTED for MVP: cost/complexity. CONSEQUENCES: report model-uncertainty vs data-limitation vs
validation-error separately.

## D-004 — Deadline treated as a 5-day critical path (Aug 25→30)
DATE 2026-08-25. REASON: real inter-college gate is Aug 30. CONSEQUENCES: optional products off the critical path.

## D-005 — Team = 3 units; Mitun+Niru share one account/branch; Darshan owns pipeline+integration
DATE 2026-08-25. REASON: only 3 Claude accounts; strict single-owner files prevent merge conflicts. CONSEQUENCES:
overrides the generic "Darshan=UI" split; Niru is red-teamer within Unit C.

## D-006 — Tables use parquet (pyarrow) with CSV fallback
DATE 2026-08-25. REASON: pyarrow not yet installed; scaffold must run today. CONSEQUENCES: `utils.io` auto-detects;
fixtures ship as CSV until `pip install -r requirements.txt`.
