# F6 — Event detection: design spec

**Owner:** Unit A (Arjhun) · **Branch:** `phase2-events` (cut from `phase2-physics`, see §8)
**Status:** DESIGN — nothing implemented at time of writing
**Written:** 2026-08-26 · **Revised:** 2026-08-26 after the real data bundle landed

> **Revision note.** This spec was written while the only data here was a synthetic stand-in and no
> wind existed. Unit B's 133 MB bundle has since landed and verified. Three things changed:
> wind is real and present, so `ekman_pumping` is runnable rather than aspirational (§4.3);
> `subsurface.npz` is now genuinely real, so the §3 honesty gate flips from *tripwire* to
> *precondition*; and a **new** alignment hazard was found in the wind grid (§2.1) that did not
> exist before. Sections below are the revised text; the original reasoning is preserved where it
> still holds.

Spec lives here rather than `docs/superpowers/specs/` because this repo already has one place for
Phase-2 feature docs (`docs/phase2/f5-physics.md`), and a second doc tree is a second source of
truth nobody reads.

---

## 1. What F6 is, and what it is not

F6 detects **mesoscale ocean events in a single snapshot**: eddies, thermal fronts, and an
upwelling *signature*.

**It does not track anything.** Our sampling is one field per month. Mesoscale eddies in the North
Indian Ocean persist weeks to a few months and translate at a few km/day, so consecutive monthly
fields cannot be assumed to show the same feature. Linking them would be invention. `PHASE2_STATUS`
and the audit already record this; it is restated here because "detection" and "tracking" are one
word apart and the wrong one is easy to type.

**It does not attribute upwelling to wind.** No wind product exists on this machine. The design
makes that structural rather than a footnote — see §4.3.

---

## 2. Data actually available [VERIFIED 2026-08-26]

From `data/processed/grids.npz`, per timestep on the frozen 100x240 grid at 0.25 deg:

| field | shape | note |
|---|---|---|
| `sst` | (T, 100, 240) | degC — drives fronts |
| `sss`, `ssh` | (T, 100, 240) | |
| `u`, `v` | (T, 100, 240) | m/s **surface** — drives eddies |

From `data/processed/subsurface.npz`: `salinity`, `u`, `v` at (T, 100, 240, 15).

Grid, depths and region are **imported from `oceanembed.config`**, never restated:
`REGION = 5-30N, 45-105E, step 0.25`; `DEPTHS` = 15 levels to 1000 m.

**T = 48, real GLORYS, 2019-01-15 to 2022-12-15** [VERIFIED 2026-08-26 by
`scripts/phase2/verify_data_bundle.py`, all three levels pass, plus an independent re-run of the
four F5 checks]. `grids.npz` stamps `source = real-glorys`.

**Wind is present:** `data/raw/wind/wind_YYYYMM.nc`, 48 monthly files, each carrying
`eastward_wind`, `northward_wind`, **`eastward_stress`, `northward_stress`** (N/m2),
`wind_speed`, `wind_stress_magnitude` on a (1, 100, 240) grid. Stress is provided directly, so
`ekman_pumping` needs no drag coefficient.

### 2.1 The wind grid is offset half a cell — regrid, never assign [VERIFIED]

```
wind latitude :  5.125  5.375  5.625  ...  29.875
base latitude :  5.000  5.250  5.500  ...  29.750
offset = +0.125 deg in BOTH lat and lon, constant, and the shape is identically (100, 240)
```

The wind product is on **cell centres**; the baseline grid is on **cell edges**. Same shape, same
spacing, same count — so `np.shape` agrees, a bounds check on values agrees, and every wind value
still lands ~14 km southwest of where it belongs.

This is the project's recurring failure mode (`START_HERE` §5.7): *correct array, plausible values,
wrong data*. It matters more here than almost anywhere else, because Ekman pumping is a **curl** —
a spatial derivative — and the upwelling we want to detect is **coastal**, exactly where a half-cell
shift moves water on and off the land mask.

**Requirement:** `upwelling.py` loads wind through a loader that interpolates onto `config.LAT` /
`config.LON` and **asserts** the resulting coordinates match the baseline to within 1e-6. Assigning
the raw array is forbidden and a test enforces it (§6.12).

One cosmetic note: the wind files' global attributes read `time_coverage_start: 2024-06-01` while
the `time` coordinate and filename both say the correct month. The attributes are stale CMEMS
product boilerplate; the coordinate is authoritative, and the seasonal check (SW monsoon 5.64 m/s
vs NE 3.99 m/s) confirms the months are labelled correctly. **Read `time`, never the attributes.**

---

## 3. The provenance finding, and the gate it forces

**The file is now real, and the code bug that mislabelled it is not fixed.** Both halves matter.

Before the bundle, `data/processed/subsurface.npz` here was stamped `source =
"real-glorys-subsurface"` while holding synthetic data — BoB salinity 34.6029 at the surface vs
34.5846 at 500 m (inverted), domain minimum 34.09 psu. After the bundle it reads 30.26 -> 35.03 psu
and a 1.29 psu river minimum. Same filename, same stamp, opposite contents.

`src/phase2/data/extract_subsurface.py:112` still writes that string unconditionally, whatever file
it read. The stamp was *accidentally* correct this time. This is `D-018`'s failure mode — the
synthetic banner switching itself off — and it is Unit B's file, so it is an **ASK, not an edit**
(§9).

**Consequence for F6, and it is a design requirement, not a caveat:** no F6 code may decide
"is this real data" by reading the `source` string. `_realdata.py` (§4.4) answers that question
from *structure* instead. This is rule 7 of `START_HERE` applied to a field we already know lies:
*could this array have been produced without real data behind it?*

---

## 4. Modules

New package `src/phase2/events/`. Unit A area. Imports the baseline and F5; edits neither.

### 4.1 `eddy.py` — Okubo-Weiss detection from surface currents

The Okubo-Weiss parameter separates strain-dominated from rotation-dominated flow:

```
Sn = du/dx - dv/dy        (normal strain)
Ss = dv/dx + du/dy        (shear strain)
w  = dv/dx - du/dy        (relative vorticity)
W  = Sn^2 + Ss^2 - w^2
```

Okubo (1970), Weiss (1991). Eddy cores are rotation-dominated: `W < -0.2 * sigma_W`, the threshold
of Isern-Fontanet et al. (2003) as used by Chelton et al. (2007), where `sigma_W` is the spatial
standard deviation of `W` over valid ocean cells in that snapshot. The threshold is **relative to
the field**, not an absolute s^-2 value carried over from another basin.

Sign of `w` classifies the eddy: in the Northern Hemisphere `w > 0` is **cyclonic**.

Connected-component labelling over the core mask gives discrete eddies. Per eddy:
`centroid_lat`, `centroid_lon`, `area_km2`, `equivalent_radius_km`, `polarity`
(`"cyclonic"`/`"anticyclonic"`), `mean_vorticity`, `n_cells`.

```python
def okubo_weiss(u, v) -> dict          # {"W", "vorticity", "normal_strain", "shear_strain"}
def detect_eddies(u, v, *, w_factor=-0.2, min_cells=4) -> list[dict]
```

`min_cells=4` because a 0.25 deg cell is ~25 km and a mesoscale eddy in this basin is ~100-200 km
across; anything smaller than a few cells is a gradient artifact, not a resolved eddy.

**Known limitation, stated in the module docstring:** Okubo-Weiss is threshold-sensitive and is
known to over-detect in noisy velocity fields (Chelton et al. 2007 discuss this). A
geometry-based alternative (Nencioli et al. 2010) avoids the threshold. We take Okubo-Weiss for
the first version because it is a direct computation on fields we have, and record the
alternative rather than pretending the choice is free.

### 4.2 `fronts.py` — thermal fronts from SST gradient

Gradient magnitude `|grad SST|` on the spherical metric (§5), reported in **degC / 100 km** so the
number is comparable to published front strengths.

Front mask at a **percentile** of the in-domain gradient distribution (default 90th), not an
absolute degC/km cutoff. An absolute threshold tuned on, say, the California Current would either
flood or empty this basin, and we have no independent front climatology here to calibrate against.
The percentile is a defensible convention; a borrowed constant would be a fabricated one.

```python
def sst_gradient(sst) -> dict          # {"magnitude", "d_dx", "d_dy"} degC/100km
def detect_fronts(sst, *, percentile=90.0, min_cells=3) -> dict
# -> {"mask", "magnitude", "threshold", "n_fronts", "fronts": [ {centroid, n_cells,
#     mean_gradient, max_gradient}, ... ]}
```

`min_cells=3` drops isolated single-cell gradient spikes; a front is a connected feature, and one
hot pixel is noise. Front segments come from the same connected-component step `eddy.py` uses.

Belkin & O'Reilly (2009) is the standard reference for SST front detection; we implement the plain
gradient step, not their full contextual median filter, and say so.

### 4.3 `upwelling.py` — signature now, attribution only with wind

Two functions, deliberately not one.

```python
def upwelling_signature(sst, theta, salinity, *, sst_reference=None,
                        sst_margin=0.5, shoal_percentile=25.0) -> dict
```
Returns a boolean `signature` mask plus its two components:
- **cold surface** — SST at least `sst_margin` (default **0.5 degC**) below `sst_reference`. If
  `sst_reference` is not supplied it defaults to the **zonal mean SST at that latitude in that
  snapshot**, not a global mean: this basin spans 25 deg of latitude and a global mean would mark
  the entire northern domain as "cold".
- **shoaled thermocline** — `physics.layers.thermocline(theta)["depth"]` and
  `physics.layers.mixed_layer_depth(salinity, theta)` both shallower than the **25th percentile**
  of their own valid-cell distribution in that snapshot.

**Both conditions must hold.** The returned dict carries `wind_attributed = False` and
`method = "signature-only"` as **data**, so a downstream panel or Sentinel rule cannot lose the
caveat by not reading the docs.

`sst_margin` and `shoal_percentile` are conventions chosen for this design, not values taken from
a paper, and the module docstring says so. They are keyword arguments so a reviewer can move them.

```python
def ekman_pumping(eastward_stress, northward_stress) -> np.ndarray
```
Wind-stress curl divided by `rho * f` — vertical Ekman velocity, positive upward. **Raises
`MissingWindError` if called with `None`.** There is no default, no "assume a drag coefficient",
no silent fallback. The monthly product carries `eastward_stress` / `northward_stress` in N/m2
directly, which is why this takes stress rather than wind speed.

**This is now runnable** — 48 months of real stress are present. A third function loads them, and
it is the only sanctioned path in, because of §2.1:

```python
def load_wind_stress(month) -> dict   # {"eastward_stress", "northward_stress", "time"}
```
It reads `data/raw/wind/wind_YYYYMM.nc`, interpolates onto `config.LAT`/`config.LON`, and asserts
coordinate agreement to 1e-6 before returning. `upwelling_signature` gains an optional
`ekman = None` argument: when supplied, the result reports `wind_attributed = True` and the
signature is intersected with `ekman > 0` (upward pumping). When absent, behaviour is exactly as
before. The caveat is still carried as data, and now it can also be *lifted* by data.

Near the equator `f -> 0` and Ekman pumping is undefined; the function returns NaN equatorward of
5 deg. Our domain starts at 5N, so this is a guard at the boundary, not a hole in the middle.

### 4.4 `_realdata.py` — the honesty gate §3 forces

```python
def structure_report(salinity, theta) -> dict
def looks_like_real_ocean(salinity, theta) -> bool
```

Answers "is there ocean structure in this array" from physics, never from a provenance string:

1. **Fresh cap in the northern Bay of Bengal** — mean surface salinity in 15-22N / 85-95E is at
   least **0.5 psu fresher** than the same cells at 500 m. Currently -0.018 psu, i.e. inverted.
2. **Salinity range** — the domain minimum is below **30 psu**. The real domain reaches 6.43 psu
   (Meghna/Ganges); the synthetic file bottoms out at 34.09.
3. **Thermocline below MLD** — true in at least **60%** of valid cells. Currently 11.6%, because
   the synthetic profile is `exp(-z/250)` from the surface and has no mixed layer at all.

The three numbers above (0.5 psu, 30 psu, 60%) are thresholds chosen to sit clearly between the
measured synthetic values and the expected real ones. They are a tripwire, not a measurement.

Returns the three checks with their measured values, so a failure says *which* structure is
missing. F6's CLI prints this before any result, and every F6 output dict carries the boolean.

---

## 5. Numerics: the spherical metric

All horizontal derivatives use real distance, not grid index:

```
dx = R * cos(lat) * d(lon in radians)
dy = R * d(lat in radians)
R  = 6371000 m
```

At 5N `cos = 0.996`; at 30N `cos = 0.866`. Ignoring it inflates zonal gradients by ~15% at the
northern edge of the domain and biases every eddy and front northward. This is exactly a
"never assume coordinate order / units" case (`CLAUDE.md` rules 10 and 11).

Land and below-bathymetry cells come from `land_mask` / `valid_mask`; gradients touching an
invalid neighbour return NaN rather than differencing against a fill value. Phase 1's shelf bug
was this shape.

---

## 6. Tests — `tests/phase2/test_events.py`

**Analytic, where the right answer is known independently of our code:**

1. **Rankine vortex** — solid-body rotation core. `W < 0` inside; vorticity sign matches the
   imposed rotation; `detect_eddies` finds exactly one eddy with the correct polarity and a radius
   within tolerance of the imposed one.
2. **Pure shear flow** (`u = a*y`, `v = 0`) — strain equals vorticity, so `W = 0` and **no** eddy
   is detected. Guards against a detector that fires on any velocity gradient.
3. **Synthetic step front** at a known latitude — `detect_fronts` puts the front there and nowhere
   else; the reported gradient matches the imposed degC/100 km.
4. **Metric test** — the same imposed gradient at 5N and 29N returns the same degC/100 km. Fails
   if anyone reverts to index spacing.
5. **`ekman_pumping(None, None)` raises `MissingWindError`.** No wind, no number.
6. **`upwelling_signature` returns all-False on a well-mixed column** — no cold anomaly, no shoaling.
7. **Land/NaN propagation** — no eddy or front is reported on a land cell.

**Scientific sanity tests** (the F5 lesson: a shape check is not a validity check):

8. **Eddy count is O(10-100)** over the domain in a snapshot, not 0 and not 10^4. Zero means the
   threshold is wrong; ten thousand means we are detecting noise.
9. **Cyclonic and anticyclonic both occur** in a real snapshot, in roughly comparable numbers.
   All-one-polarity means a sign error in the vorticity.
10. **`structure_report` on a hand-built *real-shaped* profile passes all three checks, and on a
    hand-built *flat* profile fails all three.** This is the detector's own correctness test and it
    uses fixtures, not the data file, so it is stable.
11. **Precondition: `looks_like_real_ocean(subsurface.npz)` is True.** Skips if the file is absent,
    as Unit B's salinity test does. **This assertion is inverted from the original spec** — it was
    written as a tripwire asserting *False* while the local file was synthetic, and the bundle
    flipped it. That flip is the evidence the data changed, and it is recorded rather than quietly
    edited. The assertion reads the structure check, never the `source` string.
12. **Wind alignment** — `load_wind_stress` returns coordinates equal to `config.LAT`/`config.LON`
    within 1e-6, and the raw file's coordinates do **not** (they are offset 0.125 deg). Both halves
    are asserted, so the test fails if someone deletes the regrid *or* if the product silently
    changes grid. This is §2.1 pinned down.

Tests 8 and 9 run against the real 48-month record and are expected to pass; a failure there is a
scientific finding, not a flaky test.

---

## 7. Limitations — written before the results, so they cannot be softened after

- **Monthly cadence.** Detection only. No tracking, no lifetime, no propagation speed.
- **0.25 deg resolution.** Sub-mesoscale fronts and eddies below ~100 km are unresolved. We report
  what the grid can carry.
- **Wind is monthly means.** Ekman pumping from a monthly-mean stress is not the monthly mean of
  Ekman pumping — the curl of an average smooths out the short-lived, strong-curl events that drive
  much of the real pumping. Our numbers are therefore a **lower bound on episodic upwelling** and a
  reasonable estimate of the seasonal pattern. This is a limitation of the product, not of the code,
  and it must travel with any number we quote. F7 persistence stays blocked and is not attempted.
- **Surface currents are GLORYS reanalysis, not observed.** Eddies detected are eddies *in the
  reanalysis*. That is a statement about the product, and it belongs next to any count we quote.
- **Nothing here is VALIDATED** until it runs on real GLORYS and the checks in §6.8-6.10 are
  inspected by a human.

---

## 8. Branch plan

Cut **`phase2-events` from `phase2-physics`**, not from `origin/phase2`.

`upwelling.py` imports `phase2.physics.layers`, which exists only on `phase2-physics`. Branching
from `origin/phase2` would give an unimportable module and a fake reason to reimplement the
thermocline.

`phase2/<feature>` remains impossible as a branch name while `phase2` is a branch — hence
`phase2-events`. If a branch is ever cut from `origin/phase2`, `rm -f tests/phase2/__init__.py`
first; it shadows `src/phase2` and has broken imports twice on independent branches.

Files created, all Unit A area:
```
src/phase2/events/__init__.py  eddy.py  fronts.py  upwelling.py  _realdata.py
tests/phase2/test_events.py
docs/phase2/f6-events.md          # write-up, after implementation
```
No baseline file, no Unit B file, and no `main` operation.

---

## 9. Open asks for Unit B

**>>> ASK DARSHAN (4): `extract_subsurface.py:112` stamps `source="real-glorys-subsurface"`
unconditionally.** On this machine that string sits on synthetic data (§3). Suggest deriving it
from the input filename, or asserting the salinity range looks like the real domain before writing
it. Your file, your call — I have not touched it, and F6 does not trust the field.

**Asks 1 and 3 are ANSWERED** by the 133 MB bundle — `argo_error_by_depth.json` and real
`subsurface.npz` both landed and verified. Ask 2 (per-profile residuals + sigma, for F4's *held-out*
calibration path) is the only original ask still open.

**>>> ASK DARSHAN (5): the wind grid is offset +0.125 deg from `config.LAT`/`config.LON` (§2.1).**
Same shape, so nothing catches it but a coordinate comparison. F6 regrids on load. Flagging it
because F10 priority or any panel that overlays wind will hit the same thing, and it is invisible.

**>>> ASK DARSHAN (6): the bundle leaves stale synthetic artifacts next to real ones.**
`artifacts/provenance.json` now reads `n_train = 323028`, but the local `X_train.npy` is the old
synthetic file with **143514** rows, and `lgbm_model.pkl` / `lgbm_quantiles.pkl` are still
synthetic-trained. They were excluded from the bundle deliberately (regenerable), which is
reasonable — but the result is a directory where provenance describes data that is not all there.
Anything that loads `X_train` or the LightGBM baseline gets synthetic input while `provenance.json`
says `real-glorys`. Suggest the verifier also fail when a file's row count contradicts
`provenance.json`, so this cannot be discovered by a wrong metric.

---

## 10. References

- Okubo, A. (1970). *Deep-Sea Research* 17, 445-454.
- Weiss, J. (1991). *Physica D* 48, 273-294.
- Isern-Fontanet, J., Garcia-Ladona, E., Font, J. (2003). *J. Atmos. Oceanic Technol.* 20, 772-778.
- Chelton, D. B., et al. (2007). *Geophys. Res. Lett.* 34, L15606.
- Nencioli, F., et al. (2010). *J. Atmos. Oceanic Technol.* 27, 564-579.
- Belkin, I. M., O'Reilly, J. E. (2009). *J. Marine Systems* 78, 319-326.
- de Boyer Montegut, C., et al. (2004). *JGR* 109, C12003. (via F5)

Citations are named so they can be checked. None has been re-read this session; they are the
standard references for these methods as recorded in F5's research pass and the audit.
[INFERRED] that each states what is attributed to it above — **verify before any of it reaches a
slide or a report.**
