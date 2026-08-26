"""Verify the Phase-2 data bundle landed intact and is REAL — run this after unzipping.

    python scripts/phase2/verify_data_bundle.py

Checks three things, in increasing order of what they prove:
  1. FILES     — every expected file present, right size, right checksum
  2. CONTRACT  — shapes, grid, depths and times match the frozen baseline config
  3. SCIENCE   — the data behaves like the North Indian Ocean, not like a synthetic stand-in

Check 3 is the one that matters. A synthetic array can pass 1 and 2 and still be fiction.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from oceanembed import config  # noqa: E402

OK, BAD = "  [ok]  ", "  [FAIL]"
fails: list[str] = []


def check(cond: bool, msg: str, detail: str = "") -> bool:
    print(f"{OK if cond else BAD} {msg}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(msg)
    return cond


def sha16(p: str, n: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while (b := f.read(n)):
            h.update(b)
    return h.hexdigest()[:16]


def main() -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    os.chdir(os.path.abspath(root))

    print("=" * 70)
    print("1. FILES")
    print("=" * 70)
    man_path = "PHASE2_DATA_MANIFEST.json"
    if os.path.exists(man_path):
        man = json.load(open(man_path))
        missing = [f for f in man["files"] if not os.path.exists(f)]
        check(not missing, f"all {len(man['files'])} bundle files present",
              f"missing: {missing[:3]}" if missing else "")
        bad = [f for f, m in man["files"].items()
               if os.path.exists(f) and sha16(f) != m["sha256_16"]]
        check(not bad, "checksums match", f"corrupt: {bad[:3]}" if bad else "")
    else:
        print("  (no manifest — unzipped without it, or built by hand; skipping checksum check)")
        for f in ["data/processed/grids.npz", "data/processed/subsurface.npz",
                  "artifacts/provenance.json", "artifacts/argo_error_by_depth.json"]:
            check(os.path.exists(f), f"present: {f}")

    if fails:
        print("\nSTOP — files are missing or corrupt. Re-unzip into the REPO ROOT.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("2. CONTRACT — does it match the frozen baseline?")
    print("=" * 70)
    prov = json.load(open("artifacts/provenance.json"))
    check(prov.get("source") == "real-glorys", "provenance says real-glorys",
          f"got {prov.get('source')!r}")
    check(prov.get("n_depths") == config.N_DEPTHS, f"provenance depth count = {config.N_DEPTHS}",
          f"got {prov.get('n_depths')}")
    check(list(prov.get("depths", [])) == list(config.DEPTHS), "depth levels match config.DEPTHS")

    g = np.load("data/processed/grids.npz")
    sub = np.load("data/processed/subsurface.npz")
    check(g["temp"].shape[1:] == (config.N_LAT, config.N_LON, config.N_DEPTHS),
          "grids temp shape matches the grid", str(g["temp"].shape))
    check(sub["salinity"].shape == g["temp"].shape, "salinity shape matches temperature",
          str(sub["salinity"].shape))
    check((g["times"].astype("datetime64[D]") == sub["times"].astype("datetime64[D]")).all(),
          "subsurface times align with grids times")
    check("valid_mask" in g.files, "bathymetry mask present (24% of cells are < 1000 m deep)")
    nwind = len([f for f in os.listdir("data/raw/wind")]) if os.path.isdir("data/raw/wind") else 0
    check(nwind >= 48, "48 months of wind present", f"found {nwind}")

    print("\n" + "=" * 70)
    print("3. SCIENCE — does it behave like the North Indian Ocean?")
    print("=" * 70)
    theta, sal, vm = g["temp"], sub["salinity"], g["valid_mask"]

    i = int(np.argmin(np.abs(config.LAT - 18.0)))
    j = int(np.argmin(np.abs(config.LON - 88.0)))
    p = np.nanmean(sal[:, i, j, :], axis=0)
    check(p[-1] - p[0] > 0.5,
          "Bay of Bengal salinity rises with depth (fresh cap over salty water)",
          f"{p[0]:.2f} -> {p[-1]:.2f} psu  (synthetic gives ~0.0)")

    check(float(np.nanmin(sal)) < 20.0,
          "near-fresh river water present (Meghna/Ganges plume)",
          f"min {float(np.nanmin(sal)):.2f} psu")

    mean_prof = np.nanmean(theta.reshape(-1, config.N_DEPTHS), axis=0)
    check(mean_prof[0] > mean_prof[-1] + 15.0, "temperature cools strongly with depth",
          f"{mean_prof[0]:.1f} -> {mean_prof[-1]:.1f} degC")

    deep = int(vm[..., -1].sum())
    total = int((~g["land_mask"]).sum())
    check(0.6 < deep / total < 0.85, "bathymetry is realistic, not all-ocean",
          f"{deep} of {total} cells reach 1000 m ({100*deep/total:.0f}%)")

    # monsoon reversal — the single most distinctive feature of this basin
    import glob
    import xarray as xr
    def spd(pat):
        v = []
        for f in glob.glob(f"data/raw/wind/wind_*{pat}.nc"):
            with xr.open_dataset(f) as d:
                v.append(float(np.nanmean(d["wind_speed"].values)))
        return float(np.mean(v)) if v else float("nan")
    jul, jan = spd("07"), spd("01")
    check(jul > jan, "SW monsoon (Jul) windier than NE monsoon (Jan)",
          f"{jul:.2f} vs {jan:.2f} m/s")

    err = json.load(open("artifacts/argo_error_by_depth.json"))
    n = err.get("n_profiles", 0)
    check(n > 500, "real Argo error table present", f"{n} independent profiles")

    print("\n" + "=" * 70)
    if fails:
        print(f"FAILED {len(fails)} check(s):")
        for f in fails:
            print("   -", f)
        print("\nDo NOT treat results from this data as real until these pass.")
        sys.exit(1)
    print("ALL CHECKS PASSED — this is the real North Indian Ocean data.")
    print("You can now validate F4/F5/F6 against it instead of a synthetic stand-in.")
    print("=" * 70)


if __name__ == "__main__":
    main()
