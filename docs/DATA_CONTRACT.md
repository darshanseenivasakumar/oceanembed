# DATA_CONTRACT.md  (Owner: Unit B — Darshan)

Frozen shapes, filenames, units, and conventions. **Nothing in code may infer these implicitly.** Constants are also in
`src/oceanembed/config.py` — import them, don't retype them.

## Frozen constants
```python
LAT      = arange(5.0, 30.0, 0.25)   # 100 values, float32
LON      = arange(45.0, 105.0, 0.25) # 240 values, float32
DEPTHS   = [0,10,20,30,50,75,100,150,200,300,500]   # meters, positive-down, 11 levels
FEATURES = [sst, sss, ssh, u, v, sin_lat, cos_lat, sin_lon, cos_lon, sin_doy, cos_doy]  # 11, THIS order
SPLIT    = train {2019,2020,2021} | test {2022}   # by TIME, never random
SEED     = 42
```

## Datasets
### GLORYS12V1 — training truth  `[status: to download; conventions to VERIFY before freezing]`
- Source: CMEMS (Copernicus Marine) via `copernicusmarine` toolbox (free account). Product id: fill after download.
- Variables → our names: `thetao`→ temperature target (all depths) & `sst`(=thetao@0m); `so`→`sss`; `zos`→`ssh`; `uo`→`u`; `vo`→`v`.
- Units [INFERRED, verify]: thetao °C, so PSS-78 (psu), zos m, uo/vo m/s. Native ~1/12° → **regrid to 0.25°**. Daily (weekly subsample allowed).
- Missing = land NaN → masked via `land_mask.npy`. Normalize: z-score with **train-years stats only**.
- **VERIFY on first file:** latitude ascending?, longitude 0–360 or −180–180?, depth sign, exact units, NaN pattern.
  Record findings here with a `[VERIFIED]` tag before anyone freezes preprocessing.

### Argo — independent validation only  `[status: to download]`
- Source: Argo GDAC via `argopy`. Region NIO, year 2022. Interpolate each profile to `DEPTHS` (record method).

### (Phase 2) Satellite L4: OSTIA SST, CMEMS SSS, DUACS SLA — not needed for Aug 30.

## Per-variable table (fill EXPECTED RANGE after inspecting a real file → becomes assertion bounds)
| name | type | unit | expected range | shape | source | preprocessing |
|---|---|---|---|---|---|---|
| sst | float32 | °C | ~[transfer after inspect] | (100,240)/day | GLORYS thetao@0m | regrid+mask+zscore |
| sss | float32 | psu | | (100,240)/day | GLORYS so@0m | regrid+mask+zscore |
| ssh | float32 | m | | (100,240)/day | GLORYS zos | regrid+mask+zscore |
| u,v | float32 | m/s | | (100,240)/day | GLORYS uo,vo@0m | regrid+mask+zscore |
| temp(target) | float32 | °C | | (100,240,11) | GLORYS thetao@DEPTHS | regrid+mask |

## Shared `artifacts/` files (the drop-box — communicate via these, not via code)
| File | Producer | Shape / schema |
|---|---|---|
| `sample_X.npy`,`sample_y.npy`,`sample_meta.{parquet\|csv}` | B (done) | fixtures N=500, real shapes |
| `X_train.npy`,`X_test.npy` | B | float32 `(N,11)` FEATURES order |
| `y_train.npy`,`y_test.npy` | B | float32 `(N,11)` temp at DEPTHS |
| `meta_train.{parquet\|csv}`,`meta_test.*` | B | row-aligned: `[lat,lon,date,month,cell_id]` |
| `norm_stats.json` | B | `{feat_mean[11],feat_std[11],targ_mean[11],targ_std[11]}` |
| `land_mask.npy` | B | bool `(100,240)` True=land |
| `argo_test.{parquet\|csv}` | B | `[lat,lon,date,depth_idx(0..10),temp]` |
| `mlp_model.pt` | A | state_dict for MLPProfile |
| `lgbm_model.pkl` | A | list of 11 boosters |
| `climatology.npy` | C | `(12,100,240,11)` = [month,lat,lon,depth] |

**Table format note:** parquet when `pyarrow` is installed, else CSV — use `utils.io.save_table/load_table` (auto-detect).
Fixtures currently ship as **CSV** because pyarrow isn't installed yet; `pip install -r requirements.txt` switches to parquet.

## Pipeline notes [VERIFIED on synthetic data 2026-08-25]
- `scripts/prepare_dataset.py` runs synthetic-GLORYS → `preprocess.run()` → `build_samples.run()` and writes the full
  artifact set. Real data drops in with no code change (same shapes). Synthetic path exists so A/C aren't blocked on CMEMS.
- **Depth-0 handling:** GLORYS' shallowest level (~0.49 m) is *below* our `DEPTHS[0]=0 m`, so `preprocess` extrapolates the
  depth axis (0 m ≈ surface). Confirmed necessary — without it every row is NaN-dropped.
- X is stored **z-scored** (train-only stats); y is stored in **real °C**; `norm_stats.json` carries feat+targ mean/std so
  the model normalizes/denormalizes and inference can normalize raw inputs.
- **TODO [real data]:** GLORYS `dataset_id` is [INFERRED] — confirm with `copernicusmarine describe`; then inspect one
  real file and record here (with [VERIFIED]) the latitude order, longitude convention (0–360 vs −180–180), depth sign, and units.
