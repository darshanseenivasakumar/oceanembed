"""ONE COMMAND to accept whatever Phase-2 feature is on the current branch.

    python scripts/phase2/accept.py

OWNER: Unit A (Arjhun), created 2026-08-26. Darshan is short on tokens and should not have to
work out how to test a feature -- this is the whole interface.

It runs, in order, stopping at the first hard failure:

    0. SAFETY    -- you are not on main; main is unmodified; the working tree is reported
    1. SUITE     -- the FULL pytest run, not just the feature's own tests
    2. DATA      -- scripts/phase2/verify_data_bundle.py (FILES / CONTRACT / SCIENCE)
    3. FEATURE   -- a science check for each feature detected on this branch

A feature check asserts REAL SCIENCE, not that a module imported. Importing proves nothing --
we once had 130 tests green while the model returned 52 degC from a 28 degC input.

TO ADD A FEATURE: write check_fN(), returning (ok: bool, lines: list[str]), and register it in
CHECKS with the import path that indicates the feature is present on this branch.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PY = sys.executable
OK, BAD, SKIP = "  [ok]  ", "  [FAIL]", "  [skip]"


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _git(*args: str) -> str:
    code, out = _run(["git", *args])
    return out.strip() if code == 0 else ""


# =================================================================================================
# 0. SAFETY
# =================================================================================================
def safety() -> bool:
    print("=" * 74)
    print("0. SAFETY")
    print("=" * 74)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    ok = True

    if branch in ("main", "main1"):
        print(f"{BAD} on branch '{branch}' -- Phase-2 work must never sit on main")
        ok = False
    else:
        print(f"{OK} on feature branch '{branch}'")

    # main must be byte-identical to its remote: proves nothing here has touched it.
    local, remote = _git("rev-parse", "main"), _git("rev-parse", "origin/main")
    if local and remote and local == remote:
        print(f"{OK} main unmodified ({local[:8]} == origin/main)")
    elif local and remote:
        print(f"{BAD} main has diverged from origin/main ({local[:8]} vs {remote[:8]})")
        ok = False
    else:
        print(f"{SKIP} could not compare main to origin/main")

    dirty = _git("status", "--porcelain")
    tracked = [l for l in dirty.splitlines() if not l.startswith("??")]
    print(f"{OK} working tree clean" if not tracked
          else f"{SKIP} {len(tracked)} uncommitted tracked file(s) -- testing the WORKING TREE, "
               f"not the commit")
    return ok


# =================================================================================================
# 1 + 2. SUITE AND DATA
# =================================================================================================
def full_suite() -> bool:
    print("\n" + "=" * 74)
    print("1. FULL TEST SUITE")
    print("=" * 74)
    env_py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    py = env_py if os.path.exists(env_py) else PY
    code, out = _run([py, "-m", "pytest", "-q"])
    tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
    for l in tail:
        print(f"  {l}")
    print(f"{OK} full suite passed" if code == 0 else f"{BAD} suite failed (exit {code})")
    if code != 0:
        print("\n".join(out.strip().splitlines()[-25:]))
    return code == 0


def data_bundle() -> bool:
    print("\n" + "=" * 74)
    print("2. DATA BUNDLE")
    print("=" * 74)
    script = os.path.join(ROOT, "scripts", "phase2", "verify_data_bundle.py")
    if not os.path.exists(script):
        print(f"{SKIP} verify_data_bundle.py absent on this branch")
        return True
    env_py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    py = env_py if os.path.exists(env_py) else PY
    code, out = _run([py, script])
    fails = [l for l in out.splitlines() if "[FAIL]" in l]
    for l in fails:
        print(l)
    print(f"{OK} FILES / CONTRACT / SCIENCE all pass" if code == 0 and not fails
          else f"{BAD} data verification failed -- do NOT build on this data")
    return code == 0 and not fails


# =================================================================================================
# 3. FEATURE CHECKS -- real science, per feature
# =================================================================================================
def check_f5() -> tuple[bool, list[str]]:
    """Physics: a real mixed layer must exist and the thermocline must sit BELOW it."""
    import numpy as np
    from oceanembed import config
    from phase2.physics import layers

    g = np.load(os.path.join(config.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    s = np.load(os.path.join(config.DATA_PROCESSED, "subsurface.npz"), allow_pickle=True)
    theta = np.asarray(g["temp"], dtype="float64")
    sal = np.asarray(s["salinity"], dtype="float64")

    mld = layers.mixed_layer_depth(sal, theta)
    th = layers.thermocline(theta)["depth"]
    ok_cells = np.isfinite(mld) & np.isfinite(th)
    frac = float(((th > mld) & ok_cells).sum() / ok_cells.sum())
    good = frac >= 0.60
    return good, [
        f"thermocline below MLD in {100*frac:.1f}% of {ok_cells.sum()} cell-dates "
        f"(need >=60%; a synthetic stand-in gives ~12%)",
        f"median MLD {np.nanmedian(mld[ok_cells]):.0f} m, "
        f"median thermocline {np.nanmedian(th[ok_cells]):.0f} m",
    ]


def check_f6() -> tuple[bool, list[str]]:
    """Events: the Somali anticyclone (Great Whirl) must be far larger in Aug than in Jan."""
    import numpy as np
    from oceanembed import config
    from phase2.events import eddy

    g = np.load(os.path.join(config.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    times = np.asarray(g["times"]).astype("datetime64[D]")
    land = np.asarray(g["land_mask"], dtype=bool)
    months = np.array([int(str(t)[5:7]) for t in times])

    def biggest(month: int) -> float:
        radii = []
        for k in np.nonzero(months == month)[0]:
            u = np.where(land, np.nan, np.asarray(g["u"], dtype="float64")[k])
            v = np.where(land, np.nan, np.asarray(g["v"], dtype="float64")[k])
            got = [e["equivalent_radius_km"] for e in eddy.detect_eddies(u, v)
                   if e["polarity"] == "anticyclonic"
                   and 4 <= e["centroid_lat"] <= 12 and 48 <= e["centroid_lon"] <= 58]
            if got:
                radii.append(max(got))
        return float(np.mean(radii)) if radii else 0.0

    aug, jan = biggest(8), biggest(1)
    good = aug > 1.8 * jan and aug > 150.0
    return good, [
        f"largest Somali anticyclone: Aug {aug:.0f} km vs Jan {jan:.0f} km "
        f"(need Aug > 1.8x Jan and > 150 km)",
        "this is the Great Whirl's seasonal cycle -- an expectation external to our code",
    ]


def check_f8() -> tuple[bool, list[str]]:
    """Validation Lab: the thermocline error must be inherited, the mixed layer ours."""
    from phase2.validation import lab

    d = lab.per_depth()
    iv = lab.inherited_vs_earned()
    gap = lab.reanalysis_gap()
    ba = lab.baseline_availability()

    checks = [
        (d["all_depths_positive_skill"], "skill positive at all 15 depths"),
        (d["worst_skill_is_also_best_absolute"],
         f"the {d['worst_skill_depth_m']:.0f} m paradox is surfaced: worst skill "
         f"({d['worst_skill']:+.3f}) is also best absolute RMSE ({d['best_absolute_rmse']:.3f} C)"),
        (gap["worst_depth_m"] == 100.0,
         f"reanalysis' own worst depth is {gap['worst_depth_m']:.0f} m "
         f"({gap['worst_mae']:.3f} C MAE) over {gap['n_comparisons']} comparisons"),
        (all(z in iv["at_ceiling_depths"] for z in (100.0, 125.0, 150.0)),
         "thermocline (100-150 m) is AT THE CEILING of the training truth -- inherited error"),
        (all(z in iv["model_limited_depths"] for z in (20.0, 30.0, 50.0)),
         "mixed layer (20-50 m) is MODEL-LIMITED -- genuinely ours to fix"),
        (not ba["lightgbm"]["available"],
         "LightGBM baseline correctly REFUSED (provenance unverifiable), not silently omitted"),
    ]
    lines = [("     " + ("ok   " if c else "FAIL ") + msg) for c, msg in checks]
    return all(c for c, _ in checks), lines


CHECKS = [
    ("F5 physics", "phase2.physics.layers", check_f5),
    ("F6 events", "phase2.events.eddy", check_f6),
    ("F8 validation", "phase2.validation.lab", check_f8),
]


def features() -> bool:
    print("\n" + "=" * 74)
    print("3. FEATURE SCIENCE CHECKS")
    print("=" * 74)
    ran, all_ok = 0, True
    for name, module, fn in CHECKS:
        try:
            importlib.import_module(module)
        except ImportError:
            print(f"{SKIP} {name} -- not on this branch")
            continue
        ran += 1
        try:
            ok, lines = fn()
        except Exception as e:  # a check that cannot run is a failure, not a skip
            print(f"{BAD} {name} -- check raised {type(e).__name__}: {e}")
            all_ok = False
            continue
        print(f"{OK if ok else BAD} {name}")
        for l in lines:
            print(f"        {l}")
        all_ok = all_ok and ok
    if ran == 0:
        print(f"{SKIP} no known Phase-2 feature detected on this branch")
    return all_ok


def main() -> None:
    results = [("safety", safety()), ("suite", full_suite()),
               ("data", data_bundle()), ("features", features())]
    print("\n" + "=" * 74)
    failed = [n for n, ok in results if not ok]
    if failed:
        print(f"REJECTED -- failed: {', '.join(failed)}")
        print("=" * 74)
        sys.exit(1)
    print("ACCEPTED -- safety, full suite, data bundle and feature science all pass.")
    print("=" * 74)


if __name__ == "__main__":
    main()
