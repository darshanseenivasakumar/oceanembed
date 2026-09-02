"""Download the PS-compliant TOTAL surface current channel. (Unit A / Arjhun, contract §13.)

WHY THIS EXISTS
The official SIH26066 PS names PO.DAAC `OSCAR_L4_OC_FINAL_V2.0` for currents -- a TOTAL surface
current. What we hold instead is DUACS `ugos`/`vgos` from `data/raw/satellite_nrt/ssh_*.nc`, which
are GEOSTROPHIC ONLY. That is the wrong physical quantity, not a unit problem: GLORYS `uo`/`vo`,
which the model trains against, include ageostrophic (Ekman) flow.

WHY NOT OSCAR ITSELF
OSCAR lives on PO.DAAC and needs a NASA Earthdata login this project does not have. Probed the
CMEMS catalogue instead and found the correct equivalent, on credentials that already work:

    MULTIOBS_GLO_PHY_MYNRT_015_003 -- "Global Total (COPERNICUS-GLOBCURRENT), Ekman and
    Geostrophic currents at the Surface"

    dataset  : cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m
    coverage : 2022-05-01 .. 2026-08-31   [VERIFIED by probing this machine 2026-09-01]
    grid     : NATIVE 0.25 deg -- our target resolution exactly, so NO regridding at all
    uo, vo   : "absolute surface geostrophic + depth Ekman velocity"

This is a DOCUMENTED DEVIATION from the PS's named product, justified by: identical physical
quantity, identical resolution and cadence, satellite multi-observation class, and the PS's own
allowance to "select the openly available product". It must appear in the bundle provenance and be
stated to the jury -- never quietly swapped.

WHY NRT AND NOT THE DELAYED-MODE TWIN
`cmems_obs-mob_glo_phy-cur_my_0.25deg_P1D-m` ends 2026-03-31 and cannot reach our test window --
the same conclusion commit 8555a86 reached for SST and SSH. One product across the whole record;
nothing spliced mid-series.

Run:  PYTHONPATH=src python scripts/phase2/download_currents_daily.py           # resumable
      PYTHONPATH=src python scripts/phase2/download_currents_daily.py --probe   # coverage only
      PYTHONPATH=src python scripts/phase2/download_currents_daily.py --verify  # check what landed
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config  # noqa: E402

START, END = "2025-06-01", "2026-06-23"
DATASET_ID = "cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m"
VARIABLES = ["uo", "vo"]
OUT_DIR = os.path.join(config.DATA_RAW, "currents_nrt")

# Physical plausibility. Surface currents in the NIO run well under 3 m/s; the Somali Jet is the
# fastest thing in our box and peaks near 2 m/s. A value past this means wrong units or a fill
# value read as data.
MAX_SPEED_MS = 3.0


def _fix_ssl() -> None:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


def probe() -> None:
    """Print the product's real coverage. Run this before trusting any of it."""
    import numpy as np
    import copernicusmarine as cm

    def to_date(x):
        x = int(x)
        # CMEMS reports these bounds in SECONDS for some datasets, MILLISECONDS for others.
        return str(np.datetime64(x // 1000 if abs(x) > 1e11 else x, "s"))[:10]

    d = cm.describe(dataset_id=DATASET_ID).products[0].datasets[0]
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
    print(f"  {'ok  ' if ok else 'GAP '} currents: {lo} .. {hi}   (need {START} .. {END})")


def download(start: str = START, end: str = END, out_dir: str = OUT_DIR) -> str:
    """One NetCDF per day. Skips files already on disk, so an interrupt just resumes.

    Serialised on purpose: concurrent CMEMS requests previously threw SSLError and
    CouldNotConnectToAuthenticationSystem on this machine.
    """
    _fix_ssl()
    import copernicusmarine as cm

    os.makedirs(out_dir, exist_ok=True)
    r = config.REGION
    dates = pd.date_range(start, end, freq="D")

    total_mb, failed = 0.0, []
    for i, d in enumerate(dates, 1):
        fname = f"cur_{d:%Y%m%d}.nc"
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            total_mb += os.path.getsize(fpath) / 1e6
            continue
        try:
            cm.subset(
                dataset_id=DATASET_ID, variables=VARIABLES,
                minimum_longitude=r["lon_min"], maximum_longitude=r["lon_max"],
                minimum_latitude=r["lat_min"], maximum_latitude=r["lat_max"],
                start_datetime=f"{d:%Y-%m-%d}", end_datetime=f"{d:%Y-%m-%d}",
                output_directory=out_dir, output_filename=fname, overwrite=True,
                disable_progress_bar=True,
            )
            total_mb += os.path.getsize(fpath) / 1e6
        except Exception as e:
            failed.append(f"{d:%Y-%m-%d}")
            print(f"[cur] {d:%Y-%m-%d} FAILED: {type(e).__name__}: {str(e)[:70]}", flush=True)
        if i % 25 == 0:
            print(f"[cur] {i}/{len(dates)}  {total_mb / 1000:.2f} GB", flush=True)

    print(f"[cur] done: {len(dates) - len(failed)}/{len(dates)} files, {total_mb / 1000:.2f} GB",
          flush=True)
    if failed:
        print(f"[cur] {len(failed)} FAILED (rerun to resume): {failed[:10]}", flush=True)
    return out_dir


def verify(out_dir: str = OUT_DIR) -> int:
    """Refuse to call this channel usable on file count alone. Returns a process exit code."""
    import numpy as np
    import xarray as xr

    dates = pd.date_range(START, END, freq="D")
    missing = [f"{d:%Y-%m-%d}" for d in dates
               if not os.path.exists(os.path.join(out_dir, f"cur_{d:%Y%m%d}.nc"))]
    print(f"  files      : {len(dates) - len(missing)}/{len(dates)}")
    if missing:
        print(f"  MISSING    : {len(missing)} days, first {missing[:5]}")
        return 1

    step_target = config.REGION["step"]
    bad = []

    # EVERY file is opened, not a sample. A sampled check cannot see a truncated file, and this
    # download is resumable-by-existence: `download()` skips any path that exists and is non-empty,
    # so a file left half-written by an interrupted run is never refetched. It would sit on disk
    # looking like a completed day and be read as data later. Opening all 388 costs seconds.
    #
    # (Not a concurrency concern: copernicusmarine spawns a child worker, so two python processes
    # for one download are normal and are not two writers.)
    unreadable = []
    for d in dates:
        p = os.path.join(out_dir, f"cur_{d:%Y%m%d}.nc")
        try:
            with xr.open_dataset(p) as ds:
                if not all(v in ds for v in VARIABLES):
                    unreadable.append(f"{d:%Y-%m-%d}: missing {set(VARIABLES) - set(ds.data_vars)}")
        except Exception as e:
            unreadable.append(f"{d:%Y-%m-%d}: {type(e).__name__}: {str(e)[:60]}")
    print(f"  readable   : {len(dates) - len(unreadable)}/{len(dates)} open cleanly with uo and vo")
    if unreadable:
        print(f"  CORRUPT    : {len(unreadable)} -- delete these and rerun to refetch:")
        for u in unreadable[:10]:
            print(f"    {u}")
        return 1

    for d in (dates[0], dates[len(dates) // 2], dates[-1]):
        p = os.path.join(out_dir, f"cur_{d:%Y%m%d}.nc")
        with xr.open_dataset(p) as ds:
            for v in VARIABLES:
                if v not in ds:
                    bad.append(f"{d:%Y-%m-%d}: {v} absent")
                    continue
                a = np.asarray(ds[v].values, dtype="float64")
                if not np.isfinite(a).any():
                    bad.append(f"{d:%Y-%m-%d}: {v} all-NaN")
                elif np.nanmax(np.abs(a)) > MAX_SPEED_MS:
                    bad.append(f"{d:%Y-%m-%d}: abs({v}) max={np.nanmax(np.abs(a)):.2f} "
                               f"> {MAX_SPEED_MS} m/s -- wrong units or a fill read as data")
            step = float(np.diff(ds["latitude"].values)[0])
            if abs(step - step_target) > 1e-6:
                bad.append(f"{d:%Y-%m-%d}: lat step {step} != {step_target}")
    # The STEP matches ours; the OFFSET does not. Native centres are 5.125, 5.375 ... against our
    # 5.0, 5.25 ... -- half a cell, ~14 km. This line used to read "no regrid needed", which was
    # wrong and green at the same time: sat_daily_pipeline applies a bilinear half-cell shift, and
    # shipping these unshifted would misplace every current value.
    print(f"  grid       : step {step_target} deg matches ours, but centres are offset half a "
          f"cell -- sat_daily_pipeline shifts them, they are NOT drop-in")
    if bad:
        print("  FAILED:")
        for b in bad:
            print(f"    {b}")
        return 1
    print(f"  ranges     : speeds <= {MAX_SPEED_MS} m/s on 3 sampled days, finite over ocean")
    print("  OK")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="print coverage and exit")
    ap.add_argument("--verify", action="store_true", help="check what landed and exit")
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args()
    if a.probe:
        probe()
        return
    if a.verify:
        raise SystemExit(verify(a.out_dir))
    download(out_dir=a.out_dir)
    raise SystemExit(verify(a.out_dir))


if __name__ == "__main__":
    main()
