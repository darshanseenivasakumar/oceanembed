"""Measure the DOMAIN SHIFT between real satellite L4 fields and the GLORYS fields we trained on.

OWNER: Unit B (Darshan).

WHY: the model learns a mapping from GLORYS surface fields to GLORYS subsurface temperature. At
inference we want to feed REAL SATELLITE observations (SIH26066 says "from surface satellite
observations"). Those are not the same quantities:

  * OSTIA analysed_sst vs GLORYS thetao@0m  -- both degC, but different products/biases
  * DUACS adt          vs GLORYS zos        -- adt is referenced to a mean geoid; an OFFSET is expected
  * DUACS ugos/vgos    vs GLORYS uo/vo      -- GEOSTROPHIC only vs full (incl. ageostrophic) flow

If we feed satellite fields to a GLORYS-trained model without knowing these gaps, any skill drop is
unexplainable. This script quantifies them on the SAME dates and grid, so the drop can be attributed.

It reports, per variable: bias (satellite - glorys), RMSD, and correlation over common ocean cells.

Run:  python scripts/compare_satellite_vs_glorys.py
"""
from __future__ import annotations
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config  # noqa: E402

G = os.path.join(config.DATA_PROCESSED, "grids.npz")
S = os.path.join(config.DATA_PROCESSED, "satellite_grids.npz")
VARS = ["sst", "sss", "ssh", "u", "v"]


def main() -> None:
    for p, what in ((G, "GLORYS (scripts/prepare_dataset.py)"),
                    (S, "satellite (preprocess_satellite)")):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p} -- build it first: {what}")

    g = dict(np.load(G, allow_pickle=False))
    s = dict(np.load(S, allow_pickle=False))
    gt = g["times"].astype("datetime64[D]")
    st = s["times"].astype("datetime64[D]")

    common = np.intersect1d(gt, st)
    if common.size == 0:
        raise SystemExit(
            f"no overlapping dates.\n  GLORYS: {gt.min()}..{gt.max()} ({gt.size})"
            f"\n  satellite: {st.min()}..{st.max()} ({st.size})"
        )
    gi = np.searchsorted(gt, common)
    si = np.searchsorted(st, common)

    print("=" * 74)
    print(f"DOMAIN SHIFT: real satellite L4  vs  GLORYS surface fields")
    print(f"  {common.size} common dates: {common.min()} .. {common.max()}")
    print("=" * 74)
    print(f"  {'var':5s} {'bias(sat-glo)':>14s} {'RMSD':>9s} {'corr':>7s} {'n_cells':>9s}")

    rows = {}
    for v in VARS:
        a = s[v][si].astype("float64")   # satellite
        b = g[v][gi].astype("float64")   # glorys
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() == 0:
            print(f"  {v:5s} {'no overlap':>14s}")
            continue
        d = a[m] - b[m]
        bias = float(d.mean())
        rmsd = float(np.sqrt((d ** 2).mean()))
        corr = float(np.corrcoef(a[m], b[m])[0, 1])
        rows[v] = dict(bias=bias, rmsd=rmsd, corr=corr, n=int(m.sum()))
        print(f"  {v:5s} {bias:+14.4f} {rmsd:9.4f} {corr:7.3f} {m.sum():9d}")

    print("-" * 74)
    print("HOW TO READ THIS")
    print("  corr high + bias small  -> the satellite field is a usable stand-in as-is.")
    print("  corr high + bias LARGE  -> systematic offset (expected for adt vs zos). The model was")
    print("                             trained on the GLORYS scale, so a constant offset shifts")
    print("                             every prediction. Report it; consider bias correction.")
    print("  corr LOW                -> genuinely different quantity (expect this for u/v:")
    print("                             geostrophic-only vs full flow). Skill loss here is physical,")
    print("                             not a bug.")
    print("\nNone of this is a reason to hide the satellite result -- it is the reason it is")
    print("interpretable. Quote these numbers alongside any satellite-driven skill figure.")


if __name__ == "__main__":
    main()
