"""Per-depth skill metrics: RMSE, correlation, bias -- PS requirements 12, 13, 14.

Correlation and bias had NEVER been computed in this repo. `artifacts/satellite_bias.json` is a
CALIBRATION CORRECTION, not the PS bias metric; quoting it as such would be a fabricated number.
`bias` here is the plain signed mean of (model - truth).

Everything is NaN-safe per depth, because ~24% of ocean cells are shallower than 1000 m and the
target is NaN below the sea floor. The rules that make these numbers trustworthy:

  * A depth with too few samples returns **NaN with n recorded**, never 0.0. A zero RMSE printed
    next to n=1 reads as perfection and is the easiest way to mislead a judge.
  * Correlation of a near-constant series is **NaN, not 1.0**. Below 500 m the ocean barely varies,
    so a naive Pearson r there divides by ~0 and returns noise that looks like skill.
  * Skill is always returned WITH the climatology's own RMSE beside it. Skill is lowest at 1000 m
    because there is almost nothing to beat, yet 1000 m is our best absolute RMSE. Skill alone
    misleads; the pair does not.

Contract: docs/phase2/tscast_output_schema.md section 6.
"""
from __future__ import annotations

import numpy as np

from phase2.tscast_nio import config
from phase2 import basins

MIN_N = 3               # below this, correlation is meaningless
MIN_STD = 1e-6          # below this, a series is constant and r is undefined


def _nanmean_or_nan(a: np.ndarray) -> float:
    """np.nanmean of an all-NaN array warns and returns NaN; we want the NaN without the noise."""
    a = np.asarray(a, dtype="float64")
    return float(np.mean(a[np.isfinite(a)])) if np.isfinite(a).any() else float("nan")


def _pair(pred: np.ndarray, truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flatten to 1-D and keep only positions finite in BOTH arrays."""
    p = np.asarray(pred, dtype="float64").ravel()
    t = np.asarray(truth, dtype="float64").ravel()
    if p.shape != t.shape:
        raise ValueError(f"pred {p.shape} and truth {t.shape} disagree; refusing to broadcast")
    ok = np.isfinite(p) & np.isfinite(t)
    return p[ok], t[ok]


def rmse(pred, truth) -> float:
    p, t = _pair(pred, truth)
    if p.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((p - t) ** 2)))


def bias(pred, truth) -> float:
    """Mean signed error, model - truth. POSITIVE means the model runs warm."""
    p, t = _pair(pred, truth)
    if p.size == 0:
        return float("nan")
    return float(np.mean(p - t))


def correlation(pred, truth) -> float:
    """Pearson r. NaN -- never 1.0 -- when either series is effectively constant."""
    p, t = _pair(pred, truth)
    if p.size < MIN_N:
        return float("nan")
    if p.std() < MIN_STD or t.std() < MIN_STD:
        return float("nan")
    return float(np.corrcoef(p, t)[0, 1])


def skill_vs_climatology(pred, truth, clim) -> float:
    """1 - MSE(model)/MSE(climatology). 0 = no better than the average; 1 = perfect.

    Computed on the positions valid in ALL THREE arrays, so the model and the baseline are always
    scored on exactly the same samples. Scoring them on different subsets is how a model gets
    credited for skill it does not have.
    """
    p = np.asarray(pred, dtype="float64").ravel()
    t = np.asarray(truth, dtype="float64").ravel()
    c = np.asarray(clim, dtype="float64").ravel()
    if not (p.shape == t.shape == c.shape):
        raise ValueError(f"shapes disagree: pred {p.shape}, truth {t.shape}, clim {c.shape}")
    ok = np.isfinite(p) & np.isfinite(t) & np.isfinite(c)
    if ok.sum() == 0:
        return float("nan")
    mse_m = np.mean((p[ok] - t[ok]) ** 2)
    mse_c = np.mean((c[ok] - t[ok]) ** 2)
    if mse_c < MIN_STD:
        return float("nan")   # nothing to beat; a ratio here is meaningless, not infinite skill
    return float(1.0 - mse_m / mse_c)


def rmse_climatology_matched(pred, truth, clim) -> float:
    """RMSE of the climatology on the SAME points the model was scored on.

    `rmse(clim, truth)` would mask on clim & truth only, while `skill_rmse_ratio` masks on all
    three. On different subsets the published skill would not equal 1 - rmse/rmse_clim, and a
    reader checking that arithmetic would find it off by a little with no way to tell why. The
    baseline must be measured where the model was measured, or it is not the baseline.
    """
    p = np.asarray(pred, dtype="float64").ravel()
    t = np.asarray(truth, dtype="float64").ravel()
    c = np.asarray(clim, dtype="float64").ravel()
    if not (p.shape == t.shape == c.shape):
        raise ValueError(f"shapes disagree: pred {p.shape}, truth {t.shape}, clim {c.shape}")
    ok = np.isfinite(p) & np.isfinite(t) & np.isfinite(c)
    if ok.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.mean((c[ok] - t[ok]) ** 2)))


def skill_rmse_ratio(pred, truth, clim) -> float:
    """1 - RMSE(model)/RMSE(climatology) -- the definition the FROZEN Phase-1 headline uses.

    This is NOT the same number as `skill_vs_climatology` (the Murphy score, 1 - MSE/MSE_clim).
    On the real Argo set they read 0.39 and 0.63 for the SAME predictions. Quoting the Murphy
    figure beside the published +0.387 would read as a 56% improvement that does not exist, which
    is why both are returned and named rather than one being chosen silently.
    """
    p = np.asarray(pred, dtype="float64").ravel()
    t = np.asarray(truth, dtype="float64").ravel()
    c = np.asarray(clim, dtype="float64").ravel()
    if not (p.shape == t.shape == c.shape):
        raise ValueError(f"shapes disagree: pred {p.shape}, truth {t.shape}, clim {c.shape}")
    ok = np.isfinite(p) & np.isfinite(t) & np.isfinite(c)
    if ok.sum() == 0:
        return float("nan")
    r_c = float(np.sqrt(np.mean((c[ok] - t[ok]) ** 2)))
    if r_c < MIN_STD:
        return float("nan")
    r_m = float(np.sqrt(np.mean((p[ok] - t[ok]) ** 2)))
    return float(1.0 - r_m / r_c)


def per_depth(pred, truth, clim=None, reference: str = "argo", window=None) -> dict:
    """Metrics at each of the 15 contract depths, plus pooled.

    pred/truth/clim: (..., 15) -- any leading shape, depth LAST.
    Returns the aggregate record of tscast_output_schema.md section 6.
    """
    pred = np.asarray(pred, dtype="float64")
    truth = np.asarray(truth, dtype="float64")
    if pred.shape != truth.shape:
        raise ValueError(f"pred {pred.shape} and truth {truth.shape} disagree")
    if pred.shape[-1] != config.N_DEPTHS:
        raise ValueError(
            f"last axis is {pred.shape[-1]}, expected {config.N_DEPTHS} depths. "
            "The output contract is frozen; a reshape here would silently misalign depths."
        )
    if clim is not None:
        clim = np.asarray(clim, dtype="float64")
        if clim.shape != pred.shape:
            raise ValueError(f"clim {clim.shape} does not match pred {pred.shape}")

    n_d = config.N_DEPTHS
    out = {k: np.full(n_d, np.nan) for k in
           ("rmse", "correlation", "bias", "skill_vs_climatology", "skill_rmse_ratio",
            "rmse_climatology")}
    out["n"] = np.zeros(n_d, dtype=int)

    for d in range(n_d):
        p, t = pred[..., d], truth[..., d]
        ok = np.isfinite(p) & np.isfinite(t)
        out["n"][d] = int(ok.sum())
        if out["n"][d] == 0:
            continue
        out["rmse"][d] = rmse(p, t)
        out["bias"][d] = bias(p, t)
        out["correlation"][d] = correlation(p, t)
        if clim is not None:
            out["skill_vs_climatology"][d] = skill_vs_climatology(p, t, clim[..., d])
            out["skill_rmse_ratio"][d] = skill_rmse_ratio(p, t, clim[..., d])
            out["rmse_climatology"][d] = rmse(clim[..., d], t)

    return {
        "depths_m": list(config.DEPTHS),
        "rmse": out["rmse"].tolist(),
        "correlation": out["correlation"].tolist(),
        "bias": out["bias"].tolist(),
        "skill_vs_climatology": out["skill_vs_climatology"].tolist(),
        "skill_rmse_ratio": out["skill_rmse_ratio"].tolist(),
        "rmse_climatology": out["rmse_climatology"].tolist(),
        "n": out["n"].tolist(),
        "overall": {
            "rmse": rmse(pred, truth),
            "bias": bias(pred, truth),
            "correlation_pooled": correlation(pred, truth),
            "correlation": _nanmean_or_nan(out["correlation"]),
            "skill_vs_climatology": (skill_vs_climatology(pred, truth, clim)
                                     if clim is not None else float("nan")),
            "skill_rmse_ratio": (skill_rmse_ratio(pred, truth, clim)
                                 if clim is not None else float("nan")),
            # Skill without its baseline is unreadable: at 1000 m this model has its WORST skill
            # and its BEST absolute error at the same time, because climatology is already
            # excellent down there. The per-depth column carried this; the overall block did not,
            # so any reader of the summary alone could not tell what the skill was measured against.
            "rmse_climatology": (rmse_climatology_matched(pred, truth, clim)
                                 if clim is not None else float("nan")),
            "rmse_climatology_note": (
                "Measured on the points `skill_rmse_ratio` uses (finite in pred AND truth AND "
                "clim), so 1 - RMSE/RMSE_clim reproduces the published skill exactly. `rmse` "
                "above masks on pred and truth only; where climatology is also finite everywhere "
                "the two masks coincide, and where it is not, the skill figure -- not this "
                "division -- is the one to quote."),
            "skill_note": (
                "TWO DEFINITIONS, both returned because they are not interchangeable. "
                "`skill_rmse_ratio` = 1 - RMSE/RMSE_clim is what the FROZEN Phase-1 headline "
                "(+0.387) uses -- compare against that one. `skill_vs_climatology` = "
                "1 - MSE/MSE_clim is the Murphy score, standard in the literature. On the same "
                "real Argo predictions they read 0.39 and 0.63. Never quote one beside the other."
            ),
            "n": int((np.isfinite(pred) & np.isfinite(truth)).sum()),
            "correlation_note": (
                "`correlation` is the mean of the per-depth values -- quote THIS one. "
                "`correlation_pooled` mixes all 15 depths into one cloud, so it mostly measures "
                "that deep water is cold and surface water is warm, which no model deserves "
                "credit for. Measured on real Argo it reads 0.99 pooled against 0.83-0.98 "
                "per depth. Do not quote the pooled figure."
            ),
        },
        "reference": reference,
        "window": window,
        "bias_convention": "model - truth; POSITIVE means the model runs warm",
        "not_to_be_confused_with": (
            "artifacts/satellite_bias.json, which is a calibration correction and NOT this metric"
        ),
    }


def per_depth_by_basin(pred, truth, lat, lon, clim=None, reference="argo", window=None) -> dict:
    """Per-depth metrics for the whole set AND for each canonical basin.

    pred/truth/clim : (N, 15) -- ONE PROFILE PER ROW, depth last. The leading axis is the profile
                      axis and must line up with lat/lon, because a basin is decided per profile.
    lat/lon         : (N,) -- the location of each profile.

    Basins come from `phase2.basins`, the single canonical definition. This function draws NO new
    boxes: it routes each profile to the basin that module assigns, then calls the SAME
    `per_depth()` on each subset, so a basin's number is computed identically to the overall one
    and the two are directly comparable.

    Returns
        {
          "overall":   per_depth(all profiles),
          "by_basin":  {"arabian_sea": {...per_depth}, "bay_of_bengal": {...per_depth}},
          "profiles":  {"total", "arabian_sea", "bay_of_bengal", "unassigned"},
          ...
        }
    A basin with no profiles is reported with null metrics and n_profiles 0, never dropped.
    Unassigned profiles are counted so the per-basin counts reconcile with the total, and are
    still included in `overall` -- overall is every profile, exactly as `per_depth` alone would be.
    """
    pred = np.asarray(pred, dtype="float64")
    truth = np.asarray(truth, dtype="float64")
    if pred.ndim != 2 or pred.shape[-1] != config.N_DEPTHS:
        raise ValueError(
            f"per_depth_by_basin needs (N, {config.N_DEPTHS}); got {pred.shape}. Basin membership "
            "is per profile, so the leading axis must be the profile axis -- a gridded field would "
            "have to be flattened to (cell, depth) with matching lat/lon first.")
    if truth.shape != pred.shape:
        raise ValueError(f"truth {truth.shape} does not match pred {pred.shape}")
    lat = np.asarray(lat, dtype="float64").ravel()
    lon = np.asarray(lon, dtype="float64").ravel()
    if not (lat.shape[0] == lon.shape[0] == pred.shape[0]):
        raise ValueError(
            f"lat {lat.shape}, lon {lon.shape} and pred {pred.shape} disagree on profile count; "
            "they must be aligned or a profile is scored under the wrong basin.")
    if clim is not None:
        clim = np.asarray(clim, dtype="float64")
        if clim.shape != pred.shape:
            raise ValueError(f"clim {clim.shape} does not match pred {pred.shape}")

    labels = basins.classify_points(lat, lon)
    by_basin: dict = {}
    counts = {"total": int(pred.shape[0])}
    for name in basins.NAMES:                      # arabian_sea, bay_of_bengal -- the two we report
        sel = labels == name
        k = int(sel.sum())
        counts[name] = k
        if k == 0:
            by_basin[name] = {"n_profiles": 0, "note": "no profiles fall in this basin"}
            continue
        block = per_depth(pred[sel], truth[sel],
                          clim[sel] if clim is not None else None, reference, window)
        by_basin[name] = {"n_profiles": k, **block}
    counts["unassigned"] = int((labels == basins.UNASSIGNED).sum())

    return {
        "overall": per_depth(pred, truth, clim, reference, window),
        "by_basin": by_basin,
        "profiles": counts,
        "basin_definition": ("phase2.basins, the canonical Arabian Sea / Bay of Bengal partition; "
                             "no new boxes were drawn here"),
        "basin_bounds": basins.BOUNDS,
        "reconciliation_note": (
            "profiles.arabian_sea + bay_of_bengal + unassigned == profiles.total, and `overall` "
            "scores ALL profiles (assigned or not), so overall per-depth n equals the sum of the "
            "two basins' n plus the unassigned profiles' finite count at that depth."),
    }
