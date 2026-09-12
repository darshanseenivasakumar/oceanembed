# PROMPT FOR ARJHUN'S CLAUDE — merge Darshan's marine-heatwave feature into your UI

Paste this whole file as your first message. It is an INTEGRATION task, not a build — the feature is
already built, tested, and pushed. Your job is to merge it into your UI branch and wire it in.

## WHAT YOU ARE MERGING

Darshan built a **subsurface marine-heatwave (MHW) detector** and pushed it to
`origin/phase2-mhw-detector` (forked from `phase2-tscast-nio`). It is **purely additive** — 11 files,
1123 insertions, 0 deletions; the only existing file it touched is `.claude/launch.json` (one port
entry). 22 new tests pass.

Files it adds:
- `src/phase2/events/heatwave.py` — detection engine (Hobday 2016): `detect_events`, `event_mask`,
  `summarise`. This is the F7 the audit had shelved as BLOCKED — now built.
- `src/phase2/derived/mhw_baseline.py` — `doy_climatology_threshold` (real day-of-year), and
  `monthly_climatology_threshold` (a pilot), plus `map_to_series` / `map_monthly_to_series`.
- `src/phase2/derived/mhw_field.py` — `mhw_day_flags_grid`, `compare_detection` (model-vs-truth
  contingency skill: POD/FAR/CSI/bias).
- `src/phase2/viz_explainer.py` — `render_explainer(st, title, formula, plain, how_to_read, caveats)`,
  the shared "About this panel" footer.
- `app/phase2/mhw_page.py` — the Streamlit page, **port 8518**.
- `scripts/phase2/{download_mhw_baseline,run_mhw_comparison}.py`.
- `tests/phase2/test_{heatwave,mhw_baseline,mhw_field}.py` — 22 tests.

## STEP 1 — MERGE (on your UI branch, `phase2-ui-instrument`)

Follow the git safety rule: work only on your feature branch, never touch `main`/`main1`, commit only
after tests pass.

```
git status                        # confirm you are on phase2-ui-instrument, tree clean
git fetch origin
git merge origin/phase2-mhw-detector
```

**Two conflicts are likely, both trivial:**
1. `src/phase2/viz_explainer.py` — if your UI already created a shared explainer/footer helper, this
   is a same-file clash. Both implement the SAME documented interface
   `render_explainer(st, title, formula, plain, how_to_read, caveats=None)`. **Keep ONE copy** (yours
   if it is a superset; otherwise Darshan's), and make sure `app/phase2/mhw_page.py`'s call still
   matches its signature.
2. `.claude/launch.json` — you both added port entries. **Keep BOTH** (the MHW entry is port 8518;
   confirm it collides with nothing in your UI — the `tests/phase2/test_launch_ports.py` guard will
   tell you).

If your UI restructured any `app/phase2/` page that Darshan's branch also carries, resolve by keeping
your structure and re-pointing to the MHW modules by import.

## STEP 2 — VERIFY

```
PYTHONPATH=src python -m pytest tests/phase2/test_heatwave.py tests/phase2/test_mhw_baseline.py tests/phase2/test_mhw_field.py -q
PYTHONPATH=src python -m pytest -q      # full suite; on your machine the daily_sat tests pass too
```
All 22 MHW tests must stay green, and nothing of yours may regress.

## STEP 3 — WIRE THE PAGE INTO YOUR UI

`app/phase2/mhw_page.py` is a standalone page (port 8518) built on the same `app/phase2/*` template as
the others. Add it into your UI shell/nav the same way you register every other feature page. It ends
in the shared `render_explainer` footer, so it already matches your "formula + plain-language" convention.

The page shows: (1) a where-are-the-heatwaves map at any depth (including SUBSURFACE events invisible
to satellite SST), and (2) the model-vs-GLORYS per-depth agreement chart from
`artifacts/mhw_comparison.json`.

## STEP 4 — REGENERATE THE DATA, AND RUN THE SATELLITE LEG (this is your advantage)

The artifacts do not travel through git. Regenerate:
```
PYTHONPATH=src python scripts/phase2/run_mhw_comparison.py     # writes artifacts/mhw_comparison.json
```

**Darshan could only run the GLORYS-INPUT leg** — his machine lacks the satellite bundle
`data/processed/daily_sat/v001`. **You have it.** So point the runner at the satellite deliverable
checkpoint + its bundle to produce the REAL satellite-driven heatwave-detection skill, and update the
page's provenance banner to say so. That is the number worth showing a judge.

## STEP 5 — KEEP THE HONESTY LABELS (non-negotiable)

The current results carry two caveats that MUST stay visible in the UI until you upgrade them:
- **Leg:** the shipped comparison is the GLORYS-input reconstruction, not the satellite deliverable,
  UNLESS you re-run it on the satellite bundle (Step 4) — then relabel.
- **Baseline:** a MONTHLY pilot (grids.npz 2019-2022), NOT a Hobday day-of-year climatology. It
  over-flags absolute counts (~40% of the basin) due to ocean warming; the **model-vs-truth agreement
  cancels that bias**, so POD/CSI are valid but absolute counts are not. To remove this caveat, build
  the real day-of-year threshold — Darshan has already downloaded 17 GB of daily baseline
  (`data/raw/glorys_mhw_baseline/glorys_thetao_{2019,2020,2021}.nc`); feed it through
  `mhw_baseline.doy_climatology_threshold` and swap it into the runner and page.

Result to quote with those caveats (388 days, 15 depths, GLORYS-input leg, monthly pilot): mean
**POD 0.68 / CSI 0.52**; strongest in the upper ocean; a **~50 m mixed-layer dip** that corroborates
the independent Argo weak spot; weakest in the deep. (Do not repeat the "300 m dip" — it was a
12-day artifact that did not survive the full run.)

## BONUS FIX WORTH TAKING

`predict_field` (`src/phase2/tscast_nio/field.py`) leaves the model on CPU — moving the model
`.to('cuda')` before inference is a **5× speedup (48 s → 10 s/day)**, and it helps EVERY dashboard
page, not just this one. Darshan's runner already does it locally; the core `field.py` fix is still
open if you want it.

## FIRST REPLY — before you merge

1. Confirm `phase2-ui-instrument` is your UI branch (say if it is a different one).
2. Say whether your UI already has a `viz_explainer` / shared footer, so you know to expect that conflict.
3. Confirm you will run the SATELLITE leg (Step 4) since you have the bundle — that turns this from
   Darshan's comparator result into the real deliverable number.
