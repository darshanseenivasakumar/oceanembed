"""Ocean structure (F5) wired onto the v2 satellite model. Owner: Unit A (Arjhun).

WHY THIS FILE EXISTS, NOT MORE CASES IN test_physics.py
test_physics.py checks the SCIENCE in `phase2.physics` against synthetic profiles where the
answer is analytically forced. This file checks the WIRING added 2026-09-03: that physics_page
and cube_page ask the v2 model for temperature-only fields correctly, refuse what needs salinity
rather than approximating it, and never again offer the wrong calendar -- the exact bug this
change fixed in cube_page (GLORYS' 48 2019-2022 dates offered while v2 silently reconstructed
1052 days away, unannounced) and avoided from the start in physics_page.

Real data throughout, not synthetic profiles -- shape and plausibility on a fabricated profile
would not have caught either the calendar bug or the missing `_v2_version` (a NameError only the
selected branch executing would surface; caught here by actually calling it, not by reading it).
"""
from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

pytest.importorskip("torch")

from oceanembed import config as base  # noqa: E402

if not os.path.exists(base.art("tscast_stage1.pt")):
    pytest.skip("no shipped checkpoint on this machine", allow_module_level=True)

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _load(modname: str, relpath: str):
    """Import a Streamlit page module by path.

    `st.set_page_config`/`st.cache_data`/`st.cache_resource` are all safe to hit outside a live
    app -- they warn ("missing ScriptRunContext") and fall back to in-memory caching, verified by
    hand before relying on it here. Module-scoped so the checkpoint loads once for this file, the
    same amortisation test_field.py's `predictor` fixture uses.
    """
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, relpath))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def physics_page():
    return _load("physics_page_under_test", "app/phase2/physics_page.py")


@pytest.fixture(scope="module")
def cube_page():
    return _load("cube_page_under_test", "app/phase2/cube_page.py")


@pytest.fixture(scope="module")
def glorys_dates():
    """The OTHER calendar -- GLORYS 2019-2022 monthly -- so v2's list can be checked against it."""
    import numpy as np
    from oceanembed import config as base
    z = np.load(os.path.join(base.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    return [str(t)[:10] for t in np.asarray(z["times"])]


# --------------------------------------------------------------------------- the calendar bug


def test_v2_dates_are_disjoint_from_the_glorys_calendar(physics_page, glorys_dates):
    """The bug this regresses: v2's real span is 2025-06-01..2026-06-23; GLORYS is 2019-2022.
    Any overlap would mean the two calendars are being confused again."""
    v2 = set(physics_page._v2_dates(physics_page._v2_version()))
    assert not v2 & set(glorys_dates)
    assert min(v2) >= "2025-01-01"
    assert max(glorys_dates) <= "2022-12-31"


def test_cube_page_v2_dates_are_also_disjoint_from_glorys(cube_page, glorys_dates):
    """cube_page had the actual bug (offered GLORYS dates under 'v2 satellite'); this is its
    regression test, not physics_page's."""
    v2 = set(cube_page._v2_dates(cube_page._v2_version()))
    assert not v2 & set(glorys_dates)


def test_cube_page_v2_native_date_has_zero_offset(cube_page):
    """Before the fix: selecting the selector's own default (a GLORYS date) snapped +1052 days
    on the v2 path, with nothing on screen saying so. A date FROM the v2 list must snap 0 days."""
    v = cube_page._v2_version()
    dates = cube_page._v2_dates(v)
    d = dates[max(0, len(dates) - 6)]           # the same index the sidebar defaults to
    cube = cube_page.build_cube(d, "v2 satellite", False, v)
    assert cube.provenance["days_from_requested"] == 0
    assert cube.date == d


# --------------------------------------------------------------------------- the refusal


def test_v2_refuses_mld_and_barrier_layer(physics_page):
    """No salinity reaches this model -- MLD and barrier layer must be None, not a fallback
    number computed some other way."""
    v = physics_page._v2_version()
    dates = physics_page._v2_dates(v)
    fields = physics_page.layer_fields_v2(dates[-1], v)
    assert fields["MLD (density, m)"] is None
    assert fields["Barrier layer (m)"] is None


def test_v2_thermocline_ild_ohc_are_real_and_physically_plausible(physics_page):
    """The three fields temperature alone supports must be present, finite over real ocean, and
    in range -- not NaN-everywhere placeholders standing in for "not implemented"."""
    v = physics_page._v2_version()
    dates = physics_page._v2_dates(v)
    f = physics_page.layer_fields_v2(dates[-1], v)

    ocean = int((~f["land_mask"]).sum())
    assert ocean > 10_000                                        # ~11,832 on this grid

    th, ild, ohc_ = (f["Thermocline depth (m)"], f["ILD (temperature, m)"],
                     f["OHC 0–300 m (GJ/m²)"])
    for name, arr, lo, hi, min_finite in (
        ("thermocline", th, 0.0, 1000.0, ocean * 0.5),
        ("ILD", ild, 0.0, 1000.0, ocean * 0.5),
        ("OHC", ohc_, 0.0, 60.0, ocean * 0.5),
    ):
        fin = np.isfinite(arr)
        assert fin.sum() >= min_finite, f"{name}: only {fin.sum()} finite cells of {ocean} ocean"
        assert lo <= np.nanmin(arr) and np.nanmax(arr) <= hi, f"{name} out of [{lo}, {hi}]"


def test_v2_never_calls_the_salinity_functions(physics_page):
    """Structural guard on `layer_fields_v2` specifically -- not the whole file, since the glorys
    branch legitimately calls all four. Regresses a future 'fix' that quietly reintroduces a
    salinity call (e.g. falling back to GLORYS S under the v2 label) instead of keeping the
    refusal. Source-text, not execution, because that IS the property under test: the call must
    be structurally absent, not merely unexercised on today's inputs.
    """
    src = open(os.path.join(ROOT, "app/phase2/physics_page.py"), encoding="utf-8").read()
    start = src.index("def layer_fields_v2")
    end = src.index("\n@st.cache_data", start + 10) if "\n@st.cache_data" in src[start + 10:] \
        else src.index("\ndef ", start + 10)
    body = src[start:end]
    for forbidden in ("mixed_layer_depth(", "barrier_layer_thickness(", "ohc.ohc("):
        assert forbidden not in body, f"{forbidden} must not appear in layer_fields_v2"
    assert "ohc_constant_density(" in body


# --------------------------------------------------------------------------- shared cache key


def test_v2_cache_version_is_one_function_not_three_copies():
    """field.v2_cache_version was factored out of three near-identical copies (tscast_page,
    cube_page, physics_page) after the second copy was the one that actually went stale for 9.5
    minutes. Both page-local wrappers must delegate to it, not reimplement it."""
    from phase2.tscast_nio import field

    assert callable(field.v2_cache_version)
    v1 = field.v2_cache_version()
    v2 = field.v2_cache_version()
    assert v1 == v2 and len(v1) == 16

    for modname, relpath in (("physics_page_src", "app/phase2/physics_page.py"),
                             ("cube_page_src", "app/phase2/cube_page.py")):
        src = open(os.path.join(ROOT, relpath), encoding="utf-8").read()
        assert "v2_cache_version" in src, f"{relpath} does not delegate to the shared helper"


# --------------------------------------------------------------------------- glorys, same day


def test_both_sources_read_the_same_day_from_the_same_bundle(physics_page):
    """The toggle is a model-vs-truth comparison, not two eras.

    This page shipped reading Phase-1 GLORYS monthly 2019-2022 while the model ran on 2025-2026,
    with nothing on screen saying so -- the user question that started this. Both branches must
    now resolve the same requested date.
    """
    v = physics_page._v2_version()
    dates = physics_page._v2_dates(v)
    d = dates[len(dates) - 6]
    g = physics_page.layer_fields_glorys(d, v)
    f2 = physics_page.layer_fields_v2(d, v)
    assert g["date"] == d
    assert f2["date"][:10] == d
    assert not g["date"].startswith("2019") and not g["date"].startswith("2022")


def test_glorys_source_computes_all_four_fields_with_real_density(physics_page):
    """What v2 refuses, glorys supplies -- because there the salinity is honestly labelled."""
    v = physics_page._v2_version()
    dates = physics_page._v2_dates(v)
    g = physics_page.layer_fields_glorys(dates[len(dates) - 6], v)

    ocean = int((~g["land_mask"]).sum())
    for name, lo, hi in (("MLD (density, m)", 0.0, 1000.0),
                         ("Barrier layer (m)", 0.0, 1000.0),
                         ("Thermocline depth (m)", 0.0, 1000.0),
                         ("ILD (temperature, m)", 0.0, 1000.0),
                         ("OHC 0–300 m (GJ/m²)", 0.0, 60.0)):
        a = g[name]
        assert a is not None, f"{name} must be computed on glorys, not refused"
        fin = np.isfinite(a)
        assert fin.sum() >= ocean * 0.5, f"{name}: only {fin.sum()} finite of {ocean} ocean cells"
        assert lo <= np.nanmin(a) and np.nanmax(a) <= hi, f"{name} out of [{lo}, {hi}]"

    assert np.isfinite(g["salinity"]).any(), "glorys branch must carry real subsurface salinity"
    assert "ρ(S, θ)" in g["provenance"]["density"]


def test_v2_never_borrows_glorys_salinity_for_a_satellite_labelled_number(physics_page):
    """The compliance boundary, as a test.

    Salinity IS present in the bundle v2 reads -- that is exactly why this needs a guard rather
    than being self-evident. `layer_fields_v2` must not touch p.data["salinity"], or a reanalysis
    field ends up inside a number the UI labels "satellite".
    """
    src = open(os.path.join(ROOT, "app/phase2/physics_page.py"), encoding="utf-8").read()
    start = src.index("def layer_fields_v2")
    end = src.index("\ndef ", start + 10)
    body = src[start:end]
    code = body[body.index('"""', body.index('"""') + 3) + 3:]      # past the docstring
    assert "salinity" not in code, "layer_fields_v2 must not read salinity in its body"

    v = physics_page._v2_version()
    dates = physics_page._v2_dates(v)
    f2 = physics_page.layer_fields_v2(dates[-1], v)
    assert "salinity" not in f2, "the v2 result must not carry a salinity array at all"
    assert f2["provenance"]["input_source"] == "satellite"


# --------------------------------------------------------------------------- events page


@pytest.fixture(scope="module")
def events_page():
    return _load("events_page_under_test", "app/phase2/events_page.py")


def test_events_page_reads_the_daily_bundles_not_the_2019_2022_grids(events_page, glorys_dates):
    """Same era bug physics_page had: this page read grids.npz (48 monthly, 2019-2022) while the
    shipped model ran on 2025-2026. Both sources must now offer the daily calendar."""
    for source in ("satellite", "glorys"):
        dates = events_page.daily_dates(source)
        assert len(dates) == 388, f"{source}: expected the 388-day bundle, got {len(dates)}"
        assert not set(dates) & set(glorys_dates)
        assert dates[0].startswith("2025") and dates[-1].startswith("2026")


def test_events_reports_the_source_it_was_actually_given(events_page):
    """The hardcoded 'GLORYS reanalysis surface currents' string became false the moment this
    page could read satellite currents. Each source must describe itself correctly, and the two
    must not report the same provenance."""
    out = {}
    for source in ("satellite", "glorys"):
        dates = events_page.daily_dates(source)
        _, summary, _, _, actual, _ = events_page.detect_daily(dates[len(dates) - 6], source)
        out[source] = summary
        assert actual == dates[len(dates) - 6]

    assert "satellite" in out["satellite"]["source"].lower()
    assert "not reanalysis" in out["satellite"]["source"].lower()
    assert "glorys" in out["glorys"]["source"].lower()
    assert "not observations" in out["glorys"]["source"].lower()
    assert out["satellite"]["source"] != out["glorys"]["source"]


def test_events_detects_plausible_eddies_and_fronts_on_both_sources(events_page):
    """Real detection on real fields, both sources, same day -- not a shape check."""
    for source in ("satellite", "glorys"):
        dates = events_page.daily_dates(source)
        eddies, s, fr, vort, _, _ = events_page.detect_daily(dates[len(dates) - 6], source)
        assert 10 < s["n_eddies"] < 600, f"{source}: {s['n_eddies']} eddies is not plausible"
        assert s["n_cyclonic"] > 0 and s["n_anticyclonic"] > 0
        assert 10.0 < s["mean_radius_km"] < 300.0
        assert fr["n_fronts"] > 0
        assert np.isfinite(vort).sum() > 5_000
