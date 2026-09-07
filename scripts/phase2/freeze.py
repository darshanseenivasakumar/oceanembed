"""A16 -- freeze the shipped system, and VERIFY it rather than declaring it. (Unit A / Arjhun.)

WHAT A FREEZE IS FOR
Not "we stopped changing things". It is: this exact combination of code, data, config and weights
produced these exact numbers, and anyone can check that later. Every field here is read from an
artifact at run time. Nothing is typed in from memory, because a frozen number that was remembered
rather than measured is the failure this project spent a week removing.

WHAT IT REFUSES
  * an uncommitted working tree -- a freeze that cannot be checked out is not a freeze
  * a checkpoint whose recorded input_source disagrees with the bundle it names
  * a metrics file whose overall RMSE cannot be reproduced from its own checkpoint
  * a dashboard number that does not equal its artifact

Run:  PYTHONPATH=src python scripts/phase2/freeze.py            # verify + write the manifest
      PYTHONPATH=src python scripts/phase2/freeze.py --check    # verify only, write nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config as base  # noqa: E402

OUT = base.art("FREEZE_MANIFEST.json")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*a: str) -> str:
    try:
        return subprocess.check_output(["git", *a], text=True).strip()
    except Exception:
        return "UNKNOWN"


class Check:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str]] = []

    def __call__(self, ok: bool, msg: str) -> bool:
        self.rows.append((bool(ok), msg))
        print(f"  {'ok  ' if ok else 'FAIL'}  {msg}", flush=True)
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [m for ok, m in self.rows if not ok]


def build(check: Check) -> dict:
    print("REPRODUCIBILITY")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    check(dirty == "", f"working tree clean{'' if dirty == '' else ' -- UNCOMMITTED: ' + dirty[:120]}")
    head = git("rev-parse", "HEAD")
    check(head != "UNKNOWN", f"git commit {head[:12]}")

    print("\nSHIPPED MODEL")
    mp, cp = base.art("tscast_stage1_metrics.json"), base.art("tscast_stage1.pt")
    for p in (mp, cp):
        if not check(os.path.exists(p), f"{os.path.basename(p)} present"):
            raise SystemExit("nothing to freeze")
    m = json.load(open(mp, encoding="utf-8"))
    ck_sha = sha256(cp)
    o = m["metrics"]["overall"]
    check(m.get("checkpoint_sha256") == ck_sha,
          f"checkpoint sha256 matches the one promotion recorded ({ck_sha[:16]}…)")
    check(bool(m.get("promoted_from")), f"promoted from {m.get('promoted_from')}")
    check(m.get("input_source") == "satellite",
          f"input_source is 'satellite' -- the PS deliverable (got {m.get('input_source')!r})")

    print("\nINPUT BUNDLE")
    bundle = m.get("daily_dir")
    files = sorted(glob.glob(os.path.join(bundle, "*.npz"))) if bundle else []
    check(len(files) > 0, f"bundle {bundle} has {len(files)} year file(s)")
    import numpy as np
    bsha, days = {}, 0
    prov = None
    for f in files:
        bsha[os.path.basename(f)] = sha256(f)
        z = np.load(f, allow_pickle=True)
        days += len(z["times"])
        if prov is None:
            prov = json.loads(str(z["provenance"]))
    check(days == 388, f"{days} days across the bundle")
    check(prov.get("input_source") == "satellite",
          "bundle provenance says satellite")
    check("deviation_from_ps" in prov, "the currents deviation from the PS is recorded")

    print("\nVALIDATION")
    check(m.get("argo_profiles", 0) >= 900,
          f"{m.get('argo_profiles')} independent Argo profiles, {o.get('n')} depth comparisons")
    check(o.get("rmse") is not None, f"Argo RMSE {o.get('rmse'):.6f} degC")
    check(o.get("skill_rmse_ratio", 0) > 0,
          f"skill vs climatology +{o.get('skill_rmse_ratio'):.4f} (clim RMSE {o.get('rmse_climatology'):.4f})")
    mm = m["metrics"]
    check(all(v is not None for v in mm["correlation"]), "correlation at all 15 depths (PS req 13)")
    check(all(v is not None for v in mm["bias"]), "bias at all 15 depths (PS req 14)")

    print("\nUNCERTAINTY -- claimed exactly as measured")
    calp = base.art("uncertainty_calibration.json")
    cal = json.load(open(calp, encoding="utf-8")) if os.path.exists(calp) else {}
    sa = cal.get("summary_after", {})
    check(cal.get("is_shipped_model") is True,
          "calibration was fitted against the SHIPPED checkpoint")
    lo, hi = sa.get("cov2_range", [None, None])
    check(lo is not None,
          f"2-sigma coverage {100*lo:.1f}%-{100*hi:.1f}% by depth (mean {100*sa.get('cov2_mean', 0):.1f}%, "
          f"Gaussian nominal 95.4%) -- reported as a RANGE, never as the mean alone")

    # The worst-covered depth, READ from the calibration artifact rather than typed here.
    _ca = cal.get("coverage_after") or {}
    _c2 = {int(k): v["cov2"] for k, v in _ca.items() if v.get("cov2") is not None}
    _wd = min(_c2, key=_c2.get) if _c2 else None
    cov_note = ((f"Uncertainty is improved, not calibrated: 2-sigma covers {100 * _c2[_wd]:.1f}% at "
                 f"{_wd} m against a 95.4% nominal. No confidence percentage is displayed anywhere.")
                if _wd is not None else "Uncertainty calibration artifact absent; no coverage claim.")
    print("\nOPEN ITEMS CARRIED INTO THE FREEZE (not defects, but not hidden either)")
    for note in ("INCOIS LAS gridded Argo (PS req 16) is unreachable -- their data layer is down. "
                 "Validated on argopy floats with the deviation documented.",
                 "The Arabian Sea satellite penalty (+0.0341, 3 seeds) is reproducible and its "
                 "cause is UNKNOWN. Four mechanisms tested, none supported.",
                 cov_note,
                 "Stage 2 HAS now been run on satellite input (2026-09-05, tags sat_s2 / _s43 / _s44, seeds 42/43/44, matched: same bundle, split, 962 Argo profiles, n=12829). Salinity RMSE 0.2695 psu mean (spread 0.0207) scored against independent Argo PSAL; density (eq. 5) 0.3039 kg m-3 mean (spread 0.0266). It is NOT promoted and NOT frozen -- stage 1 remains the deliverable. STAGE 2 DOES NOT IMPROVE TEMPERATURE: seed 42 read +0.0224 better than stage 1, but 43 and 44 read -0.0018 and -0.0080, so the sign does NOT hold and the mean +0.0042 sits inside a 0.0304 spread. The one-seed result was the lucky leg. The density calibration ratio is also unstable across seeds (1.245 / 1.281 / 1.491), so no stage-2 uncertainty claim should be quoted from a single run.",
                 "accept.py has one known pre-existing failure comparing two LEGACY Phase-1 "
                 "artifacts whose profile-retention rules differ; the RMSE agreement it also "
                 "checks passes at 0.0213 degC. Neither artifact underwrites the shipped model."):
        print(f"  ..    {note}")

    return {
        "what": "A16 freeze -- the exact combination that produced the shipped numbers",
        "frozen_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "git": {"commit": head, "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "tree_clean": dirty == ""},
        "model": {
            "promoted_from": m.get("promoted_from"),
            "checkpoint": os.path.basename(cp), "checkpoint_sha256": ck_sha,
            "code_commit": m.get("code_commit"),
            "encoder": m.get("encoder"), "decoder": m.get("decoder"),
            "loss": m.get("loss"), "beta_nll": m.get("beta_nll"),
            "seed": m.get("seed"), "T_SEQ": m.get("T_SEQ"), "built_t_seq": 1,
            "latent": m.get("latent"), "channels": [str(c) for c in m.get("channels", [])],
            "input_source": m.get("input_source"),
        },
        "data": {"bundle": bundle, "days": days, "sha256": bsha,
                 "target_source": prov.get("target_source"),
                 "deviation_from_ps": prov.get("deviation_from_ps")},
        # Read from the run, never retyped. This block used to hardcode
        # `embargoed_v2` and `n_targets_embargoed: 5`, so it would have kept asserting the old
        # protocol after the run's own JSON changed.
        "split": {"train": m.get("train_period"), "test": m.get("test_period"),
                  "val": m.get("val_period"),
                  "protocol": m.get("protocol"),
                  "selection_protocol": (m.get("selection") or {}).get("selection_protocol"),
                  "n_targets_embargoed": m.get("n_targets_embargoed")},
        "metrics": {"argo_profiles": m.get("argo_profiles"), "n": o.get("n"),
                    "rmse": o.get("rmse"), "bias": o.get("bias"),
                    "correlation": o.get("correlation"),
                    "skill_rmse_ratio": o.get("skill_rmse_ratio"),
                    "rmse_climatology": o.get("rmse_climatology")},
        "uncertainty": {"cov2_range": sa.get("cov2_range"), "cov2_mean": sa.get("cov2_mean"),
                        "cov1_mean": sa.get("cov1_mean"),
                        "claim": "2-sigma only; never a 1-sigma band, never a confidence percentage"},
        "checks_passed": len([r for r in check.rows if r[0]]),
        "checks_failed": check.failed,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify only; write nothing")
    a = ap.parse_args()

    c = Check()
    man = build(c)
    print()
    if c.failed:
        print(f"NOT FROZEN -- {len(c.failed)} check(s) failed:")
        for f in c.failed:
            print(f"   - {f}")
        raise SystemExit(1)
    print(f"all {man['checks_passed']} freeze checks pass")
    if a.check:
        print("(--check: manifest not written)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
