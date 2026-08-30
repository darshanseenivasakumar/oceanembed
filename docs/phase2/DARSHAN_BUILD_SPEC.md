# DARSHAN_BUILD_SPEC.md — the implementation spec

**Companion to `docs/phase2/DARSHAN_REBUILD_PROMPT.md`.** That file is the orientation: why we are
building this, what is already true, the traps, the schedule. **This file is the how**: exact files,
exact signatures, exact commands, exact tests, per phase.

Written 2026-08-30 by Arjhun's Claude. Every API signature below was read off disk on the
`phase2-tscast-nio` branch, not remembered — 227 of them are listed in the reference appendix. Where
something could not be verified it is tagged `[INFERRED]` or `[UNKNOWN]`, and where the repo does
not settle a question it appears as a **DECISION** with a recommended default and the reason.

---

## How to use this file

**Do not read it end to end.** It is ~2,700 lines and no phase needs more than its own section.
Open a fresh chat per phase with this message:

```
Read CLAUDE.md, then docs/phase2/DARSHAN_REBUILD_PROMPT.md (orientation, ~380 lines).
Then read ONLY the PHASE <N> section of docs/phase2/DARSHAN_BUILD_SPEC.md, plus the
REFERENCE APPENDIX at the end.
Execute PHASE <N>. Work through its numbered steps. Report its DONE checklist when finished.
```

The reference appendix (frozen constants, contract shapes, API cheat-sheet, command cheat-sheet,
test conventions) is short and worth loading every time — it is what stops the model inventing a
function name or hardcoding a constant.

### Where everything is — read with `offset`/`limit`, don't load the file

| section | line | size |
|---|---|---|
| Phase 0 — cold start, environment, data audit | **89** | 155 |
| Phase 1 — wind | **245** | 415 |
| Phase 2 — T_SEQ, adjudicate only | **662** | 249 |
| Phase 3 — fix the inference path | **912** | 578 |
| Phase 4 — final stage-1 retrain | **1491** | 178 |
| Phase 5 — the v2 UI | **1670** | 686 |
| Phase 6 — handback | **2357** | 96 |
| Reference: frozen constants | **2454** | 45 |
| Reference: contract shapes | **2499** | 67 |
| Reference: API cheat-sheet | **2567** | 115 |
| Reference: command cheat-sheet | **2683** | 24 |
| Reference: test conventions | **2708** | 44 |
| **Appendix — open decisions (17 of them)** | **2753** | 127 |
| Appendix — verified API index (217 symbols) | **2881** | 660 |

Line numbers drift if anyone edits above them; if a section is not where the table says, `grep -n
"^## PHASE"` rather than reading from the top.

## Order, dependencies, and what changed since the orientation file was written

| phase | what | depends on | est. |
|---|---|---|---|
| **0** | Cold start, environment, data audit | — | ≤1 h |
| **1** | Wind: download, regrid, merge as channels 6–7 | 0 | 3–4 h download |
| **2** | T_SEQ — **adjudicate only, the sweep is finished** | 0 | **~15 min** |
| **3** | Fix the inference path (blocks everything downstream) | 0 | 1–2 h |
| **4** | Final stage-1 retrain | 1, 2, 3 | 2–4 h |
| **5** | The v2 UI | 3, 4 | 3–4 h |
| **6** | Handback — runs at 15:30 Monday no matter what | — | 1 h |

> **PHASE 2 GOT MUCH CHEAPER — read this even if you read nothing else.**
> The orientation file says the T_SEQ=31 leg "was killed mid-run and never recorded". **That was
> wrong.** It finished on Arjhun's machine at 13:29 on 2026-08-30, after the AGENT_SYNC entry
> claiming otherwise was written. Reading the metrics JSON instead of trusting the log entry is
> what caught it. The sweep is complete:
>
> | T_SEQ | RMSE ↓ | bias | corr | skill_rmse_ratio | provenance |
> |---|---|---|---|---|---|
> | 1 | 0.9096 | +0.1700 | 0.894 | 0.2580 | declared — leg JSON overwritten |
> | **11** | **0.8529** | **+0.0360** | 0.889 | **0.3040** | declared — leg JSON overwritten |
> | 31 | 0.9267 | +0.2515 | 0.882 | 0.2441 | measured — JSON on disk |
>
> **T_SEQ=11 wins by 0.0567 °C**, far clear of the 0.02 °C tie-break, so the rule selects it
> outright. All three legs held seed 42, `simple` decoder, β-NLL 0.5, 40,000 train samples, the
> cnn3d encoder, 5 channels, and the same 962 independent Argo profiles — a clean comparison.
>
> The result is committed as **`artifacts/tseq_ablation.json`** (force-added past `.gitignore`,
> because otherwise it lived on one laptop), and `scripts/phase2/record_tseq_ablation.py --check`
> re-verifies the measured leg against the metrics JSON. **Phase 2 is now adjudication, not a
> 2.5-hour training run.** Spend the time you just got back on Phase 1 and Phase 5.
>
> **The finding is scientifically interesting and belongs in the pitch:** the paper's ±15-day
> window is the *worst* of the three here — worse than no window at all, and the most warm-biased.
> TS-Cast had ~155,000 in-situ profiles at 1/8°; at our sample budget ±5 days wins. That is a
> measured disagreement with the paper, not a reimplementation failure, and it should be reported
> as one.
>
> **What the overwrite cost, and the lesson:** each leg overwrote the previous leg's checkpoint, so
> `artifacts/tscast_stage1.pt` is now the **T_SEQ=31** model — the worst of the three — and the
> winning T_SEQ=11 checkpoint **no longer exists anywhere**. Phase 4 regenerates it. Before you
> launch any training run, copy the existing checkpoint pair aside first (Phase 2 §2.2 shows the
> commands).

## Two more corrections to the orientation file

1. **plotly IS installed** (7.0.0) on Arjhun's clone — the orientation file's trap #20 says it is
   not. The altair-only rule still stands, on the reason recorded in `app/panels/_viz.py`: a panel
   that ImportErrors on demo day is worse than a plainer chart, and the demo laptop is not this
   laptop. Check your own venv rather than trusting either claim.
2. **`download_wind.py`'s docstring is factually wrong.** It claims a CMEMS coverage gap across
   2019–2022 for hourly L4 wind. The live catalog, probed today, shows
   `cmems_obs-wind_glo_phy_my_l4_0.125deg_PT1H` spanning 2007→2026. Record the correction; **do
   not** re-download the monthly wind, because the F6 upwelling numbers were measured on it and
   swapping the product invalidates them.

---

## PHASE 0 — Cold start, run top to bottom before writing any code

Every command below is given for **PowerShell in the repo root** (`D:/myproj/oceanembed` or wherever the clone lives). `.venv\Scripts\python.exe` is written out in full because `accept.py` and `verify_data_bundle.py` both prefer it and you must be running the same interpreter they do.

### 0.1 Pull the branch

```powershell
git fetch origin
git checkout phase2-tscast-nio
git pull --ff-only origin phase2-tscast-nio
git rev-parse --abbrev-ref HEAD          # must print: phase2-tscast-nio
git log --oneline -1
```

**Expected:** branch `phase2-tscast-nio`, HEAD at `06b29fd Post the daily-data results to AGENT_SYNC` or later.

**Never** `git checkout main`, `git merge main`, `git push origin main`. `main` is the tagged Aug-30 demo (`v1.0-demo-aug30`) and `accept.py` step 0 fails the whole run if local `main` has commits that `origin/main` does not. [VERIFIED — `scripts/phase2/accept.py:62-85`]

### 0.2 Delete `tests/phase2/__init__.py` if it exists

```powershell
if (Test-Path tests/phase2/__init__.py) { Remove-Item tests/phase2/__init__.py; "deleted" } else { "absent - good" }
```

**Expected:** `absent - good` on a clean pull of this branch. [VERIFIED — the file is not in `git ls-files`; `tests/phase2/` currently contains only `test_*.py`.]

**Why this matters and is not optional:** a `tests/phase2/__init__.py` makes `tests.phase2` importable as a package named `phase2`, which **shadows `src/phase2`**. Every `from phase2.tscast_nio import ...` then dies under pytest while working fine from a plain `python -c`. Both units reproduced this independently (`docs/phase2/AGENT_SYNC.md` lines 957, 1140-1160; `README_UNZIP_ME_FIRST.txt` "THINGS THAT WILL BITE YOU"). pytest discovers tests fine without it — `pyproject.toml` already sets `pythonpath = ["src"]` and `testpaths = ["tests"]`.

### 0.3 Environment check

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -c "import sys,numpy,torch,xarray,pyarrow,pandas; import oceanembed,phase2; print(sys.version.split()[0]); print('torch',torch.__version__); print('pyarrow',pyarrow.__version__); print(oceanembed.__file__)"
```

**Expected (this machine, [VERIFIED]):**
```
3.12.3
torch 2.13.0+cpu
pyarrow 25.0.1
D:\myproj\oceanembed\src\oceanembed\__init__.py
```

Three things that must be true, each with the failure it prevents:

1. **`oceanembed.__file__` must resolve inside `src/`.** That is the editable install (`pip install -e .`). Without it, `scripts/phase2/verify_daily_bundle.py` fails at `from oceanembed import config` — unlike `accept.py` and `verify_data_bundle.py`, it does **not** insert `src/` into `sys.path` itself. [VERIFIED — `verify_daily_bundle.py:35` vs `accept.py:36`.]
2. **`pyarrow` must import.** `oceanembed.utils.io.load_table` silently falls back to CSV without it, and `artifacts/*.parquet` (the Argo tables) then cannot be read at all. The system Python 3.14 on this machine has no pyarrow — that is exactly why you use `.venv\Scripts\python.exe` and not `python`.
3. **`erddapy<3` is pinned** in `requirements.txt:16` — argopy 1.4.0 imports a private symbol removed in erddapy 3.x. Do not let a resolver upgrade it. Only `scripts/phase2/fetch_argo_daily_period.py` needs argopy; if you are not re-fetching Argo, a broken argopy is not a blocker.

Then the two config sanity checks:

```powershell
.venv\Scripts\python.exe -m oceanembed.config
.venv\Scripts\python.exe -m phase2.tscast_nio.config
```

**Expected, exactly [VERIFIED]:**
```
OceanEmbed config OK: grid 100x240, 15 depths, 11 features, seed 42
tscast_nio config OK: 7 channels, T_SEQ=31, P=17 (+/-2.00 deg), 15 output depths, stage 1
```

If either differs, **stop**. A frozen constant moved and every number downstream is against a different grid than the published ones.

### 0.4 DATA AUDIT — one command per required file

**Nothing in `data/` or `artifacts/` travels through git.** `.gitignore` anchors `/data/` and `/artifacts/*` at the repo root, with exactly four exceptions (`artifacts/sample_X.npy`, `sample_y.npy`, `sample_meta.parquet`, `sample_meta.csv`) plus blanket `*.nc`, `*.pt`, `*.pkl`, `*.ckpt`. [VERIFIED — `.gitignore:1-20`.] A fresh clone therefore has **zero** of the files below. They arrive by unzipping the hand-carried bundle into the repo root (`README_UNZIP_ME_FIRST.txt`) or by regenerating them.

Run all eight. Do not start work on a red row.

**A1 — monthly archive + Argo + wind (the Phase-1 bundle)**
```powershell
.venv\Scripts\python.exe scripts/phase2/verify_data_bundle.py
```
Expected last line: `ALL CHECKS PASSED` — this is the real North Indian Ocean data.
Key rows it prints: `provenance says real-glorys`, `grids temp shape matches the grid (48, 100, 240, 15)`, `temperature cools strongly with depth 28.5 -> 7.7 degC`, `real Argo error table present  879 independent profiles`. [VERIFIED — full run, all rows `[ok]`.]
*Console note:* the script prints em-dashes; under Windows cp1252 they render as `?`. Cosmetic, not a failure.
**If it fails:** unzip the bundle into the repo root so paths land as `data/...` and `artifacts/...`, then re-run. If `provenance.json` does not say `source=real-glorys` with `n_depths=15`, the data did not land correctly — do not proceed, and do not substitute the synthetic `data/raw/synthetic_glorys.nc`.

**A2 — daily bundle (`data/processed/daily/*.npz`)**
```powershell
.venv\Scripts\python.exe -c "from phase2.tscast_nio import dataset as D; d=D.load_daily(); tr,te=D.daily_split_indices(d['times']); print('days',len(d['times']),d['times'][0],'..',d['times'][-1]); print('surface',d['surface'].shape,'temp',d['temp'].shape); print('channels',[str(c) for c in d['channels']]); print('train',len(tr),'test',len(te))"
```
**Expected [VERIFIED]:**
```
days 388 2025-06-01 .. 2026-06-23
surface (388, 100, 240, 5) temp (388, 100, 240, 15)
channels ['sst', 'sss', 'ssh', 'u', 'v']
train 304 test 84
```
Files on disk: `2025.npz` (214 days, 232 MB) and `2026.npz` (174 days, 191 MB).
**If missing:** `load_daily` raises `FileNotFoundError: no daily bundle in data/processed/daily`. Rebuild from raw NetCDF with `python -m phase2.tscast_nio.daily_pipeline --raw-dir data/raw/daily --out-dir data/processed/daily`, which needs ~388 GLORYS `.nc` files (2.9 GB, not in the zip). If you do not have the raw files, **you cannot train on daily data** — say so and fall back to `--data monthly`, do not fabricate a bundle.

**A3 — climatology prior (`artifacts/clim_daily.npz`)**
```powershell
.venv\Scripts\python.exe -c "import numpy as np; z=np.load('artifacts/clim_daily.npz',allow_pickle=True); [print(k,z[k].shape,z[k].dtype) for k in z.files]; print('train_years',z['train_years'])"
```
**Expected [VERIFIED]:**
```
clim_t (12, 100, 240, 15) float32
train_years (3,) int64
drift_by_depth (15,) float32
provenance () <U1844
train_years [2019 2020 2021]
```
`train_years` **must** read `[2019 2020 2021]`. That is the leakage proof: the prior is a 2019-2021 average applied to a 2025-2026 target — completely disjoint periods. [VERIFIED — `scripts/phase2/build_daily_climatology.py:95-118`.]
**If missing:** `.venv\Scripts\python.exe scripts/phase2/build_daily_climatology.py` (needs A2 and `artifacts/climatology.npy`).

**A4 — base climatology (`artifacts/climatology.npy`)**
```powershell
.venv\Scripts\python.exe -c "import numpy as np; a=np.load('artifacts/climatology.npy'); print(a.shape,a.dtype,round(float(np.nanmin(a)),2),round(float(np.nanmax(a)),2))"
```
**Expected:** `(12, 100, 240, 15) float32` with a physical range (roughly 1-33 degC). [VERIFIED — 16.5 MB file present; shape confirmed via `clim_daily.clim_t`, which is a straight copy of it.]
**If missing:** regenerate with `oceanembed.climatology.build_climatology` over TRAIN years only. Never over all years — that is the leakage point named in `tscast_data_model.md` section 3.

**A5 — independent Argo for the daily period (`artifacts/argo_daily_period.parquet`)**
```powershell
.venv\Scripts\python.exe -c "import pandas as pd; df=pd.read_parquet('artifacts/argo_daily_period.parquet'); d=pd.to_datetime(df['date']); te=df[(d>=pd.Timestamp('2026-04-01'))&(d<=pd.Timestamp('2026-06-23'))]; print('rows',len(df),'cols',list(df.columns)); print('test-window rows',len(te),'profiles',te.groupby([te['lat'].round(4),te['lon'].round(4),pd.to_datetime(te['date']).dt.date]).ngroups)"
```
**Expected [VERIFIED]:**
```
rows 59599 cols ['lat', 'lon', 'date', 'depth_idx', 'temp']
test-window rows 12237 profiles 908
```
908 is the number quoted in commit `7b41f2f`. If it comes back **0**, the trainer must refuse to score — that refusal already exists (commit `e1030b2`, "refuse to score on zero profiles") and you must not remove it.
**If missing:** `.venv\Scripts\python.exe scripts/phase2/fetch_argo_daily_period.py` (needs working argopy + network; writes `artifacts/argo_daily_period.parquet`, plus per-year `argo_2025/2026.parquet`).

**A6 — Phase-1 Argo test set (`artifacts/argo_test.parquet`)**
```powershell
.venv\Scripts\python.exe -c "import pandas as pd; df=pd.read_parquet('artifacts/argo_test.parquet'); print('rows',len(df),'profiles',df.groupby(['lat','lon','date']).ngroups)"
```
**Expected:** ~2,455 real Argo profiles (`README_UNZIP_ME_FIRST.txt` line 25). This is what `CollocationEngine._match_argo` reads and what `glorys_vs_argo.py` and `measure_mc_calibration.py` score against. [VERIFIED — file present, 390 KB.]
**If missing:** it is in the zip. Without it, `accept.py` check F1 still runs but every collocation returns `NO_ARGO_NEARBY`.

**A7 — measurement artifacts F8 and the v2 check read**
```powershell
.venv\Scripts\python.exe -c "import os; [print(('ok  ' if os.path.exists('artifacts/'+f) else 'MISSING'),f) for f in ['argo_error_by_depth.json','tscast_baseline_metrics.json','architecture_feasibility.json','glorys_vs_argo.json','mc_calibration.json']]"
```
**Expected:** five `ok` lines. [VERIFIED — all five present.]
**If missing:** each is regenerable and `accept.py` regenerates two of them for you (`glorys_vs_argo.json` via `glorys_vs_argo.py`, `mc_calibration.json` via `measure_mc_calibration.py` — see `accept.py:138-141`). The other two: `measure_v2_metrics.py` writes `tscast_baseline_metrics.json`; `architecture_feasibility.py` writes `architecture_feasibility.json` (a multi-hour bake-off — do **not** re-run it casually, and never regenerate it just to make a check pass). `argo_error_by_depth.json` is Phase-1 published output and comes from the zip.

**A8 — trained checkpoint (`artifacts/tscast_stage1.pt`)**
```powershell
.venv\Scripts\python.exe -c "import json,os; print('ckpt',os.path.exists('artifacts/tscast_stage1.pt')); m=json.load(open('artifacts/tscast_stage1_metrics.json')); print(m['encoder'],'T_SEQ',m['T_SEQ'],'data',m['data'],'seed',m['seed'],'best_epoch',m['best_epoch']); print('overall rmse',round(m['metrics']['overall']['rmse'],4),'argo_profiles',m['argo_profiles'])"
```
**Expected [VERIFIED]:**
```
ckpt True
cnn3d T_SEQ 31 data daily seed 42 best_epoch 4
overall rmse 0.9267 argo_profiles 962
```
**If missing:** `TSCastPredictor.__init__` raises `FileNotFoundError` with the message "this class will not fabricate a prediction from an untrained network" — that is correct behaviour. Retrain with `python -m phase2.tscast_nio.train.train_stage1` (see the command cheat-sheet). Do **not** hand-write a metrics JSON to satisfy a check.

---

## PHASE 1 — WIND (PS requirement 8, currently 0%)

Goal: daily `wu`, `wv` for **2025-06-01 .. 2026-06-23** on the frozen 0.25° grid, merged into the daily bundle as channels 6–7, so the model runs on all 7 contract channels instead of 5.

### 1.0 State you do not have to re-derive

- `data/processed/daily/{2025,2026}.npz` exist on Arjhun's machine with `channels = ['sst','sss','ssh','u','v']`, `surface` = `(214,100,240,5)` and `(174,100,240,5)`, times `2025-06-01..2025-12-31` and `2026-01-01..2026-06-23`, 388 days, 0 missing. **[VERIFIED 2026-08-30 by loading both npz.]** They are gitignored — on your machine they may need the ~1–2 h `daily_pipeline` rebuild first.
- Raw GLORYS: `data/raw/daily/glorys_YYYYMMDD.nc`, 388 files, ~63 MB each; the internal `time` coordinate is stamped **`YYYY-MM-DDT00:00:00`** for the named day. **[VERIFIED on `glorys_20250601.nc`, `glorys_20251212.nc`, `glorys_20260623.nc`.]** That is what fixes the day-boundary convention in §1.4.
- `copernicusmarine` **2.4.1** is installed; `describe()` works with **no login**. **[VERIFIED.]**
- The contract in `docs/phase2/tscast_data_model.md` §2 **already** specifies 7 channels in the order `["sst","sss","ssh","u","v","wu","wv"]` with units `[...,"m s-1","m s-1"]`. **This phase makes the data match the contract, so no contract edit is needed.** If you find yourself editing that table, stop — you are changing the frozen thing instead of the broken thing.

---

### 1.1 Which product, and the coverage gap — verified, not assumed

Probed the live catalog today: `copernicusmarine.describe(contains=["wind"], disable_progress_bar=True)`, then read `variable.coordinates` for `eastward_wind` on the `arco-geo-series` service. **[VERIFIED 2026-08-30, no login.]**

| dataset_id | time coverage (from catalog metadata) | step | verdict |
|---|---|---|---|
| `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | **2024-06-13T04:00 → 2026-08-28T23:00** | 0.125°, 1 h | **USE THIS** — covers the whole window with room at both ends |
| `cmems_obs-wind_glo_phy_my_l4_0.125deg_PT1H` | 2007-01-11 → **2026-04-20T23:00** | 0.125°, 1 h | covers all but the last 64 days — and it stops **inside the test window** |
| `cmems_obs-wind_glo_phy_my_l4_0.25deg_PT1H` | 1994-06-01 → 2009-10-31 | 0.25°, 1 h | far too early |
| `cmems_obs-wind_glo_phy_my_l4_P1M` | monthly | 0.25° | the F6 product already on disk (48 files). Not for this. |

**Decision (mine, and I recommend you keep it): use NRT alone for the entire window.** The MY 0.125° product ends 2026-04-20, and `DAILY_TEST` starts 2026-04-01 (`dataset.py:193`). Splicing MY→NRT would put a product discontinuity 20 days into the test period — a change in the input distribution exactly where the headline number is measured, which is indistinguishable from a model effect. One product, one seam-free series.

**Correction to a claim in the repo, recorded but NOT acted on:** the docstring of `src/phase2/data/download_wind.py` (lines 9–16) states "There is a genuine gap in CMEMS hourly L4 wind coverage across 2019-2022." That is **false as of today's catalog** — `cmems_obs-wind_glo_phy_my_l4_0.125deg_PT1H` spans 2007–2026 and covers 2019–2022 hourly. The docstring's other two rows check out exactly (0.25° MY = 1994–2009 ✓, NRT = 2024–2026 ✓); it simply never probed the 0.125° MY product. **Do not re-download the F6 monthly wind in this window** — the F6 upwelling numbers were measured on the monthly product and swapping it invalidates them. Post the correction to `AGENT_SYNC.md` and move on.

**Variables — the trap that will kill a copy-paste.** NRT L4 carries: `eastward_wind`, `northward_wind`, `wind_curl`, `wind_divergence`, plus `_bias` and `_sdd`/`_dv` companions. It has **no `eastward_stress`, no `northward_stress`, no `wind_speed`**. **[VERIFIED from the catalog listing.]** `download_wind.VARIABLES` (which lists all three of those) would raise `copernicusmarine.VariableDoesNotExistInTheDataset`. Request exactly `["eastward_wind", "northward_wind"]`.

*Side finding for the record:* TS-Cast's per-pixel error channels — `docs/phase2/tscast_data_model.md` §5 says "Probe CMEMS for error fields during the download" — **do exist** for wind (`eastward_wind_sdd`, `eastward_wind_bias`). The 7-channel contract is frozen, so we do not take them. Record the answered probe in AGENT_SYNC; do not widen the contract in a 24-hour window.

---

### 1.2 Step 1 — probe ONE day before you move 7 GB

Never launch the full job on an unverified grid. Build the downloader (§1.3) with a `--probe` flag that fetches a single day into a throwaway directory and prints the source grid **against `config`**.

```powershell
# repo root, Windows
$env:PYTHONPATH="src"
.venv\Scripts\python -m phase2.data.download_wind_daily --probe
```

The probe must print, and you must read, all of:

```
[windh] probe 2025-06-01 -> data/raw/wind_probe/wind_hourly_probe.nc  (<measured> MB)
        vars      : ['eastward_wind', 'northward_wind']   units: m s-1 / m s-1
        time      : 24 stamps, 2025-06-01T00:00 .. 2025-06-01T23:00, step 1 h
        latitude  : n=<n>  [<first> ... <last>]  step <s>
        longitude : n=<n>  [<first> ... <last>]  step <s>
        offset vs config.LAT[0]=5.0   : <+/-x.xxxx> deg      <-- READ THIS LINE
        offset vs config.LON[0]=45.0  : <+/-x.xxxx> deg      <-- AND THIS ONE
        NaN fraction over the box     : <f>   (land? or all-ocean product?)
```

**Predicted, not observed:** from catalog metadata (`latitude.minimum_value = -89.9375`, `step = 0.125`) the NRT grid sits at `X.0625 + k·0.125`, so the first row inside 5–30 N is **5.0625** and the first column inside 45–105 E is **45.0625**; every `config.LAT`/`config.LON` value lands **exactly halfway** between two source rows (±0.0625°). **[INFERRED from catalog step/min — the probe is what turns it into VERIFIED.]** If the probe prints something else, believe the probe and write down what it printed.

---

### 1.3 Step 2 — the downloader

**Create `src/phase2/data/download_wind_daily.py`** (Unit B area). Signatures to write:

```python
DATASET_ID = "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"
VARIABLES  = ["eastward_wind", "northward_wind"]
OUT_DIR    = os.path.join(config.DATA_RAW, "wind_hourly")   # NOT data/raw/wind — see the box below
START, END = "2025-06-01", "2026-06-23"
HALO_DEG   = 0.5

def _fix_ssl() -> None: ...
def month_chunks(start: str = START, end: str = END) -> list[tuple[pd.Timestamp, pd.Timestamp]]: ...
def download_months(chunks=None, out_dir: str = OUT_DIR) -> str: ...
def probe(out_dir: str | None = None) -> str: ...
```

> **DO NOT write these files into `data/raw/wind/`.** `phase2.events.upwelling.WIND_DIR` is `os.path.join(config.DATA_RAW, "wind")` and both `upwelling.load_wind_stress` (`upwelling.py:126`) and `tests/phase2/test_events.py:326` glob `wind_*.nc` there. An hourly NRT file dropped in that directory would be picked up by F6, which then looks for `eastward_stress` — a variable NRT does not have — and a different unit's tests start failing for reasons that have nothing to do with them. Separate directory, distinct filename prefix.

`_fix_ssl()` is copied **verbatim** from `download_wind._fix_ssl` (certifi → `SSL_CERT_FILE` + `REQUESTS_CA_BUNDLE`), same as `scripts/phase2/download_daily_2025_2026.py` lines 23–25 do at module scope.

The fetch loop, resumable in exactly the shape `download_wind.download_dates` already uses:

```python
def download_months(chunks=None, out_dir: str = OUT_DIR) -> str:
    _fix_ssl()
    import copernicusmarine                      # imported late: the repo imports without it
    chunks = chunks or month_chunks()
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    done, failed, mb = 0, [], 0.0
    for i, (lo, hi) in enumerate(chunks, 1):
        fname = f"wind_hourly_{lo:%Y%m}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            mb += os.path.getsize(fpath) / 1e6; done += 1
            print(f"[windh] {i:2d}/{len(chunks)} {lo:%Y-%m} present, skipping"); continue
        try:
            copernicusmarine.subset(
                dataset_id=DATASET_ID, variables=VARIABLES,
                minimum_longitude=r["lon_min"] - HALO_DEG, maximum_longitude=r["lon_max"] + HALO_DEG,
                minimum_latitude=r["lat_min"] - HALO_DEG,  maximum_latitude=r["lat_max"] + HALO_DEG,
                start_datetime=f"{lo:%Y-%m-%d}T00:00:00", end_datetime=f"{hi:%Y-%m-%d}T23:00:00",
                coordinates_selection_method="outside",
                output_directory=out_dir, output_filename=fname, overwrite=True,
            )
            mb += os.path.getsize(fpath) / 1e6; done += 1
            print(f"[windh] {i:2d}/{len(chunks)} {lo:%Y-%m} OK ({mb/1000:.2f} GB total)", flush=True)
        except Exception as e:                    # one bad month must not kill the run
            failed.append(f"{lo:%Y-%m}")
            print(f"[windh] {i:2d}/{len(chunks)} {lo:%Y-%m} FAILED: {type(e).__name__}: {str(e)[:90]}")
    print(f"\n[windh] {done}/{len(chunks)} months, {mb/1000:.2f} GB in {out_dir}")
    if failed: print(f"[windh] FAILED: {failed}  (re-run to retry only those)")
    return out_dir
```

Two deliberate differences from the monthly fetcher, both verified against the installed API (`inspect.signature(copernicusmarine.subset)`, cm 2.4.1):

1. **`coordinates_selection_method="outside"`** (allowed values are `'inside' | 'strict-inside' | 'nearest' | 'outside'`; the default is `'inside'`). With `'inside'` the subset starts at 5.0625/45.0625 and interpolating onto `config.LAT[0]=5.0` / `config.LON[0]=45.0` falls off the edge → the whole first row and column come back NaN. That is precisely the documented wart in `load_wind_stress` ("the first row and column ... come back NaN"). We do not have to inherit it. `HALO_DEG=0.5` is belt-and-braces in case the served grid differs from the catalog metadata.
2. **`start_datetime`/`end_datetime` carry hours** (`T00:00:00` / `T23:00:00`), because this product is hourly. A date-only end time would silently drop the last 23 hours of each month, and the partial-day check in §1.4 would then reject one day per month and you would spend an hour hunting the wrong thing.

**Chunking / cost.** 13 calendar chunks (2025-06 … 2026-06). Size arithmetic, **[INFERRED from array shape, not measured]**: 201×481 cells × 24 h × 2 vars × 4 B ≈ **18.6 MB/day** → **≈ 7.2 GB** for 388 days, which agrees with the estimate already in `AGENT_SYNC`. Wall time is **[UNKNOWN]** — measure the first month, print the running total, and extrapolate before you walk away. Check free disk first: 7.2 GB hourly + ~0.4 GB derived + the rebuilt 7-channel bundle (~1.4 GB) on top of whatever the 5-channel bundle already costs.

Run it in a **background terminal**, not in the chat loop:

```powershell
$env:PYTHONPATH="src"
.venv\Scripts\python -m phase2.data.download_wind_daily *>&1 | Tee-Object data\raw\wind_hourly.log
```

---

### 1.4 Step 3 — hourly → daily, and proving there are no partial days

**Create `src/phase2/data/preprocess_wind_daily.py`.**

```python
IN_DIR   = os.path.join(base.DATA_RAW, "wind_hourly")
OUT_PATH = os.path.join(base.DATA_PROCESSED, "wind_daily.npz")

def daily_mean_one_file(path: str) -> dict: ...   # {"times","wu","wv","n_hours","offset_deg","step_deg"}
def run(in_dir: str = IN_DIR, out_path: str = OUT_PATH) -> str: ...
```

**Day-boundary convention — decided, and here is why.** A day is the **UTC calendar day**: the mean of the hourly fields stamped `00:00 … 23:00` UTC on that date. GLORYS12V1 `P1D-m` files are stamped `T00:00:00` on the day they represent **[VERIFIED on 3 files]**, and `daily_pipeline` stores `times` as `datetime64[D]`, so calendar-date matching is what the bundle already means by "a day". Any other convention (12:00→12:00, local solar time) inserts a half-day lag between the wind and the ocean state it is supposed to explain, and nothing downstream would show it.

**Order of operations: average in time first, regrid second.** Both operations are linear, so they commute where the mask is constant in time — and averaging first does 1/24 of the interpolation work. Where the mask is *not* constant in time they do not commute exactly; time-averaging first is the safer of the two because it keeps NaN handling inside a single per-cell reduction.

```python
def daily_mean_one_file(path: str) -> dict:
    with xr.open_dataset(path) as ds:
        latn  = preprocess._find_coord(ds, "latitude", "lat")      # frozen helper, not a new one
        lonn  = preprocess._find_coord(ds, "longitude", "lon")
        timen = preprocess._find_coord(ds, "time", "time_counter")
        ds = ds.sortby(latn).sortby(lonn).sortby(timen)

        raw_lat = np.asarray(ds[latn].values, dtype="float64")
        raw_lon = np.asarray(ds[lonn].values, dtype="float64")
        offset  = (float(raw_lat[0] - float(base.LAT[0])), float(raw_lon[0] - float(base.LON[0])))
        step    = float(np.diff(raw_lat).min())

        # PROOF OF COMPLETENESS, taken from the time axis BEFORE any averaging.
        days_of  = ds[timen].values.astype("datetime64[D]")
        uniq, n_hours = np.unique(days_of, return_counts=True)

        daily = ds.resample({timen: "1D"}).mean()                  # bins labelled 00:00 UTC
        reg   = daily.interp({latn: np.asarray(base.LAT, dtype="float64"),
                              lonn: np.asarray(base.LON, dtype="float64")}, method="linear")
        ...
```

`ds.resample({timen: "1D"}).mean()` is verified working on the installed **xarray 2025.9.0**, and its bin labels come out at `00:00` — i.e. UTC calendar days, left-closed, left-labelled.

**How you prove no partial days** — three mechanical checks, none of them "it looked fine":

1. `n_hours` is computed from the raw time axis and **stored in the npz per day**. `run()` prints `min/max` and the full list of any day with `n_hours != 24`.
2. `run()` **refuses to write** if any day has `n_hours != 24`. Not a warning. A 19-hour "daily mean" during the monsoon onset is biased toward whichever hours survived, and it looks exactly like a real wind field.
3. `run()` asserts the union of days equals `pd.date_range(START, END, freq="D")` — 388 days, no gaps, no duplicates from overlapping month chunks.

Expected console output (shape, not values — the numbers are yours to measure):

```
[wind-daily] 13 files in data/raw/wind_hourly
[wind-daily] 2025-06: 30 days, hours/day min 24 max 24
...
[wind-daily] 388 days 2025-06-01..2026-06-23, 0 gaps, hours/day == 24 everywhere
[wind-daily] source grid step 0.1250 deg, offset vs config (+<x.xxxx>, +<x.xxxx>) deg -> regridded
[wind-daily] wu range <-a>..<+b> m/s, wv <-c>..<+d> m/s, NaN fraction <f>
[wind-daily] wrote data/processed/wind_daily.npz (<n> MB)
```

Output npz keys: `times` `(388,) datetime64[D]`, `wu` / `wv` `(388,100,240) float32`, `n_hours` `(388,) int16`, `provenance` `()` JSON string (dataset id, variables, day convention, regrid method, source grid offset, `git rev-parse --short HEAD`).

**Sanity bound before anything downstream sees it:** `np.nanmax(np.hypot(wu, wv)) < 40` m/s over this basin and window. A tropical cyclone in the Arabian Sea can exceed that at 10 m in an instantaneous field, but not in a 24-hour, 0.25°-cell mean. If it trips, look at the data — do not raise the bound to make it pass.

---

### 1.5 Step 4 — the 0.125° → 0.25° regrid and the +0.125° offset trap

**Read `phase2.events.upwelling.load_wind_stress` (`src/phase2/events/upwelling.py:104-163`) before writing this.** It is the existing, correct handling of exactly this trap for the monthly product, and your function must do the same three things — but you must **not** edit or extend it: it is Unit A's F6 file, it is keyed by `YYYYMM`, and it expects stress variables NRT does not carry.

What the monthly trap actually is, re-measured for this brief on `data/raw/wind/wind_201901.nc` **[VERIFIED 2026-08-30]**:

```
latitude  [5.125 5.375 5.625 ... 29.875]   n=100    offset vs config.LAT[0]: +0.125
longitude [45.125 45.375 ...  104.875]     n=240    offset vs config.LON[0]: +0.125
```

Same `(100, 240)` shape, plausible values, every cell ~14 km southwest of where a positional assignment would put it. **Shape agreement is the trap, not the evidence.**

The three things to copy:

1. **Interpolate explicitly** onto `config.LAT`/`config.LON` — `ds.interp({latn: base.LAT, lonn: base.LON}, method="linear")`, the same call `preprocess._process_one` (`preprocess.py:41`) uses for GLORYS. Do not write a bilinear interpolator; two regridders that can disagree is the D-014 failure.
2. **Assert the result's coordinates** afterwards, by value:
   ```python
   if not (np.allclose(got_lat, np.asarray(base.LAT, dtype="float64"), atol=1e-6)
           and np.allclose(got_lon, np.asarray(base.LON, dtype="float64"), atol=1e-6)):
       raise AssertionError("regridded wind coordinates do not match config.LAT/LON")
   ```
3. **Record the measured offset** in the returned dict and in `provenance` (`load_wind_stress` returns `raw_grid_offset_deg`). A number in the provenance is checkable next month; a sentence in a docstring is not.

For the NRT product the offset is **not** +0.125 — the config points fall midway between two source rows, so linear interpolation is the mean of the two neighbours. Print it, do not assume it.

**The test that actually catches a half-cell shift** (§1.8, `test_regrid_of_a_plane_field_is_exact`): a bilinear interpolation reproduces a linear field *exactly*. Build a synthetic hourly file whose `eastward_wind = 2·lat + 3·lon`, run it through your regrid, and assert `wu[i,j] == 2·LAT[i] + 3·LON[j]` to `atol=1e-4`. Any grid misalignment of δ shows up as a constant error of `2δ` or `3δ`. Verified in this environment: interpolating that plane at (5.0, 45.0) returns exactly `145.0`. This assertion needs no threshold, no real data, and no network.

---

### 1.6 Step 5 — merging into `daily_pipeline` as channels 6–7

Edit `src/phase2/tscast_nio/daily_pipeline.py`. (This crosses into Unit A's tree; the rebuild prompt's Phase 1 step 3 authorizes it in writing. Keep the edit strictly additive and post it to `AGENT_SYNC.md`.)

```python
from phase2.tscast_nio import config as tsconfig

WIND_KEYS  = ["wu", "wv"]
WIND_UNITS = ["m s-1", "m s-1"]


def _load_wind(path: str) -> dict:
    """{datetime64[D] -> (wu, wv)} from data/processed/wind_daily.npz. Refuses partial days."""
    z = np.load(path, allow_pickle=True)
    bad = z["times"][z["n_hours"] != 24]
    if bad.size:
        raise ValueError(f"{path}: {bad.size} day(s) were not built from 24 hours ({bad[:5]}); "
                         "a partial-day mean is a biased wind field, not a missing one")
    return {np.datetime64(t, "D"): (z["wu"][k], z["wv"][k]) for k, t in enumerate(z["times"])}


def build_year(files, year, out_dir, with_salinity=True, wind=None) -> str:
    keys  = SURFACE_KEYS  + (WIND_KEYS  if wind is not None else [])
    units = SURFACE_UNITS + (WIND_UNITS if wind is not None else [])
    if wind is not None and keys != list(tsconfig.CHANNELS):
        raise AssertionError(f"channel order drifted from the contract: {keys} != "
                             f"{list(tsconfig.CHANNELS)}")
    surface = np.full((n, nlat, nlon, len(keys)), np.nan, dtype="float32")
    ...
    # --- after `order = np.argsort(times)` has been applied ---------------------------
    if wind is not None:
        missing = [str(t) for t in times if np.datetime64(t, "D") not in wind]
        if missing:
            raise ValueError(f"{year}: no wind for {len(missing)} day(s), first {missing[:5]}. "
                             "Refusing to write a bundle with wind on some days and NaN on "
                             "others -- that is a distribution shift the model cannot see.")
        for k, t in enumerate(times):
            wu, wv = wind[np.datetime64(t, "D")]
            surface[k, :, :, 5] = wu
            surface[k, :, :, 6] = wv
```

Apply the wind **after** the `argsort` reorder and key it by date, never by loop position. The GLORYS loop fills `surface[k]` in glob order and sorts afterwards; a second positional fill would silently pair each day's wind with a different day's ocean.

`main()` gains:

```python
ap.add_argument("--wind", default=os.path.join("data", "processed", "wind_daily.npz"),
                help="daily wind npz; if absent, the bundle is written with 5 channels and says so")
ap.add_argument("--no-wind", action="store_true", help="force the 5-channel bundle")
```

and `payload` / `provenance` become:

```python
channels=np.array(keys), units=np.array(units),
...
"channels_note": f"{len(keys)} of the contract's {tsconfig.N_CHANNELS}"
                 + ("" if wind is not None else "; wind absent -- state this beside every result"),
"wind": None if wind is None else {
    "source":    "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H (hourly L4)",
    "reduction": "mean of the 24 hourly fields of each UTC calendar day",
    "regrid":    "xarray linear interp 0.125 -> 0.25 deg onto config.LAT/LON, coords asserted",
    "from":      os.path.abspath(a.wind),
},
```

**Command:**

```powershell
$env:PYTHONPATH="src"
.venv\Scripts\python -m phase2.tscast_nio.daily_pipeline `
    --raw-dir data/raw/daily --out-dir data/processed/daily7 `
    --wind data/processed/wind_daily.npz
```

**DECISION — where the 7-channel bundle is written.** Phase 2's `T_SEQ=31` leg must run on the **5-channel** bundle to stay comparable with the recorded `T=1` and `T=11` legs. Overwriting `data/processed/daily/` destroys that comparability mid-window. **Recommended default: write to `data/processed/daily7/`**, leave the 5-channel bundle untouched, and add a `--daily-dir` argument to `train_stage1.py` (`dataset.load_daily(d=None)` already takes a directory, so it is a one-line change at `train_stage1.py:128` — `D.load_daily(a.daily_dir)` — defaulting to the current path, i.e. no behaviour change for any existing command). The alternative — rebuild in place and re-run the ablation on 7 channels — costs a second ~2.5 h CPU leg you do not have. If you take the in-place route anyway, say so in AGENT_SYNC, because the ablation table then stops being a like-for-like comparison.

**What must NOT break** (all verified by reading the consumers):

- **Readers index by name, and they must keep doing so.** `dataset.load_daily` carries `chans = list(z["channels"])` through to `GriddedPatches(..., channels=...)`; `GriddedPatches.__init__` takes `self.C = surface.shape[-1]` (`dataset.py:58`), so the sampler widens to 7 automatically. `train_stage1.py:156` builds `TSCastNIO(enc, len(d["channels"]), ...)`, so `c_in` follows the data. Nothing needs a hardcoded 7 — and nothing should acquire one.
- **`land_mask` must stay derived from channel 0 (`sst`).** `daily_pipeline.py:89` reads `~np.isfinite(surface[:, :, :, 0]).any(axis=0)`. Leave it exactly as it is. "Generalising" it to *all* channels would fold the wind product's own mask into the ocean mask and silently shrink the training domain.
- **Rebuild BOTH years in one run.** `load_daily` takes `channels` from the *first* file only (`dataset.py:181`) and then `np.concatenate`s the `surface` arrays. A 7-channel 2025 next to a 5-channel 2026 raises a shape error whose message says nothing about wind. Optional 3-line hardening in `load_daily`: raise a named error if a later file's channel list differs from the first.
- **The shipped checkpoint will refuse the 7-channel bundle, and that is correct.** `inference.py:44` raises `ValueError("checkpoint was trained on channels ... but the loaded data has ...")`. Do not "fix" it by slicing channels off the bundle. It means: retrain (Phase 4). **Copy `artifacts/tscast_stage1.pt` and `tscast_stage1_metrics.json` aside first** — the T=11 copy is currently the only surviving artifact of the best model.
- **Two hardcoded strings become false the moment wind lands:** `train_stage1.py:300` `"channels_note": "5 of the contract's 7; wind arrives with the daily pipeline"` and `daily_pipeline.py:104` the same. Compute both from `len(d["channels"])`. Shipping a metrics JSON that says "5 of 7" beside a 7-channel result is a fabricated claim in the artifact that other people quote. (`train_stage1.py:298` `"trained_on": "monthly archive, T_SEQ=1"` is already false for every daily run — same one-line fix, pre-existing, worth doing while you are in there.)
- **`scripts/phase2/verify_daily_bundle.py` does not see wind at all** — it verifies raw GLORYS `.nc` files (`EXPECTED_VARS = {"thetao","so","zos","uo","vo"}`). Do not read a green verdict from it as wind having been checked. The wind checks are §1.7 and §1.8, and nothing else covers them.

---

### 1.7 Step 6 — the scientific sanity test: the SW monsoon reversal

A shape test proves the array is 7 wide. It does not prove channel 6 is wind, that it is on the right grid, or that `wu` is not `wv`. The check that does is the **seasonal reversal of the Findlater jet over the western Arabian Sea** — the largest, most reliable wind signal in this basin.

Box: **8–16 N, 50–60 E**, indices via the frozen helpers `grids.nearest_lat_index` / `grids.nearest_lon_index` (never `searchsorted` — trap #4).

Season coverage in our window **[VERIFIED from the bundle times]**: JJA 2025 complete (92 days), DJF 2025-26 complete (90 days), plus 2026-06-01..23. Both seasons are present, so this is a multi-month aggregate — **the trap the rebuild prompt names is real: a single-date check can invert the sign**, because a single day can sit inside a monsoon break.

**Primary assertion — threshold-free, and the one I recommend you rely on.** CF convention fixes the meaning: `eastward_wind` is the component *toward* the east. The SW monsoon blows *from* the southwest, i.e. toward the northeast → both components positive. The NE monsoon reverses both.

```python
assert wu_jja > 0 and wv_jja > 0, "SW monsoon must blow toward the NE (both components +)"
assert wu_djf < 0 and wv_djf < 0, "NE monsoon must blow toward the SW (both components -)"
```

This fails loudly on a swapped `wu`/`wv`, a sign flip, a wrong-hemisphere box, a bad regrid that smears the coast, and on wind pasted onto the wrong dates. It needs no number from any paper.

**Secondary assertion — the magnitude ratio, and I cannot pin its threshold without running it.** Compute wind speed **per day and then average** — `mean(√(wu²+wv²))`, never `√(mean(wu)² + mean(wv)²)`, because averaging the components first cancels opposing days and understates the speed by a large factor in a reversing regime.

```python
speed = np.sqrt(z["wu"] ** 2 + z["wv"] ** 2)
ratio = np.nanmean(speed[jja][:, si, sj]) / np.nanmean(speed[djf][:, si, sj])
print(f"JJA/DJF mean wind-speed ratio, western Arabian Sea: {ratio:.2f}")
assert ratio > FLOOR
```

**[UNKNOWN]** — I have not downloaded this data and I will not invent the number. My unverified expectation is a ratio somewhere around 2–3 (**[INFERRED]**, from the Findlater jet being a summer phenomenon; not from a checked citation). Procedure:

1. Run once with the assertion replaced by a print. Record the measured ratio.
2. Set `FLOOR` to the measurement rounded down to the nearest 0.5, minus 0.5 (so a 2.4 measurement gives `FLOOR = 1.5`), and put the measured value in the test docstring tagged `[VERIFIED <date>]` with the box and the day count.
3. **If the measured ratio comes in below 1.5, do not lower the floor.** The western Arabian Sea in JJA is not marginally windier than in DJF. A ratio near 1 means the components are swapped, the dates are misaligned, the box is in the wrong place, or the daily means were built from partial days. Fix the data. Never tune a scientific test to accommodate it.

Also assert the box has real coverage before believing either number: `np.isfinite(speed[jja][:, si, sj]).mean() > 0.5`, otherwise skip with a message saying the box is masked — a mean over four surviving cells is not a basin signal.

---

### 1.8 Tests — exact names and what each asserts

**New file: `tests/phase2/test_wind_daily.py`.** (Do not add `tests/phase2/__init__.py` — trap #1: it shadows `src/phase2` under pytest.) The first six run offline on a synthetic hourly NetCDF written to `tmp_path`; the last four use the real npz and `pytest.skip` when it is absent, mirroring `_any_wind_month()` in `tests/phase2/test_events.py:324`.

| test | asserts |
|---|---|
| `test_hourly_means_use_all_24_hours_of_the_utc_calendar_day` | a fixture with 48 hourly stamps yields exactly 2 days labelled `00:00`, and each day's value equals the plain mean of its own 24 hours |
| `test_a_day_with_missing_hours_is_refused_not_averaged` | delete 5 hours from the fixture → `run()` raises, and the message names the date and the hour count |
| `test_regrid_of_a_plane_field_is_exact` | `wu = 2·lat + 3·lon` on the source grid reproduces `2·LAT[i] + 3·LON[j]` to `atol=1e-4` — a half-cell shift shows as a constant offset (verified: bilinear interp is exact on a plane) |
| `test_regridded_wind_is_on_config_lat_lon_by_coordinate_not_by_shape` | shape is `(100, 240)` **and** `np.allclose(coords, config.LAT/LON, atol=1e-6)`; the docstring states that shape agreement is the trap |
| `test_the_source_grid_offset_is_measured_and_recorded` | the offset stored in `provenance` equals the offset recomputed from the source file, and is non-zero |
| `test_wind_merges_as_channels_six_and_seven_in_the_frozen_order` | after `build_year(..., wind=...)`: `list(channels) == list(tsconfig.CHANNELS)`, `units == tsconfig.CHANNEL_UNITS`, `surface.shape[-1] == 7`, and `surface[k,:,:,5]` is the wind for `times[k]` — not for `times[0]` |
| `test_land_mask_still_comes_from_sst_not_from_wind` | force channel 6 to all-NaN → `land_mask` is byte-identical to the 5-channel build |
| `test_bundle_refuses_to_merge_wind_that_does_not_cover_every_day` | drop one day from the wind dict → `build_year` raises and names the date; the npz is not written |
| `test_southwest_monsoon_reverses_the_zonal_wind_over_the_western_arabian_sea` | §1.7 primary — JJA `(wu,wv)` both `> 0`, DJF both `< 0`, over 8–16 N / 50–60 E, aggregated across months |
| `test_monsoon_wind_speed_ratio_exceeds_the_measured_floor` | §1.7 secondary — per-day speed then averaged; floor set from the recorded measurement, measurement quoted in the docstring |

Run:

```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python -m pytest tests/phase2/test_wind_daily.py -v
$env:PYTHONPATH="src"; .venv\Scripts\python -m pytest tests/phase2 -q       # expect the prior count + 10
$env:PYTHONPATH="src"; .venv\Scripts\python scripts/phase2/accept.py
```

---

### 1.9 Fallback — if CMEMS refuses, or the download cannot finish

1. **Do not fabricate wind.** No zero-filled channels 6–7, no ERA5 substituted without saying so, no climatological wind standing in for the real days. A constant channel teaches the model that wind carries no information, and the resulting "7-channel" number is a lie about the input.
2. **Do not ship a half-winded bundle.** `build_year` refuses (§1.6) when wind is missing for any day. Wind present in training and absent in test is a distribution shift the model cannot see and the loss curve will not show.
3. **Stay on 5 channels and say so, everywhere a number appears:**

   > **5 of the contract's 7 channels — wind (`wu`, `wv`) absent.** PS requirement 8 is unmet. All metrics below were produced from SST, SSS, SSH, u, v only. The wind product `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` covers the window (2024-06-13 → 2026-08-28, verified); the blocker was `<the actual reason>`, not availability.

   That sentence goes in: the AGENT_SYNC entry, `docs/HANDOFF.md`, the bundle's `provenance.channels_note`, the metrics JSON's `channels_note`, and the UI panel beside the prediction. It is a stated limitation, not a footnote, and the reason must be the real one.
4. **Partial credit is still credit.** Even if the merge never happens, a completed `data/processed/wind_daily.npz` plus a passing monsoon test is a verified artifact with the download cost already paid — Phase 4 or the next session merges it in an hour. Record what exists.

---

### 1.10 DONE checklist

- [ ] `--probe` run; source grid coordinates, step, units and NaN fraction printed **against config** and pasted into AGENT_SYNC
- [ ] `src/phase2/data/download_wind_daily.py` exists; resumable (skip-if-present), chunked by month, `_fix_ssl()`, running total; writes to `data/raw/wind_hourly/`, **not** `data/raw/wind/`
- [ ] 13 monthly hourly files on disk; measured size and wall time recorded (the 7.2 GB figure is arithmetic, replace it with the measurement)
- [ ] `src/phase2/data/preprocess_wind_daily.py` exists; `data/processed/wind_daily.npz` written with `times`, `wu`, `wv`, `n_hours`, `provenance`
- [ ] 388 days, no gaps, no duplicates, `n_hours == 24` on every day — printed, not assumed
- [ ] Regrid asserts `config.LAT`/`config.LON` by value; measured grid offset stored in `provenance`
- [ ] `daily_pipeline` merges `wu`,`wv` as channels 6–7; `channels == tsconfig.CHANNELS` asserted in code; `data/processed/daily7/{2025,2026}.npz` rebuilt **in one run**, `surface` = `(214,…,7)` and `(174,…,7)`
- [ ] `land_mask` byte-identical to the 5-channel bundle
- [ ] `"5 of the contract's 7"` literals in `daily_pipeline.py:104` and `train_stage1.py:300` replaced by computed strings
- [ ] `artifacts/tscast_stage1.pt` + metrics JSON copied aside before any 7-channel retrain
- [ ] 10 new tests pass; full `tests/phase2` suite and `scripts/phase2/accept.py` still pass
- [ ] Monsoon reversal test passes; the measured JJA/DJF speed ratio is written into the test docstring with a date tag
- [ ] AGENT_SYNC entry: product + verified coverage window, measured size/time, the grid-offset verdict, the monsoon numbers, the `download_wind.py` docstring correction, and the `daily7/` vs in-place decision you took
- [ ] `docs/HANDOFF.md` updated; committed on `phase2-tscast-nio`

### Decisions this section deliberately leaves to you

1. **`data/processed/daily7/` vs rebuilding in place.** Recommended: `daily7/` + an additive `--daily-dir` flag, so Phase 2's `T_SEQ=31` leg stays comparable with the two recorded legs.
2. **Keep or delete the 7.2 GB of hourly files after the daily npz is built.** Recommended: keep. They are the evidence behind the daily means and the only way to re-derive them without a second download. Delete only if disk forces it, and say so in `provenance`.
3. **`FLOOR` for the JJA/DJF speed-ratio test.** Cannot be pinned before the data exists. Measure, then freeze with a margin — and if the measurement is below 1.5, fix the data rather than the test.
4. **Whether to fix `train_stage1.py:298`'s stale `"trained_on"` string** while you are in that file. It is Unit A's file and a pre-existing falsehood; one line, and it is quoted in shipped artifacts.

## Phase 2 — the T_SEQ ablation, completed and adjudicated

### 2.0 Reference: the complete argparse surface of `train_stage1`

Every flag below exists in `src/phase2/tscast_nio/train/train_stage1.py` lines 68–101 [VERIFIED — read the file and ran `--help`]. There are 18 flags. There is no `--seed`, no `--out`, no `--resume`, no `--channels`: do not compose a command with one.

| flag | type | default | what it actually does |
|---|---|---|---|
| `--epochs` | int | `20` | Maximum epochs. Early stopping usually ends the run sooner. |
| `--train-samples` | int | `40000` | Cap on training patches. All valid `(t,i,j)` positions are enumerated, then randomly subsampled with `np.random.default_rng(base.SEED)`. The JSON records `len(ds_tr)`, i.e. what was actually used. |
| `--lr` | float | `1e-3` | AdamW learning rate. |
| `--batch-size` | int | `256` | Train loader only. The held-out loader and the Argo scoring loader are **hardcoded to 512** (lines 167, 256). |
| `--encoder` | str | `None` | `None` → `winning_encoder()` reads `artifacts/architecture_feasibility.json` and returns `"cnn3d"`; if that file is missing it falls back to `cnn3d` and prints `bake-off has NOT run`. **No argparse `choices`** — a typo dies later with `KeyError` from `encoders.ENCODERS` (`mlp_control`, `cnn3d`, `cnn_attention`, `vit`). |
| `--no-residual` | flag | off | Sets `residual=False`. **Under `--decoder simple` this is a no-op**: `TSCastNIO.forward` returns from the simple head (models/tscast.py line 226–229) before the residual branch. It is still written into the checkpoint and the metrics JSON as `residual`, so it is a provenance field that can mislead. [VERIFIED by reading forward] |
| `--patience` | int | `4` | Epochs with no held-out improvement (improvement means `va_nll < best - 1e-4`) before stopping. |
| `--weight-decay` | float | `1e-2` | AdamW weight decay. |
| `--device` | str | `auto` | `auto` → `cuda` if `torch.cuda.is_available()` else `cpu`. Its help text claims "43x the input elements" at T_SEQ=31; the measured wall-clock ratio is 13.8x (AGENT_SYNC 2026-08-29 §5). Where 43 came from is [UNKNOWN]. |
| `--num-workers` | int | `0` | Applied to the train and held-out loaders only; the Argo scoring loader is constructed without it. See the RAM warning in 4.2 before raising this on Windows. |
| `--latent` | int | `None` | → `config.LATENT_DIM` = 128. |
| `--unet-width` | int+ | `None` | → `config.UNET_CHANNELS` = `(32, 64, 128)`. **Only affects `--decoder film`.** |
| `--decoder` | `film`\|`simple` | `film` | `simple` is the bake-off head (latent → 256 → 2×15), the only decoder ever scored well against Argo. **The default is `film`, which is the losing decoder — you must pass `--decoder simple` explicitly on every command.** Not saved into the checkpoint (defect, see 4.4). |
| `--loss` | `nll`\|`mse` | `nll` | Training objective. Held-out is always scored at plain NLL (`beta=0`) so early stopping never moves with `--beta`; under `--loss mse` it falls back to MSE. |
| `--data` | `monthly`\|`daily` | `monthly` | **The default is `monthly`.** Every Phase 2/4 command must pass `--data daily`. |
| `--t-seq` | int | `None` | → 1. `--data monthly` with `t_seq != 1` raises `SystemExit` with an explanation. |
| `--test-samples` | int | `12000` | Held-out GLORYS patches for the NLL curve and early stopping. **It does not affect the Argo score**: line 252 overwrites `ds_te.index` with the Argo collocation triples before scoring. |
| `--beta` | float | `0.5` | beta-NLL (Seitzer 2022). Leave at 0.5 unless you are running a deliberate loss ablation. |

Two behaviours worth knowing before you spend three hours:

- **The run refuses to save rather than save a bad model.** If no epoch beats the initial `inf` held-out loss — which is what a NaN loss produces, since every NaN comparison is `False` — line 214 raises `RuntimeError("no epoch improved on the initial held-out loss; refusing to save")` *after* the full training budget has burned. Watch epoch 1's held-out NLL; if it prints `nan`, kill the run immediately.
- **`code_commit` is read at the END of the run** (line 333, `git rev-parse --short HEAD`). Commit everything *before* launching, and do not commit anything while a run is in flight, or the JSON will name a tree that is not the tree that ran.

### 2.1 Preconditions — check all five before starting a leg (2 minutes, saves hours)

Run from the repo root:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -c "import os,numpy as np;from oceanembed import config as b;from phase2.tscast_nio import dataset as D;d=D.load_daily();tr,te=D.daily_split_indices(d['times']);print('steps',len(d['times']),'train',len(tr),'test',len(te));print('channels',[str(c) for c in d['channels']]);print('clim',os.path.exists(b.art('climatology.npy')));print('argo',os.path.exists(b.art('argo_daily_period.parquet')));print('bakeoff',os.path.exists(b.art('architecture_feasibility.json')))"
```

Expected on a correct clone [VERIFIED on Arjhun's box]: `steps 388 train 304 test 84`, `channels ['sst','sss','ssh','u','v']`, and three `True`s.

1. `data/processed/daily/*.npz` — gitignored. If `load_daily` raises `FileNotFoundError`, run the daily pipeline first (1–2 h); that is another phase's card.
2. `artifacts/climatology.npy` — **gitignored, 17 MB, shape (12,100,240,15), built from 2019–2021 only.** It arrives with the data zip. If it is missing, STOP. Do not substitute `artifacts/clim_daily.npz` (tracked, but a different object) and do not synthesise a prior: with `--decoder simple` the climatology never enters the model, but it *is* the denominator of every skill number the run reports (line 264–265). A different prior silently changes the headline skill.
3. `artifacts/argo_daily_period.parquet` — **tracked in git** [VERIFIED via `git ls-files artifacts`], so it is in your clone. Without it, `--data daily` exits with a message pointing at `scripts/phase2/fetch_argo_daily_period.py`.
4. `artifacts/architecture_feasibility.json` — tracked; supplies `cnn3d`.
5. `git status` clean, so `code_commit` means something.

### 2.2 Preserve the existing checkpoint pair BEFORE you launch anything

Every run overwrites exactly two files: `artifacts/tscast_stage1.pt` and `artifacts/tscast_stage1_metrics.json` (lines 283, 336). There is no run-id in the filename. A leg that finishes destroys the previous leg's only machine-written record — that is precisely how the T_SEQ=1 and T_SEQ=11 logs were lost.

**Step 1 — read what you have before you name the copy.** Never name a backup from memory of what you think ran:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -c "import torch;ck=torch.load('artifacts/tscast_stage1.pt',map_location='cpu',weights_only=False);print({k:v for k,v in ck.items() if k not in ('state_dict','norm')})"
.venv\Scripts\python.exe -c "import json;m=json.load(open('artifacts/tscast_stage1_metrics.json'));print(m['data'],'T_SEQ',m['T_SEQ'],'chan',len(m['channels']),'decoder',m['decoder'],'samples',m['train_samples'],'epochs',m['epochs_requested'],m['best_epoch'],'argo',m['argo_profiles'],'rmse',round(m['metrics']['overall']['rmse'],4))"
```

**Step 2 — copy both, named by what they actually are:**

```powershell
Copy-Item artifacts\tscast_stage1.pt           artifacts\tscast_stage1_tseq<N>.pt
Copy-Item artifacts\tscast_stage1_metrics.json artifacts\tscast_stage1_metrics_tseq<N>.json
```

**Step 3 — the copies are also gitignored** (`/artifacts/*` and `*.pt`), so they survive only on that disk. See 4.4 for making a result durable.

> **What is on Arjhun's machine, and why you must check rather than assume.** [VERIFIED by reading the files, 2026-08-30] `artifacts/tscast_stage1_metrics.json` there (mtime 13:29) describes a **completed** T_SEQ=31 daily leg: `data=daily, T_SEQ=31, channels=5, decoder=simple, loss=nll, beta=0.5, epochs_requested=15, epochs_run=8, best_epoch=4, train_samples=40000, train_seconds=8037.1, argo_profiles=962`, **overall RMSE 0.9267**, skill_rmse_ratio 0.2441, corr 0.8824, bias +0.2515, calibration 0.70–1.77. The matching `.pt` carries `T_SEQ: 31, epochs: 4`. But `docs/phase2/AGENT_SYNC.md` (2026-08-30 §4, committed 13:47, i.e. *after* that file was written) still calls T_SEQ=31 "the leg that was killed mid-run and never recorded". **The two disagree and I cannot resolve it from here** — the JSON's contents are internally consistent with a normal early stop at patience 4, which is not a kill. Both files are gitignored, so neither reached your clone through git. Decide in step 2.3 which world you are in.

### 2.3 Run the T_SEQ=31 leg — on the 5-channel bundle

**Decision point, resolve it first:**

- **If `artifacts/tscast_stage1_metrics.json` does not exist on your machine** (the expected case — it cannot travel through git): run the leg. This is the default path.
- **If it exists and reads `data=daily, T_SEQ=31, channels 5`**: you may enter its RMSE as a *declared* leg (2.5) with `--recorded-source "artifacts/tscast_stage1_metrics_tseq31.json, machine-written <mtime>"`. That is legitimate — it is a machine-written artifact, not a retyped number. **Prefer measuring it yourself if you have 2.5 h**, because a measured leg gives you a log you own and removes the contradiction above.

The command — 5 channels, matching the two recorded legs, `--epochs 15 --patience 4` to match their budget as far as AGENT_SYNC records it:

```powershell
cd <repo root>
$env:PYTHONPATH='src'
$env:PYTHONUNBUFFERED='1'
"===== T_SEQ=31 =====" | Tee-Object -FilePath tseq_ablation.log
.venv\Scripts\python.exe -m phase2.tscast_nio.train.train_stage1 `
    --data daily --t-seq 31 --decoder simple --loss nll `
    --epochs 15 --train-samples 40000 --test-samples 12000 --patience 4 `
  | Tee-Object -FilePath tseq_ablation.log -Append
```

1. **`--decoder simple` is not optional.** The default is `film`, which measured ~0.18 °C worse under either loss (AGENT_SYNC 2026-08-29 §1). Omitting it silently runs the losing architecture.
2. **Do not add `2>&1`.** In Windows PowerShell 5.1, redirecting a native executable's stderr wraps each line in a `NativeCommandError` record. The trainer prints everything the parser needs to stdout via `print()`; a traceback still reaches your console.
3. **`$env:PYTHONUNBUFFERED='1'`** — without it, stdout is block-buffered into the pipe and epoch lines arrive in clumps, so you cannot time epoch 1.
4. **5 channels, not 7.** Arjhun's handover (AGENT_SYNC 2026-08-30 §5.2) makes this explicit: the T_SEQ=31 leg must run on the 5-channel bundle or it is not comparable to the two recorded legs. Wind enters at Phase 4, as its own variable.
5. **Do not change `--train-samples`, `--epochs`, `--patience`, `--beta`, `--batch-size`, `--lr` or the seed** between legs. The ablation's only claim is that the *window length* moved the number.

Expected console shape [VERIFIED against the recorded run's JSON]:

```
encoder: cnn3d  (bake-off winner over 4 candidates)
device : cpu   beta-NLL: 0.5
data   : daily, 388 steps, T_SEQ=31, train 304 / test 84
train 40,000 samples  |  held-out GLORYS 12,000
params : 547,238 total  (506,504 encoder + 40,734 decoder), latent 128, decoder simple, loss nll
  epoch 1/15  train NLL -0.0463   held-out NLL -0.4262  <- best
  ...
restored the best epoch: 4 (held-out NLL -0.5774). Everything below is that model, not the last one.
independent Argo in the test window: 962 profiles (median offset <N> d)
 depth     n    RMSE    corr     bias   skill   sigma  ratio
 ... 15 rows ...
OVERALL rmse=0.9267  corr=0.8824  bias=+0.2515  skill=+0.2441
calibration ratio 0.70-1.77  (1.0 = honest; >1 = overconfident. MC-dropout measured 1.56-3.54)
wrote ...\artifacts\tscast_stage1.pt
wrote ...\artifacts\tscast_stage1_metrics.json
```

The `params : 547,238 total (506,504 encoder + 40,734 decoder)` line is a cheap integrity check — if it differs, something about latent/decoder/channels differs from the recorded legs and the comparison is void.

If `independent Argo in the test window` prints a materially different count from **962**, stop and find out why before quoting anything: the profile set is supposed to be identical across legs.

### 2.4 The log format the picker actually parses

`scripts/phase2/pick_tseq_and_retrain.py::parse` (lines 32–44) needs exactly two line shapes, in order [VERIFIED by reading the regexes and by running the script]:

- a banner matching `T_SEQ=(\d+)\s*=====` — e.g. `===== T_SEQ=31 =====`;
- then, later, a line matching `OVERALL\s+rmse=([\d.]+)` — which the trainer prints itself.

Notes that matter:

1. The trainer's own `data   : daily, 388 steps, T_SEQ=31, train 304 / test 84` line **does not** match the banner regex (a comma follows, not `=====`). You must echo the banner yourself. [VERIFIED]
2. `parse` reads bytes and decodes UTF-8 with `errors="replace"`, then normalises `\r`. On this box `Tee-Object` writes **UTF-8 with BOM** (first bytes `EF BB BF`) [VERIFIED by hexdump], which parses fine. PowerShell 5.1's `Tee-Object` has **no `-Encoding` parameter** [VERIFIED] — if your shell writes UTF-16 instead, every regex silently fails to match and the picker refuses for "incomplete sweep". Check before blaming the picker:

```powershell
Select-String -Path tseq_ablation.log -Pattern 'T_SEQ=\d+\s*=====','OVERALL\s+rmse='
```
Both patterns must print a hit.
3. One banner captures the **next** `OVERALL` line only. Append legs to the same log freely; just always write the banner immediately before launching the leg.
4. A crashed leg produces a banner with no `OVERALL`, so the picker refuses instead of ranking a partial sweep. That is the designed behaviour, not a bug.

### 2.5 Adjudicate with `pick_tseq_and_retrain.py --recorded`

The T_SEQ=1 and T_SEQ=11 legs genuinely ran; their console logs were not kept and each leg overwrote the previous metrics JSON, so `docs/phase2/AGENT_SYNC.md` 2026-08-29 §5 is the surviving record: **T_SEQ=1 → 0.9096, T_SEQ=11 → 0.8529** (962 profiles, identical seed/samples/decoder/loss). **Do not reconstruct their console sections into the log file.** Arjhun retracted that instruction himself (AGENT_SYNC 2026-08-30 §3): a hand-written file that looks like run output, fed to a script built to read real runs, is manufacturing evidence. The `--recorded` flag is the labelled door for exactly this.

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe scripts\phase2\pick_tseq_and_retrain.py `
    --log tseq_ablation.log `
    --recorded "1=0.9096,11=0.8529" `
    --recorded-source "docs/phase2/AGENT_SYNC.md 2026-08-29 section 5" `
    --dry-run
```

Actual output when the measured leg reads 0.9267 [VERIFIED — I ran this against a probe log in a scratch directory]:

```
T_SEQ ablation, independent Argo RMSE (lower is better):
  T_SEQ= 1  0.9096 degC   (100,000 samples in the final run)   [declared, from docs/phase2/AGENT_SYNC.md 2026-08-29 section 5]
  T_SEQ=11  0.8529 degC   (60,000 samples in the final run)   [declared, from docs/phase2/AGENT_SYNC.md 2026-08-29 section 5]
  T_SEQ=31  0.9267 degC   (40,000 samples in the final run)   [measured in tseq_ablation.log]

  2 of 3 legs are DECLARED, not measured by this script. Anything downstream that quotes this ranking must say so too.

WINNER: T_SEQ=11 at 0.8529 degC, ahead of T_SEQ=1 by 0.0567 degC

FINAL RUN: phase2.tscast_nio.train.train_stage1 --data daily --t-seq 11 --decoder simple --loss nll --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5
```

Reading it:

- **`declared` vs `measured` is the point.** Two of three rows are quoted, not re-measured here. Every downstream sentence that uses this ranking — AGENT_SYNC, EXPERIMENT_LOG, the UI, the slide — must repeat that. The script prints the obligation; honour it.
- **Sample counts differ by leg in the FINAL run** (`SAMPLES_FOR = {1: 100000, 11: 60000, 31: 40000}`), matched to measured per-window cost. That is a real confound and the script's docstring says to report it either way: a longer window that wins, wins despite less data; a longer window that loses may have lost partly because of it.
- **The <0.02 °C tie-break.** If the margin were under 0.02 the script prints a note and, if the winner is the *longer* window, switches to the shorter one and says so. At 0.0567 that branch does not fire — T_SEQ=11 wins on its own.
- **`--log` is required even if every leg is declared** (`required=True`, and `parse` does `open(...)` unguarded → `FileNotFoundError`). Point it at a real file.
- **A T_SEQ outside {1, 11, 31} raises `KeyError` at the `SAMPLES_FOR[ts]` print.** Do not invent a fourth leg without extending that dict.
- **Refusals are features.** A leg appearing in both the log and `--recorded` exits with "Refusing to guess which one you meant"; fewer than three legs exits with "Refusing to pick a winner from a partial sweep".

Drop `--dry-run` when you want it to launch the final run itself (2.4/4.1). It uses `sys.executable`, sets `PYTHONPATH="src"` **relative to the current directory**, so you must be in the repo root, and it inherits stdout — so pipe it to a log.

### 2.6 DECISION — the trainer builds the encoder with `t_seq=1`, always

`src/phase2/tscast_nio/train/train_stage1.py` line 156:

```python
    model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent,
                      residual=not a.no_residual, unet_channels=widths,
                      decoder=a.decoder).to(dev)
```

The literal `1` is not `t_seq`, the variable computed on line 133 from `--t-seq`. The *data* is a 31-day window; the *encoder* is constructed as if it were a 1-day window. The checkpoint and the metrics JSON then record `T_SEQ: 31` (lines 286, 301).

**Why it is currently harmless.** In `encoders.CNN3D`, `t_seq` is used only to pick pooling kernels: `pt = 2 if t >= 2 else 1`. No weight shape depends on it. Measured [VERIFIED, ran it]:

| encoder | encoder params at `t_seq=1` / `t_seq=31` | same state_dict keys+shapes? | forward on a real T=31 input, built at `t_seq=1` |
|---|---|---|---|
| `cnn3d` | 506,504 / 506,504 | **yes** | runs, returns `mu (B,15)` |
| `cnn_attention` | 420,160 / 420,160 | **yes** | runs |
| `mlp_control` | 332,928 / 455,808 | no | `RuntimeError: mat1 and mat2 shapes cannot be multiplied (2x248 and 8x512)` |
| `vit` | 362,240 / 730,880 | no | `RuntimeError: The size of tensor a (497) must match the size of tensor b (17)` |

So with `cnn3d` (the bake-off winner, and what every leg used) nothing crashes and the parameter count matches the recorded 506,504 exactly. What changes is the *pooling schedule*: at `t_seq=1` all three `AvgPool3d` kernels are `(1,2,2)`, so the time axis is never pooled inside the body and the 31 days are collapsed only by the final `AdaptiveAvgPool3d(1)` — a flat mean over 31 steps instead of the paper's hierarchical 31→15→7→3 temporal downsampling. It is a valid model. It is **not** the model the constructor argument describes, and it is more expensive than the intended one.

**Exactly when it becomes a silent bug — it already has, on the serving path.** `src/phase2/tscast_nio/inference.py` line 51 rebuilds with `t_seq=ck["T_SEQ"]`, i.e. 31. Because the shapes match, `load_state_dict` succeeds with **zero missing and zero unexpected keys**, and the predictor serves a *different function* from the one that was validated. Measured on 32 real held-out daily patches with the shipped checkpoint [VERIFIED]:

```
mean |delta| 0.137 degC   max |delta| 0.891 degC
```

That drift is **2.4x the entire effect the ablation is measuring** (T=11 beat T=1 by 0.057 °C). Nothing errors, nothing logs, and the app would quote validation numbers for predictions it is not producing. It would also become a loud bug the moment anyone re-runs the bake-off's `mlp_control` or `vit` at T>1 — those raise, as measured above.

**Two options, and you must pick one and write down which:**

- **Option A — fix the value** (`t_seq=t_seq`). Architecturally correct and matches the paper. But it invalidates the T_SEQ=11 recorded leg (built at `t_seq=1` with 11-day data), so the ablation would need that leg re-run before the ranking means anything. T_SEQ=1 is unaffected — there the literal is correct.
- **Option B — pin it, and make serving agree.** Keep the encoder at 1, state it, and stop inference from silently disagreeing.

**Recommended default: Option B for this window, Option A as a separate, labelled experiment afterwards.** Reason: B preserves every measurement already taken and fixes the only part that is actually wrong today (train/serve divergence); A changes the model under a half-finished ablation and costs another leg you do not have time for. Do not present B as "the paper's encoder".

Concrete B, in three edits:

```python
# train_stage1.py, above main()
ENCODER_T_SEQ = 1          # DECISION 2026-08-31: the encoder is built at 1 REGARDLESS of the data
                           # window. cnn3d has no t_seq-dependent weight shape, so this only sets
                           # the temporal pooling schedule -- but the built model differs from a
                           # t_seq-matched one by 0.137 degC mean / 0.89 degC max on the same
                           # weights (measured). Serving MUST rebuild at this value, not at T_SEQ.

def build_model(enc, c_in, latent, widths, residual, decoder):
    return TSCastNIO(enc, c_in, t_seq=ENCODER_T_SEQ, p=config.P, latent=latent,
                     residual=residual, unet_channels=widths, decoder=decoder)
```

```python
# train_stage1.py, the torch.save dict (line 284): add two keys
    "encoder_t_seq": ENCODER_T_SEQ,   # what the ENCODER was built with
    "decoder": a.decoder,             # currently missing -- see 4.4
```

```python
# inference.py line 51: build from the new key, defaulting to the historical behaviour
    self.model = TSCastNIO(ck["encoder"], len(ck["channels"]),
                           t_seq=ck.get("encoder_t_seq", 1), p=ck["P"], latent=ck["latent"],
                           residual=ck["residual"], decoder=ck.get("decoder", "film"))
```

Record the choice in `docs/DECISIONS.md` and in the metrics JSON (a `"encoder_t_seq_note"` field), because a reader who sees `T_SEQ: 31` will otherwise reasonably assume the encoder pooled over time.

---

## PHASE 3 — Fix the inference path

`TSCastPredictor` cannot load the only validated checkpoint we have. Nothing downstream of the model — no panel, no demo, no output record — runs until this is fixed. Everything below was executed on the repo at `phase2-tscast-nio`; the numbers are measured, not illustrative.

### 3.0 What is actually broken [VERIFIED — reproduced, see 3.1]

Four separate defects, all in `src/phase2/tscast_nio/inference.py`:

1. **The decoder is assumed, not read.** `TSCastPredictor.__init__` builds `TSCastNIO(...)` without passing `decoder=`, so it takes the constructor default `decoder="film"` and constructs the FiLM `ClimatologyUNet`. The shipped `artifacts/tscast_stage1.pt` is a **simple-head** checkpoint. `load_state_dict` raises.
2. **`train_stage1.py` never persists the choice.** The saved dict (lines 284–289) has exactly these non-`state_dict` keys — measured by loading the file:
   `['encoder', 'seed', 'residual', 'channels', 'P', 'T_SEQ', 'latent', 'unet_channels', 'norm', 'epochs', 'lr', 'batch_size']`
   No `decoder`, no `loss`, no `data`, no `code_commit`. The information the predictor needs was thrown away at save time.
3. **The predictor defaults to monthly data; the checkpoint is daily.** `self.data = data or D.load_monthly()`. Measured: `artifacts/tscast_stage1_metrics.json` says `data = daily`, `T_SEQ = 31`, `decoder = simple`, `encoder = cnn3d`, 962 independent Argo profiles, overall Argo RMSE **0.9267 degC**. The daily bundle is 388 steps, 2025-06-01..2026-06-23; the monthly archive is 48 steps, 2019-01-15..2022-12-15.
4. **The channel guard cannot catch (3).** Both loaders return `['sst','sss','ssh','u','v']`. Measured — identical lists, so the guard at lines 44–48 passes and the model is silently fed a 31-*month* window in place of a 31-*day* one.

Two more things surfaced while verifying, and they must be handled here rather than discovered later:

- **`T_SEQ` in the checkpoint means two different things.** `train_stage1.py` line 156 builds the model with a hardcoded `t_seq=1` while the dataset is built with `t_seq=31`, and then saves `"T_SEQ": t_seq` (= 31). Measured: `CNN3D` has no `t_seq`-dependent parameters, so **both builds load the same `state_dict` with "All keys matched successfully"** — but they compute different functions. On identical random input the two builds' `mu` differ by up to **0.0695 degC**. A predictor that "helpfully" builds with `ck["T_SEQ"]` produces silently wrong numbers with no error.
- **`argo_check` currently has no working data source.** `CollocationEngine._argo_table()` loads `config.art("argo_test")` — measured range **2022-01-01 .. 2022-12-31**. Against any 2025–2026 prediction date it matches zero profiles, forever, and reports `NO_ARGO_NEARBY`. The right table is `artifacts/argo_daily_period.parquet` (measured 2025-06-01 .. 2026-06-22, 4331 profiles, columns `lat, lon, date, depth_idx, temp`).

---

### 3.1 Step 1 — Reproduce the failure before you change one line

A fix with no reproduction is a guess. Run this first and paste the output into `docs/HANDOFF.md`.

```bash
# bash / git-bash
PYTHONPATH=src python -c "from phase2.tscast_nio.inference import TSCastPredictor; TSCastPredictor()"
```
```powershell
# PowerShell
$env:PYTHONPATH="src"; python -c "from phase2.tscast_nio.inference import TSCastPredictor; TSCastPredictor()"
```

**Expected output [VERIFIED]** — traceback ending at `inference.py:53` in `self.model.load_state_dict(ck["state_dict"])`:

```
RuntimeError: Error(s) in loading state_dict for TSCastNIO:
	Missing key(s) in state_dict: "decoder.stem.a.weight", ... (128 keys, all decoder.*)
	Unexpected key(s) in state_dict: "simple_head.0.weight", "simple_head.0.bias",
	                                 "simple_head.2.weight", "simple_head.2.bias".
```

Then measure the checkpoint yourself rather than trusting this brief:

```bash
PYTHONPATH=src python -c "
import torch; ck=torch.load('artifacts/tscast_stage1.pt', map_location='cpu', weights_only=False)
print([k for k in ck if k!='state_dict'])
sd=ck['state_dict']
print('decoder.* keys:', sum(k.startswith('decoder.') for k in sd))
print('simple_head.* keys:', [k for k in sd if k.startswith('simple_head')])"
```

**Expected [VERIFIED]:** the 12-key meta list from 3.0(2); `decoder.* keys: 0`; four `simple_head.*` keys.

Do not proceed until you have seen both.

---

### 3.2 Step 2 — Make the checkpoint self-describing

**File to edit:** `src/phase2/tscast_nio/train/train_stage1.py`.

**2a. Factor the save payload into a function**, so the round-trip test in 3.6 exercises the real trainer code instead of re-implementing it. Add above `main()`:

```python
CHECKPOINT_KEYS = (
    "state_dict", "encoder", "decoder", "loss", "beta", "data", "seed", "residual",
    "channels", "P", "T_SEQ", "model_t_seq", "latent", "unet_channels", "norm",
    "epochs", "lr", "batch_size", "code_commit", "clim_artifact", "clim_train_years",
)


def checkpoint_payload(model, *, encoder, decoder, loss, beta, data, residual, channels,
                       p, t_seq, model_t_seq, latent, unet_channels, norm, epochs, lr,
                       batch_size, code_commit, clim_artifact, clim_train_years) -> dict:
    """Everything the predictor needs to REBUILD this model, not just its weights.

    `T_SEQ` is the DATA window the sampler cut. `model_t_seq` is what was actually handed to
    TSCastNIO. They are not the same number today (see DECISION D-P3-2) and a predictor that
    confuses them loads cleanly and returns different numbers -- measured 0.0695 degC.
    """
    return {
        "state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
        "encoder": encoder, "decoder": decoder, "loss": loss, "beta": float(beta),
        "data": data, "seed": base.SEED, "residual": bool(residual),
        "channels": [str(c) for c in channels],          # np.str_ -> str, so errors are readable
        "P": int(p), "T_SEQ": int(t_seq), "model_t_seq": int(model_t_seq),
        "latent": int(latent), "unet_channels": [int(w) for w in unet_channels],
        "norm": [v.tolist() for v in norm],
        "epochs": int(epochs), "lr": float(lr), "batch_size": int(batch_size),
        "code_commit": code_commit,
        "clim_artifact": clim_artifact, "clim_train_years": [int(y) for y in clim_train_years],
    }
```

**2b. Name the model's window explicitly.** Replace line 156's silent literal:

```python
model_t_seq = 1          # NOT t_seq -- deliberate, see DECISION D-P3-2. Recorded, not hidden.
model = TSCastNIO(enc, len(d["channels"]), t_seq=model_t_seq, p=config.P, latent=latent,
                  residual=not a.no_residual, unet_channels=widths, decoder=a.decoder).to(dev)
```

**2c. Hoist the git sha** (it is currently computed only inside the metrics dict, line 333) to just before training, and reuse it for both artifacts:

```python
code_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
```

**2d. Read the climatology's real years from the artifact**, not from `base.TRAIN_YEARS`. Measured: `artifacts/clim_daily.npz` carries `train_years = [2019 2020 2021]` plus a `provenance` string documenting why the prior is 2019–2021 and not the daily train split. A config constant can drift; the artifact is what was built.

```python
_cd = base.art("clim_daily.npz")
clim_train_years = ([int(y) for y in np.load(_cd)["train_years"]] if os.path.exists(_cd)
                    else list(base.TRAIN_YEARS))
```

**2e. Replace the `torch.save` call** (lines 284–289) with `torch.save(checkpoint_payload(model, encoder=enc, decoder=a.decoder, loss=a.loss, beta=a.beta, data=a.data, residual=not a.no_residual, channels=d["channels"], p=config.P, t_seq=t_seq, model_t_seq=model_t_seq, latent=latent, unet_channels=widths, norm=ds_tr.norm, epochs=best["epoch"], lr=a.lr, batch_size=a.batch_size, code_commit=code_commit, clim_artifact="climatology.npy", clim_train_years=clim_train_years), ck)`.

**2f.** In the metrics dict, the line `"trained_on": "monthly archive, T_SEQ=1 (the daily bundle had not landed)"` is stale — the run that produced the shipped artifact was `--data daily --t-seq 31`. Replace the hardcoded string with `f"{a.data} data, T_SEQ={t_seq}, model built at t_seq={model_t_seq}"`. Do not leave a sentence in an artifact that contradicts the artifact's own `data` field.

#### DECISION D-P3-1 — does the fix have to load a checkpoint that lacks the new keys?

**Yes, and it must do it by reading, not by defaulting.** `artifacts/tscast_stage1.pt` is the only checkpoint that has ever been scored against independent Argo (0.9267 degC over 962 profiles). Refusing it outright would take the demo offline for a full retrain and would invalidate `tscast_stage1_metrics.json`, which `output.measured_rmse_by_depth()` reads to generate every `reasons` string.

But "backward compatible" must not mean "guess a default". The state dict **states** the decoder:

- `simple_head.*` present ⇒ `decoder="simple"`. [VERIFIED on the shipped file]
- any `decoder.*` key present ⇒ `decoder="film"`.
- neither ⇒ refuse; the file is not a `TSCastNIO`.

That is a measurement of the artifact, not an assumption, and it is exact. **Recommended:** implement the state-dict read as the fallback, prefer the explicit `decoder` key when present, and record in `provenance` *which* route was used, so any record made from a legacy checkpoint is auditable.

For `data`, the state dict carries no evidence — but the trainer does. `train_stage1.py` lines 134–136 raise `SystemExit` for `--t-seq > 1` unless `--data daily`. So `T_SEQ > 1 ⇒ daily` is a fact about the code that produced the file, not a guess. `T_SEQ == 1` with no `data` key is **genuinely ambiguous** (either loader can produce it) and must be refused with instructions, not defaulted. The shipped checkpoint has `T_SEQ = 31`, so it resolves to `daily` unambiguously.

`loss` and `beta` are recorded for provenance only; they do not affect reconstruction, so a missing `loss` key is reported as `None`, never invented.

#### DECISION D-P3-2 — `T_SEQ` (data window) vs `model_t_seq` (build argument)

The trainer feeds the encoder 31-step windows while constructing it as if `t_seq=1`, so the temporal `AvgPool3d` factors are all 1 and the time axis survives to the final `AdaptiveAvgPool3d`. Whether that is the intended architecture is a **scientific** question, not an inference-path question.

**Recommended:** do **not** change the value in this phase. Changing it changes what the network computes, which invalidates the 0.9267 degC that our only Argo validation rests on. Record both numbers, make the predictor use `model_t_seq`, and file the architecture question for the retrain phase with the measured 0.0695 degC divergence as its evidence. For a legacy checkpoint that has no `model_t_seq`, use `1` and say so in provenance (`"model_t_seq_source": "assumed 1 from the trainer's hardcode at the time this checkpoint was written"`) — an assumption that is labelled is allowed; an assumption that is silent is not.

---

### 3.3 Step 3 — Rewrite the predictor

**File to edit:** `src/phase2/tscast_nio/inference.py`. Keep the existing public surface (`TSCastPredictor(checkpoint=None, data=None, clim=None)`, `.reconstruct(lat, lon, date, argo_check=None)`, `.seafloor_depth_m(lat, lon)`) — nothing imports this class today (grep: the only hit is its own definition), but the schema doc and the panels assume that shape.

**3a. Module-level helpers** — add above the class:

```python
def decoder_from_checkpoint(ck: dict) -> tuple[str, str]:
    """Which decoder this checkpoint IS. Read, never defaulted."""
    if ck.get("decoder") in ("film", "simple"):
        return ck["decoder"], "the checkpoint records it"
    sd = ck["state_dict"]
    if any(k.startswith("simple_head.") for k in sd):
        return "simple", "read off the state_dict: it names simple_head.*"
    if any(k.startswith("decoder.") for k in sd):
        return "film", "read off the state_dict: it names decoder.*"
    raise ValueError(
        "this checkpoint names neither simple_head.* nor decoder.*, so it is not a TSCastNIO. "
        "Refusing to construct a network and load weights into it by luck.")


def data_kind_from_checkpoint(ck: dict) -> tuple[str, str]:
    """'monthly' or 'daily'. Refuses when the file genuinely does not say."""
    if ck.get("data") in ("monthly", "daily"):
        return ck["data"], "the checkpoint records it"
    if int(ck["T_SEQ"]) > 1:
        return "daily", (f"inferred from T_SEQ={int(ck['T_SEQ'])}: train_stage1.py refuses "
                         "--t-seq > 1 unless --data daily, so a window longer than one step "
                         "can only have come from the daily bundle")
    raise ValueError(
        "this checkpoint predates the `data` key and has T_SEQ=1, which BOTH loaders can "
        "produce. Monthly and daily share the same 5 channel names, so nothing downstream "
        "would catch the wrong one -- it would just return wrong temperatures. Pass "
        "data=D.load_daily() or data=D.load_monthly() explicitly, or retrain so the "
        "checkpoint says which it was.")


def cadence_days(times) -> float:
    """Median gap between consecutive steps. MEASURED: monthly 31.0 (28..31), daily 1.0."""
    t = np.sort(np.asarray(times, dtype="datetime64[D]").astype("int64"))
    return float(np.median(np.diff(t))) if len(t) > 1 else float("nan")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
```

**3b. `__init__` — build what the checkpoint names, load what it says, refuse on mismatch.** Order matters: resolve the decoder and the data kind *before* loading data, so a refusal costs no I/O.

```python
    def __init__(self, checkpoint=None, data=None, clim=None, argo_table=None):
        path = checkpoint or base.art("tscast_stage1.pt")
        if not os.path.exists(path): ...          # keep the existing FileNotFoundError verbatim
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.meta = {k: v for k, v in ck.items() if k != "state_dict"}

        decoder, dec_why = decoder_from_checkpoint(ck)
        kind, kind_why = data_kind_from_checkpoint(ck)
        self.decoder_name, self.data_kind = decoder, kind
        self.checkpoint_path, self.checkpoint_sha256 = path, sha256_of(path)

        if data is None:
            data = D.load_daily() if kind == "daily" else D.load_monthly()
        self.data = data

        # GUARD 1: cadence. The 5 channel names are IDENTICAL in both archives, so the channel
        # check below cannot see a monthly/daily swap. Cadence can.
        found = cadence_days(self.data["times"])
        want = 1.0 if kind == "daily" else 31.0
        if abs(found - want) > 0.5:
            t = np.asarray(self.data["times"], dtype="datetime64[D]")
            raise ValueError(
                f"checkpoint {os.path.basename(path)} was trained on {kind!r} data "
                f"({kind_why}), which has a median cadence of {want:.0f} d. The loaded grid has "
                f"a median cadence of {found:.0f} d, {len(t)} steps spanning {t.min()}..{t.max()}. "
                f"Found {found:.0f} d, expected {want:.0f} d. Predicting across that mismatch "
                f"would feed a daily-trained encoder a window measured in months and label the "
                f"answer a day.")

        # GUARD 2: channels, unchanged in spirit -- keep the existing message.
        if [str(c) for c in self.data["channels"]] != [str(c) for c in ck["channels"]]:
            raise ValueError(...)   # existing text

        self.clim = clim if clim is not None else np.load(base.art("climatology.npy"))

        model_t_seq = int(ck.get("model_t_seq", 1))
        self.model_t_seq_source = ("the checkpoint records it" if "model_t_seq" in ck else
                                   "ASSUMED 1: this checkpoint predates the key, and the trainer "
                                   "that wrote it hardcoded t_seq=1 into the model")
        self.model = TSCastNIO(ck["encoder"], len(ck["channels"]), t_seq=model_t_seq,
                               p=ck["P"], latent=ck["latent"], residual=ck["residual"],
                               unet_channels=tuple(ck["unet_channels"]), decoder=decoder)
        self.model.load_state_dict(ck["state_dict"])   # strict=True. A silent partial load is worse.
        self.model.eval()
        ...  # norm / GriddedPatches unchanged, EXCEPT t_seq=int(ck["T_SEQ"]) for the SAMPLER
```

**Edge cases you must not smooth over:**

- `load_state_dict` stays **strict**. Passing `strict=False` to "make it work" would load a half-initialised network and return numbers. Never do this.
- The sampler gets `t_seq=ck["T_SEQ"]` (31 — the window to cut); the model gets `model_t_seq` (1 — how it was built). These are different arguments to different objects. Getting them the same way round is the whole point of D-P3-2.
- `unet_channels` must be passed through. The default `config.UNET_CHANNELS` happens to equal the shipped `[32, 64, 128]`, so a `film` checkpoint trained with `--unet-width 64 128 256` would load into a differently-shaped decoder and raise a *size mismatch* rather than a missing key — a different error for the same class of bug.
- `GriddedPatches` is constructed with `max_samples=1`, which randomly subsamples the index; `reconstruct` overwrites `self.ds.index` anyway. Leave it — it is cheap and it keeps construction bounded.
- Land: `cell_index` snaps to the nearest centre and does not check the land mask. A query on land returns a profile with `valid` all-False and 15 sea-floor reasons — correct behaviour, and the reason strings say why.

**3c. Add a CLI**, because Phase 3 must end in something a human can run. At the bottom of `inference.py`:

```python
if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Reconstruct one profile from the stage-1 checkpoint.")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--no-argo", action="store_true", help="skip the ground-truth check")
    a = ap.parse_args()
    p = TSCastPredictor(checkpoint=a.checkpoint)
    print(json.dumps(p.reconstruct(a.lat, a.lon, a.date, attach_argo=not a.no_argo), indent=1))
```

**Verification command and expected output [VERIFIED — reproduced end to end on this machine]:**

```bash
PYTHONPATH=src python -m phase2.tscast_nio.inference --lat 15.0 --lon 65.0 --date 2026-05-15
```

```
temperature : [31.05, 30.91, 30.93, 30.80, 30.31, 28.41, 26.47, 25.08, 23.28, 21.22,
               17.87, 14.56, 12.41, 11.27, 8.97]
sigma_t     : [0.37, 0.35, 0.34, 0.43, 0.61, 1.05, 1.05, 0.90, 0.94, 1.07,
               0.89, 0.65, 0.44, 0.45, 0.46]
seafloor_depth_m : 1000.0        forecast : False        input_date : 2026-05-15
reasons[0]  : "0.37 degC error bar at 0 m -- measured 0.40 degC error against independent floats"
reasons[8]  : "0.94 degC error bar at 125 m -- the weakest depth we have, measured 1.34 degC
               error against independent floats"
argo_check  : argo@15.354,64.666@2026-05-12  LOW
              "53 km and 3 days away - far enough that the ocean may have moved between the two"
```

The checkpoint sha256 begins `aac39bc4b7384f38`. **If your 0 m temperature is not 31.05, you did not build the encoder the way training built it** — check `model_t_seq`, not your floating-point luck. This forward pass is deterministic on CPU; treat any deviation above 0.01 degC as a construction bug.

---

### 3.4 Step 4 — `argo_check` through the real F1 engine

The schema is explicit: *"Collocation reuses `src/phase2/data/collocation.py` (F1, VALIDATED). We do not write a second matcher — two matchers that can disagree is the D-014 failure repeating."* So do not write a nearest-neighbour loop in `inference.py`.

Two **additive, backward-compatible** changes to `src/phase2/data/collocation.py` (Unit B's file — you are on Darshan's machine, so this is yours to edit; both changes keep every existing call and every test in `tests/phase2/test_collocation.py` behaving identically):

```python
    def __init__(self, tolerance_days: float = DEFAULT_TOLERANCE_D,
                 spatial_method: str = "nearest",
                 argo_table: "str | pd.DataFrame | None" = None):
        ...
        self._argo_source = argo_table          # None -> artifacts/argo_test (unchanged default)

    def _argo_table(self):
        if self._argo is None:
            if isinstance(self._argo_source, pd.DataFrame):
                df = self._argo_source.copy()
            else:
                src = self._argo_source or config.art("argo_test")
                try:
                    df = io.load_table(src)
                except Exception:
                    self._argo = pd.DataFrame(); return None
            df["date"] = pd.to_datetime(df["date"])
            self._argo = df
        return None if self._argo.empty else self._argo

    def match_argo(self, latitude: float, longitude: float, datetime) -> dict | None:
        """Public: nearest independent Argo profile in space AND time, or None.

        Public because the predictor needs the Argo match WITHOUT the GLORYS half of a full
        collocate() -- grids.npz is monthly 2019-2022 and has nothing to say about a 2026 date.
        """
        return self._match_argo(float(latitude), float(longitude), pd.Timestamp(datetime))
```

**`_match_argo` returns exactly these keys [VERIFIED by calling it]:** `latitude`, `longitude`, `datetime` (str, `YYYY-MM-DD`), `temperature_profile` (list of 15, `None` where the float did not sample), `spatial_offset_km` (float), `temporal_offset_days` (**signed** float), `n_levels` (int), `note`. There is **no** `profile_id` and no float WMO number.

**3d. The predictor's Argo path:**

```python
ARGO_TABLE_FOR = {"daily": "argo_daily_period", "monthly": "argo_test"}

    def _make_engine(self, argo_table):
        src = argo_table or base.art(ARGO_TABLE_FOR[self.data_kind])
        eng = CollocationEngine(tolerance_days=10.0, argo_table=src)
        df = eng._argo_table()
        if df is None:
            raise FileNotFoundError(f"no Argo table at {src}. argo_check is part of the record, "
                                    "not an optional extra -- refusing to build records that can "
                                    "never carry a ground-truth check.")
        # REFUSE a table that cannot overlap the data. This is the trainer's own D-014 guard.
        a0, a1 = df["date"].min(), df["date"].max()
        t = np.asarray(self.data["times"], dtype="datetime64[D]")
        if a1 < pd.Timestamp(str(t.min())) or a0 > pd.Timestamp(str(t.max())):
            raise ValueError(
                f"the Argo table {src} spans {a0.date()}..{a1.date()} and the {self.data_kind} "
                f"grid spans {t.min()}..{t.max()}. Found no overlap; expected overlap. Every "
                f"argo_check would come back None and the UI would read that as 'no float "
                f"nearby' rather than 'wrong file'.")
        return eng

    def _argo_check(self, lat, lon, date, temperature):
        m = self.engine.match_argo(lat, lon, date)
        if m is None:
            return None
        pid = f"argo@{m['latitude']:.3f},{m['longitude']:.3f}@{m['datetime']}"
        return output.build_argo_check(
            m["temperature_profile"], temperature, pid,
            m["spatial_offset_km"], abs(int(round(m["temporal_offset_days"]))),
            source="argopy")
```

**Measured on the reference query (15.0 N, 65.0 E, 2026-05-15):** nearest float at 15.3536 N, 64.6661 E on 2026-05-12, `spatial_offset_km = 53.197`, `temporal_offset_days = -3.0`, `n_levels = 14`. `difference[0]` is `None` because the float did not sample 0 m — the schema's per-depth-`None` rule, working.

#### DECISION D-P3-3 — `abs()` on the day offset

`temporal_offset_days` is **signed** (`-3.0` in the reference query, verified) and `output.build_argo_check` compares it raw: `if distance_km <= 25 and days_offset <= 3`. A float 12 km away and **30 days early** (`-30`) would be labelled `HIGH`. On this particular query the label lands on `LOW` either way, so the bug is currently latent — which is exactly why it must be closed now.

**Recommended:** pass `abs(...)` at the call site **and** make `build_argo_check` refuse a negative: a negative offset means the caller lost the sign convention, and silently `abs()`-ing it inside would hide that.

```python
    if days_offset < 0:
        raise ValueError(f"days_offset={days_offset} is signed; pass the ABSOLUTE offset. "
                         "A negative offset compares as 'close' in every band below and would "
                         "label a month-old float HIGH.")
```

#### DECISION D-P3-4 — `profile_id` when the data has no float id

`argo_daily_period.parquet` columns are `lat, lon, date, depth_idx, temp` [VERIFIED]. There is no WMO number to put in `profile_id`.

**Recommended:** a deterministic composite key, `argo@{lat:.3f},{lon:.3f}@{YYYY-MM-DD}`, and a one-line comment in `inference.py` stating it is **not** a WMO float id so nothing downstream cites it as one. The alternative — re-fetching float ids from argopy — is a data-pipeline task, not an inference fix, and should not block Phase 3.

#### DECISION D-P3-5 — do not copy F1's `record.quality` into `argo_check["quality"]`

`Collocation.quality` scores the **GLORYS grid** match: for any 2026 date it flags `TEMPORAL_OFFSET_EXCEEDS_TOLERANCE` against the monthly `grids.npz` and reads `REJECT`. The schema's `argo_check.quality` is about the **Argo** match. Using `match_argo` instead of `collocate` avoids the temptation entirely; `output.build_argo_check` computes the band from the Argo offsets, and that is the only quality that belongs in this field.

---

### 3.5 Step 5 — Every field of the output record, and where its value comes from

Built by `output.build_record(...)`, which is already correct and needs only the two additions in D-P3-6. Field by field against `docs/phase2/tscast_output_schema.md`:

| field | source | notes |
|---|---|---|
| `depths_m` | `config.DEPTHS` | frozen 15 levels, never a subset |
| `temperature` | `mu * y_std + y_mean`, `y_*` from `ck["norm"][2:4]` | `None` where `valid` is False, set by `build_record` |
| `log_var_t` | `logvar + 2*log(y_std)` | z-space log-var carried back to degC²; the `2*log` is the variance scaling, not a fudge |
| `sigma_t` | `sqrt(exp(log_var_t))` inside `build_record` | this is what the UI shows |
| `valid` | `np.isfinite(self.data["temp"][t_idx, i, j, :])` | GLORYS truth at the matched step. For a forecast date `t_idx` is the clamped last step — acceptable: bathymetry does not move |
| `seafloor_depth_m` | `seafloor_depth_m()`: deepest level finite in **any** time step at that cell | unchanged |
| `salinity`, `log_var_s`, `density`, `log_var_rho` | literal `None` | stage 2 is a fill-in, not a migration |
| `reasons` | `build_reasons(sigma, valid, floor)` → `measured_rmse_by_depth()` | see below |
| `argo_check` | `_argo_check(...)` via F1, or `None` | `None` **only** when no float is in the window |
| `forecast` | `target > LAST_GLORYS` | see below |
| `forecast_note` | set by `build_record` when `forecast` | must name the input lag, see D-P3-6 |
| `provenance` | assembled in `reconstruct` | see below |

**`reasons` — generated from measured quantities, never a restatement.** `measured_rmse_by_depth()` reads `artifacts/tscast_stage1_metrics.json` → `metrics.rmse`, 15 values [VERIFIED present]. Measured: worst depth **125 m at 1.34 degC**, best **1000 m at 0.24 degC**. So `_depth_context` names 125 m "the weakest depth we have" and 1000 m "our most accurate depth" *because the file says so*, and if the artifact is deleted every reason degrades to "per-depth error has not been measured for this model yet" rather than inventing a confidence. Nothing to build here — but note the coupling: **if you retrain, `tscast_stage1_metrics.json` is overwritten and every reason string changes with it.** That is correct behaviour and the tests must not pin absolute numbers.

**`forecast` — verified truth-end dates.** `LAST_GLORYS = 2026-06-23` matches the daily bundle's last step exactly [VERIFIED]. `LAST_ARGO = 2026-08-24` is stale: `artifacts/argo_2026.parquet` measured today runs to **2026-08-29**.

#### DECISION D-P3-6 — what `forecast` must say

Two problems with the current handling.

1. `LAST_ARGO` is a literal that drifts every time Argo is re-fetched, and it is not referenced anywhere in `inference.py`. **Recommended:** derive it at load time from the Argo table actually in use (`self.last_argo = df["date"].max()`), keep the module constant only as a documented fallback, and correct the `2026-08-24` in `tscast_output_schema.md` §4 to say the limit is **measured from the artifact**, not frozen. Do not silently edit the doc's number — state that it was re-measured and on what date.

2. **A "forecast" past 2026-06-23 is not an extrapolation.** `_time()` clamps to the nearest available step, so a 2026-07-15 request is the model applied to the **2026-06-23** surface field, 22 days stale. Labelling that `FORECAST` without saying so implies the model projected forward. It did not. Schema §4 also forbids attaching any RMSE to a forecast — yet `build_reasons` would happily quote "measured 1.34 degC error against independent floats" on it.

**Recommended:** make both facts structural rather than trusting the caller.

```python
# output.py
def build_reasons(sigma, valid, seafloor_depth_m, rmse=None, forecast: bool = False) -> list[str]:
    ...
    if forecast:
        line += ("; this date is past the last observed field, so no independent float can "
                 "check it and the error bar is the model's own estimate, unverified here")
```

```python
# output.py -- build_record
def build_record(..., forecast=False, forecast_input_lag_days: int | None = None, ...):
    if forecast and forecast_input_lag_days is None:
        raise ValueError("a forecast record must state how stale its input field is. The model "
                         "was applied to the last observed surface field; it did not extrapolate, "
                         "and a FORECAST label without that number overstates what happened.")
```
and append to `forecast_note`: `f" The surface input is {forecast_input_lag_days} days older than the requested date."`

Both defaults are backward compatible — every existing test in `tests/phase2/test_tscast_output.py` passes unchanged except `test_a_forecast_cannot_carry_a_ground_truth_check` and `test_forecast_records_label_themselves`, which must be given `forecast_input_lag_days=0`. **Do not weaken the new guard to keep those two tests green; update the tests.**

**`provenance` — every field of schema §5, plus what makes the fix auditable:**

```python
prov = {
    "model": "tscast-nio-stage1",
    "checkpoint": os.path.basename(self.checkpoint_path),
    "checkpoint_sha256": self.checkpoint_sha256,        # §5 -- was MISSING
    "seed": self.meta.get("seed"),
    "T_SEQ": int(self.meta["T_SEQ"]),                   # data window the sampler cut
    "model_t_seq": self.model_t_seq,                    # what the network was built with
    "model_t_seq_source": self.model_t_seq_source,
    "P": int(self.meta["P"]),
    "encoder": self.meta.get("encoder"),
    "decoder": self.decoder_name,
    "decoder_source": dec_why,                          # "the checkpoint records it" | "read off the state_dict..."
    "loss": self.meta.get("loss"), "beta": self.meta.get("beta"),
    "residual": self.meta.get("residual"),
    "data": self.data_kind, "data_source": kind_why,
    "input_source": "glorys",                           # VERIFIED: daily_pipeline says
                                                        # "GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D-m)"
    "input_date": str(np.asarray(self.data["times"])[t_idx]),
    "requested_date": str(target),
    "days_from_requested": days_off,
    "grid_cell": {"lat": float(base.LAT[i]), "lon": float(base.LON[j])},
    "clim_artifact": self.meta.get("clim_artifact", "climatology.npy"),
    "clim_train_years": self.clim_train_years,          # from clim_daily.npz, see 2d
    "clim_train_years_source": self.clim_years_source,
    "argo_table": os.path.basename(self.argo_table_path),
    "code_commit": _git_short_head(),                   # the code that ran INFERENCE
    "train_commit": self.meta.get("code_commit"),       # the code that produced the weights
}
```

`clim_train_years` is `[2019, 2020, 2021]` [VERIFIED from `artifacts/clim_daily.npz`], and its `provenance` string in that file already documents the disjointness argument (2019–2021 prior applied to a 2025–2026 period). Keep loading the array from `artifacts/climatology.npy` — that is exactly what `train_stage1.py` line 141 loads. Read only the *metadata* from `clim_daily.npz`; do not swap the array source.

`code_commit` and `train_commit` are **not** the same thing and the schema's single `code_commit` field is ambiguous about which it means. Carrying both, named, removes the ambiguity; note the addition in the schema doc.

---

### 3.6 Step 6 — Tests

New file: **`tests/phase2/test_tscast_inference.py`**. Follow the house conventions in `tests/phase2/test_tscast_model.py` (module-level `_model()` helper, `config.N_DEPTHS`) and `test_collocation.py` (`pytestmark = pytest.mark.skipif(...)` when the test needs real data on disk). `pyproject.toml` sets `pythonpath = ["src"]`, so plain `pytest` works.

Gate the artifact-dependent tests, not the logic tests:

```python
HAVE_CK = os.path.exists(base.art("tscast_stage1.pt"))
HAVE_DAILY = bool(glob.glob(os.path.join(base.DATA_PROCESSED, "daily", "*.npz")))
needs_real = pytest.mark.skipif(not (HAVE_CK and HAVE_DAILY),
                                reason="needs artifacts/tscast_stage1.pt + the daily bundle")
```

Build fake checkpoints through the **real** trainer function so the round trip is genuine:

```python
def _tiny_checkpoint(tmp_path, decoder, data="daily", t_seq=31, model_t_seq=1):
    m = TSCastNIO("cnn3d", 5, t_seq=model_t_seq, p=config.P, latent=16,
                  residual=True, unet_channels=(8, 16), decoder=decoder)
    norm = [np.zeros(5, "float32"), np.ones(5, "float32"),
            np.zeros(config.N_DEPTHS, "float32"), np.ones(config.N_DEPTHS, "float32")]
    payload = T1.checkpoint_payload(
        m, encoder="cnn3d", decoder=decoder, loss="nll", beta=0.5, data=data, residual=True,
        channels=["sst", "sss", "ssh", "u", "v"], p=config.P, t_seq=t_seq,
        model_t_seq=model_t_seq, latent=16, unet_channels=(8, 16), norm=norm,
        epochs=1, lr=1e-3, batch_size=8, code_commit="deadbee",
        clim_artifact="climatology.npy", clim_train_years=[2019, 2020, 2021])
    p = tmp_path / f"{decoder}.pt"; torch.save(payload, p); return str(p)
```

| test name | asserts |
|---|---|
| `test_the_shipped_checkpoint_loads_without_a_missing_key_error` | `TSCastPredictor()` constructs. The literal regression: it raised `RuntimeError: Missing key(s) ... decoder.stem...` before this phase. `@needs_real`. |
| `test_decoder_is_read_from_the_state_dict_not_defaulted` | `decoder_from_checkpoint({"state_dict": {"simple_head.0.weight": ...}})` → `("simple", ...)`; a dict with `decoder.stem...` → `("film", ...)`; a dict with neither raises `ValueError`. |
| `test_the_checkpoint_records_the_decoder_it_was_trained_with` | `checkpoint_payload(...)` output contains every name in `CHECKPOINT_KEYS`, and `payload["decoder"] == "simple"` when told `"simple"`. Guards regression (2). |
| `test_predictor_rebuilds_the_decoder_the_checkpoint_names` | **Round trip, both directions.** For `decoder in ("film","simple")`: save via `_tiny_checkpoint`, construct `TSCastPredictor(checkpoint=..., data=<fixture grid>, clim=<zeros>)`, assert `p.model.decoder_name == decoder`, and assert `(p.model.decoder is None) == (decoder == "simple")`. |
| `test_an_explicit_decoder_key_beats_the_state_dict_read` | payload with `decoder="simple"` resolves `("simple", "the checkpoint records it")` — the recorded value is preferred, and the *why* string says which route ran. |
| `test_t_seq_above_one_resolves_to_daily_because_the_trainer_forbids_otherwise` | `data_kind_from_checkpoint({"T_SEQ": 31})` → `("daily", ...)`, and the reason mentions `--t-seq`. |
| `test_a_t_seq_one_checkpoint_without_a_data_key_is_refused_not_guessed` | **Refusal test.** `pytest.raises(ValueError, match="BOTH loaders")` — the ambiguous case is never defaulted. |
| `test_monthly_data_under_a_daily_checkpoint_is_refused_naming_found_and_expected` | **Refusal test.** `TSCastPredictor(checkpoint=<daily>, data=D.load_monthly())` raises `ValueError`; message contains `"Found 31"` and `"expected 1"`. Proves the guard the channel check cannot make. `@needs_real`. |
| `test_channel_mismatch_is_still_refused` | existing guard intact: a 4-channel data dict raises with `"Channel order is frozen"`. |
| `test_model_t_seq_is_used_for_the_build_and_T_SEQ_for_the_sampler` | `p.model_t_seq == 1` while `p.ds.T_SEQ == 31` for the shipped checkpoint. This is the 0.0695 degC bug, pinned. `@needs_real`. |
| `test_record_satisfies_every_key_of_the_output_schema` | the returned dict has all of `depths_m, temperature, log_var_t, sigma_t, valid, seafloor_depth_m, salinity, log_var_s, density, log_var_rho, reasons, argo_check, forecast, forecast_note, provenance`; all 15-length lists are 15 long. `@needs_real`. |
| `test_provenance_carries_every_field_the_schema_names` | `checkpoint_sha256` is 64 hex chars, `clim_train_years == [2019,2020,2021]`, `input_source == "glorys"`, `encoder`, `seed`, `T_SEQ`, `P`, `input_date`, `code_commit` all present and not `None`. `@needs_real`. |
| `test_a_forecast_carries_no_argo_check_and_its_reason_says_so` | date `2026-08-01` → `forecast is True`, `argo_check is None`, `"FORECAST"` in `forecast_note`, and every valid depth's reason contains `"no independent float can check it"`. `@needs_real`. |
| `test_a_forecast_states_how_stale_its_input_field_is` | `provenance["days_from_requested"] > 0` and that same number appears in `forecast_note`. D-P3-6. `@needs_real`. |
| `test_argo_check_comes_from_the_f1_engine_not_a_second_matcher` | monkeypatch `CollocationEngine.match_argo` to return a known dict; assert the record's `distance_km`/`days_offset` are exactly those values. If the predictor ever grows its own matcher this fails. |
| `test_an_argo_table_that_cannot_overlap_the_data_is_refused` | **Refusal test.** daily checkpoint + `argo_table=base.art("argo_test")` (2022) raises `ValueError` matching `"no overlap"`. Without this, every `argo_check` is silently `None`. `@needs_real`. |
| `test_the_days_offset_handed_to_build_argo_check_is_absolute` | with a signed `temporal_offset_days = -30` and `spatial_offset_km = 12`, the resulting quality is **not** `HIGH`. |

Add to **`tests/phase2/test_tscast_output.py`**:

| test name | asserts |
|---|---|
| `test_a_negative_days_offset_is_refused_not_silently_absolved` | `pytest.raises(ValueError, match="ABSOLUTE")` from `build_argo_check(..., days_offset=-3)`. |
| `test_a_forecast_record_must_state_its_input_lag` | `pytest.raises(ValueError, match="how stale")` when `forecast=True` and `forecast_input_lag_days=None`. |
| `test_forecast_reasons_say_no_float_can_check_this` | `build_reasons(..., forecast=True)` — every valid depth mentions the missing check, and **no** reason claims an accuracy figure for the date (schema §4). |

Update `test_a_forecast_cannot_carry_a_ground_truth_check` and `test_forecast_records_label_themselves` to pass `forecast_input_lag_days=0`.

**Commands and expected output:**

```bash
python -m pytest tests/phase2/test_tscast_output.py tests/phase2/test_tscast_train.py -q
# BASELINE TODAY [VERIFIED]: 18 passed in 6.25s -- must still pass after your edits

python -m pytest tests/phase2/test_tscast_inference.py tests/phase2/test_tscast_output.py \
                tests/phase2/test_tscast_model.py tests/phase2/test_collocation.py -q
```

If a test skips, say so in `HANDOFF.md` with the reason. A skipped test is not a passing test.

---

### 3.7 DONE checklist

- [ ] The reproduction in 3.1 was run **before** any edit and its `RuntimeError` is pasted into `docs/HANDOFF.md`.
- [ ] `train_stage1.py`: `checkpoint_payload()` + `CHECKPOINT_KEYS` exist; `decoder`, `loss`, `beta`, `data`, `model_t_seq`, `code_commit`, `clim_artifact`, `clim_train_years` are saved; the stale `"trained_on": "monthly archive..."` string is gone.
- [ ] `inference.py`: `decoder_from_checkpoint`, `data_kind_from_checkpoint`, `cadence_days`, `sha256_of` exist; the model is built with `decoder=`, `unet_channels=`, `t_seq=model_t_seq`; `load_state_dict` is still **strict**.
- [ ] Both refusals fire and name found-vs-expected: cadence mismatch, and the ambiguous `T_SEQ=1` + no `data` key.
- [ ] `collocation.py`: `argo_table` constructor arg and public `match_argo` added; **existing default behaviour unchanged** — `pytest tests/phase2/test_collocation.py -q` still passes.
- [ ] `output.py`: `build_argo_check` refuses a negative `days_offset`; `build_reasons(..., forecast=)` and `build_record(..., forecast_input_lag_days=)` implemented.
- [ ] `python -m phase2.tscast_nio.inference --lat 15.0 --lon 65.0 --date 2026-05-15` runs and reproduces the 3.3 numbers; the real output is pasted into `HANDOFF.md`.
- [ ] A forecast date (e.g. `--date 2026-08-01`) returns `forecast: True`, `argo_check: null`, and a `forecast_note` naming the input lag in days.
- [ ] Every test in 3.6 exists, is named as listed, and passes (or is skipped with a stated reason).
- [ ] `docs/phase2/tscast_output_schema.md` updated for: `train_commit` alongside `code_commit`, `forecast_input_lag_days`, and the re-measured raw-Argo limit (2026-08-29, not 2026-08-24) with the measurement date stated.
- [ ] `docs/DECISIONS.md` (or `HANDOFF.md`) records D-P3-1 … D-P3-6 with the measured evidence: 0.0695 degC for the `t_seq` divergence, identical channel lists for the cadence guard, 2022-only `argo_test` for the table swap.
- [ ] `docs/HANDOFF.md` appended; committed on `phase2-tscast-nio` with the real command output in the message body.
- [ ] **Not done in this phase, filed for the next one:** whether the encoder should be built with `t_seq=31` rather than `1`. That changes what the network computes and would invalidate the 0.9267 degC Argo result. It needs a retrain and a re-validation, not a one-line edit.

## Phase 4 — the final stage-1 retrain

### 4.1 The command

The picker prints it, minus the interpreter (it strips `cmd[0:2]`). Run it *through* the picker so the selection and the run land in one auditable transcript:

```powershell
cd <repo root>
$env:PYTHONPATH='src'; $env:PYTHONUNBUFFERED='1'
"===== FINAL RETRAIN =====" | Tee-Object -FilePath final_retrain.log
.venv\Scripts\python.exe scripts\phase2\pick_tseq_and_retrain.py `
    --log tseq_ablation.log `
    --recorded "1=0.9096,11=0.8529" `
    --recorded-source "docs/phase2/AGENT_SYNC.md 2026-08-29 section 5" `
  | Tee-Object -FilePath final_retrain.log -Append
```

Equivalent by hand, if you would rather not re-run the picker (identical flags, verified against the printed line):

```powershell
.venv\Scripts\python.exe -m phase2.tscast_nio.train.train_stage1 `
    --data daily --t-seq 11 --decoder simple --loss nll `
    --epochs 25 --train-samples 60000 --test-samples 12000 --patience 5 `
  | Tee-Object -FilePath final_retrain.log -Append
```

**Before you press enter:** back up the previous pair (2.2), confirm `git status` is clean, and do not commit while it runs.

### 4.2 Expected wall-clock — and the honest spread

Two independent cost sources, and they disagree by 1.7x. Both are reported rather than one being quietly picked:

- **Measured, from the completed T_SEQ=31 run's own JSON:** `train_seconds 8037.1 / 8 epochs = 1004.6 s per epoch` at 40k train + 12k held-out on CPU. [VERIFIED]
- **`pick_tseq_and_retrain.py` docstring, Arjhun's measurement:** 1.8 / 8.4 / 24.9 min per 100k-sample epoch at T_SEQ = 1 / 11 / 31. That makes 40k at T=31 ≈ 10 min/epoch, against the 16.7 min actually recorded. The gap is probably the per-epoch 12k held-out pass plus machine load, but that is [INFERRED] — I did not re-time it.

Estimates for the final run (T=11, 60k train + 12k test), both shown:

| basis | s/epoch | 25 epochs | realistic (patience 5; the T=11 leg's best epoch was 2) |
|---|---|---|---|
| scaled from the measured T=31 run (×0.337 per sample, ×1.5 samples) | ~508 s | ~3.5 h | ~1.0–1.7 h (stop at epoch 7–12) |
| docstring table (8.4 min/100k → 60k) | ~300 s | ~2.1 h | ~0.6–1.0 h |

**Budget 1–3.5 h, then replace the estimate with a measurement:** when epoch 1 prints, multiply by 25. If that exceeds your window, kill it and relaunch with fewer `--train-samples` — and record the change, because it moves the run away from the 60k the selection rule assumed.

Two hardware notes:

- `--device auto` takes CUDA if present. A GPU changes all the numbers above; re-time epoch 1 rather than assuming a speedup.
- **Do not raise `--num-workers` on Windows without checking RAM.** Workers are spawned and pickle the dataset: the NaN-padded daily surface array is 388×116×256×5×4 B ≈ 230 MB and `temp` is 388×100×240×15×4 B ≈ 558 MB, so roughly 0.8 GB per worker. [INFERRED from the array shapes in `dataset.py`; I did not run a multi-worker job.]

### 4.3 DECISION — 5 channels or 7 for the final run

Facts: the daily bundle on disk carries **5 channels** (`sst, sss, ssh, u, v`) [VERIFIED]; `config.CHANNELS` declares 7 (`+wu, wv`); PS requirement 8 (wind) is at 0%; AGENT_SYNC 2026-08-30 §5 hands Darshan the authority to ship on 5 and says "the final retrain is where wind enters".

**Recommendation: run the 5-channel final retrain first, unconditionally.** Then, only if the wind bundle exists and time remains, run a **second** final retrain at the same `--t-seq`, same samples, same epochs, on the 7-channel bundle, and report both. Reasons:

1. A download must never decide whether you have a result. The 5-channel run is guaranteed to finish.
2. It keeps the final model on the same input set as the ablation that chose its window.
3. Running 7 channels as a *second* run with only the channel set changed makes it a clean single-variable ablation — the exact discipline this project lost when the decoder and the loss moved together.

If you do run 7 channels, three things must hold or the run is void:

- The bundle's `channels` list must be in `config.CHANNELS` order. Nothing in the trainer checks this — it only takes `len(d["channels"])`. Add the guard:
  ```python
  if list(map(str, d["channels"])) != config.CHANNELS[:len(d["channels"])]:
      raise SystemExit(f"channel order {list(d['channels'])} disagrees with the frozen contract "
                       f"{config.CHANNELS}; refusing to train on silently permuted inputs")
  ```
- Normalisation statistics change, so the 7-channel checkpoint is not interchangeable with the 5-channel one. `inference.py` lines 44–48 already refuse a channel mismatch — that refusal is correct; do not weaken it.
- The 7-channel RMSE **cannot** be compared to the ablation legs. It is a channel comparison against the 5-channel final run only.

### 4.4 Making the result survive — fix three provenance defects first

`artifacts/tscast_stage1.pt` and `artifacts/tscast_stage1_metrics.json` are gitignored (`/artifacts/*`, `*.pt`), so nothing you produce reaches anyone else by default. Worse, three fields the trainer writes are wrong for a daily run — visible in the current file [VERIFIED]:

1. `"trained_on": "monthly archive, T_SEQ=1 (the daily bundle had not landed)"` — a hardcoded string (line 298) that the current `data=daily, T_SEQ=31` JSON still carries. Replace with a computed value:
   ```python
   "trained_on": (f"{a.data} bundle, T_SEQ={t_seq}, {len(d['times'])} steps, "
                  f"{len(d['channels'])} channels"),
   ```
2. `"train_years": [2019,2020,2021], "test_years": [2022]` (line 312) — those are `base.TRAIN_YEARS/TEST_YEARS`, the *monthly* split. The daily split is `2025-06-01..2026-03-31` / `2026-04-01..2026-06-23` (`dataset.DAILY_TRAIN/DAILY_TEST`). Anyone reading the JSON would conclude the daily model was trained on 2019–2021. Fix:
   ```python
   **({"train_window": [str(D.DAILY_TRAIN[0]), str(D.DAILY_TRAIN[1])],
       "test_window":  [str(D.DAILY_TEST[0]),  str(D.DAILY_TEST[1])]}
      if a.data == "daily" else
      {"train_years": list(base.TRAIN_YEARS), "test_years": list(base.TEST_YEARS)}),
   ```
3. `"decoder"` is written to the metrics JSON but **not to the checkpoint** — which is why `TSCastPredictor` currently raises `RuntimeError: Missing key(s) decoder.*` on the shipped `simple` checkpoint (AGENT_SYNC 2026-08-30 §4). Add it in the same edit as 2.6.

Preserve the rest of the JSON shape exactly. Downstream code and the UI read `metrics.overall.{rmse,bias,correlation,skill_rmse_ratio,skill_vs_climatology,n}`, `metrics.{depths_m,rmse,correlation,bias,skill_rmse_ratio,rmse_climatology,n}`, `calibration.<depth>.{n,rmse,sigma,ratio}`, `argo_profiles`, `training_curve`, `best_epoch`, `checkpoint`, `code_commit`. Add fields; do not rename or drop any.

Then make it durable, in this order:

1. `Copy-Item` both files to `*_tseq11_final.*` (2.2).
2. **Force-add the JSON only** — 8 KB, machine-written, and the only structured provenance that exists:
   ```powershell
   git add -f artifacts\tscast_stage1_metrics_tseq11_final.json artifacts\tscast_stage1_metrics_tseq31.json
   ```
   Leave the 2.2 MB `.pt` out; `*.pt` is ignored deliberately.
3. Append one row to `docs/EXPERIMENT_LOG.md` in its existing template (it has **zero** v2 entries). Tag it `[DARSHAN, acting for Unit C during the 2026-08-30/31 handover]` — the file is Unit C's, and the handover is the authority:
   ```
   ## tscast-stage1-final 2026-08-31 HH:MM   [DARSHAN, acting for Unit C during the handover]
   model: TSCastNIO(cnn3d, decoder=simple, loss=nll beta=0.5, latent=128, residual=<flag>) | dataset: daily bundle 388 steps, 5 channels (no wind) | split: train 2025-06-01..2026-03-31 / test 2026-04-01..2026-06-23 | seed: 42 | hyperparams: T_SEQ=11 P=17 lr=1e-3 bs=256 wd=1e-2 epochs=25 patience=5 train_samples=60000 | hardware: <cpu/gpu> | git-commit: <short sha>
   metrics: Argo RMSE=<..> corr=<per-depth mean> bias=<..> skill_rmse_ratio=<..> | n_profiles=<..> | calibration ratio <min>-<max> | checkpoint: artifacts/tscast_stage1.pt (local only, gitignored)
   notes: T_SEQ chosen by scripts/phase2/pick_tseq_and_retrain.py; legs T_SEQ=1 and 11 are DECLARED from AGENT_SYNC 2026-08-29 s5, leg 31 measured in tseq_ablation.log. Encoder built at t_seq=1 (DECISION 2.6). No like-for-like incumbent number exists on this test set.
   ```
4. Post the same numbers to `docs/phase2/AGENT_SYNC.md` as a new dated section, and append to `docs/HANDOFF.md`.
5. Commit the two log files (`tseq_ablation.log`, `final_retrain.log`) — they are the only measured record of the sweep, and losing them is what created this whole mess. Add them under a tracked path, e.g. `docs/phase2/logs/`.

### 5. Comparison hygiene — what may be said about the number

**The fair comparator, and it is not an incumbent.** Both incumbent figures were measured on **2022** Argo with monthly inputs: `artifacts/argo_error_by_depth.json` → `overall.glorys.rmse = 0.9736`, `skill_vs_clim = 0.3809`; `overall.satellite.rmse = 0.9638`, `0.3871`; and `artifacts/tscast_baseline_metrics.json` (Phase-1 MLP, satellite, 897 of 2455 profiles, window 2022-01-01..2022-12-31) → `overall.rmse = 0.9578`, `skill_rmse_ratio = 0.3861`. [All VERIFIED by reading the files.] The daily model is scored on **962 profiles in 2026-04..06**. Different profiles, different period, different collocation quality — AGENT_SYNC 2026-08-29 §5 already forbids exactly this cross-set comparison for 0.8529 vs 0.9672.

So the only anchors measured on **these** profiles are computed inside the run itself:

- `metrics.overall.skill_rmse_ratio` = 1 − RMSE/RMSE_clim against the 2019–2021 climatology on the same 962 profiles. **This is the headline-comparable number** — it is the definition the frozen Phase-1 +0.387 headline uses.
- `metrics.rmse_climatology` per depth, same profiles.
- The other T_SEQ legs, same test set, same seed, same sampler.

**Forbidden, with the reason each is forbidden:**

1. *"Our daily model reaches X, beating the incumbent 0.9736 / 0.9578."* — different test set and period. Nothing in this repo scores the incumbent on 2026 Argo: `scripts/phase2/measure_v2_metrics.py` has no period flag; it calls `VA.load_argo()` (the 2022 file) and `predict.available_dates()` (the monthly grids). [VERIFIED] Producing a fair incumbent number is a separate job, not a footnote you can wave at.
2. *"...beating the 0.9638 headline."* — that is the **satellite-driven** path; our daily inputs are GLORYS. Comparing them scores two input pipelines and calls the difference model skill. The trainer's own `compare_against.why_not_the_headline_0_9638` says this; it applies doubly here, since the test set differs as well.
3. *"T_SEQ=11's 0.8529 improves on the monthly 0.9672."* — explicitly retracted in AGENT_SYNC 2026-08-29 §5.
4. **The final 60k / 25-epoch run vs the 40k / 15-epoch ablation legs.** Different sample budget and epoch budget; the difference is not attributable to the window. If the final run beats 0.8529, say "at a larger sample budget", not "the window improved further".
5. Quoting `skill_rmse_ratio` (0.24 on the current T=31 run) beside `skill_vs_climatology` (0.43) — two definitions of skill on the same predictions. The JSON's own `skill_note` says never to put them side by side. Use `skill_rmse_ratio` for anything compared to the frozen headline.
6. Quoting `correlation_pooled` (0.9931) instead of `correlation` (0.8824). Pooled correlation mostly measures that deep water is cold. The JSON's `correlation_note` says which one to quote.
7. `"trained_on"` / `"train_years"` as written today (see 4.4) — do not paste them into a report before fixing them.

**Allowed with a stated caveat:** the calibration ratio against MC-dropout's 1.56–3.54 (`artifacts/mc_calibration.json`, D-016). The method is identical by construction — RMSE per depth divided by RMS sigma per depth, aggregated *then* divided, guarded by `tests/phase2/test_tscast_train.py` — but MC-dropout was measured on the 2022 profiles. Phrase it as *"same method, different profiles"*, and never as a controlled comparison.

**Always state, in the same breath as the number:** 5 of the contract's 7 channels (no wind, PS req 8 at 0%); two of three ablation legs declared rather than re-measured; the encoder built at `t_seq=1` (2.6); and the sample-count confound across legs.

### 6. Tests

Add to the existing `tests/phase2/test_tscast_train.py` (it already imports from the trainer, so the module path is proven):

1. `test_cnn3d_state_dict_is_shape_identical_across_t_seq_builds` — build `TSCastNIO("cnn3d", 5, t_seq=1, ...)` and `t_seq=31`, assert the key lists are equal and every tensor shape matches. Asserts *why* the mismatch is silent rather than caught.
2. `test_t_seq_build_mismatch_changes_predictions` — load the same random `state_dict` into both, feed one fixed `(2,5,31,17,17)` input, assert `np.abs(a-b).mean() > 1e-3`. Asserts the mismatch is not cosmetic. (Measured 0.137 °C mean / 0.891 °C max on the real checkpoint.)
3. `test_checkpoint_records_encoder_t_seq_and_decoder` — call the trainer's `build_model` + the save-dict construction (extract it into a `checkpoint_dict(...)` helper if needed) and assert `"encoder_t_seq"` and `"decoder"` are present. Guards the serving path against silently reverting.
4. `test_inference_builds_the_encoder_at_the_checkpoints_encoder_t_seq` — construct a predictor from a tiny synthetic checkpoint with `encoder_t_seq=1, T_SEQ=31`, assert `predictor.model.encoder.body[1].kernel_size == (1, 2, 2)`. Fails if inference goes back to building at `T_SEQ`.

New file `tests/phase2/test_pick_tseq.py` (there is no test for the picker today, and it is now the thing that decides the model):

5. `test_parse_reads_the_banner_then_the_next_overall` — a two-leg fixture log parses to `{1: ..., 31: ...}`.
6. `test_the_trainers_own_data_line_is_not_a_banner` — assert `parse` on a log containing only `data   : daily, 388 steps, T_SEQ=31, train 304 / test 84` returns `{}`. Guards the regex against a well-meaning "simplification".
7. `test_a_leg_measured_and_declared_is_refused` — run the script with `--log <fixture> --recorded "31=0.9"` where the log already has 31; assert non-zero exit and "Refusing to guess" in stderr.
8. `test_partial_sweep_is_refused` — two legs only; assert non-zero exit and "Refusing to pick a winner from a partial sweep".
9. `test_margin_under_two_hundredths_prefers_the_shorter_window` — declare `1=0.900, 11=0.895, 31=0.890` and assert the printed `FINAL RUN` line contains `--t-seq 1`, i.e. the longest window did not win a 0.01 °C margin.

Run: `.venv\Scripts\python.exe -m pytest tests/phase2 -q` (the whole phase2 suite was 227 tests passing on the merged tree per AGENT_SYNC; do not land a phase with fewer). If imports fail under pytest, delete `tests/phase2/__init__.py` — it shadows `src/phase2`.

### 7. DONE checklists

**Phase 2 is done when all of these are true:**

- [ ] Preconditions 2.1 printed `388 / 304 / 84`, 5 channels, three `True`s.
- [ ] The pre-existing `tscast_stage1.pt` + metrics JSON were inspected and copied to `*_tseq<N>.*` before any run started.
- [ ] The T_SEQ=31 leg ran on the **5-channel** bundle with `--decoder simple --loss nll --epochs 15 --train-samples 40000 --test-samples 12000 --patience 4`, or its machine-written JSON was preserved and cited as declared.
- [ ] `tseq_ablation.log` contains a `===== T_SEQ=31 =====` banner and an `OVERALL rmse=` line, both confirmed with `Select-String`.
- [ ] The run reported ~962 independent Argo profiles; if not, the discrepancy was explained before anything was quoted.
- [ ] `pick_tseq_and_retrain.py --dry-run` printed all three legs, each labelled `measured` or `declared`, and named a winner.
- [ ] The declared/measured split is repeated in every place the ranking is quoted (AGENT_SYNC, EXPERIMENT_LOG, UI copy).
- [ ] DECISION 2.6 chosen, implemented, and written into `docs/DECISIONS.md` — including the fix to `inference.py` so serving matches validation.
- [ ] Tests 1–9 written and passing; full `tests/phase2` suite green.
- [ ] `tseq_ablation.log` and both `*_metrics_*.json` copies committed (force-add for the JSONs).

**Phase 4 is done when all of these are true:**

- [ ] The three provenance defects (4.4) are fixed **before** the final run, so the JSON it writes is true when it is written.
- [ ] The previous checkpoint pair was backed up.
- [ ] `git status` was clean at launch and nothing was committed while the run was in flight (`code_commit` is read at the end).
- [ ] The final run used the flags the picker printed, on the 5-channel bundle, and the log is captured.
- [ ] The run restored a best epoch and wrote both artifacts; the "no epoch improved" refusal did not fire.
- [ ] Argo profile count, per-depth table, OVERALL line and calibration range all inspected — not just the headline RMSE.
- [ ] `metrics_*.json` copied, force-added, and the numbers mirrored into `docs/EXPERIMENT_LOG.md`, `docs/phase2/AGENT_SYNC.md` and `docs/HANDOFF.md`.
- [ ] Every reported number carries: 5-of-7 channels, the declared-leg caveat, the encoder-`t_seq` decision, the sample-budget confound, and the statement that **no like-for-like incumbent number exists on this test set**.
- [ ] No forbidden comparison from section 5 appears anywhere in the write-up, the JSON, or the UI.
- [ ] If a 7-channel run happened: it is reported as a channel ablation against the 5-channel final run only, with the channel-order guard in place.

## PHASE 5 — The v2 UI: "explain every output"

**Owner:** Unit B (Darshan). **Branch:** `phase2-tscast-nio`. **Est. 3–4 h.**

### 5.0 Entry gate — read this before you write a line of UI

**[VERIFIED, 2026-08-30, this clone]** `TSCastPredictor()` currently **raises** on the shipped checkpoint:

```
RuntimeError: Error(s) in loading state_dict for TSCastNIO:
  Missing key(s) in state_dict: "decoder.stem.a.weight", "decoder.stem.a.bias", ...
```

So **no live prediction record exists yet**. Phase 3 (fix `src/phase2/tscast_nio/inference.py`) is a hard prerequisite for §5.3 only. §5.4 (benchmark), §5.5 (calibration ratios) and §5.6 (honesty) read JSON artifacts and can be built and accepted *before* Phase 3 lands.

**The rule that follows from this:** the profile tab must render a **refusal that quotes the real exception** when the predictor cannot be built. It must never fall back to a synthetic profile, a cached record from another checkpoint, or a `st.stop()` with no explanation. A blank page is a bug; a refusal that says why is the deliverable.

---

### 5.1 File layout, port, launch, and the frozen-app rule

#### The frozen-app rule (non-negotiable)

`app/streamlit_app.py` and everything in `app/panels/` are the **frozen Aug-30 demo**. You may `import` from them; you may **not** edit them, and nothing you build may change what that app renders. This is the same rule every existing Phase-2 page states in its own docstring (`app/phase2/collocation_page.py:5`, `app/phase2/validation_page.py:3`). Repeat it verbatim in your new docstring.

#### Files to create

| path | contents |
|---|---|
| `app/phase2/tscast_page.py` | **entry script.** `st.set_page_config`, sidebar query, `st.tabs([...])`, dispatch to the four tab modules. No science, no numbers of its own. |
| `app/phase2/v2/__init__.py` | empty |
| `app/phase2/v2/sources.py` | cached loaders: artifacts JSON, the predictor, the Argo table. The **only** place that touches disk. |
| `app/phase2/v2/profile_tab.py` | `render(rec: dict) -> None` |
| `app/phase2/v2/benchmark_tab.py` | `render(metrics: dict, mode: str) -> None` |
| `app/phase2/v2/calibration_tab.py` | `render(metrics: dict, mc: dict \| None, coverage: dict \| None) -> None` |
| `app/phase2/v2/honesty_tab.py` | `render(metrics: dict, gap: dict \| None) -> None` |
| `scripts/phase2/measure_coverage.py` | writes `artifacts/tscast_coverage.json` (§5.5) |
| `tests/phase2/test_v2_ui.py` | AppTest render tests (§5.9) |

#### Port

**8507.** [VERIFIED] `grep -rn "server.port" app/` returns 8502 (collocation), 8503 (validation), 8504 (cube), 8505 (physics), 8506 (events). The rebuild prompt says "Port 8503+"; 8503–8506 are taken, so 8507 is the first free one. Put the launch line in the module docstring, exactly as the other five pages do.

#### Launch

```
python -m streamlit run app/phase2/tscast_page.py --server.port 8507
```

The entry script must put **both** the repo root and `src/` on `sys.path` before any project import — the root is needed for `from app.phase2.v2 import ...`, `src/` for `oceanembed` and `phase2`. The existing pages only add `src/`; you need both:

```python
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
```

#### DECISION 1 — one page with tabs, or four pages on four ports?

Not settled by the repo (every existing Phase-2 page is one file on one port; the rebuild prompt says "New pages", plural). **Recommended default: ONE entry script on 8507 with `st.tabs`.** Reasons: (a) a judge should not be told to open four URLs; (b) **[VERIFIED]** `AppTest`'s `at.metric` accessor descends into `st.tabs`, `st.columns` and `st.expander`, so a single `AppTest.from_file` run in `accept.py` can scrape every rendered number in all four tabs at once — four ports would need four harness runs. If you split, §5.7's check must loop over the files.

#### `sources.py` skeleton

```python
"""The only module in the v2 UI that touches disk. Everything else receives dicts."""
from __future__ import annotations
import json, os
import streamlit as st
from oceanembed import config

METRICS_JSON  = "tscast_stage1_metrics.json"
MC_JSON       = "mc_calibration.json"
COVERAGE_JSON = "tscast_coverage.json"
GAP_JSON      = "glorys_vs_argo.json"

@st.cache_data
def load_json(name: str) -> dict | None:
    """None -- never {} -- when absent, so a caller must decide what to say about it."""
    p = config.art(name)
    return json.load(open(p)) if os.path.exists(p) else None

@st.cache_resource
def get_predictor() -> tuple[object | None, str | None]:
    """(predictor, None) or (None, why-it-refused). Never a fabricated stand-in."""
    from phase2.tscast_nio.inference import TSCastPredictor
    try:
        return TSCastPredictor(), None
    except Exception as e:                       # FileNotFound / channel mismatch / state_dict
        return None, f"{type(e).__name__}: {e}"
```

**Trap [VERIFIED against `app/phase2/validation_page.py:19`]:** `st.cache_data` silently *excludes* any argument whose name starts with an underscore, pinning the first result forever. No cached function here may take an underscore-prefixed argument.

---

### 5.2 What the UI is allowed to compute

**Nothing scientific.** `docs/phase2/tscast_output_schema.md` defines two records — the prediction record (§1–5) and the aggregate metrics record (§6). The UI's whole job is to lay them out. Permitted arithmetic in `app/phase2/v2/`:

- `lo = temperature - sigma_t`, `hi = temperature + sigma_t` (drawing the band the record already specifies)
- `np.nanargmin` / `np.nanargmax` over an array the record already contains, to *find which depth* to caption
- unit-free formatting (`f"{x:.4f}"`)

Everything else — RMSE, skill, bias, correlation, calibration ratio, coverage, the signed model−Argo difference — must already be a value in a record or an artifact. If a number appears on screen that no artifact contains, that is a bug, not a feature.

---

### 5.3 The profile tab — the demo centrepiece

#### 5.3.1 Inputs

Sidebar: latitude slider, longitude slider, date input. Copy the bounds from `config.LAT` / `config.LON` exactly as `collocation_page.py:76-77` does — never hardcode 5/30/45/105.

```python
lat  = st.slider("Latitude (°N)",  float(config.LAT.min()), float(config.LAT.max()), 15.0, 0.05)
lon  = st.slider("Longitude (°E)", float(config.LON.min()), float(config.LON.max()), 65.0, 0.05)
date = st.date_input("Date", value=datetime.date(2026, 5, 15))
```

Seed the caption with two known-interesting points, as the collocation page does: **15°N 88°E** (Bay of Bengal, deep, river-capped) and **26.00°N 52.50°E** (Persian Gulf — **[VERIFIED]** `accept.py:check_f2a` asserts the sea floor there reads exactly 30 m, so it is the reliable below-seafloor demo).

#### 5.3.2 Getting the record

```python
pred, why = sources.get_predictor()
if pred is None:
    st.error(
        "**No prediction. The checkpoint could not be loaded, and this page will not invent "
        f"a profile to fill the gap.**\n\n```\n{why}\n```\n\n"
        "Fix `src/phase2/tscast_nio/inference.py` (Phase 3), then reload. "
        "The benchmark, calibration and honesty tabs read saved artifacts and still work.")
    return
rec = pred.reconstruct(lat, lon, date, argo_check=build_check(pred, lat, lon, date))
```

**[VERIFIED signature]** `TSCastPredictor.reconstruct(self, lat: float, lon: float, date, argo_check=None) -> dict`. It does **not** find Argo for you — `argo_check` is a parameter you supply. See §5.3.5.

#### 5.3.3 The chart: profile + σ band

The record gives you `temperature` (`None` below the sea floor), `sigma_t` (`None` below the sea floor), `log_var_t` (**always a float, even below the sea floor**), `valid`, `depths_m`, `reasons`.

**Rule: never derive the error bar yourself from `log_var_t`.** The schema is explicit — `sigma_t` is the number the UI shows; `log_var_t` exists for the loss and for a calibration audit, and "a UI that shows a log variance to a judge has failed." Because `log_var_t` stays finite below the sea floor while `temperature` is `None`, computing `exp(0.5*log_var_t)` yourself would paint an error bar around a depth that has no water in it.

```python
def profile_frame(rec: dict) -> pd.DataFrame:
    n = lambda xs: [np.nan if v is None else float(v) for v in xs]
    ac = rec.get("argo_check")
    df = pd.DataFrame({
        "depth_m": list(rec["depths_m"]),
        "t":       n(rec["temperature"]),
        "sigma":   n(rec["sigma_t"]),
        "valid":   list(rec["valid"]),
        "reason":  list(rec["reasons"]),
        "argo":    n(ac["argo_temperature"]) if ac else [np.nan] * len(rec["depths_m"]),
        "diff":    n(ac["difference"])       if ac else [np.nan] * len(rec["depths_m"]),
    }).sort_values("depth_m")
    df["lo"], df["hi"] = df["t"] - df["sigma"], df["t"] + df["sigma"]
    return df

def profile_chart(df: pd.DataFrame) -> alt.LayerChart:
    y = alt.Y("depth_m:Q", title="depth (m)", scale=alt.Scale(reverse=True))
    band = (alt.Chart(df).mark_area(opacity=0.22, color="#4c8dff")
            .encode(x=alt.X("lo:Q", title="temperature (°C)", scale=alt.Scale(zero=False)),
                    x2=alt.X2("hi:Q"), y=y))
    model = (alt.Chart(df)
             .mark_line(point=True, color="#4c8dff", invalid="break-paths-show-domains")
             .encode(x="t:Q", y=y, tooltip=["depth_m", "t", "sigma", "reason"]))
    argo = (alt.Chart(df)
            .mark_line(point=True, color="#f5a524", invalid="break-paths-show-domains")
            .encode(x="argo:Q", y=y, tooltip=["depth_m", "argo", "diff"]))
    return (band + model + argo).properties(height=420)
```

Caption it: **"The shaded ribbon is ±1σ, the model's own predicted error bar (`sigma_t`), not a spread over ensemble members."** Then, because the band narrows with depth and a reader will misread that as certainty, add the measured caveat from the calibration tab: at the shallow depths the ribbon is **too narrow** — see §5.5.

#### 5.3.4 `reasons`, surfaced in place

The schema calls this non-negotiable: "A confidence or quality label carries its one-line reason **where the number appears** — never in a separate report file."

**Tooltips alone do not satisfy this.** A tooltip is invisible on a projector and invisible to `AppTest`. Render the reasons **twice**:

1. in the chart `tooltip` list (above), and
2. in a table beside the chart, one row per depth, columns `depth (m) | T (°C) | ±1σ | Argo (°C) | model − Argo | why this number`.

Formatting traps, both already paid for in `collocation_page.py:118-126,184-203` — reproduce the fix, not the bug:

- If **every** value in a column is `None`, pandas keeps it `object` dtype and Streamlit prints the literal word `None` fifteen times. Coerce numeric columns with `.astype({c: "float64" for c in num_cols})` **first**, then apply a `Styler` with `na_rep="—"`. This is the common case: most of the basin has no float nearby.
- `round(x, 2)` turns `-0.0009` into a bare `0` sitting next to `-0.01`, which reads as exact agreement. Use `.style.format({...}, na_rep="—")` with fixed widths.

#### 5.3.5 The `argo_check` panel

Schema §3, non-negotiable: "Every panel shows the prediction, the nearest independent Argo reading, and the difference. Never a number without its ground-truth check beside it."

Render, at the top of the panel, three `st.metric` tiles + one quality badge:

| tile | source field |
|---|---|
| distance | `argo_check["distance_km"]` |
| time offset | `argo_check["days_offset"]` |
| levels the float sampled | `sum(v is not None for v in argo_check["argo_temperature"])` |
| quality badge | `argo_check["quality"]` coloured by `QUALITY_COLOUR` (copy the dict from `collocation_page.py:28`), with `argo_check["quality_reason"]` printed underneath verbatim |

Then the signed difference column in the table (§5.3.4). Sign convention, stated on screen: **`difference = model − Argo`; positive means the model runs warm.** [VERIFIED] `output.build_argo_check` computes `diff = p - a`, and the metrics record carries `"bias_convention": "model - truth; POSITIVE means the model runs warm"`.

When `argo_check is None`, print the exact sentence the schema mandates — **"no independent float within range"** — never an empty panel, never a silent zero. Add the collocation page's context so the gap reads as the problem, not a failure: 2,455 floats across ~15 million km² is genuinely sparse.

**How to build the `argo_check` — DECISION 2, and it is a real blocker.**

**[VERIFIED]** `CollocationEngine._argo_table()` (`src/phase2/data/collocation.py:123-131`) is hardcoded to `config.art("argo_test")`, and **[VERIFIED]** `artifacts/argo_test.parquet` spans **2022-01-01 → 2022-12-31** only. The v2 daily test window is **2026-04-01 → 2026-06-23** (`dataset.DAILY_TEST`). So against a v2 date the F1 engine matches **nothing**, every time, silently.

The period-matched table exists: **[VERIFIED]** `artifacts/argo_daily_period.parquet`, 59,599 rows, 4,331 profiles, **2025-06-01 → 2026-06-22**, columns `lat, lon, date, depth_idx, temp`, `depth_idx` in 0..14.

Three options, and you must pick one explicitly:

- **(a) RECOMMENDED — add an `argo_table` parameter to `CollocationEngine.__init__`,** defaulting to `"argo_test"` so nothing existing changes, and pass `"argo_daily_period"` from the v2 page. `src/phase2/data/collocation.py` is Unit B's own F1 file, so this is inside your ownership. One matcher, one set of quality bands, no drift. Add a line to `tests/phase2/test_collocation.py` asserting the default is unchanged.
- (b) Call the existing private `_match_argo(lat, lon, when)` after swapping `engine._argo` yourself. Works, but reaches into a private attribute and will break silently.
- (c) Write a second matcher in the UI. **Do not.** That is D-014 repeating — two matchers that can disagree — and the schema forbids it in writing: "We do not write a second matcher."

Then convert the engine's dict to a schema `argo_check` using the **model-side** builder, never by hand:

```python
from phase2.tscast_nio import output
a = engine.match_argo(lat, lon, pd.Timestamp(date))     # option (a)
check = None if a is None else output.build_argo_check(
    argo_temperature=a["temperature_profile"],
    temperature=rec_temperature,                        # the model's 15 values
    profile_id=f"{a['latitude']:.4f}N_{a['longitude']:.4f}E_{a['datetime']}",
    distance_km=a["spatial_offset_km"],
    days_offset=int(abs(a["temporal_offset_days"])),
    source="argopy")
```

**[VERIFIED signature]** `output.build_argo_check(argo_temperature, temperature, profile_id, distance_km, days_offset, source="argopy") -> dict`. The HIGH/MEDIUM/LOW/REJECT bands live inside it (`≤25 km & ≤3 d` → HIGH; `≤50 km & ≤5 d` → MEDIUM; `≤100 km & ≤10 d` → LOW; else REJECT). Do not re-implement them in the page.

Note `days_offset` is typed `int` and the engine returns a **signed** float — take `abs()` and say so in the caption, or a float 6 days before reads as `-6` and lands in the wrong band.

#### 5.3.6 Below the sea floor — render as a refusal that carries the real depth

**[VERIFIED]** `output.build_record` sets `temperature[k] = None` and `sigma_t[k] = None` wherever `valid[k]` is `False`, and `build_reasons` already writes the sentence for you:

```
"no value: the sea floor here is at 30 m, shallower than this 50 m level"
```

The UI's job is to **show that string, not to invent one**. Requirements:

1. The chart line **breaks** at the first invalid depth. Keep the NaN row in the frame and use `mark_line(invalid="break-paths-show-domains")` (§5.7 gotcha 2). Do **not** `.dropna()` — Vega-Lite's default is to filter invalid rows, which *connects the path across the gap* and draws water where there is rock.
2. The table row shows `—` in T and ±σ, and the refusal sentence in the "why this number" column.
3. Above the chart, when `not all(rec["valid"])`, print:
   `st.warning(f"{n_invalid} of 15 levels are below the sea floor at this point. The sea floor here is at **{rec['seafloor_depth_m']:.0f} m** — those depths are refused, not estimated.")`
   The number comes from `rec["seafloor_depth_m"]`, which `TSCastPredictor.seafloor_depth_m(lat, lon)` measured from the deepest finite target level. Never a constant.
4. `st.metric` tiles must skip invalid depths entirely rather than printing `None` or `0.0`.

#### 5.3.7 The FORECAST label rule

Schema §4, and `build_record` enforces half of it for you.

**[VERIFIED]** `inference.LAST_GLORYS = np.datetime64("2026-06-23")`, `inference.LAST_ARGO = np.datetime64("2026-08-24")`. `reconstruct` sets `forecast = bool(target > LAST_GLORYS)` and passes `argo_check=None` whenever `forecast` is true. **[VERIFIED]** `output.build_record` *raises* `ValueError("a forecast cannot carry an argo_check: ...")` if you try to attach one anyway — so you cannot break this by accident, only by catching that exception, which you must not do.

The UI half:

```python
if rec["forecast"]:
    st.error("**FORECAST — not a validated result.**")
    st.caption(rec["forecast_note"])          # carries the real 2026-06-23 / 2026-08-24 dates
```

and then, on the same screen:

- the word **FORECAST** in the tab header, not "prediction", not "accuracy";
- **no RMSE, correlation, bias, skill or calibration number anywhere on the profile tab** while `forecast` is true. Gate the whole per-depth error column behind `if not rec["forecast"]`. There is nothing to score against; a skill number beside a forecast is a fabricated metric.
- the `argo_check` panel prints "no ground truth exists past 2026-06-23 — this is a forward forecast", not "no float nearby". They are different refusals and must read differently.

**Edge case a judge will hit:** a date *between* `LAST_GLORYS` (2026-06-23) and `LAST_ARGO` (2026-08-24). `forecast` is `True` (no GLORYS input exists), yet Argo floats *do* exist there. The record correctly refuses to attach a check. Say so explicitly rather than letting it look like an oversight: "Argo reaches 2026-08-24, but the surface input this model reads ends 2026-06-23. Without an input there is no prediction to check, so this is a forecast."

**Second edge case, [VERIFIED from the code]:** `_time()` snaps to the **nearest available** grid date and records `provenance["days_from_requested"]`. A user picking a date 40 days from any available grid gets a silent snap. Render `provenance["input_date"]`, `provenance["requested_date"]` and `days_from_requested` in a caption under the chart, and `st.warning` when `days_from_requested > 5` — 5 days is `train_stage1.MAX_DAYS`, the tolerance every published v2 number was measured at.

#### 5.3.8 Provenance

Bottom of the tab, in `st.expander("Provenance — where every number came from")`, `st.json(rec["provenance"])`, exactly as `collocation_page.py:235-236` does. Call out `clim_train_years` in the caption: it is in the record deliberately so the leakage rule is auditable from a single output.

---

### 5.4 The benchmark tiles

Source: `artifacts/tscast_stage1_metrics.json` → `["metrics"]`, the aggregate record of schema §6.

#### 5.4.1 Headline tiles (`st.metric(..., border=True)`)

| tile label (exact) | value | source |
|---|---|---|
| `RMSE vs independent Argo (°C)` | `f"{o['rmse']:.4f}"` | `metrics.overall.rmse` |
| `Correlation (mean of 15 depths)` | `f"{o['correlation']:.4f}"` | `metrics.overall.correlation` |
| `Bias, model − truth (°C)` | `f"{o['bias']:+.4f}"` | `metrics.overall.bias` |
| `Skill = 1 − RMSE/RMSE_clim` | `f"{o['skill_rmse_ratio']:.4f}"` | `metrics.overall.skill_rmse_ratio` |
| `Independent Argo profiles` | `str(j['argo_profiles'])` | top-level `argo_profiles` |

**Formatting rule that the accept check depends on: the `value` of every `st.metric` is a bare number string, units live in the label, and anything *derived* (a difference against the incumbent) goes in `delta=`, never in `value=`.** §5.7 asserts that every rendered metric value appears verbatim in an artifact at 4 decimals; a derived number in `value=` would fail it, correctly.

#### 5.4.2 Which skill definition — DECISION 3, partly settled

**[VERIFIED]** the metrics record returns **two** skill numbers and its own note says: *"Never quote one beside the other."* On the current artifact they read `skill_rmse_ratio = 0.2441` and `skill_vs_climatology` (Murphy, 1 − MSE/MSE_clim) `= 0.4286` — for the *same* predictions.

The rebuild prompt asks for "both skill definitions labelled"; the metrics record forbids quoting them side by side. Resolve it this way, and say so on screen:

- **The headline tile shows `skill_rmse_ratio` only,** labelled with its formula in the tile label itself. Reason: that is the definition the frozen Phase-1 headline (+0.387) uses and the definition `compare_against.incumbent_skill_rmse_ratio` (0.3809) is expressed in. It is the only one that can be compared to anything we have published.
- **The Murphy score appears only inside the per-depth table**, under a column headed `Murphy skill (1 − MSE/MSE_clim) — NOT comparable to the headline`, with `metrics.overall.skill_note` printed verbatim in an expander beneath.

#### 5.4.3 Absolute RMSE beside skill — and WHY

**The rule:** `rmse_climatology[d]` and `rmse[d]` are rendered in the *same row* as every skill number, always. Never a skill column on its own.

**The reason, in the caption, in plain language:** skill is a *ratio* against the climatological average. The deep ocean barely varies from month to month, so climatology is already nearly right there and there is almost nothing left to beat — the skill score collapses. But that same depth is where our **absolute** error is smallest. Skill alone therefore says "the model is worst at depth"; the absolute RMSE beside it says "the model is *best* at depth". Both are true statements about the same numbers, and only the pair is honest.

**Do not hardcode "1000 m".** [VERIFIED on the current artifact] `argmin(rmse)` is index **14 (1000 m, 0.2395 °C — our best absolute)** while `argmin(skill_rmse_ratio)` is index **12 (500 m, 0.1292)**. The paradox depths are *not* the same on this run, and Phase 4's retrain will move them again. Compute both at render time and write the caption from the result:

```python
r  = np.array(m["rmse"]);              s = np.array(m["skill_rmse_ratio"])
kb = int(np.nanargmin(r));             ks = int(np.nanargmin(s))
st.info(
  f"**Skill and absolute error disagree, and both are shown for that reason.** "
  f"Our lowest skill is **{s[ks]:+.4f} at {m['depths_m'][ks]} m**, where climatology's own "
  f"error is only **{m['rmse_climatology'][ks]:.3f} °C** — there is little left to beat. "
  f"Our *best absolute* RMSE is **{r[kb]:.4f} °C at {m['depths_m'][kb]} m**. "
  f"A skill column without its absolute RMSE beside it would call the deep ocean our weakness; "
  f"it is our strength.")
```

#### 5.4.4 Per-depth table

15 rows: `depth (m) | n | RMSE | RMSE climatology | skill (1−RMSE/RMSE_clim) | Murphy skill | correlation | bias`.

**Small-sample edge case, [VERIFIED]:** `metrics.n[0] = 21` at 0 m against ~950–960 at every other depth, and — consistently — the `calibration` block in the same file has **no `"0"` key at all**, because `train_stage1.calibration()` drops any depth with `n < 30`. Grey that row and print `only 21 floats sampled 0 m — below the 30-profile floor used for every other number in this file`. Do not let a 0.4048 °C RMSE on 21 profiles sit unmarked next to one on 960; that is how a judge is misled without a single false number being printed.

#### 5.4.5 The test window — it is NOT in the record

**[VERIFIED contradictions in the current `tscast_stage1_metrics.json`:**
- `metrics.window` is **`null`**;
- `data: "daily"` and `T_SEQ: 31`, yet `train_years: [2019,2020,2021]`, `test_years: [2022]` (written from `base.TRAIN_YEARS`, not from the daily split);
- `trained_on: "monthly archive, T_SEQ=1 (the daily bundle had not landed)"` — **stale**, contradicted by `data: "daily"` in the same file.

**Do not render `trained_on`.** For the window, use this precedence and print which branch you took:

1. `metrics.window` if non-null → show it.
2. else if `data == "daily"` → show `dataset.DAILY_TEST` (`2026-04-01 → 2026-06-23`) and caption *"window taken from `phase2.tscast_nio.dataset.DAILY_TEST`; the metrics record's `window` field is null"*.
3. else if `data == "monthly"` → show `test_years`.
4. else → `st.warning("Test window UNKNOWN — the metrics record says data='...' but carries train/test YEARS that belong to the other bundle. Not guessing.")`

If Phase 3 fixes the trainer to write `window` and the true trained-on period (it is on the Phase-3 list), branch 1 fires and the rest becomes dead-but-harmless.

#### 5.4.6 CACHED vs LIVE badge — what each means concretely

Precedent: `docs/DEMO_SPEC.md` §"LIVE vs CACHED" — a cached result must be labelled **CACHED (VERIFIED)** and never presented as live inference.

| badge | concretely means | rendered as |
|---|---|---|
| **CACHED (VERIFIED)** | the numbers were read from `artifacts/tscast_stage1_metrics.json`, written by a real training run of `phase2.tscast_nio.train.train_stage1`. The badge carries `checkpoint`, `code_commit`, `seed` and the file's mtime, all from the JSON. Nothing was computed this session. | `st.badge("CACHED (VERIFIED)", color="blue")` + caption `written by {j['checkpoint']} @ commit {j['code_commit']}, seed {j['seed']}, file dated {mtime:%Y-%m-%d %H:%M}` |
| **LIVE** | `phase2.tscast_nio.metrics.per_depth(...)` ran **in this session**, on predictions this session produced from the loaded checkpoint. | `st.badge("LIVE", color="green")` + caption naming the checkpoint sha and the profile count actually scored |

**The benchmark tab is CACHED by default and should stay that way for the demo** — scoring 962 profiles live takes minutes. Offer LIVE behind an explicit `st.checkbox("Recompute live (slow)")`, and if it is off, the badge is CACHED. Never show LIVE for a number you did not compute this run. Never show a badge at all if the artifact is missing — show the refusal instead:

```python
if metrics is None:
    st.error("No metrics artifact. Run `python -m phase2.tscast_nio.train.train_stage1` "
             "(or the Phase-4 retrain) — this page will not display numbers it cannot source.")
```

#### 5.4.7 Comparison against the incumbent

`compare_against` carries `incumbent_rmse: 0.9736`, `incumbent_skill_rmse_ratio: 0.3809`, `which`, and `why_not_the_headline_0_9638`.

Show the RMSE delta as `st.metric(..., delta=...)`. **But — [VERIFIED] the current v2 run scores 0.9267 RMSE (better than 0.9736) and 0.2441 skill (worse than 0.3809).** Those are not contradictory; they mean the climatology baseline differs between the two runs, because they are scored on different Argo sets (962 profiles in a 2026 window vs the Phase-1 879 in 2022).

**DECISION 4:** rendering a skill delta across two different reference sets would be a fabricated comparison. **Recommended default: render the RMSE delta with the caveat, and render the skill numbers side by side under an explicit heading `not a like-for-like comparison`, with `compare_against.which` and `why_not_the_headline_0_9638` printed verbatim in an expander.** If Phase 4 rescores the incumbent on the same window, promote it to a real delta then and not before.

---

### 5.5 The calibration panel — the differentiator

**[VERIFIED from the rebuild prompt, sourced to the full paper text]** TS-Cast (Chae et al., Ocean Sci. 2026) contains **no calibration and no coverage figure at all.** This panel is the thing we have that the paper does not. State that on screen, once, without overclaiming: *"The paper this architecture comes from reports accuracy but never asks whether its error bars are the right size. This panel does."*

#### 5.5.1 Per-depth ratio, v2 beside MC-dropout

Both numbers already exist and were **measured by the same method** — this is stated in both files:

- `tscast_stage1_metrics.json → calibration[depth] = {n, rmse, sigma, ratio}` — **[VERIFIED]** 14 depths (5…1000 m; no `"0"` key), ratios **0.701 … 1.773**, `calibration_method: "RMSE(pred-argo) / RMS(sigma), aggregated per depth THEN divided -- identical to artifacts/mc_calibration.json so the comparison against MC-dropout's 1.56-3.54 is like for like"`.
- `mc_calibration.json → by_depth[depth] = {n, rmse, mc_sigma, overconfidence}` — **[VERIFIED]** same 14 depths, ratios **1.563 … 3.541**, `worst 3.54 @ 20 m`, `best 1.56 @ 1000 m`.

Render a grouped bar chart, depth on an **ordinal** y-axis, one bar per (depth, method), plus a dashed rule at **1.0**. Legend: `v2 (predicted σ)` vs `MC-dropout (D-016)`.

Reading, printed under the chart, taken from `mc_calibration.json → "reading"` verbatim: **"ratio > 1 means the spread is too NARROW (model more wrong than it admits)."** Add the v2 result in plain language, computed from the array not hardcoded: v2 is honest-to-mildly-overconfident everywhere (max ratio ≈ 1.77) where MC-dropout was 1.56–3.54, and at 1000 m v2's ratio of 0.701 means the band there is *too wide*, which is the opposite failure and must be named as such rather than celebrated as "well calibrated".

**Two sample-provenance warnings that must appear, [VERIFIED]:**
- The two measurements are like-for-like in **method**, not in **sample**: MC-dropout was measured on `source: "satellite"`, `n_profiles: 879`, 2022; v2 on 962 profiles in the daily window. Print both `n` values in the table so the difference is visible, and say the comparison is of *method* not of *dataset*.
- Depth **0 m is absent from both** calibration blocks (n < 30). Render that row as "not reported — fewer than 30 floats sample 0 m", never as a blank or a zero-height bar.

#### 5.5.2 Coverage bars at 1σ and 2σ

**This number does not exist yet.** [VERIFIED] `train_stage1.py` persists per-depth aggregates only, never per-profile predictions or σ, and `src/phase2/reliability/` is empty on this branch. So you must produce it.

**DECISION 5 — where coverage is computed.** The UI computes nothing scientific (§5.2), and recomputing 962 profiles on every rerun would make the tab unusable. **Recommended default: a new script `scripts/phase2/measure_coverage.py` writing `artifacts/tscast_coverage.json`; the tab reads it and refuses if absent.** Register it in `accept.py`'s `DERIVED` dict so a fresh clone regenerates it automatically:

```python
DERIVED = {
    "glorys_vs_argo.json": "glorys_vs_argo.py",
    "mc_calibration.json": "measure_mc_calibration.py",
    "tscast_coverage.json": "measure_coverage.py",     # <-- add
}
```

**The formula.** For each contract depth index `k` and each independent Argo profile `i`:

```
covered_k(σ-multiple κ)  =  mean over the masked pairs of  [ |P[i,k] − A[i,k]|  ≤  κ · S[i,k] ]
```

where `P` = predicted temperature (°C), `S` = predicted `sigma_t` (°C, i.e. `exp(0.5·log_var_t)` already converted out of z-units), `A` = the Argo temperature at that depth. Report at **κ = 1** and **κ = 2**. The Gaussian targets to draw as dashed reference rules are **0.6827** and **0.9545**; label them "what a correctly-sized Gaussian error bar would give", not "the correct answer".

**The masking rule — all five clauses, in order:**

1. `np.isfinite(A[:, k])` — a NaN means **the float did not sample that level**. Drop the pair. Never fill, never interpolate to a neighbouring depth.
2. `valid[i, k]` is `True` — below the sea floor the record's `temperature` and `sigma_t` are `None`. Drop. Do **not** coerce `None` to 0.0; a zero prediction against a real Argo reading is a fabricated 25 °C error.
3. `np.isfinite(P) & np.isfinite(S) & (S > 0)`. σ from `exp(0.5·log_var)` is strictly positive, so a zero or NaN means something broke upstream — drop it **and count it**, printing the count in the JSON. A silently-dropped defect is how a calibration figure gets quietly flattering.
4. The **same** temporal gate as the RMSE beside it: `|days_offset| ≤ 5`, i.e. `train_stage1.MAX_DAYS`. Do not tighten or loosen it for the UI; if you do, the coverage number is no longer comparable to the RMSE printed next to it.
5. **Aggregate per depth, then divide** — pool all surviving `(profile, depth)` pairs *at that depth*. Never pool across depths, and never average per-profile coverages. This is the same aggregation rule `mc_calibration.json → "method"` states, for the same reason: sigma in a denominator makes per-point averaging inflate the shallow end.

Report `NaN` — **never 0.0** — where `n < 30`, matching `measure_mc_calibration.MIN_N = 30` and `train_stage1.calibration`'s own floor.

```python
MIN_N = 30
KAPPA = (1.0, 2.0)
GAUSSIAN = {1.0: 0.6827, 2.0: 0.9545}

def coverage(pred, sigma, argo, valid):
    """pred/sigma/argo: (N, 15) float; valid: (N, 15) bool. -> {depth_m: {...}}"""
    ok = (np.isfinite(pred) & np.isfinite(sigma) & (sigma > 0)
          & np.isfinite(argo) & np.asarray(valid, dtype=bool))
    out = {}
    for k, d in enumerate(config.DEPTHS):
        m = ok[:, k]
        if int(m.sum()) < MIN_N:
            out[int(d)] = {"n": int(m.sum()),
                           "note": f"only {int(m.sum())} usable pairs at {d} m; below the "
                                   f"{MIN_N}-profile floor, so no coverage is reported"}
            continue
        e = np.abs(pred[m, k] - argo[m, k])
        row = {"n": int(m.sum()),
               "rms_sigma": round(float(np.sqrt(np.mean(sigma[m, k] ** 2))), 4)}
        for kap in KAPPA:
            row[f"coverage_{kap:.0f}sigma"] = round(float(np.mean(e <= kap * sigma[m, k])), 4)
        out[int(d)] = row
    return out
```

The script itself: load `artifacts/argo_daily_period.parquet`, pivot with **[VERIFIED]** `validate_argo.pivot_profiles(df) -> (keys: DataFrame[lat,lon,date], truth: np.ndarray (N,15))`, map to cells with **[VERIFIED]** `dataset.cell_index(lat, lon) -> (i, j)` (the frozen nearest-centre convention — `searchsorted` disagrees on 75.5% of profiles by one cell), run the checkpoint the same way `train_stage1.py:252-262` does, and write the JSON with a `method`, `masking_rule`, `max_days_offset`, `n_profiles`, `seed`, `checkpoint` and `code_commit` block in the style of `measure_mc_calibration.py`.

**Rendering:** horizontal bars, depth ordinal on y, coverage 0–1 on x with `scale=alt.Scale(domain=[0,1])`, two facets or two colours for 1σ and 2σ, and two dashed `mark_rule` layers at 0.6827 / 0.9545. Caption: *"Bars short of the dashed line mean the error bar is too narrow at that depth — the model is wrong more often than it admits."*

---

### 5.6 The honesty page

One tab, no charts required, every claim carrying its source artifact. Contents, all **[VERIFIED]** against files on disk today — recompute each at render time from the JSON so they cannot go stale:

1. **Evidence-tag legend** — `[VERIFIED] / [INFERRED] / [UNKNOWN]`, and the rule that only VERIFIED are facts. Copy the wording from `CLAUDE.md`.
2. **5 channels, not 7.** `metrics["channels"] = ["sst","sss","ssh","u","v"]`, `channels_note: "5 of the contract's 7; wind arrives with the daily pipeline"`, against `tscast_nio.config.CHANNELS` which lists 7 including `wu, wv`. Render both lists and the diff. If Phase 4 lands wind, this row updates itself.
3. **Stage 1 only.** `stage: 1`, `stage_note` verbatim; salinity / density / the eq. 5 constraint are `None` keys in every record. Say the keys exist so stage 2 is a fill-in, not a schema migration — that is a design claim we can back.
4. **The mixed layer is ours; the thermocline is inherited.** From `tscast_stage1_metrics.json` the worst absolute RMSE is **1.3352 °C at 125 m** and bias runs warm through 30–150 m (peak **+0.6376 °C at 50 m**). From `artifacts/glorys_vs_argo.json` (11,761 comparisons) the *reanalysis itself* is worst at **100 m (0.7848 °C mean abs)**. Render both and state the split: where the training truth is already wrong, part of our error is inherited; in the mixed layer it is not, and that is genuinely ours to fix.
5. **The 0 m row is 21 profiles.** §5.4.4.
6. **`window` is null and `trained_on` is stale.** §5.4.5. Say it in the open — a metrics file that contradicts itself is a thing we found and reported, not a thing we hide.
7. **The two skill definitions.** `overall.skill_note` verbatim.
8. **The pooled correlation is not quotable.** `overall.correlation_pooled = 0.9931` vs `correlation = 0.8824`; print `correlation_note` verbatim and show which one the benchmark tile uses.
9. **Overfitting.** `epochs_requested: 15`, `epochs_run: 8`, `best_epoch: 4`, `checkpoint_is: "the BEST held-out epoch, not the last -- this run overfits after a handful of epochs"`.
10. **What was CUT and why** — F7 heatwave, F9 Sentinel, F10 priority v2, new F6 work. One line each, from the team decision. A cut list on screen is a credibility asset, not an admission.
11. **What is not measured at all** — everything in your `unknowns` list. Label `[UNKNOWN]`, do not soften.

---

### 5.7 The new `accept.py` check

Register it in `CHECKS` (the list is `(display_name, import_path, fn)`; detection is by **import path**, never branch name — see the file's own header):

```python
CHECKS = [
    ...
    ("v2 TS-Cast-NIO", "phase2.tscast_nio.metrics", check_v2_tscast),
    ("v2 UI",          "app.phase2.v2.sources",     check_v2_ui),      # <-- add
]
```

`app/phase2/v2/sources.py` importing is the presence signal; the check below is what actually proves anything.

```python
def check_v2_ui() -> tuple[bool, list[str]]:
    """The v2 pages must RENDER the metrics artifact's own numbers, to 4 decimals.

    Asserting that the page IMPORTS proves nothing -- a page that imports cleanly and then
    prints a hardcoded 0.9267 would pass, and would go on passing after the Phase-4 retrain
    moved the real number. So this runs the page headlessly through Streamlit's AppTest
    harness and reads the numbers it actually put on screen.
    """
    import json
    import numpy as np
    from streamlit.testing.v1 import AppTest
    from oceanembed import config

    mp = config.art("tscast_stage1_metrics.json")
    if not os.path.exists(mp):
        return False, ["     FAIL tscast_stage1_metrics.json missing -- train a model before "
                       "accepting a UI that claims to display its numbers"]
    j = json.load(open(mp))
    m, o = j["metrics"], j["metrics"]["overall"]

    at = AppTest.from_file(os.path.join(ROOT, "app", "phase2", "tscast_page.py"),
                           default_timeout=300)
    at.run()
    if at.exception:
        return False, ["     FAIL page raised: "
                       + "; ".join(str(e) for e in at.exception)[:220]]

    shown = {x.label: x.value for x in at.metric}

    def num(label):
        v = shown.get(label)
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return None

    # every float in the artifacts, rounded to 4 -- the set a rendered value may come from
    def floats(obj, acc):
        if isinstance(obj, dict):
            [floats(v, acc) for v in obj.values()]
        elif isinstance(obj, list):
            [floats(v, acc) for v in obj]
        elif isinstance(obj, (int, float)) and np.isfinite(obj):
            acc.add(round(float(obj), 4))
        return acc

    allowed = floats(j, set())
    for extra in ("mc_calibration.json", "tscast_coverage.json"):
        if os.path.exists(config.art(extra)):
            floats(json.load(open(config.art(extra))), allowed)

    rendered = {k: num(k) for k in shown if num(k) is not None}
    stray = {k: v for k, v in rendered.items() if round(v, 4) not in allowed}

    kb, ks = int(np.nanargmin(m["rmse"])), int(np.nanargmin(m["skill_rmse_ratio"]))
    skill_label = next((k for k in shown if k.lower().startswith("skill")), "")

    checks = [
        (num("RMSE vs independent Argo (°C)") == round(o["rmse"], 4),
         f"headline RMSE rendered {shown.get('RMSE vs independent Argo (°C)')} "
         f"== metrics JSON {o['rmse']:.4f}"),
        (num("Correlation (mean of 15 depths)") == round(o["correlation"], 4),
         f"correlation rendered == JSON {o['correlation']:.4f} (the per-depth mean, NOT the "
         f"pooled {o['correlation_pooled']:.4f})"),
        (num("Bias, model − truth (°C)") == round(o["bias"], 4),
         f"bias rendered == JSON {o['bias']:+.4f}, model-minus-truth convention"),
        (num(skill_label) == round(o["skill_rmse_ratio"], 4),
         f"skill rendered == JSON skill_rmse_ratio {o['skill_rmse_ratio']:.4f}, NOT the Murphy "
         f"score {o['skill_vs_climatology']:.4f}"),
        ("rmse" in skill_label.lower() and "clim" in skill_label.lower(),
         f"the skill tile NAMES its definition: {skill_label!r}"),
        (not stray,
         f"every rendered number is sourced from an artifact "
         f"(unsourced: {stray or 'none'})"),
        (any(f"{m['rmse_climatology'][ks]:.3f}" in t.value for t in at.info + at.caption)
         and any(f"{m['rmse'][kb]:.4f}" in t.value for t in at.info + at.caption),
         f"the skill/absolute pair is stated: worst skill at {m['depths_m'][ks]} m is shown "
         f"with climatology's own {m['rmse_climatology'][ks]:.3f} °C, and best absolute "
         f"{m['rmse'][kb]:.4f} °C at {m['depths_m'][kb]} m"),
        (any("CACHED" in b.value or "LIVE" in b.value
             for b in at.markdown + at.caption),
         "the numbers carry a CACHED-vs-LIVE badge"),
    ]
    lines = [("     " + ("ok   " if c else "FAIL ") + t) for c, t in checks]
    return all(c for c, _ in checks), lines
```

**[VERIFIED] every harness call above:** `AppTest.from_file(script_path, *, default_timeout=3)`; `at.run()`; `at.exception` (empty `ElementList()` when clean); `at.metric` yields elements with `.label`, `.value`, `.delta`; `at.metric` **descends into `st.tabs`, `st.columns` and `st.expander`**; `at.info`, `at.caption`, `at.markdown`, `at.error`, `at.warning` all exist. Default timeout is 3 s — you must pass a real one.

**Why this shape and not an import check:** `accept.py`'s own header says it, and the repo has the scar — 130 tests green while the model returned 52 °C from a 28 °C input. The `stray` check is the important one: it makes *any* hardcoded number a failure, including one that happens to be correct today.

---

### 5.8 Altair gotchas for exactly these chart types

All verified in this clone: **streamlit 1.62.0, altair 6.2.2, targeting Vega-Lite v6.4.1.**

1. **Why altair, not plotly.** The recorded reason is in `app/panels/_viz.py:5-7`: altair ships with Streamlit; matplotlib and plotly are in `requirements.txt` but *are not guaranteed to be installed on a teammate's or a demo machine*, and a panel that ImportErrors on demo day is worse than a plainer chart. **[VERIFIED] plotly 7.0.0 *is* installed in this clone's `.venv`** — that does not license using it. The rule is about the machine the demo runs on, not this one. `accept.py:check_f2b` already enforces the same principle at the module level (`"the volume layer imports NO plotting library"`).

2. **The depth axis is inverted with `scale=alt.Scale(reverse=True)`, on a `:Q` encoding.** [VERIFIED] `alt.Y("depth_m:Q", scale=alt.Scale(reverse=True))` emits `{'scale': {'reverse': True}}`. Do **not** negate the depth values, and do **not** use `sort="descending"` (that is for ordinal/nominal channels and silently does nothing here). `st.line_chart` cannot do this at all — it puts the index on x, which is how a depth axis once ended up running sideways to −100 m (`collocation_page.py:158-161`).

3. **A line does NOT break at a dropped row — it connects across the gap.** Vega-Lite filters invalid values by default, so `.dropna()` before charting *joins* the two sides of a below-seafloor gap and draws water where there is rock. **Keep the NaN row** and set `mark_line(point=True, invalid="break-paths-show-domains")` — [VERIFIED] valid in altair 6.2.2. This is the one place where `collocation_page.py:164` (`.dropna()`) is the pattern **not** to copy for below-seafloor depths.

4. **`scale=alt.Scale(zero=False)` on the temperature axis, always.** A 24–30 °C profile plotted against a zero baseline is a flat vertical line.

5. **The ±σ ribbon is `mark_area` with `x` / `x2` and a shared `y`.** [VERIFIED] `alt.X2("hi:Q")` is accepted. **Sort the frame by `depth_m` ascending before charting** or the ribbon self-intersects. Layer with `band + model + argo`; define the `y` encoding **once** as a variable and reuse it in every layer so all three share the reversed scale.

6. **Coverage and ratio bars: depth on an `:O` (ordinal) axis, with an explicit `sort`.** A `:Q` depth axis stacks 0/5/10/20/30 m on top of each other and gives 1000 m two-thirds of the plot. Pass `sort=list(config.DEPTHS)` explicitly — an ordinal axis fed strings would sort lexicographically ("1000" before "20").

7. **Reference lines are their own layer** from a one-row frame: `alt.Chart(pd.DataFrame({"v":[0.6827]})).mark_rule(strokeDash=[4,4]).encode(x="v:Q")`. [VERIFIED] layering a bar chart with a rule produces a 2-layer spec.

8. **Colour: model `#4c8dff` (blue), observation `#f5a524` (amber).** The recorded reason (`collocation_page.py:171-174`): two shades of blue made the reanalysis and the real float nearly impossible to tell apart, which hides the point of the plot. Keep the mapping consistent across every v2 chart, and pass `alt.Scale(domain=[...], range=[...])` with the domain listing the **exact** series strings you used — a typo silently recolours.

9. **`st.altair_chart(chart, width="stretch")`.** [VERIFIED] the 1.62 signature is `(altair_chart, *, width=None, height="content", use_container_width=None, theme="streamlit", key=None)`; `use_container_width` is the deprecated spelling.

10. **Tooltips are invisible to `AppTest` and to a projector.** Any explanation that exists *only* in a tooltip is, for acceptance purposes, not rendered. Every `reason` string must also appear in the table or an expander.

11. **Streamlit magic:** a bare expression at statement level gets rendered — that is how a stray `None` badge once reached the UI (`validation_page.py:20-21`). Assign or explicitly render every call.

---

### 5.9 Tests — `tests/phase2/test_v2_ui.py`

Follow `tests/test_panels.py`: render through `AppTest`, don't just import. Use `AppTest.from_string` with a prelude that inserts `.` and `src` on `sys.path`, and `default_timeout=120`.

| test name | asserts |
|---|---|
| `test_page_renders_with_no_checkpoint` | monkeypatch `sources.get_predictor` to return `(None, "RuntimeError: Missing key(s)...")`; `at.error` is non-empty and contains the exception text — a missing checkpoint produces a **refusal that quotes the reason**, not a blank tab and not `at.exception`. |
| `test_below_seafloor_renders_as_a_refusal_with_the_real_depth` | feed a record with `valid[10:] = False`, `seafloor_depth_m=30.0`; some `at.warning`/`at.markdown` contains `"30 m"`, and no rendered value for those depths parses as a float. |
| `test_seafloor_line_breaks_rather_than_dropping_rows` | on that record, `profile_frame` returns **15 rows** (NaN, not dropped) and `profile_chart(...).to_dict()` has `mark.invalid == "break-paths-show-domains"` on the temperature layer. |
| `test_forecast_carries_no_accuracy_number` | record with `forecast=True`, `argo_check=None`; `"FORECAST"` appears in an `at.error`/`at.markdown`, and **no** `at.metric` label contains `RMSE`, `skill`, `bias` or `correlation`. |
| `test_forecast_record_refuses_an_argo_check` | `pytest.raises(ValueError)` on `output.build_record(..., forecast=True, argo_check={})` — proves the contract is enforced in the record, not only in the page. |
| `test_no_argo_says_so_rather_than_showing_zero` | record with `argo_check=None`, `forecast=False`; the phrase `"no independent float within range"` is rendered, and no metric value is `"0.0000"`. |
| `test_depth_axis_is_inverted` | `profile_chart(df).to_dict()["layer"][0]["encoding"]["y"]["scale"] == {"reverse": True}` — this is the bug that shipped once already. |
| `test_reasons_are_rendered_outside_the_tooltip` | every string in `rec["reasons"]` for a valid depth appears in `at.dataframe` content or `at.markdown` — not only in the chart spec. |
| `test_skill_tile_names_its_definition` | the rendered skill label contains both `RMSE` and `clim`. |
| `test_coverage_masking_drops_and_does_not_fill` | call the `coverage()` helper with a column where `argo` is all-NaN → that depth reports `n=0` with a `note`, **not** `coverage=0.0`. |
| `test_coverage_below_the_floor_is_not_reported` | 29 usable pairs → `note` mentioning the 30-profile floor; 30 → a real number. |
| `test_metrics_missing_is_a_refusal_not_an_empty_tab` | delete/patch the artifact path → `at.error` non-empty, naming the script to run. |

Run: `.venv\Scripts\python.exe -m pytest tests/phase2/test_v2_ui.py -q`

---

### 5.10 Commands and expected output

```
# 1. produce the coverage artifact (needs a loadable checkpoint -- Phase 3)
.venv\Scripts\python.exe scripts\phase2\measure_coverage.py
    -> prints a depth / n / rms_sigma / cov_1sigma / cov_2sigma table
    -> "wrote artifacts\tscast_coverage.json"

# 2. run the page
.venv\Scripts\python.exe -m streamlit run app\phase2\tscast_page.py --server.port 8507
    -> http://localhost:8507 , four tabs, no traceback in the terminal

# 3. tests
.venv\Scripts\python.exe -m pytest tests\phase2\test_v2_ui.py -q

# 4. acceptance
.venv\Scripts\python.exe scripts\phase2\accept.py
    -> "3. FEATURE SCIENCE CHECKS"
       [ok]  v2 UI
             ok   headline RMSE rendered 0.9267 == metrics JSON 0.9267
             ok   ... every rendered number is sourced from an artifact (unsourced: none)
    -> "ACCEPTED -- safety, full suite, data bundle and feature science all pass."
```

**Every number in that expected output is from the artifact as it stands on 2026-08-30 and will change when Phase 4 retrains.** That is the point of the check: it reads the JSON, so it follows the model.

---

### 5.11 DONE checklist

- [ ] `app/phase2/tscast_page.py` exists on **port 8507**, docstring states the frozen-app rule and the launch command; `git status` shows **zero** changes to `app/streamlit_app.py` or `app/panels/`.
- [ ] `app/phase2/v2/{__init__,sources,profile_tab,benchmark_tab,calibration_tab,honesty_tab}.py` exist; `sources.py` is the only module that opens a file.
- [ ] Profile tab: σ band from `sigma_t` (never re-derived from `log_var_t`); depth axis inverted; line **breaks** at the sea floor; all 15 `reasons` rendered outside the tooltip.
- [ ] `argo_check` panel shows prediction | float | **signed** difference, with distance / days / quality / `quality_reason`, and prints "no independent float within range" when there is none.
- [ ] Below-seafloor depths render as a refusal quoting `rec["seafloor_depth_m"]`; verified live at **26.00°N 52.50°E** (sea floor 30 m).
- [ ] A date past **2026-06-23** renders **FORECAST** with zero accuracy numbers anywhere on the tab; a date between 2026-06-23 and 2026-08-24 explains the GLORYS/Argo asymmetry.
- [ ] Benchmark tiles read `metrics.overall`; the skill tile **names** its definition; `rmse_climatology` sits beside every skill number; the skill-vs-absolute caption is **computed** from `argmin`, not hardcoded to 1000 m.
- [ ] The 0 m row is flagged as 21 profiles; the test window follows the §5.4.5 precedence and says which branch it took.
- [ ] CACHED (VERIFIED) / LIVE badge present, carrying `checkpoint`, `code_commit`, `seed`; a missing artifact produces a refusal, not an empty tab.
- [ ] Calibration tab shows the per-depth ratio for v2 beside MC-dropout's, both `n` values visible, the "ratio > 1 = too narrow" reading verbatim, 0 m marked not-reported, and the 1000 m ratio of 0.701 named as the *opposite* failure.
- [ ] `scripts/phase2/measure_coverage.py` written, run, `artifacts/tscast_coverage.json` produced; registered in `accept.py`'s `DERIVED`; the JSON carries `method`, `masking_rule`, `max_days_offset=5`, `n_profiles`, `seed`, `checkpoint`, `code_commit`.
- [ ] Coverage bars at 1σ and 2σ with dashed rules at 0.6827 / 0.9545; `n < 30` reports NaN with a note, never 0.0.
- [ ] Honesty tab lists all eleven items of §5.6, each with its source artifact, recomputed at render time.
- [ ] `check_v2_ui` added to `accept.py` `CHECKS`; it asserts rendered numbers equal the metrics JSON **to 4 decimals** and that **no** rendered number is unsourced.
- [ ] `tests/phase2/test_v2_ui.py` — all twelve tests pass.
- [ ] Full `pytest -q` green; `python scripts/phase2/accept.py` prints **ACCEPTED**.
- [ ] `docs/HANDOFF.md` updated; an `AGENT_SYNC.md` entry with screenshots of all four tabs and the real `accept.py` output pasted, not paraphrased.
- [ ] Committed on `phase2-tscast-nio`. `main` untouched.

## PHASE 6 — Handback, step by step

Do all seven. Phase 6 is not "write a summary"; it is the Definition of DONE made auditable.

**6.1 — Final test run, recorded verbatim.**
```powershell
.venv\Scripts\python.exe -m pytest -q
```
Copy the real summary line. Baseline before your work: **370 tests collected** [VERIFIED]. If your work adds tests, the number goes up; if it goes down, say why. If anything fails, **do not proceed to 6.2** — a red suite is not handed back green.

**6.2 — Acceptance run.**
```powershell
.venv\Scripts\python.exe scripts/phase2/accept.py
```
Must end `ACCEPTED -- safety, full suite, data bundle and feature science all pass.` (exit 0). If it prints `REJECTED -- failed: <names>`, paste the failing block into your handback and fix or explain it. Never edit a check's threshold to make it pass — CLAUDE.md's real-data-only rule and "never adjust a scientific test to accommodate bad data".

**6.3 — Backfill `docs/EXPERIMENT_LOG.md`.** [VERIFIED: the file currently contains **six** entries, all Phase-1 model comparisons, and **zero** TS-Cast runs. Every v2 training run to date is unlogged. This is the gap.]

Required fields per CLAUDE.md ("For ML also: training done, validation done, metrics + checkpoint + seed + config logged"), in the file's own template:
```
## tscast-stage1 <YYYY-MM-DD HH:MM>
model: TSCastNIO(encoder=cnn3d, residual=True, decoder=simple, latent=128, unet=(32,64,128))
dataset+version: daily bundle data/processed/daily/*.npz, 388 days 2025-06-01..2026-06-23, 5 channels (wind absent)
split: DAILY_TRAIN 2025-06-01..2026-03-31 (304 d) / DAILY_TEST 2026-04-01..2026-06-23 (84 d), temporal holdout
seed: 42
hyperparams: T_SEQ=31 P=17 loss=nll beta=0.5 lr=1e-3 batch=256 epochs_requested=15 epochs_run=8 best_epoch=4 patience=4 weight_decay=0.01 train_samples=40000
hardware: cpu | train_seconds: 8037.1
git-commit: <git rev-parse --short HEAD>
metrics: overall RMSE=0.9267 bias=+0.2515 corr(per-depth mean)=0.8824 skill_vs_clim(Murphy)=0.4286 | rmse_by_depth=[...15 values from artifacts/tscast_stage1_metrics.json...]
reference: 962 independent Argo profiles, max_days_offset=5
climatology prior: artifacts/clim_daily.npz, train_years [2019,2020,2021] — disjoint from the 2025/26 target, no leakage path
checkpoint: artifacts/tscast_stage1.pt (BEST held-out epoch, not the last)
notes: <what this run changed vs the previous one, and what is still unverified>
```
Every number above is **read out of `artifacts/tscast_stage1_metrics.json`**, not typed from memory. Do not log a run whose checkpoint is not on disk.

> **DECISION — where the entry goes.** The file header says *"append-only, newest on top"* but the six existing entries are physically ordered **oldest → newest**, so the header and the file disagree. **Recommended default: append at the bottom, matching what the file actually does**, and note the discrepancy in your HANDOFF entry so Unit C can settle it. Reordering someone else's log to match a header is a worse outcome than one inconsistent line.
>
> **Ownership note:** `docs/EXPERIMENT_LOG.md` is Unit C's file under CLAUDE.md's ownership table, while the Definition of DONE requires you to log there. Append your own entry; do not edit or reformat anyone else's.

**6.4 — Append to `docs/HANDOFF.md`.** Newest on top, using the file's own template:
```
## YYYY-MM-DD — Unit A / Darshan's session (phase2-tscast-nio)
CURRENT PHASE: | BRANCH: phase2-tscast-nio | WHAT WORKS [VERIFIED]: | WHAT IS BROKEN: |
LAST CHANGE: | FILES MODIFIED: <exact paths> | TESTS RUN: <the real pytest line> |
KNOWN ISSUES: | NEXT TASK: | BLOCKERS:
```
Tag every claim `[VERIFIED]` / `[INFERRED]` / `[UNKNOWN]`. "WHAT WORKS" admits only things you executed.

**6.5 — Update `PHASE2_STATUS.md`** (repo root). Move only the rows you actually touched, using the file's vocabulary: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `TESTED` · `VALIDATED` · `DEMO READY`. The file's own rule: **a feature is never VALIDATED because unit tests pass.** TESTED = the code does what the code intends; VALIDATED = the science was checked against an independent source (real Argo, or a documented physical expectation). Fill the `Tests` column with the real count and the `Known limitation` column with the honest one — the existing rows are frank about limits ("FRONTS ARE NOT [validated]", "NOT validated — needs real X_train.npy"), and yours must be too.

**6.6 — Append the AGENT_SYNC entry.** `docs/phase2/AGENT_SYNC.md`, **at the top of the LOG section** (immediately under the `# LOG (newest first)` line at the top of the log, above the current newest entry — this file genuinely is newest-first). Shape, matching the existing entries:

```markdown
## 2026-MM-DD [DARSHAN] <one-line headline that states the RESULT, not the activity>

**What I did.** 2-4 sentences. Files created/edited with exact paths.

**What I MEASURED [VERIFIED].** The numbers, with the command that produced them and its real
output pasted. No number here that you did not run.

**What I could NOT verify [UNKNOWN].** Name it. An unverified thing stated plainly is worth more
than a verified-sounding thing that is not.

**What I refused, and why.** e.g. "did not implement x_ssh_anom because clim_ssh does not exist in
clim_daily.npz and building it from the daily bundle's own SSH would put the test window into the
prior."

**Files changed.** <exact absolute-or-repo-relative paths>
**Tests.** <the real pytest summary line>  **accept.py.** ACCEPTED / REJECTED + the reason.

>>> ASK ARJHUN: <anything you need from the other unit — the human relays it>
```
Headlines in this file lead with the finding, e.g. *"DAILY DATA IS IN. The FiLM decoder was the regression, not the loss."* Never edit another agent's entry.

**6.7 — Commit and push.**
```powershell
git status --porcelain
git add <the exact files you changed>
git commit -m "<what changed and what it measured>"
git push origin phase2-tscast-nio
git rev-list --left-right --count origin/phase2-tscast-nio...HEAD    # must print: 0  0
```
Rules: commit to `phase2-tscast-nio` only; never `git push origin main`; do not `git add -A` (it would sweep in untracked local files such as `README_UNZIP_ME_FIRST.txt`); `data/` and `artifacts/` are gitignored and must stay that way — if a `git status` shows a `.npz`/`.pt`/`.parquet` as untracked-but-addable, something bypassed `.gitignore` and you should stop and check rather than commit it.

### DONE checklist for Phase 6

- [ ] `pytest -q` run, real summary line captured, no failures
- [ ] `scripts/phase2/accept.py` exits 0 with `ACCEPTED`
- [ ] `docs/EXPERIMENT_LOG.md` has an entry with model, dataset+version, split, **seed**, hyperparams, hardware, git-commit, metrics, **checkpoint path** — every number read from `artifacts/tscast_stage1_metrics.json`
- [ ] `docs/HANDOFF.md` entry appended, newest on top, every claim evidence-tagged
- [ ] `PHASE2_STATUS.md` rows updated; nothing marked VALIDATED on unit tests alone
- [ ] `docs/phase2/AGENT_SYNC.md` entry appended at the top of the LOG, tagged `[DARSHAN]`, with measured numbers, unknowns, and refusals
- [ ] Contract changes (if any) made **in the contract file first**, then posted to AGENT_SYNC, then coded
- [ ] Committed to `phase2-tscast-nio` and pushed; `origin/phase2-tscast-nio...HEAD` reads `0 0`
- [ ] `main` untouched: `git rev-parse main` still equals `git rev-parse origin/main`

## FROZEN CONSTANTS — import, never retype

Everything here lives in `src/oceanembed/config.py` and is re-exported by `src/phase2/tscast_nio/config.py`. Importing from either is correct; typing the value into your file is a contract violation (CLAUDE.md, "Contract-first rule").

| Constant | Value | Import path |
|---|---|---|
| `REGION` | `dict(lat_min=5.0, lat_max=30.0, lon_min=45.0, lon_max=105.0, step=0.25)` | `from oceanembed import config` → `config.REGION` |
| `LAT` | `float32[100]`, 5.00 → 29.75 step 0.25 | `config.LAT` |
| `LON` | `float32[240]`, 45.00 → 104.75 step 0.25 | `config.LON` |
| `N_LAT`, `N_LON` | `100`, `240` | `config.N_LAT`, `config.N_LON` |
| `DEPTHS` | `[0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]` metres | `config.DEPTHS` |
| `N_DEPTHS` | `15` | `config.N_DEPTHS` |
| `FEATURES` | `["sst","sss","ssh","u","v","sin_lat","cos_lat","sin_lon","cos_lon","sin_doy","cos_doy"]` — **this order** | `config.FEATURES` |
| `N_FEAT` | `11` | `config.N_FEAT` |
| `TRAIN_YEARS` / `TEST_YEARS` | `[2019,2020,2021]` / `[2022]` (monthly archive) | `config.TRAIN_YEARS`, `config.TEST_YEARS` |
| `SEED` | `42` | `config.SEED` |
| `ROOT`, `DATA_RAW`, `DATA_PROCESSED`, `ARTIFACTS` | absolute paths derived from `config.__file__` | `config.DATA_PROCESSED`, etc. |
| `art(name)` | `os.path.join(ARTIFACTS, name)` | `config.art("clim_daily.npz")` |
| `MLP` | `dict(hidden=(128,128), dropout=0.2, lr=1e-3, epochs=100, batch_size=256, mc_passes=30)` | `config.MLP` |

Units, stated because assuming them is rule 10: **`sst` degC** (never Kelvin), **`sss` psu**, **`ssh` m**, **`u`/`v` m s-1**, **`temp` degC**, depths in **metres**, `bias` in degC with the convention **model − truth, positive = model runs warm**.

TS-Cast tunables (`from phase2.tscast_nio import config as vcfg`) — these are modelling choices, not frozen science:

| Constant | Value | Note |
|---|---|---|
| `vcfg.CHANNELS` | `["sst","sss","ssh","u","v","wu","wv"]` (7) | contract order; the bundle on disk has only the first 5 |
| `vcfg.CHANNEL_UNITS` | `["degC","psu","m","m s-1","m s-1","m s-1","m s-1"]` | |
| `vcfg.T_SEQ` | `31` | `1` collapses the temporal encoder onto the monthly archive |
| `vcfg.P` | `17` (must be odd) | 17 cells at 0.25 deg = ±2.0 deg |
| `vcfg.LATENT_DIM` | `128` | |
| `vcfg.UNET_CHANNELS` | `(32, 64, 128)` | `PAPER_UNET_CHANNELS = (64,128,256,512)` kept for the record |
| `vcfg.INTERNAL_LEVELS` | `64`, range `(0.0, 1000.0)` | decoder works internally then resamples to the 15 contract depths |
| `vcfg.TRAIN` | `dict(epochs=250, lr=1e-5, batch_size=512, optimizer="adamw", val_fraction=0.2, n_ensemble=3)` | **note:** `train_stage1.py` argparse defaults are different (`--epochs 20 --lr 1e-3 --batch-size 256`) and the CLI is what actually runs |
| `vcfg.STAGE` | `1` | temperature + log-variance only |
| `D.DAILY_TRAIN` / `D.DAILY_TEST` | `2025-06-01..2026-03-31` / `2026-04-01..2026-06-23` | `from phase2.tscast_nio import dataset as D` |
| `inference.LAST_GLORYS` / `LAST_ARGO` | `2026-06-23` / `2026-08-24` | past these, `forecast=True` and no metric may be attached |
| `collocation.TEMPORAL_HIGH_D/MED_D/LOW_D` | `2.0 / 5.0 / 10.0` days | quality tiers |
| `collocation.DEFAULT_TOLERANCE_D` | `10.0` days | beyond → `REJECT` |
| `collocation.SPATIAL_MAX_KM` | `20.0` km | half-diagonal of a 0.25 deg cell is ~19.6 km |

**DECISION for the implementer — `vcfg.TRAIN` vs the trainer CLI.** `config.TRAIN` says `epochs=250, lr=1e-5, batch_size=512`; `train_stage1.py` defaults to `epochs=20, lr=1e-3, batch_size=256` and the recorded run used `lr=0.001, batch_size=256, epochs_requested=15`. Nothing in the repo reconciles them. **Recommended default: treat the CLI flags as authoritative and log exactly what you passed**, because the checkpoint metadata records the CLI values, not `config.TRAIN`. Do not "fix" `config.TRAIN` to match — that would silently change a value another module may read.

---

## CONTRACT SHAPES

### Daily bundle — `data/processed/daily/YYYY.npz`

| array | contract shape | **on disk [VERIFIED]** | dtype |
|---|---|---|---|
| `times` | `(T,)` | `(214,)` 2025, `(174,)` 2026 | `datetime64[D]` |
| `surface` | `(T,100,240,7)` | **`(T,100,240,5)`** | `float32` |
| `channels` | `(7,) <U4` | **`(5,) <U3`** = `sst,sss,ssh,u,v` | `<U3` |
| `units` | `(7,) <U8` | **`(5,) <U5`** = `degC,psu,m,m s-1,m s-1` | `<U5` |
| `temp` | `(T,100,240,15)` | `(T,100,240,15)` | `float32` |
| `salinity` | `(T,100,240,15)` | `(T,100,240,15)` | `float32` |
| `land_mask` | `(100,240)` | `(100,240)` | `bool` |
| `valid_mask` | `(100,240,15)` | `(100,240,15)` | `bool` |
| `missing_days` | `(M,)` | `(0,)` — no gaps | `datetime64[D]` |
| `provenance` | `()` JSON string | `() <U362` | `<U` |

> **DECISION — the bundle is 5 channels, the contract says 7.** Wind (`wu`,`wv`) is absent; the bundle's own provenance says so: *"5 of the contract's 7; wind needs the hourly NRT product"*. The contract file has not been amended. Per CLAUDE.md's contract-first rule the fix is to **edit `docs/phase2/tscast_data_model.md` first, post to AGENT_SYNC, then code** — not to quietly write 7-channel code that never sees wind. **Recommended default: keep building against `len(d["channels"])` read from the data (which every existing consumer already does — `GriddedPatches` sets `self.C = surface.shape[-1]`), and add one line to the contract's section 2 recording that the shipped bundle is 5-channel with wind pending.** Do not pad two zero channels to reach 7: a constant channel teaches the model that wind is irrelevant.

### Climatology prior — `artifacts/clim_daily.npz`

| array | contract | **on disk [VERIFIED]** |
|---|---|---|
| `clim_t` | `(12,100,240,15)` | `(12,100,240,15) float32` |
| `clim_s` | `(12,100,240,15)` | **absent** |
| `clim_ssh` | `(12,100,240)` | **absent** |
| `train_years` | `(Y,)` | `(3,) int64` = `[2019 2020 2021]` |
| `drift_by_depth` | not in contract | `(15,) float32` — extra, measured staleness |
| `provenance` | not in contract | `() <U1844` JSON |

> **DECISION — `clim_s` and `clim_ssh` do not exist.** `clim_s` is a stage-2 field and stage 2 is not enabled (`vcfg.STAGE == 1`), so its absence is expected. **`clim_ssh` is not**: `tscast_data_model.md` section 4 needs it for `x_ssh_anom`. **Recommended default: if you implement `x_ssh_anom`, build `clim_ssh` from the same 2019-2021 monthly source inside `build_daily_climatology.py` and add it to the same npz — never from the daily bundle's own SSH, which would put the test window into the prior.** If you do not implement `x_ssh_anom`, say in HANDOFF that it remains unimplemented rather than leaving the contract looking satisfied.

### One model sample — `GriddedPatches.__getitem__(k)`

Default (`return_clim=False`) returns a **5-tuple**; with `return_clim=True` a **7-tuple**. [VERIFIED — `dataset.py:138-146`.]

| position | name | shape | dtype |
|---|---|---|---|
| 0 | `x` | `(C, T_SEQ, P, P)` — C from the data (5 today), P=17 | `torch.float32` |
| 1 | `x_geo` | `(3, 1, P, P)` — X/Y/Z broadcast over the patch | `torch.float32` |
| 2 | `y_z` | `(15,)` — z-scored target, 0.0 where invalid | `torch.float32` |
| 3 | `y_valid` | `(15,)` | `torch.bool` |
| 4 | `latlon` | `(2,)` = `[lat, lon]` degrees | `torch.float32` |
| 5 | `cp_z` | `(12, 15)` — all 12 monthly climatology profiles at that cell, z-scored | `torch.float32` |
| 6 | `month` | scalar 0-11 | `torch.int64` |

> **Contract gap, state it plainly:** the contract lists `x_ssh_anom` `(1, T_SEQ, 12)` as part of a sample. **It is not implemented** — no such tensor is produced anywhere in `dataset.py`. [VERIFIED by reading the whole of `__getitem__`.] The contract also writes `clim_prior` as `(12, 15, C_out)`; the code returns `(12, 15)` because `C_out == 1` at stage 1. Treat the missing trailing axis as a documentation shorthand, and the missing `x_ssh_anom` as **unimplemented work, not a satisfied contract.**

### Prediction record — `output.build_record(...)` return

Keys, in order, from `docs/phase2/tscast_output_schema.md` section 1 and confirmed against `output.py:109-150`:

`depths_m [15] int` · `temperature [15] float|None` (None where `valid` is False) · `log_var_t [15] float` · `sigma_t [15] float|None` = `sqrt(exp(log_var_t))` · `valid [15] bool` · `seafloor_depth_m float` · `salinity`/`log_var_s`/`density`/`log_var_rho` (stage-2 keys, `None` today) · `reasons [15] str` · `argo_check dict|None` · `forecast bool` · `provenance dict`.

`build_record` **raises `ValueError`** if any of `temperature`/`log_var_t`/`valid` is not exactly `(15,)`, and **raises** if `forecast=True` and `argo_check is not None`. Both refusals are deliberate — do not soften them.

`argo_check` sub-record (`output.build_argo_check`): `argo_temperature [15]` · `difference [15]` (model − argo, signed) · `profile_id` · `distance_km` · `days_offset` · `quality` in `HIGH|MEDIUM|LOW|REJECT` · `quality_reason` · `source` in `argopy|incois_las`.

`provenance` sub-record: `model`, `checkpoint_sha256`, `seed`, `T_SEQ`, `P`, `encoder`, `input_source`, `input_date`, `clim_train_years`, `code_commit`.

### Aggregate metrics record — `metrics.per_depth(...)` return

`depths_m [15]` · `rmse [15]` · `correlation [15]` · `bias [15]` · `skill_vs_climatology [15]` · `skill_rmse_ratio [15]` · `rmse_climatology [15]` · `n [15] int` · `reference` · `window` · `bias_convention` · `not_to_be_confused_with` · `overall{rmse, bias, correlation_pooled, correlation, skill_vs_climatology, skill_rmse_ratio, skill_note, n, correlation_note}`.

Two rules the module enforces in its own output strings and you must respect when reporting: quote **`overall["correlation"]`** (mean of per-depth), never `correlation_pooled`, which mostly measures that deep water is cold; and **never quote one skill definition beside the other** — `skill_rmse_ratio` (1 − RMSE/RMSE_clim, what the frozen Phase-1 headline +0.387 uses) and `skill_vs_climatology` (Murphy, 1 − MSE/MSE_clim) read 0.39 and 0.63 on the same predictions. `rmse_climatology` is shown **beside** skill, always.

---

## API CHEAT-SHEET — real signatures, verified on disk

**`src/oceanembed/config.py`**
```python
config.art(name: str) -> str          # os.path.join(ARTIFACTS, name)
config.sanity_check() -> None         # asserts 100x240, 15 depths, 11 features, surface order
```

**`src/oceanembed/utils/grids.py`** — the frozen nearest-centre convention
```python
nearest_lat_index(lat: float) -> int          # argmin(|config.LAT - lat|)
nearest_lon_index(lon: float) -> int
latlon_to_cell_id(lat: float, lon: float) -> int      # i * N_LON + j
cell_id_to_latlon(cell_id: int) -> tuple[float, float]
day_of_year_features(doy: int) -> tuple[float, float]
latlon_features(lat: float, lon: float) -> tuple[float, float, float, float]
```

**`src/oceanembed/utils/io.py`**
```python
save_table(df: pd.DataFrame, path_noext: str) -> str   # parquet, csv fallback
load_table(path_noext: str) -> pd.DataFrame            # NOTE: pass the path WITHOUT extension
save_npy(arr, path) / load_npy(path) / save_json(obj, path) / load_json(path)
```
`config.art("argo_test")` — no `.parquet` — is the correct argument to `load_table`.

**`src/phase2/tscast_nio/dataset.py`**
```python
cell_index(lat, lon) -> tuple[np.ndarray, np.ndarray]      # arrays i, j; delegates to grids.*
geo_encoding(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray   # (..., 3) = X, Y, Z

class GriddedPatches(torch.utils.data.Dataset):
    def __init__(self, surface, temp, times, land_mask, channels,
                 t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None,
                 stride=1, clim=None, return_clim=False)
    norm -> tuple            # property: (mean, std, y_mean, y_std)
    __len__() -> int
    __getitem__(k) -> tuple  # 5-tuple, or 7-tuple when return_clim=True

load_monthly(path=None) -> dict      # keys: surface temp times land_mask valid_mask channels
load_daily(d=None)      -> dict      # same keys (+ salinity); default data/processed/daily
daily_split_indices(times) -> (tr, te)
split_indices(times, train_years=None, test_years=None) -> (tr, te)
```
**`cell_index` is not `np.searchsorted(LAT, lat) - 1`.** The two conventions disagree on 75.5% of real Argo profiles by one cell (~28 km). The frozen pipeline (`predict.py`, `glorys_vs_argo.py`) uses nearest-centre. Call `cell_index`; do not reimplement it. [VERIFIED — `dataset.py:29-42` docstring.]

`GriddedPatches` with `return_clim=True` and `clim=None` **raises `ValueError`** ("refusing to fabricate a zero prior"). `daily_split_indices` **asserts** no overlap and that test starts after train ends. Both are refusals — keep them.

**`src/phase2/data/collocation.py`** (F1, VALIDATED — do not write a second matcher; that is the D-014 failure)
```python
@dataclass
class Collocation:
    requested: dict; matched: dict; offsets: dict
    sources: dict; quality: str; flags: list; provenance: dict
    def to_dict(self) -> dict

class CollocationEngine:
    def __init__(self, tolerance_days: float = DEFAULT_TOLERANCE_D,
                 spatial_method: str = "nearest")           # "nearest" | "bilinear"
    def collocate(self, latitude: float, longitude: float, datetime, *,
                  include_profile: bool = True) -> Collocation

collocate(latitude: float, longitude: float, datetime, **kw) -> dict   # module-level, cached engine
```
**Gotcha:** `CollocationEngine.collocate` returns a `Collocation` **object**; the module-level `collocate` returns a **dict**. `accept.py:276` uses the object form (`ocean.quality`, `ocean.offsets["spatial_km"]`).
Record keys: `offsets = {"spatial_km", "temporal_days", "spatial_method"}`; `matched = {latitude, longitude, datetime, grid_i, grid_j, time_index, cell_id}`; `sources = {"glorys", "subsurface", "satellite", "argo"}` (any may be `None`). Flags seen in practice: `OUTSIDE_DOMAIN`, `LAND_IN_GLORYS`, `SPATIAL_OFFSET_EXCEEDS_CELL`, `TEMPORAL_OFFSET_EXCEEDS_TOLERANCE`, `SATELLITE_UNAVAILABLE`, `SATELLITE_OUTSIDE_TOLERANCE`, `SUBSURFACE_UNAVAILABLE`, `NO_ARGO_NEARBY`, `COASTLINE_DISAGREEMENT_SATELLITE_SAYS_OCEAN`/`_LAND`. Quality is **derived from measured offsets**, never asserted. It raises `FileNotFoundError` if `data/processed/grids.npz` is absent.

**`src/phase2/tscast_nio/metrics.py`**
```python
rmse(pred, truth) -> float
bias(pred, truth) -> float                      # mean(model - truth), signed
correlation(pred, truth) -> float               # Pearson r
skill_vs_climatology(pred, truth, clim) -> float    # Murphy, 1 - MSE/MSE_clim
skill_rmse_ratio(pred, truth, clim) -> float        # 1 - RMSE/RMSE_clim
per_depth(pred, truth, clim=None, reference: str = "argo", window=None) -> dict
```
`per_depth` **raises `ValueError`** on shape mismatch or when the last axis is not 15. Depth must be the **last** axis; leading shape is free.

**`src/phase2/tscast_nio/output.py`**
```python
measured_rmse_by_depth() -> tuple[list | None, str]
build_reasons(sigma, valid, seafloor_depth_m, rmse=None) -> list[str]
build_argo_check(argo_temperature, temperature, profile_id, distance_km, days_offset,
                 source="argopy") -> dict
build_record(temperature, log_var_t, valid, seafloor_depth_m, provenance,
             argo_check=None, forecast=False, salinity=None, log_var_s=None,
             density=None, log_var_rho=None) -> dict
```

**`src/phase2/tscast_nio/encoders.py` / `models/tscast.py`**
```python
build(name: str, c_in: int, t_seq: int, p: int, n_depths: int, latent: int = 128) -> Candidate
n_params(m: nn.Module) -> int
class TSCastNIO(nn.Module):
    def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None,
                 latent: int = None, residual: bool = True, unet_channels=None,
                 decoder: str = "film")
```
Encoder names: `mlp_control`, `cnn3d`, `cnn_attention`, `vit`. `mlp_control` is a genuine blind control — `accept.py` asserts it does **not** react to a perturbed neighbour cell while `cnn3d` does.

**`src/phase2/tscast_nio/inference.py`**
```python
class TSCastPredictor:
    def __init__(self, checkpoint: str | None = None, data: dict | None = None,
                 clim: np.ndarray | None = None)
LAST_GLORYS = np.datetime64("2026-06-23");  LAST_ARGO = np.datetime64("2026-08-24")
```
It raises `FileNotFoundError` with no checkpoint, and `ValueError` if the checkpoint's channel list differs from the loaded data's. Checkpoint dict keys it relies on: `state_dict, channels, encoder, T_SEQ, P, latent, residual, norm`.

**`src/phase2/tscast_nio/daily_pipeline.py`**
```python
build_year(files: list[str], year: int, out_dir: str, with_salinity: bool = True) -> str
```

---

## COMMAND CHEAT-SHEET — `scripts/phase2/` (real flags only)

Prefix everything with `.venv\Scripts\python.exe`. With the editable install, `PYTHONPATH` is not needed; several docstrings show `PYTHONPATH=src` (bash form) — in PowerShell that is `$env:PYTHONPATH="src"`.

| Command | Flags that exist | Purpose |
|---|---|---|
| `scripts/phase2/accept.py` | *(none)* | **The one command that decides.** Runs SAFETY → full pytest → `verify_data_bundle.py` → regenerate derived artifacts → per-feature science checks. Exit 0 = ACCEPTED, exit 1 = REJECTED. |
| `scripts/phase2/verify_data_bundle.py` | *(none)* | FILES / CONTRACT / SCIENCE on the Phase-1 monthly bundle. |
| `scripts/phase2/verify_daily_bundle.py` | `--dir <path>` (default `data/raw/daily`), `--full` | Verifies **raw NetCDF** before preprocessing: depth bracket, Kelvin, reversed depth axis, missing days, reanalysis-vs-forecast, grid coverage. `--full` opens every file. |
| `python -m phase2.tscast_nio.daily_pipeline` | `--raw-dir`, `--out-dir`, `--no-salinity`, `--limit N` | Raw daily NetCDF → `data/processed/daily/YYYY.npz`. `--limit` for a smoke test. |
| `scripts/phase2/download_daily_2025_2026.py` | *(none)* | Overnight, resumable GLORYS + satellite L4 download for 2025-06-01..2026-06-23. |
| `scripts/phase2/fetch_argo_daily_period.py` | *(none)* | Independent Argo for the daily window → `artifacts/argo_daily_period.parquet`. |
| `scripts/phase2/build_daily_climatology.py` | *(none)* | Writes `artifacts/clim_daily.npz` from the 2019-2021 climatology and measures the 2019-21 → 2025/26 drift. |
| `scripts/phase2/measure_v2_metrics.py` | *(none)* | Writes `artifacts/tscast_baseline_metrics.json`. |
| `scripts/phase2/architecture_feasibility.py` | `--quick`, `--epochs N` (8), `--train-samples N` (40000), `--test-samples N` (12000) | The 4-way encoder bake-off → `artifacts/architecture_feasibility.json`. Long; do not re-run casually. |
| `scripts/phase2/glorys_vs_argo.py` | *(none)* | GLORYS-vs-Argo reanalysis error → `artifacts/glorys_vs_argo.json`. Auto-regenerated by `accept.py`. |
| `scripts/phase2/measure_mc_calibration.py` | *(none)* | → `artifacts/mc_calibration.json`. Auto-regenerated by `accept.py`. |
| `scripts/phase2/pick_tseq_and_retrain.py` | `--log <path>` (**required**), `--recorded`, `--recorded-source`, `--dry-run` | Parses a T_SEQ ablation log, picks the winner on independent Argo RMSE, retrains. |
| `scripts/phase2/try_collocation.py` | positional `lat lon date`, `--json`, `--dates`, `--tour` | Manual F1 probe. |
| `python -m phase2.tscast_nio.train.train_stage1` | `--epochs 20` · `--train-samples 40000` · `--test-samples 12000` · `--lr 1e-3` · `--batch-size 256` · `--encoder` · `--no-residual` · `--patience 4` · `--weight-decay 1e-2` · `--device auto` · `--num-workers 0` · `--latent` · `--unet-width N [N...]` · `--decoder film\|simple` · `--loss nll\|mse` · `--data monthly\|daily` · `--t-seq N` · `--beta 0.5` | Stage-1 training → `artifacts/tscast_stage1.pt` + `tscast_stage1_metrics.json`. |

> **`scripts/phase2/pick_tseq_and_retrain.py` was untracked at the time this brief was written** (`git status` showed `?? scripts/phase2/pick_tseq_and_retrain.py`). If `git ls-files scripts/phase2/pick_tseq_and_retrain.py` returns nothing after your pull, it did not travel — that is a missing file, not a missing feature.

---

## TEST CONVENTIONS

**Where.** Baseline Phase-1 tests in `tests/*.py` (**read-only** — AGENT_SYNC rule 2). Phase-2 tests in `tests/phase2/*.py`. TS-Cast tests are `tests/phase2/test_tscast_<module>.py`, one file per module: `test_tscast_dataset.py`, `test_tscast_encoders.py`, `test_tscast_metrics.py`, `test_tscast_model.py`, `test_tscast_output.py`, `test_tscast_train.py`. A new TS-Cast module gets `tests/phase2/test_tscast_<module>.py`. **Never create `tests/phase2/__init__.py`.**

**Naming.** Test functions are full sentences stating the failure they prevent, not `test_foo_works`. Real examples from the branch:
- `test_western_edge_patch_is_filled_not_wrapped_from_the_east`
- `test_off_grid_cells_become_zero_after_zscoring_not_a_fabricated_value`
- `test_geo_encoding_is_a_unit_vector_matching_eq1`
- `test_load_argo_rejects_a_table_missing_contract_columns`

Docstrings say why the failure would be invisible ("a bug that trains cleanly and is invisible in the loss curve"). Follow that voice.

**Skipping when gitignored data is absent.** Three patterns are in use — pick the matching one:

1. Whole-file gate at module level:
```python
pytestmark = pytest.mark.skipif(
    not os.path.exists(GRIDS), reason="grids.npz absent (gitignored) -- real-data tests skipped")
```
2. Inside a fixture or test body:
```python
if not os.path.exists(GRIDS):
    pytest.skip("grids.npz absent (gitignored) -- real-data cube tests skipped")
```
3. Optional dependency: `xr = pytest.importorskip("xarray")`, `pytest.importorskip("lightgbm")`.

The reason string **always names the file and says `(gitignored)`**, so a skip reads as "data absent", never as "this passed".

Tests that must **not** skip: pure-logic tests. Every TS-Cast dataset/metrics/output test builds a toy array in-process (`_toy(n_t=6, n_lat=20, n_lon=30, n_c=5)` in `test_tscast_dataset.py`) and runs everywhere. `test_verify_daily_bundle.py` writes synthetic NetCDF files each carrying **one known defect** and asserts the verifier catches it — a verifier that passes everything is worse than no verifier.

**Running.**
```powershell
.venv\Scripts\python.exe -m pytest -q                                  # everything (370 collected)
.venv\Scripts\python.exe -m pytest tests/phase2 -q                     # phase 2 only
.venv\Scripts\python.exe -m pytest tests/phase2/test_tscast_dataset.py -q
.venv\Scripts\python.exe -m pytest -q -k "tscast and not train"
.venv\Scripts\python.exe -m pytest tests/phase2/test_tscast_dataset.py::test_western_edge_patch_is_filled_not_wrapped_from_the_east -q
.venv\Scripts\python.exe -m pytest -q -rs                              # show WHY things skipped
```
`pyproject.toml` supplies `pythonpath=["src"]` and `testpaths=["tests"]`, so run pytest from the repo root and pass no `-p` or `--rootdir`.

---

---

# APPENDIX — OPEN DECISIONS

Things the repo does **not** settle. Each has a recommended default and the reason. Taking the
default is fine; taking the other option is fine if you say why in AGENT_SYNC. What is not fine is
implementing one silently and leaving the next person to discover it.

## D1 — The collocation engine is pinned to 2022 Argo, so `argo_check` silently matches nothing
**Severity: highest. This will produce an empty panel that looks like a working one.**
`CollocationEngine._argo_table()` loads `artifacts/argo_test.parquet`, which is **2022 only**. Every
v2 date is in 2026. So today, for any v2 prediction, the engine matches **zero floats and says so
only as "no float nearby"** — indistinguishable from a genuinely unsampled ocean.
**Recommended:** add an `argo_table` parameter to `CollocationEngine.__init__` defaulting to
`"argo_test"` (so F1's validated behaviour is byte-identical) and pass `"argo_daily_period"` from
the v2 path. **Announce it in AGENT_SYNC first** — `collocation.py` is a VALIDATED file and this is
the contract-first rule. A test must assert a 2026 date returns a non-null `argo_check`, or the bug
comes straight back.

## D2 — `train_stage1.py` always builds the encoder with `t_seq=1`
Line 156: `model = TSCastNIO(enc, len(d["channels"]), t_seq=1, ...)` regardless of `--t-seq`. It is
harmless **only** because `cnn3d` never pools the time axis (`AdaptiveAvgPool3d`), so its weights do
not depend on the window length. Both builds accept the same `state_dict`, but their outputs differ
by up to 0.0695 °C on identical input — so train and serve are quietly not the same function.
**Recommended:** *pin*, don't fix — keep `t_seq=1` and write an `encoder_t_seq` key into the
checkpoint so inference reproduces training exactly. Fixing it properly invalidates every recorded
measurement and costs a re-run you do not have time for. **Add a guard** that refuses
`--encoder vit|mlp_control|cnn_attention` together with `--t-seq > 1`, because for those encoders
this silently mis-shapes instead of being harmless.

## D3 — 5 channels or 7 for the final retrain
**Recommended: run 5 channels first, unconditionally.** It is the only run guaranteed to finish, it
is comparable to the whole ablation, and it gives you a shippable number by morning. Then, if wind
landed, run 7 as a *separate single-variable change* so the delta means something. Do not make the
one overnight run depend on the one download that might fail. AGENT_SYNC hands you this decision
explicitly.

## D4 — Where the 7-channel bundle is written
Writing wind into `data/processed/daily/` **in place** destroys the 5-channel bundle every recorded
number rests on. **Recommended:** write `data/processed/daily7/` and point the trainer at it, so
both remain reproducible and the ablation stays re-runnable. Costs a directory; saves the ability to
compare.

## D5 — The monsoon test threshold
Do **not** invent a JJA/DJF wind-speed ratio. The **sign reversal** of the meridional/zonal
component over the western Arabian Sea between the SW and NE monsoon is threshold-free and should
carry the test. Add a magnitude floor only after you have measured it once and recorded the number.
If the measurement lands implausibly low, the data is wrong — not the threshold.

## D6 — Coverage: precomputed or live
The calibration panel needs coverage (fraction of Argo truth within ±1σ, ±2σ, per depth). Computing
it live means 962 profiles per Streamlit rerun.
**Recommended:** a `scripts/phase2/measure_coverage.py` writing `artifacts/tscast_coverage.json`,
which the UI renders. Consistent with the standing rule that the UI computes nothing scientific.
Neither the script nor the artifact exists yet, and `train_stage1.py` currently persists no
per-profile sigma — so this needs the trainer to save them, or a separate scoring pass.

## D7 — The metrics JSON contradicts itself; the UI must not paper over it
In `tscast_stage1_metrics.json`: `metrics.window` is `null`; `data: "daily"` and `T_SEQ: 31` sit
beside `train_years: [2019,2020,2021]` / `test_years: [2022]`; and `trained_on` reads
`"monthly archive, T_SEQ=1"`, which is stale boilerplate. **Trust `data` and `T_SEQ`; distrust
`trained_on` and the year fields.** Phase 3 should fix the writer. Until then the UI must *derive*
the test window and state which branch it took, or render `UNKNOWN` — never print the wrong window
confidently.

## D8 — Do not show a skill delta against the incumbent as if it were like-for-like
`compare_against` gives incumbent `skill_rmse_ratio` 0.3809 against our 0.2441 — but they were
scored on **different Argo sets** (879 profiles in 2022 vs 962 in the 2026 window). The delta is not
a model comparison. **Recommended:** show the RMSE delta with the caveat attached, and put any skill
comparison under an explicit "not like-for-like" heading, or leave it out.

## D9 — Contract items that do not exist yet
`tscast_data_model.md` §4 specifies `x_ssh_anom` `(1, T_SEQ, 12)` — the SSH-minus-climatological-SSH
vector. **It is not implemented anywhere**, and `clim_daily.npz` carries only `clim_t`,
`train_years`, `drift_by_depth`, `provenance` — no `clim_ssh` to build it from. `clim_s` is
defensibly absent (stage 2 is not enabled). **Recommended:** leave `x_ssh_anom` unbuilt in this
window and record in AGENT_SYNC that the model ships without the paper's steric-anomaly branch —
that is a real deviation and belongs in the deviations table, not in a silence.

## D10 — `config.TRAIN` and the CLI defaults disagree
`config.TRAIN` says `epochs=250, lr=1e-5, batch_size=512` (the paper's recipe); `train_stage1.py`
defaults to `epochs=20, lr=1e-3, batch_size=256`, and every recorded run used the CLI values.
**Recommended:** treat the CLI as authoritative, and add a comment in `config.py` saying `TRAIN` is
the paper's recipe kept for reference rather than the one in force. Do not "fix" either to match the
other mid-window.

## D11 — Small metrics JSONs into git
`/artifacts/*` is gitignored, yet 11 artifacts are already tracked, and this window has already
force-added `tseq_ablation.json` for exactly this reason. **Recommended:** `git add -f` the ~8 KB
metrics JSONs so the numbers survive; leave the 2.2 MB `.pt` out. A repo-hygiene call the team may
prefer to make differently — say what you did.

## D12 — UI layout: tabs or pages
Every existing Phase-2 page is one file per port. **Recommended:** one page with `st.tabs`, because a
judge should get one URL, and one AppTest run can scrape all tabs. Not settled by the repo.

## D13 — Forecast horizon
The schema permits `forecast: true` records, and the time lookup clamps to the last available field
— so a 2027 request is served from the 2026-06-23 surface silently. No horizon is specified
anywhere. **Recommended:** do not refuse, but require the input lag to be stated in the record's
reason string, so "this is a 200-day extrapolation" is visible rather than implied.

## D14 — `profile_id` has no real float identifier
The Argo parquet columns are `lat, lon, date, depth_idx, temp` — no WMO id — so `profile_id` must be
a composite key (e.g. `lat_lon_date`). Recovering true float ids is a data-pipeline task; scope it
later and do not pretend the composite is a float number.

## D15 — `EXPERIMENT_LOG.md` ordering
Its header says "newest on top"; its six existing entries run oldest-to-newest. **Recommended:**
append at the bottom, matching what the file actually does, and note the discrepancy. Reordering
someone else's log to match its own header is a worse outcome than one inconsistent line. The file
is Unit C's; add your entry, do not reformat theirs.

## D16 — Things measured on Arjhun's machine that you cannot re-verify
These reach you as numbers, not as files, because they are gitignored: the T_SEQ=1 and T_SEQ=11 legs
(now in the tracked `tseq_ablation.json`, marked `declared`), `artifacts/climatology.npy` (17 MB, no
CLI rebuild path — it must be obtained, never substituted with `clim_daily.npz`), and the
per-profile residuals that would make coverage cheap. If `climatology.npy` is missing on your clone,
**training cannot be scored** — solve that in Phase 0, not at midnight.

## D17 — Unverified cost figures
The 7.2 GB wind estimate is arithmetic (201×481 cells × 24 h × 2 vars × 4 B × 388 days), and the
"3–4 h" is unmeasured. The per-epoch table in `pick_tseq_and_retrain.py`'s docstring (1.8 / 8.4 /
24.9 min per 100k-sample epoch) disagrees with the one measured leg (1004.6 s/epoch at T=31, 40k
samples) by about 1.7×, unexplained. **Measure the first month of the download and the first epoch
of the retrain before trusting any total.**


---

# APPENDIX — VERIFIED API INDEX

Every symbol referenced anywhere in this spec, with the signature as it exists on disk on `phase2-tscast-nio`. 217 entries, read from source, not remembered. If your code calls something that is not here, stop and check it exists before building on it.


### `.gitignore`

| symbol | signature |
|---|---|
| `.gitignore data/artifact rules` | `/data/ ; *.nc ; *.zarr/ ; *.grib ; /artifacts/* with !sample_X.npy !sample_y.npy !sample_meta.parquet !sample_meta.csv ; *.pt ; *.pkl ; *.ckpt` |

### `D:/myproj/oceanembed/.venv (copernicusmarine 2.4.1)`

| symbol | signature |
|---|---|
| `copernicusmarine.core_functions.models.CoordinatesSelectionMethod` | `typing.Literal['inside', 'strict-inside', 'nearest', 'outside']` |
| `copernicusmarine.describe` | `describe(show_all_versions: bool = False, contains: list[str] = [], product_id: str \| None = None, dataset_id: str \| None = None, max_concurrent_requests: int = 15, disable_progress_bar: bool = False, staging: bool = False, raise_on_error: bool = False) -> CopernicusMarineCatalogue` |
| `copernicusmarine.subset` | `subset(dataset_id=None, dataset_version=None, dataset_part=None, username=None, password=None, variables=None, minimum_longitude=None, maximum_longitude=None, minimum_latitude=None, maximum_latitude=None, minimum_depth=None, maximum_depth=None, vertical_axis='depth', start_datetime=None, end_datetime=None, minimum_x=None, maximum_x=None, minimum_y=None, maximum_y=None, coordinates_selection_method='inside', output_filename=None, file_format=None, service=None, request_file=None, output_directory=None, credentials_file=None, motu_api_request=None, overwrite=False, skip_existing=False, dry_run=False, disable_progress_bar=False, staging=False, netcdf_compression_level=0, netcdf3_compatible=False, chunk_size_limit=-1, raise_if_updating=False, platform_ids=None)` |

### `D:/myproj/oceanembed/.venv (xarray 2025.9.0)`

| symbol | signature |
|---|---|
| `xarray Dataset.resample (dict form) — verified on xarray 2025.9.0` | `ds.resample({time_name: "1D"}).mean()   # bins labelled at 00:00 UTC; verified to return 2 days from 48 hourly stamps` |

### `D:/myproj/oceanembed/artifacts/argo_error_by_depth.json`

| symbol | signature |
|---|---|
| `artifacts/argo_error_by_depth.json (incumbent numbers)` | `overall.glorys = {rmse: 0.9736, mae: 0.6234, skill_vs_clim: 0.3809}; overall.satellite = {rmse: 0.9638, mae: 0.6225, skill_vs_clim: 0.3871}; overall.climatology.rmse = 1.5725` |

### `D:/myproj/oceanembed/artifacts/tscast_baseline_metrics.json`

| symbol | signature |
|---|---|
| `artifacts/tscast_baseline_metrics.json (Phase-1 MLP baseline)` | `model='phase1-mlp (incumbent baseline)', source='satellite', window 2022-01-01..2022-12-31, n_profiles_matched=897 of 2455, overall.rmse=0.95783, overall.skill_rmse_ratio=0.38611, overall.correlation=0.91513` |

### `D:/myproj/oceanembed/artifacts/tscast_stage1_metrics.json`

| symbol | signature |
|---|---|
| `artifacts/tscast_stage1_metrics.json (shape to preserve)` | `top-level keys: model, encoder, encoder_selected_by, residual, stage, stage_note, trained_on, channels, channels_note, device, data, T_SEQ, latent, unet_channels, n_params_encoder, n_params_decoder, seed, epochs_requested, epochs_run, best_epoch, best_heldout_nll, patience, weight_decay, beta_nll, decoder, loss, beta_nll_why, training_curve, checkpoint_is, lr, batch_size, train_samples, train_seconds, train_years, test_years, argo_profiles, max_days_offset, metrics{depths_m,rmse,correlation,bias,skill_vs_climatology,skill_rmse_ratio,rmse_climatology,n,overall{...},reference,window,bias_convention,not_to_be_confused_with}, calibration{<depth>:{n,rmse,sigma,ratio}}, calibration_method, mc_dropout_for_comparison, compare_against, checkpoint, code_commit` |

### `D:/myproj/oceanembed/scripts/phase2/download_daily_2025_2026.py`

| symbol | signature |
|---|---|
| `scripts/phase2/download_daily_2025_2026.py` | `START, END = "2025-06-01", "2026-06-23"; daily_dates() -> list[pd.Timestamp]; main() -> None   # certifi env vars set at module scope, lines 23-25` |

### `D:/myproj/oceanembed/scripts/phase2/pick_tseq_and_retrain.py`

| symbol | signature |
|---|---|
| `pick_tseq_and_retrain.main + SAMPLES_FOR` | `flags: --log (required), --recorded (default ''), --recorded-source (default 'docs/phase2/AGENT_SYNC.md 2026-08-29 section 5'), --dry-run; SAMPLES_FOR = {1: 100000, 11: 60000, 31: 40000}; final cmd = [sys.executable, '-m', 'phase2.tscast_nio.train.train_stage1', '--data','daily','--t-seq',<win>,'--decoder','simple','--loss','nll','--epochs','25','--train-samples',<n>,'--test-samples','12000','--patience','5']` |
| `pick_tseq_and_retrain.parse` | `def parse(log_path: str) -> dict[int, float]  # banner regex r'T_SEQ=(\d+)\s*=====', result regex r'OVERALL\s+rmse=([\d.]+)'` |
| `pick_tseq_and_retrain.parse_recorded` | `def parse_recorded(spec: str) -> dict[int, float]  # '1=0.9096,11=0.8529'` |

### `D:/myproj/oceanembed/scripts/phase2/verify_daily_bundle.py`

| symbol | signature |
|---|---|
| `scripts/phase2/verify_daily_bundle.py EXPECTED_VARS` | `EXPECTED_VARS = {"thetao","so","zos","uo","vo"}; CLI: --dir (default data/raw/daily), --full   # covers raw GLORYS only, never wind` |

### `D:/myproj/oceanembed/src/oceanembed/climatology.py`

| symbol | signature |
|---|---|
| `climatology.build_climatology` | `def build_climatology(y_train: np.ndarray, meta_train: pd.DataFrame, save: bool = True) -> np.ndarray  # no CLI entry point` |

### `D:/myproj/oceanembed/src/oceanembed/config.py`

| symbol | signature |
|---|---|
| `oceanembed.config` | `SEED = 42; TRAIN_YEARS = [2019, 2020, 2021]; TEST_YEARS = [2022]; DATA_PROCESSED = <root>/data/processed; ARTIFACTS = <root>/artifacts; def art(name: str) -> str` |

### `D:/myproj/oceanembed/src/oceanembed/data/download_glorys.py`

| symbol | signature |
|---|---|
| `download_glorys.download_dates` | `download_dates(dates=None, out_dir: str \| None = None, dataset_id: str = DATASET_ID, variables=VARIABLES) -> str   # DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m", filename f"glorys_{d:%Y%m%d}.nc"` |

### `D:/myproj/oceanembed/src/oceanembed/data/preprocess.py`

| symbol | signature |
|---|---|
| `oceanembed.data.preprocess._find_coord` | `_find_coord(ds: xr.Dataset, *names: str) -> str   # raises KeyError listing ds.coords` |
| `oceanembed.data.preprocess._process_one` | `_process_one(path: str) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]   # (times, surf{sst,sss,ssh,u,v}, temp); regrid is ds.interp({latn: config.LAT, lonn: config.LON}, method="linear") at line 41` |

### `D:/myproj/oceanembed/src/oceanembed/utils/grids.py`

| symbol | signature |
|---|---|
| `oceanembed.utils.grids.nearest_lat_index / nearest_lon_index` | `nearest_lat_index(lat: float) -> int   # int(np.argmin(np.abs(config.LAT - lat)));  nearest_lon_index(lon: float) -> int` |

### `D:/myproj/oceanembed/src/oceanembed/validation/validate_argo.py`

| symbol | signature |
|---|---|
| `validate_argo.load_argo / pivot_profiles` | `def load_argo(path_noext: str \| None = None) -> pd.DataFrame; def pivot_profiles(argo_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]` |

### `D:/myproj/oceanembed/src/phase2/data/download_wind.py`

| symbol | signature |
|---|---|
| `download_wind.DATASET_ID / VARIABLES / OUT_DIR` | `DATASET_ID = "cmems_obs-wind_glo_phy_my_l4_P1M"; VARIABLES = ["eastward_wind","northward_wind","eastward_stress","northward_stress","wind_speed","wind_stress_magnitude"]; OUT_DIR = os.path.join(config.DATA_RAW, "wind")` |
| `download_wind._fix_ssl` | `_fix_ssl() -> None   # certifi -> SSL_CERT_FILE, REQUESTS_CA_BUNDLE via os.environ.setdefault` |
| `download_wind.download_dates` | `download_dates(dates=None, out_dir: str = OUT_DIR) -> str` |
| `download_wind.monthly_dates` | `monthly_dates(years=None) -> list[pd.Timestamp]` |

### `D:/myproj/oceanembed/src/phase2/events/upwelling.py`

| symbol | signature |
|---|---|
| `phase2.events.upwelling.WIND_DIR / MissingWindError` | `WIND_DIR = os.path.join(config.DATA_RAW, "wind"); glob pattern "wind_*.nc" (line 126); class MissingWindError(RuntimeError)` |
| `phase2.events.upwelling.load_wind_stress` | `load_wind_stress(month) -> dict   # {"eastward_stress","northward_stress","time","path","raw_grid_offset_deg"}; regrids via ds.interp(latitude=config.LAT, longitude=config.LON, method="linear") and raises AssertionError if the regridded coords do not match config (lines 141-161)` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/config.py`

| symbol | signature |
|---|---|
| `phase2 config constants` | `T_SEQ = 31; P = 17; LATENT_DIM = 128; UNET_CHANNELS = (32, 64, 128); PAPER_UNET_CHANNELS = (64,128,256,512); INTERNAL_LEVELS = 64; INTERNAL_DEPTH_RANGE = (0.0, 1000.0); CHANNELS = ['sst','sss','ssh','u','v','wu','wv']; SEED = _base.SEED; STAGE = 1; def sanity_check() -> None` |
| `phase2.tscast_nio.config` | `CHANNELS = ["sst","sss","ssh","u","v","wu","wv"]; CHANNEL_UNITS = ["degC","psu","m","m s-1","m s-1","m s-1","m s-1"]; N_CHANNELS = 7; T_SEQ = 31; P = 17` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/daily_pipeline.py`

| symbol | signature |
|---|---|
| `phase2.tscast_nio.daily_pipeline (land_mask derivation)` | `line 89: land_mask = ~np.isfinite(surface[:, :, :, 0]).any(axis=0)   # channel 0 == sst` |
| `phase2.tscast_nio.daily_pipeline.SURFACE_KEYS / SURFACE_UNITS` | `SURFACE_KEYS = ["sst","sss","ssh","u","v"]; SURFACE_UNITS = ["degC","psu","m","m s-1","m s-1"]` |
| `phase2.tscast_nio.daily_pipeline._salinity_at_depths / _commit` | `_salinity_at_depths(path: str) -> np.ndarray  # (T,100,240,15);  _commit() -> str  # git rev-parse --short HEAD` |
| `phase2.tscast_nio.daily_pipeline.build_year` | `build_year(files: list[str], year: int, out_dir: str, with_salinity: bool = True) -> str` |
| `phase2.tscast_nio.daily_pipeline.main (CLI)` | `--raw-dir (default data/raw/daily), --out-dir (default data/processed/daily), --no-salinity, --limit N` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/dataset.py`

| symbol | signature |
|---|---|
| `dataset.DAILY_TRAIN / DAILY_TEST` | `DAILY_TRAIN = (np.datetime64('2025-06-01'), np.datetime64('2026-03-31')); DAILY_TEST = (np.datetime64('2026-04-01'), np.datetime64('2026-06-23'))` |
| `dataset.GriddedPatches.__getitem__` | `returns (x (C,T,P,P), x_geo (3,1,P,P), y_z (15,), y_valid (15,), latlon (2,)) and, when return_clim, + (cp_z (12,15), month int tensor)` |
| `dataset.GriddedPatches.__init__` | `def __init__(self, surface, temp, times, land_mask, channels, t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None, stride=1, clim=None, return_clim=False)` |
| `dataset.cell_index` | `def cell_index(lat, lon) -> tuple[np.ndarray, np.ndarray]  # delegates to grids.nearest_lat_index / nearest_lon_index` |
| `dataset.daily_split_indices` | `def daily_split_indices(times) -> tuple[np.ndarray, np.ndarray]  # asserts disjoint and test strictly after train` |
| `dataset.load_daily` | `def load_daily(d=None) -> dict  # keys: surface, temp, times, land_mask, valid_mask, channels (+ salinity when present); default dir data/processed/daily` |
| `dataset.load_monthly` | `def load_monthly(path=None) -> dict  # chans = ['sst','sss','ssh','u','v']` |
| `dataset.split_indices` | `def split_indices(times, train_years=None, test_years=None) -> tuple[np.ndarray, np.ndarray]` |
| `phase2.tscast_nio.dataset.GriddedPatches.__init__` | `__init__(self, surface, temp, times, land_mask, channels, t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None, stride=1, clim=None, return_clim=False)   # self.C = surface.shape[-1] (line 58)` |
| `phase2.tscast_nio.dataset.daily_split_indices / DAILY_TRAIN / DAILY_TEST` | `DAILY_TRAIN = (2025-06-01, 2026-03-31); DAILY_TEST = (2026-04-01, 2026-06-23); daily_split_indices(times) -> (tr, te)` |
| `phase2.tscast_nio.dataset.load_daily` | `load_daily(d=None) -> dict   # d defaults to os.path.join(base.DATA_PROCESSED, "daily"); channels taken from the FIRST npz only (line 181)` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/encoders.py`

| symbol | signature |
|---|---|
| `encoders.CNN3D.__init__` | `def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128, widths=(24, 48, 96))  # t_seq only selects AvgPool3d temporal kernel: pt = 2 if t >= 2 else 1; no weight shape depends on it` |
| `encoders.ENCODERS` | `ENCODERS = {'mlp_control': MLPControl, 'cnn3d': CNN3D, 'cnn_attention': CNNAttention, 'vit': ViT}` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/inference.py`

| symbol | signature |
|---|---|
| `inference.TSCastPredictor.__init__` | `def __init__(self, checkpoint: str \| None = None, data: dict \| None = None, clim: np.ndarray \| None = None)  # line 51 builds TSCastNIO(ck['encoder'], len(ck['channels']), t_seq=ck['T_SEQ'], p=ck['P'], latent=ck['latent'], residual=ck['residual']) -- no decoder= argument, so it defaults to 'film'` |
| `inference.TSCastPredictor.reconstruct` | `def reconstruct(self, lat: float, lon: float, date, argo_check=None) -> dict; LAST_GLORYS = np.datetime64('2026-06-23'); LAST_ARGO = np.datetime64('2026-08-24')` |
| `phase2.tscast_nio.inference.TSCastPredictor.__init__` | `__init__(self, checkpoint: str \| None = None, data: dict \| None = None, clim: np.ndarray \| None = None)   # line 44 raises ValueError when list(data['channels']) != list(ck['channels'])` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/metrics.py`

| symbol | signature |
|---|---|
| `metrics.per_depth` | `def per_depth(pred, truth, clim=None, reference: str = "argo", window=None) -> dict` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/models/tscast.py`

| symbol | signature |
|---|---|
| `models.LOGVAR_MIN / LOGVAR_MAX` | `LOGVAR_MIN, LOGVAR_MAX = -7.0, 7.0` |
| `models.TSCastNIO.__init__` | `def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None, latent: int = None, residual: bool = True, unet_channels=None, decoder: str = "film")` |
| `models.TSCastNIO.forward` | `def forward(self, x, x_geo, clim, month) -> tuple[Tensor (B,15), Tensor (B,15)]  # with decoder='simple' returns from the simple head BEFORE the residual branch, so residual= is a no-op there` |
| `models.build` | `def build(encoder_name: str, c_in: int, **kw) -> TSCastNIO` |
| `models.gaussian_nll` | `def gaussian_nll(mu, logvar, y, mask, beta: float = 0.0) -> Tensor` |
| `phase2.tscast_nio.models.TSCastNIO.__init__` | `__init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None, latent: int = None, residual: bool = True, unet_channels=None, decoder: str = "film")` |

### `D:/myproj/oceanembed/src/phase2/tscast_nio/train/train_stage1.py`

| symbol | signature |
|---|---|
| `train_stage1 checkpoint dict` | `lines 284-289: torch.save({'state_dict','encoder','seed','residual','channels','P','T_SEQ','latent','unet_channels','norm','epochs','lr','batch_size'}, base.art('tscast_stage1.pt'))  # NOTE: no 'decoder' key` |
| `train_stage1 model construction (the t_seq defect)` | `line 156: model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent, residual=not a.no_residual, unet_channels=widths, decoder=a.decoder).to(dev)` |
| `train_stage1 model construction + checkpoint payload` | `line 156: TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent, residual=..., unet_channels=widths, decoder=a.decoder); line 284 torch.save({... "channels": d["channels"], "norm": [v.tolist() for v in ds_tr.norm], ...}); line 300 literal "channels_note": "5 of the contract's 7; wind arrives with the daily pipeline"` |
| `train_stage1.MAX_DAYS` | `MAX_DAYS = 5  # +/- days for Argo collocation` |
| `train_stage1.calibration` | `def calibration(pred, sigma, truth) -> dict[int, dict]  # per depth: {'n','rmse','sigma','ratio'}; depths with ok.sum() < 30 omitted` |
| `train_stage1.main (argparse surface)` | `def main() -> None  # flags, lines 69-100: --epochs int=20, --train-samples int=40000, --lr float=1e-3, --batch-size int=256, --encoder str=None, --no-residual store_true, --patience int=4, --weight-decay float=1e-2, --device str='auto', --num-workers int=0, --latent int=None, --unet-width int nargs='+' =None, --decoder choices=['film','simple'] default='film', --loss choices=['nll','mse'] default='nll', --data choices=['monthly','daily'] default='monthly', --t-seq int=None, --test-samples int=12000, --beta float=0.5` |
| `train_stage1.winning_encoder` | `def winning_encoder(default: str = "cnn3d") -> tuple[str, str]  # reads base.art('architecture_feasibility.json')['winner']` |

### `altair 6.2.2 -> Vega-Lite v6.4.1`

| symbol | signature |
|---|---|
| `altair depth axis / band / break` | `alt.Y('depth_m:Q', scale=alt.Scale(reverse=True)) -> {'scale': {'reverse': True}}; alt.X2('hi:Q') with mark_area; mark_line(invalid='break-paths-show-domains') -> {'type':'line','invalid':'break-paths-show-domains'}  [all three verified by building the spec]` |

### `app/panels/_viz.py:39,72,85`

| symbol | signature |
|---|---|
| `_viz.colorize / value_range / nearest_argo` | `def colorize(grid, land_mask=None, diverging=False, robust=True) -> np.ndarray; def value_range(grid, robust=True) -> tuple[float,float]; def nearest_argo(argo_df, lat, lon, max_deg=2.0)  # DEGREE distance, display only -- never for a metric` |

### `artifacts/argo_2026.parquet`

| symbol | signature |
|---|---|
| `artifacts/argo_2026.parquet (measured)` | `2026-01-01 02:55 .. 2026-08-29 01:30, 2637 profiles -- later than the 2026-08-24 stated in inference.LAST_ARGO and in tscast_output_schema.md section 4` |

### `artifacts/argo_daily_period.parquet`

| symbol | signature |
|---|---|
| `artifacts/argo_daily_period.parquet (measured)` | `columns ['lat','lon','date','depth_idx','temp']; 59599 rows; 4331 distinct (lat,lon,date) profiles; 2025-06-01 05:18 .. 2026-06-22 22:43` |

### `artifacts/argo_test.parquet`

| symbol | signature |
|---|---|
| `artifacts/argo_test.parquet (measured)` | `columns ['lat','lon','date','depth_idx','temp']; 2022-01-01 .. 2022-12-31 ONLY` |

### `artifacts/clim_daily.npz`

| symbol | signature |
|---|---|
| `artifacts/clim_daily.npz (measured)` | `files ['clim_t','train_years','drift_by_depth','provenance']; train_years = [2019 2020 2021]; provenance is a JSON string documenting why the prior is 2019-2021 and not the daily train split` |

### `artifacts/tscast_stage1.pt`

| symbol | signature |
|---|---|
| `artifacts/tscast_stage1.pt (measured contents)` | `meta keys ['encoder','seed','residual','channels','P','T_SEQ','latent','unet_channels','norm','epochs','lr','batch_size']; encoder='cnn3d', seed=42, residual=True, channels=['sst','sss','ssh','u','v'], P=17, T_SEQ=31, latent=128, unet_channels=[32,64,128], epochs=4; state_dict has 32 keys, 0 starting with 'decoder.', 4 named simple_head.{0,2}.{weight,bias}; sha256 begins aac39bc4b7384f38` |

### `artifacts/tscast_stage1_metrics.json`

| symbol | signature |
|---|---|
| `artifacts/tscast_stage1_metrics.json (measured)` | `data='daily', T_SEQ=31, decoder='simple', loss='nll', beta_nll=0.5, encoder='cnn3d', latent=128, argo_profiles=962, best_epoch=4, code_commit='06b29fd'; metrics.rmse (15) worst 1.335 at 125 m, best 0.239 at 1000 m; overall.rmse=0.9267, bias=+0.2515, correlation=0.8824, skill_rmse_ratio=0.2441` |

### `pyproject.toml`

| symbol | signature |
|---|---|
| `pytest configuration` | `[tool.pytest.ini_options] pythonpath = ['src']; testpaths = ['tests']` |

### `requirements.txt`

| symbol | signature |
|---|---|
| `erddapy pin` | `erddapy<3   # argopy 1.4.0 imports a private symbol removed in erddapy 3.x` |

### `scripts/phase2/accept.py`

| symbol | signature |
|---|---|
| `accept.CHECKS` | `CHECKS = [('F1 collocation','phase2.data.collocation',check_f1), ('F2b volume',...), ('F2a OceanCube',...), ('F5 physics',...), ('F6 events',...), ('F8 validation',...), ('v2 TS-Cast-NIO','phase2.tscast_nio.metrics',check_v2_tscast)]` |
| `accept.DERIVED` | `DERIVED = {'glorys_vs_argo.json': 'glorys_vs_argo.py', 'mc_calibration.json': 'measure_mc_calibration.py'}` |

### `scripts/phase2/accept.py:138`

| symbol | signature |
|---|---|
| `accept.DERIVED` | `DERIVED = {'glorys_vs_argo.json': 'glorys_vs_argo.py', 'mc_calibration.json': 'measure_mc_calibration.py'}  # artifact -> regenerating script` |

### `scripts/phase2/accept.py:267`

| symbol | signature |
|---|---|
| `accept.check_f1 (style reference)` | `def check_f1() -> tuple[bool, list[str]]  # builds `checks = [(bool, msg), ...]`, returns (all(...), ['     ok   '/'     FAIL ' + msg])` |

### `scripts/phase2/accept.py:482`

| symbol | signature |
|---|---|
| `accept.CHECKS` | `CHECKS = [(display_name: str, import_path: str, fn: Callable[[], tuple[bool, list[str]]]), ...]  # detection by import path, never branch name` |

### `scripts/phase2/architecture_feasibility.py`

| symbol | signature |
|---|---|
| `architecture_feasibility CLI` | `--quick \| --epochs 8 \| --train-samples 40000 \| --test-samples 12000` |

### `scripts/phase2/measure_mc_calibration.py:59`

| symbol | signature |
|---|---|
| `measure_mc_calibration.MIN_N` | `MIN_N = 30  # below this a depth is not reported rather than reported noisily` |

### `scripts/phase2/pick_tseq_and_retrain.py`

| symbol | signature |
|---|---|
| `pick_tseq_and_retrain CLI` | `--log <required> \| --recorded \| --recorded-source \| --dry-run ; SAMPLES_FOR = {1: 100000, 11: 60000, 31: 40000}` |

### `scripts/phase2/try_collocation.py`

| symbol | signature |
|---|---|
| `try_collocation CLI` | `positional lat lon date \| --json \| --dates \| --tour` |

### `scripts/phase2/verify_daily_bundle.py`

| symbol | signature |
|---|---|
| `verify_daily_bundle CLI` | `--dir (default data/raw/daily) \| --full` |
| `verify_daily_bundle constants` | `EXPECTED_VARS = {'thetao','so','zos','uo','vo'}; SST_MIN, SST_MAX = 11.0, 38.0; DEEP_MIN, DEEP_MAX = 1.0, 20.0` |

### `src/oceanembed/config.py`

| symbol | signature |
|---|---|
| `DEPTHS` | `DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]` |
| `FEATURES` | `FEATURES = ['sst','sss','ssh','u','v','sin_lat','cos_lat','sin_lon','cos_lon','sin_doy','cos_doy']` |
| `LAT` | `LAT = np.arange(5.0, 30.0, 0.25).astype('float32')  # shape (100,)` |
| `LON` | `LON = np.arange(45.0, 105.0, 0.25).astype('float32')  # shape (240,)` |
| `N_LAT / N_LON / N_DEPTHS / N_FEAT` | `N_LAT = 100; N_LON = 240; N_DEPTHS = 15; N_FEAT = 11` |
| `REGION` | `REGION = dict(lat_min=5.0, lat_max=30.0, lon_min=45.0, lon_max=105.0, step=0.25)` |
| `ROOT / DATA_RAW / DATA_PROCESSED / ARTIFACTS` | `ROOT = <repo root>; DATA_RAW = ROOT/data/raw; DATA_PROCESSED = ROOT/data/processed; ARTIFACTS = ROOT/artifacts` |
| `SEED` | `SEED = 42` |
| `TRAIN_YEARS / TEST_YEARS` | `TRAIN_YEARS = [2019, 2020, 2021]; TEST_YEARS = [2022]` |
| `config.MLP` | `MLP = dict(hidden=(128, 128), dropout=0.2, lr=1e-3, epochs=100, batch_size=256, mc_passes=30)` |
| `config.art` | `def art(name: str) -> str` |
| `config.sanity_check` | `def sanity_check() -> None` |
| `oceanembed.config constants` | `TRAIN_YEARS = [2019, 2020, 2021]; TEST_YEARS = [2022]; SEED = 42; DEPTHS = [0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]; N_DEPTHS = 15; DATA_PROCESSED = <root>/data/processed` |
| `oceanembed.config.art` | `def art(name: str) -> str  # os.path.join(ARTIFACTS, name); does NOT append an extension` |

### `src/oceanembed/config.py:16-17`

| symbol | signature |
|---|---|
| `config.LAT / config.LON` | `LAT = np.arange(5.0, 30.0, 0.25).astype('float32'); LON = np.arange(45.0, 105.0, 0.25).astype('float32')` |

### `src/oceanembed/config.py:22`

| symbol | signature |
|---|---|
| `config.DEPTHS` | `DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]  # 15 levels, metres` |

### `src/oceanembed/config.py:29-31`

| symbol | signature |
|---|---|
| `config.N_DEPTHS / N_LAT / N_LON` | `N_LAT = 100; N_LON = 240; N_DEPTHS = 15` |

### `src/oceanembed/config.py:37-51`

| symbol | signature |
|---|---|
| `config.ARTIFACTS / DATA_PROCESSED / TRAIN_YEARS / TEST_YEARS / SEED` | `TRAIN_YEARS = [2019, 2020, 2021]; TEST_YEARS = [2022]; SEED = 42; ARTIFACTS = <root>/artifacts; DATA_PROCESSED = <root>/data/processed` |

### `src/oceanembed/config.py:54`

| symbol | signature |
|---|---|
| `config.art` | `def art(name: str) -> str  # os.path.join(ARTIFACTS, name)` |

### `src/oceanembed/utils/grids.py`

| symbol | signature |
|---|---|
| `cell_id_to_latlon` | `def cell_id_to_latlon(cell_id: int) -> tuple[float, float]` |
| `day_of_year_features` | `def day_of_year_features(doy: int) -> tuple[float, float]` |
| `latlon_features` | `def latlon_features(lat: float, lon: float) -> tuple[float, float, float, float]` |
| `latlon_to_cell_id` | `def latlon_to_cell_id(lat: float, lon: float) -> int  # i * N_LON + j` |
| `nearest_lat_index` | `def nearest_lat_index(lat: float) -> int` |
| `nearest_lon_index` | `def nearest_lon_index(lon: float) -> int` |

### `src/oceanembed/utils/io.py`

| symbol | signature |
|---|---|
| `io.load_table` | `def load_table(path_noext: str) -> pd.DataFrame` |
| `io.save_npy / load_npy / save_json / load_json` | `def save_npy(arr: np.ndarray, path: str) -> str; def load_npy(path: str) -> np.ndarray; def save_json(obj: dict, path: str) -> str; def load_json(path: str) -> dict` |
| `io.save_table` | `def save_table(df: pd.DataFrame, path_noext: str) -> str` |
| `oceanembed.utils.io.load_table` | `def load_table(path_noext: str) -> pd.DataFrame  # tries path+'.parquet' then path+'.csv', else FileNotFoundError` |

### `src/oceanembed/validation/validate_argo.py:53`

| symbol | signature |
|---|---|
| `validate_argo.load_argo` | `def load_argo(path_noext: str \| None = None) -> pd.DataFrame` |

### `src/oceanembed/validation/validate_argo.py:70`

| symbol | signature |
|---|---|
| `validate_argo.pivot_profiles` | `def pivot_profiles(argo_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]  # (keys[lat,lon,date], (N,15) float32); asserts depth_idx in 0..14` |

### `src/phase2/data/collocation.py`

| symbol | signature |
|---|---|
| `Collocation` | `@dataclass class Collocation: requested: dict; matched: dict; offsets: dict; sources: dict = {}; quality: str = 'UNKNOWN'; flags: list = []; provenance: dict = {}; def to_dict(self) -> dict` |
| `Collocation (dataclass)` | `@dataclass class Collocation: requested: dict; matched: dict; offsets: dict; sources: dict; quality: str = "UNKNOWN"; flags: list; provenance: dict; def to_dict(self) -> dict` |
| `CollocationEngine.__init__` | `def __init__(self, tolerance_days: float = DEFAULT_TOLERANCE_D, spatial_method: str = 'nearest')` |
| `CollocationEngine._argo_table` | `def _argo_table(self) -> pd.DataFrame \| None  # hardcoded io.load_table(config.art("argo_test")) -- the 2022-only set` |
| `CollocationEngine._match_argo` | `def _match_argo(self, lat: float, lon: float, when: pd.Timestamp) -> dict \| None  # keys: latitude, longitude, datetime, temperature_profile (15, None where unsampled), spatial_offset_km, temporal_offset_days (SIGNED float), n_levels, note` |
| `CollocationEngine._quality` | `def _quality(self, r: Collocation) -> str  # scores the GLORYS grid match, NOT the Argo match` |
| `CollocationEngine.collocate` | `def collocate(self, latitude: float, longitude: float, datetime, *, include_profile: bool = True) -> Collocation` |
| `TEMPORAL_HIGH_D / TEMPORAL_MED_D / TEMPORAL_LOW_D / DEFAULT_TOLERANCE_D / SPATIAL_MAX_KM / EARTH_R_KM` | `TEMPORAL_HIGH_D = 2.0; TEMPORAL_MED_D = 5.0; TEMPORAL_LOW_D = 10.0; DEFAULT_TOLERANCE_D = 10.0; SPATIAL_MAX_KM = 20.0; EARTH_R_KM = 6371.0` |
| `collocate (module-level)` | `def collocate(latitude: float, longitude: float, datetime, **kw) -> dict` |
| `collocation thresholds` | `TEMPORAL_HIGH_D = 2.0; TEMPORAL_MED_D = 5.0; TEMPORAL_LOW_D = 10.0; DEFAULT_TOLERANCE_D = 10.0; SPATIAL_MAX_KM = 20.0` |
| `collocation.collocate` | `def collocate(latitude: float, longitude: float, datetime, **kw) -> dict` |

### `src/phase2/data/collocation.py:107`

| symbol | signature |
|---|---|
| `CollocationEngine.__init__` | `def __init__(self, tolerance_days: float = DEFAULT_TOLERANCE_D, spatial_method: str = 'nearest')  # NO argo_table parameter` |

### `src/phase2/data/collocation.py:123`

| symbol | signature |
|---|---|
| `CollocationEngine._argo_table` | `def _argo_table(self) -> pd.DataFrame \| None  # hardcoded to io.load_table(config.art('argo_test'))` |

### `src/phase2/data/collocation.py:157`

| symbol | signature |
|---|---|
| `CollocationEngine.collocate` | `def collocate(self, latitude: float, longitude: float, datetime, *, ...) -> Collocation  # .quality, .flags, .offsets, .requested, .matched, .sources, .provenance` |

### `src/phase2/data/collocation.py:274`

| symbol | signature |
|---|---|
| `CollocationEngine._match_argo` | `def _match_argo(self, lat: float, lon: float, when: pd.Timestamp) -> dict \| None  # keys: latitude, longitude, datetime, temperature_profile, spatial_offset_km, temporal_offset_days (SIGNED float), n_levels, note` |

### `src/phase2/tscast_nio/config.py`

| symbol | signature |
|---|---|
| `tscast_nio.config constants` | `DEPTHS, N_DEPTHS=15, T_SEQ=31, P=17, INTERNAL_LEVELS=64, INTERNAL_DEPTH_RANGE=(0.0,1000.0), LATENT_DIM=128, UNET_CHANNELS=(32,64,128), CHANNELS=['sst','sss','ssh','u','v','wu','wv']` |
| `vcfg.CHANNELS / CHANNEL_UNITS / N_CHANNELS` | `CHANNELS = ['sst','sss','ssh','u','v','wu','wv']; CHANNEL_UNITS = ['degC','psu','m','m s-1','m s-1','m s-1','m s-1']; N_CHANNELS = 7` |
| `vcfg.INTERNAL_LEVELS / INTERNAL_DEPTH_RANGE` | `INTERNAL_LEVELS = 64; INTERNAL_DEPTH_RANGE = (0.0, 1000.0)` |
| `vcfg.LATENT_DIM / UNET_CHANNELS / PAPER_UNET_CHANNELS` | `LATENT_DIM = 128; UNET_CHANNELS = (32, 64, 128); PAPER_UNET_CHANNELS = (64, 128, 256, 512)` |
| `vcfg.STAGE` | `STAGE = 1` |
| `vcfg.TRAIN` | `TRAIN = dict(epochs=250, lr=1e-5, batch_size=512, optimizer='adamw', val_fraction=0.2, n_ensemble=3)` |
| `vcfg.T_SEQ / vcfg.P` | `T_SEQ = 31; P = 17` |
| `vcfg.sanity_check` | `def sanity_check() -> None` |

### `src/phase2/tscast_nio/config.py:23-37`

| symbol | signature |
|---|---|
| `phase2.tscast_nio.config` | `DEPTHS, N_DEPTHS re-exported from oceanembed.config; CHANNELS = ['sst','sss','ssh','u','v','wu','wv']; T_SEQ = 31; P = 17; STAGE = 1` |

### `src/phase2/tscast_nio/daily_pipeline.py`

| symbol | signature |
|---|---|
| `daily_pipeline CLI` | `--raw-dir (default data/raw/daily) \| --out-dir (default data/processed/daily) \| --no-salinity \| --limit N` |
| `daily_pipeline source string` | `line 99: "source": "GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D-m)"  -- confirms provenance input_source == 'glorys' for the daily bundle` |
| `daily_pipeline.build_year` | `def build_year(files: list[str], year: int, out_dir: str, with_salinity: bool = True) -> str` |

### `src/phase2/tscast_nio/dataset.py`

| symbol | signature |
|---|---|
| `DAILY_TRAIN / DAILY_TEST` | `DAILY_TRAIN = (np.datetime64('2025-06-01'), np.datetime64('2026-03-31')); DAILY_TEST = (np.datetime64('2026-04-01'), np.datetime64('2026-06-23'))` |
| `GriddedPatches` | `class GriddedPatches(Dataset): def __init__(self, surface, temp, times, land_mask, channels, t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None, stride=1, clim=None, return_clim=False)` |
| `GriddedPatches.__getitem__` | `def __getitem__(self, k: int)  # -> (x (C,T,P,P), x_geo (3,1,P,P), y_z (15,), y_valid (15,), latlon (2,)) [+ (cp_z (12,15), month) when return_clim=True]` |
| `GriddedPatches.norm` | `@property def norm(self) -> tuple  # (mean, std, y_mean, y_std)` |
| `cell_index` | `def cell_index(lat, lon)  # -> (np.ndarray i, np.ndarray j), nearest-centre via grids.*` |
| `daily_split_indices` | `def daily_split_indices(times)  # -> (tr, te); asserts disjoint and test strictly after train` |
| `dataset.GriddedPatches.__getitem__` | `def __getitem__(self, k)  # 5-tuple (x, x_geo, y_z, y_valid, latlon); + (clim_z (12,15), month int) when return_clim=True` |
| `dataset.GriddedPatches.__init__` | `def __init__(self, surface, temp, times, land_mask, channels, t_indices, norm=None, t_seq=None, p=None, max_samples=None, seed=None, stride=1, clim=None, return_clim=False)` |
| `dataset.GriddedPatches.norm` | `@property def norm(self) -> (mean, std, y_mean, y_std)` |
| `dataset.cell_index` | `def cell_index(lat, lon)  # -> (i, j) arrays via grids.nearest_lat_index / nearest_lon_index` |
| `dataset.daily_split_indices` | `def daily_split_indices(times)  # DAILY_TRAIN = (2025-06-01, 2026-03-31); DAILY_TEST = (2026-04-01, 2026-06-23)` |
| `dataset.geo_encoding` | `def geo_encoding(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray  # (...,3)` |
| `dataset.load_daily` | `def load_daily(d=None)  # -> dict(surface, temp, times, land_mask, valid_mask, channels[, salinity]); MEASURED 388 steps 2025-06-01..2026-06-23, surface (388,100,240,5), temp (388,100,240,15), median cadence 1.0 d` |
| `dataset.load_monthly` | `def load_monthly(path=None)  # -> same dict shape; MEASURED 48 steps 2019-01-15..2022-12-15, median cadence 31.0 d (min 28, max 31)` |
| `dataset.split_indices` | `def split_indices(times, train_years=None, test_years=None)` |
| `geo_encoding` | `def geo_encoding(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray  # (..., 3) X,Y,Z` |
| `load_daily` | `def load_daily(d=None)  # -> dict(surface, temp, times, land_mask, valid_mask, channels[, salinity])` |
| `load_monthly` | `def load_monthly(path=None)  # -> dict(surface, temp, times, land_mask, valid_mask, channels)` |
| `split_indices` | `def split_indices(times, train_years=None, test_years=None)  # -> (tr, te)` |

### `src/phase2/tscast_nio/dataset.py:149,160`

| symbol | signature |
|---|---|
| `dataset.load_daily / load_monthly` | `def load_monthly(path=None) -> dict; def load_daily(d=None) -> dict  # keys: surface, temp, times, land_mask, valid_mask, channels` |

### `src/phase2/tscast_nio/dataset.py:192-203`

| symbol | signature |
|---|---|
| `dataset.DAILY_TRAIN / DAILY_TEST / daily_split_indices` | `DAILY_TRAIN = (2025-06-01, 2026-03-31); DAILY_TEST = (2026-04-01, 2026-06-23); def daily_split_indices(times) -> tuple[np.ndarray, np.ndarray]` |

### `src/phase2/tscast_nio/dataset.py:29`

| symbol | signature |
|---|---|
| `dataset.cell_index` | `def cell_index(lat, lon) -> tuple[np.ndarray, np.ndarray]  # nearest-centre, via oceanembed.utils.grids` |

### `src/phase2/tscast_nio/encoders.py`

| symbol | signature |
|---|---|
| `CNN3D.__init__` | `def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128, widths=(24, 48, 96))  # t_seq only sets AvgPool3d factors (no parameters), so state_dict is identical for any t_seq` |
| `encoders.ENCODERS` | `ENCODERS = {"mlp_control": MLPControl, "cnn3d": CNN3D, "cnn_attention": CNNAttention, "vit": ViT}` |
| `encoders.build` | `def build(name: str, c_in: int, t_seq: int, p: int, n_depths: int, latent: int = 128) -> Candidate` |
| `encoders.n_params` | `def n_params(m: nn.Module) -> int` |

### `src/phase2/tscast_nio/inference.py`

| symbol | signature |
|---|---|
| `LAST_GLORYS / LAST_ARGO` | `LAST_GLORYS = np.datetime64('2026-06-23'); LAST_ARGO = np.datetime64('2026-08-24')` |
| `TSCastPredictor` | `class TSCastPredictor: def __init__(self, checkpoint: str \| None = None, data: dict \| None = None, clim: np.ndarray \| None = None)` |
| `TSCastPredictor.__init__` | `def __init__(self, checkpoint: str \| None = None, data: dict \| None = None, clim: np.ndarray \| None = None)  # current, defective signature; Phase 3 adds argo_table=None` |
| `TSCastPredictor._cell` | `def _cell(self, lat: float, lon: float) -> tuple[int, int]` |
| `TSCastPredictor._time` | `def _time(self, date) -> tuple[int, int]  # (nearest time index, \|offset\| in days)` |
| `TSCastPredictor.reconstruct` | `def reconstruct(self, lat: float, lon: float, date, argo_check=None) -> dict` |
| `TSCastPredictor.seafloor_depth_m` | `def seafloor_depth_m(self, lat: float, lon: float) -> float` |

### `src/phase2/tscast_nio/inference.py:27-28`

| symbol | signature |
|---|---|
| `inference.LAST_GLORYS / LAST_ARGO` | `LAST_GLORYS = np.datetime64('2026-06-23'); LAST_ARGO = np.datetime64('2026-08-24')` |

### `src/phase2/tscast_nio/inference.py:32`

| symbol | signature |
|---|---|
| `TSCastPredictor.__init__` | `def __init__(self, checkpoint: str \| None = None, data: dict \| None = None, clim: np.ndarray \| None = None)` |

### `src/phase2/tscast_nio/inference.py:76`

| symbol | signature |
|---|---|
| `TSCastPredictor.seafloor_depth_m` | `def seafloor_depth_m(self, lat: float, lon: float) -> float` |

### `src/phase2/tscast_nio/inference.py:82`

| symbol | signature |
|---|---|
| `TSCastPredictor.reconstruct` | `def reconstruct(self, lat: float, lon: float, date, argo_check=None) -> dict` |

### `src/phase2/tscast_nio/metrics.py`

| symbol | signature |
|---|---|
| `metrics.per_depth` | `def per_depth(pred, truth, clim=None, reference: str = 'argo', window=None) -> dict` |
| `metrics.rmse / bias / correlation` | `def rmse(pred, truth) -> float; def bias(pred, truth) -> float; def correlation(pred, truth) -> float` |
| `metrics.skill_rmse_ratio` | `def skill_rmse_ratio(pred, truth, clim) -> float  # 1 - RMSE/RMSE_clim` |
| `metrics.skill_vs_climatology` | `def skill_vs_climatology(pred, truth, clim) -> float  # Murphy, 1 - MSE/MSE_clim` |

### `src/phase2/tscast_nio/metrics.py:116`

| symbol | signature |
|---|---|
| `metrics.per_depth` | `def per_depth(pred, truth, clim=None, reference: str = 'argo', window=None) -> dict` |

### `src/phase2/tscast_nio/metrics.py:26-27`

| symbol | signature |
|---|---|
| `metrics.MIN_N / MIN_STD` | `MIN_N = 3; MIN_STD = 1e-6` |

### `src/phase2/tscast_nio/metrics.py:46-68`

| symbol | signature |
|---|---|
| `metrics.rmse / bias / correlation` | `def rmse(pred, truth) -> float; def bias(pred, truth) -> float  # model - truth; def correlation(pred, truth) -> float  # NaN, never 1.0, when constant` |

### `src/phase2/tscast_nio/metrics.py:71-113`

| symbol | signature |
|---|---|
| `metrics.skill_rmse_ratio / skill_vs_climatology` | `def skill_vs_climatology(pred, truth, clim) -> float  # 1 - MSE/MSE_clim; def skill_rmse_ratio(pred, truth, clim) -> float  # 1 - RMSE/RMSE_clim` |

### `src/phase2/tscast_nio/models/tscast.py`

| symbol | signature |
|---|---|
| `ClimatologyUNet.__init__` | `def __init__(self, latent: int, n_months: int = 12, levels: int = None, widths=None, n_out_channels: int = 1)  # submodules named stem, down_blocks, down_films, up_blocks, up_films, mu_head, logvar_head` |
| `LOGVAR_MIN, LOGVAR_MAX` | `LOGVAR_MIN, LOGVAR_MAX = -7.0, 7.0` |
| `TSCastNIO` | `class TSCastNIO(nn.Module): def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None, latent: int = None, residual: bool = True, unet_channels=None, decoder: str = 'film')` |
| `TSCastNIO.__init__` | `def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None, latent: int = None, residual: bool = True, unet_channels=None, decoder: str = "film")  # decoder must be 'film' or 'simple', else ValueError; sets self.encoder_name, self.decoder_name; decoder=='simple' sets self.decoder = None and builds self.simple_head = nn.Sequential(Linear(latent,256), Mish(), Linear(256, 2*config.N_DEPTHS))` |
| `TSCastNIO.forward` | `def forward(self, x, x_geo, clim, month)  # x (B,C,T,P,P); x_geo (B,3,1,P,P); clim (B,12,15) z-scored; month (B,) int -> (mu (B,15), logvar (B,15) clamped to [-7,7])` |
| `build (models)` | `def build(encoder_name: str, c_in: int, **kw) -> TSCastNIO` |
| `depth_interp_matrix` | `def depth_interp_matrix(src_depths, dst_depths) -> np.ndarray  # (n_dst, n_src)` |
| `gaussian_nll` | `def gaussian_nll(mu, logvar, y, mask, beta: float = 0.0)` |

### `src/phase2/tscast_nio/output.py`

| symbol | signature |
|---|---|
| `output._depth_context` | `def _depth_context(depth_m: int, rmse: list \| None) -> str` |
| `output.build_argo_check` | `def build_argo_check(argo_temperature, temperature, profile_id, distance_km, days_offset, source='argopy') -> dict` |
| `output.build_reasons` | `def build_reasons(sigma, valid, seafloor_depth_m, rmse=None) -> list[str]` |
| `output.build_record` | `def build_record(temperature, log_var_t, valid, seafloor_depth_m, provenance, argo_check=None, forecast=False, salinity=None, log_var_s=None, density=None, log_var_rho=None) -> dict` |
| `output.measured_rmse_by_depth` | `def measured_rmse_by_depth() -> tuple[list \| None, str]` |

### `src/phase2/tscast_nio/output.py:109`

| symbol | signature |
|---|---|
| `output.build_record` | `def build_record(temperature, log_var_t, valid, seafloor_depth_m, provenance, argo_check=None, forecast=False, salinity=None, log_var_s=None, density=None, log_var_rho=None) -> dict  # raises ValueError if forecast and argo_check is not None` |

### `src/phase2/tscast_nio/output.py:28`

| symbol | signature |
|---|---|
| `output.measured_rmse_by_depth` | `def measured_rmse_by_depth() -> tuple[list \| None, str]  # ERROR_SOURCES = ('tscast_stage1_metrics.json', 'tscast_baseline_metrics.json')` |

### `src/phase2/tscast_nio/output.py:59`

| symbol | signature |
|---|---|
| `output.build_reasons` | `def build_reasons(sigma, valid, seafloor_depth_m, rmse=None) -> list[str]` |

### `src/phase2/tscast_nio/output.py:78`

| symbol | signature |
|---|---|
| `output.build_argo_check` | `def build_argo_check(argo_temperature, temperature, profile_id, distance_km, days_offset, source='argopy') -> dict` |

### `src/phase2/tscast_nio/train/train_stage1.py`

| symbol | signature |
|---|---|
| `train_stage1 CLI` | `--epochs 20 \| --train-samples 40000 \| --test-samples 12000 \| --lr 1e-3 \| --batch-size 256 \| --encoder \| --no-residual \| --patience 4 \| --weight-decay 1e-2 \| --device auto \| --num-workers 0 \| --latent \| --unet-width N+ \| --decoder film\|simple \| --loss nll\|mse \| --data monthly\|daily \| --t-seq N \| --beta 0.5` |
| `train_stage1 checkpoint save` | `torch.save({"state_dict":..., "encoder":enc, "seed":base.SEED, "residual":not a.no_residual, "channels":d["channels"], "P":config.P, "T_SEQ":t_seq, "latent":latent, "unet_channels":list(widths), "norm":[v.tolist() for v in ds_tr.norm], "epochs":best["epoch"], "lr":a.lr, "batch_size":a.batch_size}, ck)  # lines 284-289; no decoder/loss/data/code_commit` |
| `train_stage1 model construction` | `model = TSCastNIO(enc, len(d["channels"]), t_seq=1, p=config.P, latent=latent, residual=not a.no_residual, unet_channels=widths, decoder=a.decoder).to(dev)  # line 156: t_seq is hardcoded 1 while the sampler uses t_seq (31)` |
| `train_stage1.MAX_DAYS` | `MAX_DAYS = 5` |
| `train_stage1.calibration` | `def calibration(pred, sigma, truth)  # per-depth RMSE / RMS(sigma); omits depths with <30 samples` |
| `train_stage1.main (argparse flags)` | `--epochs --train-samples --lr --batch-size --encoder --no-residual --patience --weight-decay --device --num-workers --latent --unet-width --decoder{film,simple} --loss{nll,mse} --data{monthly,daily} --t-seq --test-samples --beta` |
| `train_stage1.winning_encoder` | `def winning_encoder(default: str = "cnn3d") -> tuple[str, str]` |

### `src/phase2/tscast_nio/train/train_stage1.py:40`

| symbol | signature |
|---|---|
| `train_stage1.MAX_DAYS` | `MAX_DAYS = 5  # the Argo temporal gate every published v2 number was measured at` |

### `src/phase2/tscast_nio/train/train_stage1.py:52`

| symbol | signature |
|---|---|
| `train_stage1.calibration` | `def calibration(pred, sigma, truth) -> dict  # per depth RMSE / RMS(sigma); skips any depth with ok.sum() < 30` |

### `streamlit 1.62.0`

| symbol | signature |
|---|---|
| `st.altair_chart` | `st.altair_chart(altair_chart, *, width=None, height='content', use_container_width=None, theme='streamlit', key=None)  # use width='stretch'` |
| `st.metric` | `st.metric(label, value, delta=None, delta_color='normal', *, help=None, icon=None, label_visibility='visible', border=False, width='stretch', height='content', chart_data=...)` |

### `streamlit 1.62.0 streamlit/testing/v1`

| symbol | signature |
|---|---|
| `AppTest accessors` | `at.run(); at.exception; at.metric (elements with .label/.value/.delta); at.caption/.markdown/.info/.warning/.error/.success/.dataframe/.slider/.selectbox/.date_input/.tabs/.expander/.columns/.main  [VERIFIED at.metric descends into tabs, columns and expanders]` |
| `AppTest.from_file / from_string` | `AppTest.from_file(script_path: str \| Path, *, default_timeout: float = 3) -> AppTest; AppTest.from_string(script: str, *, default_timeout: float = 3) -> AppTest` |
