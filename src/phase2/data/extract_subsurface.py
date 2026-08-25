"""Extract SUBSURFACE salinity and currents from the GLORYS files we ALREADY have.

OWNER: Unit B (Darshan). PHASE-2 ONLY. Reads the baseline's raw files; writes a NEW file.
Does not touch data/processed/grids.npz and does not modify any baseline module.

WHY THIS EXISTS — and why it needed no download
The Phase-2 audit recorded "no subsurface salinity" as a blocker for ocean heat content. That was
wrong about the CAUSE. [VERIFIED 2026-08-26] the raw GLORYS files already contain
    thetao, so, uo, vo   all with dims (time, depth, latitude, longitude), 36 depth levels
The baseline simply never extracted them: `preprocess.py` takes `so`/`uo`/`vo` at depth index 0
only, because Phase 1 needed surface predictors and nothing else. The subsurface fields have been
sitting in data/raw/ the whole time.

So F5 (ocean heat content) is unblocked with zero download and zero baseline change.

WHAT THIS UNLOCKS
    salinity at depth  -> real seawater density -> honest OHC instead of an assumed constant rho
    currents at depth  -> subsurface circulation for event detection
    T and S together   -> stratification, buoyancy frequency, water-mass identification

OUTPUT: data/processed/subsurface.npz
    times      datetime64[D]        (T,)
    salinity   float32              (T, 100, 240, 15)   PSS-78
    u, v       float32              (T, 100, 240, 15)   m s-1
    valid_mask bool                 (100, 240, 15)      True = real water (same convention as baseline)

Grid, depths and conventions are IMPORTED from the baseline config so they cannot drift.

Run:  python -m phase2.data.extract_subsurface
"""
from __future__ import annotations
import glob as _glob
import os
import numpy as np
import xarray as xr

from oceanembed import config                        # baseline config: IMPORTED, never modified
from oceanembed.data.preprocess import _find_coord   # baseline helper: IMPORTED, never modified

OUT = os.path.join(config.DATA_PROCESSED, "subsurface.npz")

# Physical-range guards: a unit slip must fail loudly rather than propagate into a density
# calculation. The salinity FLOOR is 0, not the ~20 psu one might assume for open ocean.
# [VERIFIED 2026-08-26] the raw GLORYS minimum in this domain is 6.43 psu at 22.50N 91.25E --
# the Meghna/Ganges estuary in the northern Bay of Bengal -- and it goes lower during peak monsoon
# discharge. The extrapolated value equals the raw value there, so this is real river-influenced
# water, not an interpolation artifact. A 20 psu floor would have rejected the single most
# distinctive feature of this basin. Only NEGATIVE salinity is unphysical.
BOUNDS = {"salinity": (0.0, 42.0), "u": (-5.0, 5.0), "v": (-5.0, 5.0)}


def _one_file(path: str):
    """Regrid one GLORYS file's subsurface so/uo/vo onto the frozen grid and depth levels."""
    with xr.open_dataset(path) as ds:
        latn = _find_coord(ds, "latitude", "lat", "nav_lat")
        lonn = _find_coord(ds, "longitude", "lon", "nav_lon")
        depthn = _find_coord(ds, "depth", "deptht", "lev")
        timen = _find_coord(ds, "time", "time_counter")

        ds = ds.sortby(latn).sortby(lonn).sortby(depthn)
        ds = ds.interp({latn: config.LAT, lonn: config.LON}, method="linear")

        # Deep extrapolation would invent water below the sea floor, exactly the bug the baseline
        # hit at 500 m. Refuse instead, same as preprocess.run().
        d_max = float(ds[depthn].max())
        too_deep = [d for d in config.DEPTHS if d > d_max]
        if too_deep:
            raise ValueError(
                f"{os.path.basename(path)} only reaches {d_max:.1f} m but config.DEPTHS asks for "
                f"{too_deep}. Refusing to extrapolate below the sea floor."
            )

        out = {}
        for var, name in [("so", "salinity"), ("uo", "u"), ("vo", "v")]:
            a = ds[var].interp({depthn: config.DEPTHS}, method="linear",
                               kwargs={"fill_value": "extrapolate"})
            out[name] = a.transpose(timen, latn, lonn, depthn).values.astype("float32")
        times = np.asarray(ds[timen].values).astype("datetime64[D]")
    return times, out


def run(raw_glob: str | None = None, out_path: str = OUT) -> str:
    raw_glob = raw_glob or os.path.join(config.DATA_RAW, "glorys_*.nc")
    files = sorted(_glob.glob(raw_glob))
    if not files:
        raise FileNotFoundError(f"no GLORYS files matched {raw_glob}")
    print(f"[subsurface] {len(files)} GLORYS file(s)")

    all_t, acc = [], {k: [] for k in ["salinity", "u", "v"]}
    for i, f in enumerate(files, 1):
        t, o = _one_file(f)
        all_t.append(t)
        for k in acc:
            acc[k].append(o[k])
        if i % 12 == 0 or i == len(files):
            print(f"[subsurface]   {i}/{len(files)} done")

    times = np.concatenate(all_t)
    order = np.argsort(times)
    times = times[order]
    fields = {k: np.concatenate(v, axis=0)[order] for k, v in acc.items()}

    for k, (lo, hi) in BOUNDS.items():
        f = fields[k][np.isfinite(fields[k])]
        if f.size and (f.min() < lo or f.max() > hi):
            raise ValueError(f"{k} out of physical range [{lo},{hi}]: {f.min():.2f}..{f.max():.2f}")

    valid_mask = ~np.isnan(fields["salinity"]).any(axis=0)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    np.savez_compressed(out_path, times=times, valid_mask=valid_mask,
                        source=np.array("real-glorys-subsurface"), **fields)

    print(f"[subsurface] wrote {out_path}: T={len(times)}, "
          f"grid={config.N_LAT}x{config.N_LON}x{config.N_DEPTHS}")
    for k in ["salinity", "u", "v"]:
        a = fields[k][np.isfinite(fields[k])]
        print(f"    {k:9s} {a.min():7.2f} .. {a.max():7.2f}   mean {a.mean():7.2f}")
    print(f"    cells with water at {config.DEPTHS[-1]} m: {int(valid_mask[..., -1].sum())}")
    return out_path


if __name__ == "__main__":
    run()
