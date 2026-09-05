"""Export one reconstructed field to NetCDF. (Unit A / Arjhun.)

    PYTHONPATH=src python scripts/phase2/export_field.py --date 2026-05-15

WHY A DATE OUTSIDE THE BUNDLE IS REFUSED RATHER THAN SNAPPED
`TSCastPredictor._time` is `argmin(|times - t|)` with no bound. Ask for 1850-01-01 and it returns
bundle index 0, and `predict_field` then produces a complete, plausible, fully-populated file
labelled with a date 64,000 days from the one requested. Nothing in the file would look wrong.

A product file is the artifact that travels without us next to it, so this script refuses instead,
and the refusal names the range -- an error that does not say what IS valid is one the reader cannot
act on. `days_from_requested` is still recorded for the in-bundle case, where snapping to the
nearest available day is legitimate.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                      # noqa: E402
from phase2.export import netcdf as X                      # noqa: E402

OUT_DIR = os.path.join(base.ARTIFACTS, "derived", "export")


def bundle_range(predictor) -> tuple[str, str]:
    times = np.asarray(predictor.data["times"]).astype("datetime64[D]")
    return str(times.min()), str(times.max())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="output .nc (default: artifacts/derived/export/)")
    ap.add_argument("--checkpoint", default=None, help="a specific .pt (default: the shipped model)")
    ap.add_argument("--batch-size", type=int, default=512)
    a = ap.parse_args()

    from phase2.tscast_nio.inference import TSCastPredictor

    predictor = TSCastPredictor(checkpoint=a.checkpoint)
    lo, hi = bundle_range(predictor)

    try:
        want = np.datetime64(a.date, "D")
    except ValueError:
        print(f"[FAIL] {a.date!r} is not a YYYY-MM-DD date")
        return 2
    if not (np.datetime64(lo) <= want <= np.datetime64(hi)):
        print(f"[FAIL] {a.date} is outside the bundle, which covers {lo} .. {hi}.\n"
              f"       Refusing rather than snapping: the model would return the nearest day and "
              f"the file would carry no sign that it is not the day you asked for.")
        return 1

    out = a.out or os.path.join(OUT_DIR, f"oceanembed_{a.date}.nc")
    info = X.export_field(predictor, a.date, out, batch_size=a.batch_size)

    print(f"wrote {info['path']}")
    print(f"  {info['bytes'] / 1e6:.2f} MB · date {info['date']} · stage {info['stage']}")
    print(f"  variables: {', '.join(info['variables'])}")
    print(f"  predict {info['predict_seconds']:.2f}s · build {info['build_seconds']:.2f}s · "
          f"write {info['write_seconds']:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
