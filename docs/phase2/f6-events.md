# F6 — Event detection: eddies, fronts, upwelling

**Owner:** Unit A (Arjhun) · **Branch:** `phase2-events` · **Status:** TESTED
(eddies and upwelling additionally have independent scientific validation; **fronts do not** — §5)

Design spec: `docs/phase2/f6-events-design.md`. Built after Unit B's real-data bundle landed, so
unlike F4 and F5 this feature ran on **real GLORYS and real wind from the start**.

---

## 1. What was built

`src/phase2/events/` — 64 tests pass (`tests/phase2/`), 206 pass repo-wide, baseline untouched.

| module | what it does |
|---|---|
| `_metric.py` | spherical-metric derivatives (`dx = R cos(lat) dlon`), cell areas, 4-connected components |
| `eddy.py` | Okubo-Weiss `W = Sn² + Ss² − ω²`, cores at `W < −0.2 σ_W`, discrete eddies with polarity |
| `fronts.py` | SST gradient in °C/100 km, percentile threshold, connected front segments |
| `upwelling.py` | `upwelling_signature`, `ekman_pumping`, `load_wind_stress`, `climatological_sst_reference` |
| `_realdata.py` | "is this a real ocean" from **structure**, never from a provenance string |

**Detection only.** No function accepts a time axis; `detect_eddies` raises on one. 48 monthly
fields cannot support tracking, and a caller passing the whole record is usually about to try.

---

## 2. The eddy detector finds the Great Whirl [VERIFIED]

The strongest result in F6, because the expectation is external to this codebase.

Largest **anticyclonic** eddy in 4–12°N / 48–58°E, averaged across four years by month:

```
month   n_anticyc   largest R (km)      centre
  01        2.5           86         11.1N 54.0E   #######
  02        5.5           84          8.3N 53.3E   #######
  03        7.5          104          6.8N 55.9E   ########
  04        8.5          124          7.4N 53.8E   ##########
  05        7.0          134          8.1N 53.8E   ###########
  06        6.0          178          7.0N 52.0E   ##############
  07        6.2          234          7.4N 52.7E   ###################
  08        4.8          243          7.6N 52.6E   ####################
  09        3.5          214          8.4N 53.1E   #################
  10        4.8          229          7.9N 53.0E   ###################
  11        4.0          194          6.5N 52.4E   ################
  12        5.0           77          6.5N 52.3E   ######
```

A large anticyclone grows from ~85 km in Jan–Feb to **243 km in August**, sits at a stable
~7.5°N 53°E through the season, and collapses to 77 km in December. That is the seasonal cycle,
location and scale of the **Great Whirl** — the Somali anticyclone that spins up with the SW
monsoon and decays in late autumn.

**Evidence tags, kept apart deliberately.** That a large anticyclone with this seasonal cycle,
position and radius exists in the data is **[VERIFIED]** — the run is reproducible from
`detect_eddies` on `grids.npz`. That this feature *is* the Great Whirl rests on the standard
description of it, which is **[INFERRED]**: no paper was re-read this session. Before this goes on
a slide, check the season, latitude band and radius against a citable source.

Basin-wide counts are plausible and the polarities are balanced — 115–163 eddies per snapshot,
mean radius ~50 km, cyclonic/anticyclonic within a few percent of even. A sign error in the
vorticity would show as an all-one-polarity census; a test asserts against it.

---

## 3. Upwelling: the SW-monsoon signal is there, with a working control [VERIFIED]

Fraction of each box flagged (signature **and** positive Ekman pumping), monthly means over 4 years:

| box | SW monsoon (Jun–Sep) | NE monsoon (Dec–Feb) | ratio |
|---|---|---|---|
| Somali coast (5–12N, 45–55E) | 0.10% | 0.01% | **8.3×** |
| Oman/Arabian (17–23N, 56–60E) | 1.96% | 0.00% | **∞** |
| Bay of Bengal *(control)* | 0.00% | 0.13% | 0.0× |

Somali and Oman are SW-monsoon dominated; the Bay of Bengal control — which has no comparable
monsoon upwelling system — goes the other way. **The control is what makes this a test**: a
detector that simply fired wherever the ocean was cold would have lit up the Bay too.

**The absolute fractions are small (1–5%), and that is a real property of the criterion, not a
bug.** The signature is an intersection of three partly-independent masks. Decomposed for the Oman
box:

```
month     cold   shoaled   ekman>0   cold&shoaled    ALL
  01    73.25%     0.23%     7.83%          0.12%   0.00%
  06    57.71%    25.00%    48.36%         22.08%   5.14%
  08    94.51%    14.72%    49.65%         12.73%   1.40%
  11    52.92%     0.00%     0.58%          0.00%   0.00%
```

`shoaled_thermocline` is the term carrying the seasonality — 0% for eight months of the year,
15–25% in June–August. The result records `limiting_term` so nobody credits the SST term with
work it is not doing.

---

## 4. A finding against my own design: the default SST reference inverts the Somali signal

The spec chose "colder than the **zonal mean** at that latitude" as the default for *cold*. On real
data that is **wrong in the one place it matters most** [VERIFIED]:

| box | reference | SW (Jun–Sep) | NE (Dec–Feb) | ratio |
|---|---|---|---|---|
| Somali | zonal mean *(spec default)* | 85.8% | 97.3% | **0.88× — backwards** |
| Somali | monthly climatology | 42.7% | 25.4% | **1.68× — correct** |
| Oman | zonal mean | 81.9% | 73.9% | 1.11× |
| Oman | monthly climatology | 47.2% | 38.6% | 1.22× |

**Why.** A coastal upwelling box is colder than its own latitude band *all year*. "Colder than the
zonal mean" is therefore a geographic fact about the Somali coast, not an event — it is true 97.9%
of the time in January. The climatology reference asks "colder than normal **here**, for **this
month**", which is an anomaly, and the direction corrects.

**What changed, and what did not.** `upwelling_signature` already took `sst_reference`, so no API
change was needed. Added `climatological_sst_reference(month)`, and the result now reports
`sst_reference_kind`, with the zonal path labelled `FALLBACK` in the payload itself. The default
was **kept** rather than switched, because `climatology.npy` is gitignored and may be absent — but
it can no longer present itself as the right answer.

The `cold` term remains the weak one (~40% baseline even against climatology). Stated here so the
weakness is on the record rather than discovered by whoever builds F9 on top of it.

---

## 5. What is NOT validated

- **Fronts.** The detector runs and reports plausible gradients (strongest 11.4 °C/100 km at
  11.4°N 51.5°E in July — the Somali upwelling front region, which is encouraging). But **nothing
  independent was checked**. No front climatology, no published census. `detect_fronts` is
  `TESTED`, not `VALIDATED`, and the percentile threshold means it *always* returns the sharpest
  gradients present — it can never tell you a snapshot has no fronts. `threshold` and
  `mean_gradient` are returned so a flat field is visible as one.
- **The Great Whirl identification** — see §2, `[INFERRED]` pending a citation check.
- **Eddy census against an independent product.** Counts are plausible and balanced; they have not
  been compared to AVISO/META or any published eddy database.

---

## 6. Limitations, written before the numbers and unchanged by them

- **Monthly cadence.** Detection only — no tracking, lifetime, or propagation speed. F7 persistence
  remains impossible and was not attempted.
- **0.25° grid.** ~25 km cells; sub-mesoscale features are unresolved. `min_cells=4` for eddies.
- **Monthly-mean wind stress.** The curl of an average is not the average of the curl. Averaging
  removes the short, strong-curl events that drive much of real pumping, so these numbers are a
  **lower bound on episodic upwelling** and an estimate of the seasonal pattern.
- **GLORYS reanalysis, not observations.** Every eddy here is an eddy *in the reanalysis*.
  `summarise()` carries that string in its output.
- **Okubo-Weiss is threshold-sensitive** and over-detects in noisy velocity fields. A
  geometry-based alternative (Nencioli et al. 2010) avoids the threshold; recorded, not adopted.

---

## 7. Two data traps found while building this

**1. The wind grid is offset half a cell** [VERIFIED]. The CMEMS monthly product is on cell centres
(5.125, 5.375, …); the frozen grid is on cell edges (5.000, 5.250, …). Identical `(100, 240)`
shape, identical spacing, plausible values — and every wind value ~14 km southwest of where a naive
assignment puts it. Ekman pumping is a curl and the upwelling is coastal, so the shift lands
exactly where it does most damage. `load_wind_stress` regrids and asserts; a test checks *both*
that the raw grid is offset and that the loader corrects it, so it fails if either the regrid is
deleted or the product changes grid.

**2. A provenance string lied, and the code that writes it is unchanged.** Before the bundle,
`subsurface.npz` here was stamped `source="real-glorys-subsurface"` over synthetic data (BoB
salinity inverted, domain minimum 34.09 psu against a real 1.29). It is real now and the stamp is
accurate **by coincidence** — `extract_subsurface.py:112` still writes it unconditionally. Hence
`_realdata.py`: F6 decides "is this a real ocean" from the fresh cap, the salinity range and the
mixed-layer/thermocline ordering, never from a string. Current reading:

```
[ok] bob_fresh_cap_psu           4.776   (threshold 0.5)
[ok] domain_min_salinity_psu     1.287   (threshold 30.0)
[ok] thermocline_below_mld_frac  0.878   (threshold 0.6)
=> REAL OCEAN STRUCTURE
```

Test 11 in `test_events.py` was specified as a tripwire asserting `False` and **flipped to
`True`** when the bundle landed. The flip is documented rather than quietly edited, because the
flip is the evidence.

---

## 8. Reproduce

```bash
python -m pytest tests/phase2/ -q          # 64 passed
```

Requires `data/processed/{grids,subsurface}.npz`, `data/raw/wind/`, `artifacts/climatology.npy` —
all gitignored, all in Unit B's bundle. Real-data tests **skip** (never fake) when absent.

## 9. References

Okubo (1970) *Deep-Sea Res.* 17, 445–454 · Weiss (1991) *Physica D* 48, 273–294 ·
Isern-Fontanet et al. (2003) *JTECH* 20, 772–778 · Chelton et al. (2007) *GRL* 34, L15606 ·
Nencioli et al. (2010) *JTECH* 27, 564–579 · Belkin & O'Reilly (2009) *J. Mar. Sys.* 78, 319–326 ·
de Boyer Montégut et al. (2004) *JGR* 109, C12003 (via F5).

**[INFERRED]** that each states what is attributed to it — these are the standard references for
these methods, recorded in F5's research pass and the Phase-2 audit, but none was re-read this
session. **Verify before any of it reaches a slide or a report.**
