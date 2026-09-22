# PROMPT FOR ARJHUN'S CLAUDE — make the marine-heatwave detector a NATIVE feature in your instrument

Paste this as your first message. This is the follow-on to PR **#1** (Darshan's
`phase2-mhw-detector` → your `phase2-ui-instrument`). That PR brings the CODE; this turns it into a
feature tile in your `app/ui/` shell, the same way `cyclone` and `validation` are — not a standalone
port-8518 page.

## STEP 1 — MERGE PR #1 FIRST

`git merge origin/phase2-mhw-detector`. It is additive. Resolve the two expected conflicts:
- `src/phase2/viz_explainer.py` — **keep YOURS** (the `Explainer` dataclass version is the superset;
  Darshan's is the simple shim). The heatwave feature below uses your `ux`/`Explainer`, not the shim.
- `.claude/launch.json` — keep both entries.

That merge gives you the reusable logic the feature needs:
- `phase2.events.heatwave` — `detect_events`, `event_mask`, `summarise` (Hobday 2016)
- `phase2.derived.mhw_baseline` — `monthly_climatology_threshold`, `map_monthly_to_series`
- `phase2.derived.mhw_field` — `mhw_day_flags_grid`, `compare_detection`
- `scripts/phase2/run_mhw_comparison.py` → writes `artifacts/mhw_comparison.json`

## THE ONE ARCHITECTURAL NOTE — this feature is WINDOW-LEVEL, not per-date

Your instrument renders one `ctx.date` per feature via `D.field(ctx.date, …)`. A marine heatwave is
defined by **5 consecutive days**, so it lives over the whole 388-day window, not a single day. So
the heatwave feature does NOT call `D.field`. Instead it:
- reads the **precomputed** model-vs-GLORYS skill from `artifacts/mhw_comparison.json`
  (produced once by `run_mhw_comparison.py` — the 388-day model inference is expensive and must not
  run inside the UI), and
- computes a **cached** per-depth "fraction of the window in a heatwave" map from the daily GLORYS
  bundle (`data/processed/daily/*.npz`) via `mhw_field.mhw_day_flags_grid` — the same ~6 s/depth
  computation Darshan's standalone `app/phase2/mhw_page.py` already does; cache it with
  `@st.cache_data`.
`ctx.date` is used only to label which window is shown, not to pick a single field.

## STEP 2 — CREATE `app/ui/features/heatwave.py`

Mirror the shape of `app/ui/features/cyclone.py` (controls → map → tiles → `ux.maths` →
`ux.inference`). Contract: exactly `def render(ctx) -> None`. Skeleton:

```python
"""Heatwaves the surface hides. OWNER: Unit A. NOT a page.

A third of marine heatwaves never reach the surface (Sun et al.; Fragkopoulou et al.), so an SST map
misses them. Because this project reconstructs the whole column, it can see them at depth. This is a
window-level feature: it reads the precomputed model-vs-GLORYS skill and a cached per-depth map, not
a single ctx.date field.
"""
from __future__ import annotations
import json, os
import numpy as np
import streamlit as st

from oceanembed import config
from phase2.derived import mhw_baseline as mb
from phase2.derived import mhw_field as mf
from app.ui import data as D, maps, ux

_CMP = os.path.join(config.ARTIFACTS, "mhw_comparison.json")

@st.cache_data(show_spinner=True)
def _fraction(depth_m: int) -> np.ndarray:
    d25 = np.load(os.path.join(config.DATA_PROCESSED, "daily", "2025.npz"), allow_pickle=True)
    d26 = np.load(os.path.join(config.DATA_PROCESSED, "daily", "2026.npz"), allow_pickle=True)
    z = list(config.DEPTHS).index(depth_m)
    temp = np.concatenate([d25["temp"], d26["temp"]], 0)[:, :, :, z].astype("float64")
    times = np.concatenate([d25["times"], d26["times"]])
    land = d25["land_mask"]
    g = np.load(os.path.join(config.DATA_PROCESSED, "grids.npz"), allow_pickle=True)
    clm12, thr12 = mb.monthly_climatology_threshold(g["temp"][:, :, :, z], g["times"])
    flags = mf.mhw_day_flags_grid(temp, mb.map_monthly_to_series(clm12, times),
                                  mb.map_monthly_to_series(thr12, times), land)
    frac = flags.mean(0); frac[land] = np.nan
    return frac

def render(ctx) -> None:
    depth = ...   # ux.control + st.selectbox over config.DEPTHS, default 100
    frac = _fraction(int(depth))
    # LEFT: maps.frame(frac, land_mask, LAT, LON) -> maps.clickable(...) -> st.altair_chart(on_select)
    # RIGHT: ux.tiles([...]); if artifacts/mhw_comparison.json exists, show POD/CSI per depth
    #        (read _CMP), else st.info("run scripts/phase2/run_mhw_comparison.py")
    # ux.maths(r"T(x,y,z,t) > T_{90}(x,y,z,\mathrm{doy}(t))\ \text{for}\ \geq 5\ \text{days}", [...symbols...], note)
    # ux.inference(what=..., conclude=..., limits=[(text, source), ...])   # caveats below
```

Land/seafloor stays a gap (NaN), never a value — `mhw_field` already enforces this.

## STEP 3 — REGISTER IT

- `app/ui/features/__init__.py` — add to `MODULES`: `"heatwave": "heatwave",`
- `app/ui/words.py` — add to `FEATURES`, in the **PROVE IT** band (next to `cyclone`):

```python
("heatwave", "Hidden heat",
 "Heatwaves the surface hides",
 "A third of marine heatwaves never touch the surface. Reconstruct the column and they appear.",
 "PROVE IT"),
```

Optionally drop `app/phase2/mhw_page.py` from any ELSEWHERE list once it lives in the shell (your
established pattern — cloud/cyclone-case-study/physics were removed from ELSEWHERE when they moved in).

## STEP 4 — THE HONESTY CAVEATS (put them in `ux.inference(limits=…)`)

Same rules Darshan shipped, non-negotiable until upgraded:
- **Leg:** `artifacts/mhw_comparison.json` as produced on Darshan's machine is the **GLORYS-input**
  reconstruction (his machine lacks `data/processed/daily_sat/v001`). **You have that bundle — re-run
  `run_mhw_comparison.py` pointed at the satellite deliverable checkpoint** to get the real
  satellite-driven skill, then relabel. Evidence: `artifacts/mhw_comparison.json` `model_leg`.
- **Baseline:** a **monthly pilot** (grids.npz 2019-2022), not a Hobday day-of-year climatology —
  absolute counts inflate ~40% from ocean warming; the model-vs-truth **agreement cancels that bias**,
  so POD/CSI are valid, the map's absolute level is not. To remove it, build the day-of-year threshold
  from Darshan's 17 GB download via `mhw_baseline.doy_climatology_threshold`. Evidence: `mhw_comparison.json` `baseline`.
- **Shelf:** continental shelf (<200 m) is the reconstruction's weakest region (Argo can't train there).
- Result to quote WITH those caveats: mean **POD 0.68 / CSI 0.52**; a **~50 m mixed-layer dip** that
  matches the independent Argo weak spot; weakest in the deep. (Not the "300 m dip" — a 12-day artifact.)

## STEP 5 — VERIFY

```
PYTHONPATH=src python -m pytest tests/phase2/test_heatwave.py tests/phase2/test_mhw_baseline.py tests/phase2/test_mhw_field.py tests/phase2/test_launch_ports.py -q
streamlit run app/ui/main.py --server.port 8500
```
Pick **PROVE IT → Hidden heat** in the rail; confirm the map and the skill panel render and the
`ux.inference` caveats show. Then push and it's on the PR into your branch.

## FIRST REPLY
1. Confirm the band/label (`PROVE IT` / "Hidden heat") or propose a better fit.
2. Confirm you'll re-run the comparison on the **satellite** checkpoint (you have the bundle) so the
   feature shows the real deliverable number, not Darshan's GLORYS-input comparator.
