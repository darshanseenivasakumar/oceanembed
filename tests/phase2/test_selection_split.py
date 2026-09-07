"""Model selection must not read the period the headline is scored on (audit finding #7).

`train_stage1` used to build its early-stopping loader from the test indices and keep the epoch
with the lowest NLL on them, then score the Argo headline on those same days. These tests pin the
replacement, `dataset.selection_split`, and -- in `test_the_legacy_arrangement_fails_this_check` --
prove that the property actually catches the bug rather than passing vacuously.
"""
import io
import os

import numpy as np
import pytest

from phase2.tscast_nio import dataset as D


def toy(n_train=80, n_test=20):
    """A bundle of consecutive days: train first, test strictly after."""
    start = np.datetime64("2025-01-01", "D")
    times = start + np.arange(n_train + n_test, dtype="timedelta64[D]")
    tr = np.arange(n_train)
    te = np.arange(n_train, n_train + n_test)
    return times, tr, te


# ---------------------------------------------------------------- the property


def test_the_selection_set_is_carved_from_train_and_never_touches_the_test_block():
    times, tr, te = toy()
    tr_keep, va, info = D.selection_split(times, tr, te, t_seq=11, val_days=20)

    assert np.intersect1d(va, te).size == 0, "the selection set overlaps the scored block"
    assert np.intersect1d(va, tr_keep).size == 0
    assert set(va.tolist()) <= set(tr.tolist()), "the val block must come out of TRAIN"
    assert info["selection_protocol"] == "val_carved_v1"


def test_the_split_is_chronological_not_random():
    times, tr, te = toy()
    tr_keep, va, _ = D.selection_split(times, tr, te, t_seq=11, val_days=20)
    assert tr_keep.max() < va.min(), "every validation day must follow every training day"


def test_a_training_window_cannot_reach_the_validation_block():
    times, tr, te = toy()
    for t_seq in (1, 3, 11, 31):
        tr_keep, va, _ = D.selection_split(times, tr, te, t_seq=t_seq, val_days=45)
        h = t_seq // 2
        assert tr_keep.max() + h < va.min(), (
            f"T_SEQ={t_seq}: a training target reads the val block it is selected on")


def test_a_validation_window_cannot_reach_the_test_block():
    times, tr, te = toy()
    for t_seq in (1, 3, 11, 31):
        _, va, _ = D.selection_split(times, tr, te, t_seq=t_seq, val_days=45)
        h = t_seq // 2
        assert va.max() + h < te.min(), (
            f"T_SEQ={t_seq}: the selection signal reads surface fields from the scored block")


def test_the_train_to_test_embargo_still_holds_for_free():
    """It is implied -- val sits between them -- but the run must not depend on that reasoning."""
    times, tr, te = toy()
    tr_keep, _, _ = D.selection_split(times, tr, te, t_seq=11, val_days=20)
    assert tr_keep.max() + 11 // 2 < te.min()


def test_the_legacy_arrangement_fails_this_check():
    """The control. Selecting on the test block -- what train_stage1 did until 2026-09-07 -- must
    violate the very property the tests above assert, or those tests prove nothing."""
    _, _, te = toy()
    legacy_selection_set = te                      # exactly what `ds_te` was built from
    scored_block = te
    assert np.intersect1d(legacy_selection_set, scored_block).size > 0, (
        "the control is broken: the legacy selection set must overlap the scored block")


# ---------------------------------------------------------------- the refusals


def test_it_refuses_a_val_block_larger_than_what_is_left_to_train_on():
    times, tr, te = toy()
    with pytest.raises(SystemExit, match="selecting on more data than it trains on"):
        D.selection_split(times, tr, te, t_seq=11, val_days=78)


def test_it_refuses_a_val_block_too_small_to_be_a_signal():
    times, tr, te = toy()
    with pytest.raises(SystemExit, match="below MIN_VAL_STEPS"):
        D.selection_split(times, tr, te, t_seq=11, val_days=2)


def test_it_refuses_when_the_embargo_eats_the_val_block():
    """A long window against a short val block leaves nothing to select on. That must be an
    error, not a silently tiny validation set."""
    times, tr, te = toy()
    with pytest.raises(SystemExit, match="after its embargo against the"):
        D.selection_split(times, tr, te, t_seq=31, val_days=16)


def test_t_seq_1_embargoes_nothing():
    times, tr, te = toy()
    tr_keep, va, info = D.selection_split(times, tr, te, t_seq=1, val_days=20)
    assert info["n_train_dropped_embargo"] == 0
    assert info["n_val_dropped_embargo"] == 0
    assert len(tr_keep) + len(va) == len(tr)


def test_the_default_reserves_the_configured_fraction():
    times, tr, te = toy(n_train=200, n_test=40)
    _, _, info = D.selection_split(times, tr, te, t_seq=1, val_days=None)
    assert info["val_days_requested"] == round(200 * D.VAL_FRACTION) == 30


# ---------------------------------------------------------------- real data


@pytest.mark.parametrize("bundle", ["data/processed/daily_sat/v001"])
def test_the_shipped_bundle_splits_into_the_recorded_blocks(bundle):
    """Pinned against the real satellite bundle the deliverable trains on. If the bundle or the
    fraction changes, this fails loudly rather than moving the training set in silence."""
    import os
    if not os.path.isdir(bundle):
        pytest.skip(f"{bundle} is not on this machine")
    d = D.load_daily(bundle)
    tr, te = D.daily_split_indices(d["times"])
    assert (len(tr), len(te)) == (304, 84)

    tr_keep, va, info = D.selection_split(d["times"], tr, te, t_seq=11, val_days=None)
    assert info["val_days_requested"] == 46
    assert info["n_train_targets"] == 253
    assert info["n_val_targets"] == 41
    assert info["n_train_dropped_embargo"] == 5
    assert info["n_val_dropped_embargo"] == 5
    assert info["train_period"] == ["2025-06-01", "2026-02-08"]
    assert info["val_period"] == ["2026-02-14", "2026-03-26"]
    assert info["test_period"] == ["2026-04-01", "2026-06-23"]
    # the whole point, stated on the real data
    assert va.max() + 5 < te.min()
    assert tr_keep.max() + 5 < va.min()


# ------------------------------------------------- the wiring, not just the helper


TRAIN_SRC = os.path.join("src", "phase2", "tscast_nio", "train", "train_stage1.py")


def selection_can_see_the_test_block(src: str):
    """Read a training script and decide whether its epoch choice can see the scored period.

    `selection_split` only hands back the right indices; it cannot stop a caller from building a
    loader over the test block anyway. That is precisely what the shipped script did, so the
    wiring gets its own check. Returns (leaks, reason).
    """
    restore = src.find('model.load_state_dict(best["state"])')
    if restore < 0:
        return True, "cannot find where the best epoch is restored"
    built = src.find("ds_te = D.GriddedPatches(")
    if built < 0:
        return True, "cannot find where the test block is instantiated"
    if built < restore:
        return True, "the test block is built before the best epoch is restored"
    before = src[:restore]
    if "ds_te" in before:
        return True, "the test block is referenced during training"
    loop = src.find("for ep in range(a.epochs)")
    if loop < 0 or "va_loader" not in src[loop:restore]:
        return True, "the epoch loop does not evaluate on the validation loader"
    return False, "selection reads the validation block only"


def test_the_training_script_cannot_select_on_the_test_block():
    """Stage 1 only, deliberately.

    `train/train_stage2.py` had the identical wiring and is fixed the same way in the working
    tree, but that file also carries another session's uncommitted work, so the fix could not be
    committed with this test. Add `train_stage2.py` to this check once that work lands -- running
    `selection_can_see_the_test_block` on it is the whole change.
    """
    src = io.open(TRAIN_SRC, encoding="utf-8").read()
    leaks, why = selection_can_see_the_test_block(src)
    assert not leaks, f"{TRAIN_SRC}: {why}"


def test_the_wiring_check_catches_the_shape_of_the_original_bug():
    """The control. The pre-fix arrangement -- test block built up front and used as the
    early-stopping set -- must be flagged, or the check above proves nothing."""
    legacy = (
        '    ds_te = D.GriddedPatches(surface, temp, times, land, chans, te_t, norm=ds_tr.norm)\n'
        '    te_loader = DataLoader(ds_te, batch_size=512)\n'
        '    for ep in range(a.epochs):\n'
        '        for batch in te_loader:\n'
        '            vt += heldout(batch)\n'
        '    model.load_state_dict(best["state"])\n'
    )
    leaks, why = selection_can_see_the_test_block(legacy)
    assert leaks, "the control is broken: the legacy wiring must be flagged"
    assert "before the best epoch is restored" in why


# ------------------------------------------------- multi-block seasonal selection


def test_multi_block_purges_the_training_set_on_both_sides_of_every_block():
    """A single trailing block only needs purging on its leading edge. Interior blocks need it on
    both, and `embargo_indices` cannot express that -- so it is asserted on the real geometry."""
    times, tr, te = toy(n_train=300, n_test=80)
    t_seq = 11
    h = t_seq // 2
    tr_keep, va, info = D.selection_split(times, tr, te, t_seq=t_seq, val_days=45, n_blocks=3)

    assert info["n_blocks"] == 3
    held = set(va.tolist()) | set(te.tolist())
    for i in tr_keep:
        window = set(range(max(0, int(i) - h), int(i) + h + 1))
        assert not (window & held), f"training target {int(i)} reads a held-out day"


def test_multi_block_blocks_do_not_overlap_or_touch():
    times, tr, te = toy(n_train=300, n_test=80)
    _, _, info = D.selection_split(times, tr, te, t_seq=11, val_days=45, n_blocks=3)
    spans = [(np.datetime64(a), np.datetime64(b)) for a, b in info["blocks"]]
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert start > end, "two selection blocks overlap"


def test_multi_block_spans_more_seasons_than_one_trailing_block():
    """The whole point. One trailing block sees the two months before the test window; spreading
    the same budget across the year reaches the season the test window is actually in."""
    times, tr, te = toy(n_train=300, n_test=80)
    _, _, one = D.selection_split(times, tr, te, t_seq=11, val_days=45, n_blocks=1)
    _, _, many = D.selection_split(times, tr, te, t_seq=11, val_days=45, n_blocks=3)
    assert len(many["val_months"]) > len(one["val_months"])


def test_one_block_is_still_the_trailing_block():
    """The regression pin. Adding n_blocks must not move any run already measured."""
    times, tr, te = toy(n_train=300, n_test=80)
    a1, v1, i1 = D.selection_split(times, tr, te, t_seq=11, val_days=45)
    a2, v2, i2 = D.selection_split(times, tr, te, t_seq=11, val_days=45, n_blocks=1)
    assert np.array_equal(a1, a2) and np.array_equal(v1, v2)
    assert v1.max() == max(tr) - 11 // 2, "the single block must still sit at the END of train"
    assert i1["val_period"] == i2["val_period"]


def test_it_refuses_blocks_that_cannot_fit_with_their_purge():
    times, tr, te = toy(n_train=60, n_test=20)
    with pytest.raises(SystemExit, match="do not fit"):
        D.selection_split(times, tr, te, t_seq=11, val_days=40, n_blocks=4)


def test_it_refuses_blocks_too_small_to_be_a_signal():
    times, tr, te = toy(n_train=300, n_test=80)
    with pytest.raises(SystemExit, match="below MIN_VAL_STEPS"):
        D.selection_split(times, tr, te, t_seq=11, val_days=8, n_blocks=4)


def test_the_shipped_bundle_gets_a_same_season_block(tmp_path):
    """On the real bundle the train block opens in June, the same month as the back half of the
    scored window. A trailing block can never reach it; three blocks can."""
    import os
    bundle = "data/processed/daily_sat/v001"
    if not os.path.isdir(bundle):
        pytest.skip(f"{bundle} is not on this machine")
    d = D.load_daily(bundle)
    tr, te = D.daily_split_indices(d["times"])
    _, _, one = D.selection_split(d["times"], tr, te, t_seq=11, val_days=45, n_blocks=1)
    _, _, many = D.selection_split(d["times"], tr, te, t_seq=11, val_days=45, n_blocks=3)

    test_months = {4, 5, 6}
    assert not (set(one["val_months"]) & test_months), "the trailing block has no test-season day"
    assert set(many["val_months"]) & test_months, "three blocks should reach the test season"
    assert many["n_train_targets"] == 239
    assert many["n_val_targets"] == 40
