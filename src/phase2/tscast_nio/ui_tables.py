"""The exact tables the v2 UI renders, built here rather than inside the page.

OWNER: Unit B (Darshan). PHASE-2 ONLY.

WHY THIS MODULE EXISTS
`app/phase2/tscast_page.py` must not be the place where a number is decided -- two definitions
drift and only one can be right. But "the UI shows the metrics JSON" is an untested claim as long
as the transformation lives inside a Streamlit callback, which cannot be imported (importing the
page runs `st.set_page_config` and renders it).

So the page imports these functions and renders what they return, and `scripts/phase2/accept.py`
imports the SAME functions and asserts every value matches the artifact to 4 decimals. That makes
"the UI does not invent numbers" a check that can fail, instead of a comment.

Nothing here computes science. Every value is copied or rounded from a measured artifact; the only
arithmetic is the signed difference in `argo_comparison_rows`, which is prediction minus float and
is already carried in the record as `difference`.
"""
from __future__ import annotations

import numpy as np

# Display rounding. 4 decimals is what accept.py compares to, so this constant is the contract
# between the UI and the check -- change it in one place or the check stops meaning anything.
DECIMALS = 4


def _r(v, nd: int = DECIMALS):
    """Round for display, preserving None and non-finite values as themselves."""
    if v is None:
        return None
    v = float(v)
    return None if not np.isfinite(v) else round(v, nd)


def benchmark_rows(m: dict) -> list[dict]:
    """Per-depth RMSE / correlation / bias / both skills / n, straight from the metrics artifact.

    `rmse_climatology` sits beside skill in every row on purpose: at 1000 m the model has its worst
    skill and its best absolute error at the same time, and either column alone misreads that.
    """
    mm = m["metrics"]
    depths = mm["depths_m"]
    rows = []
    for k, d in enumerate(depths):
        rows.append({
            "depth (m)": int(d),
            "RMSE (°C)": _r(mm["rmse"][k]),
            "climatology RMSE (°C)": _r(mm["rmse_climatology"][k]),
            "correlation": _r(mm["correlation"][k]),
            "bias (°C)": _r(mm["bias"][k]),
            "skill 1−RMSE/RMSEclim": _r(mm["skill_rmse_ratio"][k]),
            "skill Murphy": _r(mm["skill_vs_climatology"][k]),
            "n": int(mm["n"][k]),
        })
    return rows


def calibration_rows(m: dict) -> list[dict]:
    """Per-depth RMSE / RMS(sigma) / ratio / coverage, straight from the calibration block.

    Coverage columns are None on any run that predates them; the UI says so rather than filling
    the gap with a number it worked out itself.
    """
    cal = m.get("calibration") or {}
    rows = []
    for d in sorted(int(k) for k in cal):
        v = cal[str(d)]
        rows.append({
            "depth (m)": d,
            "n": v.get("n"),
            "RMSE (°C)": _r(v.get("rmse")),
            "RMS σ (°C)": _r(v.get("sigma")),
            "ratio RMSE/σ": _r(v.get("ratio")),
            "within ±1σ": _r(v.get("coverage_1sigma")),
            "within ±2σ": _r(v.get("coverage_2sigma")),
        })
    return rows


def profile_rows(record: dict) -> list[dict]:
    """One row per depth. A depth with no valid value is a REFUSAL carrying its reason, not a blank.

    Below-seafloor is a real answer -- "there is no ocean here" -- and rendering it as an empty
    cell would read as a missing number instead.
    """
    floor = record.get("seafloor_depth_m")
    rows = []
    for k, d in enumerate(record["depths_m"]):
        t, s = record["temperature"][k], record["sigma_t"][k]
        if t is None:
            why = (f"REFUSED — below the seafloor, which is at {float(floor):.0f} m here"
                   if floor is not None else "REFUSED — no valid ocean at this depth")
            rows.append({"depth (m)": int(d), "temperature (°C)": None, "± 2σ °C": None,
                         "explanation": why})
        else:
            # 2 SIGMA ONLY, never 1. MEASURED 2026-09-02 on the shipped model against 908
            # held-out Argo profiles: +/-2 sigma covers 80.1%-95.5% BY DEPTH (mean 91.2%,
            # worst 80.1% at 50 m); +/-1 sigma averages 63.9% and falls to 46.1% there
            # (Gaussian nominals 95.4 and 68.3). Both run slightly narrow, so the column is
            # labelled +/-2 sigma and NOT "95%" -- the nominal is not the measured figure.
            # An earlier version of this comment cited 4-5x thermocline scales; those came
            # from a calibration fitted on the wrong bundle. See EXPERIMENT_LOG E-CAL-01.
            two = None if s is None else _r(2.0 * float(s), 2)
            rows.append({"depth (m)": int(d), "temperature (°C)": _r(t, 2),
                         "± 2σ °C": two,
                         "explanation": ("0 m band UNFITTED (n=20 profiles) — "
                                         + record["reasons"][k]) if int(d) == 0
                                        else record["reasons"][k]})
    return rows


def argo_comparison_rows(record: dict) -> list[dict]:
    """Prediction, the independent float, and the signed difference -- never one without the others."""
    ac = record.get("argo_check")
    if not ac or not ac.get("argo_temperature"):
        return []
    rows = []
    for k, d in enumerate(record["depths_m"]):
        a = ac["argo_temperature"][k]
        p = record["temperature"][k]
        if a is None or p is None:
            continue
        rows.append({"depth (m)": int(d), "us (°C)": _r(p, 2), "float (°C)": _r(a, 2),
                     "difference (°C)": _r(float(p) - float(a), 2)})
    return rows


def headline(m: dict) -> dict:
    """The four tiles above the benchmark table, with missing values named rather than shown as nan."""
    o = (m.get("metrics") or {}).get("overall") or {}
    return {
        "overall RMSE": _r(o.get("rmse")),
        "skill 1−RMSE/RMSEclim": _r(o.get("skill_rmse_ratio")),
        "skill Murphy": _r(o.get("skill_vs_climatology")),
        "climatology RMSE": _r(o.get("rmse_climatology")),
    }


# ── stage 2: salinity and density ──────────────────────────────────────────────────────

def is_stage2(m: dict) -> bool:
    """Whether this metrics artifact came from a stage-2 run. Absent field means stage 1."""
    return int(m.get("stage", 1)) == 2


def salinity_rows(m: dict) -> list[dict]:
    """Per-depth salinity metrics, or [] if this run had no independent salinity to score on.

    Empty is a real answer -- it means the salinity head was never checked against an
    observation -- and the page says so rather than showing an empty table as if it were a
    measurement of zero.
    """
    ms = m.get("metrics_salinity")
    if not ms:
        return []
    cal = m.get("calibration_salinity") or {}
    rows = []
    for k, d in enumerate(ms["depths_m"]):
        c = cal.get(str(int(d)), {})
        rows.append({
            "depth (m)": int(d),
            "RMSE (psu)": _r(ms["rmse"][k]),
            "correlation": _r(ms["correlation"][k]),
            "bias (psu)": _r(ms["bias"][k]),
            "RMS σ (psu)": _r(c.get("sigma")),
            "ratio RMSE/σ": _r(c.get("ratio")),
            "n": int(ms["n"][k]),
        })
    return rows


def density_summary(m: dict) -> dict | None:
    """The eq. 5 target, measured: how far predicted density sits from observed density."""
    d = m.get("density")
    if not d:
        return None
    return {
        "RMSE (kg m⁻³)": _r(d.get("rmse_kg_m3")),
        "bias (kg m⁻³)": _r(d.get("bias_kg_m3")),
        "predicted RMS σ (kg m⁻³)": _r(d.get("predicted_rms_sigma_kg_m3")),
        "calibration ratio": _r(d.get("calibration_ratio")),
        "n": d.get("n"),
    }


def stage2_profile_rows(record: dict) -> list[dict]:
    """Salinity and density beside temperature, one row per depth, refusals kept as refusals."""
    if record.get("salinity") is None:
        return []
    rows = []
    for k, d in enumerate(record["depths_m"]):
        s = record["salinity"][k]
        rows.append({
            "depth (m)": int(d),
            "temperature (°C)": _r(record["temperature"][k], 2),
            "salinity (psu)": _r(s, 3),
            "± σ (psu)": _r((record.get("sigma_s") or [None] * len(record["depths_m"]))[k], 3),
            "density (kg m⁻³)": _r((record.get("density") or [None] * len(record["depths_m"]))[k], 3),
            "± σ (kg m⁻³)": _r((record.get("sigma_rho") or [None] * len(record["depths_m"]))[k], 3),
        })
    return rows
