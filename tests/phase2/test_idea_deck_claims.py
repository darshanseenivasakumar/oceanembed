"""The SIH idea-submission deck must quote the frozen deliverable, at its own precision.

WHY THIS EXISTS AND IS SEPARATE FROM test_presentation_claims.py
That file guards OceanEmbed_SIH26066.pptx, the 12-slide pitch deck, and requires every headline at
FOUR decimal places. OceanEmbed_SIH26066_IDEA.pptx is a jury-facing submission slide that rounds to
two -- 0.91 degC, not 0.9063 -- so the same assertion cannot be reused. What must hold is that the
rounding is OF the frozen number and not of some other run.

The build script reads every figure from artifacts/frozen_manifest.json, so this suite is really
asking a different question: did anyone hand-edit the .pptx afterwards, or rebuild it against a
manifest that has since moved? Both have happened to the other deck.
"""
from __future__ import annotations

import json
import os
import re
import zipfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DECK = os.path.join(REPO, "OceanEmbed_SIH26066_IDEA.pptx")
MANIFEST = os.path.join(REPO, "artifacts", "frozen_manifest.json")

needs_deck = pytest.mark.skipif(not os.path.exists(DECK),
                                reason="the idea deck is not built on this machine")
needs_manifest = pytest.mark.skipif(not os.path.exists(MANIFEST),
                                    reason="no frozen_manifest.json on this machine")

#: Retracted legs and the GLORYS-fed comparator, same list the pitch deck is guarded against.
FORBIDDEN = ("0.9267", "0.8529", "0.9096", "0.8873", "0.8548")

#: Published headlines from the papers in docs/LITERATURE_MATRIX.md. Every row there is
#: [ABSTRACT-ONLY] -- nobody on the team has read the methods -- so a numerical comparison against
#: them is exactly the claim the matrix forbids.
PAPER_METRICS = ("0.022", "0.0028")


def _slide_text() -> dict[str, str]:
    out = {}
    with zipfile.ZipFile(DECK) as z:
        for n in z.namelist():
            if re.match(r"ppt/slides/slide\d+\.xml$", n):
                xml = z.read(n).decode("utf-8")
                out[n] = " ".join(re.findall(r"<a:t>(.*?)</a:t>", xml, flags=re.S))
    return out


def _claim() -> dict:
    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    return man["claims"][man["deliverable_key"]]


@needs_deck
def test_the_idea_deck_has_five_slides():
    assert len(_slide_text()) == 5


@needs_deck
@needs_manifest
def test_the_idea_deck_states_the_frozen_headline():
    """RMSE, profile count and comparison count, at the precision the deck actually prints."""
    c = _claim()
    blob = " ".join(_slide_text().values())

    for label, want in (
        ("RMSE", f"{c['overall_rmse']:.2f}"),
        ("skill vs climatology", f"{c['overall_skill_rmse_ratio'] * 100:.0f}%"),
        ("Argo profiles", f"{c['argo_profiles']:,}"),
        ("depth comparisons", f"{c['overall_n']:,}"),
    ):
        assert want in blob, (
            f"the deck does not state the frozen {label} ({want}). Rebuild it: "
            f"python scripts/deck/build_idea_slides.py")


@needs_deck
@needs_manifest
def test_the_idea_deck_is_the_satellite_deliverable_not_the_comparator():
    c = _claim()
    assert c["deliverable"] is True and c["input_source"] == "satellite"
    for part, text in _slide_text().items():
        for bad in FORBIDDEN:
            assert bad not in text, (
                f"{part} carries {bad} -- either a retracted pre-embargo leg or the GLORYS-fed "
                f"comparator, whose reanalysis inputs fail the PS's satellite-only clause.")


@needs_deck
@needs_manifest
def test_the_idea_deck_reports_the_measured_depth_win_count():
    """It must say 14 of 15 while 14 of 15 is what the metrics artifact says, and never 'all'."""
    c = _claim()
    with open(os.path.join(REPO, "artifacts", c["metrics_file"]), encoding="utf-8") as f:
        per = json.load(f)["metrics"]
    wins = sum(1 for r, k in zip(per["rmse"], per["rmse_climatology"]) if r < k)
    n = len(per["depths_m"])
    assert wins < n, "climatology is beaten everywhere -- re-check before the deck claims it"

    blob = " ".join(_slide_text().values())
    assert f"{wins} of the {n} depths" in blob, (
        f"the deck must say '{wins} of the {n} depths'; the metrics artifact says climatology "
        f"wins at {n - wins}.")
    for phrase in ("at all 15 depths", "every one of the 15 depths", "at all fifteen depths"):
        assert phrase not in blob.lower()


@needs_deck
def test_the_idea_deck_makes_no_numerical_comparison_against_the_literature():
    """LITERATURE_MATRIX.md marks every row [ABSTRACT-ONLY]. Citing a paper is fine; putting its
    reported RMSE beside ours is the comparison the matrix says we have not earned."""
    for part, text in _slide_text().items():
        for metric in PAPER_METRICS:
            assert metric not in text, (
                f"{part} quotes {metric}, a published figure from a paper reviewed at abstract "
                f"level only. Cite those papers for approach, never for a number.")


@needs_deck
def test_the_forbidden_detector_is_not_vacuous():
    """A guard that cannot fire is not a guard."""
    blob = " ".join(_slide_text().values())
    assert any(ch.isdigit() for ch in blob), "no digits in the deck at all -- extraction is broken"
    assert "0.9267" not in blob
    assert "0.9267" in "the deck said 0.9267", "substring check itself is broken"
