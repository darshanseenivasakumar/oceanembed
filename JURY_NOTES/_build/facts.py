"""Numbers the notes quote, read from artifacts at build time. One definition, not four.

WHY THIS FILE EXISTS
The buoy time-axis claim was written into three separate builders, and when the measurement
succeeded all three went stale at once -- each of them still saying the data was "unreachable from
our network" after it had been fetched and scored. A claim worth making in three documents is worth
reading from one place.

`artifacts/` is gitignored, so every reader here returns None when the artifact is absent rather
than raising. A note built on a machine without the run says so, in words, instead of quoting a
number it cannot see.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(name):
    p = os.path.join(ROOT, "artifacts", name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def buoy_time() -> dict | None:
    """The moored-buoy time-axis validation, or None if the run is not on this machine.

    This is the one validation axis Argo structurally cannot supply: a float drifts, so it can
    never say whether the model tracks a FIXED point as it changes. A moored buoy stays put.
    """
    d = _read("buoy_validation.json")
    if not d or "summary" not in d:
        return None
    s = d["summary"]
    return {
        "n_series": s["n_series"],
        "days": s["total_matched_days"],
        "rmse": s["median_rmse"],
        "bias": s["median_bias"],
        "corr": s["median_correlation"],
        "n_intraseasonal": s.get("n_intraseasonal"),
        "corr_intraseasonal": s.get("median_intraseasonal_correlation"),
    }


#: Whether the buoy PANEL ships in the current build. The measurement existing and the feature
#: being demonstrable are different facts, and a jury note must not blur them: the panel was moved
#: out to be rebuilt on its own branch, so the result can be described but not shown on screen.
BUOY_PANEL_SHIPS = os.path.exists(
    os.path.join(ROOT, "app", "ui", "features", "buoy.py"))


def buoy_sentence() -> str:
    """One honest sentence about time-axis validation, whatever the machine holds."""
    b = buoy_time()
    if b is None:
        return ("A moored-buoy comparison is the right test and has not been run on this machine, "
                "so we cannot answer it.")
    shown = ("It is on the rail as <b>Time at one point</b>."
             if BUOY_PANEL_SHIPS else
             "<b>The panel is not in this build</b> - it is being rebuilt on its own branch - so "
             "the result can be described but not demonstrated on screen.")
    return (f"<b>This has been measured.</b> Against moored buoys, which stay in one place: "
            f"<b>{b['n_series']} series</b>, <b>{b['days']:,} matched days</b>, median error "
            f"<b>{b['rmse']:.3f} degC</b> and median correlation <b>{b['corr']:.2f}</b>. {shown}")
