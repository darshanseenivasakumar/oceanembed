"""Independent validation against REAL Argo profiles -- validation level L5.

OWNER: Unit C (Mitun+Niru).

This is the strongest check we have: Argo is a completely separate data source from the GLORYS
reanalysis the model trains on, so it cannot be gamed by anything in our pipeline.

TWO HONESTY GATES, both enforced in code rather than by memory:

1. **Never validate a synthetic-trained model against real Argo.** Comparing a model fitted to
   fake fields against genuine float measurements produces numbers that look like a result and
   mean nothing. `validate_against_argo()` refuses unless the model is real-trained, or the
   caller passes `allow_unverified=True` and accepts a loud SYNTHETIC label on every output.
   (Unit B raised this in docs/HANDOFF.md; it is exactly right.)

2. **Always report n per depth.** Argo floats rarely sample at exactly 0 m -- the shallowest bin
   typically holds only tens of observations against ~2,400 at every other depth. An RMSE at 0 m
   computed from 32 points sitting in a table next to one computed from 2,450 reads as equally
   solid unless n is on the same row.

We interpolate nothing and extrapolate nothing: NaN where a float did not sample.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from oceanembed import config
from oceanembed.utils import grids, io
from oceanembed.validation.metrics import compute_metrics

# Below this many matched observations, a per-depth number is reported but marked unreliable.
MIN_OBS_PER_DEPTH = 100


def model_provenance() -> tuple[str, str]:
    """(status, label) for what the current model was trained on: synthetic / real / unverified.

    Inferred from data/raw/ because the artifacts carry no provenance flag yet
    (docs/DECISIONS.md D-018). The fallback is 'unverified', never 'real' -- an absence of
    evidence must not be promoted into a claim.
    """
    raw = config.DATA_RAW
    if os.path.exists(os.path.join(raw, "synthetic_glorys.nc")):
        return "synthetic", "model trained on SYNTHETIC GLORYS"
    if os.path.isdir(raw) and any(f.endswith(".nc") for f in os.listdir(raw)):
        return "real", "model trained on real GLORYS"
    return "unverified", "model provenance UNVERIFIED (data/raw/ absent, no flag in artifacts)"


def load_argo(path_noext: str | None = None) -> pd.DataFrame:
    """Load artifacts/argo_test.{parquet|csv}. Raises with a regeneration hint if absent."""
    path_noext = path_noext or config.art("argo_test")
    try:
        df = io.load_table(path_noext)
    except Exception as exc:
        raise SystemExit(
            f"Could not load {path_noext}.(parquet|csv): {exc}\n"
            "Regenerate with:  python -m oceanembed.data.download_argo   (~5 min, no credentials)"
        ) from exc

    required = {"lat", "lon", "date", "depth_idx", "temp"}
    missing = required - set(df.columns)
    assert not missing, f"argo_test is missing columns {sorted(missing)}; see docs/DATA_CONTRACT.md"
    return df


def pivot_profiles(argo_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Long Argo rows -> one row per (lat, lon, date) and a (N, 11) temperature array.

    Cells a float never sampled stay NaN. Nothing is filled in.
    """
    df = argo_df.copy()
    df["depth_idx"] = df["depth_idx"].astype(int)
    assert df["depth_idx"].between(0, config.N_DEPTHS - 1).all(), (
        f"depth_idx must be 0..{config.N_DEPTHS - 1}"
    )

    wide = (df.pivot_table(index=["lat", "lon", "date"], columns="depth_idx",
                           values="temp", aggfunc="mean")
              .reindex(columns=range(config.N_DEPTHS)))
    keys = wide.reset_index()[["lat", "lon", "date"]]
    return keys, wide.to_numpy(dtype="float32")


def predict_at_argo_points(keys: pd.DataFrame, reconstruct_grid=None) -> np.ndarray:
    """(N, 11) model temperature at each Argo profile's cell and nearest available date.

    Grouped by date so we reconstruct each grid ONCE rather than once per profile -- the same
    numbers, but O(dates) instead of O(profiles).
    """
    if reconstruct_grid is None:
        from oceanembed.inference.predict import reconstruct_grid  # imported lazily

    out = np.full((len(keys), config.N_DEPTHS), np.nan, dtype="float32")
    for date, block in keys.groupby("date"):
        try:
            grid = reconstruct_grid(date, with_uncertainty=False)
        except Exception as exc:  # a date outside the model's range should skip, not abort
            print(f"  [skip] {date}: {type(exc).__name__}: {str(exc)[:70]}")
            continue

        temp = np.asarray(grid["temp"], dtype="float32")
        for pos, (_, row) in zip(block.index, block.iterrows()):
            i = grids.nearest_lat_index(float(row["lat"]))
            j = grids.nearest_lon_index(float(row["lon"]))
            out[pos] = temp[i, j, :]
    return out


def validate_against_argo(argo_df: pd.DataFrame | None = None, *,
                          allow_unverified: bool = False,
                          reconstruct_grid=None) -> dict:
    """Compare model predictions against real Argo profiles. Returns a metrics dict.

    Refuses to run against a synthetic-trained model unless allow_unverified=True, in which case
    every output is stamped SYNTHETIC / UNVERIFIED.
    """
    status, label = model_provenance()
    if status != "real" and not allow_unverified:
        raise SystemExit(
            f"REFUSING to validate: {label}.\n"
            "Comparing a synthetic-trained model against REAL Argo profiles produces numbers "
            "that look like a result and mean nothing.\n"
            "Sequence: real GLORYS download -> retrain -> then Argo validation.\n"
            "Pass allow_unverified=True only to exercise the code path; every output will be "
            "stamped SYNTHETIC and must never be quoted."
        )

    argo_df = load_argo() if argo_df is None else argo_df
    keys, y_true = pivot_profiles(argo_df)
    y_pred = predict_at_argo_points(keys, reconstruct_grid=reconstruct_grid)

    # A depth only counts where BOTH the float sampled and the model produced a value.
    matched = np.isfinite(y_true) & np.isfinite(y_pred)
    n_per_depth = matched.sum(axis=0)

    masked_true = np.where(matched, y_true, np.nan)
    masked_pred = np.where(matched, y_pred, np.nan)

    with np.errstate(invalid="ignore"):
        overall = compute_metrics(masked_true, masked_pred)
        bias = np.nanmean(masked_pred - masked_true, axis=0)

    return dict(
        provenance=status,
        provenance_label=label,
        is_publishable=(status == "real"),
        n_profiles=int(len(keys)),
        n_matched_total=int(matched.sum()),
        depths=list(config.DEPTHS),
        n_per_depth=[int(v) for v in n_per_depth],
        rmse_by_depth=overall["rmse_by_depth"],
        bias_by_depth=[float(v) for v in bias],
        rmse_overall=overall["rmse"],
        mae_overall=overall["mae"],
        unreliable_depths=[int(config.DEPTHS[k]) for k in range(config.N_DEPTHS)
                           if n_per_depth[k] < MIN_OBS_PER_DEPTH],
        min_obs_threshold=MIN_OBS_PER_DEPTH,
    )


def report(result: dict) -> str:
    """Human-readable summary. Leads with provenance so it cannot be skimmed past."""
    lines: list[str] = []
    if not result["is_publishable"]:
        lines += ["=" * 70,
                  f"  {result['provenance_label'].upper()}",
                  "  THESE NUMBERS ARE NOT A RESULT. Do not quote them.",
                  "=" * 70]

    lines += [
        f"Independent Argo validation — {result['n_profiles']} profiles, "
        f"{result['n_matched_total']} matched observations",
        f"  overall RMSE {result['rmse_overall']:.4f} °C · MAE {result['mae_overall']:.4f} °C",
        "",
        f"  {'depth':>7}{'n':>8}{'RMSE':>10}{'bias':>10}",
    ]
    for k, d in enumerate(result["depths"]):
        n = result["n_per_depth"][k]
        flag = "  ← too few obs" if n < result["min_obs_threshold"] else ""
        lines.append(f"  {d:>7}{n:>8}{result['rmse_by_depth'][k]:>10.4f}"
                     f"{result['bias_by_depth'][k]:>+10.4f}{flag}")

    if result["unreliable_depths"]:
        lines += ["",
                  f"  Depths with fewer than {result['min_obs_threshold']} matched observations: "
                  f"{result['unreliable_depths']} m.",
                  "  Argo floats rarely sample at exactly 0 m (shallowest is typically ~4–6 m) and we do",
                  "  NOT extrapolate upward. Validate at 10 m instead, or state surface extrapolation",
                  "  as an explicit assumption. Never silently extrapolate."]

    lines += ["",
              "  Error is expected to grow with depth — surface observations constrain deep",
              "  temperature less. Reporting that openly is a strength, not a weakness."]
    return "\n".join(lines)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Validate against independent Argo profiles")
    p.add_argument("--allow-unverified", action="store_true",
                   help="run even if the model is synthetic-trained; output is stamped SYNTHETIC")
    args = p.parse_args()
    print(report(validate_against_argo(allow_unverified=args.allow_unverified)))


if __name__ == "__main__":
    main()
