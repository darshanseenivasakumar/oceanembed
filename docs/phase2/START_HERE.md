# START HERE — orientation for a fresh session

You are picking up **OceanEmbed** (SIH26066) mid-Phase-2. This file exists so you can orient in
about a minute instead of reading eighteen documents. It is a **map, not a summary** — every claim
below points at the file that owns it, because duplicated facts drift and the stale copy is the one
someone reads.

Written 2026-08-26 by Unit A (Arjhun). If it disagrees with the file it points to, **the pointed-at
file wins.** Rule 8 added 2026-09-05, after the same failure had recurred five times in five
different files and no test had caught any of them.

---

## 1. Read in this order

| # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | The operating rules. Evidence tags, the 15 never-assume rules, file ownership. Non-negotiable. |
| 2 | `docs/phase2/AGENT_SYNC.md` | **The live channel between the two agents.** Newest entry first. Open asks live here. |
| 3 | `PHASE2_STATUS.md` | Feature-by-feature status table. ⚠ see §3 — it differs per branch. |
| 4 | `PHASE2_ARCHITECTURE_AUDIT.md` | What Phase 2 is, F1–F10, what the audit thought was blocked. |
| 5 | `docs/DECISIONS.md` | D-001 → D-019. **Read before re-litigating anything.** |
| 6 | Feature docs | `docs/phase2/f4-reliability.md`, `f5-physics.md` — but see §3, they live on different branches. |

Phase 1 background, only if needed: `docs/STATUS_REPORT.md`, `HANDOFF.md`,
`VALIDATION_PROTOCOL.md`, `MODEL_SPEC.md`, `DATA_CONTRACT.md`.

---

## 2. Where the project actually is

**Phase 1 is done and demoed.** `main` @ `4995444`, tagged `v1.0-demo-aug30`. The headline number is
**skill +0.387 against 879 independent Argo profiles**, satellite-driven. Never quote the GLORYS
holdout figure (+0.626) — same source as training, and "held out from what?" unravels it on stage.

**Phase 2 is two features in, both TESTED, neither VALIDATED.**

- **F4** — calibrated uncertainty (variance scaling) + Mahalanobis OOD. 40 tests.
- **F5** — MLD / barrier layer / thermocline / OHC with real seawater density. 31 tests.

`TESTED` means the code does what was intended. `VALIDATED` means the science was checked against
something independent. **Neither feature has touched real data on Unit A's machine** — that is the
single fact that governs what you can and cannot claim.

---

## 3. ⚠ Branch map, and the trap in it

| branch | head | contains |
|---|---|---|
| `main` | `4995444` | Phase 1 demo. **Untouchable.** Tagged `v1.0-demo-aug30`. |
| `phase2` | `1d7face` | Unit B's data layer: subsurface extraction, wind downloader, AGENT_SYNC |
| `phase2-reliability` | `9b1feb6` | **F4** + its doc + its `PHASE2_STATUS.md` row |
| `phase2-physics` | `a9dabff` | **F5** + its doc + its `PHASE2_STATUS.md` row |

**No single branch has everything, and `PHASE2_STATUS.md` disagrees with itself.** On
`phase2-physics` the F4 row still reads *"NOT STARTED"*, because that update was committed on
`phase2-reliability`. Do not read a status row without checking which branch you are on.

**Fix:** merge `phase2-reliability` and `phase2-physics` into `phase2`. That is Unit B's call —
posted as an ask in `AGENT_SYNC.md`, not done unilaterally.

### Two scaffold traps
- **`tests/phase2/__init__.py` breaks imports.** It makes pytest import tests as `phase2.test_*`,
  shadowing `src/phase2` so `phase2.reliability` / `phase2.physics` are unimportable. Already
  deleted *inside* both feature branches. **Cutting a new branch from `origin/phase2`? `rm -f` it
  first.** Reproduced independently twice.
- **`phase2/<feature>` branch names are impossible.** `phase2` exists as a branch, and a git ref
  cannot be both a branch and a directory. Use `phase2-<feature>`.

---

## 4. The three blockers — all the same shape

The code is written; the data lives only on Unit B's machine. Nothing else is stopping F4 or F5.

1. **`artifacts/argo_error_by_depth.json`** is gitignored → F4 cannot see real per-depth error.
   Ask: whitelist it. ~15 numbers, and it is a *result*, not raw data.
2. **Per-profile residuals + σ** are not persisted → F4's *held-out* calibration path is unusable.
   The aggregate-only path cannot be held out (a summary has no per-sample identity to split on),
   so it is hard-wired `is_validated = False`.
3. **`data/processed/subsurface.npz`** is gitignored → F5 ran on a synthetic stand-in.

**One zip of `data/raw/` + `data/processed/` + `artifacts/` closes all three** — and doubles as the
demo-day copy rehearsal, since the presentation laptop needs exactly those directories and they do
not travel through git.

---

## 5. Rules that must not be broken

From `CLAUDE.md` and hard experience. Every one of these was learned by finding a real bug.

1. **`main` is untouchable.** Never checkout, merge, rebase, reset or push to it.
2. **`src/oceanembed/`, `app/streamlit_app.py`, `app/panels/`, baseline `tests/test_*.py` are
   READ-ONLY.** Import from them. Need different behaviour? Adapter in `src/phase2/`.
3. **Stay in your own area.** Unit A owns `src/phase2/{models,reliability,physics,events,sentinel}`.
   Unit B owns `data/`, `cube/`, `validation/`, `priority/`, `app/phase2/`, `config/`. Cross-area
   change → post an ASK in `AGENT_SYNC.md` first.
4. **Never mark VALIDATED because tests pass.**
5. **Never adjust a scientific test to accommodate synthetic data.** This nearly happened: Unit B's
   `test_salinity_generally_increases_with_depth_in_the_bay_of_bengal` *failed* against a synthetic
   stand-in (34.60 psu surface vs 34.58 at depth — noise). That test was working. The data was
   wrong. Nothing was changed in response.
6. **Verify constants against published values before building on them.** The 15 EOS-80 coefficients
   were checked against four UNESCO values (incl. ρ(35,25) = 1023.343) *before* any physics used
   them.
7. **A shape check is not a validity check.** Ask of every array: *could this have been produced
   without real data behind it?*
8. **An absence is not a value.** When something is missing — a file, a year of data, a caller's
   context, water at that depth — say it is missing. Never substitute the meaning it would have
   had. A function that can mean *"I don't know"* either returns `None`/NaN, or returns **the
   reason alongside the value**. `bundle_for_checkpoint` was the first to do this; `argo_coverage`,
   `eddy.summarise(source=...)` and `field._promoted_from` now do.

### The question in rule 7 has now caught five bugs
`.gitignore` excluding `src/oceanembed/data/` · 46 m of extrapolated "500 m" values · SSS stacked
`(12,1,1,100,240)` past a bounds check that inspects values not shape · MC-dropout claiming ±0.26 °C
where the real error was 2.0 °C · the model painting 1000 m temperatures in the ~90 m Persian Gulf.

All five: **correct arrays, plausible values, wrong data.** Unit B's phrasing, now the L1 rule in
`VALIDATION_PROTOCOL.md` — *plausible values are not proof of a correct array.*

### Rule 8 has now caught five of its own, and rule 7 could not see any of them

| where | the absence | what it was reported as |
|---|---|---|
| `inference.py` | which bundle a checkpoint used | hardcoded `input_source: "glorys"` |
| `field.py` | `promoted_from` lives in the metrics, not the `.pt` | `"unpromoted"` — about the SHIPPED model |
| `eddy.summarise` | the caller never said which currents | hardcoded `"GLORYS reanalysis"` |
| `collocation_page` | the Argo table holds no rows for that year | *"floats are genuinely sparse"* — a claim about the ocean |
| `transect` (script + page) | land, or a column that never cools | *"below 26 °C at the surface"* |

**Rule 7 asks whether an array could have been produced without real data. Rule 8 asks the
opposite: was there any data at all, and did we invent its meaning?** Every entry above is
well-formed, plausible and correctly typed, so no shape check and no value check can see it — the
array is fine; the *label* is fabricated. Four were caught only by rendering the thing and reading
it against data we already had.

They also share a direction, which is the part worth remembering: **the invented meaning is always
the interesting one.** GLORYS rather than unknown; sparse ocean rather than empty table; cold
surface rather than land. That is not chance. A default gets reached for precisely because it reads
like a result — so the fabricated answer is, by construction, the one most likely to end up on a
slide.

---

## 6. What to do next

**If you are Unit A (Arjhun):** F6 events — but only what the data honestly supports. Single-snapshot
eddy/front **detection** yes; **tracking** no. Upwelling once Unit B's monthly wind-stress download
lands, using **wind-stress curl (Ekman pumping)** directly, since the monthly product carries
`eastward_stress`/`northward_stress` rather than a drag coefficient we would have to assume.

**F7 persistence is genuinely blocked and cannot be made honest.** A marine heatwave is defined on
≥5 consecutive *days*; our sampling is 48 monthly fields. Do not attempt it.

**If real data arrives:** re-run F4 and F5 and check the four things in the newest `AGENT_SYNC.md`
entry. All four fail or degenerate on synthetic data, which is exactly why they are the signal —
a genuine mixed layer should appear, the thermocline should move *below* the MLD, a real barrier
layer should show up in the northern Bay of Bengal, and the constant-density error should grow well
beyond the 0.028% measured on synthetic.

**If those do not change qualitatively, something is wrong** — the data path or the physics.
Investigate it; do not work around it.
