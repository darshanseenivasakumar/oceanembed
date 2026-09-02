"""A12 / A9 -- score trained runs per BASIN, and test whether the satellite penalty concentrates.

THE CLAIM THIS EXISTS TO TEST
Satellite SSS floors at 30.78 psu while the real Bay of Bengal reaches 6.43 (Meghna/Ganges). So
the satellite input is blind to that basin's defining feature, and the satellite-vs-GLORYS penalty
SHOULD be larger in the Bay of Bengal than in the Arabian Sea.

That is a hypothesis, and until now it has been asserted with no number under it. Darshan's D5
review is blunt about the consequence: the BoB story is the most jury-legible result in the
project, and it becomes EVIDENCE only if the penalty is shown to concentrate rather than being
basin-flat. A basin-flat result would mean the SSS explanation is wrong, or at least not the
mechanism -- and that is a real possible outcome of running this.

Basins come from `phase2.basins`, the single canonical partition (Darshan, 21b5131). No new box is
drawn here. Per-basin scoring uses `metrics.per_depth_by_basin`, also his.

Run:  PYTHONPATH=src python scripts/phase2/score_by_basin.py
      PYTHONPATH=src python scripts/phase2/score_by_basin.py --tags sat_7ch_s42 canon_7ch_s42
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base                       # noqa: E402
from oceanembed.validation import validate_argo as VA       # noqa: E402
from phase2.tscast_nio import dataset as D, eval_argo, metrics  # noqa: E402
from phase2.tscast_nio.models import TSCastNIO              # noqa: E402

MAX_DAYS = 5
OUT = base.art("basin_by_depth.json")
DEFAULT_TAGS = ("sat_7ch_s42", "canon_7ch_s42")


def score(tag: str, device: str = "cuda") -> dict:
    """Score one trained run against independent Argo, split by canonical basin."""
    mpath = base.art(f"tscast_stage1_{tag}_metrics.json")
    cpath = base.art(f"tscast_stage1_{tag}.pt")
    for p in (mpath, cpath):
        if not os.path.exists(p):
            raise SystemExit(f"{p} absent -- cannot score {tag!r} without both its checkpoint and "
                             f"its metrics (the metrics name the bundle it was trained on).")
    meta = json.load(open(mpath, encoding="utf-8"))
    ck = torch.load(cpath, map_location="cpu", weights_only=False)

    bundle = meta.get("daily_dir") or os.path.join(base.DATA_PROCESSED, "daily")
    d = D.load_daily(bundle)
    src = d.get("input_source", "unknown")

    # Match the training run's channel set exactly, or the tensor will not line up.
    want = list(ck["channels"])
    have = [str(c) for c in d["channels"]]
    keep = [have.index(c) for c in want]
    d["surface"] = d["surface"][..., keep]
    d["channels"] = want

    times = np.asarray(d["times"], dtype="datetime64[D]")
    _, te_t = D.daily_split_indices(times)
    # EXACTLY train_stage1.py:224 -- a different climatology would make these irreconcilable.
    clim = np.load(base.art("climatology.npy"))

    # Built with the SAME arguments train_stage1 uses for ds_te, including letting p default to
    # config.P rather than passing it. The whole point of eval_argo is that there is one path;
    # rebuilding the dataset differently here would reintroduce the drift it exists to remove.
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ck["norm"], t_seq=ck["T_SEQ"],
                             max_samples=meta.get("test_samples", 12000),
                             seed=ck.get("seed"), clim=clim, return_clim=True)

    dev = torch.device(device if (device != "cuda" or torch.cuda.is_available()) else "cpu")
    model = TSCastNIO(ck["encoder"], c_in=len(want), t_seq=ck["T_SEQ"], p=ck["P"],
                      latent=ck.get("latent"), residual=ck.get("residual", True),
                      unet_channels=tuple(ck["unet_channels"]) if ck.get("unet_channels") else None,
                      decoder=ck.get("decoder", "simple"), stage=1).to(dev)
    model.load_state_dict(ck["state_dict"])

    keys, truth, keep, t_idx, la, lo = eval_argo.collocate(d, te_t, verbose=False)
    mu, sigma, truth_k, clim_k = eval_argo.predict_at_argo(
        model, ds_te, keys, truth, keep, t_idx, la, lo, clim, dev)
    lat = keys["lat"].values[keep]
    lon = keys["lon"].values[keep]

    by_basin = metrics.per_depth_by_basin(mu, truth_k, lat, lon,
                                          clim=clim_k, reference="argo")
    return {"tag": tag, "input_source": src, "bundle": bundle,
            "seed": ck.get("seed"), "by_basin": by_basin}


def _overall(block: dict) -> dict:
    """`per_depth_by_basin` nests per-basin blocks; pull each one's overall RMSE and n."""
    out = {}
    ov = block.get("overall", {}).get("overall", {})
    if ov:
        out["overall"] = (ov.get("rmse"), ov.get("n"))
    for name, b in block.get("by_basin", {}).items():
        o = (b or {}).get("overall", {}) or {}
        out[name] = (o.get("rmse"), o.get("n"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+", default=list(DEFAULT_TAGS))
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()

    results = [score(t, a.device) for t in a.tags]

    print("\n" + "=" * 76)
    print("A12 -- PER-BASIN SCORES  (canonical partition, phase2.basins)")
    print("=" * 76)
    per_tag = {}
    for r in results:
        ov = _overall(r["by_basin"])
        per_tag[r["tag"]] = (r["input_source"], ov)
        print(f"\n  {r['tag']}  [input: {r['input_source']}]  seed {r['seed']}")
        for name, (rmse, n) in ov.items():
            print(f"      {name:22} RMSE {rmse if rmse is None else round(rmse, 4)}   n={n}")

    sat = [t for t, (s, _) in per_tag.items() if s == "satellite"]
    glo = [t for t, (s, _) in per_tag.items() if s == "glorys"]
    if sat and glo:
        print("\n" + "-" * 76)
        print("  SATELLITE PENALTY BY BASIN  (satellite RMSE - GLORYS RMSE)")
        print("-" * 76)
        _, so = per_tag[sat[0]]
        _, go = per_tag[glo[0]]
        deltas = {}
        for name in so:
            if name in go and so[name][0] is not None and go[name][0] is not None:
                deltas[name] = so[name][0] - go[name][0]
                print(f"      {name:22} {deltas[name]:+.4f}   "
                      f"(sat {so[name][0]:.4f} vs glorys {go[name][0]:.4f}, n={so[name][1]})")
        bob = next((v for k, v in deltas.items() if "beng" in k.lower()), None)
        ara = next((v for k, v in deltas.items() if "arab" in k.lower()), None)
        print()
        if bob is not None and ara is not None:
            if bob > ara:
                print(f"  The penalty is LARGER in the Bay of Bengal ({bob:+.4f}) than the Arabian "
                      f"Sea ({ara:+.4f}),")
                print(f"  a difference of {bob - ara:+.4f} degC. That is consistent with satellite "
                      f"SSS being blind")
                print("  to the Meghna/Ganges plume -- the hypothesis survives this test.")
            else:
                print(f"  The penalty is NOT larger in the Bay of Bengal ({bob:+.4f}) than the "
                      f"Arabian Sea ({ara:+.4f}).")
                print("  The SSS-blindness story does NOT explain the satellite penalty, or is not")
                print("  the dominant mechanism. It must not be presented as if it did.")
        print("\n  n=1 per leg. A basin difference smaller than the seed spread is not a result.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"runs": results, "basins": "phase2.basins canonical partition"}, f, indent=2)
    print(f"\n  wrote {OUT}")


if __name__ == "__main__":
    main()
