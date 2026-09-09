

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

## 2026-09-06 — Unit A — three novelty features on the frozen model

Full write-up in `docs/phase2/f_novelty.md`; cross-machine notes in `docs/phase2/AGENT_SYNC.md` A30.

New: `src/phase2/physics/stability.py`, `src/phase2/reliability/{harness,observability,
assimilation}.py`, three scripts under `scripts/phase2/`, three panels under `app/ui/features/`,
four test files (**59 tests**, all offline). `train_stage2.py` gained `--w-stab` (default 0.0, so
every existing stage-2 objective is byte-identical) with the same overwrite guard `--w-grad` has.

**The shared loader caught a silent architecture bug before any experiment ran.** `built_t_seq` (the
value CNN3D's temporal pooling is built from) is not `T_SEQ` (the input window). The shipped
checkpoint is `T_SEQ=11, built_t_seq=1`, and both constructions load the same state_dict without
complaint because AdaptiveAvgPool3d equalises every parameter shape. Building at t_seq=11 scored
0.9297 against a recorded 0.9078 with no error raised. Fixed by reading `built_t_seq` and calling
the repo's own `assert_architecture_matches`.

Measured, all with the control reproducing the checkpoint's recorded RMSE exactly:

* **Stability.** 805 of 13,468 adjacent pairs (5.98%) in 597 of 962 Argo columns are statically
  unstable; 12,153 of 165,648 (7.34%) in 8,298 of 11,832 cells across the basin. After projection:
  **0**, re-verified from the projected temperature. Cost **+0.0002 degC** RMSE, 2.2 ms/profile.
  Stage 2 only — density needs salinity, and `project_profile` raises on stage 1 rather than
  enforcing a monotone temperature that would delete BoB barrier-layer inversions.
  **Soft vs hard, now trained and measured:** a `--w-stab 1000.0` model cuts violations ~400-fold
  (805 -> 2) and still does **not** reach zero, at a cost of **+0.0220 degC** RMSE and a doubled
  warm bias (+0.0831 -> +0.1782). The projection reaches zero for **+0.0002 degC** — about 100x
  cheaper in accuracy — and works on a model never trained for it.
* **Observability.** The Jacobian shows the model reading **SST for the mixed layer and SSH for the
  thermocline** (48% of the response at 100-125 m), untaught. Relative leverage falls 3.3x from
  125 m to 1000 m. The hypothesis that our errors sit below the information floor is **REFUTED** —
  depth-controlled ratios 0.38 / 0.78 / 0.65 / 0.74 at 300/500/700/1000 m. Low sensitivity marks
  quiescent water that is easy to predict.
* **Latent assimilation.** At lambda=0.03, MAE 0.5441 -> 0.5291 at latent-similar cells
  (**+0.0150 degC**) while random recipients get 0.0241 worse and the least-similar decile 0.0745
  worse. Still +0.0065 degC at recipients >= 500 km away, so the correction follows the water mass
  — though most of the benefit is local (+0.0422 under 200 km).

**For Unit C:** `docs/EXPERIMENT_LOG.md` is yours and I have not written to it. Three runs want
logging: stability projection, observability, and the assimilation lambda sweep. Each artifact
carries its seed, config and control.

**For Unit B:** nothing you own was edited. `app/streamlit_app.py`, `app/panels/`, `config.py`,
`data/`, `features/` and `inference/predict.py` are untouched.

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

---
---

## 2026-09-07 — Decision: ship 0.9006 and state the selection leak

**The decision.** The deliverable stays `sat_7ch_s42` at RMSE 0.9006. Its epoch was chosen on the
2026-04-01..06-23 test block — the days its Argo headline is scored on — and that is now stated on
every surface that quotes the number rather than left to a reader who knows when the bug was fixed.
The alternative was shipping a leak-free run at roughly 0.98; that was considered and declined.

**What was measured before deciding.** Four selection layouts, seed 42, everything else matched to
the deliverable. RMSE is reported only — the layouts were judged on the validation curve, never on
this column, because picking a validation protocol by test score is the original bug in a new hat:

| layout | train days | val months | epoch chosen | RMSE |
|---|---|---|---|---|
| the test block itself (as shipped) | 299 | the scored months | 4 | **0.9006** |
| 1 trailing block, 46 days | 253 | Feb, Mar | 1 | 1.0121 |
| 1 trailing block, 90 days | 209 | Jan–Mar | 1 | 0.9903 |
| 3 blocks across the year, 45 days | 239 | Mar, Jun, Oct, Nov | 4 | 1.1037 |

plus three seeds of the 46-day layout: 1.0121 / 0.9685 / 0.9684 against 0.9006 / 0.8989 / 0.9023.
**Mean +0.0824 °C, spread 0.0454, sign holds 3/3.** Real-baseline skill falls +0.156 → +0.078.

**Two findings worth keeping.** A contiguous trailing block removes a whole season from training
and then ranks epochs on the one season the model has never seen, where the least-specialised model
wins — both trailing layouts picked **epoch 1** and early-stopped holding a barely-trained model.
Spreading the blocks across the year fixed precisely that (epoch 4, matching the leaked signal, on
a clean monotone curve) **and scored worst of the four**, with a negative real-baseline skill. So
the pre-registered stability criterion did not predict the outcome and is recorded as **NOT
VALIDATED**. It was chosen in advance so it could fail visibly, and it did.

**The confound, unresolved.** The +0.0824 is not the price of the leak alone: the leak-free arm
also trains on 253 days instead of 299. Separating them needs an arm that keeps the reduced
training set and still selects on test — deliberately reintroducing the bug behind a flag — and it
was not run.

**Where it is now written down.**

* `artifacts/frozen_manifest.json`: every claim carries `selection_protocol`, and the deliverable
  carries a `selection_leak` block with what it is, the measured cost, the confound, why it ships
  and the commit that fixed the code (`cc8d672`). `freeze_headline.py` defaults a missing value to
  `test_period_v0` the same way it defaults a missing `scoring_protocol` to `unmasked_v1`.
* `PROJECT_RECORD.md`: flaw **3a** in §16.1, and a new **§16.6** with the three-seed table, the
  four-layout sweep, the confound and the decision.
* `note_19_conclusion.py` → the rebuilt conclusion PDF: flaw 3a, and the strengths list now says
  the project found and priced a selection leak in its own code.
* `PHASE2_STATUS.md` row 16, ahead of the headline.
* The deck's slide-7 speaker notes, phrased to be volunteered if the question is about validation.
* Three guard tests in `test_presentation_claims.py`: the manifest must carry the protocol and,
  when it is `test_period_v0`, a complete `selection_leak` block; the jury notes must mention it;
  `PROJECT_RECORD` must list it and carry the measured cost. Two were red before this change.

**Also here.** The run banner printed `carved from the END of train (2025-06-01..2026-03-26)` for a
three-block layout, which reads as one contiguous tail across the whole training period. The dates
were right, the wording was not; it now names the layout and lists each block.

**Audit finding #7 is closed in the code and open in the artifact**: no run can select on the
scored period any more, and the shipped checkpoint predates that and says so.

---

## 2026-09-07 — JURY_NOTES/00_Demo_Walkthrough.pdf: the 10-minute walkthrough

A four-page note for whoever runs the demo: the one command, what the three rows of buttons mean,
eight features in the order to show them (SEE IT → PROVE IT → STRESS IT), the novelty on one page,
and how to finish. Each feature is four fixed lines — Click / Shows / Say / Careful — so the eye
learns the shape. Every number is copied from an artifact and every click path is the real rail in
`app/ui/main.py`. Built by `JURY_NOTES/_build/note_00_demo.py`, wired into `build_all.py` (20 PDFs
now). QA was done by rasterising all four pages with pymupdf and looking at them, which caught a
footer printing `&middot;` literally and an orphaned closing block; both fixed. Rebuilding
regenerates all nineteen other PDFs byte-differently even where the text is unchanged — that is the
pipeline, not a content change.

---

## 2026-09-07 — Audit #8: Argo pressure was being read as depth; the truth table is regenerated

**The bug.** `oceanembed.data.download_argo._profiles_to_rows` interpolated each float's
temperature onto `config.DEPTHS` with `np.interp(config.DEPTHS, p, t)` where `p` was PRES in
**decibars** and `config.DEPTHS` is **metres**. Reading pressure as depth samples every float about
1% too shallow — at 15 N: 0.6 m at 100 m, 1.3 m at 200 m, 3.5 m at 500 m, 8.2 m at 1000 m. In a
thermocline with dT/dz ≈ 0.1 °C/m that is a tenth of a degree charged to the model. Every Argo
table this project scored against was built that way: `argo_test.parquet` (2022, Phase 1),
`argo_daily_period.parquet` (2025-26, every v2 number) and its salinity twin. **[VERIFIED]** by
reading the code, by a synthetic-thermocline test, and by the measured delta below.

**The fix.** `src/phase2/data/argo_depth.py` — `depth_from_pressure(p_dbar, lat)`, the UNESCO 1983
formula (Fofonoff & Millard, Tech. Paper 44, eq. 25), pinned to the paper's check value
(10000 dbar at 30 N → 9712.653 m). `download_argo._profiles_to_rows` converts before both
interpolations. **This is a cross-unit edit** — `download_argo.py` is Unit B's file; the change is
five lines and is the smallest that fixes the axis. Phase 1's `argo_test.parquet` was NOT
regenerated (it underwrites the published Phase-1 numbers and the fetch script guards it).

**Regeneration, and what it changed.** Both daily-period tables were re-fetched through the
project's own scripts (`fetch_argo_daily_period.py`, `fetch_argo_ts_daily_period.py`). The
pre-fix tables are kept as `*_pres_as_depth_v1.parquet`. `scripts/phase2/argo_axis_fix_delta.py`
separates the axis fix from upstream drift: on the 4,330 profiles both tables share, the 0/5/10 m
levels — where the axis error is ≤ 0.06 m — agree to **0.005 °C RMS**, so the re-fetch itself
changed nothing and every deeper difference is the axis alone. The truth moved **colder** below
the mixed layer, peaking at 100–150 m (mean −0.054 to −0.064 °C; 13–18% of comparisons moved by
more than 0.1 °C), and **89 comparisons at 1000 m existed only because a float reaching 1000 dbar
had been read as reaching 1000 m**. Artifact: `artifacts/argo_axis_fix_delta.json`.

**Protocol.** `seafloor_masked_v2` = the v1 mask against the depth-axis table. Names now live in
`src/phase2/tscast_nio/protocols.py` (torch-free; `eval_argo` re-exports them) with
`PROTOCOL_HISTORY`, and every new score records `argo_table` — file, sha256, rows, profiles,
`truth_axis` — via `protocols.argo_table_provenance`. The v1 re-scores stay on disk under their
own names. `freeze_headline.py` reads the names from `protocols` instead of retyping them.

**The deliverable, re-scored under v2** (`sat_7ch_s42`, same bytes, sha 53848bb5…):

| | seafloor_masked_v1 | **seafloor_masked_v2** |
|---|---|---|
| RMSE | 0.9006 | **0.9063** |
| bias | +0.1066 | **+0.1400** |
| correlation | 0.8809 | 0.8804 |
| skill / real-baseline skill | +0.2400 / +0.1494 | **+0.2379 / +0.1480** |
| n / profiles / refused | 12,736 / 962 / 93 | 12,727 / 963 / 92 |
| depths beating climatology | 14 of 15 | 14 of 15 (1000 m by 0.024, was 0.055) |
| ±2σ coverage range | 80.1–96.0% | 79.7–96.2% |

Per depth the RMSE rises 0.005–0.023 °C from 20 to 125 m and falls 0.007–0.018 °C below 300 m.
**A third of the model's warm bias had been hidden by the truth being read too shallow.** The
strict-window figure (909 profiles inside 2026-04-01..06-23, masked) is 0.9037 on n 12,011.

**Comparators and the two three-seed sentences, all re-scored under v2.** Satellite minus
reanalysis-fed (abl_full − canon_7ch): +0.0237 / +0.0231 / −0.0040, mean +0.0143, sign does not
hold, ~95% of the comparator's skill retained (three-seed mean skill 0.240 vs 0.252). The
selection-leak cost (sel_7ch − abl_full): +0.0907 / +0.0736 / +0.0531, mean **+0.0725**, spread
0.0376, sign holds 3/3 (was +0.0824 on the old table). Four-layout sweep: 0.9063 / 0.9970 /
0.9994 / 1.0869. Embargoed GLORYS comparator (withUV) 0.8652; stage-1 GLORYS canon 0.8826.

**Promoted and re-frozen.** `promote_run.py --tag sat_7ch_s42 --rescore seafloor_masked_v2`;
`calibrate_uncertainty.py` re-run (old artifact kept as `uncertainty_calibration_seafloor_masked_v1.json`);
`frozen_manifest.json` re-frozen with `argo_table` on every claim and `protocol_history`.

**Every surface moved to 0.9063**: the deck (slides 7, 8, 12 and the slide-7 notes), the 20 jury
PDFs (notes 00, 01, 02, 08, 14, 19 via their sources), `PHASE2_STATUS.md` (header table, framing,
a TRUTH-TABLE CHANGE paragraph, row 16), `PROJECT_RECORD.md` (§1.2, §7, §8 banner, §8.1, §8.x
1000 m, §12 acoustics, §13 PS audit rows, §16.1 flaws 4 and 6, §16.6 all tables, the closing
quote), the app (`words.py`, `buoy.py`, `acoustics_page.T_RMSE_DELIVERABLE`, `clickmap_page`,
`tscast_page`), and the manifest's `selection_leak` block. `test_presentation_claims` now treats
0.9006 / +0.2400 / 12,736 as superseded unless labelled, the same way it treats 0.9078.

**Tests.** `tests/phase2/test_argo_depth.py` (9): the UNESCO check value, monotonicity, the error
table on the shipped grid, a synthetic thermocline showing the misread is 0.06 °C at 100 m, the
real `_profiles_to_rows` sampling at the depth it labels, a float stopping at 1002 dbar no longer
getting a 1000 m value, salinity on the same axis, and a control proving the pre-fix path differs.
The seafloor real-data pin is re-measured (963 / 92 / 12,727 / 896).

**Not touched, and why.** Phase 1's `argo_test.parquet` and every Phase-1 number rest on the
pressure-as-depth axis — a stated limitation, not regenerated here. The stage-2 comparators are
carried forward under `unmasked_v1` and labelled. The other session's novelty artifacts
(`stability_projection`, `observability`, `latent_assimilation`) were computed against the v1
table; their `control_rmse` will now report no same-protocol record until re-run — that is the
harness doing its job, and it is theirs to re-run. The cloud-dropout sweep is quoted as
unmasked_v1 and labelled.


---

## 2026-09-07 — SIH idea-submission deck built (Arjhun)

**What.** `OceanEmbed_SIH26066_IDEA.pptx` — the five official SIH idea-format slides (Proposed
Solution / Technical Approach / Feasibility and Viability / Impact and Benefits / Research and
References), in the structure and visual language of a winning SIH deck the user supplied as
reference screenshots. **`OceanEmbed_SIH26066.pptx` is untouched** — the two decks serve different
stages: submission format vs. live pitch.

| file | what |
|---|---|
| `scripts/deck/build_idea_slides.py` | the deck. No arguments, idempotent, ~20 s (it collects the test suite) |
| `scripts/deck/diagrams.py` | five matplotlib PNGs -> `artifacts/deck/` |
| `tests/phase2/test_idea_deck_claims.py` | 6 tests, additive; `test_presentation_claims.py` untouched |
| `docs/superpowers/specs/2026-09-07-sih-idea-deck-design.md` | design + number ledger |

**No number is typed into the deck.** Every figure is derived at build time from
`artifacts/frozen_manifest.json` and the metrics artifact it names — RMSE, skill, bias,
correlation, n, profiles, depths, T_SEQ, channels, the selection-leak cost, the depth-win count,
the thermocline peak, the parameter count (encoder+decoder), training minutes and device. The test
count is read by actually collecting the suite. `_guard()` refuses to save a deck that quotes a
retracted leg (0.9267 / 0.8529 / 0.9096) or the GLORYS comparator (0.8873 / 0.8548), that omits the
frozen headline, or that claims climatology is beaten at every depth.

**This was load-bearing within the hour.** The build was first run against the `seafloor_masked_v1`
manifest and picked up `seafloor_masked_v2` on the next run without an edit: 0.9006 -> **0.9063**,
962 -> **963** profiles, 12,736 -> **12,727**, bias +0.11 -> **+0.14**. Re-derived rather than
assumed: climatology is still beaten at **14 of 15** depths (it wins only at 1000 m), and the
thermocline band re-reads **1.06–1.24 °C through 50–150 m, peaking at 100 m** — the old deck's
"1.1–1.2 °C" understated the peak. Two claims inherited from the 12-slide deck were stale and are
now derived: "530 tests" (the suite collects **1,032**) and "549k parameters" (507,848 + 40,734 =
548,582, so 549k holds).

**Verification.** `test_idea_deck_claims` 6 passed; `test_presentation_claims` 14 passed against
the same tree. Geometry and text-overflow checked programmatically (no Office renderer here): all
5 slides inside the border, every text box <= 89% estimated fill, no image outside the frame. The
five PNGs were inspected as images.

**Two placeholders, deliberately not filled.** (1) The **SIH logo** — a copyrighted mark, no
licensed asset in the repo, and I will not redraw a lookalike; every slide carries a dashed grey
box. Note the reference deck says 2025 and SIH26066 is the 2026 cycle. (2) The **team name** —
nothing in this repo records one; `TEAM_NAME` at the top of the build script.

**Not verified, flagged to the user.** Two sentences on the Impact slide are general-knowledge
context rather than repo measurements: "the most densely populated cyclone basin" and "ocean holds
the dominant share of excess planetary heat". Both need a citation attached if the jury is strict.

**Nothing owned by another unit was edited.** No app file, no existing deck, no existing test, and
`docs/EXPERIMENT_LOG.md` untouched. This HANDOFF entry is appended without committing the file,
because it also carries another session's pending 46-line block.


---

## 2026-09-07 — the idea deck now fills the OFFICIAL SIH template (Arjhun)

Supersedes the entry above. That build generated its own chrome with a placeholder where the SIH
logo goes. The user then supplied the real portal template, so the deck is now built by **opening
`SIH2026-IDEA-Presentation-Format.pptx` and filling it**. The template is copied unmodified into
`scripts/deck/template/` so the build is reproducible.

**Its chrome is the portal's and is untouched** — SIH logo, the "SMART INDIA HACKATHON 2026" title
page, footer bar, slide numbers, team oval, Title placeholders. Verified shape-by-shape against the
original: all six slides keep all six template shapes, nothing missing.

**Six slides, not seven.** The template's own instruction slide states a maximum of six including
the title page, and says to delete itself before uploading. Both done. Its prompt text
("Detailed explanation of the proposed solution", …) sat in a `TextBox 8` per slide; those are
deleted and replaced with our content, which is what the reference winning deck does.

**Title page** carries PS ID `SIH26066`, theme **Disaster Management**, category **Software**,
organisation **MoES (INCOIS)** — `[VERIFIED]` from the PS transcription confirmed at
`docs/ARJHUN_EXECUTION_PLAN.md:30`. `README.md:6` says "Software / Space Technology"; that is an
older informal note and was NOT used. **Three fields carry a visible `‹fill from portal›` marker**
because this repo records them nowhere: the verbatim PS title, the team ID and the team name (the
last also on the oval of all five content slides).

**Numbers still come from the freeze, not from prose.** Same derivation as before. Two live proofs
this session: the manifest moved v1→v2 mid-build and the deck followed with no edit, and the test
count re-read **1,032 → 1,040** between two builds as the other session added tests.

**Geometry re-fitted** to the template's tighter band (y 1.26–6.88, logo keep-out above y 1.16 for
x > 10.70). `flow.png` re-rendered 1.02 -> 0.75 in tall and `facts.png` 2.45 -> 2.10 to clear the
footer bar. QA: no shape collides with the logo, footer or title band; every text box <= 87% of its
estimated fill.

**Tests.** `test_idea_deck_claims.py` now 8 (six-slide maximum, prompt-text removal, template
chrome survival, plus the five claim guards). 7 passed, **1 skipped**: the chrome test needs
python-pptx, which the venv does not have — it was therefore verified by hand and reported as such,
not assumed. `test_presentation_claims.py` untouched, still 14.

**For Unit B:** `requirements.txt` does not list `python-pptx`, which `scripts/deck/` now needs.
The system Python has it; the venv does not, which is why one test skips and why the deck cannot
be built with the venv interpreter. Adding it is yours to make — I did not edit the file.

**Upload is a PDF, not a PPTX** (the template requires it). No Office renderer on this machine, so
that export is a manual step in PowerPoint.

---

## 2026-09-07 — Audit #13: the encoder can now tell a data gap from average water

**The bug.** `GriddedPatches.__getitem__` zero-fills NaN after z-scoring, so a missing value and
an observation at the channel mean are both 0.0 to the network. It computed a `finite` mask, used
it only for the fill, and discarded it — while the module docstring said the mask was recorded so
the model could learn to distrust those cells. **[VERIFIED]** by reading the code.

**How much of it there is.** Measured on the shipped satellite bundle: **5.5% of ocean cells are
missing at least one channel on every day** — SST 285 cells, SSS 534, SSH 245, currents ~625
(the currents also vary by ~60–140 cells day to day; the rest is a fixed product coastline). 798
of those cells have GLORYS water, i.e. the product serves a prediction there. Independently, an
ocean-centred 17×17 patch is **15% land on average**, more than half land for 6% of cells. All of
it reached the encoder as the channel mean. Pinned in `tests/phase2/test_mask_channels.py`.

**The fix.** `GriddedPatches(mask_channels=True)` appends a per-channel presence mask to `x` —
C extra channels, 1 where observed, 0 where filled — so channel c's mask is channel C + c and the
value block is unchanged. **Off by default; the shipped checkpoint's path is byte-identical** (a
test asserts it). `dataset.input_channels(channels, mask_channels)` is the one place the input
width is computed. A checkpoint records `mask_channels`; `assert_architecture_matches` refuses a
model built for the wrong width and names the cause before load; `train_stage1 --mask-channels`,
`rescore_checkpoint`, `harness.load` and `inference.TSCastPredictor` all read the flag from the
checkpoint rather than assuming `len(channels)`. `train_stage2.py` is not wired (it does not need
to be for the default, and it carries another session's uncommitted work).

**Does it help? Three seeds, one difference.** Control `sel_7ch_s{42,43,44}` (leak-free
selection, no mask, re-scored under `seafloor_masked_v2`) against `mask_7ch_s{42,43,44}`
(identical plus the mask, scored natively under v2). Same 963 profiles, same n 12,727:

| seed | no mask | epoch | mask | epoch | delta |
|---|---|---|---|---|---|
| 42 | 0.9970 | 1 | 0.9779 | 5 | −0.0190 |
| 43 | 0.9757 | 1 | 0.9686 | 2 | −0.0072 |
| 44 | 0.9567 | 4 | 0.9470 | 3 | −0.0096 |

**Mean −0.0119 °C, spread 0.0119, sign holds 3/3** — an established effect by the three-seed
rule, and a small one: about a seventh of the selection-leak cost. Real-baseline skill moves
+0.077/+0.089/+0.102 → +0.075/+0.092/+0.112, so the gain is not from the 67 shelf profiles. The
per-depth profile is NOT uniform (helps 0–30 m and 125–200 m, hurts 50–75 m and 500–700 m); three
seeds license the sign of the overall and nothing about that shape. The mask runs chose epochs
5/2/3 where the controls chose 1/1/4 — suggestive about the selection signal, not established.
Bias moved erratically across seeds and is not a mask effect either way.

**Decision (2026-09-07): committed as is, the shipped checkpoint unchanged.** A mask-aware,
leak-free model (mean 0.9645) is the honest configuration; it is also a new checkpoint with a
new sha, and promoting it would reopen the decision to ship the test-selected 0.9063. The six
run artifacts (`tscast_stage1_mask_7ch_s4{2,3,4}.pt` + metrics) are on disk, not promoted.

**Tests.** 8 in `test_mask_channels.py`: the default path byte-identical; a gap and an observation
at the mean both z-score to 0.0 and only the mask separates them; land and off-grid marked
absent; appended not interleaved; the helper; the guard in both directions; a legacy checkpoint
without the field still loads; and the real-data pin of the 5.5% and the 798.

---

## 2026-09-07 — Audit #19: the shipped metrics file said the wrong era; and the test count is now measured

**#19.** `train_stage1` wrote `train_years: list(base.TRAIN_YEARS)` and `test_years:
list(base.TEST_YEARS)` on every run — the Phase-1 MONTHLY constants, `[2019, 2020, 2021]` and
`[2022]`. So `artifacts/tscast_stage1_metrics.json` claimed the shipped model trained on 2019-21
and was tested on 2022, three lines above a `train_period` of `2025-06-01..2026-03-26` saying
otherwise. Nothing reads the fields back (checked across `src/`, `scripts/`, `app/`, `tests/`), so
no published number moved: the artifact was lying about itself, which is the defect class an
unnamed scoring protocol belonged to.

`dataset.years_in(times, indices)` derives the calendar years a split actually covers.
`train_stage1` and `rescore_checkpoint` both use it and both write a `years_note` saying the
constants do not describe a daily run. The deliverable was re-scored and re-promoted: it now reads
`train_years [2025, 2026]`, `test_years [2026]`. All twelve current-protocol re-scores were re-run
and all twelve still agree with their records to 4 dp, so only the metadata moved.

**The 46 historical training JSONs are deliberately NOT rewritten.** They record what the code
wrote when they ran; correcting them in place would falsify the record of an experiment, the same
reason `unmasked_v1` and `seafloor_masked_v1` scores are kept under their own names. The guard is
scoped by `years_note` — the mark the fixed writer leaves — and anchored by a separate test that
what actually SHIPS carries the note and the right years, so the scoping cannot hide a regression.

**The test count.** The conclusion note said "925 passing, 9 skipped" in two places; the suite
reported 1055 passed / 10 skipped on the merged branch and collects 1070 with the tests added here.
Retyping it would only restart the drift, so `test_the_conclusion_note_states_the_real_test_count`
asserts `passing + skipped == len(request.session.items)` on any full-suite run and skips on a
targeted one, where the collected count says nothing. The note now reads **1060 passing, 10
skipped**, and the PDFs are rebuilt.

**Tests.** `tests/phase2/test_artifact_self_description.py`, 6: `years_in` on a synthetic axis and
on the shipped bundle; no fixed-writer record contradicts its own split; the promoted deliverable
carries the note, the years and the period; and the count guard with its full-run gate.

---

## 2026-09-07 — the count guard caught its own parser

The guard added in 24f4532 failed on its first full run, and correctly: `_claimed_counts` stripped
EVERY comma from the note to handle a thousands separator like "1,060", which also removed the one
in "passing, 10 skipped" that its own pattern depended on. It matched nothing, and `assert pairs`
turned that into a failure instead of a vacuous pass -- which is the only reason it was visible.

Fixed to strip commas only between digits, and a control test now asserts the parser actually
finds the note's numbers, so a pattern that matches nothing can never again read as agreement.

The note reads **1061 passing, 10 skipped** against 1071 collected. Note the self-reference:
adding the control test changed the number the guard checks, so the count was re-measured after
the test file was final, not before.

---

## 2026-09-07 — Audit #22 and #26, committed WITHOUT tests

Both fixes work and were verified by hand; neither has a test, because work stopped mid-task. That
is stated here rather than left for someone to discover.

**#22 — two domain gates disagreed.** `data/collocation.py` tested the range of cell CENTRES
(5.00..29.75 N) while `tscast_nio.inference.assert_point_in_domain` tested the advertised box
(`config.REGION`, 5.0..30.0). So 29.9 N was inside the domain for the predictor and
`OUTSIDE_DOMAIN` for the collocation engine, and the UI showed both. New light module
`src/phase2/domain.py` (numpy + config only, no torch, so every consumer can import it) holds the
one definition; both call sites read it. REGION wins because it is what the problem statement asks
for, what the sliders offer and what every download used. The 0.125 deg strip between the last
centre and the box edge is a DISTANCE question, not a membership one, and collocation already
flags it as `SPATIAL_OFFSET_EXCEEDS_CELL`. Verified by hand: (29.9, 75), (29.75, 75), (30.0, 75),
(30.01, 75), (5.0, 45), (4.9, 45), (15, 104.9) — all seven now agree between the two gates.

**#26 — a clamped channel passed the physical gate silently.** `_check_range` accepted any field
whose extremes sat inside `RANGES`. The satellite SSS product pins at exactly 40.0000 psu, which
is inside the 25..42 gate and was never mentioned. `clamped_at()` now reports any value sitting on
a channel's exact extreme more than `CLAMP_REPEAT_LIMIT` (5) times, the build logs it per day, and
a per-channel summary travels in the bundle's `provenance` under `clamped_values`. The threshold is
calibrated on the shipped bundle: sst, ssh, u and v each touch their own extreme EXACTLY ONCE in
~4.4 million samples, which is what a continuous field does; SSS touches 40.0000 fifty-three times
across 12 ocean cells on 24 of 388 days. A clamp is a measurement the instrument could not make,
wearing a plausible number.

**Correction.** An earlier count of "426 samples at exactly 40.000" was wrong: `np.isclose`'s
default `rtol` made that a plus-or-minus 0.0004 window. The true figure is **53**. The finding
stands; the number was inflated 8x.

**What is missing.** No test covers either fix. For #22 the test to write is the seven-point
agreement table above; for #26, that `clamped_at` fires on a synthetic pinned field and stays
silent on a continuous one, plus a real-data pin of the 53. The bundle has NOT been rebuilt, so
`clamped_values` will only appear in a bundle built after this commit.

---

## 2026-09-07 — The marine-heatwave detector moves into the instrument (port 8500)

Darshan's detector shipped as its own Streamlit page on 8518. Sixteen features on sixteen ports
reads as sixteen prototypes, so it now lives on the rail as **Hidden heatwaves** (PROVE IT), in the
house shape: `app/ui/features/heatwave.py`, registered in `words.FEATURES` with three explainers.
His engine and baseline builders are imported unchanged; nothing under `phase2/` was touched.

**What it adds over the standalone page.** The shared basin map, so land and sea floor are their
own layers rather than whatever colour the value scale gives null. Click a cell and get the ACTUAL
events under that column — start, end, duration, peak intensity, Hobday category — instead of only
a fraction of days; an event list is checkable against the ocean, a fraction is not. And the
surface-versus-depth comparison, measured rather than asserted.

**The measurement corrected the claim, which is the point.** "A heatwave at depth can be invisible
from orbit" is prose in the notes, the deck and the page. Measured at 100 m over 388 days:

| | |
|---|---|
| surface flagged, ever | 11,831 of 11,832 ocean cells |
| 100 m flagged, ever | 9,745 |
| most of their event days unseen from the surface | 8,667 (89%), median share 0.73 |
| the REVERSE — surface flagged, 100 m not | 11,783 cells |

So it is not one-way invisibility, it is **decoupling in both directions**: an SST observation is
not an incomplete view of the subsurface, it is a different signal. The first metric tried, "at
least one hidden day", read 100% and is vacuous — over 388 days almost every cell clears it. It was
replaced, and the reverse-direction tile is on screen so the panel cannot be read as one-way.

The 11,831 figure is also the clearest statement of the pilot baseline's bias yet: against 2019–22,
nearly the entire basin reads above its own 90th percentile somewhere in 2025–26. That is the
warming trend. It is now a stated limit with the number in it.

**Two defects found and fixed while verifying.** The STRONGEST tile paired one event's intensity
with `summarise()`'s max category, which is the maximum over ALL events and can belong to a
different one. And the category surprise: a **+3.82 °C** peak at 18°N 88°E is *Moderate* while
**+2.59 °C** at 15°N 68°E is *Extreme*, because category counts multiples of the LOCAL
(threshold − mean) gap — 1.3x against a 2.86 °C gap versus 7.7x against 0.34 °C. Correct Hobday
2018, reads as a sorting bug, so the caption now explains it with those measured numbers.

**A developer gotcha worth knowing.** Feature modules are imported lazily through `importlib`, so
Streamlit's file watcher never sees them: editing one and reloading shows STALE CODE WITH NO ERROR.
The rail updates (words.py is imported normally) while the stage does not. Restart the server.
Two false readings were taken before this was noticed.

**Also.** `run_mhw_comparison.py` hardcoded `tscast_stage1_7ch.pt`, which does not exist here, so
it could not run at all on this machine. It now takes `--checkpoint` and derives its cache and
output per leg, so the satellite and GLORYS runs cannot overwrite each other's numbers. The
satellite leg — the PS deliverable — is running; until it lands the agreement panel says so rather
than showing the comparator.

**Not done.** No test covers the feature module. `features/__init__.py` is staged as HEAD plus the
one `heatwave` line: the other session's four registrations there are uncommitted and point at
untracked modules.

---

## 2026-09-08 — The heatwave detector, run on the SATELLITE leg

`run_mhw_comparison.py --checkpoint artifacts/tscast_stage1.pt`, 388 days, GPU, ~55 min. The leg
Darshan could not run: he lacked the satellite bundle, so his artifact is the GLORYS comparator.
This one is the PS deliverable answering the question the PS asks. Result:
`artifacts/mhw_comparison_satellite.json` (tracked; the 206 MB field cache is not).

| depth | POD | FAR | CSI | freq bias |
|---|---|---|---|---|
| 0 m | 0.671 | 0.383 | 0.474 | 1.09 |
| 5–20 m | 0.693–0.715 | 0.355–0.392 | 0.490–0.502 | 1.08–1.18 |
| 30–50 m | 0.638–0.697 | 0.438–0.452 | 0.418–0.452 | 1.16–1.24 |
| 75–150 m | 0.608–0.625 | 0.252–0.331 | 0.477–**0.505** | 0.81–0.93 |
| 200–300 m | 0.617–0.628 | 0.323–0.391 | 0.442–0.483 | 0.93–1.01 |
| 500 m | 0.598 | 0.494 | 0.377 | 1.18 |
| 700–1000 m | 0.455–0.476 | 0.451–0.488 | 0.328–0.331 | 0.83–0.93 |

**Two findings worth quoting, both measured here.**

1. **The model's worst temperature depth is its best detection depth.** RMSE peaks at 1.24 °C at
   100 m, and that is exactly where CSI is highest (0.503–0.505 at 100–150 m) with the LOWEST false
   alarm ratio of any level (0.25–0.27). Detection asks whether an anomaly crosses a threshold, not
   whether the absolute value is right, so a model that is off but CONSISTENTLY off still ranks
   days correctly. Easy to state backwards without the per-depth table in hand.

2. **The frequency bias reproduces the warm bias by an independent route.** The model over-flags in
   the mixed layer (1.09–1.24 at 0–50 m) and under-flags in the thermocline (0.81–0.86 at
   100–150 m). A model running warm near the surface crosses a 90th-percentile threshold too often
   there. The warm bias was measured this morning from Argo residuals (+0.1400 °C overall, peaking
   +0.676 at 50 m); this is the same defect seen through detection counts against GLORYS, with no
   Argo involved.

**The floor is stated, not hidden.** Below 700 m POD falls to 0.455–0.476 with FAR near 0.49, so
roughly half the deep detections are false alarms. That is the same depth range where skill over
climatology collapses and where climatology beats the model outright at 1000 m.

**Caveats unchanged.** Detection on both legs uses the 2019–2022 monthly pilot baseline, so
absolute counts are inflated; the contingency table is immune because model and truth share one
threshold. The truth is GLORYS, which carries its own error.
