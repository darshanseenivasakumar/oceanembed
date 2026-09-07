"""The presentation must not quote a retracted number, or the wrong model's numbers.

WHY THIS EXISTS
Six wrong claims reached the jury pack and the slide deck, and none of them was catchable by any
existing test, because every one was well-formed prose about a real measurement -- just the wrong
measurement (audit 2026-09-06):

  * the T_SEQ ablation (0.9267 / 0.8529 / 0.9096) is quoted as a "measured disagreement" while
    `artifacts/INVALID_PRE_EMBARGO.md` lists the 31-day leg under "Never quote" and the two
    shorter legs' checkpoints no longer exist;
  * "the thermocline error is inherited -- within 0.023 degC of the reanalysis's own error" is a
    PHASE-1 number restated about the shipped v2 model, where the gap is 0.178 degC at 100 m;
  * the speaker notes on two slides carried `tscast_stage1_embargo_withUV_s42` -- the GLORYS-fed
    COMPARATOR -- as if it were the deliverable;
  * one slide said climatology is beaten at all 15 depths while the slide before it said 14.

`freeze.py` checks the artifacts. Nothing checked the sentences a human actually reads out, which
is the surface a jury sees. These tests do.

They are deliberately about the SOURCES a rebuild regenerates from (`JURY_NOTES/_build/*.py`) and
about the deck itself, not the built PDFs: fixing a PDF without fixing its source is a correction
that disappears at the next `build_all.py`.
"""
from __future__ import annotations

import io
import json
import os
import re
import zipfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JN_BUILD = os.path.join(REPO, "JURY_NOTES", "_build")
DECK = os.path.join(REPO, "OceanEmbed_SIH26066.pptx")
MANIFEST = os.path.join(REPO, "artifacts", "frozen_manifest.json")

needs_notes = pytest.mark.skipif(not os.path.isdir(JN_BUILD),
                                 reason="JURY_NOTES/_build is not on this machine")
needs_deck = pytest.mark.skipif(not os.path.exists(DECK),
                                reason="the deck is not on this machine")

#: Every leg of the T_SEQ ablation. All three predate the 1d3c135 embargo fix; the 31-day leg is
#: named in artifacts/INVALID_PRE_EMBARGO.md and the other two were only ever "declared" in a chat
#: log, their checkpoints overwritten by the next run.
PRE_EMBARGO_TSEQ = ("0.9267", "0.8529", "0.9096")

#: The GLORYS-fed comparator, tscast_stage1_embargo_withUV_s42. Legitimate as a comparator, and
#: never the deliverable: its inputs are reanalysis, which fails the PS's satellite-only clause.
COMPARATOR_METRICS = ("0.8873", "0.1105", "0.2948")


def _notes_sources() -> dict[str, str]:
    out = {}
    for name in os.listdir(JN_BUILD):
        if name.endswith(".py"):
            with open(os.path.join(JN_BUILD, name), encoding="utf-8") as f:
                out[name] = f.read()
    return out


def _deck_text() -> dict[str, str]:
    """Every slide and speaker-notes part of the deck, as plain text."""
    out = {}
    with zipfile.ZipFile(DECK) as z:
        for n in z.namelist():
            if re.match(r"ppt/(slides|notesSlides)/(slide|notesSlide)\d+\.xml$", n):
                xml = z.read(n).decode("utf-8")
                out[n] = " ".join(re.findall(r"<a:t>(.*?)</a:t>", xml, flags=re.S))
    return out


# ── the withdrawn input-window comparison ───────────────────────────────────────────────

def _quotes_a_retracted_leg(text: str) -> str | None:
    return next((leg for leg in PRE_EMBARGO_TSEQ if leg in text), None)


def test_the_retracted_leg_detector_is_not_vacuous():
    """The two guards below are string searches, so prove the string they search for is the one
    that was actually in the pack: this is the sentence the jury notes carried until 2026-09-07."""
    was_in_the_pack = ("Its 31-day input window is the worst of three at our data scale (0.9267 "
                       "against 0.8529 at 11 days and 0.9096 at 1 day).")
    assert _quotes_a_retracted_leg(was_in_the_pack) == "0.9267"
    assert _quotes_a_retracted_leg("We ship an 11-day window and cannot prove it is best.") is None


@needs_notes
def test_the_jury_notes_do_not_quote_the_pre_embargo_tseq_ablation():
    for name, text in _notes_sources().items():
        leg = _quotes_a_retracted_leg(text)
        assert leg is None, (
            f"{name} quotes {leg}, a pre-embargo T_SEQ leg. All three legs predate the "
            f"leakage fix and the 31-day one is on INVALID_PRE_EMBARGO.md's do-not-quote "
            f"list. Re-run the ablation under the embargo before making the claim again.")


@needs_deck
def test_the_deck_does_not_quote_the_pre_embargo_tseq_ablation():
    """FORWARD-LOOKING. Unlike the jury-note guard above, this one never fired on the real deck --
    the deck described the 11-day window without quoting the ablation. It is here so that the
    numbers cannot be promoted into the deck later, which is exactly how they reached the notes."""
    for part, text in _deck_text().items():
        leg = _quotes_a_retracted_leg(text)
        assert leg is None, f"{part} quotes the pre-embargo T_SEQ leg {leg}"


# ── the Phase-1 inherited-error figure, restated about v2 ───────────────────────────────

#: How far either side of a "0.023" the scoping label may sit. Wide enough to cover the sentence
#: and its neighbour, narrow enough that a bare claim in an unrelated paragraph still fails --
#: see the control at the end of this test, which is what stops the window from being vacuous.
SCOPE_WINDOW = 600


@needs_notes
def test_the_0023_thermocline_figure_is_always_labelled_phase_1():
    """0.023 degC is the PHASE-1 model's gap to the reanalysis. On the shipped v2 model the gap at
    100 m is 0.178 degC. The figure may appear -- the Validation Lab page really does display the
    Phase-1 record -- but never without saying so in the same breath."""
    def scoped(text: str, at: int) -> bool:
        w = text[max(0, at - SCOPE_WINDOW):at + SCOPE_WINDOW]
        return bool(re.search(r"phase[- ]1", w, re.IGNORECASE))

    for name, text in _notes_sources().items():
        for m in re.finditer(r"0\.023", text):
            assert scoped(text, m.start()), (
                f"{name} quotes 0.023 degC near offset {m.start()} without naming Phase 1. "
                f"Restated about the v2 deliverable it is wrong: the gap there is 0.178 degC at "
                f"100 m, measured on the shipped checkpoint against the same 962 profiles.")

    # THE CONTROL. A window this wide could pass on almost anything, so prove it does not: the
    # exact sentence that was in the pack before the 2026-09-07 correction must still fail.
    bad = ("Its thermocline error is inherited from the training target, within 0.023 degC of the "
           "reanalysis's own error, and is not fixable by us. " + "filler. " * 90)
    assert not scoped(bad, bad.index("0.023")), (
        "the scoping window has grown wide enough to accept the very claim this test exists to "
        "reject -- narrow SCOPE_WINDOW until this control fails again")


@needs_notes
def test_the_v2_inherited_split_is_stated_where_the_deliverable_is_described():
    """The deliverable's own note must carry the v2 numbers, not only the Phase-1 ones."""
    text = _notes_sources()["features_07_12.py"]
    assert "0.178" in text, "the deliverable note must state how much of the thermocline error is ours"
    assert "1.042" in text, "and the reanalysis's own error at the same depth, so it can be compared"


# ── the deck must quote the deliverable, not the comparator ─────────────────────────────

@needs_deck
def test_the_deck_headline_matches_the_frozen_manifest():
    """Every headline figure the deck states must be the one the freeze recorded."""
    if not os.path.exists(MANIFEST):
        pytest.skip("no frozen_manifest.json on this machine")
    import json

    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    claim = man["claims"][man["deliverable_key"]]
    blob = " ".join(_deck_text().values())
    for key, dp in (("overall_rmse", 4), ("overall_correlation", 4),
                    ("overall_bias", 4), ("overall_skill_rmse_ratio", 4)):
        want = f"{claim[key]:.{dp}f}".lstrip("0") if claim[key] < 1 else f"{claim[key]:.{dp}f}"
        assert want in blob.replace("+0.", "0."), (
            f"the deck does not state the frozen {key} ({claim[key]:.4f}). A deck that quotes a "
            f"different run than the manifest is quoting a model it did not freeze.")


@needs_deck
def test_the_deck_does_not_present_the_glorys_comparator_as_the_result():
    """The comparator may be NAMED -- refusing to ship it is one of the project's better lines --
    but its metrics must never stand where the deliverable's belong."""
    for part, text in _deck_text().items():
        for metric in COMPARATOR_METRICS:
            assert metric not in text, (
                f"{part} carries {metric}, a metric of the GLORYS-fed comparator "
                f"(tscast_stage1_embargo_withUV_s42). Its inputs are reanalysis, so it fails the "
                f"PS's satellite-only requirement and cannot be presented as the result.")


# ── internal consistency ────────────────────────────────────────────────────────────────

@needs_deck
def test_the_deck_never_claims_climatology_is_beaten_at_every_depth():
    """Climatology wins at 1000 m by 0.012 degC. One slide said 14 of 15 and the next said 15,
    which is the kind of contradiction a reviewer reads out loud."""
    banned = ("at all 15 depths", "every one of the 15 depths", "at all fifteen depths",
              "no depth where the seasonal average")
    for part, text in _deck_text().items():
        low = text.lower()
        for phrase in banned:
            assert phrase.lower() not in low, (
                f"{part} claims climatology is beaten everywhere. It is beaten at 14 of 15 "
                f"depths; at 1000 m climatology wins by 0.012 degC.")


@needs_notes
def test_the_buoy_series_are_not_described_as_independent_validation():
    """The buoy fetch succeeded on 2026-09-06, but every series lies inside the training period,
    so it is an in-sample check. Calling it blocked was wrong; calling it independent validation
    would be worse."""
    text = _notes_sources()["note_19_conclusion.py"]
    assert "blocked, not done" not in text, (
        "the buoy validation is no longer blocked -- artifacts/buoy_validation.json holds 46 "
        "scored series")
    assert re.search(r"in-sample|IN-SAMPLE", text), (
        "the buoy result must be labelled in-sample: its series span the training period and "
        "moored profiles feed the reanalysis the model is trained against")


# ── the live UI must quote the CURRENT scoring protocol (audit 2026-09-07) ──────────────
#
# From 2026-09-07 the deliverable is scored under seafloor_masked_v1 (eval_argo). The previous
# headline, 0.9078 under unmasked_v1, may still appear in the app only where it is labelled as
# such: a page that describes an experiment whose artifact was scored under the old protocol, or a
# line that names it as superseded. A bare 0.9078 presented as the current error is the defect
# `app/ui/data.py` warns about in its own docstring: a UI that hardcodes the number "will still say
# 0.9078 after the model changes". It did.

APP_DIR = os.path.join(REPO, "app")
SUPERSEDED_HEADLINE = ("0.9078", "0.2595", "12,829", "12829")
LABELS = ("unmasked", "superseded", "before 2026-09-07", "old protocol", "previous protocol")


def _app_sources() -> dict[str, list[str]]:
    out = {}
    for root, _dirs, files in os.walk(APP_DIR):
        for name in files:
            if name.endswith(".py"):
                p = os.path.join(root, name)
                with open(p, encoding="utf-8") as f:
                    out[os.path.relpath(p, REPO)] = f.read().splitlines()
    return out


def test_the_app_does_not_present_the_superseded_headline_as_current():
    offenders = []
    for path, lines in _app_sources().items():
        for i, line in enumerate(lines, 1):
            if any(tok in line for tok in SUPERSEDED_HEADLINE):
                window = " ".join(lines[max(0, i - 3):i + 2]).lower()
                if not any(lbl in window for lbl in LABELS):
                    offenders.append(f"{path}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "these lines present the unmasked_v1 headline (0.9078 / +0.2595 / 12,829) as the current "
        "number. The deliverable is scored under seafloor_masked_v1 since 2026-09-07; either read the "
        "figure from artifacts/frozen_manifest.json or label the line as the superseded protocol:\n  "
        + "\n  ".join(offenders))


def test_the_manifest_deliverable_is_scored_under_the_current_protocol():
    """If someone re-freezes from the unmasked training JSON, the deck/manifest test above would
    happily pass against the wrong protocol. Pin the protocol itself."""
    if not os.path.exists(MANIFEST):
        pytest.skip("no frozen_manifest.json on this machine")
    import json
    from phase2.tscast_nio import eval_argo as EA

    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    claim = man["claims"][man["deliverable_key"]]
    assert claim.get("scoring_protocol") == EA.SCORING_PROTOCOL, (
        f"the deliverable is frozen under {claim.get('scoring_protocol')!r}, the code scores under "
        f"{EA.SCORING_PROTOCOL!r}: re-run rescore_checkpoint.py and freeze_headline.py")
    assert claim.get("refusals", {}).get("n_refused_below_seafloor") is not None, (
        "a claim under the masked protocol must carry its refusal count beside the score")


# --------------------------------------------------------------- the selection leak, stated

SELECTION_LEAK_WORDS = ("chose its epoch", "chosen on the test", "selection leak",
                        "epoch was chosen", "selected on the test", "test_period_v0")


def test_the_manifest_says_how_the_deliverable_chose_its_epoch():
    """The shipped checkpoint selected its epoch on the days it is scored on. It ships anyway, by
    decision (2026-09-07), so the manifest must SAY so rather than leave it to a reader who knows
    what date the bug was fixed."""
    man = json.load(open(os.path.join(REPO, "artifacts", "frozen_manifest.json"), encoding="utf-8"))
    d = man["claims"]["deliverable_satellite"]
    assert d.get("selection_protocol"), "the deliverable records no selection protocol"
    if d["selection_protocol"] == "test_period_v0":
        leak = d.get("selection_leak")
        assert leak, "a test_period_v0 deliverable must carry its selection_leak block"
        for k in ("what", "measured_cost_degC", "confound", "why_shipped", "fixed_in"):
            assert leak.get(k), f"selection_leak is missing {k}"
        assert leak["measured_cost_degC"] > 0


def test_the_jury_notes_state_the_selection_leak():
    """A juror reading the conclusion must find it without asking. Checked on the note SOURCES,
    which is what a rebuild regenerates, not on the built PDFs."""
    blob = ""
    for name in ("note_19_conclusion.py", "note_01_problem.py", "features_07_12.py"):
        p = os.path.join(REPO, "JURY_NOTES", "_build", name)
        if os.path.exists(p):
            blob += io.open(p, encoding="utf-8").read().lower()
    assert any(w.lower() in blob for w in SELECTION_LEAK_WORDS), (
        "no jury note mentions that the shipped epoch was chosen on the scored period")


def test_the_project_record_lists_the_selection_leak_as_a_flaw():
    rec = io.open(os.path.join(REPO, "PROJECT_RECORD.md"), encoding="utf-8").read().lower()
    assert any(w.lower() in rec for w in SELECTION_LEAK_WORDS), (
        "PROJECT_RECORD does not list the selection leak among the flaws"
    )
    assert "0.0824" in rec, "PROJECT_RECORD does not carry the measured cost of the leak"
