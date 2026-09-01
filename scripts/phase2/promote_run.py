"""Promote one tagged training run to the canonical artifact name. (Unit A / Arjhun.)

THE PROBLEM THIS FIXES
Training writes TAGGED files -- `tscast_stage1_withUV_s42.pt` and its metrics JSON -- because
several experiments must coexist without clobbering each other. But every CONSUMER expects the
unsuffixed canonical name:

    app/phase2/tscast_page.py::_newest_run      tscast_stage1_metrics.json + tscast_stage1.pt
    src/phase2/tscast_nio/output.py::ERROR_SOURCES
    scripts/phase2/record_tseq_ablation.py
    scripts/phase2/accept.py::check_v2_ui

Nothing bridged the two, so the dashboard rendered only its error banner and `check_v2_ui`
returned pass-with-a-skip. Producer and consumer had drifted apart and the acceptance gate was
green the whole time.

THE RULE
Tagged files are EXPERIMENTS. The unsuffixed name is THE SHIPPED MODEL, and it exists only
because someone deliberately promoted a run. Promotion is recorded in the metrics JSON
(`promoted_from`, `promoted_at`, `checkpoint_sha256`) so a served prediction can be tied back to
the experiment that produced it -- which `docs/phase2/tscast_output_schema.md:117-129` requires
and nothing previously supplied.

THE GUARD
A run whose code commit predates the A1 temporal-embargo fix is INVALID (see
artifacts/INVALID_PRE_EMBARGO.md) and is refused. Promoting one would put a leaky number back on
the dashboard, which is exactly the failure this project has already had once.

Run:  python scripts/phase2/promote_run.py --tag embargo_withUV_s42
      python scripts/phase2/promote_run.py --list
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from oceanembed import config  # noqa: E402

# The commit that fixed the temporal leak in dataset._window(). Any run built from code that does
# NOT contain this commit read test-period surface fields on 5 of 304 train days.
EMBARGO_COMMIT = "1d3c135"
STAGES = ("stage1", "stage2")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _contains_embargo_fix(commit: str | None) -> tuple[bool, str]:
    """True if `commit` has the A1 fix in its history. Fail closed on anything unclear."""
    if not commit:
        return False, "the run records no code_commit, so it cannot be shown to contain the fix"
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", EMBARGO_COMMIT, commit],
                       check=True, capture_output=True)
        return True, f"{commit} contains {EMBARGO_COMMIT}"
    except subprocess.CalledProcessError:
        return False, (f"{commit} does NOT contain the embargo fix {EMBARGO_COMMIT}: this run was "
                       f"trained by the leaky sampler")
    except FileNotFoundError:
        return False, "git is not available, so the run's lineage cannot be checked"


def available(stage: str = "stage1") -> list[str]:
    """Tags with BOTH a checkpoint and a metrics file present."""
    d, pre = config.ARTIFACTS, f"tscast_{stage}_"
    tags = []
    for f in sorted(os.listdir(d)):
        if f.startswith(pre) and f.endswith("_metrics.json"):
            tag = f[len(pre):-len("_metrics.json")]
            if os.path.exists(os.path.join(d, f"{pre}{tag}.pt")):
                tags.append(tag)
    return tags


def promote(tag: str, stage: str = "stage1", force: bool = False) -> None:
    ck_src = config.art(f"tscast_{stage}_{tag}.pt")
    m_src = config.art(f"tscast_{stage}_{tag}_metrics.json")
    for p in (ck_src, m_src):
        if not os.path.exists(p):
            raise SystemExit(f"refusing: {p} does not exist. Available tags for {stage}: "
                             f"{available(stage) or '(none)'}")

    with open(m_src, encoding="utf-8") as f:
        m = json.load(f)

    ok, why = _contains_embargo_fix(m.get("code_commit"))
    if not ok and not force:
        raise SystemExit(
            f"REFUSING to promote '{tag}': {why}.\n"
            f"Promoting it would put a leaky number back on the dashboard. See "
            f"artifacts/INVALID_PRE_EMBARGO.md.\n"
            f"If you genuinely intend to ship a pre-embargo run, pass --force and say so in the "
            f"commit message.")

    ck_dst = config.art(f"tscast_{stage}.pt")
    m_dst = config.art(f"tscast_{stage}_metrics.json")

    shutil.copy2(ck_src, ck_dst)
    m["promoted_from"] = tag
    m["promoted_at"] = dt.datetime.now().replace(microsecond=0).isoformat()
    m["checkpoint_sha256"] = _sha256(ck_dst)
    m["promotion_note"] = (
        "This is the SHIPPED model. It is a copy of the tagged experiment named in "
        "`promoted_from`, which remains on disk unchanged. Retraining does NOT update this file: "
        "promote again to ship a new run.")
    if not ok:
        m["promotion_warning"] = f"FORCED despite: {why}"
    with open(m_dst, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)

    rmse = m.get("metrics", {}).get("overall", {}).get("rmse")
    print(f"promoted {tag} -> canonical tscast_{stage}")
    print(f"  lineage : {why}")
    print(f"  rmse    : {rmse}")
    print(f"  sha256  : {m['checkpoint_sha256'][:16]}...")
    print(f"  wrote   : {ck_dst}")
    print(f"            {m_dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="tag to promote, e.g. embargo_withUV_s42")
    ap.add_argument("--stage", default="stage1", choices=STAGES)
    ap.add_argument("--list", action="store_true", help="show promotable tags and exit")
    ap.add_argument("--force", action="store_true",
                    help="promote even a run that predates the embargo fix. Almost never right.")
    a = ap.parse_args()

    if a.list or not a.tag:
        for stage in STAGES:
            tags = available(stage)
            print(f"{stage}: {', '.join(tags) if tags else '(none)'}")
        if not a.tag:
            raise SystemExit(0 if a.list else "give --tag")
        return
    promote(a.tag, a.stage, a.force)


if __name__ == "__main__":
    main()
