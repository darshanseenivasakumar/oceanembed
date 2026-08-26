"""The evidence behind every validation claim, assembled from measured artifacts only.

OWNER: Unit A (Arjhun). PHASE-2 ONLY. Reads baseline artifacts; modifies nothing.

WHAT THIS IS FOR
A judge trusts a team that shows its worst number. This module assembles the honest picture:
where the model beats climatology, where it does not, and -- the part nothing else in the repo
could answer -- how much of the remaining error is OURS versus inherited from the reanalysis we
trained on.

THE ONE NAMING TRAP, AND IT WOULD BE A SERIOUS ERROR IN A UI
`artifacts/argo_error_by_depth.json` has a key called `rmse_glorys`. That is **our model fed
GLORYS surface inputs** -- a model score, the model's own ceiling on its training source. It is
NOT the GLORYS reanalysis. Labelling it "GLORYS" on a panel would tell a judge we had measured the
reanalysis when we had not.

The reanalysis itself is measured in `artifacts/glorys_vs_argo.json`, written by
`scripts/phase2/glorys_vs_argo.py`. This module keeps the two apart by name everywhere:

    model_satellite   our model, real satellite inputs   <- the PS deliverable
    model_glorys      our model, GLORYS inputs           <- was `rmse_glorys` in the file
    reanalysis        GLORYS itself vs Argo              <- the training-truth ceiling

SKILL CONVENTION
skill = 1 - rmse_model / rmse_climatology. [VERIFIED] this reproduces the stored overall figure:
1 - 0.9638/1.5725 = 0.3871, matching `overall.satellite.skill_vs_clim`. It is NOT the
variance-based 1 - (rmse/rmse_clim)^2, and mixing the two would change every number on the panel.
"""
from __future__ import annotations

import json
import os

import numpy as np

from oceanembed import config  # baseline config: IMPORTED, never modified

ARGO_ERROR = os.path.join(config.ARTIFACTS, "argo_error_by_depth.json")
REANALYSIS_GAP = os.path.join(config.ARTIFACTS, "glorys_vs_argo.json")

#: Below this, the model's remaining error at that depth is within noise of the reanalysis's own
#: error, so it is inherited rather than earned. A convention for presentation, not a measurement;
#: it is exposed so a reviewer can move it.
CEILING_TOLERANCE_C = 0.05

#: A depth resting on too few Argo profiles must not set a headline. Depth 0 has only 12.
MIN_OBS_FOR_HEADLINE = 100


class MissingArtifactError(FileNotFoundError):
    """Raised with an actionable message rather than a bare path."""


def _load(path: str, how: str) -> dict:
    if not os.path.exists(path):
        raise MissingArtifactError(
            f"{path} is absent. It is gitignored and does not travel through git. {how}"
        )
    with open(path) as f:
        return json.load(f)


def skill(rmse_model, rmse_clim):
    """1 - rmse_model/rmse_clim, elementwise, NaN-safe. Positive means better than climatology."""
    m = np.asarray(rmse_model, dtype="float64")
    c = np.asarray(rmse_clim, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c > 0, 1.0 - m / c, np.nan)


def per_depth() -> dict:
    """Per-depth error and skill of the model against independent Argo.

    Returns arrays aligned to `config.DEPTHS`, plus the two interpretation flags the panel needs.
    """
    d = _load(ARGO_ERROR, "It ships in Unit B's data bundle (artifacts/).")
    depths = np.asarray(d["depths"], dtype="float64")
    if list(d["depths"]) != list(config.DEPTHS):
        raise ValueError(
            f"artifact depths {d['depths']} do not match config.DEPTHS {config.DEPTHS}"
        )

    sat = np.asarray(d["rmse_satellite"], dtype="float64")
    glo = np.asarray(d["rmse_glorys"], dtype="float64")     # MODEL fed GLORYS -- see module docstring
    clim = np.asarray(d["rmse_climatology"], dtype="float64")
    sk = skill(sat, clim)

    best_abs = int(np.nanargmin(sat))
    worst_skill = int(np.nanargmin(sk))

    return {
        "depths": depths,
        "rmse_model_satellite": sat,
        "rmse_model_glorys": glo,
        "rmse_climatology": clim,
        "skill_vs_climatology": sk,
        "n_obs": np.asarray(d["n_obs_per_depth"], dtype="int64"),
        "n_profiles": int(d["n_profiles"]),
        "max_days_offset": int(d["max_days_offset"]),
        "overall": d["overall"],
        "all_depths_positive_skill": bool(np.all(sk > 0)),
        "best_absolute_depth_m": float(depths[best_abs]),
        "best_absolute_rmse": float(sat[best_abs]),
        "worst_skill_depth_m": float(depths[worst_skill]),
        "worst_skill": float(sk[worst_skill]),
        # The counter-intuitive fact the panel must EXPLAIN rather than hide: the depth with the
        # weakest skill is also the depth with the best absolute error, because the deep ocean
        # barely varies so climatology is already excellent there.
        "worst_skill_is_also_best_absolute": bool(best_abs == worst_skill),
        "labels": {
            "rmse_model_satellite": "our model, real satellite inputs",
            "rmse_model_glorys": "our model, GLORYS inputs (NOT the reanalysis)",
            "rmse_climatology": "monthly climatology baseline",
        },
    }


def reanalysis_gap() -> dict:
    """How accurate is our TRAINING TRUTH? GLORYS reanalysis vs the same independent floats."""
    d = _load(REANALYSIS_GAP, "Generate it: python scripts/phase2/glorys_vs_argo.py")
    if list(d["depths"]) != list(config.DEPTHS):
        raise ValueError("glorys_vs_argo.json depths do not match config.DEPTHS")

    base = d["baseline"]
    rmse = np.asarray([np.nan if x is None else x for x in base["rmse"]], dtype="float64")
    mae = np.asarray([np.nan if x is None else x for x in base["mae"]], dtype="float64")
    bias = np.asarray([np.nan if x is None else x for x in base["bias"]], dtype="float64")
    depths = np.asarray(d["depths"], dtype="float64")

    worst = int(np.nanargmax(mae))
    return {
        "depths": depths,
        "rmse": rmse,
        "mae": mae,
        "bias": bias,
        "n": np.asarray(base["n"], dtype="int64"),
        "n_profiles": int(d["n_matched"]),
        "n_comparisons": int(base["n_comparisons"]),
        "overall_mae": float(base["overall_mae"]),
        "overall_rmse": float(base["overall_rmse"]),
        "worst_depth_m": float(depths[worst]),
        "worst_mae": float(mae[worst]),
        "bias_convention": d["bias_convention"],
        "collocation_distance_km": d["collocation_distance_km"],
        "tightening": {
            "time_only": d["tightened_time_only"],
            "distance_only": d["tightened_distance_only"],
            "both": d["tightened"],
        },
        "includes_regridding_error": bool(d.get("includes_regridding_error", True)),
    }


def inherited_vs_earned(tolerance_c: float = CEILING_TOLERANCE_C) -> dict:
    """Per depth: is our remaining error OURS, or inherited from the reanalysis we trained on?

    A model cannot be more accurate than the truth it was fit to. Comparing our RMSE against
    Argo with the reanalysis's OWN RMSE against the same floats separates the two:

        headroom = rmse_ours - rmse_reanalysis
          > tolerance   -> WE are the weak link at this depth. Genuine model error.
          <= tolerance  -> at the ceiling of the training truth. Error is largely inherited.
          < -tolerance  -> we BEAT the reanalysis (possible: it is smoother than reality).

    Both terms are measured against the SAME independent instrument at the same <=5-day
    tolerance. The profile counts differ slightly (the Phase-1 evaluation additionally drops
    profiles where reconstruction failed), which is reported rather than hidden.
    """
    ours = per_depth()
    rean = reanalysis_gap()
    headroom = ours["rmse_model_satellite"] - rean["rmse"]

    verdict = np.where(np.isnan(headroom), "unknown",
                       np.where(headroom > tolerance_c, "model-limited",
                                np.where(headroom < -tolerance_c, "beats-reanalysis", "at-ceiling")))

    return {
        "depths": ours["depths"],
        "rmse_ours": ours["rmse_model_satellite"],
        "rmse_reanalysis": rean["rmse"],
        "headroom_c": headroom,
        "verdict": verdict,
        "tolerance_c": float(tolerance_c),
        "n_profiles_ours": ours["n_profiles"],
        "n_profiles_reanalysis": rean["n_profiles"],
        "model_limited_depths": [float(z) for z, v in zip(ours["depths"], verdict)
                                 if v == "model-limited"],
        "at_ceiling_depths": [float(z) for z, v in zip(ours["depths"], verdict)
                              if v == "at-ceiling"],
        "beats_reanalysis_depths": [float(z) for z, v in zip(ours["depths"], verdict)
                                    if v == "beats-reanalysis"],
    }


MC_CALIBRATION = os.path.join(config.ARTIFACTS, "mc_calibration.json")


def mc_dropout_calibration() -> dict:
    """How badly does the model UNDER-state its own error, per depth?

        ratio = RMSE(prediction - argo) / RMS(MC-dropout sigma)      (1.0 == calibrated)

    Both terms are AGGREGATED PER DEPTH AND THEN DIVIDED, over exactly the profiles where Argo
    sampled that depth. Read, not recomputed: the measurement lives in
    `scripts/phase2/measure_mc_calibration.py` (Unit B) and is written to
    `artifacts/mc_calibration.json`, seeded so it is reproducible.

    READING IT HERE RATHER THAN RECOMPUTING IS DELIBERATE. An earlier version of this function
    computed its own ratio and was wrong by roughly 2x at the shallow end -- two implementations
    of one number is the D-014 failure (two loaders, one z-scored, a silent 20x error). There is
    now one measurement and one file.

    **This corrects D-016.** That decision was measured on FIXTURES and concluded the failure was
    "at depth", worst at 500 m. On real data the pattern INVERTS: 500-1000 m are the best-calibrated
    depths and the worst is the MIXED LAYER at 20-50 m. A panel that warns about deep water while
    staying quiet about 30 m points a reader away from the actual problem.

    Returns `available=False` with a reason rather than raising, so the page degrades to text.
    """
    if not os.path.exists(MC_CALIBRATION):
        return {"available": False,
                "why": f"{MC_CALIBRATION} is absent. Generate it: "
                       "python scripts/phase2/measure_mc_calibration.py"}
    with open(MC_CALIBRATION) as f:
        d = json.load(f)

    by = d["by_depth"]
    depths, ratio, rmse, sigma, n = [], [], [], [], []
    for z in config.DEPTHS:
        rec = by.get(str(z))
        depths.append(float(z))
        if rec is None:                       # a depth with too few floats to report honestly
            ratio.append(np.nan); rmse.append(np.nan); sigma.append(np.nan); n.append(0)
        else:
            ratio.append(float(rec["overconfidence"])); rmse.append(float(rec["rmse"]))
            sigma.append(float(rec["mc_sigma"])); n.append(int(rec["n"]))

    ratio = np.asarray(ratio); depths_a = np.asarray(depths)
    mixed = (depths_a >= 20) & (depths_a <= 50)
    deep = depths_a >= 500
    return {
        "available": True,
        "depths": depths_a,
        "ratio": ratio,
        "rmse": np.asarray(rmse),
        "sigma": np.asarray(sigma),
        "n": np.asarray(n),
        "n_profiles": int(d["n_profiles"]),
        "seed": int(d["seed"]),
        "source": d["source"],
        "method": d["method"],
        "worst_depth_m": float(d["worst"]["depth_m"]),
        "worst_factor": float(d["worst"]["ratio"]),
        "best_depth_m": float(d["best"]["depth_m"]),
        "best_factor": float(d["best"]["ratio"]),
        "mixed_layer_mean": float(d["mixed_layer_20_50m_mean"]),
        "deep_mean": float(d["deep_500m_plus_mean"]),
        "overconfident_everywhere": bool(d["overconfident_at_every_depth"]),
        "worse_in_mixed_layer_than_at_depth": bool(
            float(d["mixed_layer_20_50m_mean"]) > float(d["deep_500m_plus_mean"])),
        "not_reported_depths": [z for z, c in zip(depths, n) if c == 0],
    }


def baseline_availability() -> dict:
    """Which baselines can be shown against Argo HONESTLY, and which cannot.

    Climatology can: its per-depth RMSE against the same 879 profiles is in
    `argo_error_by_depth.json`, measured by the Phase-1 evaluation.

    **LightGBM cannot, on this machine.** [VERIFIED 2026-08-26]
      - `argo_error_by_depth.json` contains no LightGBM column; it was never scored against Argo.
      - `artifacts/lgbm_model.pkl` was DELIBERATELY EXCLUDED from Unit B's data bundle as
        regenerable, so the local file is whatever predated the bundle.
      - The local `X_train.npy` has 143514 rows while `provenance.json` records
        `n_train = 323028`, i.e. the local training inputs are NOT the real-data ones.
      - The checkpoint is a bare list of boosters (D-012) with no provenance stamp, so its
        training source cannot be read back from the file.

    Conclusion: quoting this checkpoint would either report a synthetic-trained model as a
    baseline, or claim provenance that cannot be verified. Both are forbidden here. The panel
    states the omission instead of hiding it.
    """
    x_train = os.path.join(config.ARTIFACTS, "X_train.npy")
    n_rows = None
    if os.path.exists(x_train):
        n_rows = int(np.load(x_train, mmap_mode="r").shape[0])
    n_expected = None
    prov = os.path.join(config.ARTIFACTS, "provenance.json")
    if os.path.exists(prov):
        with open(prov) as f:
            n_expected = json.load(f).get("n_train")

    lgbm_ok = n_rows is not None and n_expected is not None and n_rows == n_expected
    return {
        "climatology": {
            "available": os.path.exists(ARGO_ERROR),
            "why": "per-depth RMSE against the same 879 Argo profiles is in "
                   "argo_error_by_depth.json",
        },
        "lightgbm": {
            "available": bool(lgbm_ok),
            "why": ("shown" if lgbm_ok else
                    f"NOT SHOWN: local X_train.npy has {n_rows} rows but provenance.json records "
                    f"n_train={n_expected}, so the local LightGBM checkpoint was not trained on "
                    "the real data. It carries no provenance stamp, and it was excluded from the "
                    "data bundle as regenerable. Quoting it would be a fabricated baseline."),
            "how_to_unblock": "python scripts/prepare_dataset.py --real && "
                              "python -m oceanembed.train.train_lgbm, then score it against Argo",
            "local_x_train_rows": n_rows,
            "provenance_n_train": n_expected,
        },
    }


def known_weaknesses() -> list[dict]:
    """The limitations that must appear on the panel. Stating them is the point of the feature."""
    return [
        {
            "what": "MC-dropout uncertainty is overconfident EVERYWHERE, worst in the MIXED LAYER",
            "detail": "Measured against real Argo error at every reportable depth: the model "
                      "under-states its own error by 1.6x to 3.5x. The worst is 20-50 m (the "
                      "mixed layer); the "
                      "BEST-calibrated depths are 500-1000 m. D-016 originally concluded the "
                      "opposite -- 'overconfident at depth' -- from fixture data; the real-data "
                      "re-measurement inverted the pattern. Quote the MEASURED per-depth error "
                      "from argo_error_by_depth.json, never the model's own spread.",
            "evidence": "docs/DECISIONS.md D-016 (UPDATE 2026-08-26); reproduced live by "
                        "measured by scripts/phase2/measure_mc_calibration.py",
        },
        {
            "what": "Satellite covers 24 of 48 dates",
            "detail": "The satellite-driven result rests on half the record. The GLORYS-driven "
                      "column uses all 48 and is shown beside it for that reason.",
            "evidence": "data/processed/satellite_grids.npz -- 24 dates vs grids.npz 48",
        },
        {
            "what": "Argo validation is 2022 only",
            "detail": "Every independent number here comes from the test year. There is no "
                      "independent check on 2019-2021.",
            "evidence": "artifacts/argo_test.parquet date range",
        },
        {
            "what": "24% of ocean cells are shallower than 1000 m",
            "detail": "Bathymetry is masked everywhere; a deep value in a shallow cell is a bug, "
                      "not a prediction. Phase 1 shipped that bug once.",
            "evidence": "grids.npz valid_mask",
        },
    ]


def summary() -> dict:
    """Everything the page needs, in one call, so the UI holds no science of its own."""
    d = per_depth()
    return {
        "per_depth": d,
        "reanalysis_gap": reanalysis_gap(),
        "inherited_vs_earned": inherited_vs_earned(),
        "baseline_availability": baseline_availability(),
        "mc_dropout_calibration": mc_dropout_calibration(),
        "known_weaknesses": known_weaknesses(),
        "headline": {
            "rmse": d["overall"]["satellite"]["rmse"],
            "skill": d["overall"]["satellite"]["skill_vs_clim"],
            "n_profiles": d["n_profiles"],
            "against": "879 independent Argo profiles, satellite-driven",
            "do_not_quote": "the GLORYS-holdout figure -- same source as training",
        },
    }
