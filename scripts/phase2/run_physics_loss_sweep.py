"""Does penalising the vertical-gradient error help? Owner: Unit A (Arjhun).

    python scripts/phase2/run_physics_loss_sweep.py

DO NOT ASSUME A PHYSICS TERM HELPS. This project has already MEASURED one costing accuracy: the
eq. 5 density constraint read 0.8593 with the term on against 0.8548 with it off. So `--w-grad` is
swept from zero and judged on three seeds, exactly as `run_sat_ablations.py` judges a channel.

THE CONTROL ALREADY EXISTS AND IS NOT RE-RUN
`abl_full_s42/43/44` are the same 7-channel satellite configuration at the same three seeds:

    seed 42  0.9078      seed 43  0.9047      seed 44  0.9084
    mean 0.9070, SPREAD 0.0037  <- the noise floor any effect has to clear

Re-training them would burn 28 minutes to reproduce numbers already on disk, and would produce
slightly different ones, because training here is NOT deterministic: there is no
`torch.use_deterministic_algorithms`, no `cudnn.deterministic`, and these run on CUDA. That is also
why the "w=0 reproduces the frozen model to <0.001 degC" check the build spec asks for is
unreachable -- the seed spread alone is 4x that. The achievable and STRONGER version is a unit
test that the w=0 objective is bit-identical on a fixed batch, which is in
tests/phase2/test_physics_loss.py and needs no training at all.

WHY THESE WEIGHTS
[MEASURED on a real 2,048-sample batch with the shipped checkpoint] the gradient term is 4.85e-4
degC^2/m^2 against a beta-NLL objective of -0.1834. So the weight is not a free parameter:

    w = 10     term is  2.6% of the total loss   -- too weak to move anything
    w = 100    term is 20.9%                     -- meaningful
    w = 1000   term is 72.5%                     -- dominant

100 and 1000 bracket "meaningful" and "dominant". A sweep at w=1 would have tested nothing and
reported that the term does not matter.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base            # noqa: E402

BUNDLE = os.path.join("data", "processed", "daily_sat", "v001")
OUT = base.art("physics_loss_sweep.json")
SEEDS = (42, 43, 44)
WEIGHTS = (100.0, 1000.0)

#: The control legs, already on disk. Same bundle, same T_SEQ, same seeds, same everything but the
#: term under test -- which is what makes the comparison a paired one.
CONTROL_TAG = "abl_full_s{seed}"

#: Identical to run_sat_ablations.BASE_ARGS. Copied deliberately rather than imported: if that
#: script's constants ever change, this sweep must NOT silently start comparing against a control
#: trained under different hyperparameters.
BASE_ARGS = [
    "--data", "daily", "--daily-dir", BUNDLE,
    "--t-seq", "11", "--encoder", "cnn3d", "--decoder", "simple",
    "--loss", "nll", "--beta", "0.5", "--epochs", "25",
    "--train-samples", "60000", "--test-samples", "12000",
    "--lr", "1e-3", "--batch-size", "256", "--patience", "5",
    "--weight-decay", "1e-2", "--latent", "128", "--device", "cuda",
]


def tag_for(w: float, seed: int) -> str:
    return f"grad{str(w).replace('.', 'p')}_s{seed}"


def metrics_path(tag: str) -> str:
    return base.art(f"tscast_stage1_{tag}_metrics.json")


def read(tag: str):
    p = metrics_path(tag)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def run_one(w: float, seed: int) -> None:
    tag = tag_for(w, seed)
    if read(tag) is not None:
        print(f"  [skip] {tag} already has metrics")
        return
    cmd = [sys.executable, "-m", "phase2.tscast_nio.train.train_stage1", *BASE_ARGS,
           "--seed", str(seed), "--w-grad", str(w), "--tag", tag]
    print(f"  [run ] w={w} seed={seed} -> {tag}")
    t0 = time.time()
    env = dict(os.environ, PYTHONPATH="src")
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        raise SystemExit(f"{tag} failed with exit code {r.returncode}")
    print(f"  [done] {tag} in {time.time() - t0:.0f} s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=float, nargs="+", default=list(WEIGHTS))
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--summarise-only", action="store_true")
    a = ap.parse_args()

    control = {s: read(CONTROL_TAG.format(seed=s)) for s in a.seeds}
    missing = [s for s, m in control.items() if m is None]
    if missing:
        raise SystemExit(
            f"the control legs {[CONTROL_TAG.format(seed=s) for s in missing]} are not on this "
            f"machine. Run scripts/phase2/run_sat_ablations.py first -- an unpaired comparison "
            f"against a differently-configured baseline would measure the configuration.")

    if not a.summarise_only:
        for w in a.weights:
            for s in a.seeds:
                run_one(w, s)

    # ---- paired, per seed ------------------------------------------------------------------
    legs, rows = {}, []
    for w in a.weights:
        deltas, rmses = [], []
        for s in a.seeds:
            m = read(tag_for(w, s))
            if m is None:
                continue
            c = control[s]
            # THE SAME ARGO POINTS, OR THE COMPARISON IS MEANINGLESS. `rmse_climatology` is a
            # property of the scored population alone, so if two legs scored different profiles
            # it differs -- run_sat_ablations.py's own guard, kept.
            a_clim = m["metrics"]["overall"].get("rmse_climatology")
            c_clim = c["metrics"]["overall"].get("rmse_climatology")
            if a_clim is not None and c_clim is not None and abs(a_clim - c_clim) > 1e-6:
                raise SystemExit(
                    f"{tag_for(w, s)} scored a DIFFERENT Argo population from its control "
                    f"(rmse_climatology {a_clim:.6f} vs {c_clim:.6f}). The comparison would be "
                    f"between two different test sets, not between two objectives.")
            r_w = m["metrics"]["overall"]["rmse"]
            r_c = c["metrics"]["overall"]["rmse"]
            rmses.append(r_w)
            deltas.append(r_w - r_c)
            rows.append({"w_grad": w, "seed": s, "rmse": r_w, "control_rmse": r_c,
                         "delta": r_w - r_c, "epochs_run": m.get("epochs_run"),
                         "train_seconds": m.get("train_seconds"),
                         "bias": m["metrics"]["overall"]["bias"],
                         "skill_rmse_ratio": m["metrics"]["overall"]["skill_rmse_ratio"]})
        if deltas:
            legs[str(w)] = {
                "mean_rmse": float(np.mean(rmses)), "mean_delta": float(np.mean(deltas)),
                "deltas": [float(x) for x in deltas], "n_seeds": len(deltas),
                # A sign only counts if EVERY paired seed agrees. The eq. 5 lesson and the
                # stage-2 lesson are both that one lucky seed is not a result.
                # A sign only counts if EVERY paired seed agrees AND all three ran. Declaring on
                # two seeds is how the stage-2 temperature result got believed before seeds 43 and
                # 44 reversed it.
                "sign_holds": bool(len(deltas) >= 3
                                   and (all(d < 0 for d in deltas) or all(d > 0 for d in deltas))),
                "complete": len(deltas) >= 3,
            }

    c_rmse = [control[s]["metrics"]["overall"]["rmse"] for s in a.seeds]
    spread = float(np.max(c_rmse) - np.min(c_rmse))
    summary = {
        "what": "does a vertical-gradient loss term improve RMSE against independent Argo?",
        "control_tag": CONTROL_TAG, "control_rmse": [float(x) for x in c_rmse],
        "control_mean": float(np.mean(c_rmse)), "control_spread": spread,
        "spread_note": ("the seed spread of the CONTROL is the noise floor; a mean delta smaller "
                        "than this is not a result, whatever its sign"),
        "weights": a.weights, "seeds": a.seeds, "legs": legs, "runs": rows,
        "determinism": ("training here is NOT deterministic -- no use_deterministic_algorithms, "
                        "no cudnn.deterministic, and these run on CUDA. That is why the control "
                        "is three seeds and why a w=0 leg is not re-trained: bit-identity at w=0 "
                        "is asserted as a unit test on a fixed batch instead."),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)

    print("")
    print(f"control {CONTROL_TAG}: " + "  ".join(f"s{s}={r:.4f}" for s, r in zip(a.seeds, c_rmse)))
    print(f"   mean {np.mean(c_rmse):.4f}, SEED SPREAD {spread:.4f}  <- the noise floor")
    for w, leg in legs.items():
        verdict = ("BETTER" if leg["mean_delta"] < 0 else "WORSE")
        beats = abs(leg["mean_delta"]) > spread
        print(f"w_grad={w:>7}: mean {leg['mean_rmse']:.4f}  delta {leg['mean_delta']:+.4f}  "
              f"per-seed {['%+.4f' % d for d in leg['deltas']]}")
        state = ("INCOMPLETE -- %d of 3 seeds" % leg["n_seeds"] if not leg["complete"]
                 else (verdict if (leg["sign_holds"] and beats) else "NOT A RESULT"))
        print(f"           sign holds across seeds: {leg['sign_holds']}   "
              f"|delta| beats the seed spread: {beats}   -> {state}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
