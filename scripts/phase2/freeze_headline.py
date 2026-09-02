"""Freeze the v2 headline checkpoints and give them a checksum identity.

    python scripts/phase2/freeze_headline.py           # freeze + write the manifest
    python scripts/phase2/freeze_headline.py --verify   # re-check local files against it

WHY A CHECKSUM, AND NOT A ROW COUNT
-----------------------------------
D-012 records that the model pickles/checkpoints carry no provenance stamp: nothing inside the
file says which data trained it, so a baseline's training source "cannot be read back from the
file". The first guard tried against that was a row count -- compare local `X_train.npy` rows
against `provenance.json:n_train` -- and it was REMOVED for a documented reason
(`tests/phase2/test_validation.py::test_lightgbm_stays_refused...`): a row count proves the
training DATA is right, never that THIS CHECKPOINT was trained on it, and it silently passed on
the demo machine while rendering an empty baseline.

A SHA-256 does not prove provenance either, and this file does not claim it does. What it proves
is narrower and actually true: that the checkpoint on this machine is byte-for-byte the same file
that produced the numbers recorded beside it. That is the identity that was missing, and it is
what stops a retrain from silently replacing the shipped result.

WHAT IS FROZEN
--------------
The 7-channel headline AND the matched 5-channel control. The wind claim is a DELTA between the
two, so freezing only the winner would leave the comparison unreproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS = os.path.join(REPO, "artifacts")
FROZEN_DIR = os.path.join(ARTIFACTS, "frozen")
MANIFEST = os.path.join(ARTIFACTS, "frozen_manifest.json")

# (filename, role) -- every checkpoint a shipped claim rests on, plus the metrics json that
# scored it. Both legs of BOTH ablations are frozen: a delta is only reproducible if the losing
# leg survives too.
FREEZE = [
    ("tscast_stage2_s2_nodensity.pt", "HEADLINE: stage-2, density loss OFF (T+S+rho)"),
    ("tscast_stage2_s2_nodensity_metrics.json", "scored metrics for the headline"),
    ("tscast_stage2_s2.pt", "stage-2 control, density loss ON (the physics ablation)"),
    ("tscast_stage2_s2_metrics.json", "scored metrics for the physics control"),
    ("tscast_stage1_7ch.pt", "stage-1, wind ON (the wind ablation)"),
    ("tscast_stage1_7ch_metrics.json", "scored metrics for wind ON"),
    ("tscast_stage1_5ch.pt", "stage-1, wind OFF -- matched control"),
    ("tscast_stage1_5ch_metrics.json", "scored metrics for wind OFF"),
]

# Which frozen metrics file backs which claim, for the manifest's `claims` block.
CLAIMS = {
    "headline":          "tscast_stage2_s2_nodensity_metrics.json",
    "physics_control":   "tscast_stage2_s2_metrics.json",
    "wind_on":           "tscast_stage1_7ch_metrics.json",
    "wind_off_control":  "tscast_stage1_5ch_metrics.json",
}

OK, BAD = "  [ok]  ", "  [FAIL]"


def sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def headline_numbers(metrics_path: str) -> dict:
    """Pull the scored numbers OUT of the metrics file. Never hardcode them here."""
    if not os.path.exists(metrics_path):
        return {}
    with open(metrics_path) as f:
        m = json.load(f)
    met = m.get("metrics", {})
    picked = {
        "seed": m.get("seed"),
        "channels": m.get("channels"),
        "T_SEQ": m.get("T_SEQ"),
        "encoder": m.get("encoder"),
        "argo_profiles": m.get("argo_profiles"),
        "train_period": m.get("train_period"),
        "test_period": m.get("test_period"),
        "best_epoch": m.get("best_epoch"),
        "protocol": m.get("protocol"),
        "code_commit": m.get("code_commit"),
    }
    # The scored scalars live in metrics.overall. Copy them verbatim -- these are the numbers
    # this checkpoint ACTUALLY produced, which is the whole point of stamping it.
    overall = met.get("overall", {})
    for key in ("rmse", "bias", "correlation", "skill_rmse_ratio", "skill_vs_climatology",
                "rmse_climatology", "n"):
        if key in overall:
            picked[f"overall_{key}"] = overall[key]
    if isinstance(met.get("depths_m"), list):
        picked["n_depths"] = len(met["depths_m"])
    return {k: v for k, v in picked.items() if v is not None}


def do_freeze() -> int:
    os.makedirs(FROZEN_DIR, exist_ok=True)
    missing = [f for f, _ in FREEZE if not os.path.exists(os.path.join(ARTIFACTS, f))]
    if missing:
        print(f"{BAD} cannot freeze, missing from artifacts/: {missing}")
        return 1

    entries = {}
    print("=" * 72)
    print("FREEZING")
    print("=" * 72)
    for fname, role in FREEZE:
        src = os.path.join(ARTIFACTS, fname)
        dst = os.path.join(FROZEN_DIR, fname)
        digest = sha256(src)
        size = os.path.getsize(src)
        if os.path.exists(dst):                # a previous freeze left it read-only, by design
            try:
                os.chmod(dst, 0o644)           # re-freezing is deliberate: you ran this command
            except OSError:
                pass
        shutil.copy2(src, dst)
        try:                                   # best-effort read-only; Windows honours this
            os.chmod(dst, 0o444)
        except OSError:
            pass
        entries[fname] = {"role": role, "bytes": size, "sha256": digest}
        print(f"{OK} {fname:38s} {size:>10,} B  {digest[:16]}...")

    manifest = {
        "what": "Byte identity of the frozen v2 headline. Proves a checkpoint is the file that "
                "produced the recorded numbers -- NOT that it was trained on any given data "
                "(unknowable from the file, D-012).",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "frozen_copy_dir": "artifacts/frozen/",
        "files": entries,
        "claims": {name: headline_numbers(os.path.join(ARTIFACTS, fname))
                   for name, fname in CLAIMS.items()},
        "recorded_in": "docs/EXPERIMENT_LOG.md :: v2-embargoed 2026-09-01",
        "note": "Every number in `claims` is copied out of the frozen metrics file beside it, "
                "never retyped. Stage-1 legs were independently reproduced from disk by "
                "scripts/phase2/rescore_checkpoint.py (gap 0.00e+00 on both).",
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n{OK} wrote {os.path.relpath(MANIFEST, REPO)}")
    print(f"{OK} froze {len(entries)} files into {os.path.relpath(FROZEN_DIR, REPO)}")
    return 0


def do_verify() -> int:
    if not os.path.exists(MANIFEST):
        print(f"{BAD} no manifest at {os.path.relpath(MANIFEST, REPO)} -- run without --verify first")
        return 1
    with open(MANIFEST) as f:
        man = json.load(f)

    fails: list[str] = []
    print("=" * 72)
    print(f"VERIFYING against manifest frozen at {man.get('frozen_at')}")
    print("=" * 72)
    for fname, rec in man["files"].items():
        live = os.path.join(ARTIFACTS, fname)
        if not os.path.exists(live):
            print(f"{BAD} {fname:38s} MISSING from artifacts/")
            fails.append(fname)
            continue
        digest, size = sha256(live), os.path.getsize(live)
        if digest != rec["sha256"]:
            print(f"{BAD} {fname:38s} CHANGED  {rec['sha256'][:16]}... -> {digest[:16]}...")
            fails.append(fname)
        elif size != rec["bytes"]:
            print(f"{BAD} {fname:38s} size {rec['bytes']:,} -> {size:,}")
            fails.append(fname)
        else:
            print(f"{OK} {fname:38s} unchanged  {digest[:16]}...")

    if fails:
        print(f"\n{BAD} {len(fails)} file(s) differ from the frozen headline: {fails}")
        print("        A retrain has overwritten a shipped artifact. Either restore from")
        print("        artifacts/frozen/, or re-freeze DELIBERATELY and update EXPERIMENT_LOG.")
        return 1
    print(f"\n{OK} all {len(man['files'])} frozen artifacts are byte-identical")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="check live artifacts against the manifest instead of re-freezing")
    args = ap.parse_args()
    return do_verify() if args.verify else do_freeze()


if __name__ == "__main__":
    sys.exit(main())
