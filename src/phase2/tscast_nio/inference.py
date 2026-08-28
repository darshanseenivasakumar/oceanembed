"""Reconstruct one profile from a trained TS-Cast-NIO checkpoint, as an output-schema record.

This is the join between the model and the UI: it loads a checkpoint, predicts at a
(lat, lon, date), attaches the nearest independent Argo profile, and returns the record defined in
docs/phase2/tscast_output_schema.md -- reasons and argo_check included, because those are part of
the record rather than something the page adds afterwards.

Refuses rather than guesses:
  * a checkpoint whose channel list disagrees with the loaded data
  * a date beyond the last date with ground truth is served as a FORECAST, never with an
    accuracy claim attached
  * a depth below the sea floor is None with a reason, never a fabricated temperature
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import torch

from oceanembed import config as base
from phase2.tscast_nio import config, dataset as D, output
from phase2.tscast_nio.models import TSCastNIO

# Verified availability limits; past these there is no truth to check against.
LAST_GLORYS = np.datetime64("2026-06-23")
LAST_ARGO = np.datetime64("2026-08-24")


class TSCastPredictor:
    def __init__(self, checkpoint: str | None = None, data: dict | None = None,
                 clim: np.ndarray | None = None):
        path = checkpoint or base.art("tscast_stage1.pt")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"no checkpoint at {path}. Train one with "
                "`python -m phase2.tscast_nio.train.train_stage1` -- this class will not "
                "fabricate a prediction from an untrained network.")
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.meta = {k: v for k, v in ck.items() if k != "state_dict"}

        self.data = data or D.load_monthly()
        if list(self.data["channels"]) != list(ck["channels"]):
            raise ValueError(
                f"checkpoint was trained on channels {ck['channels']} but the loaded data has "
                f"{self.data['channels']}. Channel order is frozen; predicting across a mismatch "
                "would silently feed the model the wrong variables.")

        self.clim = clim if clim is not None else np.load(base.art("climatology.npy"))
        self.model = TSCastNIO(ck["encoder"], len(ck["channels"]), t_seq=ck["T_SEQ"],
                               p=ck["P"], latent=ck["latent"], residual=ck["residual"])
        self.model.load_state_dict(ck["state_dict"])
        self.model.eval()

        norm = [np.asarray(v, dtype="float32") for v in ck["norm"]]
        self.ds = D.GriddedPatches(
            self.data["surface"], self.data["temp"], self.data["times"],
            self.data["land_mask"], self.data["channels"],
            np.arange(len(self.data["times"])), norm=norm, t_seq=ck["T_SEQ"], p=ck["P"],
            max_samples=1, clim=self.clim, return_clim=True)
        self.y_mean, self.y_std = norm[2], norm[3]

    # ------------------------------------------------------------------ helpers
    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        i, j = D.cell_index(lat, lon)          # frozen nearest-centre convention
        return int(i[0]), int(j[0])

    def _time(self, date) -> tuple[int, int]:
        t = np.datetime64(pd.Timestamp(date).date())
        times = np.asarray(self.data["times"], dtype="datetime64[D]")
        offs = np.abs((times - t).astype("timedelta64[D]").astype(int))
        k = int(np.argmin(offs))
        return k, int(offs[k])

    def seafloor_depth_m(self, lat: float, lon: float) -> float:
        i, j = self._cell(lat, lon)
        col = np.isfinite(self.data["temp"][:, i, j, :]).any(axis=0)
        return float(config.DEPTHS[int(np.nonzero(col)[0].max())]) if col.any() else 0.0

    # ------------------------------------------------------------------ the API
    def reconstruct(self, lat: float, lon: float, date, argo_check=None) -> dict:
        i, j = self._cell(lat, lon)
        t_idx, days_off = self._time(date)

        self.ds.index = np.array([[t_idx, i, j]])
        x, g, _, _, _, cp, mo = self.ds[0]
        with torch.no_grad():
            mu, logvar = self.model(x[None], g[None], cp[None], mo[None])

        temp = mu.numpy()[0] * self.y_std + self.y_mean
        # sigma is in z-units; y_std carries it back to degC, per depth
        logvar_deg = logvar.numpy()[0] + 2.0 * np.log(self.y_std)

        valid = np.isfinite(self.data["temp"][t_idx, i, j, :])
        floor = self.seafloor_depth_m(lat, lon)

        target = np.datetime64(pd.Timestamp(date).date())
        forecast = bool(target > LAST_GLORYS)

        prov = {
            "model": "tscast-nio-stage1",
            "encoder": self.meta.get("encoder"),
            "seed": self.meta.get("seed"),
            "T_SEQ": self.meta.get("T_SEQ"),
            "P": self.meta.get("P"),
            "residual": self.meta.get("residual"),
            "input_source": "glorys",
            "input_date": str(np.asarray(self.data["times"])[t_idx]),
            "requested_date": str(target),
            "days_from_requested": days_off,
            "grid_cell": {"lat": float(base.LAT[i]), "lon": float(base.LON[j])},
            "clim_train_years": list(base.TRAIN_YEARS),
        }
        return output.build_record(
            temperature=temp, log_var_t=logvar_deg, valid=valid, seafloor_depth_m=floor,
            provenance=prov, argo_check=None if forecast else argo_check, forecast=forecast)
