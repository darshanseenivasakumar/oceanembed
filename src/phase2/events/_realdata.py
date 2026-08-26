"""Is this array a real ocean, or does it merely have the right shape?

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Imports the baseline config and F5 physics; modifies nothing.

WHY THIS EXISTS -- a provenance string lied, and it will lie again
[VERIFIED 2026-08-26] `data/processed/subsurface.npz` on this machine was stamped
`source = "real-glorys-subsurface"` while containing a synthetic stand-in: Bay of Bengal salinity
34.6029 psu at the surface against 34.5846 psu at 500 m (inverted -- the real basin has a fresh cap
over saltier water) and a domain minimum of 34.09 psu against a real 1.29 psu at the Meghna/Ganges
mouth. `src/phase2/data/extract_subsurface.py` writes that string unconditionally, whatever file it
read. The real bundle has since landed and the stamp is now accurate -- BY COINCIDENCE, because the
code that writes it is unchanged.

So: **nothing in F6 decides "is this real" by reading a provenance string.** This module answers
the question from physical structure, which cannot be faked by relabelling a file.

That is `START_HERE` rule 7 made executable -- *could this array have been produced without real
data behind it?* -- and it is the same class of check as Unit B's salinity test, which is what
caught the synthetic stand-in during F5 in the first place.

THE THRESHOLDS ARE A TRIPWIRE, NOT A MEASUREMENT
Each sits clearly between the value measured on the synthetic stand-in and the value measured on
the real bundle, so it discriminates without pretending to be a physical constant.

    check                        synthetic      real       threshold
    BoB fresh cap (psu)            -0.018       +4.78       >= 0.5
    domain minimum salinity        34.09         1.29        < 30
    thermocline below MLD (%)      11.6          87.8        >= 60
"""
from __future__ import annotations

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

from ..physics import layers

#: Northern Bay of Bengal -- the Ganges/Brahmaputra/Meghna plume region.
BOB_LAT = (15.0, 22.0)
BOB_LON = (85.0, 95.0)

MIN_FRESH_CAP_PSU = 0.5
MAX_DOMAIN_MIN_SALINITY_PSU = 30.0
MIN_THERMOCLINE_BELOW_MLD_FRAC = 0.60

_SURFACE_K = 0
_DEEP_K = config.DEPTHS.index(500) if 500 in config.DEPTHS else config.N_DEPTHS - 1


def _box(field: np.ndarray) -> np.ndarray:
    lat = np.asarray(config.LAT, dtype="float64")
    lon = np.asarray(config.LON, dtype="float64")
    i = (lat >= BOB_LAT[0]) & (lat <= BOB_LAT[1])
    j = (lon >= BOB_LON[0]) & (lon <= BOB_LON[1])
    return field[..., i, :, :][..., :, j, :]


def structure_report(salinity, theta) -> dict:
    """Three physical checks, each with the number that decided it.

    salinity, theta : (..., n_lat, n_lon, n_depths). A leading time axis is fine and is averaged
    over -- but note the Bay of Bengal barrier layer is SEASONAL, so a single-month input is a
    weaker test than the full record.

    Returns each check as {"passed", "value", "threshold"} plus an overall "passed".
    """
    s = np.asarray(salinity, dtype="float64")
    t = np.asarray(theta, dtype="float64")
    if s.shape[-1] != config.N_DEPTHS:
        raise ValueError(f"last axis must be {config.N_DEPTHS} depths, got {s.shape[-1]}")
    if s.shape != t.shape:
        raise ValueError(f"salinity {s.shape} and theta {t.shape} must match")

    box = _box(s)
    surf = float(np.nanmean(box[..., _SURFACE_K]))
    deep = float(np.nanmean(box[..., _DEEP_K]))
    fresh_cap = deep - surf

    domain_min = float(np.nanmin(s))

    mld = layers.mixed_layer_depth(s, t)
    th = layers.thermocline(t)["depth"]
    ok = np.isfinite(mld) & np.isfinite(th)
    frac_below = float((((th > mld) & ok).sum()) / ok.sum()) if ok.any() else float("nan")

    checks = {
        "bob_fresh_cap_psu": {
            "passed": bool(fresh_cap >= MIN_FRESH_CAP_PSU),
            "value": fresh_cap,
            "threshold": MIN_FRESH_CAP_PSU,
            "what": "northern Bay of Bengal is fresher at the surface than at 500 m",
        },
        "domain_min_salinity_psu": {
            "passed": bool(domain_min < MAX_DOMAIN_MIN_SALINITY_PSU),
            "value": domain_min,
            "threshold": MAX_DOMAIN_MIN_SALINITY_PSU,
            "what": "river-influenced water is present somewhere in the domain",
        },
        "thermocline_below_mld_frac": {
            "passed": bool(frac_below >= MIN_THERMOCLINE_BELOW_MLD_FRAC),
            "value": frac_below,
            "threshold": MIN_THERMOCLINE_BELOW_MLD_FRAC,
            "what": "a genuine mixed layer sits above the thermocline",
        },
    }
    return {"checks": checks, "passed": all(c["passed"] for c in checks.values())}


def looks_like_real_ocean(salinity, theta) -> bool:
    """True only if all three structural checks pass. Never reads a provenance string."""
    return bool(structure_report(salinity, theta)["passed"])


def describe(salinity, theta) -> str:
    """Human-readable report -- printed before any F6 result so a run says what it ran on."""
    r = structure_report(salinity, theta)
    lines = ["ocean-structure check (physical, NOT the provenance stamp):"]
    for name, c in r["checks"].items():
        lines.append(f"  [{'ok' if c['passed'] else 'FAIL'}] {name:28s} "
                     f"{c['value']:>9.3f}  (threshold {c['threshold']})  -- {c['what']}")
    lines.append(f"  => {'REAL OCEAN STRUCTURE' if r['passed'] else 'NO OCEAN STRUCTURE'}")
    return "\n".join(lines)
