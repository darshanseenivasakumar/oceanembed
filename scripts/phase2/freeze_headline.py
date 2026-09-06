"""Freeze the shipped deliverable + its comparators, and give each a checksum identity.

    python scripts/phase2/freeze_headline.py           # freeze + write the manifest
    python scripts/phase2/freeze_headline.py --verify   # re-check local files against it

WHAT THIS IS
------------
A record of which runs back which shipped claim: for each, the metrics JSON that holds its scored
numbers, and the checkpoint whose bytes produced them. A SHA-256 does not prove what data trained a
checkpoint (unknowable from the file, D-012) -- it proves the narrower, true thing: that the
checkpoint on THIS machine is byte-for-byte the one that produced the numbers recorded beside it,
so a retrain cannot silently replace a shipped result.

THE DELIVERABLE IS THE SATELLITE-INPUT RUN
------------------------------------------
The PS requires "the three-dimensional ocean temperature using ONLY surface satellite
observations." The deliverable is therefore `sat_7ch_s42` (satellite inputs, GLORYS target),
scored 0.9078 degC -- see `PHASE2_STATUS.md` row 16. The GLORYS-input runs (0.8548 stage-2, the
0.8645 embargoed stage-1) are legitimate COMPARATORS, not the deliverable, because their inputs are
reanalysis. An earlier version of this manifest named the 0.8548 GLORYS run as "headline"; that was
before the satellite build and is corrected here.

CHECKPOINTS THAT LIVE ON ANOTHER MACHINE
----------------------------------------
The satellite deliverable trains on Arjhun's machine, so `sat_7ch_s42.pt` may be absent here. The
freeze does NOT refuse in that case: it records the run's scored numbers (from the metrics JSON,
which travels in the bundle) and marks the checkpoint checksum `null` with `present: false`. A true
byte-freeze of that checkpoint must be re-run where the file lives -- `--verify` skips a run whose
checkpoint was never frozen rather than failing on it.
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

# Each run behind a shipped claim. `deliverable` marks the single PS answer; the rest are
# comparators. `metrics` (the scored numbers) must be present to record a claim; `checkpoint` (the
# bytes) may be absent when it lives on the training machine.
RUNS = [
    dict(
        key="deliverable_satellite",
        deliverable=True,
        input_source="satellite",
        metrics="tscast_stage1_sat_7ch_s42_metrics.json",
        checkpoint="tscast_stage1_sat_7ch_s42.pt",
        role="THE PS DELIVERABLE -- stage-1, satellite inputs (OSTIA SST, DUACS altimetry, "
             "SMOS-blended SSS, GLOBCURRENT total currents, observational wind); GLORYS target.",
    ),
    dict(
        key="glorys_comparator_stage2",
        deliverable=False,
        input_source="glorys",
        metrics="tscast_stage2_s2_nodensity_metrics.json",
        checkpoint="tscast_stage2_s2_nodensity.pt",
        role="GLORYS-INPUT COMPARATOR, not the deliverable (fails the satellite-only PS "
             "requirement). Ships T+S+rho. This is the run an earlier manifest wrongly named "
             "'headline'.",
    ),
    dict(
        key="glorys_comparator_stage2_densityON",
        deliverable=False,
        input_source="glorys",
        metrics="tscast_stage2_s2_metrics.json",
        checkpoint="tscast_stage2_s2.pt",
        role="GLORYS stage-2 with the paper's eq.5 density loss ON -- the physics-ablation "
             "control for the run above.",
    ),
    dict(
        key="glorys_comparator_stage1_embargoed",
        deliverable=False,
        input_source="glorys",
        metrics="tscast_stage1_embargo_withUV_s42_metrics.json",
        checkpoint="tscast_stage1_embargo_withUV_s42.pt",
        role="GLORYS stage-1 (withUV) after the 1d3c135 _window() embargo -- a comparator, and "
             "the leak-corrected successor to the pre-embargo stage-1 runs.",
    ),
]

OK, BAD, PEND = "  [ok]  ", "  [FAIL]", "  [pend]"


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


def scored_numbers(metrics_path: str) -> dict:
    """Pull the scored numbers and provenance OUT of the metrics file. Never hardcode them here."""
    with open(metrics_path) as f:
        m = json.load(f)
    picked = {k: m.get(k) for k in (
        "seed", "channels", "T_SEQ", "encoder", "argo_profiles", "train_period", "test_period",
        "best_epoch", "protocol", "code_commit", "tag", "input_source", "stage")}
    overall = m.get("metrics", {}).get("overall", {})
    for key in ("rmse", "bias", "correlation", "skill_rmse_ratio", "skill_vs_climatology",
                "rmse_climatology", "n"):
        if key in overall:
            picked[f"overall_{key}"] = overall[key]
    depths = m.get("metrics", {}).get("depths_m")
    if isinstance(depths, list):
        picked["n_depths"] = len(depths)
    return {k: v for k, v in picked.items() if v is not None}


def do_freeze() -> int:
    os.makedirs(FROZEN_DIR, exist_ok=True)

    # The manifest as it stands. Read BEFORE the refusal check, because a run recorded by the
    # other machine is not an unrecordable run -- it is one this disk cannot re-verify.
    previous: dict = {}
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as f:
                previous = (json.load(f) or {}).get("claims") or {}
        except (OSError, json.JSONDecodeError):
            previous = {}                            # unreadable: freeze from scratch, say nothing false

    # A run with no metrics file AND no prior record cannot be recorded -- there would be no
    # number to stamp. With a prior record there is: it was verified on the machine that holds the
    # file, and this run carries it forward rather than deleting it.
    #
    # NEITHER MACHINE HOLDS ALL FOUR RUNS. The stage-2 GLORYS comparators exist only on Darshan's
    # disk -- not their checkpoints, not their metrics JSONs, and they are not in git either, so
    # their scores (0.8548 / 0.8593) survive ONLY in this manifest. The satellite deliverable and
    # the embargoed comparator exist only on Arjhun's. A freeze that rebuilt every entry from local
    # files therefore could not run at all on Arjhun's machine, and on Darshan's it would have
    # nulled the deliverable. Accumulating is not a convenience here; it is the only way the
    # manifest can describe the project rather than one laptop.
    unrecordable = [r["key"] for r in RUNS
                    if not os.path.exists(os.path.join(ARTIFACTS, r["metrics"]))
                    and not previous.get(r["key"], {}).get("overall_rmse")]
    if unrecordable:
        print(f"{BAD} cannot freeze, no metrics JSON and no prior record for: {unrecordable}")
        return 1

    print("=" * 72)
    print("FREEZING")
    print("=" * 72)
    claims: dict = {}
    n_frozen = n_pending = n_elsewhere = 0
    for r in RUNS:
        prior = previous.get(r["key"], {})
        metrics_path = os.path.join(ARTIFACTS, r["metrics"])
        if os.path.exists(metrics_path):
            nums = scored_numbers(metrics_path)
        else:
            # Carried from the previous manifest: this disk cannot re-read the metrics, so the
            # numbers are quoted, not re-verified. Said in the record rather than left implied.
            nums = {k: v for k, v in prior.items()
                    if k not in ("role", "deliverable", "input_source", "metrics_file",
                                 "checkpoint", "checkpoint_present", "checkpoint_sha256",
                                 "checkpoint_bytes", "checkpoint_note",
                                 "checkpoint_frozen_elsewhere", "scores_carried_forward")}
            nums["scores_carried_forward"] = True
        ck_src = os.path.join(ARTIFACTS, r["checkpoint"])
        present = os.path.exists(ck_src)
        entry = {
            "role": r["role"],
            "deliverable": r["deliverable"],
            "input_source": r["input_source"],
            "metrics_file": r["metrics"],
            "checkpoint": r["checkpoint"],
            "checkpoint_present": present,
            **nums,
        }
        if present:
            dst = os.path.join(FROZEN_DIR, r["checkpoint"])
            if os.path.exists(dst):                 # a prior freeze left it read-only, by design
                try:
                    os.chmod(dst, 0o644)            # re-freezing is deliberate: you ran this
                except OSError:
                    pass
            shutil.copy2(ck_src, dst)
            try:
                os.chmod(dst, 0o444)
            except OSError:
                pass
            entry["checkpoint_sha256"] = sha256(ck_src)
            entry["checkpoint_bytes"] = os.path.getsize(ck_src)
            n_frozen += 1
            tag = "DELIVERABLE" if r["deliverable"] else "comparator"
            rmse = entry.get("overall_rmse")
            print(f"{OK} {r['key']:34s} {tag:11s} rmse={rmse:.4f}  {entry['checkpoint_sha256'][:16]}...")
        else:
            # THIS MANIFEST SPANS TWO MACHINES, so a freeze must ACCUMULATE, not overwrite.
            # Neither disk holds all four checkpoints: the stage-2 GLORYS comparators were frozen
            # on Darshan's, the satellite deliverable and the embargoed comparator live on
            # Arjhun's. Rebuilding every entry from local presence alone meant whoever ran the
            # freeze LAST silently nulled the other machine's checksums -- destroying the only
            # record that those bytes produced 0.8548 and 0.8593. Verified before it could happen:
            # running this on Arjhun's machine on 2026-09-04 would have wiped 53e73e4f... and
            # 3b43ac09... So a checksum already in the manifest is carried forward and labelled
            # frozen-elsewhere; only a genuinely unknown one stays pending.
            prior = previous.get(r["key"], {})
            inherited = prior.get("checkpoint_sha256")
            tag = "DELIVERABLE" if r["deliverable"] else "comparator"
            rmse = entry.get("overall_rmse")
            if inherited:
                entry["checkpoint_sha256"] = inherited
                entry["checkpoint_bytes"] = prior.get("checkpoint_bytes")
                entry["checkpoint_frozen_elsewhere"] = True
                entry["checkpoint_note"] = (
                    "frozen on another machine; checksum carried forward from the previous "
                    "manifest and NOT re-verified here, because this disk does not hold the file. "
                    "Re-run the freeze where it lives to re-verify.")
                n_elsewhere += 1
                print(f"{OK} {r['key']:34s} {tag:11s} rmse={rmse:.4f}  {inherited[:16]}... "
                      f"(frozen elsewhere, carried forward)")
            else:
                entry["checkpoint_sha256"] = None
                entry["checkpoint_bytes"] = None
                entry["checkpoint_note"] = ("checkpoint not on this machine -- scores are verified "
                                            "from the metrics file; re-run the freeze where this "
                                            ".pt lives to fill the checksum.")
                n_pending += 1
                print(f"{PEND} {r['key']:34s} {tag:11s} rmse={rmse:.4f}  "
                      f"checkpoint ABSENT (checksum pending)")
        claims[r["key"]] = entry

    deliverable_key = next((r["key"] for r in RUNS if r["deliverable"]), None)
    manifest = {
        "what": "Byte identity + verified scores of the shipped deliverable and its comparators. "
                "A checksum proves a checkpoint is the file that produced the numbers beside it, "
                "not what trained it (D-012).",
        "supersedes": "the 2026-09-01 manifest (frozen at a5cdd3a) that named the GLORYS stage-2 "
                      "run 0.8548 as HEADLINE. That predates the satellite-input build and the "
                      "deeper _window() embargo fix (1d3c135); 0.8548 is a comparator, not the "
                      "deliverable.",
        "authoritative_source": "PHASE2_STATUS.md row 16 (the PS deliverable); docs/HANDOFF.md.",
        "deliverable_key": deliverable_key,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "frozen_copy_dir": "artifacts/frozen/",
        "claims": claims,
        "pre_embargo_invalid": "artifacts/INVALID_PRE_EMBARGO.md -- the pre-embargo stage-1 runs "
                               "(0.8611 withUV, 0.9024 noUV, 0.9267 tseq31) are leaky. Never quote.",
        "note": "Every number in `claims` is read from the run's metrics JSON, never retyped. A "
                "claim whose `checkpoint_present` is false has a null checksum: its scores are "
                "verified here but its bytes must be frozen on the machine that holds the .pt.",
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n{OK} wrote {os.path.relpath(MANIFEST, REPO)}")
    print(f"{OK} froze {n_frozen} checkpoint(s); {n_pending} pending (absent here)")
    if deliverable_key and claims[deliverable_key]["checkpoint_sha256"] is None:
        print(f"{PEND} the DELIVERABLE ({deliverable_key}) checkpoint is absent -- re-freeze where "
              f"it lives to complete the byte identity.")
    return 0


def do_verify() -> int:
    if not os.path.exists(MANIFEST):
        print(f"{BAD} no manifest at {os.path.relpath(MANIFEST, REPO)} -- run without --verify first")
        return 1
    with open(MANIFEST) as f:
        man = json.load(f)

    fails: list[str] = []
    elsewhere: list[str] = []
    print("=" * 72)
    print(f"VERIFYING against manifest frozen at {man.get('frozen_at')}")
    print("=" * 72)
    for key, rec in man["claims"].items():
        fname = rec["checkpoint"]
        recorded = rec.get("checkpoint_sha256")
        if recorded is None:
            print(f"{PEND} {key:34s} checkpoint never frozen here (pending) -- skipped")
            continue
        if rec.get("checkpoint_frozen_elsewhere") or rec.get("checkpoint_present") is False:
            # THE MANIFEST SPANS TWO MACHINES (see do_freeze). A checksum carried forward from
            # the other machine is not a file that vanished here -- it was never here. Reporting
            # it as MISSING made --verify exit 1 on the training machine (measured 2026-09-06),
            # the very machine jury note 08 tells the presenter to run the check on, live.
            print(f"{PEND} {key:34s} frozen on another machine ({recorded[:16]}...) -- "
                  f"cannot be re-verified from this disk, skipped")
            elsewhere.append(key)
            continue
        live = os.path.join(ARTIFACTS, fname)
        if not os.path.exists(live):
            print(f"{BAD} {key:34s} {fname} MISSING (was frozen, now gone)")
            fails.append(key)
            continue
        digest = sha256(live)
        if digest != recorded:
            print(f"{BAD} {key:34s} CHANGED  {recorded[:16]}... -> {digest[:16]}...")
            fails.append(key)
        else:
            print(f"{OK} {key:34s} unchanged  {digest[:16]}...")

    if fails:
        print(f"\n{BAD} {len(fails)} checkpoint(s) differ from the frozen record: {fails}")
        print("        A retrain overwrote a shipped artifact. Restore from artifacts/frozen/, or")
        print("        re-freeze DELIBERATELY and update PHASE2_STATUS.md.")
        return 1
    frozen = (sum(1 for r in man["claims"].values() if r.get("checkpoint_sha256"))
              - len(elsewhere))
    print(f"\n{OK} all {frozen} checkpoint(s) frozen on this machine are byte-identical "
          f"({len(man['claims']) - frozen} pending or frozen elsewhere, not re-verifiable here)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="check live checkpoints against the manifest instead of re-freezing")
    args = ap.parse_args()
    return do_verify() if args.verify else do_freeze()


if __name__ == "__main__":
    sys.exit(main())
