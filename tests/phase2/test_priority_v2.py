"""Observation priority v2. Owner: Unit A (Arjhun).

Two classes of failure here, and neither raises.

SCIENTIFIC: computing EKE from the TOTAL current instead of its anomaly. The map then shows the
Somali Current, which is fast but perfectly well understood, and every candidate region is wrong
while looking entirely plausible.

RHETORICAL: this product is a heuristic that NOVELTY_MATRIX marks "ALREADY DONE". A page that
drifts into "the model tells INCOIS where to deploy floats" makes a claim the project has
explicitly disowned, and no numerical test would catch it -- so the wording is tested too.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config as base
from phase2.products import priority_v2 as P

NLAT, NLON, NT = base.N_LAT, base.N_LON, 40
D = base.N_DEPTHS


def currents(kind="eddy", seed=0):
    """(u, v) over NT days. 'steady' is a uniform jet with no variability at all."""
    rng = np.random.default_rng(seed)
    if kind == "steady":
        u = np.full((NT, NLAT, NLON), 1.5)
        v = np.zeros((NT, NLAT, NLON))
        return u, v
    u = rng.normal(0.0, 0.05, (NT, NLAT, NLON))
    v = rng.normal(0.0, 0.05, (NT, NLAT, NLON))
    u[:, 40:60, 20:40] += rng.normal(0.0, 0.4, (NT, 20, 20))     # an energetic patch
    u += 1.5                                                      # on top of a strong mean jet
    return u, v


# ==================================================== EKE is the anomaly, not the flow

def test_the_time_mean_of_the_eddy_component_is_zero_by_construction():
    """If the mean subtraction were missing, 'EKE' would be the kinetic energy of the mean flow and
    the map would rank the strongest currents rather than the most variable ones."""
    u, v = currents()
    k = P.eddy_kinetic_energy(u, v)
    assert np.nanmax(np.abs(np.nanmean(k["u_prime"], axis=0))) < 1e-12
    assert np.nanmax(np.abs(np.nanmean(k["v_prime"], axis=0))) < 1e-12


def test_a_strong_but_perfectly_steady_current_has_zero_eke():
    """THE test that separates the two quantities. A 1.5 m/s jet that never varies is fast and
    completely uninteresting; total kinetic energy would rank it top."""
    u, v = currents("steady")
    k = P.eddy_kinetic_energy(u, v)
    assert np.nanmax(k["eke"]) < 1e-20
    assert np.nanmax(k["mean_speed"]) == pytest.approx(1.5)


def test_eke_finds_the_variable_patch_and_not_the_mean_jet():
    u, v = currents()
    k = P.eddy_kinetic_energy(u, v)
    patch = k["eke"][40:60, 20:40]
    elsewhere = np.concatenate([k["eke"][:40].ravel(), k["eke"][60:].ravel()])
    assert np.nanmedian(patch) > 10 * np.nanmedian(elsewhere)
    # the mean speed is ~uniform, so it could NOT have produced that contrast
    assert np.nanstd(k["mean_speed"]) < 0.1 * np.nanmean(k["mean_speed"])


def test_the_window_is_centred_and_truncates_honestly_at_the_ends():
    u, v = currents()
    mid = P.eddy_kinetic_energy(u, v, t_index=NT // 2, window_days=5)
    end = P.eddy_kinetic_energy(u, v, t_index=NT - 1, window_days=5)
    assert mid["n_steps_used"] == 11
    assert end["n_steps_used"] == 6, "a window past the end must shrink, not wrap or pad"
    assert end["window"][1] == NT


def test_mismatched_or_wrongly_shaped_currents_raise():
    u, v = currents()
    with pytest.raises(ValueError):
        P.eddy_kinetic_energy(u, v[:, :10])
    with pytest.raises(ValueError):
        P.eddy_kinetic_energy(u[0], v[0])


# ==================================================== the shallow-water guard

def _fields(shallow_rows=slice(0, 20)):
    sigma = np.full((NLAT, NLON), 0.8)
    sigma[10:30, 10:30] = 1.6
    eke = np.full((NLAT, NLON), 0.01)
    eke[15:35, 15:35] = 0.2
    vm = np.ones((NLAT, NLON, D), bool)
    vm[shallow_rows, :, -1] = False          # water, but not deep enough for a float
    return sigma, eke, vm


def test_cells_too_shallow_for_a_float_are_excluded_and_counted():
    """v1 ranked the Persian Gulf, ~20 m deep, at the top: a place no float can enter is by
    definition a place with no floats. The fix lived at v1's single CALL SITE, so every new caller
    reintroduced it. Here it belongs to the product."""
    sigma, eke, vm = _fields()
    r = P.priority(sigma, eke, valid_mask=vm)
    assert r["guarded_by_valid_mask"] is True
    assert r["n_cells_excluded_as_too_shallow"] == 20 * NLON
    assert np.isnan(r["priority"][:20]).all()
    assert np.isfinite(r["priority"][20:]).all()


def test_omitting_the_guard_is_recorded_rather_than_silently_defaulted():
    """A caller may leave it off; the result must SAY so, so a page cannot present an unguarded
    map as a guarded one."""
    sigma, eke, vm = _fields()
    r = P.priority(sigma, eke)
    assert r["guarded_by_valid_mask"] is False
    assert r["n_cells_excluded_as_too_shallow"] == 0
    assert np.isfinite(r["priority"][:20]).any(), "without the guard, shallow cells DO rank"


def test_a_wrongly_shaped_valid_mask_raises_rather_than_broadcasting():
    sigma, eke, _ = _fields()
    with pytest.raises(ValueError, match="valid_mask"):
        P.priority(sigma, eke, valid_mask=np.ones((10, 10, D), bool))


# ==================================================== combination

def test_both_factors_have_to_be_high_to_rank():
    """The product's whole premise. A place that is only uncertain, or only turbulent, is not a
    candidate -- and a geometric mean is what enforces that rather than an average."""
    sigma, eke, vm = _fields()
    r = P.priority(sigma, eke, valid_mask=vm)
    p = r["priority"]
    both = float(np.nanmean(p[20:30, 20:30]))          # high sigma AND high eke
    only_sigma = float(np.nanmean(p[20:30, 10:14]))    # high sigma, low eke
    only_eke = float(np.nanmean(p[30:35, 20:30]))      # low sigma, high eke
    assert both > only_sigma and both > only_eke


def test_the_normalisation_matches_v1s_so_the_two_products_are_comparable():
    """Deliberately the same method as `observation_priority`: 1st-99th percentile clipping to
    [0,1], then a geometric mean. If v2 invented its own scaling, a v1-vs-v2 comparison would be
    measuring the scaling and not the factor swap."""
    from oceanembed.products.observation_priority import observation_priority

    sigma, eke, _ = _fields()
    ones = np.ones_like(sigma)
    v1 = observation_priority(ones, sigma, eke)          # a neutral first factor
    v2 = P.priority(sigma, eke)["priority"]
    a, b = v1[np.isfinite(v1)], v2[np.isfinite(v2)]
    assert a.size == b.size
    # the same ORDERING is what matters; v1 takes a cube root over three factors, v2 a square root
    assert np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1] > 0.999


def test_a_factor_with_no_spatial_variation_is_neutral_not_zero():
    """Min-max on a constant grid gives all-zeros, which would blank the whole map and read as a
    bug rather than as a missing input. v1 made the same choice for the same reason."""
    sigma, eke, _ = _fields()
    with pytest.warns(RuntimeWarning, match="no spatial variation"):
        r = P.priority(np.full_like(sigma, 0.9), eke)
    assert r["sigma_is_neutral"] is True
    assert np.nanmax(r["priority"]) > 0.5, "a neutral factor must not zero the product"


@pytest.mark.parametrize("bad", [(0.0, 0.0), (-1.0, 1.0), (1.0,)])
def test_impossible_weights_raise(bad):
    sigma, eke, _ = _fields()
    with pytest.raises(ValueError):
        P.priority(sigma, eke, weights=bad)


def test_top_cells_returns_an_empty_list_rather_than_arbitrary_ones():
    """On a date where the guard excludes everything, "no candidate region" is the honest answer.
    Padding to k would put coordinates in front of a reader that mean nothing."""
    sigma, eke, _ = _fields()
    vm = np.zeros((NLAT, NLON, D), bool)
    r = P.priority(sigma, eke, valid_mask=vm)
    assert P.top_cells(r, 20) == []


def test_top_cells_are_sorted_and_resolve_to_real_coordinates():
    sigma, eke, vm = _fields()
    top = P.top_cells(P.priority(sigma, eke, valid_mask=vm), 10)
    assert len(top) == 10
    assert [c["rank"] for c in top] == list(range(1, 11))
    assert all(a["priority"] >= b["priority"] for a, b in zip(top, top[1:]))
    for c in top:
        assert c["lat"] == base.LAT[c["i"]] and c["lon"] == base.LON[c["j"]]


# ==================================================== the claim this product may make

def test_the_sanctioned_wording_is_carried_in_the_module_not_invented_per_page():
    assert "high scientific value" in P.CLAIM
    assert "complementary" in P.NOT_A_CLAIM


def test_no_page_or_module_promises_to_choose_deployment_locations():
    """NOVELTY_MATRIX marks this ALREADY DONE and disowns the stronger claim outright. The
    forbidden phrasing is checked in the SOURCE, because no numerical test can see it.
    """
    import re

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    banned = re.compile(r"tells?\s+(INCOIS|MoES|anyone)\s+where\s+to\s+deploy", re.I)
    for rel in ("src/phase2/products/priority_v2.py", "app/phase2/priority_page.py"):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        for m in banned.finditer(text):
            line = text[:m.start()].count("\n") + 1
            context = text[max(0, m.start() - 90):m.start()]
            assert ("never" in context.lower() or "not" in context.lower()
                    or "does not" in context.lower()), (
                f"{rel}:{line} promises to choose deployment locations: {m.group(0)!r}")


# ==================================================== against the real currents

BUNDLE = os.path.join("data", "processed", "daily_sat", "v001", "2025.npz")


@pytest.mark.skipif(not os.path.exists(BUNDLE), reason="satellite bundle not on this machine")
def test_on_real_currents_high_eke_is_not_simply_high_mean_speed():
    """The scientific failure this file exists for, on the real thing.

    If EKE had been computed from the total current, the top-decile EKE cells and the top-decile
    mean-speed cells would be almost the same set. MEASURED 2026-09-05: Jaccard 0.305.
    """
    z = np.load(BUNDLE, allow_pickle=True)
    ch = [str(c) for c in z["channels"]]
    u = np.asarray(z["surface"][:, :, :, ch.index("u")], dtype="float64")
    v = np.asarray(z["surface"][:, :, :, ch.index("v")], dtype="float64")
    k = P.eddy_kinetic_energy(u, v, t_index=100)

    eke, spd = k["eke"], k["mean_speed"]
    fin = np.isfinite(eke) & np.isfinite(spd)
    assert fin.sum() > 5000
    te = (eke >= np.nanpercentile(eke[fin], 90)) & fin
    ts = (spd >= np.nanpercentile(spd[fin], 90)) & fin
    jaccard = float((te & ts).sum() / (te | ts).sum())
    assert jaccard < 0.5, (
        f"top-decile EKE and top-decile mean speed overlap {jaccard:.1%} -- EKE is probably being "
        f"computed from the total current rather than its anomaly")
    assert jaccard > 0.05, "no overlap at all would be suspicious too -- jets do host eddies"
