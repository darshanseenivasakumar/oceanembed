"""Everything the instrument reads. Cached once, shared by every feature.

OWNER: Unit A (Arjhun). NOT a page.

TWO RULES THIS FILE EXISTS TO ENFORCE

1. NO NUMBER IS TYPED. The headline scores are read from artifacts/frozen_manifest.json, which
   was written by the training run and states its own rule: "Every number in claims is read from
   the run's metrics JSON, never retyped." A UI that hardcodes 0.9078 is a UI that will still say
   0.9078 after the model changes. (It did: when the scoring protocol changed on 2026-09-07, every
   typed 0.9078 in app/ was stale -- the unmasked_v1 number -- and had to be found by a test.)

2. NO UNDERSCORE-PREFIXED CACHE ARGUMENTS. Streamlit silently DROPS any argument to a cached
   function whose name starts with an underscore. A cache key that is silently dropped is no
   cache key at all, and the result is a dashboard pinned to the first answer it ever computed --
   a bug this project has already been bitten by twice. Hence `version`, never `_version`.
"""
from __future__ import annotations

import json
import os
import sys

import streamlit as st

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from oceanembed import config as base          # noqa: E402
from phase2.tscast_nio import field_cache as FC  # noqa: E402

#: How many whole fields to keep. Each is roughly 12 MB, so six is about 72 MB -- enough that
#: flicking between features on one date never recomputes, small enough to leave the laptop
#: alone during a demo.
MAX_FIELDS = 6

DEPTHS = list(base.DEPTHS)


# ------------------------------------------------------------------------------- provenance
@st.cache_data(show_spinner=False)
def manifest() -> dict:
    p = base.art("frozen_manifest.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def claim(name: str = "deliverable_satellite") -> dict:
    """One scored claim from the frozen manifest, or {} if absent.

    `deliverable_satellite` is THE deliverable. The glorys_* claims are comparators and carry
    `deliverable: false` plus a role string saying why -- surface that role, never the bare
    number, or a screenshot of a comparator becomes the headline.
    """
    return (manifest().get("claims") or {}).get(name, {})


def headline() -> dict:
    """The four numbers on the top bar, formatted for display. Values from the manifest only."""
    c = claim()
    if not c:
        return {}
    rmse = c.get("overall_rmse")
    corr = c.get("overall_correlation")
    skill = c.get("overall_skill_vs_climatology")
    n = c.get("argo_profiles")
    return {
        "rmse": f"{rmse:.4f}" if rmse is not None else "—",
        "corr": f"{corr:.4f}" if corr is not None else "—",
        "skill": f"{skill * 100:.0f}%" if skill is not None else "—",
        "profiles": f"{n:,}" if n is not None else "—",
        "bias": f"{c.get('overall_bias'):+.4f}" if c.get("overall_bias") is not None else "—",
        "tag": c.get("tag") or c.get("run_tag") or "",
        "sha": (c.get("checkpoint_sha256") or "")[:12],
    }


@st.cache_data(show_spinner=False)
def calibration() -> dict:
    p = base.art("uncertainty_calibration.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def calibration_summary() -> dict:
    """Coverage before and after calibration, normalised for display.

    The artifact nests these under summary_before / summary_after; `method_used` names which of
    the two fitted methods was chosen ("coverage"), and the rejected one is kept beside it.

    cov2 is returned as a RANGE as well as a mean, deliberately: the mean alone (0.91) reads as
    "nearly calibrated", while the per-depth spread (0.80 to 0.96 against a 0.954 target) is the
    honest picture and is what this project requires be quoted.
    """
    c = calibration()
    if not c:
        return {}
    before, after = c.get("summary_before") or {}, c.get("summary_after") or {}
    r2 = after.get("cov2_range") or [None, None]
    r1 = after.get("cov1_range") or [None, None]
    return {
        "cov1": after.get("cov1_mean"), "cov2": after.get("cov2_mean"),
        "cov1_before": before.get("cov1_mean"), "cov2_before": before.get("cov2_mean"),
        "cov1_range": r1, "cov2_range": r2,
        "target1": after.get("target_cov1"), "target2": after.get("target_cov2"),
        "method": c.get("method_used"), "n_fit": c.get("n_fit_profiles"),
        "n_eval": c.get("n_eval_profiles"),
        "scales": c.get("scales") or {},
    }


# ------------------------------------------------------------------------------ the model
def version(stage: int = 1) -> str:
    """Cache key that moves when the shipped checkpoint or the code that loads it moves."""
    return FC.cache_version(stage=stage)


@st.cache_resource(show_spinner=False)
def _predictor(stage: int, version: str):
    return FC.get_predictor(stage=stage)


@st.cache_data(show_spinner=False)
def dates(stage: int, version: str) -> list[str]:
    return FC.available_dates(stage=stage, predictor=_predictor(stage, version))


@st.cache_data(show_spinner=False, max_entries=MAX_FIELDS)
def field(date_str: str, stage: int, version: str,
          keep: tuple = FC.DEFAULT_KEEP, device: str | None = None) -> dict:
    """One whole reconstructed field: (100, 240, 15) temperature plus sigma and masks.

    Roughly 32 s on CPU and 8 s on CUDA, measured -- artifacts/export_timing.json. Which is why
    it is cached on (date, stage, version, keep, device) and why a caller that only needs a
    profile should use `point` instead.
    """
    return FC.field_for(date_str, stage=stage, keep=keep, device=device,
                        predictor=_predictor(stage, version))


@st.cache_data(show_spinner=False, max_entries=128)
def point(lat: float, lon: float, date_str: str, stage: int, version: str) -> dict:
    return FC.reconstruct_point(lat, lon, date_str, stage=stage,
                                predictor=_predictor(stage, version))


def cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False
