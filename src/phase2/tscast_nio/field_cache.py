"""One predictor, one lock, one cache key. Owner: Unit A (Arjhun).

WHY THIS EXISTS
---------------
Seven new pages are about to each need "give me the reconstructed field for date D". Every existing
page that needed it wrote its own loader, and the three pieces that get written wrong are always the
same three:

1. THE CACHE KEY. `st.cache_resource`/`st.cache_data` key on the function's ARGUMENTS, never on the
   source of the modules the function imports. On 2026-09-02 `inference.py` was fixed at 19:27 to
   load the bundle its checkpoint was trained on; a server started at 19:17 went on serving a
   predictor built from the wrong bundle, and the Profile tab showed an 8 degC error while the same
   call outside Streamlit was correct. `field.v2_cache_version()` was factored out after being
   pasted three times. `physics_page._v2s2_version()` is the FOURTH copy -- the stage-1 version
   hashes the stage-1 checkpoint, so a stage-2 page reusing it pins its cache to a file that never
   changes when stage 2 does. `cache_version(stage)` here is the one definition of both.

2. THE LOCK. `inference.reconstruct` OVERWRITES `predictor.ds.index` (inference.py:203) and never
   restores it. `field.predict_field` BORROWS the same attribute and restores it in a `finally`
   (field.py:124-144). So two concurrent callers sharing one predictor corrupt each other: a point
   lookup arriving during a field reconstruction shrinks the index from ~11,832 rows to 1
   mid-iteration, and the `finally` then writes the other's saved value back. It does not reliably
   raise -- it returns a plausible wrong answer. `api/service.py` holds a lock for exactly this
   reason and says so at length. [VERIFIED 2026-09-05] FOUR app pages -- cube_page.py:78,
   physics_page.py:89 and :171, tscast_page.py:123 -- put the predictor in `st.cache_resource`,
   which is a CROSS-SESSION singleton shared by every browser tab, with no lock at all. Two tabs
   open on the demo laptop is enough to reach it.

3. THE MEMORY. A (100, 240, 15) float64 array is 2.88 MB and a full field dict is ~12 MB. Cached
   unbounded across the 388 available dates that is 4.6 GB. No existing page bounds its cache, so
   `keep` exists to let a page cache only the arrays it draws.

NO STREAMLIT HERE
-----------------
`src/` has no module-level Streamlit import anywhere, and `tests/phase2/test_viz_explainer.py`
asserts it for the whole tree. The `@st.cache_*` decorators live in `app/phase2/_fields.py`; this
module is what they call. Keeping the lock down here rather than in the wrapper is deliberate --
`scripts/` and the FastAPI service call the same predictor, and a lock only some callers take is
not a lock.
"""
from __future__ import annotations

import hashlib
import os
import threading

import numpy as np

from oceanembed import config as base

#: Held across every predictor call. RLock so a caller holding it can call a second locked path
#: without deadlocking against itself -- the same choice `api/service.py` documents.
_LOCK = threading.RLock()

#: Process-level predictors, one per (stage, checkpoint). Built under the lock, on first use.
_PREDICTORS: dict[tuple, object] = {}

STAGE2_CHECKPOINT = "tscast_stage2_sat_s2.pt"

#: What a page usually needs. `provenance` is NOT optional -- a field with no provenance is a
#: picture with no source, and every panel built on one has to say where the number came from.
DEFAULT_KEEP = ("date", "stage", "temperature", "sigma", "valid_mask", "land_mask", "provenance")

#: Everything `predict_field` returns, for a caller that wants salinity and density too.
ALL_KEYS = DEFAULT_KEEP + ("salinity", "sigma_s", "density")


def checkpoint_for(stage: int = 1) -> str:
    """The checkpoint path a given stage loads. Stage 1 is the frozen deliverable."""
    return base.art("tscast_stage1.pt" if int(stage) == 1 else STAGE2_CHECKPOINT)


def cache_version(stage: int = 1) -> str:
    """Cache key for any Streamlit surface keyed on the v2 model at `stage`.

    Stage 1 delegates to `field.v2_cache_version()` so there is exactly one definition of the
    stage-1 key rather than a fifth transcription of it.
    """
    from phase2.tscast_nio import field as _F
    if int(stage) == 1:
        return _F.v2_cache_version()

    from phase2.tscast_nio import dataset as _D, inference as _I
    h = hashlib.sha256()
    for p in (checkpoint_for(stage), _I.__file__, _D.__file__, _F.__file__):
        try:
            st_ = os.stat(p)
            h.update(f"{p}:{st_.st_mtime_ns}:{st_.st_size}".encode())
        except OSError:
            h.update(f"{p}:missing".encode())
    return h.hexdigest()[:16]


def get_predictor(stage: int = 1, *, checkpoint: str | None = None):
    """The process's predictor for this stage, built once, under the lock.

    Callers that hand the result to two threads must still go through `field_for` /
    `reconstruct_point` rather than calling the predictor directly -- holding a reference is safe,
    using it unlocked is not. See the module docstring.
    """
    from phase2.tscast_nio.inference import TSCastPredictor
    key = (int(stage), checkpoint)
    with _LOCK:
        if key not in _PREDICTORS:
            _PREDICTORS[key] = (TSCastPredictor() if int(stage) == 1 and checkpoint is None
                                else TSCastPredictor(checkpoint=checkpoint or checkpoint_for(stage)))
        return _PREDICTORS[key]


def available_dates(stage: int = 1, *, predictor=None) -> list[str]:
    """The dates THIS MODEL can answer for, as YYYY-MM-DD.

    Not the dates some other bundle has. `cube_page` carried the bug where the picker offered
    GLORYS' 48 monthly 2019-2022 dates while the model reconstructed from a 2025-2026 daily bundle,
    so a chosen date could be over a thousand days from anything the model had seen -- and
    `_time()` is an argmin with no bound, so it answered anyway.
    """
    p = predictor if predictor is not None else get_predictor(stage)
    return [str(t)[:10] for t in np.asarray(p.data["times"]).astype("datetime64[D]")]


def device_default() -> str | None:
    """The device to reconstruct on, or None to leave the predictor where it loaded (CPU).

    `field.py` records the measurement: CPU 32.09 s, CUDA 7.78 s, a 4.1x speedup agreeing to
    6.9e-4 degC over 153,291 cells -- float32 noise against a 0.9 degC RMSE. The default is left on
    CPU on purpose, because switching it would make an exported file differ in its last digits from
    the page beside it. Set OCEANEMBED_DEVICE=cuda to opt in per machine, so it stays a decision
    someone takes rather than a code change someone ships.
    """
    return os.environ.get("OCEANEMBED_DEVICE") or None


def field_for(date: str, *, stage: int = 1, keep: tuple[str, ...] = DEFAULT_KEEP,
              device: str | None = None, predictor=None) -> dict:
    """One whole-field reconstruction, trimmed to `keep`. Costs ~32 s on CPU; cache the result.

    `keep` bounds what a caller holds: a page drawing only temperature has no reason to keep sigma,
    salinity and density alive in a cache for every date the user clicks.
    """
    from phase2.tscast_nio.field import predict_field
    p = predictor if predictor is not None else get_predictor(stage)
    dev = device if device is not None else device_default()
    with _LOCK:
        full = predict_field(p, str(date), device=dev)
    missing = [k for k in keep if k not in full]
    if missing:
        raise KeyError(f"predict_field returned no {missing}; asked for keep={keep}")
    out = {k: full[k] for k in keep}
    # Say which device produced these numbers. Two pages on one screen reconstructing on different
    # devices differ in the last digits, and a reader comparing them deserves to know why.
    if isinstance(out.get("provenance"), dict):
        out["provenance"] = dict(out["provenance"], device=str(dev or "cpu"))
    return out


def reconstruct_point(lat, lon, date: str, *, stage: int = 1, predictor=None) -> dict:
    """One point profile, through the same lock as `field_for`.

    A page that draws a map with `field_for` and a profile with `reconstruct` is exactly the
    two-caller case the module docstring describes, even in a single browser tab.
    """
    p = predictor if predictor is not None else get_predictor(stage)
    with _LOCK:
        return p.reconstruct(float(lat), float(lon), str(date))


def reset() -> None:
    """Drop the cached predictors. For tests, and for a page that has just been told the checkpoint
    on disk changed. Never call it from a request path -- another thread may be mid-reconstruction.
    """
    with _LOCK:
        _PREDICTORS.clear()
