"""Fit the satellite->GLORYS bias correction on TRAIN-PERIOD dates only.

OWNER: Unit B (Darshan).

WHY: `adt` (satellite) and `zos` (GLORYS) are different reference surfaces. MEASURED on 2022:
corr 0.975 but bias +0.417 m -- near-perfect SHAPE agreement, wrong LEVEL. The model was trained on
the zos scale, and SSH sets thermocline depth, so an uncorrected 0.4 m offset displaces every
prediction on the satellite path.

LEAKAGE RULE (the reason this is a separate script): the correction MUST be fitted on dates in the
TRAIN period only. Fitting it on 2022 -- our held-out test year -- would tune the inference pipeline
using test data, and the satellite skill number afterwards would be meaningless.

Writes artifacts/satellite_bias.json: {var: {offset, corr, n, fitted_on}}.
`preprocess_satellite.run(apply_bias=True)` subtracts these offsets.

Run:  python scripts/fit_satellite_bias.py
"""
from __future__ import annotations
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config          # noqa: E402
from oceanembed.utils import io        # noqa: E402

VARS = ["sst", "sss", "ssh", "u", "v"]


def main() -> None:
    gp = os.path.join(config.DATA_PROCESSED, "grids.npz")
    sp = os.path.join(config.DATA_PROCESSED, "satellite_grids.npz")
    for p in (gp, sp):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")

    g = dict(np.load(gp, allow_pickle=False))
    s = dict(np.load(sp, allow_pickle=False))
    gt = g["times"].astype("datetime64[D]")
    st = s["times"].astype("datetime64[D]")

    # TRAIN-period dates only -- this is the whole point of the script.
    st_years = st.astype("datetime64[Y]").astype(int) + 1970
    train_mask = np.isin(st_years, config.TRAIN_YEARS)
    common = np.intersect1d(gt, st[train_mask])
    if common.size == 0:
        raise SystemExit(
            "no TRAIN-period satellite dates overlap GLORYS.\n"
            f"  satellite years present: {sorted(set(st_years.tolist()))}\n"
            f"  TRAIN_YEARS: {config.TRAIN_YEARS}\n"
            "  Download train-year satellite dates first -- do NOT fit on the test year."
        )

    gi = np.searchsorted(gt, common)
    si = np.searchsorted(st, common)

    print(f"fitting on {common.size} TRAIN-period dates: {common.min()} .. {common.max()}")
    print(f"  (test years {config.TEST_YEARS} deliberately EXCLUDED -- fitting there would leak)")
    print(f"  {'var':5s} {'offset':>10s} {'corr':>7s} {'n':>9s}")

    out = {}
    for v in VARS:
        a = s[v][si].astype("float64")
        b = g[v][gi].astype("float64")
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() == 0:
            continue
        offset = float((a[m] - b[m]).mean())
        corr = float(np.corrcoef(a[m], b[m])[0, 1])
        out[v] = dict(offset=offset, corr=corr, n=int(m.sum()),
                      fitted_on=[str(d) for d in common])
        print(f"  {v:5s} {offset:+10.4f} {corr:7.3f} {m.sum():9d}")

    io.save_json(out, config.art("satellite_bias.json"))
    print(f"\nwrote {config.art('satellite_bias.json')}")
    print("Correct ONLY variables whose corr is high -- a low-corr variable (u/v are geostrophic-only)")
    print("is a different physical quantity, and shifting its mean does not make it the right one.")


if __name__ == "__main__":
    main()
