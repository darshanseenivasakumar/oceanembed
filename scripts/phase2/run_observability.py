"""The observability field: where the satellite stops informing depth, per cell and per day.

    PYTHONPATH=src python scripts/phase2/run_observability.py

WHAT IT PRODUCES
----------------
1. The per-depth, per-channel Jacobian of the SHIPPED model -- degrees Celsius of response at each
   depth per one-standard-deviation coherent shift of each satellite channel. This is where the
   model tells you what it is actually reading, and at which depth.
2. A sensitivity-derived information depth per profile, and a basin map of it for one date.
3. The join that makes it a claim rather than a diagnostic: are our errors larger below the
   information floor than above it?

WHAT IT IS NOT
--------------
Not an information-theoretic bound. No noise model, no likelihood, no mutual information. It is a
measured property of THIS trained network: a different architecture could in principle extract
signal where this one has gone flat. Every artifact this script writes carries that sentence.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                             # noqa: E402
from phase2 import basins                                         # noqa: E402
from phase2.reliability import harness as H                       # noqa: E402
from phase2.reliability import observability as OB                # noqa: E402

TAUS = (0.05, 0.10, 0.20, 0.30, 0.50)


def _table(J, channels, y_std) -> list[dict]:
    """Per-depth, per-channel mean |sensitivity|, plus which channel leads at each depth."""
    C = np.abs(J).mean(axis=0)                               # (15, C)
    S = OB.aggregate(J, "l2").mean(axis=0)                   # (15,)
    rows = []
    for k, d in enumerate(OB.DEPTHS):
        lead = int(np.argmax(C[k]))
        rows.append({
            "depth": float(d),
            "per_channel": {c: float(C[k, i]) for i, c in enumerate(channels)},
            "l2": float(S[k]),
            "l2_over_natural_variability": float(S[k] / y_std[k]),
            "leading_channel": channels[lead],
            "leading_share": float(C[k, lead] / max(1e-12, C[k].sum())),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default=base.art("tscast_stage1.pt"))
    ap.add_argument("--daily-dir", default=H.SAT_BUNDLE)
    ap.add_argument("--tau", type=float, default=OB.TAU)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--map-stride", type=int, default=2,
                    help="subsample the basin map by this factor in each direction")
    ap.add_argument("--skip-map", action="store_true")
    ap.add_argument("--out", default=base.art("observability.json"))
    ap.add_argument("--out-npz", default=base.art("observability_field.npz"))
    a = ap.parse_args()

    ctx = H.load(a.checkpoint, daily_dir=a.daily_dir)
    ctrl = ctx.control_rmse()
    print(f"control: rmse {ctrl['rmse']:.10f}  recorded {ctrl['recorded_rmse']}  "
          f"agrees={ctrl['agrees']}  profiles={ctrl['n_profiles']}")
    if ctrl["agrees"] is not True:
        raise SystemExit("REFUSING TO WRITE: control does not reproduce the recorded RMSE.")

    y_std = np.asarray(ctx.y_std, dtype="float64")
    chans = ctx.channels

    # ---------------------------------------------------------------- at the floats
    t0 = time.time()
    J = OB.jacobian(ctx, batch_size=a.batch_size)
    print(f"jacobian: {J['coherent'].shape[0]} profiles x 15 depths x {len(chans)} channels "
          f"in {time.time()-t0:.1f}s")

    rows = _table(J["coherent"], chans, y_std)
    print(f"\n{'depth':>6} " + "".join(f"{c:>7}" for c in chans) +
          f"{'L2':>8}{'/var':>7}  leading")
    for r in rows:
        print(f"{int(r['depth']):>6} " +
              "".join(f"{r['per_channel'][c]:7.3f}" for c in chans) +
              f"{r['l2']:8.3f}{r['l2_over_natural_variability']:7.2f}  "
              f"{r['leading_channel']} ({r['leading_share']*100:.0f}%)")

    sens = OB.aggregate(J["coherent"], "l2")
    info = OB.information_depth(sens, tau=a.tau)
    err = ctx.predict()["temperature"] - ctx.truth_t
    join = OB.residual_vs_information(err, info["depth_m"])
    print(f"\ninformation depth (tau={a.tau}): median "
          f"{np.nanmedian(info['depth_m']):.0f} m, "
          f"IQR {np.nanpercentile(info['depth_m'],25):.0f}-"
          f"{np.nanpercentile(info['depth_m'],75):.0f} m, "
          f"{info['n_without_signal']} profiles with no signal anywhere")
    print(f"error above the floor  MAE {join['mae_above_floor']:.4f} (n={join['n_above_floor']})")
    print(f"error below the floor  MAE {join['mae_below_floor']:.4f} (n={join['n_below_floor']})"
          f"   pooled ratio {join['pooled_ratio']:.2f}x  [CONFOUNDED BY DEPTH -- not the test]")
    print(f"depth-controlled ratios (below/above, at equal depth): "
          f"{[round(r, 2) for r in join['depth_controlled_ratios']]} "
          f"over {join['n_testable_depths']} testable depths")
    print(f"  -> {join['verdict']}")

    tau_sweep = {}
    for t in TAUS:
        i = OB.information_depth(sens, tau=t)
        tau_sweep[str(t)] = {
            "median_depth_m": float(np.nanmedian(i["depth_m"])),
            "p25": float(np.nanpercentile(i["depth_m"], 25)),
            "p75": float(np.nanpercentile(i["depth_m"], 75)),
            "n_without_signal": i["n_without_signal"],
        }

    out = {
        "experiment": "sensitivity-derived observability field (Jacobian of the frozen model)",
        "checkpoint": os.path.basename(ctx.ckpt_path),
        "control": ctrl,
        "not_a_claim": ("This is a sensitivity-derived information depth, NOT an "
                        "information-theoretic bound. It is a measured property of this trained "
                        "network; another architecture could extract signal where this one is "
                        "flat."),
        "units": J["units"],
        "channels": chans,
        "depths": OB.DEPTHS.tolist(),
        "natural_variability_degC": y_std.tolist(),
        "by_depth": rows,
        "information_depth": {
            "tau": a.tau,
            "definition": info["definition"],
            "median_m": float(np.nanmedian(info["depth_m"])),
            "p25_m": float(np.nanpercentile(info["depth_m"], 25)),
            "p75_m": float(np.nanpercentile(info["depth_m"], 75)),
            "n_without_signal": info["n_without_signal"],
            "tau_sweep": tau_sweep,
        },
        "residual_vs_information": join,
        "n_argo_profiles": int(len(ctx.keys)),
    }

    # ---------------------------------------------------------------- per basin
    lat = ctx.keys["lat"].to_numpy(dtype="float64")
    lon = ctx.keys["lon"].to_numpy(dtype="float64")
    who = basins.classify_points(lat, lon)
    if who is not None:
        per = {}
        for name in ("arabian_sea", "bay_of_bengal"):
            m = np.asarray(who) == name
            if m.sum() == 0:
                continue
            per[name] = {
                "n_profiles": int(m.sum()),
                "median_information_depth_m": float(np.nanmedian(info["depth_m"][m])),
                "peak_sensitivity_depth_m": float(OB.DEPTHS[int(np.argmax(sens[m].mean(axis=0)))]),
            }
            print(f"{name:14}: median info depth "
                  f"{per[name]['median_information_depth_m']:.0f} m, peak sensitivity at "
                  f"{per[name]['peak_sensitivity_depth_m']:.0f} m  (n={per[name]['n_profiles']})")
        out["by_basin"] = per

    # ---------------------------------------------------------------- the map
    if not a.skip_map:
        land = np.asarray(ctx.bundle["land_mask"], bool)
        t_idx = int(ctx.argo_idx[:, 0].max())
        ii, jj = np.nonzero(~land)
        keep = (ii % a.map_stride == 0) & (jj % a.map_stride == 0)
        ii, jj = ii[keep], jj[keep]
        index = np.stack([np.full(ii.size, t_idx), ii, jj], axis=1)
        print(f"\nmap: {ii.size} ocean cells (stride {a.map_stride}) on "
              f"{str(ctx.bundle['times'][t_idx])[:10]}")
        t0 = time.time()
        Jm = OB.jacobian(ctx, index=index, batch_size=a.batch_size)
        sm = OB.aggregate(Jm["coherent"], "l2")
        im = OB.information_depth(sm, tau=a.tau)
        print(f"  {time.time()-t0:.1f}s  median info depth {np.nanmedian(im['depth_m']):.0f} m")

        grid = np.full(land.shape, np.nan)
        grid[ii, jj] = im["depth_m"]
        peak = np.full(land.shape, np.nan)
        peak[ii, jj] = OB.DEPTHS[np.argmax(sm, axis=1)]
        np.savez_compressed(a.out_npz, information_depth=grid, peak_sensitivity_depth=peak,
                            sensitivity=sm, rows=ii, cols=jj,
                            depths=OB.DEPTHS, channels=np.array(chans),
                            date=str(ctx.bundle["times"][t_idx])[:10], tau=a.tau)
        out["map"] = {
            "date": str(ctx.bundle["times"][t_idx])[:10],
            "n_cells": int(ii.size),
            "stride": a.map_stride,
            "median_information_depth_m": float(np.nanmedian(im["depth_m"])),
            "npz": os.path.basename(a.out_npz),
            "seconds": round(time.time() - t0, 1),
        }
        print(f"  wrote {a.out_npz}")

    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
