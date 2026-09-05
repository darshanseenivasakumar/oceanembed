"""Can we reach moored-buoy temperature for the model's window? Owner: Unit A (Arjhun).

Feature 6 validates the model along a TIME axis at a fixed point -- something Argo genuinely cannot
do, because floats drift and revisit a spot every 5-10 days. Moored buoys sit still and sample
continuously. The repo has none, so this establishes what exists and whether it is reachable,
BEFORE any validation code is written against it.

WHAT THIS PROBE FOUND ON 2026-09-05 -- and the shape of it is familiar
---------------------------------------------------------------------
Exactly the INCOIS pattern from docs/INCOIS_PROBE.md: the CATALOGUE is healthy and the DATA LAYER
is not.

  reachable, 1-2 s      data.pmel.noaa.gov/pmel/erddap  -- search, /info, and even /tabledap/*.das
  reachable, 1-2 s      osmc.noaa.gov/erddap            -- /info for the same dataset
  UNREACHABLE, ~43.5 s  every request that returns actual DATA, on BOTH hosts

`/files/<dataset>/<file>` 302-redirects to `http://coastwatch.pfeg.noaa.gov/...`, which fails two
ways from here: plain HTTP times out at connect, and the HTTPS form gives
`SSL: UNEXPECTED_EOF_WHILE_READING`. Rewriting the redirect to HTTPS does not help. A tabledap
`.csv?` query on osmc -- a different host entirely -- fails the same way with the same ~43.5 s
timeout, while `/info` on that host answers instantly.

So this is NOT "the data does not exist". It demonstrably does. Whether the cause is a NOAA-side
outage or a restriction on this network is [UNKNOWN] -- it reproduces across three hosts, which
argues against a single-server outage. Re-run this script; it is cheap, and it prints the exact
fetch recipe for a machine that can reach the data layer.

WHAT EXISTS, ONCE THE DATA LAYER IS REACHABLE  [VERIFIED from metadata]
-----------------------------------------------------------------------
  dataset  pmelTaoDyT -- "TAO/TRITON, RAMA, and PIRATA Buoys, Daily, 1977-present, Temperature"
  coverage 1977-11-03 .. 2026-07-03, which CONTAINS the model window 2025-06-01 .. 2026-06-23
  in box   5 moorings inside 5-30N, 45-105E, 4.3 MB total:
             8.0N  67.0E   t8n67e_dy.cdf     0.47 MB
             8.0N  90.0E   t8n90e_dy.cdf     1.13 MB
            12.0N  90.0E   t12n90e_dy.cdf    1.10 MB
            15.0N  65.0E   t15n65e_dy.cdf    0.14 MB
            15.0N  90.0E   t15n90e_dy.cdf    1.46 MB
  also     pmelTaoDyS (salinity), pmelTaoDyIso (20 C isotherm depth), rama_hourly_temp (OceanSITES)

STILL UNVERIFIED, and it is the question that decides the feature
-----------------------------------------------------------------
Whether those five moorings carry FINITE temperature on days inside the window. RAMA has had long
servicing gaps in the northern Indian Ocean, and a mooring file spanning 1977-2026 says nothing
about 2025-2026 specifically. File size is a hint and not an answer -- t15n65e is 0.14 MB against
t15n90e's 1.46 MB. Do not write a line of validation code until this is measured.

INCOIS OMNI: their own buoy network would be the better source for an INCOIS submission, but
docs/INCOIS_PROBE.md already established that the LAS data-materialization backend is down while
the catalogue answers. This probe checks the remaining categories for an OMNI/RAMA entry.

    python scripts/phase2/probe_buoys.py
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

PMEL = "https://data.pmel.noaa.gov/pmel/erddap"
OSMC = "https://osmc.noaa.gov/erddap"
INCOIS = "https://las.incois.gov.in"
DATASET = "pmelTaoDyT"
BOX = dict(lat=(5.0, 30.0), lon=(45.0, 105.0))
WINDOW = ("2025-06-01", "2026-06-23")
OUT = os.path.join("artifacts", "buoy_probe.json")
UA = {"User-Agent": "OceanEmbed-SIH26066 (INCOIS/MoES student project) probe"}

#: Some NOAA hosts need legacy renegotiation. Kept explicit so it is a documented workaround
#: rather than a mystery flag.
_CTX = ssl.create_default_context()
_CTX.options |= 0x4                                        # OP_LEGACY_SERVER_CONNECT


class _NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url: str, timeout: float, follow: bool = True):
    """-> (seconds, status, location, body). Never raises; a failure is a result here."""
    handlers = [urllib.request.HTTPSHandler(context=_CTX)]
    if not follow:
        handlers.insert(0, _NoFollow())
    op = urllib.request.build_opener(*handlers)
    t = time.time()
    try:
        with op.open(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return time.time() - t, r.status, None, r.read()
    except urllib.error.HTTPError as e:
        return time.time() - t, e.code, e.headers.get("Location"), None
    except Exception as e:
        return time.time() - t, None, str(e)[:110], None


def _report(label, url, timeout=60, follow=True):
    dt, status, loc, body = _get(url, timeout, follow)
    ok = status == 200
    print("  [%s %5.1fs] %-46s %s" % ("ok  " if ok else "FAIL", dt, label,
                                      "" if ok else (loc or "")))
    return dict(label=label, url=url, seconds=round(dt, 1), status=status, note=loc,
                ok=ok), body


def main() -> int:
    print("Moored-buoy probe -- catalogue, then data layer\n")
    checks, bodies = [], {}

    print(" catalogue (metadata only):")
    for label, url in ((f"PMEL /info/{DATASET}", f"{PMEL}/info/{DATASET}/index.json"),
                       (f"PMEL /tabledap/{DATASET}.das", f"{PMEL}/tabledap/{DATASET}.das"),
                       (f"PMEL /files/{DATASET}/", f"{PMEL}/files/{DATASET}/.json"),
                       (f"OSMC /info/{DATASET}", f"{OSMC}/info/{DATASET}/index.json")):
        c, b = _report(label, url)
        checks.append(c)
        bodies[label] = b

    print("\n data layer (anything that returns actual numbers):")
    for label, url, follow in (
            (f"PMEL tabledap .csv query", f"{PMEL}/tabledap/{DATASET}.csv?latitude&distinct()", True),
            (f"OSMC tabledap .csv query", f"{OSMC}/tabledap/{DATASET}.csv?latitude&distinct()", True),
            (f"PMEL /files download (no follow)", f"{PMEL}/files/{DATASET}/t15n90e_dy.cdf", False)):
        c, _ = _report(label, url, timeout=90, follow=follow)
        checks.append(c)

    # Which moorings are in our box, from the file listing -- this works even when downloads do not.
    moorings = []
    listing = bodies.get(f"PMEL /files/{DATASET}/")
    if listing:
        pat = re.compile(r"^t(\d+(?:\.\d+)?)([ns])(\d+(?:\.\d+)?)([ew])_dy\.cdf$")
        for row in json.loads(listing.decode("utf-8", "replace"))["table"]["rows"]:
            m = pat.match(row[0])
            if not m:
                continue
            lat = float(m.group(1)) * (1 if m.group(2) == "n" else -1)
            lon = float(m.group(3)) * (1 if m.group(4) == "e" else -1)
            lon += 360 if lon < 0 else 0
            if BOX["lat"][0] <= lat <= BOX["lat"][1] and BOX["lon"][0] <= lon <= BOX["lon"][1]:
                moorings.append(dict(lat=lat, lon=lon, file=row[0], bytes=int(row[2])))
        moorings.sort(key=lambda d: (d["lat"], d["lon"]))
        print(f"\n moorings inside {BOX['lat']}N {BOX['lon']}E : {len(moorings)}")
        for m in moorings:
            print("   %5.1fN %6.1fE  %-18s %6.2f MB" % (m["lat"], m["lon"], m["file"],
                                                        m["bytes"] / 1e6))

    print("\n INCOIS LAS (their own OMNI network would be the better source):")
    c, b = _report("INCOIS getCategories.do", f"{INCOIS}/las/getCategories.do", timeout=45)
    checks.append(c)
    if b:
        try:
            cats = [x["name"] for x in
                    json.loads(b.decode("cp1252"))["categories"]["category"]]
            hit = [n for n in cats if any(k in n.upper() for k in ("OMNI", "RAMA", "BUOY", "MOOR"))]
            print(f"   {len(cats)} categories; buoy-like: {hit or 'NONE'}")
        except Exception as e:
            print(f"   category list unreadable: {e}")
            cats, hit = [], []
    else:
        cats, hit = [], []
        # A TLS failure here is about THIS machine's trust store, not about INCOIS. Saying
        # "INCOIS is down" on that evidence would be the same error this project keeps naming:
        # reporting an absence as a finding. scripts/phase2/probe_incois_las.py is the maintained
        # probe for that host and reached it on 2026-09-02; run it before concluding anything.
        if checks[-1]["note"] and "CERTIFICATE_VERIFY_FAILED" in str(checks[-1]["note"]):
            print("   ^ a local trust-store failure, NOT evidence about INCOIS. See "
                  "scripts/phase2/probe_incois_las.py")

    catalogue_ok = all(c["ok"] for c in checks[:4])
    data_ok = any(c["ok"] for c in checks[4:7])
    os.makedirs("artifacts", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "what": "reachability of moored-buoy temperature for the model's window",
            "probed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset": DATASET, "window": list(WINDOW), "box": BOX,
            "catalogue_reachable": catalogue_ok, "data_layer_reachable": data_ok,
            "checks": checks, "moorings_in_box": moorings,
            "incois_categories": cats, "incois_buoy_categories": hit,
            "coverage_days_in_window": None,
            "coverage_note": ("NOT MEASURED. Requires the data layer. A file spanning 1977-2026 "
                              "says nothing about 2025-2026: RAMA has had long servicing gaps in "
                              "the northern Indian Ocean."),
        }, f, indent=1)
    print(f"\n wrote {OUT}")

    if catalogue_ok and not data_ok:
        print("\n CATALOGUE REACHABLE, DATA LAYER NOT -- the same shape as docs/INCOIS_PROBE.md.")
        print(" Feature 6 is BLOCKED from this machine. The data exists and covers the window;")
        print(" what is missing is a route to it. Try another network before writing any code.")
        return 1
    if data_ok:
        print("\n DATA LAYER IS REACHABLE. Next: measure how many days inside the window carry a")
        print(" finite temperature at each mooring -- that, not file size, decides feature 6.")
        return 0
    print("\n catalogue unreachable too -- nothing can be concluded about the data.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
