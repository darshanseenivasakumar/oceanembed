"""F8 -- Validation Lab: what the model is good at, and what it is not.

OWNER: Unit A (Arjhun), transferred from Unit B 2026-08-26 (logged in AGENT_SYNC).
PHASE-2 ONLY. Reads baseline artifacts; modifies nothing.

    from phase2.validation import lab

Everything here reads measured artifacts. Nothing is trained, nothing is simulated, and no
threshold is invented. If a number cannot be traced to a file on disk, it is not in this module.
"""
from . import lab  # noqa: F401

__all__ = ["lab"]
