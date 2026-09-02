

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

### ~~The result worth showing a jury — satellite SSH BEATS the reanalysis~~ RETRACTED

**CORRECTED 2026-09-02 by Darshan (D6). The claim below was wrong and I am leaving it visible.**

I wrote: *"Swapping in GLORYS SSH makes the model WORSE: the penalty rises to +0.0418, 123% of
baseline, and the sign holds on all three seeds. DUACS `adt` is a better input for this
reconstruction than GLORYS `zos` — a replicated case of a satellite observation outperforming the
reanalysis."*

**The "3/3" was the wrong column.** `sign_holds` on the GLORYS-ssh leg answers *"is this leg worse
than ALL-GLORYS on all three seeds"*. It does **not** answer *"does swapping only SSH hurt relative
to the satellite baseline"*, which is the claim I made. The all-GLORYS term cancels in the contrast
that matters. Recomputed seed-matched, ssh-swap minus satellite baseline:

| seed | satellite SSH | GLORYS SSH | swap delta | better input |
|---|---|---|---|---|
| 42 | 0.0424 | 0.0265 | **−0.0159** | GLORYS SSH |
| 43 | 0.0528 | 0.0454 | **−0.0075** | GLORYS SSH |
| 44 | 0.0071 | 0.0536 | +0.0465 | satellite SSH |
| | | | **mean +0.0077** | **1 of 3 seeds** |

Satellite SSH wins **on the mean only**, and the mean is carried entirely by seed 44, where the
satellite baseline happened to land anomalously low (0.0071). On the other two seeds GLORYS SSH is
the better input.

**And this is the same 1-of-3 result I refused to promote for SST in the paragraph above it.** I
demoted SST for a flipping sign and headlined SSH off the wrong column, in the same table — two
standards for two results from one experiment. That is precisely the forking-paths move Darshan's
Call-2 pre-registration existed to prevent, and the pre-registration did not save me from it
because I misread which contrast the field described.

**The honest version, his wording, to be used verbatim:**

> "In our isolation, the one input where the satellite product may beat the reanalysis is sea
> surface height — our altimetry SSH was the better input on the three-run average. Like every
> effect at this scale it is carried by one of the three runs, so we present it as a lead, not a
> result — the same bar we held every other channel to."

Nuance he added and it is right: DUACS `adt` is itself an observation-driven L4 analysis, not a raw
observation. *"Altimetry-derived field beats the reanalysis field"* is exact; *"observation beats
reanalysis"* overstates what both products are.

**Do not put "outperforms on every one of three runs" or "replicated 3/3" anywhere.** The commit
message of a3604fa contains the retracted claim and cannot be edited; this entry supersedes it.

### Limits

The Bay of Bengal column flips sign on EVERY swap leg (n=283 profiles, sd up to 0.065). Channel
attribution is not possible in that basin at this sample size, and nothing about the BoB should be
read off this table. Three seeds resolves a large effect, not a small one.

artifact: `artifacts/channel_isolation.json`
