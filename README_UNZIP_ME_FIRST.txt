OceanEmbed Phase-2 REAL DATA -- from Darshan's machine
=======================================================

WHY YOU NEEDED THIS
You built F4 and F5 against a synthetic stand-in because none of this travels through git
(data/ and artifacts/ are gitignored). Everything here is REAL: 48 GLORYS dates 2019-2022,
real subsurface salinity, real satellite L4, 2,455 real Argo profiles, 48 months of wind.

HOW TO INSTALL
  1. unzip INTO THE REPO ROOT so paths land as data/... and artifacts/...
  2. verify:  python scripts/phase2/verify_data_bundle.py
  3. the one line that matters:
        python -c "import json;print(json.load(open('artifacts/provenance.json')))"
     must read  source=real-glorys  and  n_depths=15.
     Anything else means the data did not land correctly.

WHAT IS IN HERE, AND WHY
  data/processed/grids.npz          32 MB  temperature (48,100,240,15) + surface + masks
  data/processed/subsurface.npz     77 MB  salinity + u,v at depth -> REAL density for F5 OHC
  data/processed/satellite_grids.npz 4 MB  OSTIA/DUACS/Multiobs, 24 dates
  data/raw/wind/ (48 files)         23 MB  wind + WIND STRESS -> Ekman pumping for F6
  artifacts/argo_error_by_depth.json       per-depth error vs 879 independent Argo profiles
  artifacts/mlp_model.pt, X_test, y_test, norm_stats   F4 calibration + OOD
  artifacts/climatology*.npy               anomaly reference and interannual sigma
  artifacts/argo_test.parquet              2,455 real Argo profiles

DELIBERATELY EXCLUDED (not needed to TEST, only to retrain)
  lgbm_model.pkl + lgbm_quantiles.pkl  64 MB   regenerate: python -m oceanembed.train.train_lgbm
  X_train.npy + y_train.npy            32 MB   regenerate: python scripts/prepare_dataset.py --real
  data/raw/glorys_*.nc                2.9 GB   only needed to rebuild processed grids from scratch

THINGS THAT WILL BITE YOU
  * If you cut a NEW branch, `rm -f tests/phase2/__init__.py` first. It shadows src/phase2 and
    every `from phase2... import` dies under pytest while working fine outside it.
  * Branch names: `phase2-reliability`, NOT `phase2/reliability`. Git refuses the slash form
    while a branch named `phase2` exists.
  * The Bay of Bengal barrier layer is SEASONAL. A single-date check can invert the signal --
    it did for me. December is one of only two months where the Arabian Sea is thicker.
    Measure across months.

DEMO-DAY NOTE
These are exactly the directories the presentation laptop needs. Copying this zip is also the
copy rehearsal. data/raw/*.nc is NOT needed to run the app -- only data/processed/ and artifacts/.
