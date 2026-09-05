"""The `provenance` block of `docs/phase2/tscast_output_schema.md` §5, assembled in ONE place.

WHY THIS EXISTS
§5 is marked `Status: CONTRACT` and lists ten keys every output record must carry. Neither producer
satisfied it: the point path (`inference.py`) omitted `checkpoint_sha256` and `code_commit`, and the
field path (`field.py`) omitted those plus `P`, `input_date` and `clim_train_years` -- and nothing
tested §5, so the gap was invisible. An export that serialised that block would have written a
contract violation into a file and handed it to a jury.

The git-hash helper was ALSO copy-pasted five times (`daily_pipeline.py`, `sat_daily_pipeline.py`,
`measure_v2_metrics.py`, `build_daily_climatology.py`, inline in `train_stage1.py`). Those five are
left alone deliberately -- they sit in working training and pipeline code, three are one-shot
scripts, and a refactor of them days before a demo buys nothing. New code uses this module; the
copies get a post-demo ticket.

RULE 8 IS THE DESIGN CONSTRAINT
`START_HERE.md` rule 8: an absence is not a value. Every function here reports what it does not know
rather than substituting the meaning it would have had. `code_commit()` returns "unknown" and
`as_netcdf_attrs` writes "not recorded" -- both are readable as absences, and neither can be
mistaken for a real hash or a real commit.
"""
from __future__ import annotations

import hashlib
import os
import subprocess

from oceanembed import config as base

#: The ten keys §5 requires. Hardcoded rather than parsed out of the markdown: a parser is its own
#: bug source, and `tests/phase2/test_provenance.py` guards this list against the doc with a
#: source-text check, so the two cannot drift apart silently.
SCHEMA_V5_KEYS = ("model", "checkpoint_sha256", "seed", "T_SEQ", "P", "encoder",
                  "input_source", "input_date", "clim_train_years", "code_commit")

#: What an unknown looks like. One token, so a reader (and a grep) can find every gap in a file.
UNKNOWN = "unknown"
NOT_RECORDED = "not recorded"


def code_commit() -> str:
    """Short git hash of the working tree, or `UNKNOWN`.

    Matches the five existing copies' behaviour exactly, including returning a string on failure
    rather than raising -- provenance must never be the thing that takes down a reconstruction.
    """
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      cwd=base.ROOT, text=True, stderr=subprocess.DEVNULL)
        return out.strip() or UNKNOWN
    except Exception:                                   # noqa: BLE001 -- any failure is "unknown"
        return UNKNOWN


def code_dirty() -> bool | None:
    """Whether the tree had uncommitted changes. `None` if git could not be asked.

    A commit hash taken from a dirty tree does not describe the code that ran, so the hash alone is
    not enough to reproduce a result. Recorded beside it rather than left for someone to assume.
    """
    try:
        out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                      cwd=base.ROOT, text=True, stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except Exception:                                   # noqa: BLE001
        return None


def checkpoint_sha256(path: str | None) -> str:
    """SHA-256 of a checkpoint file, or `UNKNOWN` if it cannot be read.

    Chunked at 1 MB, the same read `field._promoted_from`, `promote_run.py` and `freeze.py` use --
    a checkpoint is small now but this must not become the reason a large one is loaded into memory.
    """
    if not path or not os.path.exists(path):
        return UNKNOWN
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return UNKNOWN
    return h.hexdigest()


def provenance_block(predictor, *, input_date=None, days_off=None, extra=None) -> dict:
    """The §5 block for a loaded predictor. Every required key present, unknowns named.

    `extra` is merged last so a caller can add context §5 does not cover (`bundle`, `n_cells`,
    `sigma_is_calibrated`). It cannot silently drop a §5 key -- that is asserted below, because the
    whole point of this function is that the contract holds no matter who calls it.
    """
    meta = getattr(predictor, "meta", {}) or {}
    data = getattr(predictor, "data", {}) or {}
    ck_path = getattr(predictor, "checkpoint_path", None)

    stage = int(meta.get("stage", getattr(predictor, "stage", 1)) or 1)
    block = {
        "model": f"tscast-nio-stage{stage}",
        "checkpoint_sha256": checkpoint_sha256(ck_path),
        "seed": meta.get("seed"),
        "T_SEQ": meta.get("T_SEQ"),
        "P": meta.get("P"),
        "encoder": meta.get("encoder"),
        "input_source": data.get("input_source", UNKNOWN),
        "input_date": input_date,
        # Same source the point path uses (`inference.reconstruct`), not a second definition. The
        # checkpoint does not carry this, so reading meta would silently yield "not recorded" on
        # every record while the point path reported the real years.
        "clim_train_years": meta.get("clim_train_years") or list(base.TRAIN_YEARS),
        "code_commit": code_commit(),
        # Beyond §5, but the things a reader asks next.
        "code_dirty": code_dirty(),
        "stage": stage,
        "days_from_requested": days_off,
    }
    if extra:
        block.update(extra)

    missing = [k for k in SCHEMA_V5_KEYS if k not in block]
    assert not missing, f"provenance_block dropped schema §5 keys: {missing}"
    return block


def as_netcdf_attrs(prov: dict | None, prefix: str = "") -> dict:
    """Flatten a provenance dict to NetCDF-legal scalar attributes.

    THE POINT OF THIS FUNCTION, AND THE TRAP IT AVOIDS
    NetCDF attributes cannot hold `None`, nested dicts, or (portably) `bool`. The obvious
    implementation drops a `None` -- and dropping it turns "we did not record this" into "this file
    has no such concept", which is rule 8's failure exactly, in the one artifact that leaves the
    building. So every key survives: `None` becomes the literal string `"not recorded"`, and a
    reader can tell an unrecorded field from an absent one because the attribute is still there.

    Booleans become "true"/"false" strings rather than 0/1, so a flag can never be read as a count.
    """
    out: dict[str, object] = {}
    if not prov:
        return out
    for k, v in prov.items():
        key = f"{prefix}{k}"
        if v is None:
            out[key] = NOT_RECORDED
        elif isinstance(v, bool):
            out[key] = "true" if v else "false"
        elif isinstance(v, (int, float, str)):
            out[key] = v
        elif isinstance(v, (list, tuple)):
            out[key] = ", ".join(str(x) for x in v) if v else NOT_RECORDED
        elif isinstance(v, dict):
            # An EMPTY dict must not vanish. Recursing into it adds nothing, so the key silently
            # disappears from the file -- which is this function's own failure mode committed
            # against itself. Caught by the smoke test on 2026-09-05.
            flat = as_netcdf_attrs(v, prefix=f"{key}.")
            out.update(flat if flat else {key: NOT_RECORDED})
        else:
            out[key] = str(v)
    return out
