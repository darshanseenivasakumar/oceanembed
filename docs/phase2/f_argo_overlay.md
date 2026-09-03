# Feature — Live Argo Overlay ("trust the float")

A derived product on the **frozen** TS-Cast-NIO model. Pick a point; the page runs the same frozen
inference the dashboard uses and overlays the predicted profile (with its calibrated ±2σ band) on a
real, independent Argo float from nearby, showing the per-depth error live.

- Module: `src/phase2/validation/argo_overlay.py`
- Page: `app/phase2/validate_page.py` (`streamlit run … --server.port 8508`)
- Tests: `tests/phase2/test_argo_overlay.py` (13, all offline — no bundle, no network)

## Design note (for the report appendix)

**Prediction path.** `predict_at` is a thin wrapper over `TSCastPredictor.reconstruct` — the *same*
frozen inference path the dashboard uses, so the overlay can never diverge from the shipped model.
No second model-load path exists. The predictor is dependency-injected so tests use a fake and never
touch the checkpoint or the satellite bundle.

**Float source & QC policy.** Floats come from F1's validated `CollocationEngine`, matched against
the held-out `argo_daily_period` table — the same 962 independent profiles used for validation,
never used in training. QC is inherited from that table's construction (it is the validated set),
not re-derived here. Matching is **offline**: no live argopy call, so the overlay is fast and cannot
fail on a network hiccup during a demo. `reconstruct` already attaches the single nearest float; this
feature adds only a top-k picker and an RMSE/bias summary on top.

**Matching / ranking rule.** Candidates within ±1.0° and ±5 days are ranked **lexicographically by
(distance_km, |offset_days|)** — distance dominates, time breaks ties, then (lat, lon, date) makes
the order fully deterministic. This is deliberately *not* a weighted distance+time score: there is no
defensible kilometres-per-day exchange rate, and inventing one would be a hidden assumption. The
lexicographic rule reproduces the engine's own "nearest in space within the time window" choice for
the top result and only adds a stable ordering for the rest.

**Depth handling — no interpolation.** The offline Argo table is pre-binned to the project's 15
standard depths, so the float profile and the model prediction already share one depth axis. There is
therefore **no raw-pressure→depth interpolation to do**. A depth is scored only where *both* the
prediction and the float are finite; the comparison never extrapolates past the float's deepest
sampled level, and never invents a point where the float has no data. RMSE/bias are computed over
that overlap only.

**Uncertainty shown.** The band is the model's **calibrated ±2σ** (`sigma_t × 2`) — consistent with
the project's rule to display 2σ only, never a 1σ band or a confidence percentage.

**Honest empty state.** If no independent float is within the window, the page says so and draws
nothing — never a fabricated profile.

**Runs where the bundle is.** The pure logic is unit-tested on any machine. The live page needs
`data/processed/daily_sat/v001` (the satellite bundle), so it runs on the training box; it shows a
clear message rather than blanking if the bundle is absent.

## Frozen-safety

Additive, new-files-only: nothing modifies the checkpoint, the bundle, `dataset.py`, `inference.py`,
or the split. `freeze.py --check` is unaffected (verify on the box that carries the bundle).
