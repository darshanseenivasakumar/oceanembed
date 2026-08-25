"""Day 3 verdict: does the MLP actually beat the LightGBM baseline, or do we ship LightGBM?

OWNER: Unit A (Arjhun).

TEAM_PLAN/UNIT_A_ARJHUN.md Day 3: "Tune until skill_vs_clim > 0. If MLP can't beat LightGBM,
SAY SO and we ship LightGBM -- that's an honest result." This module produces that statement,
so the choice is made by a command rather than by whoever happens to be talking.

scripts/run_slice.py compares MLP vs climatology only; it has no LightGBM arm. This adds the
third model so the comparison is three-way and the decision is defensible.

Usage:
    python -m oceanembed.train.compare_models            # real artifacts (X_test/y_test)
    python -m oceanembed.train.compare_models --fixtures # plumbing check before real data lands
"""
from __future__ import annotations

import argparse
import datetime as dt
import os

import numpy as np

from oceanembed import config
from oceanembed.train import _data
from oceanembed.validation.metrics import compute_metrics  # Unit C's -- consumed, not edited

# A verdict is only meaningful if the gap exceeds run-to-run noise. Below this relative margin
# we declare a TIE and ship the simpler model, rather than reading noise as a win.
TIE_MARGIN = 0.02  # 2% relative RMSE

def _climatology_baseline(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """Depth-wise train mean -- the floor every model must clear to have learned anything."""
    return np.repeat(y_train.mean(axis=0)[None, :], n_test, axis=0)


def compare(fixtures: bool = False, verbose: bool = True) -> dict:
    d = _data.load(fixtures=fixtures)
    y_test = d["y_test"]

    clim = _climatology_baseline(d["y_train"], len(y_test))
    preds: dict = {"climatology": clim}

    try:
        from oceanembed.models.lgbm_baseline import load_lgbm, predict_lgbm

        preds["lightgbm"] = predict_lgbm(load_lgbm(), d["X_test"])
    except Exception as exc:
        if verbose:
            print("[skip] LightGBM: " + type(exc).__name__ + ": " + str(exc)[:80])
            print("       run `python -m oceanembed.train.train_lgbm` first")

    try:
        from oceanembed.models.mlp_profile import load_mlp, predict_mlp

        preds["mlp"] = predict_mlp(load_mlp(config.art("mlp_model.pt")), d["X_test"])
    except Exception as exc:
        if verbose:
            print("[skip] MLP: " + type(exc).__name__ + ": " + str(exc)[:80])
            print("       run `python -m oceanembed.train.train_mlp` first")

    results = {name: compute_metrics(y_test, p, y_clim=clim) for name, p in preds.items()}
    out = dict(
        dataset=d["dataset"],
        provenance=d.get("provenance", "fixtures" if fixtures else "unverified"),
        split=d["split"],
        n_test=len(y_test),
        results=results,
        verdict=_verdict(results),
        fixtures=fixtures,
    )
    if verbose:
        _report(out)
    return out


def _verdict(results: dict) -> dict:
    """Pick a model -- and be explicit when the data cannot support a pick."""
    if "mlp" not in results or "lightgbm" not in results:
        have = [k for k in results if k != "climatology"]
        return dict(
            choice=have[0] if len(have) == 1 else None,
            reason="only one model available -- train both for a real comparison",
            conclusive=False,
        )

    mlp_rmse = results["mlp"]["rmse"]
    lgb_rmse = results["lightgbm"]["rmse"]
    rel = abs(mlp_rmse - lgb_rmse) / max(lgb_rmse, 1e-9)

    if rel < TIE_MARGIN:
        return dict(
            choice="lightgbm",
            conclusive=False,
            reason=(
                "TIE: MLP {:.4f} vs LightGBM {:.4f} degC differ by {:.1%}, under the {:.0%} "
                "noise margin. Ship the simpler model."
            ).format(mlp_rmse, lgb_rmse, rel, TIE_MARGIN),
        )
    if mlp_rmse < lgb_rmse:
        return dict(
            choice="mlp",
            conclusive=True,
            reason="MLP {:.4f} beats LightGBM {:.4f} degC by {:.1%}".format(mlp_rmse, lgb_rmse, rel),
        )
    return dict(
        choice="lightgbm",
        conclusive=True,
        reason=(
            "LightGBM {:.4f} beats MLP {:.4f} degC by {:.1%}. Ship LightGBM -- "
            "an honest result, not a failure."
        ).format(lgb_rmse, mlp_rmse, rel),
    )


def _report(out: dict) -> None:
    r = out["results"]
    print()
    print("=" * 68)
    print("MODEL COMPARISON   dataset: " + str(out["dataset"]))
    print("                   split  : " + str(out["split"]))
    print("                   n_test : " + str(out["n_test"]))
    print("=" * 68)
    print("  {:<14}{:>9}{:>9}{:>9}{:>16}".format("model", "RMSE", "MAE", "R2", "skill_vs_clim"))

    for name in ("climatology", "lightgbm", "mlp"):
        if name not in r:
            continue
        m = r[name]
        skill = m.get("skill_vs_clim")
        skill_s = "--" if (name == "climatology" or skill is None) else "{:+.3f}".format(skill)
        print("  {:<14}{:>9.4f}{:>9.4f}{:>9.4f}{:>16}".format(
            name, m["rmse"], m["mae"], m["r2"], skill_s))

    cols = [n for n in ("climatology", "lightgbm", "mlp") if n in r]
    if len(cols) > 1:
        print()
        print("  per-depth RMSE (degC)")
        print("  " + "{:>7}".format("depth") + "".join("{:>13}".format(c) for c in cols))
        for i, depth in enumerate(config.DEPTHS):
            row = "".join("{:>13.4f}".format(r[c]["rmse_by_depth"][i]) for c in cols)
            print("  " + "{:>7}".format(depth) + row)

    v = out["verdict"]
    print()
    print("-" * 68)
    print("  VERDICT: {}   ({})".format(
        str(v["choice"]).upper(), "conclusive" if v["conclusive"] else "NOT conclusive"))
    print("  " + v["reason"])
    print("-" * 68)

    if out["fixtures"]:
        print("  FIXTURES -- synthetic. This verifies the HARNESS, not the models.")
        print("  docs/DECISIONS.md D-013: both models saturate the 0.20 degC noise floor,")
        print("  so no verdict from fixtures can be meaningful. Re-run on real GLORYS.")


def log_to_experiment_log(out: dict) -> None:
    """Append to docs/EXPERIMENT_LOG.md in the template's format (Unit C owns the file)."""
    if out["fixtures"]:
        print("\n[NOT logged -- fixture runs are not experiments (docs/DECISIONS.md D-013)]")
        return

    r = out["results"]
    v = out["verdict"]
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Provenance goes in the HEADER, not buried in a field. Someone skimming headers months
    # later must not be able to mistake a synthetic run for a result (docs/DECISIONS.md D-018).
    prov = out.get("provenance", "unverified")
    tag = "" if prov == "real" else f"  [{prov.upper()} DATA -- NOT A RESULT]"

    lines = ["\n## model-comparison " + stamp + tag + "\n"]
    if prov != "real":
        lines.append(
            f"> WARNING: provenance is '{prov}'. {out['dataset']} "
            "These numbers describe the PIPELINE, not real ocean performance. Do not quote them.\n")
    lines.append(
        "models: {} | dataset: {} | split: {} | seed: {} | n_test: {}\n".format(
            ", ".join(r), out["dataset"], out["split"], config.SEED, out["n_test"]))
    for name, m in r.items():
        skill = m.get("skill_vs_clim")
        skill_s = "--" if skill is None else "{:+.4f}".format(skill)
        lines.append("metrics[{}]: RMSE={:.4f} MAE={:.4f} R2={:.4f} skill_vs_clim={}\n".format(
            name, m["rmse"], m["mae"], m["r2"], skill_s))
    lines.append("VERDICT: {} ({}) -- {}\n".format(
        v["choice"], "conclusive" if v["conclusive"] else "not conclusive", v["reason"]))

    with open(os.path.join(config.ROOT, "docs", "EXPERIMENT_LOG.md"), "a", encoding="utf-8") as fh:
        fh.writelines(lines)
    print("\n[logged to docs/EXPERIMENT_LOG.md]")


def main() -> None:
    p = argparse.ArgumentParser(description="Compare climatology vs LightGBM vs MLP")
    p.add_argument("--fixtures", action="store_true", help="verify the harness on synthetic fixtures")
    p.add_argument("--no-log", action="store_true", help="skip appending to EXPERIMENT_LOG.md")
    args = p.parse_args()

    out = compare(fixtures=args.fixtures)
    if not args.no_log:
        log_to_experiment_log(out)


if __name__ == "__main__":
    main()
