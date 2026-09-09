"""A two-page quick-answer card: all 16 features, one sentence of execution each.

Feature names, bands and order are READ from app/ui/words.py at build time, so the card cannot
drift from the rail the demo actually shows. Headline numbers come from frozen_manifest.json for
the same reason.
"""
from __future__ import annotations

import json
import os
import sys

from engine import (
    PageBreak, Spacer, _p, build, callout, cmd, cover, heading, kvstrip, table,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for p in (ROOT, os.path.join(ROOT, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

BRAND = "OceanEmbed  |  SIH26066  |  Quick-answer card"

#: key -> (what you DO on screen, the one-line answer to give)
ACTIONS = {
    "ocean3d": (
        "Click it, then drag to rotate; the volume is already built for the chosen date.",
        "This is the whole output - 24,000 cells x 15 depths. The holes are the sea floor, not "
        "missing data."),
    "clickpoint": (
        "Click anywhere in the sea on the map; then click on land.",
        "A float answers this only where it happens to be. We answer it everywhere - and on land "
        "we refuse instead of guessing."),
    "confidence": (
        "Click it, then switch <b>View</b> to uncertainty alone.",
        "The model is least sure exactly where the ocean is most active - the Somali Current and "
        "the Arabian Sea eddies."),
    "transect": (
        "Type two end points (try 8 N 68 E to 20 N 88 E) to cut a vertical wall through the sea.",
        "Structure is what oceanographers read - a tilting thermocline is obvious here and "
        "invisible on a map."),
    "acoustics": (
        "Click it and pick a <b>Layer</b>; the sound-speed profile is computed from our "
        "temperature.",
        "Sound speed follows temperature, so a temperature model is an acoustics model - this is "
        "what a navy actually acts on."),
    "validation": (
        "Click it and walk down the per-depth table.",
        "Measured against real floats it never saw. It beats the long-term average at 14 of 15 "
        "depths, and we label the one where it loses."),
    "heatwave": (
        "Click it; the detection is precomputed, so it appears instantly.",
        "Five days above the seasonal 90th percentile <b>at depth</b> - a marine heatwave a "
        "satellite physically cannot see."),
    "cyclone": (
        "Click it, pick <b>Show</b>, and choose an October or November date.",
        "Not surface warmth - the depth of the warm layer, which is what decides whether a storm "
        "intensifies."),
    "priority": (
        "Click it; leave the sliders alone unless asked.",
        "Where our doubt meets an energetic ocean. A suggestion of where to measure next, never an "
        "instruction."),
    "buoy": (
        "Click it and pick a <b>Station and depth</b> from the list.",
        "Argo floats drift, so they cannot test tracking through time. A moored buoy sits still, "
        "so it can."),
    "assimilate": (
        "Click it; the experiment is precomputed.",
        "A real float is fed back into the frozen model with no retraining, and the fix spreads to "
        "water in a similar state - not water nearby."),
    "wake": (
        "Click it, pick a <b>Storm</b>, then switch <b>Panel</b> from the naive view to the "
        "passage-relative one.",
        "Cooling at 11 of 12 track points, from a model never taught that cyclones cool the ocean. "
        "The naive view finds nothing - we show both."),
    "cloud": (
        "Click it; the sweep is precomputed.",
        "We blanked the satellite input on purpose, like monsoon cloud. Past 20% the loss is real "
        "and steady."),
    "shape": (
        "Click it.",
        "Error scores each depth alone. This asks whether the shape between depths survived - and "
        "the thermocline gradient does."),
    "stability": (
        "Click it and read the before/after bars.",
        "805 physically impossible columns become 0. A training penalty makes that rare; a "
        "projection makes it impossible."),
    "observability": (
        "Click it and read the stacked bar down the depths.",
        "It reads sea-surface temperature near the top and sea-surface <b>height</b> at the "
        "thermocline - untaught, and physically correct."),
}

BAND_NOTE = {
    "SEE IT": "What the system produces.",
    "PROVE IT": "Evidence that it is right.",
    "STRESS IT": "Us attacking our own model.",
}


def _facts() -> dict:
    with open(os.path.join(ROOT, "artifacts", "frozen_manifest.json"), encoding="utf-8") as f:
        d = json.load(f)["claims"]["deliverable_satellite"]
    return {"rmse": d["overall_rmse"], "profiles": d["argo_profiles"],
            "skill": d["overall_skill_rmse_ratio"],
            "protocol": d.get("scoring_protocol", "unknown")}


def build_note(path):
    from app.ui.words import BANDS, FEATURES

    f = _facts()
    s = []

    s += cover(
        badge=str(len(FEATURES)), badge_sub="FEATURES",
        kicker="OCEANEMBED  ·  SIH26066  ·  QUICK-ANSWER CARD",
        title="Every Feature, One Sentence Each",
        subtitle="What to click, and what to say while it loads. Keep this beside you.",
    )

    s.append(kvstrip([
        ("Error vs real floats", f"{f['rmse']:.4f} degC"),
        ("Independent profiles", f"{f['profiles']}"),
        ("Better than average by", f"{f['skill']*100:.1f}%"),
        ("Features on the rail", f"{len(FEATURES)}"),
    ]))

    s.append(cmd(".venv/Scripts/python.exe -m streamlit run app/ui/main.py --server.port 8500",
                 "START EVERYTHING ONCE, THEN JUST CLICK THE RAIL"))
    s.append(_p(
        "Set the <b>Date</b> once at the top and leave <b>Input</b> on <b>Satellite</b>. Those two "
        "apply to every feature below, so you never set them again.", "body"))

    n = 0
    for band in BANDS:
        rows = [x for x in FEATURES if x[4] == band]
        s += heading(f"{band}  -  {BAND_NOTE.get(band, '')}")
        data = [["#", "Feature", "Do this", "Say this"]]
        for key, label, _title, _blurb, _b in rows:
            n += 1
            do, say = ACTIONS.get(key, ("Click it.", ""))
            data.append([str(n), f"<b>{label}</b>", do, say])
        s += table(data, widths=[0.05, 0.15, 0.39, 0.41], font_size=8.1, align=["CENTER"], keep=False)

    s.append(callout(
        "The three we built that the published work does not do",
        "<b>Physical profiles</b> - a hard physical guarantee where the field uses a soft penalty "
        "and therefore never reports a violation count.  <b>What it can see</b> - a map of which "
        "satellite measurement informs which depth.  <b>Learn from a float</b> - an observation "
        "fed back into the frozen model at run time. If asked what is novel, these three, and the "
        "system around them - not the reconstruction method, which is published prior art.",
        "jury"))

    s.append(callout(
        "If a feature will not load",
        "Say so and move on - every panel refuses rather than inventing a number, and that refusal "
        "is the behaviour we designed. Do not restart the app mid-demo.", "warn"))

    s.append(callout(
        "The one number to never get wrong",
        f"<b>{f['rmse']:.4f} degC against {f['profiles']} independent Argo profiles</b>, under "
        f"scoring protocol <b>{f['protocol']}</b>. Older documents may say 0.9078 - that was an "
        f"earlier protocol on the same checkpoint, before below-seafloor comparisons were declined "
        f"and the float depth axis was corrected. Quote the number above.", "note"))

    build(path, BRAND, s, doc_title=f"OceanEmbed - Quick-answer card, {len(FEATURES)} features")
    return path


if __name__ == "__main__":
    print(build_note(os.path.join(ROOT, "JURY_NOTES", "OceanEmbed_QuickCard.pdf")))
