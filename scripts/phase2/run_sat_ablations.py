"""A10 -- matched feature ablations on the SATELLITE bundle, three seeds each.

WHY THREE SEEDS AND NOT ONE
Every effect this project has measured lives at +/-0.02 degC, and one of them has already flipped
sign under a single retrain: wind read -0.0149 (helps) pre-embargo and +0.0111 (hurts) after. A
one-seed ablation cannot tell an effect from a seed. So each leg runs three times and the reported
answer is "the sign held across three seeds" or "it did not" -- both are results.

WHAT IS MATCHED
Identical bundle, split, embargo, architecture, T_SEQ, sample counts, optimiser and schedule. The
ONLY thing that varies within a leg is the seed, and the only thing that varies between legs is
which channels are dropped. `rmse_climatology` is asserted equal across every run, which is what
proves they were scored on the same points rather than on different populations.

WHY ON THE SATELLITE BUNDLE
Because that is the deliverable. An ablation on the GLORYS-input bundle would answer "which
reanalysis fields matter", which is not the question the PS asks.

Resumable: a leg whose metrics file already exists is skipped, so an interrupt costs nothing.

Run:  PYTHONPATH=src python scripts/phase2/run_sat_ablations.py
      PYTHONPATH=src python scripts/phase2/run_sat_ablations.py --summarise-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base  # noqa: E402

BUNDLE = os.path.join("data", "processed", "daily_sat", "v001")
SEEDS = (42, 43, 44)

# name -> channels removed. "full" is the reference every other leg is measured against.
LEGS: dict[str, list[str]] = {
    "full": [],
    "noSSS": ["sss"],
    "noCUR": ["u", "v"],
    "noWIND": ["wu", "wv"],
}
OUT = base.art("sat_ablation.json")

BASE_ARGS = [
    "--data", "daily", "--daily-dir", BUNDLE,
    "--t-seq", "11", "--encoder", "cnn3d", "--decoder", "simple",
    "--loss", "nll", "--beta", "0.5", "--epochs", "25",
    "--train-samples", "60000", "--test-samples", "12000",
    "--lr", "1e-3", "--batch-size", "256", "--patience", "5",
    "--weight-decay", "1e-2", "--latent", "128", "--device", "cuda",
]


def tag_for(leg: str, seed: int) -> str:
    return f"abl_{leg}_s{seed}"


def metrics_path(leg: str, seed: int) -> str:
    return base.art(f"tscast_stage1_{tag_for(leg, seed)}_metrics.json")


def run_one(leg: str, seed: int) -> bool:
    path = metrics_path(leg, seed)
    if os.path.exists(path):
        print(f"[abl] {leg} s{seed}: already done, skipping", flush=True)
        return True
    cmd = [sys.executable, "-m", "phase2.tscast_nio.train.train_stage1",
           *BASE_ARGS, "--seed", str(seed), "--tag", tag_for(leg, seed)]
    if LEGS[leg]:
        cmd += ["--drop-channels", *LEGS[leg]]
    env = dict(os.environ, PYTHONPATH="src")
    t0 = time.time()
    print(f"[abl] {leg} s{seed}: training ({'all 7 channels' if not LEGS[leg] else 'dropping ' + ' '.join(LEGS[leg])})",
          flush=True)
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"[abl] {leg} s{seed}: FAILED rc={p.returncode}\n{p.stdout[-1500:]}", flush=True)
        return False
    with open(path, encoding="utf-8") as f:
        o = json.load(f)["metrics"]["overall"]
    print(f"[abl] {leg} s{seed}: rmse {o['rmse']:.4f}  skill {o['skill_rmse_ratio']:+.4f}  "
          f"({time.time() - t0:.0f}s)", flush=True)
    return True


def summarise() -> dict:
    import statistics as st

    rows: dict[str, list[dict]] = {}
    clim = set()
    for leg in LEGS:
        rows[leg] = []
        for seed in SEEDS:
            p = metrics_path(leg, seed)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            o = m["metrics"]["overall"]
            rows[leg].append(dict(seed=seed, rmse=o["rmse"], bias=o["bias"],
                                  correlation=o["correlation"],
                                  skill=o["skill_rmse_ratio"], n=o["n"],
                                  channels=len(m["channels"])))
            clim.add(round(o["rmse_climatology"], 10))

    def agg(vals):
        return (st.mean(vals), st.stdev(vals) if len(vals) > 1 else float("nan"))

    print("\n" + "=" * 78)
    print("A10 -- SATELLITE-BUNDLE FEATURE ABLATIONS, 3 SEEDS")
    print("=" * 78)
    if len(clim) == 1:
        print(f"  rmse_climatology identical across every run: {clim.pop():.10f}  "
              f"-- all legs scored on the same points")
    else:
        print(f"  !! rmse_climatology DIFFERS across runs: {sorted(clim)} -- legs are NOT matched, "
              f"the comparison below is invalid")
    print()
    print(f"  {'leg':8} {'ch':>3} {'n':>2}  {'RMSE mean':>10} {'sd':>7}   {'skill mean':>10} "
          f"{'delta vs full':>14}  {'sign holds?':>12}")

    base_r = [r["rmse"] for r in rows["full"]]
    bm, bs = agg(base_r) if base_r else (float("nan"), float("nan"))
    out = {"what": "feature ablation on the satellite bundle, 3 seeds per leg",
           "bundle": BUNDLE, "seeds": list(SEEDS), "legs": {}}

    for leg in LEGS:
        rs = [r["rmse"] for r in rows[leg]]
        if not rs:
            print(f"  {leg:8} {'-':>3} {0:>2}  (no runs)")
            continue
        m, sd = agg(rs)
        ch = rows[leg][0]["channels"]
        if leg == "full":
            print(f"  {leg:8} {ch:>3} {len(rs):>2}  {m:>10.4f} {sd:>7.4f}   "
                  f"{agg([r['skill'] for r in rows[leg]])[0]:>10.4f} {'(reference)':>14}")
            verdict = "reference"
        else:
            # per-seed deltas: the sign must agree across seeds for the effect to be real
            paired = [(r["rmse"] - next(b["rmse"] for b in rows["full"] if b["seed"] == r["seed"]))
                      for r in rows[leg]
                      if any(b["seed"] == r["seed"] for b in rows["full"])]
            same = len(paired) > 1 and (all(d > 0 for d in paired) or all(d < 0 for d in paired))
            verdict = "YES" if same else "NO -- flips"
            print(f"  {leg:8} {ch:>3} {len(rs):>2}  {m:>10.4f} {sd:>7.4f}   "
                  f"{agg([r['skill'] for r in rows[leg]])[0]:>10.4f} "
                  f"{m - bm:>+14.4f}  {verdict:>12}")
            out["legs"][leg] = dict(dropped=LEGS[leg], rmse_mean=m, rmse_sd=sd,
                                    delta_vs_full=m - bm, per_seed_delta=paired,
                                    sign_holds=bool(same), runs=rows[leg])
            continue
        out["legs"][leg] = dict(dropped=LEGS[leg], rmse_mean=m, rmse_sd=sd, runs=rows[leg])

    print()
    print("  READING THIS: a leg with a POSITIVE delta got WORSE without those channels, i.e. they")
    print("  helped. 'sign holds' means every seed agreed; 'flips' means the effect is not")
    print("  separable from seed noise at n=3 and must not be quoted as a finding.")
    out["seed_spread_full"] = bs
    print(f"\n  seed spread on the full leg (sd {bs:.4f}) is the noise floor: any |delta| below it")
    print("  is not a measurement.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n  wrote {OUT}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summarise-only", action="store_true")
    a = ap.parse_args()

    if not a.summarise_only:
        if not os.path.isdir(BUNDLE):
            raise SystemExit(f"{BUNDLE} absent -- build the satellite bundle first")
        total = len(LEGS) * len(SEEDS)
        done = 0
        for leg in LEGS:
            for seed in SEEDS:
                done += 1
                print(f"\n--- [{done}/{total}] {leg} seed {seed} ---", flush=True)
                if not run_one(leg, seed):
                    raise SystemExit(f"leg {leg} seed {seed} failed; refusing to summarise a "
                                     f"partial ablation")
    summarise()


if __name__ == "__main__":
    main()
