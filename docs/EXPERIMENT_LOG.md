

## E-BASIN-03  2026-09-02  — the hybrid leg: currents are NOT the mechanism

**Status: VALIDATED. The Arabian Sea penalty SURVIVES swapping in GLORYS currents.**

Direct test of the E-BASIN-02 hypothesis. Built `data/processed/daily_hybrid_glocur/v001` — the
satellite bundle with GLORYS `uo/vo` substituted for the two currents channels, everything else
untouched — and trained 3 seeds with the identical recipe. **This bundle is a DIAGNOSTIC and is
marked as such in its own provenance; the anti-GLORYS guard must reject it, and no shipped model
may ever be trained on it.**

Penalty = leg RMSE minus the seed-matched GLORYS-input RMSE.

| basin | satellite (sat u/v) | hybrid (GLORYS u/v) |
|---|---|---|
| overall | +0.0190 sd 0.0160 holds | +0.0183 sd 0.0104 holds |
| **Arabian Sea** | **+0.0341** sd 0.0240 holds | **+0.0245** sd 0.0072 holds |
| Bay of Bengal | -0.0194 sd 0.0171 holds | +0.0030 sd 0.0280 FLIPS |

### The result

**Giving the model GLORYS' own currents removes only about a quarter of the Arabian Sea penalty.**
It falls from +0.0341 to +0.0245, and the sign holds on all three seeds with a
TIGHTER spread (sd 0.0072 against 0.0240). Roughly 72% of the penalty is still there when the
currents channels are byte-identical to the comparator's.

The per-seed CHANGE is -0.0209, -0.0335, +0.0256 — **inconsistent**, so no portion of the penalty
may be attributed to currents as a number. What IS established is that currents cannot be the
dominant cause, because removing the difference entirely leaves most of the effect standing.

### Where that leaves the cause

Narrowed, not solved. The Arabian Sea penalty must come from **SST, SSS, SSH, or the encoder's
response to them** — those are what remain different between the hybrid leg and the GLORYS leg.

Three mechanisms proposed, three not supported:
  1. SSS blindness in the Bay of Bengal — **falsified** (E-BASIN-01)
  2. Currents contribute differently by basin — **unsupported** (E-BASIN-02)
  3. Satellite currents are worse in the Arabian Sea — **refuted here**: the penalty survives them

**Also worth recording:** the Bay of Bengal's satellite ADVANTAGE (-0.0194, sign holding 3/3)
disappears in the hybrid leg (+0.0030, flipping). That hints satellite currents were HELPING
in the BoB, which is the opposite of the original story. It flips across seeds, so it is a lead,
not a result.

The honest position for the jury: a measured, reproducible, 3-seed-stable basin asymmetry whose
cause we have tested three ways and not yet found. artifact: `artifacts/hybrid_currents_basin.json`
