"""Static stability as a GUARANTEE: measure the violations, then remove them by construction.

    PYTHONPATH=src python scripts/phase2/run_stability_projection.py
    PYTHONPATH=src python scripts/phase2/run_stability_projection.py --compare-tag s2_stab

WHAT IT MEASURES
----------------
1. How many predicted profiles are statically UNSTABLE -- density decreasing downward. This number
   is not reported anywhere in this specialisation, because a soft penalty cannot promise it.
2. What the isotonic projection does to it: zero, by construction, and re-verified by recomputing
   density from the projected temperature rather than trusting the algebra.
3. What the guarantee COSTS in RMSE against independent Argo. If it costs something, that is
   reported; "we accept +0.00x degC for a guarantee" is a defensible trade and a hidden cost is not.

Optionally 4: the same three numbers for a checkpoint trained WITH the soft penalty
(`--compare-tag`), which is what turns "projection eliminates violations" into the full claim
"soft penalties reduce them, projection eliminates them", measured on one test set.

STAGE 2 ONLY, AND THE REASON IS THE POINT
------------------------------------------
Density needs salinity at depth. The shipped deliverable is stage 1, which predicts temperature
alone, so static stability is not a well-posed question about it and this script refuses to run
there. The tempting substitute -- enforce monotone cooling with depth -- would delete the Bay of
Bengal's barrier-layer temperature inversions, which are real and which this project already
measures. See `phase2.physics.stability` for the full argument.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                          # noqa: E402
from phase2.physics import stability as ST                     # noqa: E402
from phase2.reliability import harness as H                    # noqa: E402
from phase2.tscast_nio import config as c2                     # noqa: E402

TS_TABLE = "argo_daily_period_ts.parquet"


def _score(ctx, temperature) -> dict:
    o = ctx.score(temperature)["overall"]
    return {k: float(o[k]) for k in ("rmse", "bias", "correlation", "skill_rmse_ratio")} | {
        "n": int(o["n"])}


def _leg(ctx, label: str) -> dict:
    """Predict, count violations, project, re-count, and score both ways."""
    pred = ctx.predict()
    T, S = pred["temperature"].astype("float64"), pred["salinity"].astype("float64")
    print(f"\n[{label}] {T.shape[0]} profiles, {c2.N_DEPTHS} levels")

    t0 = time.time()
    proj = ST.project_many(T, S)
    secs = time.time() - t0

    before, after = proj["violations_before"], proj["violations_after"]
    print(f"  violations BEFORE : {before['n_violating']:>6} of {before['n_pairs']} adjacent pairs "
          f"({before['fraction']*100:.3f}%) in {before['n_profiles_with_violation']} profiles")
    print(f"  violations AFTER  : {after['n_violating']:>6} of {after['n_pairs']} pairs "
          f"({after['fraction']*100:.3f}%)")
    print(f"  worst gradient    : {before['worst_drho_dz']:.3e} -> {after['worst_drho_dz']:.3e} "
          f"kg m-3 m-1")
    print(f"  projection changed {proj['n_levels_changed']} levels in "
          f"{proj['n_profiles_changed']} profiles, {secs:.2f}s "
          f"({secs/max(1,T.shape[0])*1000:.2f} ms/profile)")
    if proj["refusals"]:
        print(f"  refusals          : {len(proj['refusals'])} (first: {proj['refusals'][0]})")

    m_before, m_after = _score(ctx, T), _score(ctx, proj["temperature"])
    d = m_after["rmse"] - m_before["rmse"]
    print(f"  RMSE vs Argo      : {m_before['rmse']:.4f} -> {m_after['rmse']:.4f} "
          f"({d:+.4f} degC)  bias {m_before['bias']:+.4f} -> {m_after['bias']:+.4f}")

    return {
        "label": label,
        "checkpoint": os.path.basename(ctx.ckpt_path),
        "n_profiles": int(T.shape[0]),
        "violations_before": before,
        "violations_after": after,
        "verified_zero": bool(proj["verified"] and after["n_violating"] == 0),
        "n_levels_changed": proj["n_levels_changed"],
        "n_profiles_changed": proj["n_profiles_changed"],
        "seconds": round(secs, 3),
        "ms_per_profile": round(secs / max(1, T.shape[0]) * 1000, 3),
        "refusals": proj["refusals"][:20],
        "n_refusals": len(proj["refusals"]),
        "metrics_before": m_before,
        "metrics_after": m_after,
        "rmse_cost_degC": float(d),
    }


def _basin(ctx, date_idx: int | None = None) -> dict:
    """The same count over every ocean cell on one date -- profiles a float never visited."""
    land = np.asarray(ctx.bundle["land_mask"], bool)
    t_idx = int(ctx.argo_idx[:, 0].max()) if date_idx is None else int(date_idx)
    ii, jj = np.nonzero(~land)
    index = np.stack([np.full(ii.size, t_idx), ii, jj], axis=1)
    print(f"\n[basin] date index {t_idx} ({str(ctx.bundle['times'][t_idx])[:10]}), "
          f"{ii.size} ocean cells")

    pred = ctx.predict(index=index)
    T, S = pred["temperature"].astype("float64"), pred["salinity"].astype("float64")
    valid = np.isfinite(T) & np.isfinite(S)
    t0 = time.time()
    proj = ST.project_many(T, S, mask=valid)
    secs = time.time() - t0
    b, a = proj["violations_before"], proj["violations_after"]
    print(f"  violations BEFORE : {b['n_violating']} of {b['n_pairs']} pairs "
          f"({b['fraction']*100:.3f}%) in {b['n_profiles_with_violation']} of {ii.size} cells")
    print(f"  violations AFTER  : {a['n_violating']}   [{secs:.1f}s for the whole basin]")
    return {
        "date": str(ctx.bundle["times"][t_idx])[:10],
        "n_ocean_cells": int(ii.size),
        "violations_before": b,
        "violations_after": a,
        "verified_zero": bool(proj["verified"] and a["n_violating"] == 0),
        "n_profiles_changed": proj["n_profiles_changed"],
        "seconds": round(secs, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default=base.art("tscast_stage2_sat_s2.pt"))
    ap.add_argument("--compare-tag", default=None,
                    help="a second stage-2 checkpoint trained WITH the soft stability penalty")
    ap.add_argument("--daily-dir", default=H.SAT_BUNDLE)
    ap.add_argument("--skip-basin", action="store_true")
    ap.add_argument("--out", default=base.art("stability_projection.json"))
    a = ap.parse_args()

    ctx = H.load(a.checkpoint, daily_dir=a.daily_dir, argo_table=TS_TABLE)
    if ctx.stage != 2:
        raise SystemExit(
            "static stability needs salinity at depth, so this experiment is stage 2 only. Stage 1 "
            "predicts temperature alone and the question is not well posed there -- see "
            "phase2.physics.stability on why a monotone-temperature substitute would be wrong in "
            "the Bay of Bengal.")

    ctrl = ctx.control_rmse()
    print(f"control: rmse {ctrl['rmse']:.10f}  recorded {ctrl['recorded_rmse']}  "
          f"agrees={ctrl['agrees']}  profiles={ctrl['n_profiles']}")
    if ctrl["agrees"] is not True:
        raise SystemExit(
            "REFUSING TO WRITE: the control does not reproduce the checkpoint's recorded RMSE. "
            "Every violation count below it would be a property of the harness, not the model.")

    out = {
        "experiment": "hard static-stability projection (isotonic on density) vs soft penalty",
        "control": ctrl,
        "eos": "EOS-80 one-atmosphere potential density (phase2.physics.seawater)",
        "projection": "isotonic regression (PAVA) on density, inverted back to T at fixed S",
        "legs": [_leg(ctx, "baseline stage-2 (eq.5 density NLL, no stability term)")],
    }

    if a.compare_tag:
        ctx2 = H.load(a.compare_tag, daily_dir=a.daily_dir, argo_table=TS_TABLE)
        c2ctrl = ctx2.control_rmse()
        print(f"\ncompare control: rmse {c2ctrl['rmse']:.6f} agrees={c2ctrl['agrees']}")
        out["compare_control"] = c2ctrl
        out["legs"].append(_leg(ctx2, f"soft stability penalty ({a.compare_tag})"))

    if not a.skip_basin:
        out["basin"] = _basin(ctx)

    base_leg = out["legs"][0]
    out["headline"] = {
        "violating_pairs_before": base_leg["violations_before"]["n_violating"],
        "violating_pairs_after": base_leg["violations_after"]["n_violating"],
        "profiles_with_violation_before":
            base_leg["violations_before"]["n_profiles_with_violation"],
        "guarantee_verified": base_leg["verified_zero"],
        "rmse_cost_degC": base_leg["rmse_cost_degC"],
        "claim": ("Soft constraints reduce violations; projection eliminates them. The zero is "
                  "re-verified by recomputing density from the projected temperature, not asserted "
                  "from the algebra."),
    }
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
