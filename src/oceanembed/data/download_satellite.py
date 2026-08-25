"""Download REAL satellite L4 surface observations for the NIO box.

OWNER: Unit B (Darshan).

WHY THIS EXISTS
---------------
SIH26066 asks for reconstruction "from surface satellite observations". Training uses GLORYS12
reanalysis (it is the only source with a complete gridded SUBSURFACE target), but inference should
run on ACTUAL SATELLITE FIELDS. This module fetches them.

Train on reanalysis -> infer on observations is the standard setup, and it is also an honest
DOMAIN-SHIFT experiment: the satellite fields are NOT the same quantities GLORYS produces, so skill
is expected to drop. We measure that drop rather than hide it (scripts/compare_satellite_vs_glorys.py).

PRODUCTS  [dataset ids + variables + units VERIFIED 2026-08-25 by probe download]
  SST : METOFFICE-GLO-SST-L4-REP-OBS-SST                          analysed_sst  [KELVIN]
  SSH : cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1D  adt, ugos, vgos  [m, m/s]
  SSS : cmems_obs-mob_glo_phy-sss_my_multi_P1D                    sos  [0.001 == PSS-78]

KNOWN QUANTITY MISMATCHES vs the GLORYS fields the model was trained on -- state these, do not paper
over them:
  * analysed_sst is in KELVIN; GLORYS thetao is degC. Converted here (-273.15). Silent if missed.
  * DUACS `adt` (absolute dynamic topography, referenced to a mean geoid) is the closest analogue to
    GLORYS `zos`, but they are not identical and can carry a constant offset. Measured, not assumed.
  * `ugos`/`vgos` are GEOSTROPHIC currents from altimetry. GLORYS `uo`/`vo` also contain ageostrophic
    (e.g. Ekman) flow. This is a genuine difference in the physical quantity, not a units problem.

Run:  python -m oceanembed.data.download_satellite
"""
from __future__ import annotations
import os
import pandas as pd
from oceanembed import config

SST_ID = "METOFFICE-GLO-SST-L4-REP-OBS-SST"
SSH_ID = "cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1D"
SSS_ID = "cmems_obs-mob_glo_phy-sss_my_multi_P1D"

SOURCES = [
    ("sst", SST_ID, ["analysed_sst"]),
    ("ssh", SSH_ID, ["adt", "ugos", "vgos"]),
    ("sss", SSS_ID, ["sos"]),
]

OUT_DIR = os.path.join(config.DATA_RAW, "satellite")


def _fix_ssl() -> None:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def download_dates(dates=None, out_dir: str = OUT_DIR) -> str:
    """One NetCDF per (source, date) into data/raw/satellite/. Skips files already present."""
    _fix_ssl()
    import copernicusmarine

    if dates is None:  # default: the TEST year -- that is where Argo validation happens
        dates = [pd.Timestamp(year=y, month=m, day=15)
                 for y in config.TEST_YEARS for m in range(1, 13)]
    dates = [pd.Timestamp(d) for d in dates]
    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION

    total_mb, failed = 0.0, []
    for i, d in enumerate(dates, 1):
        for name, did, variables in SOURCES:
            fname = f"{name}_{d:%Y%m%d}.nc"
            fpath = os.path.join(out_dir, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                total_mb += os.path.getsize(fpath) / 1e6
                continue
            try:
                copernicusmarine.subset(
                    dataset_id=did, variables=variables,
                    minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                    minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                    start_datetime=f"{d:%Y-%m-%d}", end_datetime=f"{d:%Y-%m-%d}",
                    output_directory=out_dir, output_filename=fname, overwrite=True,
                )
                total_mb += os.path.getsize(fpath) / 1e6
            except Exception as e:
                failed.append(f"{name}_{d:%Y-%m-%d}")
                print(f"[sat] {name} {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:80]}")
        print(f"[sat] {i:3d}/{len(dates)} {d:%Y-%m-%d} done  (total {total_mb:.0f} MB)")

    print(f"\n[sat] {len(dates)} dates, {total_mb:.0f} MB in {out_dir}")
    if failed:
        print(f"[sat] FAILED ({len(failed)}): {failed}\n  re-run to retry only those.")
    return out_dir


if __name__ == "__main__":
    download_dates()
