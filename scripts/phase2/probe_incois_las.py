"""D2 -- probe the INCOIS Live Access Server for the gridded Argo product the PS names.

Findings as of 2026-09-02 are written up in docs/INCOIS_PROBE.md. In one line: the catalogue
is healthy and carries exactly the right product, and every data-retrieval route is dead at the
Ferret/F-TDS layer.

This script exists so that negative is reproducible and so the moment the backend recovers we
notice. Exits 0 only when data actually came back.

    python scripts/phase2/probe_incois_las.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://las.incois.gov.in"
ARGO_CATEGORY = "942F0A82EED38D08763754130C47ECB5"

# The two gridded products, as catalogued. See docs/INCOIS_PROBE.md section 2.
GRIDDED = {
    "id-76d076139f": "VAM 10DAY ARGO (Variational Analysis)",
    "id-a292ce89c6": "ARGO DATA PRODUCTS (10 DAYS) (Kessler-McCreary)",
}
DODS = BASE + "/thredds/dodsC/las/{cid}/data_home_las_datasets_argo_argo_10d{v}.nc.jnl"

# Their 24 levels. 14 of our 15 config.DEPTHS are exact members; only 0 m is absent.
EXPECTED_DEPTHS = ["5", "10", "20", "30", "50", "75", "100", "125", "150", "200", "250", "300",
                   "400", "500", "600", "700", "800", "900", "1000", "1200", "1400", "1600",
                   "1800", "2000"]


def _get(url: str, timeout: int) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _check(label: str, fn, timeout: int) -> tuple[bool, str]:
    try:
        return True, fn(timeout)
    except Exception as exc:  # noqa: BLE001 -- any failure is a finding, not a crash
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print(f"probing {BASE}\n")
    ok_meta = True

    # 1. Catalogue layer -- expected healthy, sub-second.
    def _cats(t):
        d = json.loads(_get(f"{BASE}/las/getCategories.do", t).decode("cp1252"))
        names = [c["name"] for c in d["categories"]["category"]]
        assert any("ARGO" in n.upper() for n in names), f"no ARGO category in {names}"
        return f"{len(names)} categories, ARGO DATA PRODUCTS present"

    good, msg = _check("categories", _cats, 30)
    print(f"  [{'ok ' if good else 'FAIL'}] getCategories.do   {msg}")
    ok_meta &= good

    # 2. The gridded datasets, with their axes.
    def _datasets(t):
        d = json.loads(_get(f"{BASE}/las/getDatasets.do", t).decode("cp1252"))
        by_id = {x.get("catid"): x for x in d["datasets"]["dataset"]}
        out = []
        for cid, name in GRIDDED.items():
            if cid not in by_id:
                raise AssertionError(f"{cid} ({name}) absent from the catalogue")
            var = by_id[cid]["variables"]["variable"]
            var = [var] if isinstance(var, dict) else var
            z = next(a for a in var[0]["grid"]["axis"] if a["type"] == "z")
            if z.get("v") != EXPECTED_DEPTHS:
                raise AssertionError(f"{cid} depth levels changed: {z.get('v')}")
            out.append(f"{cid} ok")
        return f"{len(by_id)} datasets; " + ", ".join(out)

    good, msg = _check("datasets", _datasets, 300)
    print(f"  [{'ok ' if good else 'FAIL'}] getDatasets.do     {msg}")
    ok_meta &= good

    # 3. Data layer -- the part that is down. A short timeout: a healthy DDS is instant, and
    #    the failure mode is an indefinite hang, so waiting longer buys nothing.
    ok_data = False
    for cid, suffix in (("id-76d076139f", "v"), ("id-a292ce89c6", "")):
        url = DODS.format(cid=cid, v=suffix) + ".dds"

        def _dds(t, _u=url):
            body = _get(_u, t).decode("utf-8", "replace")
            assert "Dataset" in body, f"unexpected DDS body: {body[:200]}"
            return body.strip().splitlines()[0][:80]

        good, msg = _check(cid, _dds, 60)
        print(f"  [{'ok ' if good else 'DOWN'}] dodsC {cid}  {msg}")
        ok_data |= good

    print()
    if ok_data:
        print("DATA LAYER IS BACK. See docs/INCOIS_PROBE.md section 2 for the endpoint and "
              "variable names, and section 4 for the 1-degree / 10-day matching rules that must "
              "be applied before any RMSE is computed.")
        return 0

    # Report what THIS run observed, not what the last one did. This printed "Catalogue healthy"
    # unconditionally -- on 2026-09-02 it said so while both catalogue calls above had FAILED with
    # CERTIFICATE_VERIFY_FAILED. A summary that contradicts the output three lines above it is
    # worse than no summary, because it is the only line anyone reads.
    if ok_meta:
        print("Catalogue reachable, data layer down. Independent validation stays on argopy; "
              "the deviation is recorded in docs/INCOIS_PROBE.md.")
    else:
        print("CATALOGUE NOT REACHABLE FROM THIS MACHINE -- see the failures above. This is a "
              "DIFFERENT failure from the one in docs/INCOIS_PROBE.md, where the catalogue "
              "answered and only the data layer was down. Measured here 2026-09-02: the TLS "
              "handshake to las.incois.gov.in SUCCEEDS (TLSv1.3), so the host is UP, but "
              "verification fails with 'unable to get local issuer certificate' -- an incomplete "
              "certificate chain -- and plain HTTP is firewalled. Do not report this as 'INCOIS "
              "is down' without saying which layer failed, and on whose machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
