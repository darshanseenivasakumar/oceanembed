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
