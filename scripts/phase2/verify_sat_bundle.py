"""Validate the satellite bundle (A5) and prove GLORYS cannot masquerade as it (A6).

WHY A GUARD AND NOT A LABEL
`inference.py` used to report `"input_source": "glorys"` as a hardcoded string literal. A literal
is not evidence: it would have kept saying whatever it said no matter what was in the tensor. The
contract is blunt about this -- do not accept `input_source = satellite` as sufficient; the lineage
must be traceable.

So this checks TWO independent things, and both must hold:

  PROVENANCE  the bundle says it is satellite, names a real product per channel, and does not
              name a reanalysis product anywhere in its input channels
  DATA        the satellite channels MEASURABLY DIFFER from the GLORYS bundle on the same days

Either alone is defeatable. Provenance alone is a string. Data-difference alone would pass for any
two datasets. Together they say: this is satellite-sourced, and it is not a copy of the target.

WIND IS THE CONTROL, NOT AN EXCEPTION
`wu, wv` are carried through from the same observational product in both bundles, so they SHOULD be
identical. That makes them a positive control: if wind ever differs, the pipeline is corrupting a
passthrough channel, and if a *satellite* channel matches GLORYS exactly, it was substituted.

Run:  PYTHONPATH=src python scripts/phase2/verify_sat_bundle.py
      PYTHONPATH=src python scripts/phase2/verify_sat_bundle.py --negative-test
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base          # noqa: E402
from phase2.tscast_nio import config           # noqa: E402

SAT_DIR = os.path.join(base.DATA_PROCESSED, "daily_sat", "v001")
GLORYS_DIR = os.path.join(base.DATA_PROCESSED, "daily")

# A satellite channel that matches GLORYS this closely on a whole year is not an independent
# measurement of the same ocean -- it is the same array. Chosen well below the smallest real
# difference measured (currents, mean |diff| 0.107 m/s) and far above float noise.
IDENTICAL_TOL = 1e-6
SAT_CHANNELS = ("sst", "sss", "ssh", "u", "v")
PASSTHROUGH = ("wu", "wv")
REANALYSIS_WORDS = ("glorys", "reanalysis", "cmems_mod_glo_phy")


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str]] = []

    def check(self, ok: bool, msg: str) -> None:
        self.rows.append((bool(ok), msg))
        print(f"  {'ok  ' if ok else 'FAIL'}  {msg}", flush=True)

    @property
    def failed(self) -> list[str]:
        return [m for ok, m in self.rows if not ok]


def _years(d: str) -> list[str]:
    return sorted(glob.glob(os.path.join(d, "*.npz")))


def check_provenance(r: Result) -> None:
    print("\nPROVENANCE")
    for path in _years(SAT_DIR):
        s = np.load(path, allow_pickle=True)
        p = json.loads(str(s["provenance"]))
        tag = os.path.basename(path)

        r.check(p.get("input_source") == "satellite",
                f"{tag}: input_source is 'satellite' (got {p.get('input_source')!r})")

        chans = p.get("channels", {})
        r.check(set(chans) == set(config.CHANNELS),
                f"{tag}: provenance covers all {len(config.CHANNELS)} contract channels")

        # The INPUT channels must not BE a reanalysis. Check the STRUCTURED fields -- `product`
        # and `data_class` -- never the serialised dict.
        #
        # This first matched substrings against json.dumps() of the whole channel entry, prose and
        # all, and failed all five channels. The "offending" text was legitimate explanation:
        # "GLORYS land mask" (which is the correct mask source, since satellite SST contains inland
        # water) and "adt vs GLORYS zos" (the datum caveat). It flagged a bundle for DESCRIBING the
        # reanalysis it is careful not to be. Same mistake as the earlier `"analysis" in
        # "reanalysis"` substring bug -- a guard that reads documentation as evidence punishes
        # writing any, which is exactly backwards.
        bad = []
        for c in SAT_CHANNELS:
            meta = chans.get(c, {})
            fields = f"{meta.get('product', '')} {meta.get('data_class', '')}".lower()
            if any(w in fields for w in REANALYSIS_WORDS):
                bad.append(c)
        r.check(not bad, f"{tag}: no satellite input channel IS a reanalysis product "
                         f"{'(offenders: ' + ', '.join(bad) + ')' if bad else ''}")

        # `cmems_obs-mob_...` (observation) vs `cmems_mod_glo_phy...` (model) differ by one word,
        # and that word is the whole distinction. Assert the positive form too, so a channel
        # cannot pass merely by not matching a blocklist.
        classes = {c: chans.get(c, {}).get("data_class", "") for c in SAT_CHANNELS}
        wrong = {c: v for c, v in classes.items() if "SATELLITE" not in v.upper()}
        r.check(not wrong, f"{tag}: every satellite input channel is classed SATELLITE* "
                           f"{'(got ' + str(wrong) + ')' if wrong else ''}")

        r.check("GLORYS" in p.get("target_source", ""),
                f"{tag}: target_source is still GLORYS -- the PS's named training target")

        for c in SAT_CHANNELS:
            meta = chans.get(c, {})
            r.check(bool(meta.get("product")) and bool(meta.get("data_class")),
                    f"{tag}: {c} names a product and a data class")

        r.check("deviation_from_ps" in p,
                f"{tag}: the currents substitution is recorded as a deviation")


def check_differs_from_glorys(r: Result, substitute: str | None = None) -> None:
    """The data half. `substitute` injects a GLORYS channel to prove the guard catches it."""
    print("\nDATA LINEAGE" + (f"  [NEGATIVE TEST: {substitute} replaced with GLORYS]"
                              if substitute else ""))
    for path in _years(SAT_DIR):
        year = os.path.basename(path)[:4]
        gpath = os.path.join(GLORYS_DIR, f"{year}.npz")
        if not os.path.exists(gpath):
            r.check(False, f"{year}: GLORYS bundle absent, cannot compare")
            continue
        s, g = np.load(path, allow_pickle=True), np.load(gpath, allow_pickle=True)
        sd = [str(t).replace("-", "")[:8] for t in s["times"]]
        gd = {str(t).replace("-", "")[:8]: i for i, t in enumerate(g["times"])}
        gi = [gd[d] for d in sd if d in gd]
        si = [k for k, d in enumerate(sd) if d in gd]
        sc, gc = list(s["channels"]), list(g["channels"])
        S, G = s["surface"][si], np.asarray(g["surface"])[gi]

        for c in SAT_CHANNELS:
            a = S[..., sc.index(c)]
            b = G[..., gc.index(c)]
            if substitute == c:
                a = b.copy()                      # the substitution the guard must catch
            d = np.abs(a - b)
            d = d[np.isfinite(d)]
            mean = float(d.mean()) if d.size else 0.0
            r.check(mean > IDENTICAL_TOL,
                    f"{year} {c}: differs from GLORYS (mean |diff| {mean:.6f})")

        for c in PASSTHROUGH:
            a, b = S[..., sc.index(c)], G[..., gc.index(c)]
            d = np.abs(a - b)
            d = d[np.isfinite(d)]
            mean = float(d.mean()) if d.size else 0.0
            r.check(mean <= IDENTICAL_TOL,
                    f"{year} {c}: matches GLORYS as expected (passthrough control, "
                    f"mean |diff| {mean:.6f})")


def check_shapes_and_ranges(r: Result) -> None:
    print("\nSHAPE / CONTRACT")
    for path in _years(SAT_DIR):
        s = np.load(path, allow_pickle=True)
        tag = os.path.basename(path)
        n = len(s["times"])
        r.check(s["surface"].shape == (n, len(base.LAT), len(base.LON), len(config.CHANNELS)),
                f"{tag}: surface is {s['surface'].shape}")
        r.check(s["temp"].shape == (n, len(base.LAT), len(base.LON), config.N_DEPTHS),
                f"{tag}: temp is {s['temp'].shape}")
        r.check(list(s["channels"]) == config.CHANNELS,
                f"{tag}: channel order matches the frozen contract")
        t = np.asarray(s["times"], dtype="datetime64[D]")
        r.check(bool(np.all(np.diff(t) > np.timedelta64(0, "D"))),
                f"{tag}: dates strictly increasing, no duplicates")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--negative-test", action="store_true",
                    help="inject GLORYS into each satellite channel in turn; the guard MUST fail "
                         "every time. Proves the guard can detect the thing it exists to detect.")
    a = ap.parse_args()

    if not _years(SAT_DIR):
        print(f"no bundle in {SAT_DIR} -- build it first with "
              f"`python -m phase2.tscast_nio.sat_daily_pipeline`")
        return 1

    if a.negative_test:
        print("NEGATIVE TEST -- each run below MUST report a failure. A clean pass here would\n"
              "mean the guard cannot see a substituted channel, which is worse than no guard.")
        all_caught = True
        for c in SAT_CHANNELS:
            r = Result()
            check_differs_from_glorys(r, substitute=c)
            caught = any(f"{c}: differs" in m for m in r.failed)
            print(f"  --> substituting {c}: {'CAUGHT' if caught else 'NOT CAUGHT'}\n")
            all_caught &= caught
        print("negative test:", "PASS -- every substitution was caught" if all_caught
              else "FAIL -- a substituted channel slipped through")
        return 0 if all_caught else 1

    r = Result()
    check_shapes_and_ranges(r)
    check_provenance(r)
    check_differs_from_glorys(r)
    print()
    if r.failed:
        print(f"FAILED {len(r.failed)} of {len(r.rows)} checks:")
        for m in r.failed:
            print(f"   - {m}")
        return 1
    print(f"all {len(r.rows)} checks pass -- the bundle is satellite-sourced and is not a copy "
          f"of the GLORYS target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
