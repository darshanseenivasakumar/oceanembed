

## E-BASIN-02  2026-09-02  — the currents explanation is NOT supported either

**Status: the Arabian Sea penalty remains UNEXPLAINED. Report it as an open question.**

E-BASIN-01 found the satellite penalty sits entirely in the Arabian Sea (+0.0341) while the Bay of
Bengal is slightly better on satellite input (-0.0194), both signs holding 3/3. The proposed
mechanism was that GLOBCURRENT (geostrophic + Ekman) resolves the Somali Jet and summer upwelling
less well than GLORYS' modelled `uo/vo`.

Tested it: currents contribution by basin = noCUR RMSE minus full RMSE, satellite bundle, 3 seeds.
A positive value means dropping currents hurt, i.e. currents were helping there.

| seed | overall | Arabian Sea | Bay of Bengal |
|---|---|---|---|
| 42 | -0.0072 | -0.0049 | -0.0131 |
| 43 | +0.0080 | -0.0255 | +0.0928 |
| 44 | +0.0297 | +0.0266 | +0.0383 |
| mean | +0.0101 | **-0.0013** | +0.0393 |

**No sign holds in any basin.** Arabian-minus-BoB is +0.0083, -0.1183, -0.0117 —
inconsistent. If currents were the mechanism, dropping them should hurt the Arabian Sea most; the
Arabian Sea contribution averages **-0.0013**, indistinguishable from zero.

### What this does and does not establish

It does NOT refute the currents hypothesis — the test lacks the power to. It establishes that the
hypothesis is **not supported**, which is a weaker and honest statement. Two reasons the test is
underpowered: the Bay of Bengal holds only 283 of 962 profiles, so its per-basin delta carries
sd 0.0530 — larger than any effect we are chasing; and this measures whether satellite currents
CONTRIBUTE differently by basin, not whether GLOBCURRENT is WORSE than GLORYS there. The direct
test is a hybrid leg — satellite inputs with GLORYS `uo/vo` substituted — which does not exist.

### The position to hold

The basin asymmetry is real, reproducible and 3-seed stable. **Its cause is unknown.** Two
candidate mechanisms have now been proposed and neither survived: SSS blindness (falsified,
E-BASIN-01) and currents (unsupported, here).

That is the honest state and it is what should be presented. A measured asymmetry with an admitted
open cause is stronger than a plausible story with no number under it -- which is exactly what we
had this morning, twice.
