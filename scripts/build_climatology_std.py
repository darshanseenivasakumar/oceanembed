"""Build the climatology STANDARD DEVIATION array Unit C needs for a real standardized anomaly.

OWNER: Unit B (Darshan). Requested by Unit C in products/anomaly.py.

WHY: `standardized_anomaly()` currently divides by the SPATIAL spread of the anomaly field at each
depth -- "how unusual is this cell versus the rest of the basin today". That is a real quantity but
it is NOT a climatological sigma: a cell can be 2 sigma spatially while being perfectly normal for
that location, that depth, that month.

A proper standardized anomaly divides by the INTERANNUAL variability at each (month, cell, depth) --
how much this place actually varies year to year. That needs the training time series, which lives
on the Unit B side. This script computes it and writes artifacts/climatology_std.npy, same shape as
climatology.npy: (12, 100, 240, 15).

HONEST LIMITATION, and it must be quoted wherever the sigma is used: our training set has ONE date
per month per year over 3 train years, so each (month, cell) sigma is estimated from n=3. That is a
very small sample -- the sigma is indicative, not a rigorous climatological standard deviation.
Cells with fewer than MIN_N samples fall back to that month's basin-wide sigma at that depth, and
the per-cell sample count is saved alongside so nobody has to guess.

Run:  python scripts/build_climatology_std.py
"""
from __future__ import annotations
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from oceanembed import config          # noqa: E402
from oceanembed.utils import io        # noqa: E402

MIN_N = 2   # need at least 2 samples for a spread at all


def main() -> None:
    y = io.load_npy(config.art("y_train.npy"))
    meta = io.load_table(config.art("meta_train"))

    shape = (12, config.N_LAT, config.N_LON, config.N_DEPTHS)
    s1 = np.zeros(shape, dtype="float64")      # sum
    s2 = np.zeros(shape, dtype="float64")      # sum of squares
    cnt = np.zeros((12, config.N_LAT, config.N_LON), dtype="int64")

    months = meta["month"].to_numpy().astype(int) - 1
    cells = meta["cell_id"].to_numpy().astype(int)
    ii, jj = np.divmod(cells, config.N_LON)
    yy = y.astype("float64")
    np.add.at(s1, (months, ii, jj), yy)
    np.add.at(s2, (months, ii, jj), yy ** 2)
    np.add.at(cnt, (months, ii, jj), 1)

    n = cnt[..., None].astype("float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        var = s2 / n - (s1 / n) ** 2
    var = np.where(np.isfinite(var), np.maximum(var, 0.0), np.nan)
    std = np.sqrt(var).astype("float32")
    std[cnt < MIN_N] = np.nan                  # not enough samples to claim a spread

    # Fall back to that month's basin-wide sigma per depth where a cell is unusable.
    for m in range(12):
        basin = np.nanmean(std[m].reshape(-1, config.N_DEPTHS), axis=0)
        bad = ~np.isfinite(std[m])
        std[m][bad] = np.broadcast_to(basin, std[m].shape)[bad]

    io.save_npy(std, config.art("climatology_std.npy"))
    io.save_npy(cnt.astype("int16"), config.art("climatology_n.npy"))

    print(f"wrote {config.art('climatology_std.npy')}  shape={std.shape}")
    print(f"wrote {config.art('climatology_n.npy')}    per-(month,cell) sample counts")
    occupied = cnt[cnt > 0]
    print(f"\nsamples per (month,cell): min {occupied.min()}, median {int(np.median(occupied))}, "
          f"max {occupied.max()}   <-- n is TINY; treat sigma as indicative")
    print("\n  basin-mean interannual sigma by depth (degC):")
    for k, d in enumerate(config.DEPTHS):
        print(f"    {d:5d} m : {float(np.nanmean(std[:, :, :, k])):6.3f}")


if __name__ == "__main__":
    main()
