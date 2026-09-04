# Feature — Cyclone Heat (TCHP + OHC + D26)

A derived product on the **frozen** TS-Cast-NIO temperature field. Tropical Cyclone Heat Potential
(TCHP) is the heat stored above the 26 °C isotherm — the variable that fuels cyclone rapid
intensification — produced daily over the Bay of Bengal and Arabian Sea from satellite-only inputs.

- Module: `src/phase2/derived/heat_content.py`
- CLI: `scripts/phase2/make_heat_content.py --date YYYY-MM-DD [--range S E]` → NetCDF in `artifacts/derived/heat_content/`
- Page: `app/phase2/cyclone_heat_page.py` (`streamlit run … --server.port 8509`)
- Tests: `tests/phase2/test_heat_content.py` (10, all offline — synthetic profiles, no bundle)

## Design note (for the report appendix)

**Constants — and a named difference from the physics module.** TCHP uses the TCHP-literature
convention **cp = 4000 J/(kg·°C), ρ = 1026 kg/m³** (Leipper & Volgenau 1972), both configurable. The
project's OHC-budget module `phase2.physics.ohc` uses cp = 3985, ρ = 1025 (the climate-budget
convention). They differ by ~0.4% and are kept as each field's own convention rather than silently
unified. The **OHC_0-700 product reuses `ohc_constant_density`**, so it carries the physics module's
constants, not TCHP's — a deliberate reuse, since the shipped model predicts temperature only (no
salinity), which is exactly the temperature-only, constant-density case that function exists for.

**Unit factor.** cp·ρ·∫(T−26)dz has units J/m². 1 J/m² = 1×10⁻³ kJ ÷ 1×10⁴ cm² = **1×10⁻⁷ kJ/cm²**,
so TCHP = cp·ρ·∫/1e7. A realistic tropical column lands ~20–120 kJ/cm²; a result near 1e6 is a unit
bug, and a test guards that range explicitly.

**D26 — the 26 °C isotherm depth, by linear interpolation.** Walk down from the surface; the
surface-connected warm layer is the cumulative-AND of (T ≥ 26) — so a deep re-warming below a cold
layer is correctly *excluded*. D26 is interpolated between the last warm level `z[k-1]` (T ≥ 26) and
the first colder level `z[k]` (T < 26):

    D26 = z[k-1] + (z[k] - z[k-1]) · (T[k-1] − 26) / (T[k-1] − T[k])

**Integration.** Trapezoid of (T−26) across the non-uniform standard depths over the contiguous warm
levels, **plus a final partial triangle** from the deepest warm level down to D26, where (T−26)
reaches 0.

**Edge cases (all tested).** SST < 26 → TCHP = 0 (no warm layer). Whole valid column ≥ 26 → D26 = the
deepest valid level, flagged (physically rare in the NIO — a data smell). Land / all-NaN column →
**NaN, never 0** (0 would read as "cold"). OHC that does not reach z_ref → NaN, never a partial
integral labelled as full (the Phase-1 shelf-extrapolation failure this project already fixed once).

**Field == scalar, by construction.** `heat_content_field` maps the *same* unit-tested scalar TCHP
and D26 functions across the depth axis, and OHC is one vectorised `ohc_constant_density` call. There
is no second implementation to drift from the scalar — the drift-safety rule `field.py` itself
follows — and a test asserts field value == scalar value at each cell.

## Uncertainty (added after Arjhun's review)

Every other v2 surface shows ±2σ; TCHP originally showed a bare number. `integrated_uncertainty`
now propagates the model's per-depth σ through the TCHP / D26 / OHC integrals by Monte Carlo (sample
candidate profiles, evaluate the *same* tested scalar functions on each), and the point-inspect panel
shows a ±1σ range beside each value.

**Honest limit, stated on screen and in the number itself.** The model provides per-depth variance
with **no cross-depth covariance**, so samples draw each depth independently. Adjacent-depth errors
are physically likely correlated, so the reported spread is a measured **lower bound**, not the true
uncertainty. This is the *same* situation the model already handles for T/S→density: `tscast.py`
predicts a density-uncertainty head directly rather than propagating T/S variance analytically,
"because the paper is explicit that T/S error covariance is non-negligible." There is no learned
joint-uncertainty head for these derived quantities, so the sampled lower bound is the honest best
available, and the caveat travels with the number (`assumption` field), not just in a docstring.
Monte Carlo (not a delta-method formula) because the 26 °C crossing and partial-layer term make the
analytic derivative awkward across the edge cases (SST<26, all-warm, land) that the scalar functions
already handle correctly.

## Frozen-safety

Additive, new-files-only: nothing modifies the checkpoint, the bundle, `dataset.py`, `inference.py`,
or the split. `freeze.py --check` is unaffected (verify on the box that carries the bundle). The CLI
and page need `data/processed/daily_sat/v001`, so they run on the training box; the page shows a
clear message rather than blanking if the bundle is absent.
