"""Cyclone tracks and the cold wake. Owner: Unit A (Arjhun).

Two failures worth guarding, neither of which raises.

A BLANK WIND READ AS ZERO. IBTrACS leaves `WMO_WIND` empty for storms no WMO agency rated. `int(x
or 0)` turns that into a calm cyclone, and `peak_index` then puts the "during" panel of a case
study at genesis.

A WAKE MEASURED AGAINST THE WRONG DATES. One fixed before/after pair asks the wrong question at
every track point but one, and returns a null result from data that plainly contains a wake. That
is not a crash; it is a confident "no signal".
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.data import ibtracs as IB
from phase2.derived import cyclone as CY

CSV = IB.DEFAULT_PATH
D = base.N_DEPTHS


def a_storm(n=9, lat0=20.0, lon0=68.0, dlon=-1.0, winds=None):
    """A westward storm, one point per day from 2025-10-01."""
    t = [f"2025-10-{1 + i:02d} 00:00:00" for i in range(n)]
    return {
        "sid": "TEST", "name": "TESTY", "time": t,
        "lat": np.full(n, lat0), "lon": lon0 + dlon * np.arange(n, dtype="float64"),
        "wind_kt": list(winds) if winds is not None else [20 + 5 * i for i in range(n)],
        "track_types": ["TEST"],
    }


def tchp_fields(dates, *, base_value=40.0, wake=None):
    """A flat TCHP field per date. `wake` = {date: {(lat,lon): value}} overrides specific cells."""
    lat_g, lon_g = np.asarray(base.LAT), np.asarray(base.LON)
    out = {}
    for d in dates:
        f = np.full((lat_g.size, lon_g.size), base_value)
        for (la, lo), v in (wake or {}).get(d, {}).items():
            i = int(np.argmin(np.abs(lat_g - la)))
            j = int(np.argmin(np.abs(lon_g - lo)))
            f[max(0, i - 2):i + 3, max(0, j - 2):j + 3] = v
        out[d] = f
    return out


# ==================================================== the archive

def test_a_blank_wind_is_none_and_never_zero():
    """`float("")` raises and `int(x or 0)` lies. A storm no agency rated is UNRATED, and calling
    it a calm cyclone would put a case study's peak at genesis."""
    assert IB._num({"WMO_WIND": ""}, "WMO_WIND") is None
    assert IB._num({"WMO_WIND": "  "}, "WMO_WIND") is None
    assert IB._num({"WMO_WIND": "NOT_NAMED"}, "WMO_WIND") is None
    assert IB._num({"WMO_WIND": "60"}, "WMO_WIND") == 60.0
    assert IB.category(None) == "unrated"
    assert IB.category(0.0) == "depression", "0 kt is a real reading, unlike a blank"


def test_peak_index_is_none_for_an_unrated_storm_not_zero():
    s = a_storm(winds=[None] * 5)
    assert IB.peak_index(s) is None
    assert IB.case_study_dates(s)["peak_index"] is None


def test_the_case_study_brackets_the_PEAK_not_the_midpoint():
    """The wake is cut by the strongest winds; centring on the storm's midpoint would blur it."""
    s = a_storm(n=7, winds=[20, 30, 90, 40, 35, 25, 20])
    cs = IB.case_study_dates(s, before_days=3, after_days=5)
    assert cs["peak_index"] == 2 and cs["peak_wind_kt"] == 90
    assert cs["during"] == "2025-10-03"
    assert cs["before"] == "2025-09-30" and cs["after"] == "2025-10-08"


def test_the_after_window_is_longer_than_the_before_window_by_default():
    """A wake takes days to form and persists; the ocean ahead of a storm is undisturbed."""
    assert CY.DEFAULT_AFTER_DAYS > CY.DEFAULT_BEFORE_DAYS


def test_in_box_reports_membership_and_does_not_clip():
    s = a_storm(n=5, lon0=104.0, dlon=1.0)          # runs off the eastern edge
    inside = IB.in_box(s, lat=(5.0, 30.0), lon=(45.0, 104.75))
    assert inside.sum() < inside.size
    assert s["lon"].max() > 104.75, "the track itself must be untouched -- clipping it would be a "\
                                    "statement about the grid drawn as a statement about the storm"


@pytest.mark.skipif(not os.path.exists(CSV), reason="IBTrACS csv not on this machine")
def test_the_units_row_is_skipped_and_real_storms_load():
    """Row 1 is units -- SEASON reads 'Year', LAT reads 'degrees_north'. Parsed as data it becomes
    a storm at an impossible position."""
    tracks = IB.load_tracks(window=("2025-06-01", "2026-06-23"))
    assert len(tracks) > 5
    for s in tracks.values():
        assert 0.0 <= float(s["lat"].min()) and float(s["lat"].max()) < 40.0
        assert len(s["time"]) == s["lat"].size == s["lon"].size == len(s["wind_kt"])
        assert s["name"] != "NAME"


@pytest.mark.skipif(not os.path.exists(CSV), reason="IBTrACS csv not on this machine")
def test_both_agencies_are_carried_because_they_disagree():
    """MEASURED on SHAKHTI: WMO peaks at 60 kt over 41 rated points, the US agency at 74 over 29 --
    14 kt apart, spanning the tropical-storm / Category-1 boundary. Reporting one silently, or the
    max across both, presents a choice between two estimates as a single fact."""
    s = IB.load_tracks(window=("2025-06-01", "2026-06-23"))["2025275N22068"]
    assert s["name"] == "SHAKHTI"
    assert s["max_wind_kt_wmo"] == 60.0
    assert s["max_wind_kt_usa"] == 74.0
    assert s["agencies_disagree_kt"] == 14.0
    assert s["max_wind_kt"] == s["max_wind_kt_wmo"], "the WMO archive's own figure is preferred"
    assert s["track_types"] == ["US-PROVISIONAL"]


# ==================================================== the wake, measured correctly

def test_dates_needed_asks_once_per_day_not_once_per_track_point():
    """IBTrACS is 3- or 6-hourly; a caller reconstructing per point would build the same field
    four times over."""
    s = a_storm(n=8)
    s["time"] = [f"2025-10-0{1 + i // 4} {6 * (i % 4):02d}:00:00" for i in range(8)]
    need = CY.dates_needed(s, before_days=1, after_days=1)
    assert len(need) == len(set(need)) == 4          # 2 distinct days x (before, after)


def test_a_passage_relative_wake_is_found_where_a_fixed_pair_finds_nothing():
    """THE test for this feature. Same synthetic storm, same TCHP fields, two questions.

    The storm crosses west one degree a day. Each cell cools only AFTER the storm reaches it and
    then recovers. A fixed 'after' date therefore catches early points already recovered and late
    points still cold, and the two cancel.
    """
    s = a_storm(n=7, lat0=20.0, lon0=68.0, dlon=-1.0)
    dates = sorted({d for d in CY.dates_needed(s, before_days=2, after_days=3)}
                   | {t[:10] for t in s["time"]})

    # build fields where cell k is cold for exactly 4 days after the storm passes it
    lat_g, lon_g = np.asarray(base.LAT), np.asarray(base.LON)
    fields = {}
    for d in dates:
        f = np.full((lat_g.size, lon_g.size), 40.0)
        for k in range(len(s["time"])):
            passed = np.datetime64(s["time"][k][:10])
            age = (np.datetime64(d) - passed).astype(int)
            if 0 <= age <= 4:
                i = int(np.argmin(np.abs(lat_g - s["lat"][k])))
                j = int(np.argmin(np.abs(lon_g - s["lon"][k])))
                f[max(0, i - 2):i + 3, max(0, j - 2):j + 3] = 40.0 - 8.0
        fields[d] = f

    rel = CY.cold_wake(s, fields, before_days=2, after_days=3)
    assert rel["n_points"] == 7
    assert rel["fraction_cooled"] == 1.0
    assert rel["mean_change"] < -5.0
    assert rel["verdict"] == "cold wake resolved"

    # The claim is that a fixed pair UNDERSTATES the wake, not that it returns exactly zero. On
    # this fixture only the last two points are still cold at the fixed 'after' date, so the naive
    # answer is diluted to about a quarter of the true one. On the real storm the dilution goes
    # further and the answer is a null (-0.18 against -4.26), because the ocean's own variability
    # warms some already-recovered points. Asserting "zero" here would be asserting a property of
    # real data that this fixture does not have.
    naive = CY.naive_wake(s, fields, dates[0], dates[-1])
    assert abs(naive["mean_change"]) < 0.5 * abs(rel["mean_change"]), (
        f"the fixed pair found {naive['mean_change']:+.2f} against the passage-relative "
        f"{rel['mean_change']:+.2f} -- the fixture is not exercising the difference this feature "
        f"exists for")


def test_a_point_with_no_field_or_no_water_is_skipped_and_counted_not_filled():
    """Scoring a missing point as zero change would read as 'the storm did nothing here'."""
    s = a_storm(n=3)
    fields = tchp_fields(CY.dates_needed(s, before_days=1, after_days=1)[:2])
    r = CY.cold_wake(s, fields, before_days=1, after_days=1)
    assert r["skipped"]["no_field"] > 0
    assert all(np.isfinite(p["change"]) for p in r["points"])

    nan_fields = {d: np.full((base.N_LAT, base.N_LON), np.nan)
                  for d in CY.dates_needed(s, before_days=1, after_days=1)}
    r2 = CY.cold_wake(s, nan_fields, before_days=1, after_days=1)
    assert r2["n_points"] == 0 and r2["skipped"]["not_finite"] > 0
    assert r2["verdict"] == "no track point could be evaluated"


def test_the_verdict_refuses_to_call_a_null_result_a_wake():
    """A number is easy to render as a finding. The verdict is a string precisely so a page cannot
    put '-0.2 kJ/cm2' under the word 'wake'."""
    s = a_storm(n=5)
    flat = tchp_fields(CY.dates_needed(s, before_days=1, after_days=1))
    r = CY.cold_wake(s, flat, before_days=1, after_days=1)
    assert r["mean_change"] == 0.0
    assert r["verdict"] == "no clear cold wake in this reconstruction"


def test_stride_reduces_the_sample_without_changing_which_points_are_valid():
    s = a_storm(n=8)
    f = tchp_fields(CY.dates_needed(s, before_days=1, after_days=1))
    every = CY.cold_wake(s, f, before_days=1, after_days=1, stride=1)
    every_other = CY.cold_wake(s, f, before_days=1, after_days=1, stride=2)
    assert every["n_points"] == 8 and every_other["n_points"] == 4
    assert [p["index"] for p in every_other["points"]] == [0, 2, 4, 6]


# ==================================================== against the real reconstruction


def _have_model():
    return (os.path.exists(base.art("tscast_stage1.pt")) and os.path.exists(CSV)
            and os.path.isdir(os.path.join("data", "processed", "daily_sat", "v001")))


@pytest.mark.skipif(not _have_model(), reason="checkpoint, bundle or IBTrACS csv not present")
def test_the_reconstruction_resolves_shakhtis_cold_wake():
    """The acceptance check for this feature, on real data.

    MEASURED 2026-09-05: passage-relative, mean -4.26 kJ/cm2 with 11 of 12 points cooling. The
    naive fixed-pair version of the SAME data returns -0.18 and 7 of 12 -- which is why the page
    shows both. If this ever stops holding, the page's headline is wrong and must be rewritten
    rather than the threshold relaxed.
    """
    from phase2.derived import heat_content as HC
    from phase2.tscast_nio import field_cache as FC

    s = IB.load_tracks(window=("2025-06-01", "2026-06-23"))["2025275N22068"]
    # stride=4 throughout: `dates_needed` honours it, so this reconstructs the days actually
    # sampled rather than every day of the storm.
    tchp = {d: HC.heat_content_field(FC.field_for(d))["tchp"]
            for d in CY.dates_needed(s, stride=4)}

    w = CY.cold_wake(s, tchp, stride=4)
    assert w["n_points"] >= 10
    assert w["fraction_cooled"] >= 0.8, f"only {w['fraction_cooled']:.0%} of points cooled"
    assert w["mean_change"] < -2.0, f"mean change {w['mean_change']:+.2f} kJ/cm2"
    assert w["verdict"] == "cold wake resolved"

    naive = CY.naive_wake(s, tchp, "2025-10-02", "2025-10-10", stride=4)
    assert abs(naive["mean_change"]) < 1.0, (
        "the fixed-pair comparison no longer returns a null result -- the page's central "
        "methodological point needs re-measuring")
