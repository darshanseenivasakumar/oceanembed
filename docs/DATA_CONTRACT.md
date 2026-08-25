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
| `X_train.npy`,`X_test.npy` | B | float32 `(N,11)` FEATURES order, **RAW units** (D-009) |
| `y_train.npy`,`y_test.npy` | B | float32 `(N,11)` temp at DEPTHS |
| `meta_train.{parquet\|csv}`,`meta_test.*` | B | row-aligned: `[lat,lon,date,month,cell_id]` |
| `norm_stats.json` | B | `{feat_mean[11],feat_std[11],targ_mean[11],targ_std[11]}` |
| `land_mask.npy` | B | bool `(100,240)` True=land |
| `argo_test.{parquet\|csv}` | B | `[lat,lon,date,depth_idx(0..10),temp]` |
| `mlp_model.pt` | A | state_dict for MLPProfile |
| `lgbm_model.pkl` | A | list of 11 boosters |
| `climatology.npy` | C | `(12,100,240,11)` = [month,lat,lon,depth] |
| `provenance.json` | B | `{source: "synthetic"\|"real-glorys", built, x_units, n_train, n_test}` (D-018) |
| `lgbm_quantiles.pkl` | A | `{"q10":[...11], "q90":[...11]}` boosters (D-012) |

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

## REAL data findings [VERIFIED 2026-08-25 by execution]

### GLORYS12 — dataset id CONFIRMED
`copernicusmarine.describe(contains=['GLOBAL_MULTIYEAR_PHY_001_030'])` (works WITHOUT login) lists:
- **`cmems_mod_glo_phy_my_0.083deg_P1D-m`** ← GLORYS12V1 daily means, what we use
- also `..._P1M-m` (monthly), `..._0.083deg-climatology_P1M-m`, `..._static`
The `subset` **download itself still requires a free CMEMS account** (`copernicusmarine login`). NOT yet downloaded.

### Argo — REAL data downloaded ✅
`artifacts/argo_test.parquet` — **24,328 measurements from ~2,453 real profiles**, NIO, all 12 months of 2022.
- lat 5.00–25.53 °N, lon 45.58–91.45 °E → **100 % inside the frozen region**
- temp 9.35–32.32 °C; mean profile **29.0 °C @0 m → 12.2 °C @500 m** (textbook tropical stratification)
- QC-filtered to flags {1,2} (good / probably good) on TEMP, PRES, POSITION
- interpolated onto `DEPTHS` **without extrapolation** (values beyond a profile's own sampled range → NaN)

**Known limitation — 0 m level:** only 32 obs. Argo floats rarely sample at exactly 0 m (shallowest is typically
~4–6 m), and we deliberately do NOT extrapolate upward. All other depths have ~2,350–2,450 obs. If Unit C wants
0 m validation, the honest options are (a) validate at 10 m instead, or (b) explicitly document surface
extrapolation as an assumption. Do **not** silently extrapolate.

**Windows SSL note:** the Argo ERDDAP server fails with `CERTIFICATE_VERIFY_FAILED` because Python's default SSL
context finds no CA bundle. `download_argo._fix_ssl()` sets `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` from `certifi`
at import — every teammate gets this automatically.

**Dependency pin:** `erddapy<3` — argopy 1.4.0 imports a private symbol removed in erddapy 3.x.


## X UNITS: RAW, not z-scored  [changed 2026-08-25, resolves D-009]
`build_samples` writes `X_train/X_test` in **RAW physical units** (°C, psu, m, m/s, and the
sin/cos encodings). The **model owns the entire normalization transform** — it carries
`feat_mean/feat_std` as registered buffers and z-scores internally, so no caller can
double-normalize or skip it.

**Why this changed [VERIFIED bug].** Previously `build_samples` wrote z-scored X while
`train_mlp` z-scored *again* using `norm_stats.json`. Measured on the merged tree:
`X_train` mean 0.000/std 1.000 → after the second z-score, **mean −14.29 / std 29.95**.
The model would have been trained on doubly-scaled data and then served single-scaled data
at inference. Nothing would have errored; the temperatures would just have been wrong.

`norm_stats.json` is unchanged and still carries the stats (computed from TRAIN rows only);
`train_mlp` bakes them into the checkpoint buffers.

**Unit A follow-up:** `train/_data.py::load_real()` still says *"X_train/X_test are ALREADY
z-scored"* and `load_fixtures()` z-scores the fixtures to match that. Both should now pass RAW
straight through — `sample_X.npy` already ships raw. Not a live bug (each path is internally
consistent, and trees are scale-invariant), but the two paths now disagree on convention, which
is exactly the D-014 trap.

## PROVENANCE: `artifacts/provenance.json`  [D-018 fixed]
`build_samples` stamps `{"source": "synthetic"|"real-glorys", "built": <iso>}` **into the
artifacts**. `preprocess` determines it from which files it actually read. The Streamlit banner
and any log MUST read this file — never infer provenance from `data/raw/`, which is gitignored
and absent on a demo laptop. If the file is missing, the app shows a hard **UNKNOWN PROVENANCE**
error rather than silently implying the data is real.
