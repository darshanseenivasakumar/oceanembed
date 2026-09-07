

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

---

## 2026-09-03 (last) — collocation_page: taken from Unit B, message fixed, 2026 era added

Taken with Arjhun's explicit authorization (as with `tscast_page.py`). Told Darshan via this entry.

### The bug: an empty Argo match was explained as an empty OCEAN

`argo_test.parquet` holds **2022 only** (32,836 rows; zero in 2019/2020/2021). The date picker
offered all 48 grid dates, 12 per year — so **36 of 48 (75%)** fell in years the table has no rows
for. On every one the page said:

> "No Argo profile within tolerance. 2,455 floats across ~15 million km² is genuinely sparse —
> that gap is the problem this project exists to fill."

That asserts a fact about the ocean from an absence in a file. Measured at 15°N 65°E, open Arabian
Sea, same point and tolerance: **no match 2019 / 2020 / 2021, match in 2022.** The only variable
was the year. [VERIFIED]

This is precisely the hazard `CollocationEngine`'s own docstring names — *"indistinguishable from
genuinely unsampled ocean"* — which Darshan identified and solved for the v2 path by making the
table caller-selected. The page still walked into it.

### Fixed by making the page read coverage instead of describing the sea

New on the engine: `argo_coverage()` (table, span, years, rows) and `argo_table_covers(when)`. The
page now branches on evidence:

* year NOT in the table → **warning**: *"No Argo data for 2019 in this table — this says nothing
  about the ocean. argo_test spans 2022-01-01 to 2022-12-31 (32,836 rows). An empty match here is
  a gap in the reference table, not an unsampled sea."*
* year IS in the table → the sparsity explanation, which is now true when shown.

The neighbouring `"satellite covers 24 of our 48 dates"` was accurate but hardcoded; it is now
counted per era (`_satellite_coverage`), and the monthly-grid caveat is conditional on the era.

### 2026 era added

`CollocationEngine(era=...)`, `ERAS = ("phase1", "daily")`:

| era | grids | satellite | argo table |
|---|---|---|---|
| `phase1` (default) | grids.npz, 48 monthly 2019-2022 | satellite_grids.npz (24 dates) | argo_test |
| `daily` | `daily` bundle, 388 daily 2025-2026 | `daily_sat/v001` — real observations | argo_daily_period |

`_npz` presents the daily bundles in the Phase-1 key layout, so `collocate()` needs no branch of
its own and the two eras cannot drift into computing different things. `argo_table` now defaults
FROM the era rather than being fixed at `argo_test`; an explicit table still overrides. That is not
the "guess from the date" the docstring forbids — the era is a choice the caller states.

The daily bundles carry no subsurface currents, so u/v profiles come back all-None with a
`SUBSURFACE_CURRENTS_UNAVAILABLE` flag naming the bundle rather than implying an unsampled ocean.

### Verified

- **phase1 is byte-identical**: `CollocationEngine()` still era=phase1 / argo_test; all 20 original
  tests pass untouched.
- daily era at 15°N 65°E on 2026-06-18: exact day, 0 d offset, SST 29.98 (GLORYS) vs **29.52
  (satellite — genuinely different numbers)**, 15/15 profile levels, provenance era/argo_table
  recorded.
- daily Argo matching **works**, not just "doesn't crash": a float taken from the table matched at
  0.0 km / +0 d / 14 levels; live UI showed another at 71 km / −7 d.
- Rendered live on 8502, both eras, with a successful Argo match on each (phase1: 53 km / +5 d).
- Both message branches rendered and their exact text checked.
- Explicit widget keys (`era`, `date_<era>`) added after the era was seen resetting under
  automation — the sidebar is built in two blocks, and position-derived widget identity is one
  rerun away from silently changing the record under the user.
- 5 new tests; full suite **566 passed, 10 skipped** (was 561).

### Not verified

The warning branch's on-screen pixels. Its condition, inputs and exact string are all checked, but
Streamlit's 48-item dropdown resisted automation and I did not select a 2019 date in the browser.

---

## 2026-09-04 — the depth-error chart: it already existed, and it was unreadable

Arjhun asked for a jury-facing depth-vs-RMSE plot, believing the numbers were "just in a table".
They were not — `tscast_page` has had exactly that chart beside the table all along. **It was
rendering as a zigzag through itself**, which is very likely why it read as a table page.

### The bug

`mark_line(point=True)` with `x=RMSE`, `y=depth`. **Altair sorts a line by its X encoding unless
given `order`**, and RMSE is not monotonic in depth (0.40 surface → 1.19 at 50 m → 1.08 at 75 m →
1.22 at 100 m), so the line was drawn in ascending-RMSE order and crossed itself repeatedly.
Nothing errored; the numbers were right; the picture said "unstable model". `validation_page`
carried the identical defect in **both** of its panels. [VERIFIED]

### The honesty correction that mattered more

The brief was "your line beats climatology everywhere". **It does not.** At 1000 m climatology
wins by 0.012 °C (0.293 vs 0.305) — **14 of 15 depths, not 15**. The chart now draws the band from
the SIGNED difference and labels the crossover outright ("climatology wins by 0.012 °C here"),
with a test asserting the label appears on the real data and does NOT appear when a model really
does win everywhere. The page's existing copy already explained why this happens (the deep ocean
barely varies, so climatology is near-unbeatable there); the chart no longer contradicts it.

### What the chart now shows

Model and climatology as 2px profiles ordered by depth, the gap between them shaded as one
quantity (that gap IS the skill), a legend below the plot, and three selective annotations — the
thermocline peak (our worst, 1.22 °C at 100 m), the widest gain (+0.56 °C at 200 m), and the
crossover. Error is small at the surface, bulges through the thermocline where a surface field
constrains depth least, and collapses below 500 m. The physics, at a glance.

### Colour, computed rather than chosen

Ran the palette validator instead of eyeballing:

* old pair `#1f77b4` / `#999999` — the grey **FAILED** the chroma floor and sat at **2.78:1**.
* first fix `#eb6834` passed on white and **FAILED** the dark lightness band (0.671). No theme is
  pinned in this project, so Streamlit follows the viewer's browser — the demo laptop picks the
  mode, not us.
* shipped pair **`#2a78d6` / `#d95926`** passes all six checks in **both** modes (worst adjacent
  CVD ΔE 25.4 protan, normal-vision 32.3, contrast ≥3:1). The Validation Lab's skill panel
  (`#1baf7a`) passes alongside them.

**Annotation ink was a live defect found by measuring the rendered DOM:** Streamlit themes axis
text but NOT free `mark_text`, which defaults to **black — rgb(0,0,0) on rgb(14,17,23), 1.11:1,
invisible**. Now `#787878`, the balanced dual-surface optimum (4.30:1 light, 4.28:1 dark).

### Verified

Rendered both pages and inspected the live SVG: annotations `rgb(120,120,120)` @12px, model line
`rgb(42,120,214)` 2px, climatology `rgb(217,89,38)` 2px. 5 new tests in
`tests/phase2/test_depth_chart.py`, one run as a negative control by hand (deleting `order`
fails exactly the ordering test). Full suite **571 passed, 10 skipped** (was 566).

### Still open, unrelated and unresolved

The Validation Lab headline (**RMSE 0.9638 / 879 profiles**) still disagrees with the freeze
manifest (**0.9078 / 962**). Flagged 2026-09-03, never traced.

---

## 2026-09-05 — Prompt 7: export to NetCDF and an HTTP API (Arjhun)

Prompt 4 (live mode) **deferred by Arjhun** — six hard blockers, recorded in the plan file and
summarised at the end of this entry so they are not rediscovered.

### The gap this closed

There was no way to get a reconstruction out of the system. Verified before starting: zero hits for
`fastapi`, `flask`, `st.download_button` or `BytesIO` anywhere. A jury asking "can I have the data?"
got nothing.

### Schema §5 was a contract nobody checked

`docs/phase2/tscast_output_schema.md` §5 is marked `Status: CONTRACT` and requires ten provenance
keys. **Neither producer satisfied it** and **nothing tested it** — the point path omitted
`checkpoint_sha256` and `code_commit`; the field path omitted those plus `P`, `input_date` and
`clim_train_years`. New `src/phase2/tscast_nio/provenance.py` assembles the block once and asserts
the contract holds; both paths now emit all ten. `tests/phase2/test_provenance.py` parametrises over
the keys **and** source-text-guards the doc, so code and contract cannot drift apart silently.

The git-hash helper was copy-pasted in five places. Those five are **deliberately untouched** —
working training/pipeline code, three of them one-shot scripts. New code uses the helper.

### The export

`src/phase2/export/netcdf.py` — `field_to_xarray` / `write_netcdf` / `to_bytes` / `export_field`.
Not an extension of `heat_content.to_xarray`: that is 2-D and this is `(lat, lon, depth)`, and one
function serving both would branch on dict keys, i.e. a second definition of "a product file".

Three rule-8 decisions in the file format:
- **`_FillValue` set explicitly** on every float var. Left to a reader's default, a land cell
  becomes a 0 °C measurement.
- **A stage-1 file omits the salinity variables entirely**, with an attr saying why. An all-NaN
  `salinity` grid asserts "this file has salinity, missing everywhere" — a different, false claim.
- **Masks are int8 flags** with `flag_values`/`flag_meanings`. NetCDF has no bool, and a silent
  float cast is how a mask stops being a mask.

`scripts/phase2/export_field.py` **refuses an out-of-bundle date** rather than snapping, and the
refusal names the range. Exit 1, verified.

### Measured, replacing an [INFERRED] claim

`field.py` said *"seconds on the GPU, under a minute on CPU"* — an estimate standing where a reader
takes a cost figure. `scripts/phase2/measure_export_timing.py` → `artifacts/export_timing.json`:

| | measured |
|---|---|
| `predict_field` | **32.09 s** median of 4 (30.98–32.92) |
| predictor load | 7.20 s, paid once |
| build + write | 0.49 s + 0.25 s, 3.29 MB |

And the estimate was wrong in a way that mattered: **CUDA is available and the inference path never
uses it.** `TSCastPredictor` loads with `map_location="cpu"` and never moves the model, so every
dashboard reconstruction is a CPU reconstruction. `model.to("cuda")` measures **7.78 s — a 4.1×
speedup** — and agrees with CPU to **max |diff| 6.9e-4 °C over 153,291 cells**, float32 noise
against a 0.9 °C RMSE. **The default is deliberately left on CPU**: switching days before a demo
would make an exported file differ in its last digits from the page beside it. Recorded so it is a
decision someone takes, not a discovery someone repeats.

### The API

`src/phase2/api/service.py` holds every decision and **imports no web framework**; `app.py` is a
thin FastAPI adapter. FastAPI was taken only for its `/docs` page; if it ever conflicts with the
starlette version Streamlit pins, `app.py` becomes a starlette adapter and nothing else changes.

**The dependency risk was to Streamlit, not the data pipeline** — `copernicusmarine` has no
starlette dependency; `streamlit 1.62.0` pins `starlette<2,>=0.46.0`. Gated accordingly: dry-run
report read before installing, then `fastapi` → `streamlit` → `copernicusmarine` imports in that
order. **starlette stayed at 1.6.0.**

`GET /health · /coverage · /profile · /field.nc`. Two things that must not be "simplified":
- **Handlers are `def`, never `async def`** — an async handler calling `predict_field` blocks the
  event loop for 32 s. Guarded by an **AST** check (a text grep matches the warning in the
  docstring as readily as a violation).
- **Every predictor call is inside a lock.** `predict_field` borrows `ds.index`; `reconstruct`
  **overwrites it and never restores it**. Two concurrent requests return plausible wrong answers
  rather than raising.

`test_launch_ports.py` broke on a non-Streamlit entry (`args.index("run")` → ValueError). Fixed by
scoping the two page tests to Streamlit configs **and adding back the lost property** as
`test_the_api_config_port_matches_its_module_docstring`. Port collision still checks every config.
API on **8511**, `127.0.0.1` not `0.0.0.0`.

### Verified live

`/health` and `/coverage` 200 with real bundle dates; `/profile` **1.1 s**, 15 depths, no `NaN`
token in the body; `/field.nc` **3.29 MB in 34.3 s**, correct content-type, reopens as valid NetCDF
carrying `input_source=satellite` and the checkpoint sha. `/docs` renders all four routes. An
out-of-bundle date returns **422 naming the valid range**, on both endpoints.

**681 passed, 9 skipped** (was 628). This closes a real gap: no test in this repo previously wrote a
product file and read it back, and `to_xarray` had zero tests.

### Not attempted, deliberately

Consolidating the five `_commit()` copies; de-mutating `predict_field` (the correct fix reopens the
field-equals-point guarantee); renaming `provenance["checkpoint"]` (app pages read it —
`promoted_from` added beside it); switching inference to GPU. All post-demo.

### Prompt 4 blockers, for the record

`sat_daily_pipeline.build_year` requires a GLORYS target and drops days lacking one — GLORYS `my`
ends 2026-06-23, so every live day would be dropped and the bundle would come out empty; `build_year`
is year-granular and overwrites the whole year npz; `download_wind_daily.download_months` clips to
module constants; `build_daily_wind` has no incremental path; `inference.forecast` compares against a
hardcoded `LAST_GLORYS` so **the guard inverts** once the bundle extends; `verify_sat_bundle`
hard-fails without a matching GLORYS year. The bundle is 74 days stale and SSS lag (~6 d) binds.

## 2026-09-06 — the three stranded novelty features move into the instrument

Cloud dropout, the physics/consistency measurement and the cyclone case study were the three
spec features still reachable only on their own ports. They are now features in the one-page
instrument on 8500, which is grouped SEE IT / PROVE IT / STRESS IT.

The wake is PRECOMPUTED by `scripts/phase2/run_cyclone_wake.py` into
`artifacts/cyclone_wake_<sid>.{json,npz}` and rendered behind a CACHED chip. Live it costs about
17 whole-basin reconstructions (~9 min CPU) once the 6-entry field cache evicts; precomputed it
is 48 reconstructions for all four storms in 6.0 min on CUDA, once.

All four usable storms resolve a cold wake. SHAKHTI reproduces A26 exactly: -4.26 kJ/cm2 and
11/12 points cooled passage-relative, against -0.18 and 7/12 for one fixed date pair.

F6 (buoy time-axis validation) re-probed 2026-09-06: NOAA catalogue reachable in ~2 s, data layer
times out after 44 s. Same shape as A28, on a day the machine had working network. Still blocked.

Ports unchanged. app/phase2/, src/, app/streamlit_app.py and app/panels/ are untouched.

---

## 2026-09-07 — audit session — four mechanical fixes from the 2026-09-06 audit, with tests

Scope: the four items the audit called mechanical (#11, #12, #20, #21 in the audit report). No
scientific number changes; no artifact, bundle or checkpoint touched. 14 new tests, red before
the fix and green after; the full suite was re-run afterwards (see AGENT_SYNC / chat for the count).

* **`scripts/phase2/freeze_headline.py --verify` no longer fails on the training machine.** A
  checksum carried forward from the other machine (`checkpoint_frozen_elsewhere`) was reported as
  "MISSING (was frozen, now gone)" and the script exited 1 — the machine jury note 08 tells the
  presenter to run it on, live. Such entries are now `[pend]`; a checkpoint frozen HERE that is
  gone or changed still fails. Verified: exit 0 on this disk, 2 ok / 2 pend.
* **`TSCastPredictor` refuses what it cannot answer for** (`inference.assert_point_in_domain`,
  `_cell`, `_time`). Before: (45N, 120E) snapped to the domain corner, lat=NaN snapped to (5N, 45E)
  and returned a full profile with an error bar, and a 2020-01-01 request was served from the
  2025-06-01 inputs with `forecast=False` and `days_from_requested=1978`. Now: out-of-REGION or
  non-finite coordinates raise `ValueError`; a date before the bundle's first day raises; a date
  after the bundle is unchanged (served, labelled FORECAST). `api/service.profile` returns 422
  `point_out_of_domain` with the domain spelled out, before the lock and before the model runs.
* **Truth and Argo limits are read from the data, not typed.** `predictor.first_day`,
  `last_truth_day` (bundle) and `last_argo_day` (the predictor's own Argo table) replace the
  module constants in `reconstruct` and in `/coverage`. `LAST_ARGO` had read 2026-08-24 while
  `argo_daily_period.parquet` ends 2026-06-22, and `output.build_record`'s forecast note repeated
  the typed date; the note now names the limits it is given and says "unknown" for an absent one.
  The constants stay importable as documented fallbacks for a stub with no bundle.
* **An even `T_SEQ` is refused.** `_window` takes `T_SEQ // 2` steps each side, so `t_seq=10` built
  an 11-step window with no error. `dataset.GriddedPatches` and `config.sanity_check` now require a
  positive odd value. The shipped T_SEQ=11 is unaffected.

Files: `src/phase2/tscast_nio/{inference,output,dataset,config}.py`, `src/phase2/api/service.py`,
`scripts/phase2/freeze_headline.py`; tests appended to `tests/phase2/test_{tscast_dataset,
frozen_manifest,tscast_inference_path,api,tscast_output}.py`. Not committed by the audit session:
the tree carried another session's uncommitted work, so the commit is left to the owner.

Still open from the same audit and NOT touched here (they change numbers or need retraining):
epoch selection on test-period GLORYS (#7), Argo pressure treated as depth (#8), buoy validation
spanning the training period (#9), below-seafloor comparisons inside the headline (#10), and the
presentation claims (#1–#6) — see the audit report.

---

## 2026-09-07 — audit session — six wrong claims corrected in the jury pack, the deck and the record

The audit's highest-risk findings were not code. They were sentences: numbers the project's own
files forbid quoting, and Phase-1 measurements restated about the shipped v2 model. All six are
corrected at SOURCE, the 19 PDFs are rebuilt, and a new guard makes each one a test failure if it
comes back. No model, artifact, bundle or metric changed — only what we say about them.

**The measurement behind the corrections.** The shipped checkpoint was re-scored against the same
962 profiles, with GLORYS scored at the identical cells and days, so "inherited vs ours" could be
split on the deliverable rather than inferred from Phase 1:

| depth | model | GLORYS target | ours |
|---|---|---|---|
| 20 m | 0.780 | 0.553 | +0.227 |
| 50 m | 1.187 | 0.805 | +0.382 |
| 100 m | 1.218 | 1.042 | **+0.178** |
| 150 m | 1.063 | 0.999 | +0.065 |

Bias: model +0.1003, target +0.1078, model against its own target **−0.007**.

1. **The T_SEQ claim is WITHDRAWN.** The pack presented "the paper's 31-day window is the worst of
   three (0.9267 / 0.8529 / 0.9096)" as a measured disagreement. All three legs predate the
   embargo fix; `artifacts/INVALID_PRE_EMBARGO.md` lists the 31-day leg under *never quote*; the
   two shorter legs were only ever "declared" and their checkpoints were overwritten. The pack now
   says we ship an 11-day window and cannot presently prove it is the best one, and names the
   re-run as an open item. "Three measured disagreements" is now two, each labelled one-seed.
2. **"Thermocline error is inherited — within 0.023 °C"** was a Phase-1 number restated about v2.
   On v2 the gap at 100 m is **0.178 °C**: still mostly inherited, not at the ceiling. The Phase-1
   figure survives only where the Validation Lab page genuinely displays the Phase-1 record, and
   there it is labelled as such.
3. **"The model runs warm — ours"** is corrected to *mostly inherited*: the target carries the
   average. What is ours is the shape, +0.447 °C added at 50 m.
4. **The deck quoted the GLORYS-fed comparator as the deliverable.** Speaker notes on slide 7
   carried `embargo_withUV_s42` (0.8645 / 0.8873 / +0.1105 / 0.2948) and slide 9 carried its
   calibration ratios; slide 8 carried its 1000 m RMSE. All now read the shipped run.
5. **Slide 8 contradicted slide 7** on climatology. It now reads 14 of 15, with the 1000 m
   crossover named.
6. **The 962 profiles** are described as matched within 5 days of the test window, which is what
   they are: 908 fall strictly inside it and score 0.9054 °C.
7. **The buoy validation is no longer called blocked.** It ran on 2026-09-06 (46 series, median
   RMSE 0.477 °C) — but every series lies inside the TRAINING period and moored profiles feed the
   reanalysis we train against, so it is labelled an **in-sample** check and must not be quoted
   beside the 962-profile headline.

Also corrected while in the same sentences: slide 5's training time (the deliverable took 9.2 min,
not seed 43's 8.5), slide 9's stale "recalibration is scheduled" (it ran on 2 Sep), and slide 11's
"0.02 °C is signal not noise" — the three-seed spread is itself ~0.02 °C and two of three channel
effects flip sign, so that is the noise floor, not signal.

**New guard:** `tests/phase2/test_presentation_claims.py` (9 tests) reads the jury-note SOURCES and
the deck itself, not the built PDFs, because fixing a PDF without its source is a correction that
disappears at the next `build_all.py`. It asserts the retracted legs are absent, that any 0.023
mention is scoped to Phase 1, that the deck's headline equals `frozen_manifest.json`, and that no
slide claims climatology is beaten everywhere. Three of the four deck guards were checked against
the pre-fix backup and fail on it; the fourth is documented as forward-looking, and the two string
guards carry their own controls so neither can pass vacuously.

Files: `JURY_NOTES/_build/{features_01_06,features_07_12,note_19_conclusion}.py` (18 regions), all
19 rebuilt PDFs, `OceanEmbed_SIH26066.pptx` (7 runs across 5 slides and 2 notes),
`PROJECT_RECORD.md`, `PHASE2_STATUS.md`, and the new test file. The deck was validated against the
original as baseline and passes; **visual rendering was NOT possible — no LibreOffice on this
machine — so slide layout after the text changes is UNVERIFIED.** The longest addition is +27
characters on a full-width subtitle; someone should open the deck once and look at slides 7, 8, 9
and 11.

Still open from the audit and NOT touched: epoch selection on test-period GLORYS, Argo pressure
treated as depth, the buoy split, below-seafloor comparisons inside the headline. Those change
numbers or need retraining.

---
---

## 2026-09-07 — Audit #10 closed: the scorer no longer compares below the seafloor (`seafloor_masked_v1`)

**The bug.** `eval_argo.collocate` handed every Argo depth to `metrics.per_depth`, including depths
where the GLORYS training target has no water. The shipped product refuses those points —
`output.build_record` returns None below the target's seafloor — so the headline was scored on
comparisons the product itself will not make. 93 of 12,829 comparisons, plus one profile whose
nearest cell is land. RMSE there was 1.614 °C, so they were not noise. **[VERIFIED]**

**The fix.** A named scoring protocol, `SCORING_PROTOCOL = "seafloor_masked_v1"`, in
`src/phase2/tscast_nio/eval_argo.py`:

* `seafloor_mask(la, lo, valid_mask, land_mask)` → (N,15) water-and-not-land,
* `apply_seafloor_mask(truth, ...)` → truth with those cells set NaN, plus a `refusals` dict that
  **counts what was declined and why** (`n_refused_below_seafloor`, `n_profiles_on_land`,
  `per_depth_refused`). Refusals are recorded in every metrics JSON, never silently dropped.

`collocate` now returns the masked truth and the refusals. `train_stage1`, the reliability harness,
`calibrate_uncertainty`, `run_cloud_dropout`, `measure_physical_consistency` and `score_by_basin`
were wired through it; `harness.control_rmse` is protocol-aware and returns `agrees=None` with a
note rather than comparing across protocols.

**Held back from this commit, deliberately.** Five files carry another session's uncommitted
work, so committing them whole would commit that work: `train/train_stage2.py` (its `--w-stab`
branch), the wholly untracked `src/phase2/reliability/harness.py`, `app/ui/words.py`, and the
untracked `app/ui/features/{buoy,assimilate}.py`. **The stage-2 mask wiring, the harness's
protocol-aware `control_rmse`, and the buoy/assimilate labels are in the working tree and tested
there, but are NOT in this commit** — they will land with that session's own commit, and a fresh
clone of this branch does not have them. `app/ui/words.py` is committed as a synthesized blob:
HEAD plus my four headline corrections, none of their additions.

**The deliverable, re-scored** (`scripts/phase2/rescore_checkpoint.py`, same checkpoint
`53848bb5…`, promoted with `promote_run.py --rescore seafloor_masked_v1`):

| | `unmasked_v1` | **`seafloor_masked_v1`** |
|---|---|---|
| RMSE | 0.9078 | **0.9006** |
| bias | +0.1003 | **+0.1066** |
| correlation | 0.8812 | **0.8809** |
| skill vs climatology | +0.2595 | **+0.2400** |
| Murphy skill | +0.4517 | **+0.4225** |
| n | 12,829 | **12,736** |

**A second finding, from the same work.** `build_samples` drops any-NaN columns, so no cell
shallower than 1000 m contributes a training row — and `build_climatology` fills those cells with a
**basin mean**. 67 of the 962 profiles are therefore scored against a climatology that does not
exist, where "skill" read +0.55. `metrics.per_depth(baseline_ok=…)` now reports a second, labelled
number on the 895 profiles whose cell has a real per-cell climatology:
**skill +0.1494** (RMSE 0.8768 against climatology 1.0308, n = 12,054). Both are recorded; the
blended +0.2400 is no longer quoted alone.

**Two claims changed sign or size under the mask, and were corrected everywhere:**

* *Satellite input costs +0.019 °C, retains 92 % of the comparator's skill.* Re-measured on three
  seeds: **+0.0263 / +0.0267 / −0.0028**, mean +0.0167. **The sign does not hold**, so by this
  project's own three-seed rule the overall cost is no longer an established effect — the two input
  sources are within seed noise, and the satellite model retains ~94 %. The per-basin split was
  **not** re-run and is now labelled `unmasked_v1`.
* *At 1000 m climatology wins by 0.012 °C.* Now **0.055 °C** (climatology 0.2497, model 0.3048).
  Dropping the 21 below-seafloor comparisons there costs climatology far more than the model, so
  scoring them flattered us. Still 14 of 15 depths. The widest gain moves from +0.56 at 200 m to
  **+0.53 at 5 m**.

**Recalibrated** (`artifacts/uncertainty_calibration.json`; the old file kept as
`…_unmasked_v1.json`): ±1σ 0.6389, **±2σ 0.9127**, per-depth range **[0.8007, 0.9601]**. The "80.1 %
at 50 m" limit is unchanged; the top of the range moves 95.5 → 96.0 %.

**Also traced and closed:** the Validation Lab / freeze manifest disagreement (0.9638 / 879 against
0.9006 / 962), open as **[UNKNOWN]** since 2026-09-03. `validation/lab.py` reads
`artifacts/argo_error_by_depth.json`, written by `scripts/eval_satellite_vs_argo.py`, which scores
the **Phase-1** model on **12 monthly dates in 2022** against `argo_test.parquet`. Two models, two
eras, two records — not a contradiction. **[VERIFIED]** by reading the code, not inferred.

**Tests.** `tests/phase2/test_eval_argo_seafloor.py` (7 new: toy-grid behaviour plus a real-data pin
on 962 kept / 93 refused / 1 land / n 12,736 / 21 refused at 1000 m / 895 real-baseline profiles).
`test_frozen_manifest.py` now groups legs by protocol and demands a `comparability_note` on any leg
scored under a different one from the deliverable. `test_presentation_claims.py` gains two guards:
the app must not present a superseded headline unlabelled, and the manifest's deliverable must carry
the current protocol. Both were confirmed RED before the fix (13 offending UI lines).

**Every quoted surface was moved or labelled**, in two audited passes with a `count == 1` guard per
region: the five jury-note sources and their 19 rebuilt PDFs, `PHASE2_STATUS.md`,
`PROJECT_RECORD.md`, eight `app/` files, `src/phase2/derived/acoustics.py`,
`scripts/phase2/freeze_headline.py`, and eight runs in the deck (slides 7, 8, 12 and speaker notes
7 and 9). Historical artifacts are **not** rewritten — they are labelled `unmasked_v1` where they
appear. The manifest was re-frozen; the stage-2 legs carry a `comparability_note` because they were
never re-scored.

**Deck layout after the text edits is [UNVERIFIED]** — no renderer on this machine. Schema, rels,
content types and chart checks pass (`validate.py --original`).

---
---

## 2026-09-07 — Audit #7: model selection no longer reads the period the headline is scored on

**The bug.** `train_stage1.py:265` built the early-stopping loader from `te_t`, the
2026-04-01..06-23 GLORYS test block, and the epoch with the lowest NLL on that block was the one
saved. The Argo headline is then scored on the same days. So the shipped epoch was the one that
best fit the block being scored. The temporal embargo already stopped training INPUTS from reaching
the test block; nothing stopped the SELECTION SIGNAL from being computed on it. **[VERIFIED]** by
reading the code and by the delta below.

**The fix.** `dataset.selection_split(times, tr_t, te_t, t_seq, val_days, n_blocks)` carves the
selection set out of the train block, with an embargo on **both** sides:

* train → val: a training target within `t_seq//2` of a val day reads val surface fields, which
  flatters the signal it is selected on. Dropped.
* val → test: a validation target within `t_seq//2` of the first test day reads TEST surface
  fields. Harmless for a test target — those observations genuinely precede the forecast date —
  but not for a selection target. Dropped.

`n_blocks=1` (default) reserves one trailing block. Above 1 the same budget is spread over evenly
spaced blocks from the start of train to its end, purged on both sides; `embargo_indices` is
single-sided and cannot express that, so the forbidden days are marked on the time axis and every
training window is checked against them. On the shipped bundle:

| layout | train steps | val steps | months the signal sees |
|---|---|---|---|
| 1 block, 46 days (default) | 253 | 41 | Feb, Mar |
| 3 blocks, 45 days | 239 | 40 | Mar, Jun, Oct, Nov |

The test block is now instantiated **after** the best epoch is restored, so it cannot be reached
during training at all. Runs record `protocol: embargoed_v3_val_carved` and
`selection.selection_protocol: val_carved_v1`; everything earlier is `test_period_v0`.
`best_heldout_nll` is replaced by `best_val_nll` so a stale reader fails loudly instead of
quietly changing meaning. `--test-samples` survives as an alias for `--val-samples`.

**What it costs, three seeds, same 962 profiles and the same `seafloor_masked_v1` scoring:**

| seed | control (`test_period_v0`) | leak-free (`val_carved_v1`) | delta | epoch chosen |
|---|---|---|---|---|
| 42 | 0.9006 | 1.0121 | +0.1115 | 4 → 1 |
| 43 | 0.8989 | 0.9685 | +0.0696 | 3 → 1 |
| 44 | 0.9023 | 0.9684 | +0.0661 | 5 → 4 |

**Mean +0.0824 °C, spread 0.0454, sign holds 3/3.** Real-baseline skill falls from +0.156 mean to
+0.078. The delta bundles two things and is **not** attributable to the leak alone: the selection
protocol changed AND the training block lost 46 of 299 days to make room for the validation set.

**Why it costs that much — measured, not argued.** It is not noise. The pre-registered stability
criterion (mean |Δ val NLL| ÷ mean |Δ train NLL|, computed from the training curve alone so the
choice never touches the test score) rates the carved block the *least* noisy signal of the four:
4.26 against the test block's 4.66 / 7.83 / 6.69. The mechanism is seasonal mismatch. On the
Feb–Mar val block the NLL is lowest at **epoch 1** and rises after; on the Apr–Jun test block it
keeps falling to epoch 4. Same architecture, same data, near-identical train curves, opposite
verdicts on which epoch is best. Two of three seeds therefore early-stopped at epoch 6 holding a
barely-trained model.

**Open, and deliberately not decided here.** The 90-day trailing block and the 3-block seasonal
layout were queued but had not finished when this was committed. No new checkpoint is promoted:
**the shipped deliverable (`sat_7ch_s42`, RMSE 0.9006) was selected under `test_period_v0`**, and
that stands as a stated property of it until a leak-free run is promoted. The manifest and the
promoted metrics are untouched by this commit.

**Also fixed here.** `freeze.py` hardcoded `"protocol": "embargoed_v2", "n_targets_embargoed": 5`
into its manifest, so it would have kept asserting the old protocol after the run's own JSON
changed. It now reads both from the run.

**Held back from this commit.** `train/train_stage2.py` had the identical wiring and is fixed the
same way **in the working tree**, where it passes the same structural check — but that file carries
another session's uncommitted `--w-stab` work, so it cannot be committed here. The committed guard
covers stage 1 only and its docstring says why and what to add.

**Tests.** `tests/phase2/test_selection_split.py`, 21 of them: the two embargoes asserted on real
geometry, chronological ordering, the refusals, a real-data pin on the shipped bundle, the
multi-block both-sides purge, a regression pin that `n_blocks=1` reproduces the trailing block, and
a structural guard that reads the training script and rejects any wiring where the test block is
built before the epoch is chosen. Two of them are **controls** that fail on the pre-fix arrangement,
so the checks are not vacuous.
