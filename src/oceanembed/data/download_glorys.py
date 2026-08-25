"""Download GLORYS12 (CMEMS reanalysis) surface+subsurface fields for the NIO box.

OWNER: Unit B (Darshan).
API VERIFIED via Context7 (copernicus-marine-toolbox). Runtime NOT verified here: needs a free CMEMS
account + `pip install copernicusmarine`. Set credentials once, then run this.

Credentials (either):
  copernicusmarine login          # CLI, saves to ~/.copernicusmarine
  # or env vars:
  #   set COPERNICUSMARINE_SERVICE_USERNAME=you
  #   set COPERNICUSMARINE_SERVICE_PASSWORD=***

Dataset id [VERIFIED 2026-08-25 via `copernicusmarine.describe(contains=['GLOBAL_MULTIYEAR_PHY_001_030'])`]:
  cmems_mod_glo_phy_my_0.083deg_P1D-m     <- GLORYS12V1 daily means (what we use)
Others in the same product: ..._P1M-m (monthly), ..._0.083deg-climatology_P1M-m, ..._static.
The catalog listing worked WITHOUT login; the actual `subset` download DOES require a free CMEMS account.

Run:  python -m oceanembed.data.download_glorys
"""
from __future__ import annotations
import os
from oceanembed import config

DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"   # [INFERRED] confirm before trusting
VARIABLES = ["thetao", "so", "zos", "uo", "vo"]        # temp, salinity, ssh, u, v
# Depth range to cover our DEPTHS (0..500 m) with margin; regridding to DEPTHS happens in preprocess.py
MIN_DEPTH, MAX_DEPTH = 0.0, 600.0


def download(start="2019-01-01", end="2022-12-31", dataset_id=DATASET_ID, variables=VARIABLES,
             out_dir=None) -> str:
    """Subset GLORYS to the NIO box and save NetCDF(s) into data/raw/. Returns the output directory."""
    import copernicusmarine  # imported here so the repo imports without the package installed
    out_dir = out_dir or config.DATA_RAW
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    print(f"[glorys] subset {dataset_id} vars={variables} box=({r['lat_min']}-{r['lat_max']}N,"
          f"{r['lon_min']}-{r['lon_max']}E) {start}..{end}")
    resp = copernicusmarine.subset(
        dataset_id=dataset_id,
        variables=variables,
        minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
        minimum_latitude=r["lat_min"],  maximum_latitude=r["lat_max"],
        minimum_depth=MIN_DEPTH, maximum_depth=MAX_DEPTH,
        start_datetime=start, end_datetime=end,
        file_format="netcdf",
        output_directory=out_dir,
    )
    print(f"[glorys] saved to {out_dir}  ({resp})")
    print("NEXT: inspect one file and record lat/lon order, depth sign, units in docs/DATA_CONTRACT.md [VERIFIED].")
    return out_dir


if __name__ == "__main__":
    # Tip: for a first, lighter pull use one year, or subsample later in preprocess.
    download()
