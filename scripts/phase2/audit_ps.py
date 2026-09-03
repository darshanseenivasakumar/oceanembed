"""Audit every SIH26066 requirement against EVIDENCE on this disk. (Unit A / Arjhun.)

WHY THIS IS A SCRIPT AND NOT A TABLE IN A DOC
A requirements matrix written by hand records what someone believed on the day they wrote it. This
project has now had six numbers that were believed and wrong -- a leaky headline, a GLORYS-fed
dashboard, a calibration fitted through the wrong bundle, a 3/3 claim that was 1/3, a coverage mean
hiding an 80% depth, and a 3-D view rendering a model from 2022. Every one looked right.

So each row below opens an artifact and checks it. A row can read PASS, FAIL, or BLOCKED -- and
BLOCKED is a real answer with a reason, not a softer word for FAIL.

The 17 rows are the PS's own clauses, transcribed from the rendered PDF (it has no text layer; see
docs/ARJHUN_EXECUTION_PLAN.md section 0).

Run:  PYTHONPATH=src python scripts/phase2/audit_ps.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base          # noqa: E402
from phase2.tscast_nio import config           # noqa: E402

PS_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


def _shipped() -> dict | None:
    p = base.art("tscast_stage1_metrics.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _bundle_prov(m: dict | None) -> dict | None:
    if not m or not m.get("daily_dir"):
        return None
    f = sorted(glob.glob(os.path.join(m["daily_dir"], "*.npz")))
    if not f:
        return None
    z = np.load(f[0], allow_pickle=True)
    return json.loads(str(z["provenance"])) if "provenance" in z.files else None


def audit() -> list[tuple[int, str, str, str]]:
    m = _shipped()
    prov = _bundle_prov(m)
    rows: list[tuple[int, str, str, str]] = []

    def row(n, name, status, ev):
        rows.append((n, name, status, ev))

    if not m:
        row(0, "shipped model artifact", FAIL, "artifacts/tscast_stage1_metrics.json absent")
        return rows

    mm, o = m["metrics"], m["metrics"]["overall"]
    chans = [str(c) for c in m.get("channels", [])]

    # 1 -- preprocessing / harmonisation of multi-source satellite and ocean datasets
    n_products = len({v.get("product") for v in (prov or {}).get("channels", {}).values()
                      if v.get("product")})
    row(1, "preprocessing + harmonisation, multi-source",
        PASS if n_products >= 4 else FAIL,
        f"{len(chans)} channels harmonised from {n_products} distinct products into "
        f"{m['daily_dir']}")

    # 2 -- 0.25 deg
    ok2 = base.REGION["step"] == 0.25 and len(base.LAT) == 100 and len(base.LON) == 240
    row(2, "spatial resolution 0.25 deg", PASS if ok2 else FAIL,
        f"REGION step {base.REGION['step']}, grid {len(base.LAT)}x{len(base.LON)}, "
        f"{base.REGION['lat_min']}-{base.REGION['lat_max']}N {base.REGION['lon_min']}-"
        f"{base.REGION['lon_max']}E")

    # 3 -- daily.
    # Counts timestamps across EVERY year file. This first read `n_days` out of the first file's
    # provenance and reported 214 -- that is 2025's count, not the bundle's, and the row failed on
    # a complete dataset. A per-file field read as a whole-bundle total is the same mistake as a
    # coverage mean read as a per-depth guarantee.
    times, gaps = [], None
    for f in sorted(glob.glob(os.path.join(m["daily_dir"], "*.npz"))):
        times.append(np.load(f, allow_pickle=True)["times"])
    if times:
        t = np.sort(np.concatenate(times).astype("datetime64[D]"))
        gaps = int((np.diff(t).astype("timedelta64[D]").astype(int) != 1).sum())
    n = len(t) if times else 0
    row(3, "temporal resolution daily", PASS if (n == 388 and gaps == 0) else FAIL,
        f"{n} daily steps {t.min()}..{t.max()}, {gaps} gaps" if times else "no bundle files")

    # 4-8 -- the five input variable groups
    want = {4: ("SST", ["sst"]), 5: ("SSS", ["sss"]), 6: ("SSH / SLA", ["ssh"]),
            7: ("surface currents U,V", ["u", "v"]), 8: ("surface winds U,V", ["wu", "wv"])}
    for n, (label, keys) in want.items():
        present = all(k in chans for k in keys)
        cls = {k: (prov or {}).get("channels", {}).get(k, {}).get("data_class", "?") for k in keys}
        prod = (prov or {}).get("channels", {}).get(keys[0], {}).get("product", "?")
        obs = all("SATELLITE" in str(v).upper() for v in cls.values())
        row(n, f"input: {label}", PASS if (present and obs) else FAIL,
            f"{'/'.join(keys)} present, class {sorted(set(cls.values()))}, {prod[:46]}")

    # 9 -- compact satellite embedding via a DL architecture
    bake = base.art("architecture_feasibility.json")
    cands = json.load(open(bake, encoding="utf-8")).get("results", {}) if os.path.exists(bake) else {}
    row(9, "compact satellite embedding via DL",
        PASS if (m.get("encoder") and m.get("latent") and m.get("input_source") == "satellite") else FAIL,
        f"{m.get('encoder')} -> {m.get('latent')}-dim latent, chosen over {len(cands)} candidates "
        f"{sorted(cands) if cands else ''}, input_source={m.get('input_source')}")

    # 10 -- reconstruction surface state -> temperature profile
    row(10, "reconstruction: surface -> profile",
        PASS if len(mm["depths_m"]) == 15 else FAIL,
        f"one forward pass returns {len(mm['depths_m'])} depths per (lat, lon, date)")

    # 11 -- the exact 15 standard depths
    row(11, "15 standard depths, exactly",
        PASS if list(config.DEPTHS) == PS_DEPTHS else FAIL,
        f"config.DEPTHS == the PS list: {list(config.DEPTHS) == PS_DEPTHS}")

    # 12-14 -- the named skill metrics
    for n, key, label in ((12, "rmse", "RMSE"), (13, "correlation", "correlation"),
                          (14, "bias", "bias")):
        per = mm.get(key, [])
        ok = len(per) == 15 and all(v is not None for v in per)
        row(n, f"evaluate: {label}", PASS if ok else FAIL,
            f"{label} at {sum(v is not None for v in per)}/15 depths, overall {o.get(key):+.4f}"
            if ok else f"{label} incomplete")

    # 15 -- GLORYS as the training target
    tgt = (prov or {}).get("target_source", "")
    row(15, "training target: GLORYS reanalysis", PASS if "GLORYS" in tgt else FAIL, tgt[:70])

    # 16 -- independent validation: INCOIS LAS gridded ARGO
    probe = os.path.join("docs", "INCOIS_PROBE.md")
    # BLOCKED, and the reason differs BY MACHINE -- which is stated rather than flattened into one
    # story. Unit B's probe: catalogue answers in 0.19 s and lists the right gridded products, but
    # every retrieval route fails (dodsC hangs, ftds_url 404s, ProductServer errors). This machine
    # 2026-09-02: the TLS handshake succeeds (TLSv1.3, host UP) and certificate verification fails
    # on an incomplete chain, so even the catalogue is unreachable here; plain HTTP is firewalled.
    # Two different failures. Neither of them is "INCOIS is down".
    row(16, "independent validation: INCOIS LAS gridded ARGO", BLOCKED,
        f"{m.get('argo_profiles')} independent argopy float profiles used, deviation documented"
        f"{' in docs/INCOIS_PROBE.md' if os.path.exists(probe) else ''}. Host is UP; retrieval "
        f"blocked -- data layer on Unit B's machine, TLS chain on this one. "
        f"Re-probe: scripts/phase2/probe_incois_las.py")

    # 17 -- PoC over the Bay of Bengal / Arabian Sea
    bas = base.art("basin_3seed.json")
    b = json.load(open(bas, encoding="utf-8")) if os.path.exists(bas) else {}
    pen = b.get("penalty_by_basin", {})
    row(17, "PoC over Bay of Bengal / Arabian Sea",
        PASS if pen else FAIL,
        f"per-basin skill over 3 seeds: Arabian {np.mean(pen['arabian_sea']):+.4f}, "
        f"Bay of Bengal {np.mean(pen['bay_of_bengal']):+.4f} (satellite-minus-GLORYS RMSE)"
        if pen else "no per-basin metrics")
    return rows


def main() -> None:
    rows = audit()
    print("=" * 96)
    print("SIH26066 REQUIREMENTS AUDIT -- every row checked against an artifact on this disk")
    print("=" * 96)
    for n, name, status, ev in rows:
        mark = {PASS: "ok  ", FAIL: "FAIL", BLOCKED: "BLKD"}[status]
        print(f"  {mark} {n:>2}. {name}")
        print(f"          {ev}")
    p = sum(1 for r in rows if r[2] == PASS)
    f = sum(1 for r in rows if r[2] == FAIL)
    b = sum(1 for r in rows if r[2] == BLOCKED)
    print()
    print(f"  {p} PASS   {f} FAIL   {b} BLOCKED   of {len(rows)}")
    if b:
        print("\n  BLOCKED is not FAIL and not PASS. It means the requirement is understood, the")
        print("  work to meet it is done on our side, and an external dependency is unavailable.")
        print("  It must be stated to the jury as exactly that, never quietly counted either way.")
    raise SystemExit(1 if f else 0)


if __name__ == "__main__":
    main()
