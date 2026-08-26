"""One command Darshan runs to accept a feature Arjhun built.

    python scripts/phase2/accept.py

Darshan is short on tokens, so this exists to make testing cost one command and one screenful of
output instead of a conversation. It runs, in order:

  0. SAFETY   -- are we off main, is the tree clean, is main still where it should be
  1. SUITE    -- the FULL pytest suite, not just the new feature's tests
  2. DATA     -- scripts/phase2/verify_data_bundle.py (files, contract, science)
  3. FEATURE  -- a science check for whatever feature is on this branch

Step 3 is the one that matters. Steps 1 and 2 prove the code runs on the right data; only step 3
proves the feature is scientifically right. We have had 130 tests pass while the model returned
52 C from a 28 C input -- green tests are not evidence.

ARJHUN: every feature you build MUST add a check function here and register it in CHECKS, keyed by
branch name. Assert real numbers against real expectations. A check that only asserts the module
imported is worse than no check, because it manufactures false confidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PASS, FAIL, INFO = "  [ok]  ", "  [FAIL]", "  [--]  "
_failures: list[str] = []


def check(cond: bool, msg: str, detail: str = "") -> bool:
    print(f"{PASS if cond else FAIL} {msg}{('  ' + detail) if detail else ''}")
    if not cond:
        _failures.append(msg)
    return bool(cond)


def run(cmd: list[str], env_extra: dict | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src")
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def banner(n: int, title: str) -> None:
    print("\n" + "=" * 72)
    print(f"{n}. {title}")
    print("=" * 72)


# --------------------------------------------------------------------------------------
# FEATURE CHECKS -- one per branch. ARJHUN: add yours here.
# --------------------------------------------------------------------------------------

def check_f1_collocation() -> None:
    """F1: the engine must report MEASURED offsets and refuse land, not silently return zeros."""
    import datetime as dt
    from phase2.data.collocation import CollocationEngine

    eng = CollocationEngine(tolerance_days=10.0)

    # An open-ocean point that sits exactly on a grid cell and an exact grid date.
    ocean = eng.collocate(15.0, 65.0, dt.date(2022, 12, 15))
    check(ocean.quality == "HIGH", "open ocean 15N 65E accepted", f"quality={ocean.quality}")
    check(ocean.offsets["spatial_km"] < 1.0, "exact grid hit reports ~0 km offset",
          f"{ocean.offsets['spatial_km']:.2f} km")
    prof = (ocean.sources.get("glorys") or {}).get("temperature_profile") or []
    check(len(prof) == 15 and prof[0] > prof[-1] + 10,
          "profile has 15 levels and cools with depth",
          f"{prof[0]:.1f} -> {prof[-1]:.1f} C" if prof else "no profile")

    # Inland India must be rejected, not quietly answered.
    land = eng.collocate(15.0, 75.0, dt.date(2022, 12, 15))
    check(land.quality == "REJECT", "inland point 15N 75E rejected", f"quality={land.quality}")
    check(bool(land.flags), "rejection explains itself with flags", " ".join(land.flags[:2]))


def check_f2_ocean_cube() -> None:
    """F2a: the cube must mask by bathymetry, not invent values under the sea floor."""
    try:
        from phase2.cube import OceanCube  # noqa: F401
    except Exception as e:  # pragma: no cover - runs only once F2 lands
        check(False, "phase2.cube imports", repr(e))
        return
    check(False, "ARJHUN: replace this with a real F2a science check",
          "must prove a <20 m Persian Gulf cell returns None at 1000 m, not a number")


def check_f8_validation() -> None:
    """F8: the lab must report the REAL per-depth shape, incl. the thermocline being worst."""
    p = os.path.join(ROOT, "artifacts", "argo_error_by_depth.json")
    if not check(os.path.exists(p), "argo_error_by_depth.json present"):
        return
    err = json.load(open(p))
    check(err.get("n_profiles", 0) > 500, "built on the real independent Argo set",
          f"{err.get('n_profiles')} profiles")
    check(False, "ARJHUN: replace this with a real F8 science check",
          "must prove the page reports skill worst at ~100 m, positive at all 15 depths")


def check_f10_priority() -> None:
    """F10: ranking must exclude cells the sea floor rules out."""
    check(False, "ARJHUN: replace this with a real F10 science check",
          "must prove no cell shallower than the scored depth appears in the top ranks")


CHECKS = {
    "phase2-collocation": ("F1 collocation engine", check_f1_collocation),
    "phase2-ocean-cube": ("F2a OceanCube", check_f2_ocean_cube),
    "phase2-validation": ("F8 Validation Lab", check_f8_validation),
    "phase2-priority-v2": ("F10 Observation Priority v2", check_f10_priority),
}


# --------------------------------------------------------------------------------------

def main() -> None:
    os.chdir(ROOT)
    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    banner(0, "SAFETY")
    print(f"{INFO} branch: {branch}")
    check(branch not in ("main", "main1"),
          "not sitting on a protected branch", f"on {branch}")
    main_head = git("log", "-1", "--format=%h %s", "main")
    print(f"{INFO} main is at: {main_head}")
    check(main_head.startswith("4995444"),
          "main is untouched at the frozen Aug-30 demo", main_head[:9])
    dirty = git("status", "--short")
    check(not dirty, "working tree is clean",
          f"{len(dirty.splitlines())} uncommitted file(s)" if dirty else "")

    banner(1, "FULL TEST SUITE")
    code, out = run([sys.executable, "-m", "pytest", "-q"])
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or ["(no output)"]
    check(code == 0, "every test passes", tail[0].strip())
    if code != 0:
        print("\n".join(out.strip().splitlines()[-25:]))

    banner(2, "DATA BUNDLE")
    code, out = run([sys.executable, os.path.join("scripts", "phase2", "verify_data_bundle.py")])
    check(code == 0, "data is the real North Indian Ocean",
          "" if code == 0 else "see verify_data_bundle output below")
    if code != 0:
        print("\n".join(out.strip().splitlines()[-25:]))

    label, fn = CHECKS.get(branch, (None, None))
    banner(3, f"FEATURE SCIENCE — {label or 'no check registered for this branch'}")
    if fn is None:
        print(f"{INFO} No feature check registered for branch {branch!r}.")
        print(f"{INFO} If Arjhun just built a feature here, he owed you a check function in")
        print(f"{INFO} scripts/phase2/accept.py. Steps 0-2 passing does NOT mean the science is right.")
        _failures.append(f"no feature check registered for {branch}")
    else:
        try:
            fn()
        except Exception as e:
            check(False, f"{label} check raised", repr(e))

    print("\n" + "=" * 72)
    if _failures:
        print(f"NOT ACCEPTED — {len(_failures)} check(s) failed:")
        for f in _failures:
            print("   -", f)
        print("\nSend this output back to Arjhun. Do not merge.")
        sys.exit(1)
    print(f"ACCEPTED — {label} is safe, tested, on real data, and scientifically checked.")
    print("=" * 72)


if __name__ == "__main__":
    main()
