"""Does the stage-2 satellite result hold across seeds? (Unit A / Arjhun.)

WHY THIS EXISTS
The first stage-2 satellite run (seed 42) scored T 0.8854 against stage 1's 0.9078 on the SAME 962
Argo profiles -- 0.0224 better. That is exactly the scale at which this project has already been
burned: the wind channel's own ablation effect flipped sign from -0.0149 to +0.0111 under a
retrain, which is why `run_sat_ablations.py` requires three seeds before a sign is believed. One
seed is an anecdote no matter how carefully it was measured.

Salinity and density are a different case again: they are NEW claims with no stage-1 counterpart,
so there is nothing to compare them against and the only question is how much they move.

Reads every number out of each run's own metrics JSON. Nothing is transcribed.

    PYTHONPATH=src python scripts/phase2/stage2_seed_check.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base  # noqa: E402

RUNS = {42: "tscast_stage2_sat_s2_metrics.json",
        43: "tscast_stage2_sat_s2_s43_metrics.json",
        44: "tscast_stage2_sat_s2_s44_metrics.json"}


def load(name: str) -> dict | None:
    p = base.art(name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    runs = {s: load(n) for s, n in RUNS.items()}
    missing = [s for s, m in runs.items() if m is None]
    if missing:
        print(f"missing metrics for seed(s) {missing} -- run train_stage2 with --seed first")
        return 1

    # Every leg must be the same comparison, or the spread is measuring the setup, not the seed.
    print("MATCHED?  (a spread across legs that differ in these is not a seed effect)")
    keys = ("input_source", "daily_dir", "T_SEQ", "train_period", "test_period",
            "argo_profiles", "argo_table", "w_density", "beta_nll")
    ok = True
    for k in keys:
        vals = {s: json.dumps(m.get(k)) for s, m in runs.items()}
        same = len(set(vals.values())) == 1
        ok &= same
        print(f"  {'ok  ' if same else 'DIFF'}  {k:16s} {vals[42][:58]}")
    n = {s: m["metrics"]["overall"].get("n") for s, m in runs.items()}
    same_n = len(set(n.values())) == 1
    ok &= same_n
    print(f"  {'ok  ' if same_n else 'DIFF'}  {'n (depth cmp)':16s} {n}")

    base1 = {s: (m.get("compare_against") or {}).get("stage1_rmse") for s, m in runs.items()}
    same_b = len({round(v, 10) for v in base1.values() if v is not None}) == 1
    ok &= same_b
    print(f"  {'ok  ' if same_b else 'DIFF'}  {'stage-1 baseline':16s} {base1[42]}")

    print("\nTEMPERATURE -- the only quantity with a stage-1 number to beat")
    t = {s: m["metrics"]["overall"]["rmse"] for s, m in runs.items()}
    b1 = base1[42]
    for s in sorted(t):
        d = b1 - t[s]
        print(f"  seed {s}: stage2 {t[s]:.4f}   stage1 {b1:.4f}   stage2 better by {d:+.4f}")
    deltas = [b1 - v for v in t.values()]
    mean_d, spread = st.mean(deltas), max(deltas) - min(deltas)
    signs = {d > 0 for d in deltas}
    held = len(signs) == 1
    print(f"\n  mean improvement {mean_d:+.4f} degC, spread {spread:.4f}, "
          f"sd {st.stdev(list(t.values())):.4f}")
    print(f"  sign holds across all 3 seeds: {'YES' if held else 'NO'}"
          + ("" if held else "  -- the effect does not survive a reseed"))
    if held and mean_d > 0:
        print("  -> stage 2 is better on temperature in every seed. Still a 3-seed result on one\n"
              "     architecture, not a law; quote it with the spread, never the best leg.")
    elif held:
        print("  -> stage 2 is WORSE on temperature in every seed.")

    print("\nSALINITY and DENSITY -- new claims, no stage-1 counterpart. Spread only.")
    for label, get in (("salinity RMSE (psu)",
                        lambda m: _overall_s(m)),
                       ("density RMSE (kg/m3)",
                        lambda m: (m.get("density") or {}).get("rmse_kg_m3")),
                       ("density ratio", lambda m: (m.get("density") or {}).get("calibration_ratio"))):
        v = {s: get(m) for s, m in runs.items()}
        if any(x is None for x in v.values()):
            print(f"  {label:22s} NOT SCORED in at least one leg: {v}")
            continue
        vals = list(v.values())
        print(f"  {label:22s} " + "  ".join(f"s{s}={v[s]:.4f}" for s in sorted(v))
              + f"   mean {st.mean(vals):.4f}  spread {max(vals)-min(vals):.4f}")

    print(f"\n{'MATCHED across all legs' if ok else 'NOT MATCHED -- fix before quoting anything'}")
    return 0 if ok else 1


def _overall_s(m: dict):
    """Sample-weighted salinity RMSE across depths -- the per-depth table is what gets written."""
    ms = m.get("metrics_salinity")
    if not ms:
        return None
    num = sum(r * r * n for r, n in zip(ms["rmse"], ms["n"]) if r is not None)
    den = sum(n for r, n in zip(ms["rmse"], ms["n"]) if r is not None)
    return (num / den) ** 0.5 if den else None


if __name__ == "__main__":
    sys.exit(main())
