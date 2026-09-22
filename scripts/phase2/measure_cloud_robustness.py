"""Cloud-robustness harness: RMSE vs independent Argo as a function of input cloud cover.

WHY THIS EXISTS
"Low latency + cloud-robust" is the pitch. Latency we can measure (predict_field is 32 s on CPU;
field.py header). Cloud-robustness we have ASSERTED and never measured. The model already produces a
complete field under holes -- dataset.py z-scores then fills every missing pixel with 0.0 (the
channel mean, line ~194) -- so it never crashes on clouds. That is not the same as being RIGHT under
clouds: a model that quietly slides toward the channel mean as inputs vanish looks perfectly stable
while getting steadily more wrong. This script puts a NUMBER on that slide.

WHAT IT DOES
Punches spatially-correlated cloud holes into the satellite input channels at increasing coverage
(0, 20, 40, 60, 80 % of ocean pixels), re-scores the SAME independent-Argo comparison the headline
uses, and reports RMSE / skill / per-depth error as a curve. At coverage 0 it MUST reproduce the
shipped headline (~0.901 degC) -- that is the built-in sanity check; if it does not, the harness is
wrong before the curve means anything.

    python -m scripts.phase2.measure_cloud_robustness
    python -m scripts.phase2.measure_cloud_robustness --coverages 0 0.3 0.6 --channels sst sss

HONEST SCOPE (state the weakness, per team practice)
  * The shipped L4 inputs (OSTIA etc.) are ALREADY gap-filled, so real days rarely show raw holes.
    This is therefore a STRESS TEST of "what if the upstream gap-fill were absent / L3 holes reached
    us" -- an upper bound on cloud sensitivity, not a replay of observed cloud days. Named as such.
  * The comparison set (which Argo profiles, which truth) is FIXED across coverages -- only the model
    input changes -- so the curve is a controlled A/B on cloud cover and nothing else.
  * The cloud field is synthetic (correlated Gaussian, thresholded). It is reproducible (seeded) and
    its coverage is exact, but it is not a real cloud mask. Swap in a real MODIS/INSAT cloud flag
    later and the same harness scores it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                       # noqa: E402
from phase2.tscast_nio import dataset as D                  # noqa: E402
from phase2.tscast_nio import eval_argo as EA               # noqa: E402
from phase2.tscast_nio.inference import TSCastPredictor     # noqa: E402


def correlated_cloud_field(shape, rng, smooth: float = 4.0) -> np.ndarray:
    """A smooth (lat, lon) random field. High values will become 'cloudy'.

    White noise blurred with a Gaussian kernel gives spatially-correlated blobs -- clouds come in
    patches, not salt-and-pepper pixels, and a per-pixel coin flip would let the 17x17 patch always
    see enough clear neighbours to be trivially robust. `smooth` is the blob scale in grid cells
    (~0.25 deg each), so 4.0 is ~1 degree blobs.
    """
    from scipy.ndimage import gaussian_filter          # scipy is already a project dependency
    return gaussian_filter(rng.standard_normal(shape).astype("float32"), sigma=smooth, mode="nearest")


def cloud_masked_surface(surface, land_mask, coverage: float, channels_idx, rng,
                         smooth: float = 4.0) -> np.ndarray:
    """A COPY of `surface` with `coverage` of ocean pixels set to NaN in `channels_idx`, per day.

    An INDEPENDENT cloud field per time step (clouds move day to day), and the SAME field masks all
    listed channels on a given day -- a cloud that blocks the thermal sensor blocks everything the IR
    retrieval feeds at once. Coverage is measured over OCEAN pixels only (land is already NaN and
    means nothing to a cloud). NaN is exactly what a real gap looks like to dataset.py, which then
    mean-fills it -- so this exercises the real fill path, not a special case.
    """
    surf = np.asarray(surface, dtype="float32").copy()
    if coverage <= 0:
        return surf
    ocean = ~np.asarray(land_mask, dtype=bool)              # (lat, lon)
    n_t = surf.shape[0]
    for t in range(n_t):
        field = correlated_cloud_field(ocean.shape, rng, smooth)
        thr = np.quantile(field[ocean], 1.0 - coverage)     # top `coverage` of OCEAN cells
        cloudy = ocean & (field >= thr)                     # (lat, lon) bool
        for c in channels_idx:
            surf[t, :, :, c][cloudy] = np.nan
    return surf


def build_ds(predictor, surface) -> D.GriddedPatches:
    """A dataset over `surface` that is byte-for-byte the shipped one except for the pixels we hid.

    Reuses the predictor's OWN normalisation, window, patch size and mask-channel flag. Recomputing
    norm here would be a second definition of the inputs and could shift the score for a reason that
    has nothing to do with clouds -- exactly the producer/consumer drift eval_argo.py exists to kill.
    """
    return D.GriddedPatches(
        surface, predictor.data["temp"], predictor.data["times"],
        predictor.data["land_mask"], predictor.data["channels"],
        np.arange(len(predictor.data["times"])),
        norm=predictor.ds.norm, t_seq=predictor.ds.T_SEQ, p=predictor.ds.P,
        clim=predictor.clim, return_clim=True, mask_channels=predictor.ds.mask_channels)


def score(mu, truth, clim_at) -> dict:
    """Overall + per-depth RMSE and skill-vs-climatology, on the finite comparisons only.

    `truth` is already seafloor-masked by eval_argo.collocate, and it is IDENTICAL across coverages,
    so the same cells are scored every time. Skill blends real-climatology and basin-mean-fill cells
    the same way the headline does -- kept identical on purpose so coverage 0 reproduces it.
    """
    m = np.isfinite(truth) & np.isfinite(mu)
    err2 = (mu - truth) ** 2
    clim2 = (clim_at - truth) ** 2
    rmse = float(np.sqrt(err2[m].mean()))
    rmse_clim = float(np.sqrt(clim2[m].mean()))
    per_depth = []
    for k in range(truth.shape[1]):
        mk = m[:, k]
        per_depth.append(None if not mk.any() else round(float(np.sqrt(err2[mk, k].mean())), 4))
    return {"rmse": round(rmse, 4), "rmse_clim": round(rmse_clim, 4),
            "skill_vs_clim": round(1.0 - rmse / rmse_clim, 4),
            "n_comparisons": int(m.sum()), "rmse_by_depth": per_depth}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coverages", type=float, nargs="+", default=[0.0, 0.2, 0.4, 0.6, 0.8],
                    help="fraction of OCEAN input pixels made missing, per day")
    ap.add_argument("--channels", type=str, nargs="+", default=["sst"],
                    help="input channels the clouds block (default: sst)")
    ap.add_argument("--smooth", type=float, default=4.0, help="cloud blob scale, in grid cells")
    ap.add_argument("--seed", type=int, default=0, help="reproducible cloud fields")
    ap.add_argument("--out", type=str, default=base.art("cloud_robustness.json"))
    args = ap.parse_args()

    predictor = TSCastPredictor()
    chans = [str(c) for c in predictor.data["channels"]]
    print(f"bundle channels: {chans}  |  input_source: {predictor.data.get('input_source')}")
    missing = [c for c in args.channels if c not in chans]
    if missing:
        raise SystemExit(f"--channels {missing} not in bundle channels {chans}")
    channels_idx = [chans.index(c) for c in args.channels]

    # The independent-Argo comparison, computed ONCE and reused for every coverage.
    tr_t, te_t = D.daily_split_indices(predictor.data["times"])
    keys, truth, keep, t_idx, la, lo, refusals = EA.collocate(predictor.data, te_t, data="daily")
    dev = next(predictor.model.parameters()).device

    rows = []
    for cov in args.coverages:
        rng = np.random.default_rng(args.seed + int(round(cov * 1000)))     # per-coverage, seeded
        surf = cloud_masked_surface(predictor.data["surface"], predictor.data["land_mask"],
                                    cov, channels_idx, rng, args.smooth)
        ds = build_ds(predictor, surf)
        mu, sigma, truth_kept, clim_at = EA.predict_at_argo(
            predictor.model, ds, keys, truth, keep, t_idx, la, lo, predictor.clim, dev)
        s = score(mu, truth_kept, clim_at)
        s["coverage"] = cov
        rows.append(s)
        print(f"  cloud {cov*100:4.0f}%  RMSE {s['rmse']:.4f} degC   "
              f"skill {s['skill_vs_clim']:+.3f}   n={s['n_comparisons']}")

    base_rmse = rows[0]["rmse"]
    for r in rows:
        r["rmse_delta_vs_clear"] = round(r["rmse"] - base_rmse, 4)

    out = {
        "what": "RMSE vs independent Argo as input cloud cover rises. Stress test (L4 inputs are "
                "already gap-filled): an UPPER BOUND on cloud sensitivity, not observed cloud days.",
        "clouded_channels": args.channels,
        "cloud_model": {"type": "correlated_gaussian_thresholded", "blob_scale_cells": args.smooth,
                        "coverage_is": "fraction of ocean input pixels missing per day",
                        "seed": args.seed, "independent_field_per_day": True},
        "scoring_protocol": refusals.get("scoring_protocol"),
        "n_refused_below_seafloor": refusals.get("n_refused_below_seafloor"),
        "curve": rows,
    }
    # Provenance, read from what the predictor already loaded -- no extra reconstruction.
    try:
        from phase2.tscast_nio import provenance as _prov
        out["checkpoint_sha256"] = _prov.checkpoint_sha256(predictor.checkpoint_path)
        out["code_commit"] = _prov.code_commit()
    except Exception:
        out["checkpoint_sha256"] = None

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {args.out}")
    print(f"SANITY: coverage 0 RMSE = {base_rmse:.4f} degC -- must match the shipped headline "
          f"(~0.901). If it does not, fix the harness before trusting the curve.")


if __name__ == "__main__":
    main()
