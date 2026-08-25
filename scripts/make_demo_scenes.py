"""Generate VERIFIED demo scenes from the real model, with full provenance.

OWNER: Unit B (Darshan).

Every value is produced by the actual trained model on real data at generation time and stamped with
the checkpoint, provenance and timestamp that produced it. Nothing here is hand-written. If the app
serves a cached scene it must label it CACHED (VERIFIED), never present it as live inference.

Scenes are chosen to be oceanographically meaningful for the North Indian Ocean, not to flatter the
model -- each one is paired with the nearest independent Argo profile so the error is visible.

Run:  python scripts/make_demo_scenes.py
"""
from __future__ import annotations
import datetime as dt
import json
import os
import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
warnings.filterwarnings("ignore")
# MC-dropout is stochastic by design, so quoted numbers drifted ~0.001 skill between runs.
# Seeding here (not in Unit A's mc_dropout_predict) makes every reported figure exactly
# reproducible without changing the uncertainty contract.
import torch as _torch; _torch.manual_seed(0); np_seed = 0
from oceanembed import config                       # noqa: E402
from oceanembed.utils import io                     # noqa: E402
from oceanembed.inference import predict as P       # noqa: E402

SCENES = [
    dict(id="arabian-sea-summer-monsoon", lat=15.0, lon=65.0, month=8,
         why="Arabian Sea during the SW monsoon: strong wind-driven upwelling and the saltiest "
             "surface water in the basin. A hard, dynamically active case."),
    dict(id="bay-of-bengal-post-monsoon", lat=15.0, lon=88.0, month=11,
         why="Bay of Bengal after the monsoon: river discharge caps the surface with fresh water, "
             "giving strong salinity stratification and a shallow, sharp thermocline. This is the "
             "regime global models handle worst, and it drives cyclone intensification."),
    dict(id="somali-upwelling", lat=10.0, lon=52.0, month=8,
         why="Somali Current upwelling zone: the coldest surface temperatures in the basin during "
             "the SW monsoon, with cold water drawn up from depth."),
    dict(id="equatorial-indian-winter", lat=6.0, lon=80.0, month=2,
         why="Near-equatorial winter: a warm, deep, weakly-stratified mixed layer -- the opposite "
             "regime from the Somali upwelling, so it tests the other end of the range."),
]


def _nearest_argo(lat, lon, date, max_km=200.0, max_days=10):
    """Nearest independent Argo profile to a scene, or None."""
    try:
        df = io.load_table(config.art("argo_test"))
    except Exception:
        return None
    df["date"] = pd.to_datetime(df["date"])
    d = pd.Timestamp(date)
    sub = df[(df["date"] - d).abs() <= pd.Timedelta(days=max_days)]
    if sub.empty:
        return None
    prof = sub.groupby(["lat", "lon", "date"])
    best, best_km = None, 1e9
    for (la, lo, dtm), grp in prof:
        km = np.hypot((la - lat) * 111.0, (lo - lon) * 111.0 * np.cos(np.deg2rad(lat)))
        if km < best_km:
            best_km, best = km, (la, lo, dtm, grp)
    if best is None or best_km > max_km:
        return None
    la, lo, dtm, grp = best
    t = np.full(config.N_DEPTHS, np.nan)
    t[grp["depth_idx"].to_numpy()] = grp["temp"].to_numpy()
    return dict(lat=float(la), lon=float(lo), date=str(pd.Timestamp(dtm).date()),
                distance_km=round(float(best_km), 1),
                temp=[None if np.isnan(v) else round(float(v), 3) for v in t])


def main() -> None:
    prov = P.provenance()
    if prov.get("source") != "real-glorys":
        raise SystemExit(f"provenance is {prov.get('source')!r} -- refusing to build demo scenes "
                         "from anything but a real-data build.")

    out = dict(
        generated_at=dt.datetime.now().isoformat(timespec="seconds"),
        provenance=prov,
        checkpoint="artifacts/mlp_model.pt",
        depths=list(config.DEPTHS),
        note=("Every number was produced by the real model at generation time. If the UI serves "
              "these, it MUST label them CACHED (VERIFIED) -- never as live inference."),
        scenes=[],
    )

    dates = P.available_dates()
    for sc in SCENES:
        cand = [d for d in dates if d.month == sc["month"] and d.year in config.TEST_YEARS]
        if not cand:
            cand = [d for d in dates if d.month == sc["month"]]
        date = cand[-1]
        rec = dict(sc); rec["date"] = str(date)

        for src in ("satellite", "glorys"):
            if not P.source_available(src):
                continue
            P.set_source(src)
            try:
                o = P.reconstruct(sc["lat"], sc["lon"], date)
            except Exception as e:
                rec[src] = {"error": f"{type(e).__name__}: {e}"}
                continue
            if o["is_land"]:
                rec[src] = {"error": "land"}
                continue
            rec[src] = dict(
                lat=o["lat"], lon=o["lon"], date=str(o["date"]),
                surface={k: round(float(v), 3) for k, v in o["surface"].items()},
                profile=[round(float(v), 3) for v in o["profile_mean"]],
                sigma=[round(float(v), 3) for v in o["profile_std"]],
                reliability=list(o["reliability"]),
                anomaly=None if o["anomaly"] is None else [round(float(v), 3) for v in o["anomaly"]],
            )
        rec["argo"] = _nearest_argo(sc["lat"], sc["lon"], date)
        out["scenes"].append(rec)
        sat = rec.get("satellite", {})
        a = rec["argo"]
        print(f"  {sc['id']:32s} {rec['date']}  "
              f"surface {sat.get('profile',[float('nan')])[0]:6.2f} degC  "
              f"argo {'yes @%.0fkm' % a['distance_km'] if a else 'none within 200 km'}")

    io.save_json(out, config.art("demo_scenes.json"))
    print(f"\nwrote {config.art('demo_scenes.json')}  ({len(out['scenes'])} scenes)")


if __name__ == "__main__":
    main()
