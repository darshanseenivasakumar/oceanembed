# F6 — Event detection: design spec

**Owner:** Unit A (Arjhun) · **Branch:** `phase2-events` (cut from `phase2-physics`, see §8)
**Status:** DESIGN — nothing implemented at time of writing
**Written:** 2026-08-26

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

**Locally T = 8 and the data is synthetic.** Unit B's machine has T = 48 real GLORYS. Every number
F6 produces here is a code check, not a scientific result.

**No wind.** `src/phase2/data/download_wind.py` exists (Unit B) but no wind file has landed here.

---

## 3. The provenance finding, and the gate it forces

[VERIFIED] `data/processed/subsurface.npz` on this machine is stamped
`source = "real-glorys-subsurface"` and contains synthetic data:

```
BoB 18N/88E salinity, surface vs 500 m : 34.6029  vs  34.5846
global salinity minimum                : 34.09 psu
```

The real domain minimum measured by Unit B is **6.43 psu** at the Meghna/Ganges mouth, and the real
Bay of Bengal has a fresh cap over saltier water — the opposite of the profile above.
`src/phase2/data/extract_subsurface.py:112` writes that string unconditionally, whatever file it
read. This is `D-018`'s failure mode: the synthetic banner switching itself off.

That file is Unit B's, so this is an **ASK, not an edit** (§9).

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
no silent fallback. When Unit B's monthly product lands it carries `eastward_stress` /
`northward_stress` in N/m2 directly, which is why this takes stress rather than wind speed.

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
11. **Tripwire: `looks_like_real_ocean(subsurface.npz)` is False today.** Skips if the file is
    absent, as Unit B's salinity test does. It asserts the §3 finding — the file claims real
    provenance and has no ocean structure. **When real data lands this test FAILS**, and that
    failure is the signal: it forces a human to look, invert it, and re-run every F6 number.
    The assertion reads the structure check, never the `source` string.

Tests 8 and 9 cannot be meaningfully evaluated on synthetic currents and will be marked
`xfail(strict=False)` with the reason recorded, not silently skipped.

---

## 7. Limitations — written before the results, so they cannot be softened after

- **Monthly cadence.** Detection only. No tracking, no lifetime, no propagation speed.
- **0.25 deg resolution.** Sub-mesoscale fronts and eddies below ~100 km are unresolved. We report
  what the grid can carry.
- **No wind.** No upwelling attribution, no Ekman transport, no curl-driven claim. F7 persistence
  stays blocked and is not attempted.
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

Asks 1-3 are unchanged and still open: whitelist `artifacts/argo_error_by_depth.json`; persist
per-profile residuals + sigma; a copy of real `subsurface.npz` or the raw `glorys_*.nc`.
The monthly wind download unblocks `ekman_pumping`, which is written but cannot be run.

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
