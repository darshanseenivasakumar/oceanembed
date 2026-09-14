"""Skill of a reconstruction at the temperature inversion, and the adopt/reject rule of E-INV-00.

Owner: Unit B (Darshan). Pure numpy. The contingency table is `mhw_field.compare_detection`, reused
so heatwave and inversion detection are scored by one piece of code.

WHAT IS SCORED
Per column (a grid cell on a day, or an Argo profile) the engine in `inversion.py` gives an inversion
AMPLITUDE. Thresholding it gives presence. Model presence against truth presence is a contingency
table (POD / FAR / CSI / frequency bias). Amplitude error is scored ONLY where the truth has an
inversion: a model that says 0 everywhere would otherwise look accurate on the 80 % of columns that
have nothing to detect. Depth error is scored only where BOTH have one, because "how deep is the
inversion the model did not draw" is not a number.

THE RULE (pre-registered, E-INV-00; do not edit after results exist)
A leg is ADOPTED against the control iff
  (a) the same three seeds exist on both sides;
  (b) its winter inversion CSI beats the control's on EVERY seed, and the mean gain exceeds the
      control's own seed standard deviation;
  (c) its headline RMSE (`seafloor_masked_v2`) is no worse than the control's by more than
      HEADLINE_TOLERANCE_DEGC, the seed spread A27 measured on the deliverable recipe.
Fewer than three seeds is NOT A RESULT. Anything else is REJECTED, with every failed clause named.
"""
from __future__ import annotations

import numpy as np

from phase2.derived import inversion as INV
from phase2.derived.mhw_field import compare_detection

ADOPTED = "ADOPTED"
REJECTED = "REJECTED"
NOT_A_RESULT = "NOT A RESULT"

#: The control's measured 3-seed RMSE spread (AGENT_SYNC A27: 0.9078 / 0.9047 / 0.9084).
HEADLINE_TOLERANCE_DEGC = 0.004
MIN_SEEDS = 3


def _valid_columns(model_amp, truth_amp, valid):
    m = np.asarray(model_amp, dtype="float64")
    t = np.asarray(truth_amp, dtype="float64")
    if m.shape != t.shape:
        raise ValueError(f"model {m.shape} and truth {t.shape} amplitudes must match")
    keep = np.isfinite(t)                       # a column without a truth value cannot be scored
    if valid is not None:
        keep &= np.broadcast_to(np.asarray(valid, dtype=bool), t.shape)
    return m, t, keep


def contingency(model_amp, truth_amp, *, threshold: float = INV.THRESHOLD_DEGC, valid=None) -> dict:
    """Presence contingency at `threshold`. A NaN MODEL amplitude counts as 'absent' -- a model that
    produced nothing where the truth has an inversion has missed it, and hiding that would flatter it.
    """
    m, t, keep = _valid_columns(model_amp, truth_amp, valid)
    out = compare_detection(INV.present(m, threshold=threshold), INV.present(t, threshold=threshold),
                            valid=keep)
    out["n"] = int(keep.sum())
    out["threshold"] = float(threshold)
    return out


def amplitude_stats(model_amp, truth_amp, *, threshold: float = INV.THRESHOLD_DEGC, valid=None) -> dict:
    """Bias and RMSE of the amplitude, over columns where the TRUTH has an inversion and the model
    returned a number. None (not 0) when there is nothing to score."""
    m, t, keep = _valid_columns(model_amp, truth_amp, valid)
    sel = keep & INV.present(t, threshold=threshold) & np.isfinite(m)
    n = int(sel.sum())
    if n == 0:
        return {"n": 0, "bias": None, "rmse": None, "mean_truth": None, "mean_model": None,
                "bias_fraction": None, "threshold": float(threshold)}
    d = m[sel] - t[sel]
    mean_truth = float(t[sel].mean())
    bias = float(d.mean())
    return {"n": n, "bias": bias, "rmse": float(np.sqrt(np.mean(d ** 2))),
            "mean_truth": mean_truth, "mean_model": float(m[sel].mean()),
            "bias_fraction": bias / mean_truth if mean_truth != 0 else None,
            "threshold": float(threshold)}


def depth_stats(model_depth, truth_depth, both_present) -> dict:
    """Depth-of-maximum error where both sides drew an inversion. MAE and bias in metres."""
    md = np.asarray(model_depth, dtype="float64")
    td = np.asarray(truth_depth, dtype="float64")
    sel = np.asarray(both_present, dtype=bool) & np.isfinite(md) & np.isfinite(td)
    n = int(sel.sum())
    if n == 0:
        return {"n": 0, "mae": None, "bias": None}
    d = md[sel] - td[sel]
    return {"n": n, "mae": float(np.abs(d).mean()), "bias": float(d.mean())}


def three_seed_summary(per_seed: dict) -> dict:
    """mean / sample-sd / spread over seeds; `complete` only with MIN_SEEDS finite values."""
    items = {int(k): v for k, v in per_seed.items() if v is not None and np.isfinite(v)}
    vals = np.array(list(items.values()), dtype="float64")
    n = int(vals.size)
    out = {"n": n, "complete": n >= MIN_SEEDS, "per_seed": items}
    if n == 0:
        return out | {"mean": None, "sd": None, "spread": None}
    out["mean"] = float(vals.mean())
    out["sd"] = float(vals.std(ddof=1)) if n > 1 else None
    out["spread"] = float(vals.max() - vals.min())
    return out


def adopt(leg: dict, control: dict) -> dict:
    """The E-INV-00 rule. `leg` and `control` map seed -> {"csi": float|None, "headline_rmse": float}."""
    seeds = sorted(set(int(s) for s in leg) & set(int(s) for s in control))
    reasons: list[str] = []
    detail: dict = {"seeds": seeds}
    if len(seeds) < MIN_SEEDS:
        return {"verdict": NOT_A_RESULT, "adopted": False,
                "reasons": [f"only {len(seeds)} seed(s) on both sides; the rule needs {MIN_SEEDS}"],
                "detail": detail}

    leg_csi = {s: leg[s].get("csi") for s in seeds}
    ctl_csi = {s: control[s].get("csi") for s in seeds}
    if any(v is None for v in list(leg_csi.values()) + list(ctl_csi.values())):
        return {"verdict": NOT_A_RESULT, "adopted": False,
                "reasons": ["a CSI is None (no truth-present columns) on at least one seed"],
                "detail": detail}

    worse = [s for s in seeds if not leg_csi[s] > ctl_csi[s]]
    if worse:
        reasons.append("CSI did not improve on every seed: " + ", ".join(
            f"seed {s} leg {leg_csi[s]:.4f} vs control {ctl_csi[s]:.4f}" for s in worse))

    ls, cs = three_seed_summary(leg_csi), three_seed_summary(ctl_csi)
    gain = ls["mean"] - cs["mean"]
    detail["csi_gain_mean"] = gain
    detail["control_csi_sd"] = cs["sd"]
    if not gain > cs["sd"]:
        reasons.append(f"mean CSI gain {gain:+.4f} is inside the control's seed noise (sd {cs['sd']:.4f})")

    lh = three_seed_summary({s: leg[s].get("headline_rmse") for s in seeds})
    ch = three_seed_summary({s: control[s].get("headline_rmse") for s in seeds})
    if not (lh["complete"] and ch["complete"]):
        return {"verdict": NOT_A_RESULT, "adopted": False,
                "reasons": ["headline RMSE missing on at least one seed"], "detail": detail}
    delta = lh["mean"] - ch["mean"]
    detail["headline_delta_mean"] = delta
    if delta > HEADLINE_TOLERANCE_DEGC:
        reasons.append(f"headline RMSE worse by {delta:+.4f} degC, beyond the {HEADLINE_TOLERANCE_DEGC} tolerance")

    verdict = ADOPTED if not reasons else REJECTED
    return {"verdict": verdict, "adopted": verdict == ADOPTED, "reasons": reasons, "detail": detail}
