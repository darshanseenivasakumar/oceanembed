# F5 — Physics: mixed layer, barrier layer, thermocline, ocean heat content

**Owner:** Unit A (Arjhun) · **Branch:** `phase2-physics` · **Status:** IMPLEMENTED + TESTED,
**not VALIDATED** (§5).

---

## 1. What was blocked, and why it no longer is

The Phase-2 audit listed OHC as computable "only under an assumed constant seawater density",
because subsurface salinity was believed missing. Unit B established the cause was wrong: the raw
GLORYS files always carried `so` at 36 levels — Phase 1 simply took index 0, since it only needed
surface predictors (`AGENT_SYNC.md`, 2026-08-26). No download was required.

So density comes from real T and S, and the caveat is gone rather than documented.

---

## 2. Method

### Mixed layer depth — density criterion
de Boyer Montégut, Madec, Fischer, Lazar & Iudicone (2004), *Mixed layer depth over the global
ocean*, JGR Oceans 109, C12003. https://doi.org/10.1029/2004JC002378

From a **10 m reference** (chosen to skip the diurnal skin layer):

| quantity | criterion |
|---|---|
| **MLD** | shallowest depth where σθ exceeds σθ(10 m) + **0.03 kg m⁻³** |
| **ILD** | shallowest depth where \|θ − θ(10 m)\| exceeds **0.2 °C** |
| **Barrier layer** | **ILD − MLD** |

### Why both criteria, and why that matters here more than almost anywhere

The two disagree wherever **salinity**, not temperature, sets the stratification. Their difference
is the barrier layer: a salinity-stratified lid inside an isothermal layer, which suppresses
entrainment of cool water from below so the surface keeps warming. It is a recognised control on
cyclone intensification.

The northern Bay of Bengal has one of the strongest barrier layers in the world ocean, from
Ganges–Brahmaputra–Meghna discharge. Unit B measured the signature in our own data: **minimum
salinity 6.43 psu at 22.50 °N, 91.25 °E**.

So a temperature-only MLD would be systematically **too deep** in exactly the region our
observation-priority map ranks first (17.75–19.25 °N, 85.75–93.75 °E), and in exactly the process
the project's impact story rests on. A synthetic test measures that error at **≥ 50 m** for a
realistic plume profile. Using density here is not a refinement — it is the difference between
describing this basin and mis-describing it.

### Equation of state
One-atmosphere EOS-80 implemented directly — `gsw` (TEOS-10) is not installed and
`requirements.txt` is Unit B's file, so a team-wide dependency is not Unit A's call. σθ needs only
the one-atmosphere polynomial, which is ~20 lines.

  UNESCO (1983), *Algorithms for computation of fundamental properties of seawater*, Technical
  Papers in Marine Science 44 · Millero & Poisson (1981), *Deep-Sea Research A* 28(6), 625–629.

**Coefficients verified against published check values before anything was built on them** — all
agree to < 1×10⁻³ kg m⁻³:

| S | θ | published | ours |
|---|---|---|---|
| 0 | 5 | 999.96675 | ✓ |
| 35 | 25 | **1023.34300** | ✓ |
| 35 | 0 | 1028.10600 | ✓ |
| 0 | 25 | 997.04700 | ✓ |

GLORYS `thetao` is *potential* temperature, so it feeds σθ directly with no conversion.

### Ocean heat content
`OHC(0→z) = ∫ ρ(S,θ)·cp·θ dz`, reported in **GJ m⁻²**.

---

## 3. Named assumptions

1. **cp = 3985 J kg⁻¹ K⁻¹**, constant. Conventional in OHC budgets; varies ~±0.5% over our T/S
   range — small beside model error, but it is an assumption.
2. **0 °C reference** for heat content, so values are absolute. Differences between two OHC fields
   are unaffected by the choice.
3. **One-atmosphere density**, not in-situ. Pressure raises in-situ density ~0.4–0.5% at 1000 dbar,
   so integrating to 1000 m understates OHC by well under 1%. TEOS-10 with a pressure term is the
   upgrade path.
4. **Trapezoidal integration on 15 non-uniform levels.** Resolution is finest where the gradient is
   steepest, but the thermocline is still coarsely sampled.

**Bathymetry:** a column that does not reach the requested depth returns **NaN**, never a partial
integral labelled as a full one — the Phase-1 shelf-extrapolation failure in a different costume.

---

## 4. Tests — 31, scientific rather than shape-only

- EOS matches four published UNESCO check values
- fresher water is lighter; negative salinity yields NaN, not a number
- MLD recovers a known mixed-layer base; deeper mixing gives deeper MLD
- a fully uniform column returns **NaN, not the deepest level** — "unresolved" and "at least this
  deep" are different claims
- adding a halocline does not move the ILD (which is what makes the comparison meaningful)
- **barrier layer detected in a Bay-of-Bengal-style profile**, absent without salinity
  stratification, and never negative
- a temperature-only MLD is measured as ≥ 50 m too deep in a plume profile
- OHC matches an **analytic** isothermal column exactly; lands in a plausible 1–50 GJ m⁻² range
- a shelf column returns NaN at 700 m but still resolves at 200 m
- constant-density error is measured as larger in fresh water than open ocean — the claim in §2 is
  produced, not asserted

---

## 5. 🔴 Why this is NOT VALIDATED

`data/processed/subsurface.npz` is gitignored and absent on this machine, so it was regenerated
locally from `synthetic_glorys.nc`. `provenance.json` reads **`synthetic`**. Every number below
exercises the code path; none validates the science.

### Grid run, and how to read it

```
MLD (density)      23919 cells   20.00 ..  30.00   mean  20.02 m
ILD (temperature)  23919 cells   20.00 ..  30.00   mean  20.00 m
barrier layer      23919 cells    0.00 ..  10.00   mean   0.00 m
thermocline depth  23919 cells    2.50 ..  87.50   mean  11.84 m
OHC 0-300 m        23919 cells   20.48 ..  24.28   mean  22.38 GJ/m2
land stays NaN                                                 True
constant-density error       mean 0.028%   max 0.093%
```

**"Thermocline below MLD in only 11.6% of cells" looks like a failure and is not.** Checked one
profile directly: `make_synthetic_glorys.py` builds temperature as `exp(-z/250)` **from the
surface**, so there is no mixed layer at all and the steepest gradient sits at the top by
construction. Salinity varies by 0.28 psu across the whole column, so there is no barrier layer to
find and the constant-density error is correspondingly tiny.

Every one of those numbers is consistent with the synthetic data's known structure. **On real
GLORYS all three should change qualitatively** — a genuine mixed layer, a thermocline beneath it,
a real barrier layer in the northern Bay of Bengal, and a much larger constant-density error where
salinity reaches 6.43 psu. That is the validation, and it needs the real file.


### Unit B's test caught the synthetic data — exactly as designed

Running the full suite with my locally-regenerated `subsurface.npz` in place, **Darshan's
scientific sanity test failed**:

```
test_salinity_generally_increases_with_depth_in_the_bay_of_bengal
  AssertionError: Bay of Bengal should be saltier at depth than at the surface
  assert 34.58458 > 34.602943
```

At 18 N, 88 E the synthetic file has 34.60 psu at the surface and 34.58 psu at depth — a 0.018 psu
difference, which is noise. The real Bay of Bengal has a **fresh cap over saltier water**, and his
test encodes that physical expectation.

This is the correct outcome on three counts:
1. **His test works.** It rejected data that has the right shape, right dtype, right units and
   plausible magnitudes but no ocean structure — the exact Phase-1 failure mode.
2. **It confirms F5 must not be marked VALIDATED.** The synthetic stand-in is adequate for
   exercising code paths and nothing more.
3. **It only fails locally.** `subsurface.npz` is gitignored; his test SKIPS when the file is
   absent, so no one else sees this, and on his machine with real GLORYS it should pass.

No code was changed in response. Fixing a scientific sanity test to accommodate synthetic data
would be exactly backwards.

**>>> ASK DARSHAN:** a copy of `data/processed/subsurface.npz` (or the raw `glorys_*.nc`). Then
F5 produces real numbers and the barrier-layer claim becomes measured rather than argued.

---

## 6. Limitations

- **Barrier layer needs vertical resolution we partly lack.** Between 30 m and 50 m our grid has no
  level, so a 35 m MLD is reported as 50 m. Thickness estimates are quantised to the depth axis.
- **Monthly cadence.** These are snapshots; no seasonal cycle of MLD from 48 monthly fields without
  care, and no storm-response timescales at all.
- **σθ is surface-referenced**, so MLD is correct by the published definition, but deep density
  comparisons would need pressure terms.
- **Thermocline depth is quantised** to level midpoints — 14 possible values, not a continuum.
  `gradient` is returned so a caller can reject a flat profile rather than trust a depth from one.
