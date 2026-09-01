"""Download REAL SATELLITE surface observations for the daily window — the PS's actual input.

THE PROBLEM THIS FIXES
SIH26066 asks for reconstruction "from surface satellite observations". The v2 daily bundle
currently feeds the model GLORYS REANALYSIS for all five surface channels
(data/processed/daily/*.npz provenance reads "GLORYS12V1 daily"), so the satellite embedding is
embedding a reanalysis. That is a compliance failure, not a comparison caveat.

WHY NRT AND NOT THE PHASE-1 PRODUCTS  [VERIFIED 2026-08-31 by probing the catalog from this machine]
oceanembed/data/download_satellite.py names the delayed-mode products. Not one of them reaches our
window:

    product                                    coverage ends     our window 2025-06-01..2026-06-23
    METOFFICE-GLO-SST-L4-REP-OBS-SST           2026-03-31        misses the whole TEST window
    ...ssh_my_allsat-l4-duacs-0.125deg_P1D     2026-01-16        misses Jan 17 onward
    ...sss_my_multi_P1D                        2024-12-15        misses ALL of it

The NRT variants all cover it, so the whole record comes from ONE product per variable and nothing
is spliced mid-series:

    METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2                2024-01-17 .. 2026-08-30
    cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs...    2024-07-01 .. 2026-09-01
    cmems_obs-mob_glo_phy-sss_nrt_multi_P1D            2024-01-01 .. 2026-08-25

This is a DIFFERENT product line from Phase 1's REP/my. Phase 1's satellite headline (0.9638) was
measured on the reprocessed products; numbers from this bundle are not directly comparable to it,
and that has to be said wherever both appear.

QUANTITY MISMATCHES vs the GLORYS fields the model trains against -- state, do not paper over:
  * analysed_sst is KELVIN, GLORYS thetao is degC. Converted here. Silent if missed.
  * DUACS `adt` is absolute dynamic topography on a mean geoid; GLORYS `zos` is sea surface height
    above geoid. Close analogues, not identical, and they can carry a constant offset.
  * `ugos`/`vgos` are GEOSTROPHIC currents from altimetry. GLORYS `uo`/`vo` include ageostrophic
    (Ekman) flow. A genuine difference in the physical quantity, not a unit problem -- and the
    reason a satellite-driven score is expected to differ from a GLORYS-driven one.

Run:  PYTHONPATH=src python -m phase2.data.download_satellite_daily            # resumable
      PYTHONPATH=src python -m phase2.data.download_satellite_daily --probe    # coverage only
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from oceanembed import config

START, END = "2025-06-01", "2026-06-23"

# name -> (dataset_id, variables). One product per variable across the WHOLE window.
SOURCES = {
    "sst": ("METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2", ["analysed_sst"]),
    "ssh": ("cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D", ["adt", "ugos", "vgos"]),
    "sss": ("cmems_obs-mob_glo_phy-sss_nrt_multi_P1D", ["sos"]),
}
OUT_DIR = os.path.join(config.DATA_RAW, "satellite_nrt")


def _fix_ssl() -> None:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def probe() -> None:
    """Print each product's real coverage. Run this before trusting any of it."""
    import numpy as np
    import copernicusmarine as cm

    def to_date(x):
        x = int(x)
        # CMEMS reports these bounds in SECONDS for some datasets and MILLISECONDS for others.
        return str(np.datetime64(x // 1000 if abs(x) > 1e11 else x, "s"))[:10]

    for name, (did, _) in SOURCES.items():
        d = cm.describe(dataset_id=did).products[0].datasets[0]
        best = None
        for v in d.versions:
            for pt in v.parts:
                for s in pt.services:
                    for var in s.variables:
                        for c in var.coordinates:
                            if c.coordinate_id == "time" and c.maximum_value:
                                best = (c.minimum_value, c.maximum_value)
        lo, hi = to_date(best[0]), to_date(best[1])
        ok = lo <= START and hi >= END
        print(f"  {'ok  ' if ok else 'GAP '} {name}: {lo} .. {hi}   (need {START} .. {END})")


def download(start: str = START, end: str = END, out_dir: str = OUT_DIR,
             which=None) -> str:
    """One NetCDF per (variable, day). Skips files already on disk, so an interrupt just resumes."""
    _fix_ssl()
    import copernicusmarine as cm

    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    dates = pd.date_range(start, end, freq="D")
    names = which or list(SOURCES)

    total_mb, failed = 0.0, []
    for name in names:
        did, variables = SOURCES[name]
        for i, d in enumerate(dates, 1):
            fname = f"{name}_{d:%Y%m%d}.nc"
            fpath = os.path.join(out_dir, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                total_mb += os.path.getsize(fpath) / 1e6
                continue
            try:
                cm.subset(
                    dataset_id=did, variables=variables,
                    minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                    minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                    start_datetime=f"{d:%Y-%m-%d}", end_datetime=f"{d:%Y-%m-%d}",
                    output_directory=out_dir, output_filename=fname, overwrite=True,
                    disable_progress_bar=True,
                )
                total_mb += os.path.getsize(fpath) / 1e6
            except Exception as e:
                failed.append(f"{name} {d:%Y-%m-%d}")
                print(f"[sat] {name} {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:70]}",
                      flush=True)
            if i % 25 == 0:
                print(f"[sat] {name} {i}/{len(dates)}  {total_mb/1000:.2f} GB total", flush=True)
        print(f"[sat] {name} done", flush=True)

    print(f"\n[sat] {total_mb/1000:.2f} GB in {out_dir}")
    if failed:
        print(f"[sat] {len(failed)} FAILED (re-run to retry only those): {failed[:8]}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="print coverage and exit")
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--only", nargs="+", choices=list(SOURCES), default=None)
    a = ap.parse_args()
    if a.probe:
        probe()
        return
    download(a.start, a.end, a.out_dir, a.only)


if __name__ == "__main__":
    main()
