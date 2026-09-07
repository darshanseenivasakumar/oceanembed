"""One loader for every novelty experiment. Owner: Unit A (Arjhun).

WHY THIS EXISTS
---------------
Three experiments -- the stability projection, the observability field and latent assimilation --
all need the same six things: the bundle, the train/test split with its embargo, the exact
normalisation the checkpoint was fitted under, the checkpoint itself, the independent-Argo
collocation, and a way to run the model at chosen cells.

`scripts/phase2/rescore_checkpoint.py` already does all six, correctly, and its output has been
checked against the recorded metrics. Writing that sequence a second, third and fourth time is how
this project produced an 8 degC dashboard error and a warm-surface report that was really a
missing variable. So it is written once, here, and the scripts import it.

THE CONTROL IS PART OF THE LOADER
---------------------------------
`Context.control_rmse()` re-scores the loaded checkpoint against independent Argo with nothing
applied. If that does not reproduce the number recorded beside the checkpoint, every result
measured downstream of it is harness error rather than science, and the calling script is expected
to refuse to write its artifact. This is the discipline `run_cloud_dropout.py` used, and it is the
only reason its counter-intuitive result could be believed.

NORMALISATION COMES FROM THE TRAIN SPLIT, NEVER FROM THE TEST SPLIT
-------------------------------------------------------------------
`ds_tr` is rebuilt for one reason: to recover `ds_tr.norm`, the channel statistics the weights were
fitted under. Recomputing them from the test data would change the input scaling as well as its
content, and the experiment would measure two things at once.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from oceanembed import config as base
from oceanembed.validation import validate_argo as VA
from phase2.tscast_nio import config as c2
from phase2.tscast_nio import dataset as D
from phase2.tscast_nio import eval_argo as EA
from phase2.tscast_nio import metrics as M
from phase2.tscast_nio.models.tscast import TSCastNIO, assert_architecture_matches

#: Maximum |model date - float date| for a collocation, in days. The project's working default,
#: the same one `rescore_checkpoint.py` and the trainer use.
MAX_DAYS = 5

#: Tolerance for the control check, in degC. The repo quotes its metrics at 4 dp.
CONTROL_TOL = 1e-4

SAT_BUNDLE = os.path.join("data", "processed", "daily_sat", "v001")


@dataclass
class Context:
    """Everything an experiment needs, loaded once."""
    model: TSCastNIO
    ck: dict
    ckpt_path: str
    stage: int
    device: str
    bundle: dict
    clim: np.ndarray
    ds_tr: D.GriddedPatches
    ds_te: D.GriddedPatches
    keys: pd.DataFrame          # kept Argo profiles: lat, lon, date
    truth_t: np.ndarray         # (N, 15) observed temperature, NaN where unsampled
    truth_s: np.ndarray | None  # (N, 15) observed salinity, or None if the table has none
    argo_idx: np.ndarray        # (N, 3) the (t, i, j) rows those profiles map to
    clim_at: np.ndarray         # (N, 15) climatology at each profile's cell and month
    _cache: dict = field(default_factory=dict)
    #: Which comparisons the collocation declined, and why (eval_argo.apply_seafloor_mask).
    refusals: dict = field(default_factory=dict)
    #: One flag per kept profile: True where its cell has a real climatology, not the fill.
    baseline_ok: np.ndarray | None = None
    scoring_protocol: str = EA.SCORING_PROTOCOL

    # ---------------------------------------------------------------- properties
    @property
    def y_mean(self):
        return self.ds_te.y_mean

    @property
    def y_std(self):
        return self.ds_te.y_std

    @property
    def s_mean(self):
        return getattr(self.ds_te, "s_mean", None)

    @property
    def s_std(self):
        return getattr(self.ds_te, "s_std", None)

    @property
    def channels(self) -> list[str]:
        return [str(x) for x in self.bundle["channels"]]

    # ---------------------------------------------------------------- running
    def loader(self, index, batch_size: int = 512):
        """A DataLoader over EXACTLY the (t, i, j) rows given, in order.

        `ds.index` is mutated and restored -- the same borrow-and-return `predict_field` does, and
        for the same reason: the dataset is shared and leaving it mutated silently changes what
        every later caller reads.
        """
        saved = self.ds_te.index
        try:
            self.ds_te.index = np.asarray(index)
            yield from DataLoader(self.ds_te, batch_size=batch_size, shuffle=False)
        finally:
            self.ds_te.index = saved

    def predict(self, index=None, batch_size: int = 512) -> dict:
        """Run the model at `index` (default: the Argo cells). Returns PHYSICAL units.

        Stage 1 -> temperature and sigma. Stage 2 -> those plus salinity and its sigma, each
        denormalised with ITS OWN statistics; scaling salinity with temperature's would be a units
        error nothing downstream could catch.
        """
        index = self.argo_idx if index is None else index
        mus, lvs, smus, slvs = [], [], [], []
        self.model.eval()
        with torch.no_grad():
            for batch in self.loader(index, batch_size):
                x, g, cp, mo = self._unpack(batch)
                out = self.model(x, g, cp, mo)
                mus.append(out[0].cpu().numpy())
                lvs.append(out[1].cpu().numpy())
                if self.stage == 2:
                    smus.append(out[2].cpu().numpy())
                    slvs.append(out[3].cpu().numpy())

        res = {
            "temperature": np.concatenate(mus) * self.y_std + self.y_mean,
            "sigma": np.sqrt(np.exp(np.concatenate(lvs))) * self.y_std,
        }
        if self.stage == 2:
            res["salinity"] = np.concatenate(smus) * self.s_std + self.s_mean
            res["sigma_salinity"] = np.sqrt(np.exp(np.concatenate(slvs))) * self.s_std
        return res

    def latents(self, index=None, batch_size: int = 512) -> np.ndarray:
        """The encoder's (N, latent) output -- the compact satellite embedding itself."""
        index = self.argo_idx if index is None else index
        hs = []
        self.model.eval()
        with torch.no_grad():
            for batch in self.loader(index, batch_size):
                x, g, _cp, _mo = self._unpack(batch)
                hs.append(self.model.encoder(x, g).cpu().numpy())
        return np.concatenate(hs)

    def _unpack(self, batch):
        """(x, x_geo, y, y_valid, latlon, clim, month) -> the four the model takes, on device."""
        x, g, _y, _v, _ll, cp, mo = batch[:7]
        return (x.to(self.device), g.to(self.device), cp.to(self.device), mo.to(self.device))

    # ---------------------------------------------------------------- the control
    def control_rmse(self) -> dict:
        """Score the checkpoint with nothing applied, and compare to what is recorded beside it.

        Returns {"rmse", "recorded", "agrees", "n", ...}. `recorded` is None when no metrics file
        sits next to the checkpoint, and `agrees` is then None -- which is a different thing from
        False and must not be reported as a pass.
        """
        if "control" in self._cache:
            return self._cache["control"]
        mu = self.predict()["temperature"]
        m = M.per_depth(mu, self.truth_t, clim=self.clim_at, reference="argo",
                        baseline_ok=self.baseline_ok)["overall"]

        # Compare against a record made under the SAME scoring protocol, or say there is none.
        # The training-run JSON of every checkpoint before 2026-09-07 is unmasked_v1; a re-score
        # under this protocol lives beside it as *_rescore_<protocol>.json. Comparing across
        # protocols would report a real difference as a harness error, or worse, hide one.
        recorded, recorded_from, recorded_protocol = None, None, None
        import json
        same = self.ckpt_path.replace(".pt", f"_rescore_{self.scoring_protocol}.json")
        training = self.ckpt_path.replace(".pt", "_metrics.json")
        for cand in (training, same):
            if not os.path.exists(cand):
                continue
            with open(cand, encoding="utf-8") as f:
                rec = json.load(f)
            proto = rec.get("scoring_protocol", EA.UNMASKED_PROTOCOL)
            if proto == self.scoring_protocol:
                recorded = rec["metrics"]["overall"]["rmse"]
                recorded_from, recorded_protocol = os.path.basename(cand), proto
                break
            recorded_protocol = recorded_protocol or proto

        out = {
            "rmse": float(m["rmse"]),
            "bias": float(m["bias"]),
            "correlation": float(m["correlation"]),
            "n": int(m["n"]),
            "n_profiles": int(len(self.keys)),
            "scoring_protocol": self.scoring_protocol,
            "refusals": dict(self.refusals),
            "recorded_rmse": recorded,
            "recorded_from": recorded_from,
            "recorded_protocol": recorded_protocol,
            "agrees": None if recorded is None else bool(abs(m["rmse"] - recorded) <= CONTROL_TOL),
            "tolerance": CONTROL_TOL,
            "note": (None if recorded is not None else
                     f"no record under {self.scoring_protocol}"
                     + (f"; the training JSON is {recorded_protocol}" if recorded_protocol else "")
                     + " -- run scripts/phase2/rescore_checkpoint.py to create one"),
        }
        self._cache["control"] = out
        return out

    def score(self, temperature) -> dict:
        """Per-depth + overall metrics for a temperature array shaped like `truth_t`."""
        return M.per_depth(temperature, self.truth_t, clim=self.clim_at, reference="argo",
                           baseline_ok=self.baseline_ok)


def _pivot_ts(df: pd.DataFrame):
    """Long Argo rows -> keys, temperature (N, 15), salinity (N, 15) or None.

    Deliberately mirrors `validate_argo.pivot_profiles` for the temperature half -- same index,
    same aggregation -- so the two cannot disagree. `tests/phase2/test_novelty_harness.py` asserts
    the temperature array is identical to what `pivot_profiles` returns on the same table.
    """
    df = df.copy()
    df["depth_idx"] = df["depth_idx"].astype(int)
    idx = ["lat", "lon", "date"]
    wide_t = (df.pivot_table(index=idx, columns="depth_idx", values="temp", aggfunc="mean")
                .reindex(columns=range(base.N_DEPTHS)))
    keys = wide_t.reset_index()[idx]
    t = wide_t.to_numpy(dtype="float32")

    s = None
    if "psal" in df.columns:
        wide_s = (df.pivot_table(index=idx, columns="depth_idx", values="psal", aggfunc="mean")
                    .reindex(columns=range(base.N_DEPTHS))
                    .reindex(wide_t.index))          # the SAME row order as temperature
        s = wide_s.to_numpy(dtype="float32")
    return keys, t, s


def load(checkpoint: str, daily_dir: str = SAT_BUNDLE, t_seq: int = 11,
         argo_table: str = "argo_daily_period.parquet", max_days: int = MAX_DAYS,
         train_samples: int = 60000, test_samples: int = 12000,
         device: str | None = None) -> Context:
    """Load a checkpoint and everything needed to experiment on it.

    `checkpoint` may be a bare tag ("sat_7ch_s42"), a filename, or a full path.
    """
    ckpt_path = checkpoint
    if not os.path.exists(ckpt_path):
        for cand in (base.art(checkpoint), base.art(f"{checkpoint}.pt"),
                     base.art(f"tscast_stage1_{checkpoint}.pt"),
                     base.art(f"tscast_stage2_{checkpoint}.pt")):
            if os.path.exists(cand):
                ckpt_path = cand
                break
        else:
            raise SystemExit(f"no checkpoint found for {checkpoint!r}")

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(ckpt_path, map_location=dev, weights_only=False)
    stage = int(ck.get("stage", 1))

    d = D.load_daily(daily_dir)
    tr_t, te_t = D.daily_split_indices(d["times"])
    tr_t = D.embargo_indices(tr_t, t_seq, int(te_t.min()) if len(te_t) else None)
    clim = np.load(base.art("climatology.npy"))

    want_s = stage == 2
    common = dict(t_seq=t_seq, clim=clim, return_clim=True,
                  mask_channels=bool(ck.get("mask_channels", False)))    # audit #13
    if want_s:
        common["salinity"] = d.get("salinity")
        common["return_salinity"] = True
    ds_tr = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             tr_t, max_samples=train_samples, seed=base.SEED, **common)
    ds_te = D.GriddedPatches(d["surface"], d["temp"], d["times"], d["land_mask"], d["channels"],
                             te_t, norm=ds_tr.norm, max_samples=test_samples,
                             seed=base.SEED + 1, **common)

    # THE MODEL'S t_seq IS NOT THE DATA'S t_seq, AND CONFUSING THEM COSTS 0.022 degC SILENTLY.
    #
    # `built_t_seq` is the value the encoder was CONSTRUCTED with; it sets the temporal pooling
    # stride in CNN3D (t_seq=1 -> no temporal pooling, t_seq=11 -> [2,2,2]). The shipped
    # checkpoint records T_SEQ=11 -- an 11-day input window -- and built_t_seq=1, so it sees all
    # eleven days but pools them only in the final adaptive average.
    #
    # Both constructions accept the same state_dict without complaint, because AdaptiveAvgPool3d
    # makes every parameter shape identical either way. Building at t_seq=11 and scoring gave
    # 0.9297 degC against the recorded 0.9078 -- a plausible number, from the wrong architecture,
    # with no error raised anywhere. Found here by `control_rmse()` refusing to agree.
    built = int(ck.get("built_t_seq", ck.get("T_SEQ", t_seq)))
    model = TSCastNIO(ck.get("encoder", "cnn3d"),
                      D.input_channels(d["channels"], bool(ck.get("mask_channels", False))),
                      t_seq=built, p=c2.P,
                      latent=c2.LATENT_DIM, residual=bool(ck.get("residual", True)),
                      unet_channels=tuple(c2.UNET_CHANNELS),
                      decoder=ck.get("decoder", "simple"), stage=stage).to(dev)
    assert_architecture_matches(model, ck, where=f"harness.load({os.path.basename(ckpt_path)})")
    model.load_state_dict(ck["state_dict"])
    model.eval()

    # ---- independent-Argo collocation, the trainer's own rule ----
    argo_df = pd.read_parquet(argo_table if os.path.exists(argo_table) else base.art(argo_table))
    keys, truth_t, truth_s = _pivot_ts(argo_df)
    all_times = np.asarray(d["times"], dtype="datetime64[D]")
    dts = pd.to_datetime(keys["date"].values).values.astype("datetime64[D]")
    offs = np.array([np.abs((all_times[te_t] - x).astype("timedelta64[D]").astype(int))
                     for x in dts])
    keep = offs.min(axis=1) <= max_days
    t_idx = np.asarray(te_t)[offs.argmin(axis=1)]
    la, lo = D.cell_index(keys["lat"].values, keys["lon"].values)

    keys = keys[keep].reset_index(drop=True)
    # Decline what the product declines (eval_argo.apply_seafloor_mask), and remember how much.
    truth_t, refusals = EA.apply_seafloor_mask(truth_t[keep], la[keep], lo[keep],
                                               d["valid_mask"], d["land_mask"])
    if truth_s is not None:
        water = EA.seafloor_mask(la[keep], lo[keep], d["valid_mask"], d["land_mask"])
        truth_s = np.where(water, np.asarray(truth_s[keep], dtype="float64"), np.nan)
    baseline_ok = EA.baseline_exists_mask(la[keep], lo[keep], d["valid_mask"], d["land_mask"])
    argo_idx = np.stack([t_idx[keep], la[keep], lo[keep]], axis=1)
    clim_at = clim[pd.to_datetime(keys["date"].values).month - 1, la[keep], lo[keep], :]

    return Context(model=model, ck=ck, ckpt_path=ckpt_path, stage=stage, device=dev,
                   bundle=d, clim=clim, ds_tr=ds_tr, ds_te=ds_te, keys=keys,
                   truth_t=truth_t, truth_s=truth_s, argo_idx=argo_idx, clim_at=clim_at,
                   refusals=refusals, baseline_ok=baseline_ok)
