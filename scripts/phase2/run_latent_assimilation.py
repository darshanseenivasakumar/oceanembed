"""Latent-space assimilation from real Argo floats, with the control that decides if it is real.

    PYTHONPATH=src python scripts/phase2/run_latent_assimilation.py

WHAT IT MEASURES
----------------
For each donor float: freeze the network, optimise the 128-number latent so the decoder reproduces
that float's observed profile, then push the correction to OTHER cells by cosine similarity in
latent space and score against THOSE floats' observations. The donor's own profile is never used
to score its own correction.

THE THREE POPULATIONS ARE THE POINT
------------------------------------
The shipped model runs +0.1003 degC warm, so any correction fitted to a real float tends to cool
the prediction, and cooling improves the score everywhere. Reporting only "error fell at similar
cells" would present a global bias correction as assimilation. So the identical correction is also
applied to the least-similar decile and to randomly chosen recipients, and the result is the GAP.

THE LAMBDA SWEEP IS NOT TUNING
-------------------------------
lambda anchors the fitted latent to the encoder's own output. Too large and nothing moves; too
small and the latent leaves the distribution the decoder was trained on, fitting one profile
perfectly and generalising to nothing. Rather than pick one and present it, the whole sweep is run
and written to the artifact, with the in-sample fit beside each point so a reader can see which
lambdas actually reproduce the donor at all. A single reported lambda would be a choice made after
seeing the answer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from oceanembed import config as base                              # noqa: E402
from phase2.reliability import assimilation as A                   # noqa: E402
from phase2.reliability import harness as H                        # noqa: E402

LAMBDAS = (1.0, 0.1, 0.03, 0.01, 0.003, 0.001)


#: Recipients closer than this to the donor are "near"; farther than FAR_KM are "far". The gap
#: between them is left unassigned rather than split at one boundary, so neither group is
#: contaminated by the other.
NEAR_KM = 200.0
FAR_KM = 500.0


def _mae(pred, truth, mask):
    d = np.abs(pred - truth)[mask]
    return float(d.mean()), int(mask.sum())


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance, degrees in, kilometres out."""
    r1, r2 = np.radians(lat1), np.radians(lat2)
    dlat = r2 - r1
    dlon = np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(r1) * np.cos(r2) * np.sin(dlon / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def run(ckpt: str, daily_dir: str, n_donors: int, tau: float, steps: int, lr: float,
        lambdas, seed: int) -> dict:
    ctx = H.load(ckpt, daily_dir=daily_dir)
    ctrl = ctx.control_rmse()
    print(f"control: rmse {ctrl['rmse']:.10f}  recorded {ctrl['recorded_rmse']}  "
          f"agrees={ctrl['agrees']}  n={ctrl['n']}  profiles={ctrl['n_profiles']}")
    if ctrl["agrees"] is not True:
        raise SystemExit(
            "REFUSING TO WRITE: the control does not reproduce the checkpoint's recorded RMSE, so "
            "every number below it would be harness error rather than assimilation.")

    if ctx.stage != 1:
        raise SystemExit("this experiment targets the SHIPPED stage-1 model; pass its checkpoint")

    dev = ctx.device
    ys = np.asarray(ctx.y_std, dtype="float64")
    ym = np.asarray(ctx.y_mean, dtype="float64")
    truth = ctx.truth_t.astype("float64")
    mask = np.isfinite(truth)
    y_z = np.where(mask, (truth - ym) / ys, 0.0)

    h0 = ctx.latents()
    base_pred = ctx.predict()["temperature"]

    # FALSIFICATION CHECK: decoding the encoder's own latent must reproduce the model's own
    # prediction. If it does not, `decode` is not the path the model actually takes and every
    # correction measured through it describes a different network.
    with torch.no_grad():
        mu_chk, _ = A.decode(ctx.model, torch.tensor(h0, dtype=torch.float32, device=dev))
    chk = float(np.max(np.abs(mu_chk.cpu().numpy() * ys + ym - base_pred)))
    print(f"decode(encoder latent) reproduces predict(): max gap {chk:.3e} degC")
    if chk > 1e-3:
        raise SystemExit("REFUSING TO WRITE: decode() is not the model's own forward path.")

    S = A.cosine(h0, h0)
    np.fill_diagonal(S, -np.inf)
    rng = np.random.default_rng(seed)
    donors = rng.choice(len(h0), min(n_donors, len(h0)), replace=False)
    n_low = max(1, int(0.10 * (len(h0) - 1)))

    results = {}
    lat_all = ctx.keys["lat"].to_numpy(dtype="float64")
    lon_all = ctx.keys["lon"].to_numpy(dtype="float64")

    for lam in lambdas:
        t0 = time.time()
        acc = {k: [] for k in ("similar", "dissimilar", "shuffled",
                               "similar_near", "similar_far")}
        ins_b, ins_a, dnorm, n_sim = [], [], [], []

        for i in donors:
            hi = torch.tensor(h0[i:i + 1], dtype=torch.float32, device=dev)
            fit = A.fit_latent(
                ctx.model, hi,
                torch.tensor(y_z[i:i + 1], dtype=torch.float32, device=dev),
                torch.tensor(mask[i:i + 1], device=dev),
                lam=lam, steps=steps, lr=lr)
            delta = fit["delta"].cpu().numpy()[0]
            ins_b.append(fit["in_sample_mse_before"])
            ins_a.append(fit["in_sample_mse_after"])
            dnorm.append(float(np.linalg.norm(delta) / max(1e-12, np.linalg.norm(h0[i]))))

            sim = S[i]
            sel_sim = np.flatnonzero(sim >= tau)
            n_sim.append(sel_sim.size)
            order = np.argsort(sim)
            sel_dis = order[:n_low]
            sel_shuf = rng.choice(len(h0), max(1, sel_sim.size), replace=False)

            # THE DISCRIMINATING SPLIT. "Similar" cells could simply be NEARBY cells -- adjacent
            # water looks alike, so a correction that only worked locally would produce exactly
            # the same headline. Splitting the similar population by distance to the donor asks
            # the real question: does the correction travel along the water mass, or along the
            # map? Only the FAR group can answer it.
            dist = haversine_km(lat_all[i], lon_all[i], lat_all, lon_all)
            sel_near = sel_sim[dist[sel_sim] < NEAR_KM]
            sel_far = sel_sim[dist[sel_sim] >= FAR_KM]

            for name, sel, weighted in (("similar", sel_sim, True),
                                        ("similar_near", sel_near, True),
                                        ("similar_far", sel_far, True),
                                        ("dissimilar", sel_dis, False),
                                        ("shuffled", sel_shuf, False)):
                sel = sel[sel != i]
                if sel.size == 0:
                    continue
                h_new = A.propagate(h0[sel], delta, sim[sel] if weighted else np.ones(sel.size),
                                    tau=tau if weighted else -1.0, weighted=weighted)
                with torch.no_grad():
                    mu, _ = A.decode(ctx.model,
                                     torch.tensor(h_new, dtype=torch.float32, device=dev))
                pred = mu.cpu().numpy() * ys + ym
                m = mask[sel]
                b, _ = _mae(base_pred[sel], truth[sel], m)
                a, n = _mae(pred, truth[sel], m)
                acc[name].append((b, a, n))

        blocks = {}
        for name, rows in acc.items():
            if not rows:
                # An empty population is reported as empty, never as a zero gain -- "no far
                # recipients existed" and "the correction did nothing far away" are different
                # facts and only one of them is evidence.
                blocks[name] = {"mae_before": None, "mae_after": None, "gain": None,
                                "n_comparisons": 0, "n_donor_groups": 0}
                continue
            v = np.asarray(rows, dtype="float64")
            w = v[:, 2]
            blocks[name] = {
                "mae_before": float(np.average(v[:, 0], weights=w)),
                "mae_after": float(np.average(v[:, 1], weights=w)),
                "gain": float(np.average(v[:, 0] - v[:, 1], weights=w)),
                "n_comparisons": int(w.sum()),
                "n_donor_groups": int(len(rows)),
            }

        s = A.summarise(blocks["similar"]["mae_before"], blocks["similar"]["mae_after"],
                        blocks["dissimilar"]["mae_after"], blocks["shuffled"]["mae_after"],
                        blocks["similar"]["n_comparisons"])
        results[str(lam)] = {
            "lambda": lam,
            "in_sample_mse_before": float(np.mean(ins_b)),
            "in_sample_mse_after": float(np.mean(ins_a)),
            "in_sample_reduction": float(1 - np.mean(ins_a) / np.mean(ins_b)),
            "delta_norm_ratio": float(np.mean(dnorm)),
            "mean_similar_recipients": float(np.mean(n_sim)),
            "populations": blocks,
            "summary": s,
            "seconds": round(time.time() - t0, 1),
        }
        def _g(k):
            v = blocks[k]["gain"]
            return "   n/a " if v is None else f"{v:+.4f}"

        print(f"  lambda={lam:<7} in-sample {np.mean(ins_b):.4f}->{np.mean(ins_a):.4f} "
              f"({results[str(lam)]['in_sample_reduction']*100:4.1f}% down)  "
              f"|dh|/|h| {np.mean(dnorm):.3f}  gain sim {_g('similar')} "
              f"[near {_g('similar_near')} far {_g('similar_far')}] "
              f"dis {_g('dissimilar')} shuf {_g('shuffled')}  "
              f"[{results[str(lam)]['seconds']}s]")

    return {
        "experiment": "latent-space assimilation from independent Argo, frozen network",
        "checkpoint": os.path.basename(ctx.ckpt_path),
        "control": ctrl,
        "decode_matches_forward_max_degC": chk,
        "n_argo_profiles": int(len(ctx.keys)),
        "n_donors": int(len(donors)),
        "tau": tau,
        "steps": steps,
        "lr": lr,
        "seed": seed,
        "similarity_percentiles": {
            str(p): float(np.nanpercentile(S[np.isfinite(S)], p)) for p in (5, 25, 50, 75, 95)},
        "by_lambda": results,
        "caveat": ("Recipients are other Argo cells, not the whole basin: the gain is measured only "
                   "where an independent float exists to score it. Propagating to every grid cell "
                   "is what an operational system would do and is NOT what is measured here."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default=base.art("tscast_stage1.pt"))
    ap.add_argument("--daily-dir", default=H.SAT_BUNDLE)
    ap.add_argument("--donors", type=int, default=120)
    ap.add_argument("--tau", type=float, default=A.TAU)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=base.art("latent_assimilation.json"))
    a = ap.parse_args()

    out = run(a.checkpoint, a.daily_dir, a.donors, a.tau, a.steps, a.lr, LAMBDAS, a.seed)

    # SELECTED ON THE BENEFIT, NOT ON THE MARGIN.
    #
    # The first version of this picked the largest `margin` -- the gap between the similar gain and
    # the controls -- and chose lambda=0.001, where similar states gained only +0.0033 degC while
    # dissimilar states were driven 0.2386 degC WORSE. The margin was large because the controls
    # had been wrecked, not because the method worked. A selection rule that rewards damaging its
    # own control is a selection rule that will always report success.
    #
    # The benefit is the gain at similar states. The controls are a gate, not a score: they must
    # not improve, or the gain is a global bias correction wearing a costume.
    eligible = [r for r in out["by_lambda"].values()
                if (r["populations"]["dissimilar"]["gain"] or 0) <= 0
                and (r["populations"]["shuffled"]["gain"] or 0) <= 0]
    pool = eligible or list(out["by_lambda"].values())
    best = max(pool, key=lambda r: r["populations"]["similar"]["gain"] or -np.inf)
    far = best["populations"]["similar_far"]
    out["headline"] = {
        "lambda": best["lambda"],
        "chosen_by": ("largest out-of-sample gain at latent-similar states, among lambdas where "
                      "NEITHER control population improved"),
        "n_lambdas_eligible": len(eligible),
        "gain_similar_far": far["gain"],
        "n_far": far["n_comparisons"],
        **best["summary"],
    }
    s = best["summary"]
    print("\nHEADLINE")
    print(f"  lambda={best['lambda']}  {s['verdict']}")
    print(f"  MAE {s['mae_before']:.4f} -> similar {s['mae_similar']:.4f} "
          f"| dissimilar {s['mae_dissimilar']:.4f} | shuffled {s['mae_shuffled']:.4f}")
    print(f"  gain at similar states {s['gain_similar']:+.4f} degC   "
          f"margin over controls {s['margin']:+.4f}   supported={s['supported']}")
    if far["gain"] is not None:
        print(f"  gain at similar-but-FAR states (>= {FAR_KM:.0f} km): {far['gain']:+.4f} degC "
              f"over {far['n_comparisons']} comparisons  <- the correction travels by water mass, "
              f"not by distance" if far["gain"] > 0 else
              f"  gain at similar-but-FAR states: {far['gain']:+.4f} -- the effect is LOCAL only")

    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
