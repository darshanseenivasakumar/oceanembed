"""Streamlit validation panel: def render(metrics=None, argo_df=None).

OWNER: Unit C (Mitun+Niru).

NOT YET WIRED: app/streamlit_app.py calls the profile, map and priority panels but has no hook
for this one. Unit B needs one line in the shell:

    fn = _panel("validation")
    if fn: fn()

Every number here is read from a file a real run wrote. If no run exists, this panel says so
rather than showing a placeholder -- an empty validation panel is honest, a fabricated one ends us.
"""
from __future__ import annotations

import os
import re

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from oceanembed import config

LOG_PATH = os.path.join(config.ROOT, "docs", "EXPERIMENT_LOG.md")


def _parse_experiment_log(path: str | None = None) -> list[dict]:
    """Pull logged runs out of EXPERIMENT_LOG.md. Returns [] if the file has none.

    Parses rather than recomputes on purpose: the panel must show what was actually recorded,
    so it cannot drift from the log the team reviews.
    """
    # Resolved at CALL time, not def time: a default argument would bind LOG_PATH once at
    # import and silently ignore any later override, which made this panel untestable.
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []

    runs: list[dict] = []
    current: dict | None = None
    for line in open(path, encoding="utf-8"):
        header = re.match(r"^##\s+(\S+)\s+(\d{4}-\d{2}-\d{2}[^\n]*)", line)
        if header:
            current = {"id": header.group(1), "when": header.group(2).strip(), "metrics": {}}
            runs.append(current)
            continue
        if current is None:
            continue
        if line.lower().startswith("model:") or line.lower().startswith("models:"):
            current["model"] = line.split(":", 1)[1].strip()
        if "dataset" in line.lower():
            m = re.search(r"dataset[^:]*:\s*([^|]+)", line, re.I)
            if m:
                current["dataset"] = m.group(1).strip()
        for key in ("RMSE", "MAE", "R2", "skill_vs_clim"):
            m = re.search(rf"{key}\s*=\s*([+-]?\d*\.?\d+)", line)
            if m:
                current["metrics"][key] = float(m.group(1))
    return [r for r in runs if r.get("metrics")]


def _looks_synthetic(run: dict) -> bool:
    return "synth" in str(run.get("dataset", "")).lower() or "synth" in str(run.get("model", "")).lower()


def render(metrics: dict | None = None, argo_df=None) -> None:
    st.subheader("Validation")

    if metrics is not None:
        _render_metrics_dict(metrics)
        return

    runs = _parse_experiment_log()
    if not runs:
        st.info(
            "No validation run has been logged yet. Numbers appear here once "
            "`docs/EXPERIMENT_LOG.md` contains a run — this panel never invents them."
        )
        return

    latest = runs[-1]
    if _looks_synthetic(latest):
        st.error(
            "⚠️ **The most recent logged run used SYNTHETIC data.** These figures describe the "
            "pipeline, not real ocean performance, and must not be quoted as results.",
            icon="⚠️",
        )

    st.caption(f"Latest logged run: `{latest['id']}` · {latest['when']}"
               + (f" · {latest.get('dataset', '')}" if latest.get("dataset") else ""))

    m = latest["metrics"]
    cols = st.columns(4)
    for col, key, fmt, help_text in [
        (cols[0], "RMSE", "{:.4f}", "Root-mean-square error, °C. Lower is better."),
        (cols[1], "MAE", "{:.4f}", "Mean absolute error, °C."),
        (cols[2], "skill_vs_clim", "{:+.4f}",
         "1 − RMSE_model/RMSE_climatology. Must be > 0 for the model to be worth anything."),
        (cols[3], "R2", "{:.4f}",
         "POOLED R² — inflated by the depth gradient; climatology alone scores ~0.95. "
         "Quote skill_vs_clim instead. See docs/VALIDATION_PROTOCOL.md."),
    ]:
        if key in m:
            col.metric(key, fmt.format(m[key]), help=help_text)

    if "R2" in m and m["R2"] > 0.9:
        st.caption(
            f"⚠️ R² = {m['R2']:.4f} looks near-perfect but sits on a floor of about 0.95 that "
            "**climatology alone already reaches** — pooled R² is dominated by the surface-to-deep "
            "temperature gradient. The honest headline is `skill_vs_clim`."
        )

    if len(runs) > 1:
        with st.expander(f"All {len(runs)} logged runs"):
            st.dataframe(
                pd.DataFrame([{"run": r["id"], "when": r["when"],
                               "dataset": r.get("dataset", ""), **r["metrics"]} for r in runs]),
                hide_index=True, width='stretch')


def _render_metrics_dict(m: dict) -> None:
    """Render a compute_metrics() dict directly, when a caller has one in hand."""
    cols = st.columns(3)
    cols[0].metric("RMSE (°C)", f"{m.get('rmse', float('nan')):.4f}")
    cols[1].metric("MAE (°C)", f"{m.get('mae', float('nan')):.4f}")
    skill = m.get("skill_vs_clim")
    cols[2].metric("skill vs climatology",
                   "n/a" if skill is None else f"{skill:+.4f}",
                   help="Must be > 0 for the model to beat the baseline.")

    by_depth = m.get("rmse_by_depth")
    if by_depth:
        df = pd.DataFrame({"depth": config.DEPTHS[: len(by_depth)],
                           "rmse": np.asarray(by_depth, dtype="float32")})
        if m.get("r2_by_depth"):
            df["r2"] = np.asarray(m["r2_by_depth"][: len(df)], dtype="float32")

        st.altair_chart(
            alt.Chart(df).mark_bar(color="#1f77b4").encode(
                x=alt.X("rmse:Q", title="RMSE (°C)"),
                y=alt.Y("depth:O", title="Depth (m)", sort=None),
                tooltip=[alt.Tooltip("depth:O", title="depth (m)"),
                         alt.Tooltip("rmse:Q", format=".4f")],
            ).properties(height=320),
            width='stretch')
        st.caption("Error usually grows with depth — surface observations constrain deep "
                   "temperature less. We report that openly rather than hiding it.")
        st.dataframe(df, hide_index=True, width='stretch')
