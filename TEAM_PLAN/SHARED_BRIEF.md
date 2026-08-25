# SHARED BRIEF — paste this into your Claude session FIRST

> Every teammate pastes this block into their Claude Code account at the start, **then** pastes their own unit block
> (from UNIT_A / UNIT_B / UNIT_C). This makes every Claude session follow the same rules.

```
You are working on OceanEmbed (SIH26066, Ministry of Earth Sciences). We reconstruct subsurface ocean TEMPERATURE at
multiple depths from SURFACE ocean variables (SST, SSS, SSH, u, v) at 0.25° resolution over the North Indian Ocean
(5–30N, 45–105E). Training truth = GLORYS12 reanalysis. Independent validation = real Argo floats. Lead model =
per-column MLP; baselines = climatology + LightGBM; uncertainty = MC-dropout; UI = Streamlit. Python. Deadline: a
working demo on Aug 30 — a 5-day sprint. We are beginners; explain briefly what and why, then implement.

HARD RULES:
1. OWNERSHIP: I own ONLY the files listed in my unit block. NEVER create or edit files owned by another unit.
2. CONTRACTS: All array shapes, filenames, and function signatures come from docs/DATA_CONTRACT.md and
   docs/MODEL_SPEC.md. Never invent a shape, unit, or filename. Import FEATURES/DEPTHS/LAT/LON from config — never
   hardcode them. If a contract needs to change, edit the contract file first and tell me to notify the team.
3. COMMUNICATE VIA FILES: hand off work only by writing named files into artifacts/. Never import another unit's code.
4. FIXTURES: until real data exists, develop against artifacts/sample_*.npy (same shapes). No rework when real data lands.
5. EVIDENCE TAGS: label every claim [VERIFIED] (you actually ran it / inspected it / read it), [INFERRED] (reasonable
   guess, not tested), or [UNKNOWN]. Only [VERIFIED] may be stated as fact.
6. NEVER: claim code works unless you executed it; claim a dataset has a variable unless you inspected it; claim a model
   improves unless you ran the comparison; fabricate metrics, uncertainty, or citations; assume tensor dims, units,
   coordinate order, temporal alignment, missing-value handling, or a valid train/test split.
7. ENGINEERING LOOP for every task: UNDERSTAND -> INSPECT repo -> read the relevant doc -> PLAN -> IMPLEMENT smallest
   working version -> run TESTS -> run a real-data smoke test -> inspect output -> DOCUMENT (update docs/HANDOFF.md) ->
   git COMMIT. Do not jump straight from request to a huge implementation.
8. DEFINITION OF DONE: code exists + tests pass + it ran on real/fixture data + output inspected + reproducible (seed +
   config saved) + docs updated + committed. For ML also: training done, validation done, metrics + checkpoint + seed +
   config logged to docs/EXPERIMENT_LOG.md.
9. LIBRARIES: before coding against any library (copernicusmarine, argopy, xarray, streamlit, torch, lightgbm), use
   Context7 to fetch its CURRENT docs — your training data may be outdated.
10. Report the exact files you changed at the end of every task, and paste the real command output you got.
```

## The frozen constants (do not change without a group decision)

```python
LAT      = np.arange(5.0, 30.0, 0.25)     # 100 values
LON      = np.arange(45.0, 105.0, 0.25)   # 240 values
DEPTHS   = [0,10,20,30,50,75,100,150,200,300,500]   # meters, 11 depths
FEATURES = ["sst","sss","ssh","u","v",
            "sin_lat","cos_lat","sin_lon","cos_lon","sin_doy","cos_doy"]   # 11 features
SPLIT    = train 2019–2021, test 2022 (by TIME — never random-split adjacent cells/days)
```

## Shared artifacts/ file schemas (who produces what)

| File | Producer | Shape / schema |
|---|---|---|
| `sample_X.npy`,`sample_y.npy`,`sample_meta.parquet` | B (Day 1) | tiny fake fixtures, N=500, same shapes as real |
| `X_train.npy`,`X_test.npy` | B | float32 `(N, 11)` — columns in FEATURES order |
| `y_train.npy`,`y_test.npy` | B | float32 `(N, 11)` — temperature at DEPTHS |
| `meta_train.parquet`,`meta_test.parquet` | B | row-aligned to X/y: `[lat, lon, date, month, cell_id]` |
| `norm_stats.json` | B | `{feat_mean[11], feat_std[11], targ_mean[11], targ_std[11]}` |
| `land_mask.npy` | B | bool `(100,240)`, True = land |
| `argo_test.parquet` | B | `[lat, lon, date, depth_idx(0..10), temp]` (real Argo, 2022) |
| `mlp_model.pt` | A | PyTorch state_dict for MLPProfile |
| `lgbm_model.pkl` | A | list of 11 LightGBM boosters (one per depth) |
| `climatology.npy` | C | `(12, 100, 240, 11)` = [month, lat, lon, depth] |
