

## E-BASIN-01  2026-09-02  — A12: the Bay of Bengal hypothesis is FALSIFIED

**Status: VALIDATED, 3 seeds, and it overturns the story we were about to present.**

Satellite penalty = satellite-input RMSE minus GLORYS-input RMSE, seed-matched, scored through the
shared `eval_argo` path on the canonical `phase2.basins` partition. 962 profiles: 679 Arabian Sea,
283 Bay of Bengal, 0 unassigned.

| seed | overall | Arabian Sea | Bay of Bengal |
|---|---|---|---|
| 42 | +0.0289 | +0.0424 | -0.0037 |
| 43 | +0.0276 | +0.0528 | -0.0376 |
| 44 | +0.0005 | +0.0071 | -0.0168 |
| **mean** | **+0.0190** | **+0.0341** | **-0.0194** |

**Both signs hold on all three seeds, in OPPOSITE directions.** Satellite input is consistently
WORSE in the Arabian Sea and consistently BETTER in the Bay of Bengal. BoB-minus-Arabian is
-0.0462, -0.0904, -0.0238 — never once positive.

### What this kills

The project's most jury-legible story was: *satellite SSS floors at 30.78 psu against a real 6.43
at the Meghna/Ganges, so the Bay of Bengal should suffer.* Darshan proposed it, I recorded it in
the bundle provenance, and we were one step from presenting it.

**It is false.** The BoB is where satellite input does BEST. The sensor limit is real — the product
genuinely cannot see the plume — but it is NOT what costs accuracy. Two separate claims, and only
the first survives.

### What replaces it — [INFERRED], not measured

The penalty lives in the Arabian Sea. A plausible mechanism is that the Arabian Sea is the more
dynamically demanding basin for a satellite-derived current field: the Somali Jet and the summer
upwelling are strong, wind-driven and ageostrophic, and GLOBCURRENT's geostrophic+Ekman estimate
may resolve them less well than GLORYS' modelled `uo/vo`. **This is a hypothesis. It has not been
tested, and it must not be presented as the explanation until a currents-ablation-by-basin is run.**
We have just been burned once by exactly that shortcut.

artifact: `artifacts/basin_3seed.json`
