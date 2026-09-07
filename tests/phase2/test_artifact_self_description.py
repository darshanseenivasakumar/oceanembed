"""An artifact must not contradict itself, and a jury-facing count must not go stale.

Two guards for the same defect class: a record that describes itself wrongly while the correct
value sits three lines away.

  * Audit #19 -- `train_stage1` wrote `train_years: list(base.TRAIN_YEARS)` on every run, so a
    daily 2025-26 artifact claimed it trained on 2019-21 and tested on 2022, directly above a
    `train_period` that said otherwise. Nothing read the fields back, so no number moved; the
    artifact was simply lying about itself.
  * The conclusion note quoted a hardcoded test count that drifted ~100 behind reality. Retyping
    it would only restart the drift, so the count is checked against the run that is happening.
"""
import io
import os
import re

import numpy as np
import pytest

from phase2.tscast_nio import dataset as D

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS = os.path.join(REPO, "artifacts")
NOTE = os.path.join(REPO, "JURY_NOTES", "_build", "note_19_conclusion.py")

#: Below this many collected tests the session is a targeted run, not the suite, and the count
#: guard cannot say anything. Chosen well under the real total so it is not a silent skip.
FULL_RUN_MIN = 900


# ------------------------------------------------------------------ the years are derived


def test_years_in_derives_the_calendar_years_a_split_covers():
    times = np.arange(np.datetime64("2025-06-01", "D"), np.datetime64("2026-07-01", "D"))
    assert D.years_in(times, np.arange(100)) == [2025]
    assert D.years_in(times, np.arange(len(times))) == [2025, 2026]
    assert D.years_in(times, [len(times) - 1]) == [2026]


@pytest.mark.parametrize("bundle", ["data/processed/daily_sat/v001"])
def test_the_shipped_split_is_2025_26_not_the_phase_1_constants(bundle):
    if not os.path.isdir(os.path.join(REPO, bundle)):
        pytest.skip(f"{bundle} is not on this machine")
    d = D.load_daily(os.path.join(REPO, bundle))
    tr, te = D.daily_split_indices(d["times"])
    assert D.years_in(d["times"], tr) == [2025, 2026]
    assert D.years_in(d["times"], te) == [2026]


def _metrics_records():
    """Records written under the CURRENT scoring protocol that carry both a period and years.

    Deliberately NOT every record on disk. Records written before the fix carry the Phase-1
    constants because that is what the code wrote when they ran, and rewriting them would falsify
    the record of an experiment -- the same reason the unmasked_v1 and seafloor_masked_v1 scores
    are kept under their own names rather than corrected in place. `years_note` is the mark the
    fixed writer leaves, so it selects records that CLAIM to be self-describing.

    That test alone would be circular -- a regression that stopped writing the note would exempt
    itself -- so `test_the_promoted_deliverable_says_which_years_it_trained_on` anchors it: what
    actually ships must carry the note AND the right years, whatever the rest of the disk holds.
    """
    import json
    out = {}
    if not os.path.isdir(ARTIFACTS):
        return out
    for fn in sorted(os.listdir(ARTIFACTS)):
        if not (fn.startswith("tscast_stage") and fn.endswith(".json")):
            continue
        try:
            with open(os.path.join(ARTIFACTS, fn), encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            continue
        if not j.get("years_note"):
            continue                      # written before audit #19: historical, left as written
        if j.get("train_period") and j.get("train_years"):
            out[fn] = j
    return out


def test_no_shipped_record_contradicts_its_own_split():
    """The guard proper. A record whose `train_years` disagrees with the years in its own
    `train_period` is describing a different experiment than the one it ran.

    Scoped to records the fixed writer produced (see `_metrics_records`); the promoted-deliverable
    test below is the non-circular anchor that stops the scoping from hiding a regression.
    """
    records = _metrics_records()
    if not records:
        pytest.skip("no current-protocol metrics records on this machine")
    bad = []
    for fn, j in records.items():
        for key, period in (("train_years", "train_period"), ("test_years", "test_period")):
            span = j.get(period)
            if not span:
                continue
            want = sorted({int(str(span[0])[:4]), int(str(span[1])[:4])})
            got = sorted(int(y) for y in j[key])
            # the period's endpoints must be inside the claimed years
            if not set(want) <= set(got):
                bad.append(f"{fn}: {key}={got} does not cover {period}={span}")
    assert not bad, (
        "these records contradict their own split (audit #19); re-score or retrain them:\n  "
        + "\n  ".join(bad))


def test_the_promoted_deliverable_says_which_years_it_trained_on():
    import json
    p = os.path.join(ARTIFACTS, "tscast_stage1_metrics.json")
    if not os.path.exists(p):
        pytest.skip("no promoted metrics on this machine")
    with open(p, encoding="utf-8") as f:
        j = json.load(f)
    assert j.get("years_note"), (
        "the promoted deliverable carries no years_note, so it was written by code that predates "
        "audit #19 -- or the fix regressed. Re-score and re-promote.")
    assert j.get("train_years") == [2025, 2026], j.get("train_years")
    assert j.get("test_years") == [2026], j.get("test_years")
    assert j.get("train_period") == ["2025-06-01", "2026-03-26"], j.get("train_period")


# ------------------------------------------------------------------ the test count is measured


def _claimed_counts() -> list[tuple[int, int]]:
    """Every "<N> passing, <M> skipped" and "<N> tests passing" the conclusion note states."""
    src = io.open(NOTE, encoding="utf-8").read()
    pairs = [(int(a), int(b)) for a, b in
             re.findall(r"(\d[\d,]*)\s+passing,\s*(\d[\d,]*)\s+skipped", src.replace(",", ""))]
    bare = [int(n) for n in re.findall(r"(\d[\d,]*)\s+tests passing", src.replace(",", ""))]
    return pairs, bare


@pytest.mark.skipif(not os.path.exists(NOTE), reason="JURY_NOTES/_build is not on this machine")
def test_the_conclusion_note_states_the_real_test_count(request):
    """Checked against THIS run's collected total, so it cannot drift again.

    Skips on a targeted run, where the collected count says nothing about the suite. That makes it
    a full-suite guard: it is silent when it cannot know, and exact when it can.
    """
    collected = len(request.session.items)
    if collected < FULL_RUN_MIN:
        pytest.skip(f"targeted run ({collected} collected); this guard needs the full suite")
    pairs, bare = _claimed_counts()
    assert pairs, "the note no longer states a 'N passing, M skipped' count"
    for passing, skipped in pairs:
        assert passing + skipped == collected, (
            f"the note claims {passing} passing + {skipped} skipped = {passing + skipped}, but the "
            f"suite collects {collected}. Update JURY_NOTES/_build/note_19_conclusion.py and "
            f"rebuild the PDFs.")
    for n in bare:
        assert n == pairs[0][0], (
            f"the note says '{n} tests passing' in one place and '{pairs[0][0]} passing' in "
            f"another; they must agree")
