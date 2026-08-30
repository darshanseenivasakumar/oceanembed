"""Read the T_SEQ ablation log, pick the winner on independent Argo RMSE, retrain at full scale.

Ranked on held-out INDEPENDENT Argo RMSE, not on the training loss and not on the train/test gap.
The encoder bake-off already showed why the gap is the wrong criterion: it rewards underfitting,
and the blind control won on it while being 0.068 degC worse against real floats.

Sample count is matched to the MEASURED per-window cost so the final run finishes in hours rather
than days:

    T_SEQ= 1   1.8 min per 100k-sample epoch
    T_SEQ=11   8.4 min
    T_SEQ=31  24.9 min

so a longer window trains on fewer samples. That is a real confound and it is REPORTED rather than
hidden -- if T_SEQ=31 wins it wins despite seeing less data, and if it loses, part of the reason may
be that it saw less. Stated either way.

Run:  PYTHONPATH=src python scripts/phase2/pick_tseq_and_retrain.py --log <ablation log>
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# samples chosen so each run is roughly 1.5-4 h at 25 epochs on this CPU
SAMPLES_FOR = {1: 100000, 11: 60000, 31: 40000}


def parse(log_path: str) -> dict[int, float]:
    raw = open(log_path, "rb").read().decode("utf-8", "replace").replace("\r", "\n")
    out, cur = {}, None
    for line in raw.splitlines():
        m = re.search(r"T_SEQ=(\d+)\s*=====", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.search(r"OVERALL\s+rmse=([\d.]+)", line)
        if m and cur is not None:
            out[cur] = float(m.group(1))
            cur = None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    res = parse(a.log)
    if len(res) < 3:
        sys.exit(f"ablation incomplete: got {sorted(res)} of [1, 11, 31]. "
                 f"Refusing to pick a winner from a partial sweep.")

    print("T_SEQ ablation, independent Argo RMSE (lower is better):")
    for ts in sorted(res):
        print(f"  T_SEQ={ts:2d}  {res[ts]:.4f} degC   ({SAMPLES_FOR[ts]:,} samples in the final run)")
    win = min(res, key=res.get)
    second = sorted(res, key=res.get)[1]
    margin = res[second] - res[win]
    print(f"\nWINNER: T_SEQ={win} at {res[win]:.4f} degC, "
          f"ahead of T_SEQ={second} by {margin:.4f} degC")
    if margin < 0.02:
        print("  NOTE: that margin is small. Prefer the SHORTER window unless the gap is "
              "meaningful -- it trains faster and sees more samples for the same wall-clock.")
        if win > second:
            win = second
            print(f"  -> taking T_SEQ={win} on that basis, and saying so rather than claiming the "
                  f"longer window earned it.")

    n = SAMPLES_FOR[win]
    cmd = [sys.executable, "-m", "phase2.tscast_nio.train.train_stage1",
           "--data", "daily", "--t-seq", str(win), "--decoder", "simple", "--loss", "nll",
           "--epochs", "25", "--train-samples", str(n), "--test-samples", "12000",
           "--patience", "5"]
    print(f"\nFINAL RUN: {' '.join(cmd[2:])}\n" + "=" * 70, flush=True)
    if a.dry_run:
        return
    env = dict(os.environ, PYTHONPATH="src")
    sys.exit(subprocess.call(cmd, env=env))


if __name__ == "__main__":
    main()
