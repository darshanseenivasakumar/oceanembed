"""ONE COMMAND to accept whatever Phase-2 feature is on the current branch.

    python scripts/phase2/accept.py

OWNER: Unit A (Arjhun), created 2026-08-26. Darshan is short on tokens and should not have to
work out how to test a feature -- this is the whole interface.

It runs, in order, stopping at the first hard failure:

    0. SAFETY    -- nothing here has added commits to main; the working tree is reported
    1. SUITE     -- the FULL pytest run, not just the feature's own tests
    2. DATA      -- scripts/phase2/verify_data_bundle.py (FILES / CONTRACT / SCIENCE)
    2b. DERIVED  -- regenerate any measurement artifact that is missing, rather than failing
    3. FEATURE   -- a science check for each feature detected on this branch

A feature check asserts REAL SCIENCE, not that a module imported. Importing proves nothing --
we once had 130 tests green while the model returned 52 degC from a 28 degC input.

TO ADD A FEATURE: write check_fN(), returning (ok: bool, lines: list[str]), and register it in
CHECKS with the import path that indicates the feature is present on this branch.

WHY IMPORT PATH AND NOT BRANCH NAME
Unit B wrote an independent version of this file keyed by BRANCH NAME. Merged, that would run
exactly ONE check on a branch carrying five features. Detecting by import path runs every feature
actually present, which is what a branch that accumulates work needs. His F1 check is ported in
below; the rest of his file is superseded by this one. One script, not two -- D-014.
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

    # What must be true: nothing HERE has added commits to main. That is not the same as
    # "main equals origin/main" -- Unit B legitimately pushes to main (v1.0.1 did), which leaves
    # a local ref behind through no fault of ours. An earlier version of this check called that
    # DIVERGED and failed the run. A safety check that cries wolf gets ignored, and then it is
    # not there for the real thing.
    local, remote = _git("rev-parse", "main"), _git("rev-parse", "origin/main")
    if not (local and remote):
        print(f"{SKIP} could not compare main to origin/main")
    elif local == remote:
        print(f"{OK} main unmodified ({local[:8]} == origin/main)")
    elif _run(["git", "merge-base", "--is-ancestor", "main", "origin/main"])[0] == 0:
        # local main is an ancestor: behind, with no local commits of its own. Safe.
        print(f"{OK} main has no local commits ({local[:8]} is an ancestor of origin/main "
              f"{remote[:8]} -- behind, not diverged; `git fetch` to catch up)")
    else:
        print(f"{BAD} main has LOCAL COMMITS not in origin/main ({local[:8]} vs {remote[:8]}) "
              f"-- something wrote to main")
        ok = False

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
# 2b. DERIVED ARTIFACTS -- regenerate rather than fail
# =================================================================================================
#: artifact -> the script that produces it. These are DERIVED (measurements, not raw data), so
#: regenerating is always safe and always cheap relative to a failed acceptance run.
DERIVED = {
    "glorys_vs_argo.json": "glorys_vs_argo.py",
    "mc_calibration.json": "measure_mc_calibration.py",
}


def derived_artifacts() -> bool:
    """Make sure the measurements F8 reads exist, generating any that do not.

    Unit B hit this: `artifacts/` is gitignored, so switching branches removed a file he had
    generated and F8 failed with MissingArtifactError before he regenerated it by hand. Whoever
    runs this should not have to know which script produces which artifact.
    """
    print("\n" + "=" * 74)
    print("2b. DERIVED ARTIFACTS")
    print("=" * 74)
    from oceanembed import config

    env_py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    py = env_py if os.path.exists(env_py) else PY
    ok = True
    for artifact, script in DERIVED.items():
        path = os.path.join(config.ARTIFACTS, artifact)
        if os.path.exists(path):
            print(f"{OK} {artifact} present")
            continue
        gen = os.path.join(ROOT, "scripts", "phase2", script)
        if not os.path.exists(gen):
            print(f"{SKIP} {artifact} absent and {script} is not on this branch")
            continue
        print(f"       {artifact} absent -- regenerating via {script} ...")
        code, out = _run([py, gen])
        if code == 0 and os.path.exists(path):
            print(f"{OK} {artifact} regenerated")
        else:
            print(f"{BAD} could not regenerate {artifact} (exit {code})")
            print("\n".join(out.strip().splitlines()[-8:]))
            ok = False
    return ok


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
        (not ba["lightgbm"]["available"] and "never scored" in ba["lightgbm"]["why"],
         "LightGBM baseline REFUSED for the right reason -- no Argo score exists for it "
         "(the gate is the score, NOT a row count, which matched on Unit B's machine)"),
    ]
    lines = [("     " + ("ok   " if c else "FAIL ") + msg) for c, msg in checks]
    return all(c for c, _ in checks), lines


def check_f1() -> tuple[bool, list[str]]:
    """F1: the engine must report MEASURED offsets and refuse land, not silently return zeros.

    Ported from Unit B's own accept.py during the merge -- his F1 check, kept verbatim in intent.
    """
    import datetime as dt
    from phase2.data.collocation import CollocationEngine

    eng = CollocationEngine(tolerance_days=10.0)
    ocean = eng.collocate(15.0, 65.0, dt.date(2022, 12, 15))
    prof = (ocean.sources.get("glorys") or {}).get("temperature_profile") or []
    land = eng.collocate(15.0, 75.0, dt.date(2022, 12, 15))

    checks = [
        (ocean.quality == "HIGH", f"open ocean 15N 65E accepted (quality={ocean.quality})"),
        (ocean.offsets["spatial_km"] < 1.0,
         f"exact grid hit reports ~0 km offset ({ocean.offsets['spatial_km']:.2f} km)"),
        (len(prof) == 15 and prof[0] > prof[-1] + 10,
         f"profile has 15 levels and cools with depth "
         f"({prof[0]:.1f} -> {prof[-1]:.1f} C)" if prof else "no profile returned"),
        (land.quality == "REJECT", f"inland 15N 75E rejected (quality={land.quality})"),
        (bool(land.flags), f"rejection explains itself: {' '.join(land.flags[:2])}"),
    ]
    lines = [("     " + ("ok   " if c else "FAIL ") + m) for c, m in checks]
    return all(c for c, _ in checks), lines


def check_f2a() -> tuple[bool, list[str]]:
    """OceanCube: the sea floor must be a refusal, and a real profile must look like an ocean."""
    import numpy as np
    from oceanembed import config
    from phase2.cube import BelowSeafloorError, OceanCube

    cube = OceanCube.reconstruct("2022-07-15", source="satellite", with_uncertainty=False)

    # 1. the Persian Gulf cell Phase 1 painted 1000 m temperatures into
    floor = cube.seafloor_depth_m(26.0, 52.5)
    refused = False
    try:
        cube.value_at(26.0, 52.5, 1000)
    except BelowSeafloorError:
        refused = True

    # 2. a real deep profile must actually behave like the ocean
    p = cube.profile(15.0, 88.0)
    v = p["values"]
    monotonic = bool(np.all(np.diff(v) < 2.0))
    surface_ok = bool(20.0 < v[0] < 33.0)
    deep_ok = bool(v[-1] < v[0] - 10.0)

    cov = cube.coverage()
    dis = cube.coastline_disagreement()

    checks = [
        (floor == 30.0, f"Persian Gulf 26.00N 52.50E sea floor read as {floor:.0f} m (expect 30)"),
        (refused, "1000 m there is REFUSED, not returned as NaN"),
        (surface_ok and deep_ok and monotonic,
         f"BoB 15N 88E profile {v[0]:.1f} -> {v[-1]:.1f} degC, no upward jumps"),
        (abs(cov["coverage_fraction"][-1] - 0.758) < 0.015,
         f"1000 m coverage {100*cov['coverage_fraction'][-1]:.1f}% (expect ~75.8%)"),
        (dis["n_cells"] == 179,
         f"coastline disagreement {dis['n_cells']} cells (expect 179; Unit B's F1 sees the same)"),
    ]
    lines = [("     " + ("ok   " if c else "FAIL ") + m) for c, m in checks]
    return all(c for c, _ in checks), lines


CHECKS = [
    ("F1 collocation", "phase2.data.collocation", check_f1),
    ("F2a OceanCube", "phase2.cube.ocean_cube", check_f2a),
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
               ("data", data_bundle()), ("derived artifacts", derived_artifacts()),
               ("features", features())]
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
