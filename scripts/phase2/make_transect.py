"""Produce a depth-vs-distance transect from the FROZEN model, as an npz.

    PYTHONPATH=src python scripts/phase2/make_transect.py --lat0 10 --lon0 85 --lat1 15 --lon1 95 --date 2026-05-15
    PYTHONPATH=src python scripts/phase2/make_transect.py --lat0 8 --lon0 68 --lat1 20 --lon1 90 --date 2026-05-15 --n 60

Runs the same frozen inference path the dashboard uses (predict_field -> the shipped checkpoint on
its own bundle), samples the reconstructed field along the great circle between the two endpoints
by bilinear interpolation, and writes one npz per call to artifacts/derived/transect/. Touches
nothing frozen; a read-only consumer of model outputs.

By default it loads the shipped checkpoint on its own bundle, so it needs the machine that carries
that bundle. Pass --checkpoint / --bundle to sample a different (e.g. local GLORYS) run.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base            # noqa: E402
from phase2.derived import transect as T          # noqa: E402

OUT_DIR = os.path.join(base.ARTIFACTS, "derived", "transect")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat0", type=float, required=True)
    ap.add_argument("--lon0", type=float, required=True)
    ap.add_argument("--lat1", type=float, required=True)
    ap.add_argument("--lon1", type=float, required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--n", type=int, default=50, help="points along the track (default 50)")
    ap.add_argument("--checkpoint", default=None, help="a specific .pt (default: the shipped model)")
    ap.add_argument("--bundle", default=None,
                    help="a specific processed daily bundle dir, if --checkpoint needs one")
    args = ap.parse_args()

    from phase2.tscast_nio.field import predict_field
    from phase2.tscast_nio.inference import TSCastPredictor
    from phase2.tscast_nio import dataset as D

    data = D.load_daily(args.bundle) if args.bundle else None
    predictor = TSCastPredictor(checkpoint=args.checkpoint, data=data)

    field = predict_field(predictor, args.date)
    track = T.track_points(args.lat0, args.lon0, args.lat1, args.lon1, n=args.n)
    sec = T.sample_transect(track, field)

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = f"{args.lat0}_{args.lon0}__{args.lat1}_{args.lon1}_{field['date']}"
    out = os.path.join(OUT_DIR, f"transect_{tag}.npz")
    np.savez_compressed(
        out, date=field["date"], lat=sec["lat"], lon=sec["lon"],
        distance_km=sec["distance_km"], depths=sec["depths"],
        temperature=sec["temperature"], sigma=sec["sigma"],
        d20=T.isotherm_line(sec, 20.0), d26=T.isotherm_line(sec, 26.0))

    temp = sec["temperature"]
    d26 = T.isotherm_line(sec, 26.0)
    print(f"wrote {out}")
    print(f"  {temp.shape[0]} points, {int(sec['distance_km'][-1])} km, "
          f"{int(np.isfinite(temp).sum())}/{temp.size} finite cells")
    if np.isfinite(temp[:, 0]).any():
        print(f"  surface {np.nanmin(temp[:, 0]):.2f}..{np.nanmax(temp[:, 0]):.2f} C")
    if np.isfinite(d26).any():
        # A NaN D26 has THREE causes and they are not interchangeable. This line used to call all
        # of them "below 26 C at the surface" -- on an 8N 68E -> 20N 88E track in May that was
        # wrong for every one of the 22 NaN points: 17 were LAND (the great circle crosses India)
        # and 5 were columns that never cool to 26 C. Zero had a cold surface, in a basin reading
        # 30-31 C. Reporting land as a temperature condition is the same error class as letting a
        # missing value read as zero.
        temp_arr = np.asarray(sec["temperature"])
        land = warm_all = cold_surf = 0
        for row, isnan in zip(temp_arr, np.isnan(d26)):
            if not isnan:
                continue
            fin = np.isfinite(row)
            if not fin.any():
                land += 1
            elif row[fin][0] < 26.0:
                cold_surf += 1
            elif np.nanmin(row) > 26.0:
                warm_all += 1
        why = ", ".join(p for p in (
            f"{land} no valid water (land or dry cell)" if land else "",
            f"{warm_all} never cool to 26 C" if warm_all else "",
            f"{cold_surf} surface already below 26 C" if cold_surf else "") if p)
        print(f"  D26 {np.nanmin(d26):.1f}..{np.nanmax(d26):.1f} m "
              f"({int(np.isnan(d26).sum())} points without a D26" + (f": {why})" if why else ")"))


if __name__ == "__main__":
    main()
