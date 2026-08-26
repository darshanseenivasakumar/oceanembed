"""Manual test tool for F1 — ask the collocation engine about any point and read the answer.

Usage
    python scripts/phase2/try_collocation.py                          # a sensible default
    python scripts/phase2/try_collocation.py 18 88 2022-11-15         # lat lon date
    python scripts/phase2/try_collocation.py 18 88 2022-11-15 --json  # raw record
    python scripts/phase2/try_collocation.py --dates                  # what dates exist
    python scripts/phase2/try_collocation.py --tour                   # run a set of tricky cases

Every number printed comes straight from the record the engine returned. Nothing is recomputed
here, so what you see is exactly what a downstream feature would consume.
"""
from __future__ import annotations
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from oceanembed import config  # noqa: E402
from phase2.data.collocation import CollocationEngine  # noqa: E402


def fmt(v, nd=2):
    return "  --  " if v is None else f"{v:6.{nd}f}"


def show(r) -> None:
    q = r.quality
    mark = {"HIGH": "[HIGH]  ", "MEDIUM": "[MEDIUM]", "LOW": "[LOW]   ", "REJECT": "[REJECT]"}.get(q, q)

    print("=" * 74)
    print(f"REQUESTED   {r.requested['latitude']:.4f}N  {r.requested['longitude']:.4f}E  "
          f"{r.requested['datetime'][:10]}")
    print(f"MATCHED     {r.matched['latitude']:.4f}N  {r.matched['longitude']:.4f}E  "
          f"{r.matched['datetime']}   cell {r.matched['grid_i']},{r.matched['grid_j']}")
    print(f"OFFSET      {r.offsets['spatial_km']:.2f} km   {r.offsets['temporal_days']:+.0f} days"
          f"   ({r.offsets['spatial_method']})")
    print(f"QUALITY     {mark}")
    if r.flags:
        print(f"FLAGS       {', '.join(r.flags)}")
    print("=" * 74)

    if q == "REJECT":
        print("\nThis point was rejected. The flags above say why — the engine still reports what")
        print("each source holds there, but you should not treat it as a usable match.\n")

    g = r.sources.get("glorys") or {}
    s = r.sources.get("satellite")
    print("\nSURFACE           GLORYS     SATELLITE     difference")
    for k, unit in [("sst", "degC"), ("sss", "psu"), ("ssh", "m"), ("u", "m/s"), ("v", "m/s")]:
        gv, sv = g.get(k), (s or {}).get(k)
        d = f"{sv - gv:+6.2f}" if (gv is not None and sv is not None) else "  --  "
        print(f"  {k.upper():4s} {unit:5s}    {fmt(gv)}      {fmt(sv)}      {d}")
    if s is None:
        print("  (no satellite within tolerance on this date — normal for half our dates)")

    sub = r.sources.get("subsurface")
    argo = r.sources.get("argo")
    prof = g.get("temperature_profile")
    if prof:
        print("\nPROFILE")
        print("  depth      GLORYS T   salinity     ARGO T    ARGO-GLORYS")
        sal = (sub or {}).get("salinity_profile") or [None] * config.N_DEPTHS
        ap = (argo or {}).get("temperature_profile") or [None] * config.N_DEPTHS
        for k, dep in enumerate(config.DEPTHS):
            t, sa, a = prof[k], sal[k], ap[k]
            diff = f"{a - t:+7.2f}" if (a is not None and t is not None) else "   --  "
            print(f"  {dep:5d} m    {fmt(t)}     {fmt(sa)}    {fmt(a)}    {diff}")

    if argo:
        print(f"\nARGO        {argo['latitude']:.3f}N {argo['longitude']:.3f}E  {argo['datetime']}")
        print(f"            {argo['spatial_offset_km']:.1f} km away, "
              f"{argo['temporal_offset_days']:+.0f} days, {argo['n_levels']} levels")
        print(f"            {argo['note']}")
    else:
        print("\nARGO        none within tolerance of this point")

    p = r.provenance
    print(f"\nPROVENANCE  {p['engine']}")
    print(f"            tolerance {p['tolerance_days']} days | grid {p['grid']}")
    print(f"            files: {', '.join(p['files'])}")
    print()


TOUR = [
    (15.0, 65.0, None, "open Arabian Sea, exactly on a grid point"),
    (15.13, 65.07, None, "off-grid — watch the spatial offset appear"),
    (18.0, 88.0, None, "N Bay of Bengal — fresh surface water"),
    (15.0, 75.0, None, "inland India — should be REJECTed as LAND"),
    (0.0, 65.0, None, "south of the domain — should be REJECTed"),
    (29.5, 48.25, None, "Persian Gulf — shallow, no 1000 m water"),
]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    engine = CollocationEngine()
    dates = [str(d) for d in np.load(
        os.path.join(config.DATA_PROCESSED, "grids.npz"))["times"].astype("datetime64[D]")]

    if "--dates" in sys.argv:
        print(f"{len(dates)} dates available (grids are MONTHLY — the 15th of each month):")
        for i in range(0, len(dates), 6):
            print("   " + "  ".join(dates[i:i + 6]))
        print("\nA date between these still works — the engine matches the nearest and tells you")
        print("the offset. Beyond 10 days it returns REJECT.")
        return

    if "--tour" in sys.argv:
        for lat, lon, _, label in TOUR:
            print(f"\n### {label}")
            show(engine.collocate(lat, lon, dates[-1]))
        return

    lat = float(args[0]) if len(args) > 0 else 15.0
    lon = float(args[1]) if len(args) > 1 else 65.0
    when = args[2] if len(args) > 2 else dates[-1]

    r = engine.collocate(lat, lon, when)
    if as_json:
        print(json.dumps(r.to_dict(), indent=2, default=str))
    else:
        show(r)


if __name__ == "__main__":
    main()
