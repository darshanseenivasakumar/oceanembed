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

## D-012 — LightGBM baseline: one booster per depth, quantiles in a separate artifact
DATE 2026-08-25. OWNER Unit A. REASON: LightGBM is single-output and the depths have genuinely different error
scales (surface ~2 degC spread vs ~0.3 degC at 500 m), so per-depth boosters let each fit its own scale.
Trees are scale-invariant, so they train on X as supplied (z-scored or raw) and predict REAL degC directly — no
normalization round-trip and no dependency on norm_stats.json. ALTERNATIVE: one multi-output model — REJECTED,
LightGBM does not support it natively. ARTIFACTS: `lgbm_model.pkl` stays exactly what DATA_CONTRACT says, a list
of 11 boosters. The q10/q90 quantile boosters go in a SEPARATE `lgbm_quantiles.pkl` (`{"q10":[...11],
"q90":[...11]}`) rather than changing the shape of the contracted file. **Unit B: please add
`lgbm_quantiles.pkl` to DATA_CONTRACT.md — it is a new artifact and that file is yours.**
Quantile spread is converted to a sigma-equivalent by dividing by 2.5631 (= 2 x 1.2816, the Gaussian q90-q10
width) so it is directly comparable with the MC-dropout std from `inference/uncertainty.py`. Independently-fitted
quantiles can cross; that warns and clamps to zero spread rather than producing a negative standard deviation.
Hyperparameters are deliberately NOT tuned — tuning against synthetic data optimizes for the wrong target.

## D-013 — FINDING: on the current fixtures, MLP vs LightGBM is an UNINFORMATIVE comparison
DATE 2026-08-25. RAISED BY Unit A. MEASURED on a 100-row held-out slice of the fixtures:
climatology RMSE 1.466 | LightGBM 0.222 (skill +0.849) | MLP 0.221 (skill +0.849). The MLP "wins" by 0.2%,
which is noise. REASON — and this is the point: `make_fixtures.py` adds `N(0, 0.2)` to the target, so the
irreducible noise floor is 0.20 degC. Both models score ~0.22, i.e. **both have saturated the noise floor**, and
the comparison cannot discriminate between them BY CONSTRUCTION. CONSEQUENCE: do NOT conclude "the MLP has no
advantage over trees" or "ship either one" from this run. The model-selection decision (TEAM_PLAN Unit A Day 3:
"if MLP can't beat LightGBM, say so and we ship LightGBM") can only be made on REAL GLORYS data, where the signal
is not a 1-D exponential decay and there is genuine structure for a nonlinear model to exploit. Re-run the
comparison after `prepare_dataset.py --real` and record the result here.
