

---

## FROZEN — 2026-09-02T20:12:52  (A16)

**What is frozen.** This exact combination produced the numbers below, and
`scripts/phase2/freeze.py` re-verifies it rather than taking anyone's word.

| | |
|---|---|
| git commit | `ffd95e6e84e1` on `phase2-tscast-nio`, tree clean |
| model | `sat_7ch_s42` — cnn3d / simple / nll β=0.5 / seed 42 |
| checkpoint | `tscast_stage1.pt` sha256 `53848bb52533752d…` built at code `a67feea` |
| **input** | **satellite** — `data/processed/daily_sat/v001`, 388 days |
| target | GLORYS12V1 daily (cmems_mod_glo_phy_my_0.083deg_P1D- |
| split | train 2025-06-01..2026-03-26, test 2026-04-01..2026-06-23, `embargoed_v2`, 5 targets embargoed |
| T_SEQ | 11 (data window); **built_t_seq 1** — different numbers, and confusing them cost a day |

**Measured against 962 independent Argo profiles (12829 depth comparisons):**

    RMSE 0.907761 degC   bias +0.1003   correlation 0.8812
    skill vs climatology +0.2595   (climatology RMSE 1.2259)

**Uncertainty:** ±2σ only. Coverage 80.1%–95.5% by depth (mean
91.2%, Gaussian nominal 95.4%), worst at 50 m. No ±1σ band and no confidence
percentage is displayed anywhere, because neither is defensible.

**Smoke inference at freeze:** 15.0N 68.0E 2026-05-15 → mean |error| **0.326 °C** across 14 depths
against an independent float 13 km / 2 days away. 530 tests pass, 10 skipped.

### Carried into the freeze, stated rather than omitted

1. **INCOIS LAS gridded Argo (PS req 16) is unreachable** — their data layer is down (Darshan's
   probe: the right products exist, every retrieval route fails). Validated on argopy floats with
   the deviation documented. Re-probe before any public claim.
2. **The Arabian Sea satellite penalty (+0.0341, sign holding 3/3) is reproducible and its cause is
   UNKNOWN.** Four mechanisms proposed and tested; none supported. This is the honest headline.
3. **Uncertainty is improved, not calibrated.** 80.1% coverage at 50 m against a 95.4% nominal.
4. **Stage 2 has never been run on satellite input** — there is no satellite T+S+density number and
   none may be implied.
5. **accept.py carries one known pre-existing failure** comparing two legacy Phase-1 artifacts with
   different profile-retention rules. The RMSE agreement it also checks passes at 0.0213 degC, and
   neither artifact underwrites the shipped model.

### What must NOT change without re-freezing

The checkpoint, the bundle, `dataset.py`, `inference.py`, or the split. Any of those moving
invalidates every number above. `python scripts/phase2/freeze.py --check` is the gate.
