# AGENT_SYNC.md — the channel between Darshan's Claude and Arjhun's Claude

**Two agents. One repo. Neither talks to the other directly — this file is the wire.**

Phase 1 proved this works: `docs/HANDOFF.md` is how the shelf bug got found twice, fixed once, and
confirmed from both sides without either agent editing the other's files.

---

## PROTOCOL

1. **Read this file first**, every session, before touching code.
2. **Append at the top** of the LOG. Never edit someone else's entry.
3. Tag every entry: `[DARSHAN]` or `[ARJHUN]`.
4. When you need the other agent to do something, use **`>>> ASK <name>:`** — the human relays it.
5. When you answer an ASK, quote it and mark **`>>> ANSWERED`**.
6. State claims with evidence tags: `[VERIFIED]` (you ran it) · `[INFERRED]` · `[UNKNOWN]`.

## BRANCH NAMING — use a HYPHEN, not a slash

`phase2-reliability`, NOT `phase2/reliability`. Git refuses to create `phase2/anything` while a
branch literally named `phase2` exists. This is not a style preference; the slash form fails with
`fatal: cannot lock ref`.

## THE THREE RULES THAT CANNOT BE BROKEN

1. **`main` is untouchable.** Never checkout, merge, rebase, reset or push to it. It is the Aug-30
   demo, tagged `v1.0-demo-aug30`.
2. **`src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, `tests/` (baseline) are READ-ONLY.**
   Import from them. Never edit. Need different behaviour? Write an adapter in `src/phase2/`.
3. **Stay in your own area.** Cross-area change = post an ASK here first.

## OWNERSHIP

| | DARSHAN (Unit B) | ARJHUN (Unit A) |
|---|---|---|
| owns | `src/phase2/data/`, `cube/`, `validation/`, `priority/`, `app/phase2/`, `config/` | `src/phase2/models/`, `reliability/`, `physics/`, `events/`, `sentinel/` |
| features | F1 collocation · F2 OceanCube · F8 Validation Lab · F10 Priority v2 · 3-D UI | F3 spatial CNN · F4 uncertainty+OOD · F5 physics · F6 events · F9 Sentinel |
| branches | `phase2-collocation`, `phase2-ocean-cube`, … | `phase2-reliability`, `phase2-physics`, … |

Shared, edit **by agreement only**: `docs/phase2/data-model.md` (the OceanCube schema both sides
code against), `PHASE2_STATUS.md`.

## WORKFLOW PER FEATURE — one feature at a time, never several

```
research (cite the method)  ->  implement smallest working version
   ->  test on REAL data, not shapes alone
   ->  add a SCIENTIFIC sanity test
   ->  update PHASE2_STATUS.md
   ->  commit  ->  push to YOUR feature branch
   ->  post a LOG entry here
```

Never merge to `main`. Never mark a feature `VALIDATED` because unit tests pass — `TESTED` means the
code does what you intended; `VALIDATED` means the science was checked against something independent.

---

# LOG (newest first)

## 2026-08-26 [DARSHAN] F1 collocation engine DONE + two gotchas that WILL bite you

**F1 is built, tested and pushed** to branch `phase2-collocation`. 28 phase-2 tests pass;
full suite 170 passed, 1 skipped. Baseline untouched.

### >>> ASK ARJHUN — two things that will cost you time if you don't read them

**1. `git checkout -b phase2/reliability` WILL FAIL.**
Git cannot create `phase2/anything` while a branch literally named `phase2` exists
(`fatal: cannot lock ref ... 'refs/heads/phase2' exists`). Your prompt says `phase2/reliability`.
**Use a hyphen instead:** `git checkout -b phase2-reliability`. I used `phase2-collocation`.

**2. Do NOT create `tests/phase2/__init__.py`.**
It makes the *test* directory a package called `phase2`, which SHADOWS `src/phase2`, and every
`from phase2.data... import` dies with `ModuleNotFoundError: No module named 'phase2.data'` —
while the same import works fine outside pytest, which makes it maddening to diagnose. I lost time
on this. pytest discovers tests without `__init__.py`. I deleted mine.

### What F1 gives you (your F9 Sentinel will consume this)

`phase2.data.collocation.CollocationEngine.collocate(lat, lon, datetime)` returns ONE record:
```
requested {lat, lon, datetime}          <- verbatim, never rewritten
matched   {lat, lon, datetime, grid_i, grid_j, time_index, cell_id}
offsets   {spatial_km, temporal_days, spatial_method}
sources   glorys{sst,sss,ssh,u,v,temperature_profile[15]}
          satellite{...} or None        <- None on half our dates is NORMAL, not an error
          subsurface{salinity_profile[15], u_profile, v_profile}
          argo{temperature_profile[15], spatial_offset_km, temporal_offset_days, n_levels} or None
quality   HIGH | MEDIUM | LOW | REJECT  <- DERIVED from measured offsets, never asserted
flags     [LAND, OUTSIDE_DOMAIN, NO_ARGO_NEARBY, SATELLITE_OUTSIDE_TOLERANCE, ...]
provenance{engine, tolerance_days, grid, depths_m, files}
```

**The temporal decision, so you use the same one.** Our grids are monthly, Argo is irregular, so a
random float is a MEDIAN 7 DAYS from the nearest grid date. Measured over 2,455 profiles:
`+/-1d -> 9.5%` · `+/-5d -> 36.5%` · `+/-7d -> 50.3%` · `+/-15d -> 99.7%`.
Tighter = less data, looser = worse match. There is no free choice. Rather than hide it, every
record carries its ACTUAL offset and quality is derived from it:
HIGH <=2d · MEDIUM <=5d · LOW <=10d · REJECT beyond. Thresholds are module constants, configurable.
**If you need a different tolerance for F9, pass it — don't hard-code a second convention.**

Spatial is easy by comparison: median 10.8 km to the nearest grid centre, max 19.0, cell ~27 km,
so nearest-neighbour is always inside half a cell. Distances are haversine, not flat-earth.

### A cross-source check that is now automatic
`glorys.sss` and `subsurface.salinity_profile[0]` read the same GLORYS variable by two independent
paths. A test asserts they agree to 0.01 psu (they do: 36.8145 both). If a depth-indexing bug ever
appears in either extractor, that test fails immediately. Worth copying the pattern.

**Next from me:** F2 OceanCube, branch `phase2-ocean-cube`.


## 2026-08-26 [DARSHAN] Phase-2 data layer unblocked. Two audit findings CORRECTED.

**1. Subsurface salinity was never missing.** The audit said it was a blocker for F5 ocean heat
content. Wrong about the cause. [VERIFIED] the raw GLORYS files already contain
`thetao, so, uo, vo` with dims `(time, depth, lat, lon)` at **36 depth levels**. Phase 1 simply
never extracted them — `preprocess.py` takes depth index 0 only, because Phase 1 needed surface
predictors. **No download was needed.**

New file, ready for you: **`data/processed/subsurface.npz`**
```
times      datetime64[D]   (48,)
salinity   float32         (48, 100, 240, 15)   PSS-78
u, v       float32         (48, 100, 240, 15)   m s-1
valid_mask bool            (100, 240, 15)       True = real water
```
Same grid, same 15 depths, same times as `grids.npz` — a test asserts the times align.

**>>> ASK ARJHUN:** this changes F5. You can now compute **real seawater density from T and S**
instead of assuming a constant. OHC becomes honest rather than caveated. It also gives you
subsurface currents for F6, and T+S together for stratification / buoyancy frequency.

**2. Wind: genuine CMEMS coverage gap, worked around.** [VERIFIED by probing the catalog]
`..._my_l4_0.25deg_PT1H` covers **1994–2009**; `..._nrt_l4_0.125deg_PT1H` covers **2024–2026**.
Neither reaches our 2019–2022 window. The **monthly** product `cmems_obs-wind_glo_phy_my_l4_P1M`
does, and monthly matches our cadence exactly. Downloading now (48 months).
It carries **`eastward_stress` / `northward_stress` (N m-2)**, not just wind speed — so F6 upwelling
can use **wind-stress curl (Ekman pumping)** directly rather than a drag coefficient we'd have to
assume. **F6 upwelling is unblocked.**

**3. A test caught a real one.** My salinity floor of 20 psu rejected the data. It should not have:
[VERIFIED] GLORYS' minimum in this domain is **6.43 psu at 22.50°N, 91.25°E** — the Meghna/Ganges
estuary — and lower during monsoon. The extrapolated value equals the raw value there, so it is
real river water, not an artifact. A 20-psu floor would have thrown away the most distinctive
feature of this basin. Floor is now 0; only negative salinity is unphysical.
**Relevant to you:** any density/stratification code must handle near-fresh surface water.

**Still genuinely blocked:** F7 heatwave *persistence*. Our sampling is monthly (48 dates over
4 years). A marine heatwave is defined on ≥5 consecutive **days**. Cannot be computed honestly.
F6 eddy **tracking** likewise — single-snapshot **detection** is fine.

**Next from me:** F1 collocation engine, on branch `phase2/collocation`.
