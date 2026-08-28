# tscast_data_model.md — what the daily pipeline PRODUCES and the model CONSUMES

**Owner:** Unit A (Arjhun). **Branch:** `phase2-tscast-nio`.
**Status:** CONTRACT — frozen on first use. To change it, edit this file first, post to
`AGENT_SYNC.md`, then change code. Never the other way round.

All grid constants are **imported** from `src/oceanembed/config.py`. Nothing here is hardcoded:
`LAT` (100), `LON` (240), `DEPTHS` (15), `REGION.step` = 0.25 deg.

---

## 1. Why this differs from the frozen Phase-1 bundle

Phase 1 stored **48 monthly** snapshots (2019-01-15 .. 2022-12-15). TS-Cast's mechanism is a
**31-day daily sequence**, so monthly data reduces its temporal encoder to a no-op. This contract
is daily. It is written so the same code runs on both:

> **`T_SEQ` and `P` are configuration parameters, not constants.**
> `T_SEQ=1` runs the entire stack on the existing monthly archive — real shapes, real training,
> real validation — before any daily byte lands. `T_SEQ=31` is a config change, not a rewrite.

This is what lets the model be built and tested while the ~16 h download runs.

## 2. On-disk daily bundle — `data/processed/daily/YYYY.npz`

One file per calendar year. Written by the Phase-2 pipeline; read by the sampler in section 4.

| array | shape | dtype | meaning |
|---|---|---|---|
| `times` | `(T,)` | `datetime64[D]` | daily, ascending, **no duplicates** |
| `surface` | `(T, 100, 240, 7)` | `float32` | the 7 input channels, order frozen below |
| `channels` | `(7,)` | `<U4` | `["sst","sss","ssh","u","v","wu","wv"]` |
| `units` | `(7,)` | `<U8` | `["degC","psu","m","m s-1","m s-1","m s-1","m s-1"]` |
| `temp` | `(T, 100, 240, 15)` | `float32` | GLORYS temperature target. NaN below the sea floor |
| `salinity` | `(T, 100, 240, 15)` | `float32` | stage-2 target. Written **now** so stage 2 is not a data migration |
| `land_mask` | `(100, 240)` | `bool` | `True` = land. Carried through unchanged from the Phase-1 bundle |
| `valid_mask` | `(100, 240, 15)` | `bool` | `True` = water at that depth (bathymetry). ~24% of ocean cells are shallower than 1000 m |
| `missing_days` | `(M,)` | `datetime64[D]` | days where a source was absent |
| `provenance` | `()` | `<U` | JSON: dataset ids, download dates, code commit |

### Rules that are not negotiable

- **Channel order is frozen.** Readers index by position. A reordered write is a silent science
  bug of exactly the kind that produced 52 degC from a 28 degC input in Phase 1.
- **A missing day is recorded in `missing_days`, never interpolated and never dropped silently.**
  A gap the model cannot see is a gap the model will learn through.
- **`valid_mask` travels with the data.** Below-seafloor cells are NaN in `temp`, and any
  aggregation must mask before it means anything. The Persian Gulf at ~20 m must never produce a
  1000 m temperature.
- `sst` is degrees **Celsius**, not Kelvin. `ssh` is metres. Checked at write time, not assumed.

## 3. Climatology prior — `artifacts/clim_daily.npz`

| array | shape | meaning |
|---|---|---|
| `clim_t` | `(12, 100, 240, 15)` | monthly temperature climatology |
| `clim_s` | `(12, 100, 240, 15)` | monthly salinity climatology (stage 2) |
| `clim_ssh` | `(12, 100, 240)` | monthly SSH climatology, for the anomaly vector in section 4 |
| `train_years` | `(Y,)` | the years this was computed from |

> **This is the leakage point.** The climatology MUST be computed from **training years only**.
> A climatology that has seen the test window makes every downstream RMSE, skill and calibration
> number quietly invalid, and nothing in the test suite would catch it. `train_years` is stored so
> the check is mechanical, not a matter of memory.

## 4. One model sample, at `(t, i_lat, i_lon)`

| tensor | shape | notes |
|---|---|---|
| `x_patch` | `(7, T_SEQ, P, P)` | the 7 channels over a `T_SEQ`-day window centred on `t`, on a `P x P` patch centred on the cell |
| `x_geo` | `(3, 1, P, P)` | X/Y/Z position encoding, paper eq. 1 (below) |
| `x_ssh_anom` | `(1, T_SEQ, 12)` | the `T_SEQ`-day SSH sequence minus the 12 monthly climatological SSH values at that cell |
| `clim_prior` | `(12, 15, C_out)` | the 12 monthly climatology profiles at that cell. `C_out` = 1 at stage 1 (T), 2 at stage 2 (T,S) |
| `y_t` | `(15,)` | target temperature |
| `y_valid` | `(15,)` | `bool`, depths above the sea floor. Loss is masked by this |

**Defaults:** `T_SEQ = 31` (the paper's +/-15 d), `P = 17`.

`P = 17` at 0.25 deg is a **+/-2.0 deg** patch. The paper justifies its window as a 2 deg radius
chosen "to contain an entire mesoscale eddy (typically 100-300 km)". We match that **physical
extent**, not their cell count — their 15 cells at 1/8 deg spans only ~1.9 deg total, which does
not equal the 2 deg radius the text claims. We follow the stated physics and record the
discrepancy. `[VERIFIED]` from the PDF text; the inconsistency is theirs, not ours.

**Position encoding, paper eq. 1** (Sinha & Abernathey 2021), phi = latitude, lambda = longitude:

```
X = sin(phi)
Y = sin(lambda) * cos(phi)
Z = -cos(lambda) * cos(phi)
```

### Edge handling

A patch centred near the domain edge runs off the grid. Cells outside the domain are filled with
the channel mean and flagged; **they are never wrapped around**, because 45 deg E and 105 deg E are
opposite sides of the basin, not neighbours. Land inside a patch keeps its `land_mask` and is
filled the same way.

## 5. Known deviations from TS-Cast — stated, not hidden

| TS-Cast | Ours | Consequence |
|---|---|---|
| 6 channels: SST, SSS, ADT **+ their 3 error fields** | 7 channels, **all signal, no error fields** | the encoder has no per-pixel "how much do I trust this" input. Probe CMEMS for error fields during the download |
| ADT anomaly vs **steric dynamic height** (integrated to 700 dbar) | SSH minus monthly climatological SSH | a cheaper proxy for the same steric signal. Documented, not equivalent |
| 128 levels, 10-700 dbar | **15 levels, 0-1000 m** (frozen, PS requirement 11) | the decoder works on a 64-level internal grid and resamples to the 15 contract depths at the output head |
| targets are ~155k in-situ Argo/CTD profiles | target is **GLORYS reanalysis** on the grid (PS requirement 15) | our error is bounded by GLORYS' own error vs Argo, already measured in `artifacts/glorys_vs_argo.json` |
| no wind input | **wind u, v** included (PS requirement 8) | an addition, not a deviation |

## 6. Consumers

`src/phase2/tscast_nio/` — dataset, models, train. Output side is
`docs/phase2/tscast_output_schema.md`.
