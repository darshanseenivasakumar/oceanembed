

---

## FROZEN — 2026-09-02T20:12:52  (A16)

**What is frozen.** This exact combination produced the numbers below, and
`scripts/phase2/freeze.py` re-verifies it rather than taking anyone's word.

| | |
|---|---|
| git commit | `ffd95e6e84e1` on `phase2-tscast-nio`, tree clean |
| model | `sat_7ch_s42` — cnn3d / simple / nll β=0.5 / seed 42 |
| checkpoint | `tscast_stage1.pt` sha256 `53848bb52533752d…` built at code `a67feea` |
| **input** | **satellite** — `data/processed/daily_sat/v001`, 388 days |
| target | GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D- |
| split | train 2025-06-01..2026-03-26, test 2026-04-01..2026-06-23, `embargoed_v2`, 5 targets embargoed |
| T_SEQ | 11 (data window); **built_t_seq 1** — different numbers, and confusing them cost a day |

**Measured against 962 independent Argo profiles (12829 depth comparisons):**

    RMSE 0.907761 degC   bias +0.1003   correlation 0.8812
    skill vs climatology +0.2595   (climatology RMSE 1.2259)

**Uncertainty:** ±2σ only. Coverage 80.1%–95.5% by depth (mean
91.2%, Gaussian nominal 95.4%), worst at 50 m. No ±1σ band and no confidence
percentage is displayed anywhere, because neither is defensible.

**Smoke inference at freeze:** 15.0N 68.0E 2026-05-15 → mean |error| **0.326 °C** across 14 depths
against an independent float 13 km / 2 days away. 530 tests pass, 10 skipped.

### Carried into the freeze, stated rather than omitted

1. **INCOIS LAS gridded Argo (PS req 16) is unreachable** — their data layer is down (Darshan's
   probe: the right products exist, every retrieval route fails). Validated on argopy floats with
   the deviation documented. Re-probe before any public claim.
2. **The Arabian Sea satellite penalty (+0.0341, sign holding 3/3) is reproducible and its cause is
   UNKNOWN.** Four mechanisms proposed and tested; none supported. This is the honest headline.
3. **Uncertainty is improved, not calibrated.** 80.1% coverage at 50 m against a 95.4% nominal.
4. **Stage 2 has never been run on satellite input** — there is no satellite T+S+density number and
   none may be implied.
5. **accept.py carries one known pre-existing failure** comparing two legacy Phase-1 artifacts with
   different profile-retention rules. The RMSE agreement it also checks passes at 0.0213 degC, and
   neither artifact underwrites the shipped model.

### What must NOT change without re-freezing

The checkpoint, the bundle, `dataset.py`, `inference.py`, or the split. Any of those moving
invalidates every number above. `python scripts/phase2/freeze.py --check` is the gate.

---

## 2026-09-03 — Darshan's two feature branches verified on real data; port map fixed (Arjhun)

### `feat/argo-overlay` and `feat/cyclone-heat` — both hold [VERIFIED]

Darshan built both without the satellite bundle on his machine, so neither had ever produced a real
prediction. Both were run here against `data/processed/daily_sat/v001` and the frozen checkpoint.

| check | argo-overlay | cyclone-heat |
|---|---|---|
| `freeze.py --check` | 18/18 | 18/18 |
| unit tests | 13 passed | 10 passed |
| diff vs branch point | 4 files, +633, 0 deletions | 6 files, +611, 0 edits |
| real run | overlay at 15N 68E, 2026-05-15 | 11,832 ocean cells, `--date 2026-05-15` |
| independent re-derivation | overlay mean == `predictor.reconstruct`, max abs diff 0.00e+00 | my own TCHP/D26 integration matches at 5/5 cells incl. the maximum |
| UI vs module | page RMSE 0.441 / bias +0.051 == module exactly (and 0.430 / +0.046 at 05-16) | page TCHP 143 / D26 119 m / OHC 45.11 == artifact 142.86 / 118.69 / 45.11 |

`band_2sigma` is `mean +/- 2 * CALIBRATED sigma` at all 15 depths, and the matched float lands
inside it at 100 m. Max TCHP 173.2 kJ/cm^2 sits at 5.25N 94.75E with D26 105 m — the eastern
equatorial warm pool, which is where it should be. OHC is finite at 9,210 of 11,832 cells: it
REFUSES shelf columns shallower than the 700 m reference instead of inventing water.

### Defect this verification exposed, in OUR code — fixed (`f5264c4`)

The cyclone page's Provenance panel reported `checkpoint: "unpromoted"` for a model `freeze.py`
records as promoted from `sat_7ch_s42`. The page was faithful; `field.py` was wrong.
`promote_run.py` writes `promoted_from` into the METRICS artifact, never into the checkpoint, so
`predictor.meta.get("promoted_from")` was always None and the `or "unpromoted"` fallback fired every
time — **including on the 3-D cube**, which the U4 rewiring had pointed at the same field.

`field._promoted_from` now returns the name only when the loaded file's sha256 IS the one promotion
recorded (the same equality `freeze.py` checks); reading the metrics file alone would have credited
any loaded checkpoint with the promotion. `inference.py` keeps `checkpoint_path` so the FILE can be
identified, not just its meta. Two regression tests, one of them an impostor checkpoint.

### Port collisions fixed, and all seven apps wired [VERIFIED]

`tscast_page.py` and `cube_page.py` both documented **8504**, so starting "the dashboard" could
serve the 3-D cube instead. `DARSHAN_BUILD_SPEC.md:1733` had already assigned tscast **8507**; the
code simply never followed it. Three more pages were documented in docstrings and absent from
`launch.json`, which is why they were always started by hand.

| port | app | | port | app |
|---|---|---|---|---|
| 8501 | `app/streamlit_app.py` (was unpinned) | | 8505 | `physics_page.py` |
| 8502 | `collocation_page.py` | | 8506 | `events_page.py` |
| 8503 | `validation_page.py` | | 8507 | `tscast_page.py` (**moved from 8504**) |
| 8504 | `cube_page.py` | | | |

All seven were started and rendered — titles and content confirmed, not assumed.
`tests/phase2/test_launch_ports.py` makes it enforceable: no two configs share a port, no two
docstrings claim one, launch.json agrees with every docstring, and every runnable page has an
entry. Negative test: re-injecting the 8504 collision fails 2 of the 10 checks.

### Open for Arjhun to decide

1. **Both feature branches carry a 44 MB deletion that belongs to neither feature.** Commit
   `3eb176e` ("Remove the stale v1 artifacts.zip snapshot") is an ancestor of both and drops
   `oceanembed_artifacts.zip` (44,393,927 bytes). Merging either deletes it from `main` too.
   Recoverable from `32a5b2f`. Untouched pending a decision. Nothing has been merged.
2. **8508 / 8509 are reserved** for `validate_page.py` and `cyclone_heat_page.py`. Their docstrings
   currently claim 8505 and 8506, which are physics and events — fix at merge time, not on his
   branches, so his "clean no-conflict merge" claim stays true.
3. **The cyclone page shows TCHP with no uncertainty at all.** Nothing false, but every other v2
   surface carries +/-2 sigma and the per-depth sigma is available to propagate through the integral.

---

## 2026-09-03 — Ocean structure (physics_page) wired onto v2, honestly [VERIFIED]

### Why it stayed on GLORYS this long

Every field on this page but one goes through `phase2.physics.layers`/`ohc`, and three of the four
-- MLD (density criterion), the barrier layer, and the real-density OHC -- take a SALINITY array.
Stage 2 (salinity + density) has never been trained on satellite input, so "wire this onto v2"
could not mean "give it a source toggle and compute the same four fields": two of the four are not
computable at all without a training run that has not happened.

### What v2 mode actually does

Added `layer_fields_v2` (physics_page) using `field.predict_field` -- computes thermocline depth,
ILD and OHC via `ohc_constant_density` (temperature only, all three real v2 output), and returns
`None` for `"MLD (density, m)"` and `"Barrier layer (m)"`. `main()` renders that `None` as an
explicit refused-not-approximated warning box in place of the map, not a KeyError and not a silent
fallback to GLORYS salinity under the v2 label. The OHC map is titled "-- constant density" and the
info box under it names the ~2% cost that assumption carries (measured in `ohc.py`, worst in the
northern Bay of Bengal). Section 3 (the validated seasonal barrier-layer claim) stays GLORYS-only
regardless of the toggle -- it needs 4 years of monthly salinity no version of v2 has -- with a
caption saying so. Section 2's profile inspector drops the salinity line and shows "n/a" tiles for
MLD/barrier rather than computing `ild - mld` against a missing MLD.

### A real bug the verification pass caught in its own new code

`main()` called `_v2_version()` in the sidebar before that name was ever defined in this file --
would have been a `NameError` the instant a user touched the v2 toggle, caught only by actually
importing and exercising the function (not by reading it). Fixed by adding the missing wrapper,
delegating to the shared helper below.

### A second, unrelated bug found while building this, fixed in the same pass

`cube_page.py`'s date selector offered GLORYS' 48 2019-2022 dates under **every** source including
"v2 satellite", and `predict_field` silently snapped each one to the nearest of the 388 real
satellite days. Measured: the sidebar's own default selection (2022-07-15) rendered 2025-06-01,
**+1052 days away**, with `provenance.days_from_requested` computed but never read by that page --
nothing on screen said so. Same class of bug as the U4 audit finding this page exists to close.
Fixed by giving the v2 branch its own date list (`_v2_dates`, drawn from the real bundle), so every
offered date is an exact match -- offset 0 by construction, not by disclosure. physics_page's v2
date list was built correctly from the start using the same fix, so it never had the bug.

### Dedup

The cache-staleness guard (`st.cache_resource`/`st.cache_data` key on ARGUMENTS, not on imported
module source -- the mechanism behind the 8 degC / 9.5-minute stale-dashboard incident) had been
pasted three times: `tscast_page._predictor_version`, `cube_page._v2_version`,
and now physics_page would have been a fourth. Factored the hashing logic into
`phase2.tscast_nio.field.v2_cache_version`; `cube_page._v2_version` and physics_page's new
`_v2_version` both delegate to it. `tscast_page.py` (Unit B) left untouched.

### Verified, not asserted

- Live-imported and called `physics_page.layer_fields_v2`/`_v2_dates` and
  `cube_page._v2_dates`/`build_cube` directly against the real checkpoint and bundle (`st.set_page_config`/
  `st.cache_data`/`st.cache_resource` are safe to invoke outside a live app -- confirmed by hand, they
  warn and fall back to in-memory caching, matching the existing `test_volume.py` precedent of not
  relying on that but going further to actually prove it works here).
- `layer_fields_v2` on 2026-06-18: MLD/Barrier `None`; thermocline finite over 11,832 ocean cells,
  range [2.5, 175.0] m; ILD finite at 10,974 cells, range [20, 100] m; OHC(const-rho) finite at
  9,492 cells, range [19.9, 28.5] GJ/m^2 -- all physically plausible, none NaN-everywhere.
- `cube_page.build_cube` with a v2-native date: `days_from_requested == 0`, `cube.date` equals the
  requested string exactly.
- Rendered both pages live in-browser, toggled the radio both directions, opened the Provenance
  expander (`checkpoint: "sat_7ch_s42"`, confirming the earlier promoted_from fix reaches this page
  too since it shares `predict_field`), scrolled through every section.
- 7 new tests in `tests/phase2/test_physics_v2.py`, all against real data (no synthetic profiles --
  a fabricated one would not have caught the calendar bug or the missing `_v2_version`). Two
  negative tests run by hand: reintroducing the GLORYS-date bug fails 2 tests; fabricating an MLD
  instead of refusing it fails 1. Restored after.
- Full suite: **554 passed, 10 skipped** (was 547; +7 new).

### Still true, unchanged by this

Stage 2 has never been trained on satellite input -- this is the reason MLD/barrier layer/real-OHC
stay refused on v2, not a gap this change closes. `events_page.py` is still untouched, same reason.

---

## 2026-09-03 (later) — the "why does glorys show 2022" answer: it was reading the wrong bundle

### The finding, and a correction to the entry above

Arjhun asked why glorys mode showed 2022-07-15. Because `physics_page` read
`data/processed/grids.npz` — Phase-1 GLORYS, 48 MONTHLY steps, 2019-01-15..2022-12-15 — which is
all that file has. Meanwhile `data/processed/daily` has carried **GLORYS daily 2025-06-01..
2026-06-23, salinity included**, the whole time.

**This corrects the entry above.** That entry said MLD/barrier layer were refused on v2 because
"stage 2 has never been trained on satellite input" — true, but I had also probed for salinity
using the key `sal` when the actual key is `salinity`, concluded "salinity=NO", and framed the
refusal as "there is no salinity to compute them from". There IS salinity: shape
(388, 100, 240, 15), 0.498-40.172 psu, and it is **byte-identical between `daily` and
`daily_sat/v001`** — both bundles carry the same GLORYS12V1 target-side field. [VERIFIED]

The refusal is still correct, and the real reason is sharper: that salinity is REANALYSIS. Using
it for a "v2 satellite" MLD would put a GLORYS field inside a number labelled satellite — the
contamination the anti-GLORYS guard exists to catch, and what the PS excludes with "only surface
satellite observations". The 7 input channels carry a SURFACE `sss` (SMOS blend); nothing predicts
salinity AT DEPTH. So it is a compliance boundary, not an absence.

### What changed

Both toggle positions now read **the same day from the same bundle**:

| | source | fields | density |
|---|---|---|---|
| `v2 satellite` | shipped model reconstruction | thermocline, ILD, OHC | constant (approximation) |
| `glorys` | GLORYS12V1 target in the same bundle | **all four** | real ρ(S, θ) |

`layer_fields_glorys` reads `temp`/`salinity` out of the predictor's already-loaded bundle, so it
costs no second load and guarantees one grid, one date, one file. The old `layer_fields(idx)`
(Phase-1 monthly) is deleted; nothing outside the page referenced it.

That makes the toggle a **model-vs-truth comparison** rather than a comparison of two eras.
Measured on 2026-06-18, thermocline model vs GLORYS: **bias +0.85 m, RMSE 23.09 m over 11,832
cells** — a number that could not be produced at all while the two sides sat 1,300 days apart.

Section 3 alone still reads Phase-1 2019-2022 monthly, and now says so explicitly: a seasonal
climatology needs several years per month, the 388-day bundle covers each month about once, and
recomputing on it would silently change the published 9.5 m / 7.1 m magnitudes.

### Verified

- glorys on 2026-06-18: MLD 20-125 m (11,062 cells), barrier layer 0-80 m (10,840), thermocline
  2.5-175 m (11,832), ILD 20-150 m (10,840), OHC real-ρ 20.1-28.7 GJ/m² (9,492).
- Rendered live, toggled both ways: **the date stays 2026-06-18 across the toggle** — the symptom
  that started this is gone.
- 3 new tests (10 in the file): both sources resolve the same requested day; glorys computes all
  four with real density; and `layer_fields_v2` neither reads `salinity` in its body nor returns a
  salinity array — the compliance boundary as an executable check, needed precisely BECAUSE the
  salinity is sitting right there.
- Full suite: **557 passed, 10 skipped**.

---

## 2026-09-03 (later still) — events_page: same era bug, plus a false provenance string

### The era bug, same as physics_page

`events_page` read `data/processed/grids.npz` — Phase-1 GLORYS, 48 monthly fields, 2019-2022.
Now reads the daily bundles, 388 consecutive days 2025-06-01..2026-06-23, with a source toggle:

| | surface fields | what the detectors see |
|---|---|---|
| `satellite` | daily_sat/v001 | GLOBCURRENT currents + OSTIA SST — real observations, the PS deliverable |
| `glorys` | daily | the reanalysis of the same days |

No model reconstruction is involved on either side: eddies and fronts are SURFACE diagnostics, so
"satellite" here means the detectors read genuine observations. Measured on 2026-06-18, same day
both ways: **satellite 140 eddies (62 cyc / 78 anti, mean r 52.6 km), 35 fronts; glorys 123
eddies (59/64, 50.2 km), 40 fronts.** [VERIFIED]

### A false provenance claim, found by moving the page

`eddy.summarise()` hardcoded `"source": "GLORYS reanalysis surface currents, not observations"`.
It receives a list of eddies and cannot know what produced them. That string was accidentally TRUE
while the only caller read the Phase-1 GLORYS grids — and became FALSE the instant the page could
read satellite currents: fed GLOBCURRENT, it still reported GLORYS. Same defect as the hardcoded
`"input_source": "glorys"` in inference.py and the `"unpromoted"` checkpoint in field.py.

Now `summarise(eddies, *, source=None)`. Omitting it yields an explicit
`"unspecified -- the caller did not say which currents these are"`, so an un-updated caller reads
as unknown rather than confidently wrong. Regression test asserts it claims neither GLORYS nor
satellite when not told.

### Claims that stopped being true, and were rewritten rather than left standing

The page's own docstring said **"DETECTION, NEVER TRACKING. The record is 48 monthly fields"**, and
its closing expander said marine heatwaves were **"permanently closed at monthly cadence"**. Both
were honest for monthly data and are wrong for 388 consecutive days. Rewritten: tracking and MHWs
are now **UNBUILT, not impossible** — a gap being stated, not a limit of the data. The sub-mesoscale
limit (0.25° ≈ 25 km) is a real limit and is marked as one that does not move.

### Upwelling: what could NOT move, and why

- Its shoaled-thermocline term needs subsurface T and S. Those are GLORYS in BOTH bundles
  (byte-identical), so the panel says on screen that its subsurface half is GLORYS either way and
  that nothing there is a satellite-only product.
- **The wind-stress product runs 2019-01..2022-12 only** (48 monthly files) and cannot reach the
  2025-2026 window. So there is no Ekman term: the result is a signature, not an attribution.
  `wind_attributed: False` already records this as data; the page now explains why rather than
  showing a bare "no". The closing caveat about monthly-mean stress is conditional on wind
  actually having been used.
- Verified on 2026-06-18: **387 cells flagged, wind attributed no, limiting term
  shoaled_thermocline** — identical headless and on screen.

### Great Whirl panel

Stays on Phase-1 GLORYS monthly 2019-2022 and now says so, for the same reason physics_page's
section 3 does: a four-year seasonal climatology cannot be recomputed on a 388-day record without
silently changing published magnitudes (77 km month 12 → 243 km month 8).

### Verified

Rendered live on 8506, toggled sources and all three field panels; on-screen numbers match the
headless run exactly. 4 new tests (1 in test_events.py for the provenance fix, 3 in
test_physics_v2.py for the page wiring). Full suite: **561 passed, 10 skipped** (was 557).
