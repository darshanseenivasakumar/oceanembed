# tscast_output_schema.md — what the model RETURNS and the UI SHOWS

**Owner:** Unit A (Arjhun). **Branch:** `phase2-tscast-nio`.
**Status:** CONTRACT. Stage-2 fields were present from day one valued `None`, so adding salinity
and density was a fill-in, **not a schema migration** — which is how it actually landed.

**AMENDED 2026-08-31 (stage 2 shipped).** Two keys were ADDED, `sigma_s` and `sigma_rho`. The
schema already carried the log-variances, but every consumer wants the readable spread, and
`sigma_t` had set that precedent — leaving stage 2 to square-root its own error bars in the UI
would have put a computation in the one place this project forbids one. Additive only: no existing
key changed name, type or meaning.

**Three rules govern the stage-2 values.**
1. `salinity`, `density`, `sigma_s` and `sigma_rho` are `None` wherever `valid[k]` is False. Below
   the sea floor there is no water, so there is no salinity there either — a number would be a
   fabrication, not a rounding artefact. The log-variances are reported at every depth because
   they are diagnostics, exactly as `log_var_t` already was.
2. **Density is COMPUTED, never predicted.** `density = EOS-80(salinity, temperature)` on the
   model's own outputs, matching TS-Cast section 2.3.4 ("the network does not directly output
   density"). `sigma_rho` IS predicted, independently, because the paper states T/S error
   covariance is non-negligible and propagating the two variances analytically would understate it.
3. `log_var_rho` is already in physical units (kg m-3): eq. 5 is evaluated on density directly, so
   it is NOT rescaled by any normalisation constant. `log_var_t` and `log_var_s` ARE rescaled, from
   z-units into degC and psu. Getting this backwards is invisible downstream.

Depths are always the 15 in `config.DEPTHS`, in that order. Never a subset, never reordered.

---

## 1. The prediction record

One record = one reconstructed profile at one (lat, lon, date).

```python
{
  # ---- stage 1: built now -------------------------------------------------
  "temperature":  [15] float,     # degC
  "log_var_t":    [15] float,     # predicted log error variance, the network's raw head
  "sigma_t":      [15] float,     # exp(0.5 * log_var_t), degC. THIS is the error bar shown
  "valid":        [15] bool,      # False where the sea floor is above this depth
  "seafloor_depth_m": float,

  # ---- stage 2: None from a stage-1 checkpoint, populated by a stage-2 one -----
  "salinity":     None,           # -> [15] float|None, psu.  None where `valid` is False
  "log_var_s":    None,           # -> [15] float, every depth (a diagnostic, like log_var_t)
  "sigma_s":      None,           # -> [15] float|None, psu     = sqrt(exp(log_var_s))
  "density":      None,           # -> [15] float|None, kg m-3, EOS-80 on the PREDICTED (T,S)
  "log_var_rho":  None,           # -> [15] float, every depth
  "sigma_rho":    None,           # -> [15] float|None, kg m-3  = sqrt(exp(log_var_rho))

  # ---- required on every record, no exceptions ---------------------------
  "reasons":      [15] str,       # see section 2
  "argo_check":   {...} | None,   # see section 3
  "forecast":     bool,           # see section 4
  "provenance":   {...},          # see section 5
}
```

`sigma_t` is the number the UI shows. `log_var_t` is kept because it is what the loss operates on
and what a calibration audit needs; a UI that shows a log variance to a judge has failed.

## 2. `reasons` — every value explains itself, in place

**Non-negotiable.** A confidence or quality label carries its one-line reason **where the number
appears**, inside the model output — never in a separate report file the UI has to go and find.

One string per depth, plain language, generated from measured quantities:

```
"1.4 degC error bar: mixed layer, where this model is measurably weakest"
"0.3 degC error bar: below 500 m the ocean varies little and the model tracks it closely"
"no value: sea floor is at 30 m here, shallower than this level"
```

A reason is **never** a restatement of the number ("sigma is 1.4"). It says *why*. If code cannot
produce a real reason for a value, that is a bug to fix, not a field to leave blank.

## 3. `argo_check` — the ground-truth check travels with the prediction

**Non-negotiable.** Every panel shows the prediction, the nearest independent Argo reading, and the
difference. Never a number without its ground-truth check beside it. So the check is part of the
record, not something the UI computes on its own:

```python
"argo_check": {
  "argo_temperature": [15] float | None,   # None per-depth where the float did not sample
  "difference":       [15] float | None,   # model - argo, signed
  "profile_id":       str,
  "distance_km":      float,
  "days_offset":      int,
  "quality":          "HIGH" | "MEDIUM" | "LOW" | "REJECT",
  "quality_reason":   str,     # e.g. "12 km and 2 days away - close in both"
  "source":           "argopy" | "incois_las",
}
```

`argo_check` is `None` **only** when no float is within the collocation window. That case shows as
"no independent float within range", never as an empty panel and never as a silent zero.

Collocation reuses `src/phase2/data/collocation.py` (F1, VALIDATED). We do not write a second
matcher — two matchers that can disagree is the D-014 failure repeating.

## 4. `forecast` — 2027 output is never dressed up as a result

`forecast: True` means the target date is beyond the last date with ground truth. Verified limits:
**GLORYS to 2026-06-23**, **raw Argo to 2026-08-24**.

When `forecast` is `True`:
- `argo_check` is `None` by definition, and the reason string says so.
- The UI labels it **FORECAST**, never "validated", never "accuracy".
- No RMSE, correlation, bias or skill number may be attached to it. There is nothing to score
  against.

This applies to every feature built later, not only the baseline.

## 5. `provenance`

```python
"provenance": {
  "model": "tscast-nio-stage1",
  "checkpoint_sha256": str,
  "seed": int,
  "T_SEQ": int, "P": int,          # which config actually produced this
  "encoder": str,                  # the bake-off winner, by name
  "input_source": "glorys" | "satellite",
  "input_date": "YYYY-MM-DD",
  "clim_train_years": [int],       # proves the prior did not see the test window
  "code_commit": str,
}
```

`clim_train_years` is in here deliberately: it makes the section-3 leakage rule of the data model
auditable from any single output record.

## 6. Aggregate metrics record

Written by the metrics module, consumed by the UI benchmark tiles. Per depth **and** overall:

```python
{
  "rmse": [15] float,          # degC                      PS req 12
  "correlation": [15] float,   # Pearson r vs truth        PS req 13
  "bias": [15] float,          # mean(model - truth), signed. PS req 14
  "skill_vs_climatology": [15] float,   # 1 - mse_model/mse_clim
  "rmse_climatology": [15] float,       # shown BESIDE skill, always
  "n": [15] int,                        # sample count per depth
  "reference": "argo" | "glorys",
  "window": {"start": "...", "end": "..."},
}
```

Two rules learned from the Phase-1 validation lab:

- **`bias` here is the PS metric** (mean signed model-minus-truth). It is *not*
  `artifacts/satellite_bias.json`, which is a calibration correction. Conflating them would be a
  fabricated metric.
- **`rmse_climatology` is shown next to `skill_vs_climatology`, always.** Skill is lowest at 1000 m
  because the deep ocean barely varies, not because the model is bad there - 1000 m is our *best*
  absolute RMSE. Skill without absolute RMSE beside it misleads.
