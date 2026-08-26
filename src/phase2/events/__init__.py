"""F6 -- event detection: eddies, thermal fronts, and an upwelling signature.

OWNER: Unit A (Arjhun). Design: `docs/phase2/f6-events-design.md`.

Single-snapshot DETECTION only. Our record is 48 monthly fields, which cannot support eddy
tracking or heatwave persistence (F7); neither is attempted here.

    from phase2.events import eddy, fronts, upwelling
    from phase2.events import _realdata            # "is this a real ocean" -- by structure

Every module takes one snapshot at a time and refuses a time axis, because a caller passing the
whole record is usually about to try tracking.
"""
from . import _metric, _realdata, eddy, fronts, upwelling  # noqa: F401

__all__ = ["eddy", "fronts", "upwelling", "_realdata", "_metric"]
