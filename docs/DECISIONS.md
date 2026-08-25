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

## D-007 — Normalization stats live INSIDE the model checkpoint
DATE 2026-08-25. OWNER Unit A. REASON: `predict_mlp` must return real °C, so it needs target mean/std — but
`artifacts/norm_stats.json` is Unit B's file and does not exist yet, and Unit A must not create it. Registering
`feat_mean/feat_std/targ_mean/targ_std` as buffers on `MLPProfile` puts them in `state_dict()`, so `mlp_model.pt`
is self-describing and needs no companion file. ALTERNATIVES: (a) have A write `norm_stats.json` — REJECTED,
violates file ownership; (b) require callers to pass stats into `predict_mlp` — REJECTED, changes a frozen
signature that B and C already code against; (c) save a dict of numpy arrays next to the state_dict — REJECTED,
`torch.load` defaults to `weights_only=True` since PyTorch 2.6 and numpy arrays are not allowed under it, so it
would force the unsafe `weights_only=False`. CONSEQUENCES: `train_mlp.py` prefers B's `norm_stats.json` when it
appears and falls back to train-split stats otherwise, logging which path it took; no signature changes for B/C.

## D-008 — OPEN QUESTION for Unit B: DEPTHS is 11 levels to 500 m; the problem statement names 15 to 1000 m
DATE 2026-08-25. RAISED BY Unit A. The SIH26066 statement lists standard depths
`0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000` (15 levels). `config.DEPTHS` currently has 11, stopping at
500 m — missing 5, 125, 700 and 1000 m. This sets the MLP output width, so changing it later means a retrain and a
contract change for every unit. Cost to change now is ~zero (four more depth levels from the same GLORYS download;
output layer 11→15). NOT ACTIONED — `config.py` is Unit B's file and the constants are frozen by group decision.
DECISION REQUIRED FROM: Darshan + team. CONSEQUENCES IF DEFERRED: either a retrain later, or we ship a demo that
visibly does not match the depth list judges are scoring against.
