"""F6 event detection -- tests.

Two kinds, and the second kind is the one that matters:

  ANALYTIC   -- a flow or field whose correct answer is known from theory, independent of this
                code. A Rankine vortex has a known vorticity sign; pure shear has W = 0 exactly.
  SCIENTIFIC -- does the output behave like the North Indian Ocean? These run on the real
                48-month bundle and are skipped (not faked) when it is absent.

`START_HERE` rule 7: a shape check is not a validity check. Every test below asks whether the
number could have been produced without real physics behind it.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from oceanembed import config
from phase2.events import _metric, _realdata, eddy, fronts, upwelling

GRIDS = os.path.join(config.DATA_PROCESSED, "grids.npz")
SUBSURFACE = os.path.join(config.DATA_PROCESSED, "subsurface.npz")
WIND_DIR = os.path.join(config.DATA_RAW, "wind")

NLAT, NLON = config.N_LAT, config.N_LON
LAT = np.asarray(config.LAT, dtype="float64")
LON = np.asarray(config.LON, dtype="float64")


# ---------------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_grids():
    if not os.path.exists(GRIDS):
        pytest.skip(f"{GRIDS} absent (gitignored) -- real-data checks skipped")
    return np.load(GRIDS, allow_pickle=True)


@pytest.fixture(scope="module")
def real_subsurface():
    if not os.path.exists(SUBSURFACE):
        pytest.skip(f"{SUBSURFACE} absent (gitignored) -- real-data checks skipped")
    return np.load(SUBSURFACE, allow_pickle=True)


def _rankine(centre_lat=15.0, centre_lon=75.0, radius_km=150.0, omega=1.0e-5, sign=1.0):
    """Rankine vortex on the frozen grid: solid-body rotation inside `radius_km`, 1/r outside.

    Inside the core the flow is exactly solid-body, for which theory gives
        vorticity = 2 * omega * sign,  strain = 0,  so  W = -(2*omega)^2 < 0.
    That is an answer from theory, not from this codebase.
    """
    dy_m = _metric.EARTH_RADIUS_M * np.deg2rad(LAT - centre_lat)
    dx_m = (_metric.EARTH_RADIUS_M * np.cos(np.deg2rad(centre_lat))
            * np.deg2rad(LON - centre_lon))
    X, Y = np.meshgrid(dx_m, dy_m)
    r = np.hypot(X, Y)
    R = radius_km * 1000.0

    v_theta = np.where(r <= R, omega * r, omega * R**2 / np.maximum(r, 1.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        u = sign * -v_theta * Y / np.maximum(r, 1.0)
        v = sign * v_theta * X / np.maximum(r, 1.0)
    return u, v, (X, Y, r, R)


# ---------------------------------------------------------------------------------------------
# 1-2. eddy detection, analytic
# ---------------------------------------------------------------------------------------------
def test_rankine_vortex_core_is_rotation_dominated_with_the_right_sign():
    omega = 1.0e-5
    u, v, (X, Y, r, R) = _rankine(omega=omega, sign=+1.0)
    ow = eddy.okubo_weiss(u, v)

    deep_core = (r < 0.5 * R) & np.isfinite(ow["W"])
    assert deep_core.sum() > 20, "test fixture too small to have a resolved core"

    # Theory: solid-body rotation has vorticity 2*omega and zero strain.
    assert np.nanmean(ow["vorticity"][deep_core]) == pytest.approx(2 * omega, rel=0.15)
    assert np.all(ow["W"][deep_core] < 0), "a rotating core must be rotation-dominated (W < 0)"


def test_pure_shear_is_not_an_eddy():
    """u = a*y, v = 0. Strain and vorticity are equal in magnitude, so W = 0 exactly.

    A detector that fires on any velocity gradient fails here. This is the guard against
    Okubo-Weiss's known over-detection being hidden by a lenient threshold.
    """
    a = 1.0e-6
    y_m = _metric.EARTH_RADIUS_M * np.deg2rad(LAT - LAT.mean())
    u = np.repeat((a * y_m)[:, None], NLON, axis=1)
    v = np.zeros_like(u)

    ow = eddy.okubo_weiss(u, v)
    finite = np.isfinite(ow["W"])
    assert np.allclose(ow["W"][finite], 0.0, atol=1e-20), "pure shear must give W = 0"

    assert eddy.detect_eddies(u, v) == [], "pure shear produced spurious eddies"


def test_detect_eddies_finds_one_vortex_with_the_correct_polarity_and_size():
    u, v, (_, _, _, R) = _rankine(radius_km=150.0, omega=1.0e-5, sign=+1.0)
    found = eddy.detect_eddies(u, v)
    assert len(found) >= 1, "a strong Rankine vortex must be detected"

    e = found[0]
    assert e["polarity"] == "cyclonic", "positive vorticity in the N hemisphere is cyclonic"
    assert e["centroid_lat"] == pytest.approx(15.0, abs=1.5)
    assert e["centroid_lon"] == pytest.approx(75.0, abs=1.5)
    # The W < 0 region of a Rankine vortex is the core, so the equivalent radius should be the
    # same order as the imposed radius -- not equal to it, and the test does not pretend it is.
    assert 0.3 * 150.0 < e["equivalent_radius_km"] < 2.0 * 150.0


def test_anticyclone_gets_the_opposite_polarity():
    u, v, _ = _rankine(sign=-1.0)
    found = eddy.detect_eddies(u, v)
    assert found and found[0]["polarity"] == "anticyclonic"


def test_detect_eddies_refuses_a_time_axis():
    """Passing the whole record is how tracking gets attempted by accident."""
    u = np.zeros((3, NLAT, NLON))
    with pytest.raises(ValueError, match="ONE snapshot"):
        eddy.detect_eddies(u, u)


# ---------------------------------------------------------------------------------------------
# 3-4. fronts, analytic
# ---------------------------------------------------------------------------------------------
def test_step_front_is_found_where_it_was_put():
    row = NLAT // 2
    sst = np.full((NLAT, NLON), 28.0)
    sst[row:, :] = 26.0                       # 2 degC step across one grid row

    out = fronts.detect_fronts(sst, percentile=99.0)
    rows = np.nonzero(out["mask"])[0]
    assert rows.size, "a 2 degC step must be detected"
    # Central differences spread a step across the two neighbouring rows.
    assert set(np.unique(rows)).issubset({row - 1, row, row + 1}), \
        f"front found at rows {np.unique(rows)}, expected near {row}"


def test_gradient_is_reported_in_real_distance_not_grid_index():
    """The same physical gradient must read the same at 5N and at 29N.

    dx = R cos(lat) dlon, so index-based differencing would report the northern gradient ~15%
    larger. This test fails the moment anyone reverts the spherical metric.
    """
    # A field that is linear in METRES of easting, constructed separately at two latitudes.
    def strip_gradient(lat_deg):
        i = int(np.argmin(np.abs(LAT - lat_deg)))
        dx_m = (_metric.EARTH_RADIUS_M * np.cos(np.deg2rad(LAT[i]))
                * np.deg2rad(LON - LON[0]))
        sst = np.repeat((25.0 + 1e-5 * dx_m)[None, :], NLAT, axis=0)
        return float(np.nanmean(fronts.sst_gradient(sst)["magnitude"][i, :]))

    south, north = strip_gradient(5.5), strip_gradient(29.0)
    assert south == pytest.approx(north, rel=1e-6), \
        f"same physical gradient read differently by latitude: {south} vs {north}"
    # 1e-5 degC/m = 1.0 degC per 100 km.
    assert south == pytest.approx(1.0, rel=1e-6)


def test_flat_field_reports_a_weak_threshold_rather_than_strong_fronts():
    """The percentile always returns the top decile. The payload must make a flat field visible."""
    sst = np.full((NLAT, NLON), 28.0) + 1e-9 * np.arange(NLON)[None, :]
    out = fronts.detect_fronts(sst)
    assert out["threshold"] < 1e-3, "a flat field must report a near-zero threshold"
    assert "flat" in out["note"]


# ---------------------------------------------------------------------------------------------
# 5-6. upwelling: no wind, no number
# ---------------------------------------------------------------------------------------------
def test_ekman_pumping_refuses_to_invent_wind():
    with pytest.raises(upwelling.MissingWindError):
        upwelling.ekman_pumping(None, None)
    with pytest.raises(upwelling.MissingWindError):
        upwelling.ekman_pumping(np.zeros((NLAT, NLON)), None)


def test_signature_without_wind_is_labelled_unattributed():
    sst = np.full((NLAT, NLON), 28.0)
    theta = np.tile(np.linspace(28.0, 8.0, config.N_DEPTHS), (NLAT, NLON, 1))
    sal = np.full_like(theta, 35.0)

    out = upwelling.upwelling_signature(sst, theta, sal)
    assert out["wind_attributed"] is False
    assert out["method"] == "signature-only"
    assert "NOT demonstrated" in out["caveat"]


def test_uniform_ocean_has_no_upwelling_signature():
    """No horizontal SST contrast and no layer-depth contrast => nothing to flag."""
    sst = np.full((NLAT, NLON), 28.0)
    theta = np.tile(np.linspace(28.0, 8.0, config.N_DEPTHS), (NLAT, NLON, 1))
    sal = np.full_like(theta, 35.0)

    out = upwelling.upwelling_signature(sst, theta, sal)
    assert out["n_cells"] == 0, "a horizontally uniform ocean cannot have an upwelling signature"


def test_the_equatorial_guard_exists_and_does_not_fire_in_this_domain(monkeypatch):
    """Honest version: this domain starts at exactly 5.0N, so the guard never fires here.

    An earlier draft of this test asserted NaN for `LAT < 5.0` -- a set that is EMPTY on this
    grid, so the assertion was vacuous and would have passed with the guard deleted. Instead:
    prove the interior is computable, then raise the guard latitude and prove it actually bites.
    """
    taux = np.full((NLAT, NLON), 0.05)
    tauy = np.zeros((NLAT, NLON))

    assert (LAT < upwelling.MIN_ABS_LAT_DEG).sum() == 0, \
        "domain now extends equatorward of the guard -- this test must be rewritten"

    w = upwelling.ekman_pumping(taux, tauy)
    assert np.isfinite(w[10:-10, 10:-10]).any(), "pumping must be computable in the interior"

    monkeypatch.setattr(upwelling, "MIN_ABS_LAT_DEG", 12.0)
    guarded = upwelling.ekman_pumping(taux, tauy)
    assert np.isnan(guarded[LAT < 12.0]).all(), "the guard did not mask low latitudes"
    assert np.isfinite(guarded[LAT > 15.0]).any(), "the guard masked too much"


# ---------------------------------------------------------------------------------------------
# 7. land / NaN propagation
# ---------------------------------------------------------------------------------------------
def test_nan_neighbours_propagate_rather_than_differencing_against_a_fill_value():
    u, v, _ = _rankine()
    u = u.copy()
    u[40, 100] = np.nan
    ow = eddy.okubo_weiss(u, v)
    # The NaN must reach the cells that difference across it, not be silently replaced.
    assert np.isnan(ow["W"][40, 99]) and np.isnan(ow["W"][40, 101])


def test_no_eddy_or_front_is_reported_on_land(real_grids):
    land = np.asarray(real_grids["land_mask"], dtype=bool)
    if not land.any():
        pytest.skip("no land in this grid")
    u = np.where(land, np.nan, np.asarray(real_grids["u"], dtype="float64")[0])
    v = np.where(land, np.nan, np.asarray(real_grids["v"], dtype="float64")[0])
    found = eddy.detect_eddies(u, v)
    lat_i = [int(np.argmin(np.abs(LAT - e["centroid_lat"]))) for e in found]
    lon_i = [int(np.argmin(np.abs(LON - e["centroid_lon"]))) for e in found]
    assert not any(land[i, j] for i, j in zip(lat_i, lon_i)), "an eddy centroid landed on land"


# ---------------------------------------------------------------------------------------------
# 8-9. SCIENTIFIC sanity -- real data
# ---------------------------------------------------------------------------------------------
def test_eddy_count_is_physically_plausible(real_grids):
    """Not 0 (threshold wrong) and not 10^4 (detecting noise)."""
    u = np.asarray(real_grids["u"], dtype="float64")[0]
    v = np.asarray(real_grids["v"], dtype="float64")[0]
    found = eddy.detect_eddies(u, v)
    assert 5 <= len(found) <= 400, (
        f"{len(found)} eddies in one snapshot of a 100x240 basin is not plausible; "
        "0 means the threshold is wrong, thousands means we are detecting noise"
    )


def test_both_polarities_occur(real_grids):
    """All-one-polarity would mean a sign error in the vorticity."""
    u = np.asarray(real_grids["u"], dtype="float64")[0]
    v = np.asarray(real_grids["v"], dtype="float64")[0]
    s = eddy.summarise(eddy.detect_eddies(u, v))
    assert s["n_cyclonic"] > 0 and s["n_anticyclonic"] > 0
    minority = min(s["n_cyclonic"], s["n_anticyclonic"])
    assert minority / s["n_eddies"] > 0.15, f"suspiciously one-sided: {s}"


# ---------------------------------------------------------------------------------------------
# 10-11. the honesty gate
# ---------------------------------------------------------------------------------------------
def test_structure_report_rejects_a_flat_synthetic_profile():
    """A stand-in with the right shape, dtype, units and plausible magnitudes -- and no ocean."""
    theta = np.tile(np.exp(-np.asarray(config.DEPTHS, dtype="float64") / 250.0) * 10 + 20,
                    (NLAT, NLON, 1))
    sal = np.full_like(theta, 34.6)          # no fresh cap, no river water, no range
    r = _realdata.structure_report(sal, theta)
    assert r["passed"] is False
    assert not r["checks"]["bob_fresh_cap_psu"]["passed"]
    assert not r["checks"]["domain_min_salinity_psu"]["passed"]


def test_structure_report_accepts_a_realistic_profile():
    """Fresh cap over salty water, river water present, mixed layer above the thermocline."""
    d = np.asarray(config.DEPTHS, dtype="float64")
    prof_t = np.where(d <= 30, 29.0, 29.0 - 0.045 * (d - 30))     # mixed layer then thermocline
    prof_s = 34.9 - 2.0 * np.exp(-d / 40.0)                        # fresh cap
    theta = np.tile(prof_t, (NLAT, NLON, 1))
    sal = np.tile(prof_s, (NLAT, NLON, 1))
    sal[..., 0] = np.minimum(sal[..., 0], 34.9)
    sal[20, 200, 0] = 5.0                                          # a river mouth somewhere
    assert _realdata.looks_like_real_ocean(sal, theta) is True


def test_the_installed_data_has_real_ocean_structure(real_grids, real_subsurface):
    """PRECONDITION, and it is INVERTED from how this test was first specified.

    The spec originally wrote this as a tripwire asserting False, because the local
    `subsurface.npz` was a synthetic stand-in wearing a `real-glorys-subsurface` stamp. The real
    bundle landed and flipped it. The flip is recorded rather than quietly edited, because the
    flip IS the evidence that the data changed.

    It asserts structure, never the `source` string -- that string was wrong once already.
    """
    sal = np.asarray(real_subsurface["salinity"], dtype="float64")
    theta = np.asarray(real_grids["temp"], dtype="float64")
    report = _realdata.structure_report(sal, theta)
    assert report["passed"] is True, (
        "installed data has no ocean structure:\n" + _realdata.describe(sal, theta)
    )


# ---------------------------------------------------------------------------------------------
# 12. wind alignment -- the half-cell offset
# ---------------------------------------------------------------------------------------------
def _any_wind_month():
    import glob as _g
    hits = sorted(_g.glob(os.path.join(WIND_DIR, "wind_*.nc")))
    if not hits:
        pytest.skip("no wind files (gitignored) -- wind checks skipped")
    return os.path.basename(hits[len(hits) // 2])[5:11]


def test_raw_wind_grid_is_offset_and_the_loader_corrects_it():
    """Both halves, so the test fails if the regrid is deleted OR if the product changes grid.

    [VERIFIED] the raw product is on cell centres, +0.125 deg from the baseline's cell edges, with
    an identical (100, 240) shape. Nothing but a coordinate comparison catches that.
    """
    xr = pytest.importorskip("xarray")
    month = _any_wind_month()
    path = os.path.join(WIND_DIR, f"wind_{month}.nc")

    with xr.open_dataset(path) as ds:
        raw_lat = np.asarray(ds["latitude"].values, dtype="float64")
        raw_lon = np.asarray(ds["longitude"].values, dtype="float64")

    assert raw_lat.shape == LAT.shape, "shape alone matches -- which is exactly the trap"
    assert not np.allclose(raw_lat, LAT, atol=1e-6), \
        "raw wind grid unexpectedly matches the baseline; the offset assumption needs rechecking"
    assert float(raw_lat[0] - LAT[0]) == pytest.approx(0.125, abs=1e-6)
    assert float(raw_lon[0] - LON[0]) == pytest.approx(0.125, abs=1e-6)

    w = upwelling.load_wind_stress(month)
    assert w["eastward_stress"].shape == (NLAT, NLON)
    assert np.isfinite(w["eastward_stress"]).any(), "regridded stress is entirely NaN"


def test_ekman_pumping_runs_on_real_wind_and_has_both_signs():
    """Real wind-stress curl must produce upwelling AND downwelling. All one sign is a bug."""
    month = _any_wind_month()
    w = upwelling.load_wind_stress(month)
    pump = upwelling.ekman_pumping(w["eastward_stress"], w["northward_stress"])
    finite = np.isfinite(pump)
    assert finite.sum() > 1000, "too few valid Ekman cells"
    assert (pump[finite] > 0).any() and (pump[finite] < 0).any()
    # Order of magnitude: Ekman pumping is ~1e-6 to 1e-5 m/s (centimetres to metres per day).
    assert np.nanpercentile(np.abs(pump[finite]), 99) < 1e-3, \
        f"Ekman velocities are implausibly large: {np.nanmax(np.abs(pump[finite])):.2e} m/s"


def test_the_zonal_sst_reference_is_labelled_as_a_fallback():
    """The default reference is known-weak; the result must say so rather than look authoritative.

    [VERIFIED on the 48-month record] the zonal mean flags the Somali box "cold" 97.9% of the
    time in January, giving a SW/NE ratio of 0.88 -- backwards for the basin's best-known
    upwelling system. The climatology reference gives 1.68. The default stays (the climatology
    is gitignored and may be absent) but it must not present itself as the right answer.
    """
    sst = np.full((NLAT, NLON), 28.0)
    theta = np.tile(np.linspace(28.0, 8.0, config.N_DEPTHS), (NLAT, NLON, 1))
    sal = np.full_like(theta, 35.0)

    out = upwelling.upwelling_signature(sst, theta, sal)
    assert "FALLBACK" in out["sst_reference_kind"]
    assert out["limiting_term"] == "shoaled_thermocline"

    out2 = upwelling.upwelling_signature(sst, theta, sal, sst_reference=np.full_like(sst, 29.0))
    assert out2["sst_reference_kind"] == "caller-supplied"


def test_climatological_reference_loads_and_has_the_right_grid():
    if not os.path.exists(upwelling.CLIMATOLOGY):
        pytest.skip("climatology.npy absent (gitignored)")
    ref = upwelling.climatological_sst_reference(7)
    assert ref.shape == (NLAT, NLON)
    finite = ref[np.isfinite(ref)]
    assert 10.0 < float(finite.min()) and float(finite.max()) < 40.0, \
        "SST climatology outside a physically possible range"
    with pytest.raises(ValueError):
        upwelling.climatological_sst_reference(13)


def test_supplying_wind_flips_the_attribution_flag(real_grids, real_subsurface):
    month = _any_wind_month()
    w = upwelling.load_wind_stress(month)
    pump = upwelling.ekman_pumping(w["eastward_stress"], w["northward_stress"])

    sst = np.asarray(real_grids["sst"], dtype="float64")[0]
    theta = np.asarray(real_grids["temp"], dtype="float64")[0]
    sal = np.asarray(real_subsurface["salinity"], dtype="float64")[0]

    without = upwelling.upwelling_signature(sst, theta, sal)
    with_wind = upwelling.upwelling_signature(sst, theta, sal, ekman=pump)

    assert without["wind_attributed"] is False
    assert with_wind["wind_attributed"] is True
    assert with_wind["method"] == "signature+ekman"
    # Attribution can only ever narrow the signature, never widen it.
    assert with_wind["n_cells"] <= without["n_cells"]
