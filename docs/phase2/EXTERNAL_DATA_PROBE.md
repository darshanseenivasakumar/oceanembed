# External data probe — cyclone tracks and moored buoys

**Probed 2026-09-05. Owner: Unit A (Arjhun).** Written in the shape of `docs/INCOIS_PROBE.md`,
because the buoy result turned out to have the same shape as that one.

Features 4 (3-D TCHP + cyclone case study) and 6 (moored-buoy time-axis validation) both need data
that is not in this repo. Neither feature was started until this probe ran — the whole point is that
a case study must come from an archive, never from a storm someone remembered.

Reproduce with:

```bash
.venv/Scripts/python.exe scripts/phase2/probe_ibtracs.py
```

```bash
.venv/Scripts/python.exe scripts/phase2/probe_buoys.py
```

Artifacts: `artifacts/ibtracs_probe.json`, `artifacts/buoy_probe.json`.

---

## 1 · Cyclone tracks — **UNBLOCKED** [VERIFIED]

**Source.** IBTrACS v04r01, NOAA NCEI — the WMO-endorsed best-track archive.
`ibtracs.last3years.list.v04r01.csv`, 10.3 MB, last modified 2026-09-03, fetched to
`data/raw/ibtracs/`. The full North Indian file (`ibtracs.NI.list.v04r01.csv`, 27.9 MB) is also
reachable but unnecessary — the 3-year file covers our window with room to spare.

**Result: 15 North Indian systems have track points inside 2025-06-01 … 2026-06-23.** Four reach
tropical-storm strength (≥ 34 kt) with ≥ 10 track points inside the 5–30 °N, 45–105 °E grid box:

| SID | name | dates | pts | in box | max wind | extent |
|---|---|---|---|---|---|---|
| 2025275N22068 | **SHAKHTI** | 2025-10-01 → 10-07 | 47 | 47 | **74 kt** | 18.9–22.1 N, 60.1–68.3 E |
| 2025298N11089 | MONTHA | 2025-10-25 → 10-29 | 39 | 39 | 50 kt | 10.8–19.6 N, 80.7–89.0 E |
| 2025331N06083 | DITWAH | 2025-11-26 → 12-02 | 49 | 49 | 40 kt | 5.9–13.0 N, 80.2–82.6 E |
| 2025274N16087 | (unnamed) | 2025-10-01 → 10-03 | 17 | 17 | 35 kt | 15.9–21.2 N, 83.6–86.5 E |

**Recommended case study: SHAKHTI.** Strongest by a wide margin, seven days long, every one of its
47 track points inside the box, and it sits in the **Arabian Sea** — the basin where this project's
own error is largest and least explained, so a cyclone panel there is scientifically interesting
rather than merely decorative. MONTHA is the natural Bay of Bengal counterpart.

**The correction this probe was written to catch.** The build spec suggested "Cyclone Biparjoy or
Mocha". Both are **2023** storms and neither appears anywhere in our window. Had either been
hardcoded, the page would have rendered a track over a field from a different year.

**Caveats that must travel with any result.**

- Recent seasons in IBTrACS are **provisional**. `TRACK_TYPE` and the agency columns record how
  much of a track is operational best-track versus post-season reanalysis, and the probe keeps this
  per storm rather than flattening it.
- Longitudes in this file are already **degrees east, 60.1–100.0** for our subset, so no −180…180
  conversion is needed *for the NI basin*. A loader that assumes that globally would be wrong;
  assert the range rather than trusting it.
- `WMO_WIND` is blank for some systems (KAJIKI, BUALOI read 0 above because both wind columns are
  empty). **A blank wind is missing, not zero** — the probe takes the max of the available columns
  and a downstream loader must not treat an empty string as a calm storm.

---

## 2 · Moored buoys — **BLOCKED from this machine** [VERIFIED], data confirmed to exist

Same shape as `INCOIS_PROBE.md`: **the catalogue is healthy and the data layer is not.**

### What answers

| endpoint | result |
|---|---|
| `data.pmel.noaa.gov/pmel/erddap` — `/search`, `/info`, `/tabledap/*.das` | **200 in 1–3 s** |
| `osmc.noaa.gov/erddap` — `/info/pmelTaoDyT` | **200 in 1.7 s** |
| `data.pmel.noaa.gov/pmel/erddap/files/pmelTaoDyT/` (listing) | **200, 154 files** |

### What does not

| endpoint | result |
|---|---|
| `data.pmel.noaa.gov/.../tabledap/pmelTaoDyT.csv?…` | connect timeout, **43.9 s** |
| `osmc.noaa.gov/.../tabledap/pmelTaoDyT.csv?…` | connect timeout, **43.8 s** |
| `/files/pmelTaoDyT/t15n90e_dy.cdf` | 302 → `http://coastwatch.pfeg.noaa.gov/…` |
| that redirect target, over HTTP | connect timeout |
| that redirect target, over HTTPS | `SSL: UNEXPECTED_EOF_WHILE_READING` |

Rewriting the redirect to HTTPS does not help. The failure reproduces on **two independent hosts**
and on both the tabledap and `/files` routes, while metadata on those same hosts answers in a
second.

**Diagnosis.** The data does **not** fail to exist — it demonstrably does, see below. What is
missing is a route to it from this machine. Whether the cause is a NOAA-side outage or a restriction
on this network is **[UNKNOWN]**; reproducing across three hosts argues against a single-server
outage. This is worth re-running: the probe is cheap and the condition may be transient.

### What exists, once the data layer is reachable [VERIFIED from metadata]

- **`pmelTaoDyT`** — *TAO/TRITON, RAMA, and PIRATA Buoys, Daily, 1977-present, Temperature*.
- **Coverage 1977-11-03 → 2026-07-03**, which **contains** the model window 2025-06-01 → 2026-06-23.
- **Five moorings inside 5–30 °N, 45–105 °E**, 4.3 MB total:

| position | file | size |
|---|---|---|
| 8.0 N, 67.0 E | `t8n67e_dy.cdf` | 0.47 MB |
| 8.0 N, 90.0 E | `t8n90e_dy.cdf` | 1.13 MB |
| 12.0 N, 90.0 E | `t12n90e_dy.cdf` | 1.10 MB |
| 15.0 N, 65.0 E | `t15n65e_dy.cdf` | 0.14 MB |
| 15.0 N, 90.0 E | `t15n90e_dy.cdf` | 1.46 MB |

Companion datasets on the same host: `pmelTaoDyS` (salinity), `pmelTaoDyIso` (20 °C isotherm
depth), `pmelTaoDyD` (potential density anomaly), `rama_hourly_temp` (OceanSITES hourly).

### The question that actually decides feature 6, still unanswered

**Whether those five moorings carry finite temperature on days inside our window.** RAMA has had
long servicing gaps in the northern Indian Ocean, and a file spanning 1977–2026 says nothing about
2025–2026 specifically. File size is a hint, not an answer — `t15n65e` is 0.14 MB against
`t15n90e`'s 1.46 MB, a tenfold difference that could be a short deployment or a long gap.

`artifacts/buoy_probe.json` records this as `coverage_days_in_window: null` with a note, rather than
omitting the field — an unmeasured quantity that is simply absent from an artifact reads as one
nobody thought of.

**Do not write validation code against this source until that number is measured.** If it comes back
small, feature 6 has no time axis to validate against and the honest outcome is to say so.

### INCOIS OMNI

INCOIS's own buoy network would be the better source for an INCOIS submission. `probe_buoys.py`'s
INCOIS check failed here with `CERTIFICATE_VERIFY_FAILED`, which is **this machine's trust store,
not evidence about INCOIS** — `scripts/phase2/probe_incois_las.py` is the maintained probe for that
host and reached it on 2026-09-02. What that probe already established still stands: the LAS
catalogue answers and the Ferret/F-TDS materialization backend does not.

---

## Bearing on the plan

- **Feature 4 proceeds** on SHAKHTI, with MONTHA as the Bay of Bengal comparison.
- **Feature 6 is blocked**, not cancelled. The source is identified, its coverage is confirmed to
  span our window, and the exact five files are named. The next step is a machine that can reach
  `coastwatch.pfeg.noaa.gov` — worth Darshan trying from his network before anything else is
  attempted.
