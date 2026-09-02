"""Produce dated TCHP / OHC / D26 NetCDFs from the FROZEN model.

    PYTHONPATH=src python scripts/phase2/make_heat_content.py --date 2026-05-15
    PYTHONPATH=src python scripts/phase2/make_heat_content.py --range 2026-05-01 2026-05-07

Runs the same frozen inference path the dashboard uses (predict_field -> the shipped checkpoint on
its own satellite bundle), turns each daily temperature field into the three heat-content products,
and writes one CF-style NetCDF per date to artifacts/derived/heat_content/.

Needs the satellite bundle (data/processed/daily_sat/v001) — so it runs on the box that carries it.
Touches nothing frozen; this is a read-only consumer of model outputs.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base            # noqa: E402
from phase2.derived import heat_content as hc     # noqa: E402

OUT_DIR = os.path.join(base.ARTIFACTS, "derived", "heat_content")


def _dates(args) -> list[str]:
    if args.date:
        return [args.date]
    start, end = pd.Timestamp(args.range[0]), pd.Timestamp(args.range[1])
    return [str(d.date()) for d in pd.date_range(start, end, freq="D")]


def _one(predictor, date_str: str) -> str:
    from phase2.tscast_nio.field import predict_field

    field = predict_field(predictor, date_str)
    products = hc.heat_content_field(field)
    ds = hc.to_xarray(products)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"heat_content_{field['date']}.nc")
    ds.to_netcdf(out)

    finite = np.isfinite(products["tchp"])
    tmax = float(np.nanmax(products["tchp"])) if finite.any() else float("nan")
    print(f"  {field['date']}: wrote {out}  (max TCHP {tmax:.1f} kJ/cm^2, "
          f"{int(finite.sum())} ocean cells)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="single date, YYYY-MM-DD")
    g.add_argument("--range", nargs=2, metavar=("START", "END"), help="inclusive date range")
    args = ap.parse_args()

    from phase2.tscast_nio.inference import TSCastPredictor

    predictor = TSCastPredictor()     # frozen model, its own bundle — the same object the app uses
    dates = _dates(args)
    print(f"Heat content for {len(dates)} date(s) -> {OUT_DIR}")
    for d in dates:
        _one(predictor, d)


if __name__ == "__main__":
    main()
