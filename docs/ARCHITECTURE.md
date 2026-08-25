# ARCHITECTURE.md  (Owner: Unit A — Arjhun)  [seeded by B]

```
GLORYS surface (SST,SSS,SSH,u,v)            Argo profiles (independent, 2022)
        | [B] preprocess/normalize (train-stats)          | [B] argo_test
        v                                                 v
   [B] X[N,11], y[N,11]  ---> [A] per-column MLP --(+[A] MC-dropout)--> mean/std
        |                                                 |          [C] climatology(2019-21)
        +------------------- [B] reconstruct() seam ------+------------------+
                                    |
        +----------------+---------+----------+-------------------+
        v                v                    v                   v
  profile+uncert   [C] anomaly      [A] observation-priority   [C] metrics vs [L4 holdout / L5 Argo]
        \________________ [B] Streamlit shell + [C] panels _____________/
```

Seam = `inference/predict.py::reconstruct()` returns the frozen dict
`{depths[11], profile_mean[11], profile_std[11], reliability[11], anomaly[11], argo[11|None]}`.
Grid variant `reconstruct_grid(date)` returns `{temp, uncertainty, anomaly, priority}`.
Arjhun: expand module boundaries + data-flow notes here as you build.

---

## Observation-priority (Unit A) — method and weighting

**Honest framing (non-negotiable):** *"regions where additional observations may provide high
scientific value."* Never *"the AI tells MoES where to deploy Argo floats."*

```
anomaly(100,240,11)  --nanmean|.|over depth-->  a2d --,
uncertainty(100,240,11) --nanmean over depth-->  u2d --+--> normalize each to [0,1] --> weighted
_argo_sparsity(100,240) (distance to nearest Argo) -> s --'                             geometric mean
                                                                                             |
                                                                             priority(100,240) in [0,1]
```

**Combination:** weighted geometric mean of the three normalized factors, default weights
`(1, 1, 1)`. Equal weighting is the honest default — we have no evidence yet that one factor should
dominate. Callers can override via `weights=`.

**Why multiplicative, not additive.** A location is only worth observing if it is *all three* of
anomalous, uncertain, and unobserved. A sum lets one large factor carry a location that is
uninteresting on the other two.

**Why geometric mean, not the raw product.** With equal weights the two produce an **identical
ranking** (the cube root is monotonic — asserted in `tests/test_observation_priority.py`), but a
product of three [0,1] numbers collapses toward zero, so a colour map of it is almost entirely dark.
The geometric mean preserves the ordering while spreading values across [0,1] so the panel is
readable.

**Normalization:** 1st–99th percentile by default (`robust=True`) so a single outlier cell cannot
squash the rest of the basin. `robust=False` gives plain min-max.

**Degenerate factors — the failure this design exists to prevent.** `predict.py::_argo_sparsity()`
returns a **uniform** grid whenever `argo_test` is absent, which is the state of the repo today.
Min-max scaling a constant grid yields all-zeros, which would silently zero the entire priority map:
the panel renders blank and reads as a bug rather than as a missing input. So a constant or all-NaN
factor is treated as **NEUTRAL (all ones)** and warns. If *all three* are degenerate the result is
**all-NaN**, so the UI hides the panel — better than painting the whole basin as maximum priority.

**Land:** `NaN` in any input propagates to `NaN` in the output. Land must never score `0`, which
would read as "evaluated, and it ranked lowest."

**Verified 2026-08-25** against the real seam (`predict.py:165-176`, real `_argo_sparsity()`,
today's no-Argo repo state): `priority (100,240) float32`, ocean 0.0000–1.0000, mean 0.5654,
856 distinct values, land all-NaN, ocean all finite. `pytest tests/test_observation_priority.py`
→ **11 passed**.
