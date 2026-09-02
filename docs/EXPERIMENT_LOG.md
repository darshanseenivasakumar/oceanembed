

## E-BASIN-04  2026-09-02  — channel isolation: NO single channel explains it

**Status: the elimination is COMPLETE. The Arabian Sea penalty is DISTRIBUTED, not attributable.**

Four diagnostic bundles, each the satellite bundle with exactly ONE channel replaced by GLORYS,
3 seeds each, identical recipe. 12 runs plus the 3 already-run currents legs. Every bundle is
marked DIAGNOSTIC in its own provenance; the anti-GLORYS guard must reject all of them.

Penalty = leg RMSE minus the seed-matched all-GLORYS-input RMSE, Arabian Sea:

| swapped to GLORYS | Arabian penalty | % of baseline remaining | sign holds 3/3 |
|---|---|---|---|
| nothing (pure satellite) | **+0.0341** | 100% | yes |
| SST | +0.0109 | 32% | **NO — flips** |
| SSS | +0.0205 | 60% | yes |
| SSH | **+0.0418** | **123%** | yes |
| currents u,v | +0.0245 | 72% | yes |

### The answer, and it is a negative one

**No single channel accounts for the penalty.** SST is the largest candidate — replacing it removes
about two thirds — but **its sign does not hold across three seeds**, so it is a lead and not a
measurement. SSS removes 40% and currents 28%, both sign-holding, and neither is close to the whole.
The reductions do not sum to 100% either: 68 + 40 + 28 = 136%. Contributions are not additive,
which is what a nonlinear encoder over correlated inputs should look like.

So the cause is **distributed across the surface fields and the encoder's joint response to them**,
not localised in one product. Four mechanisms have now been tested and none is the explanation:

  1. SSS blindness in the Bay of Bengal   FALSIFIED   (E-BASIN-01)
  2. currents contribute by basin         UNSUPPORTED (E-BASIN-02)
  3. satellite currents worse in the AS   REFUTED     (E-BASIN-03, 72% survives)
  4. any single channel                   REFUTED     (here)

### The result worth showing a jury — satellite SSH BEATS the reanalysis

**Swapping in GLORYS SSH makes the model WORSE**: the penalty rises to +0.0418,
123% of baseline, and the **sign holds on all three seeds**. DUACS `adt` is a better input
for this reconstruction than GLORYS `zos` — a direct, replicated case of a satellite observation
outperforming the reanalysis it is being compared against. This is the first result today where
satellite input wins on its own terms.

### Limits

The Bay of Bengal column flips sign on EVERY swap leg (n=283 profiles, sd up to 0.065). Channel
attribution is not possible in that basin at this sample size, and nothing about the BoB should be
read off this table. Three seeds resolves a large effect, not a small one.

artifact: `artifacts/channel_isolation.json`
