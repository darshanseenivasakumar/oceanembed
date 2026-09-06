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
from phase2.physics import seawater
from phase2.tscast_nio import config
from phase2.tscast_nio import provenance as _prov, dataset as D, output
from phase2.tscast_nio.models import TSCastNIO
from phase2.tscast_nio.models.tscast import assert_architecture_matches

# Documented limits of the FROZEN deliverable's bundle and Argo table, kept for code that holds
# no predictor (the API's coverage endpoint under a stub). Anything holding a TSCastPredictor must
# read `predictor.last_truth_day` / `predictor.last_argo_day`, which are derived from the loaded
# bundle and table rather than typed here. LAST_ARGO read 2026-08-24 until 2026-09-07 -- the fetch
# horizon of argo_2026.parquet -- while the table the predictor actually checks against
# (argo_daily_period.parquet) ends 2026-06-22, and the forecast note repeated the typed date.
LAST_GLORYS = np.datetime64("2026-06-23")
LAST_ARGO = np.datetime64("2026-06-22")


def assert_point_in_domain(lat, lon) -> None:
    """Refuse a coordinate the frozen grid cannot honestly answer for.

    `dataset.cell_index` is nearest-centre with no bound: (45N, 120E) snaps to the domain corner,
    and NaN compares false everywhere so argmin returns the FIRST cell (5.0N, 45.0E). Either way
    the caller gets a complete, plausible profile about a different place, with no flag -- measured
    on the shipped predictor 2026-09-06. The requested box (config.REGION, edges included) is
    answerable: every point in it lies within one cell of a grid centre.
    """
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError(
            f"latitude/longitude must be finite numbers, got ({lat!r}, {lon!r})") from None
    if not (np.isfinite(la) and np.isfinite(lo)):
        raise ValueError(
            f"latitude/longitude must be finite, got ({lat!r}, {lon!r}); a nearest-cell lookup on "
            f"NaN silently returns the first grid cell ({float(base.LAT[0])}N, "
            f"{float(base.LON[0])}E)")
    r = base.REGION
    if not (r["lat_min"] <= la <= r["lat_max"] and r["lon_min"] <= lo <= r["lon_max"]):
        raise ValueError(
            f"({la}, {lo}) is outside the reconstruction domain {r['lat_min']}..{r['lat_max']}N, "
            f"{r['lon_min']}..{r['lon_max']}E; a nearest-cell lookup would snap it to the domain "
            f"edge and serve a profile for a different place")


def _argo_table_end(path_noext: str):
    """Last profile date in an Argo table as datetime64[D], or None when the table is absent."""
    from oceanembed.utils import io as _io
    try:
        d = pd.to_datetime(_io.load_table(path_noext)["date"])
    except Exception:
        return None
    return np.datetime64(d.max().date()) if len(d) else None


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
        self.checkpoint_path = path      # kept so provenance can identify the FILE, not just its meta
        self.meta = {k: v for k, v in ck.items() if k != "state_dict"}

        # Which BUNDLE this checkpoint belongs to. Older checkpoints predate the field; they were
        # all monthly, so that is the only safe default -- and we say we assumed it rather than
        # letting a daily model quietly read monthly inputs.
        self.trained_data = ck.get("data")
        if self.trained_data is None:
            self.trained_data = "monthly"
            self.meta["data_assumed"] = ("checkpoint predates the `data` field; assuming monthly. "
                                         "Retrain to remove this assumption.")
        if data is not None:
            self.data = data
        elif self.trained_data == "daily":
            # THE BUNDLE THE CHECKPOINT WAS TRAINED ON, not the default. This read
            # `D.load_daily()` -- defaulting to data/processed/daily, the GLORYS bundle -- while
            # the shipped model trains on data/processed/daily_sat/v001. The dashboard therefore
            # fed GLORYS reanalysis into a satellite-trained network. Measured at 15N 68E on
            # 2026-05-15: 18.84 degC at 100 m against a float reading 26.85 (8.01 error); the same
            # model on its own bundle gives 26.24 (0.61). The channel-order check below cannot see
            # it -- both bundles carry the same seven channels in the same order.
            bundle_path, self.bundle_source = D.bundle_for_checkpoint(ck, path)
            self.data = D.load_daily(bundle_path)
            self.meta["bundle"] = bundle_path
            self.meta["bundle_resolved_by"] = self.bundle_source
        else:
            self.data = D.load_monthly()

        if list(self.data["channels"]) != list(ck["channels"]):
            raise ValueError(
                f"checkpoint was trained on channels {ck['channels']} but the loaded data has "
                f"{self.data['channels']}. Channel order is frozen; predicting across a mismatch "
                "would silently feed the model the wrong variables.")

        # A daily checkpoint pointed at monthly steps produces plausible numbers from the wrong
        # inputs -- the failure mode with no symptom. Catch it on the time axis, which differs by
        # construction: daily steps are 1 day apart, monthly steps ~30.
        self._refuse_on_cadence_mismatch()

        self.clim = clim if clim is not None else np.load(base.art("climatology.npy"))

        # Build the decoder the CHECKPOINT names. Guessing `film` is what made every
        # simple-decoder checkpoint fail to load with `Missing key(s) ... decoder.*`.
        # Checkpoints written before --decoder existed carry no `decoder` field, and defaulting to
        # "film" makes every one of them fail to load. The WEIGHTS say which decoder it is --
        # `simple_head.*` keys exist only on the simple head, `decoder.*` only on the FiLM U-Net.
        # Reading that is not guessing: it is the checkpoint describing itself through its own
        # tensors instead of through a field nobody wrote. Metadata still wins when present.
        if "decoder" in ck:
            self.decoder_name = ck["decoder"]
            self.decoder_source = "checkpoint metadata"
        else:
            keys = ck["state_dict"].keys()
            has_simple = any(k.startswith("simple_head.") for k in keys)
            has_film = any(k.startswith("decoder.") for k in keys)
            if has_simple == has_film:
                raise RuntimeError(
                    f"{path} records no `decoder` and its weights are ambiguous "
                    f"(simple_head={has_simple}, decoder={has_film}). Refusing to guess.")
            self.decoder_name = "simple" if has_simple else "film"
            self.decoder_source = "inferred from the state_dict (no `decoder` in metadata)"
        # T_SEQ is the data WINDOW; the network was constructed at `built_t_seq` (1). They differ
        # for every T_SEQ>1 run, and only cnn3d's time pooling hides it.
        built_t = int(ck.get("built_t_seq", ck["T_SEQ"]))
        # Stage 1 checkpoints predate the field; they are stage 1 by definition.
        self.stage = int(ck.get("stage", 1))
        self.model = TSCastNIO(ck["encoder"], len(ck["channels"]), t_seq=built_t,
                               p=ck["P"], latent=ck["latent"], residual=ck["residual"],
                               unet_channels=(tuple(ck["unet_channels"]) if ck.get("unet_channels") else None),
                               decoder=self.decoder_name, stage=self.stage)
        # Refuse a wrongly-rebuilt architecture BEFORE loading. load_state_dict accepts a t_seq
        # mismatch silently -- conv weights do not encode temporal extent -- and the model then
        # predicts differently on identical input. Deliberately OUTSIDE the try: a mismatch here
        # is not a torch load failure and must not be reported as one.
        assert_architecture_matches(self.model, ck, "inference.TSCastPredictor")
        try:
            self.model.load_state_dict(ck["state_dict"])
        except RuntimeError as e:
            raise RuntimeError(
                f"the checkpoint at {path} does not fit the network described by its own metadata "
                f"(encoder={ck['encoder']}, decoder={self.decoder_name}, latent={ck['latent']}, "
                f"built_t_seq={built_t}).\n  torch said: {e}\n"
                "This predictor will not silently drop or invent weights to make a load succeed."
            ) from None
        self.model.eval()

        # The independent-Argo table must cover the period this checkpoint predicts in.
        # `argo_test` is 2022 only: against a 2026 daily prediction it matches nothing and the
        # panel reads "no float nearby", which looks identical to genuinely unsampled ocean.
        self.argo_table = "argo_daily_period" if self.trained_data == "daily" else "argo_test"
        self._engine = None
        # The limits this predictor can honestly speak to, READ from what it loaded rather than
        # typed at the top of the file (audit 2026-09-06). A bundle only holds days that have a
        # target, so its last day is the last day with truth.
        _t = np.asarray(self.data["times"], dtype="datetime64[D]")
        self.first_day, self.last_truth_day = _t.min(), _t.max()
        self.last_argo_day = _argo_table_end(base.art(self.argo_table))

        norm = [np.asarray(v, dtype="float32") for v in ck["norm"]]
        if self.stage == 2 and len(norm) != 6:
            raise ValueError(
                f"a stage-2 checkpoint must carry 6 normalisation entries (salinity has its own "
                f"mean and std); this one has {len(norm)}. Scaling salinity with temperature's "
                f"statistics would be a silent ~20x error.")
        self.s_mean, self.s_std = (norm[4], norm[5]) if len(norm) == 6 else (None, None)
        self.ds = D.GriddedPatches(
            self.data["surface"], self.data["temp"], self.data["times"],
            self.data["land_mask"], self.data["channels"],
            np.arange(len(self.data["times"])), norm=norm, t_seq=ck["T_SEQ"], p=ck["P"],
            max_samples=1, clim=self.clim, return_clim=True)
        self.y_mean, self.y_std = norm[2], norm[3]
        # None is a valid state: an uncalibrated sigma is still the model's honest output. What
        # must not happen is applying someone else's scales without saying so.
        self.calibration = output.load_calibration()

    @property
    def engine(self):
        """F1's CollocationEngine, pointed at this bundle's Argo table. One matcher, not two."""
        if self._engine is None:
            from phase2.data.collocation import CollocationEngine

            self._engine = CollocationEngine(argo_table=self.argo_table)
        return self._engine

    def _refuse_on_cadence_mismatch(self) -> None:
        """A daily checkpoint must not be fed monthly steps, or the reverse.

        The time axis tells us which bundle we actually hold, independently of any label, so this
        catches a mislabelled npz as well as a wrong `data=` argument.
        """
        t = np.asarray(self.data["times"], dtype="datetime64[D]")
        if len(t) < 2:
            return
        step = int(np.median(np.diff(t).astype(int)))
        looks = "daily" if step <= 3 else "monthly"
        if looks != self.trained_data:
            raise ValueError(
                f"this checkpoint was trained on the {self.trained_data} bundle, but the loaded "
                f"data has a median step of {step} day(s), which is a {looks} bundle "
                f"({len(t)} steps, {t[0]}..{t[-1]}). Predicting across that mismatch would feed "
                f"the model inputs at a cadence it never saw. Load the {self.trained_data} bundle, "
                f"or pass data= explicitly if you know why you are crossing them.")

    # ------------------------------------------------------------------ helpers
    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        assert_point_in_domain(lat, lon)
        i, j = D.cell_index(lat, lon)          # frozen nearest-centre convention
        return int(i[0]), int(j[0])

    def _time(self, date) -> tuple[int, int]:
        t = np.datetime64(pd.Timestamp(date).date())
        times = np.asarray(self.data["times"], dtype="datetime64[D]")
        if t < times[0]:
            # argmin has no lower bound: a 2020-01-01 request came back as the 2025-06-01 field
            # with forecast=False and days_from_requested=1978 -- served as an answer (measured
            # 2026-09-06). A date AFTER the bundle is a different case: still served, labelled
            # FORECAST, per tscast_output_schema.md section 4.
            raise ValueError(
                f"{t} precedes the first day of the loaded bundle ({times[0]}); the nearest-day "
                f"lookup would serve the {times[0]} inputs, "
                f"{int((times[0] - t).astype('timedelta64[D]').astype(int))} days away, as if "
                f"they described {t}. No reconstruction exists for that date.")
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
            out = self.model(x[None], g[None], cp[None], mo[None])
        mu, logvar = out[0], out[1]

        temp = mu.numpy()[0] * self.y_std + self.y_mean
        # sigma is in z-units; y_std carries it back to degC, per depth
        logvar_deg = logvar.numpy()[0] + 2.0 * np.log(self.y_std)

        sal = log_var_s = density = log_var_rho = None
        if self.stage == 2:
            mu_s, lv_s, lv_rho = out[2], out[3], out[4]
            sal = mu_s.numpy()[0] * self.s_std + self.s_mean
            # the same z-to-physical rearrangement as temperature, in psu
            log_var_s = lv_s.numpy()[0] + 2.0 * np.log(self.s_std)
            # log_var_rho is already in physical units: eq. 5 is evaluated on kg m-3 directly,
            # so it is NOT rescaled here. Rescaling it by s_std would be a units error that
            # nothing downstream could detect.
            log_var_rho = lv_rho.numpy()[0]
            density = seawater.density(sal, temp)

        valid = np.isfinite(self.data["temp"][t_idx, i, j, :])
        floor = self.seafloor_depth_m(lat, lon)

        target = np.datetime64(pd.Timestamp(date).date())
        # Past the bundle's last day there is no target the model could have been trained
        # against. Read from the loaded bundle, not the module constant: PROJECT_RECORD 16.2
        # noted the typed constant inverts this guard the day the bundle is extended.
        forecast = bool(target > self.last_truth_day)

        prov = {
            "model": "tscast-nio-stage1",
            "encoder": self.meta.get("encoder"),
            "seed": self.meta.get("seed"),
            "T_SEQ": self.meta.get("T_SEQ"),
            "P": self.meta.get("P"),
            "residual": self.meta.get("residual"),
            # Read from the loaded bundle. This was the string literal "glorys" -- flagged in
            # the forensic audit and still here until now -- which meant the shipped
            # SATELLITE model would have served every prediction labelled glorys. A literal
            # is not provenance: it says whatever it was written to say.
            "input_source": self.data.get("input_source", "unknown"),
            "input_date": str(np.asarray(self.data["times"])[t_idx]),
            "requested_date": str(target),
            "days_from_requested": days_off,
            "grid_cell": {"lat": float(base.LAT[i]), "lon": float(base.LON[j])},
            "clim_train_years": list(base.TRAIN_YEARS),
            # Schema §5 requires both, and this block carried neither until 2026-09-05 -- so no
            # record could be traced back to the exact bytes or the exact code that made it,
            # which is the whole purpose of a provenance block. Computed here rather than
            # hardcoded; `checkpoint_sha256` is the same equality freeze.py checks.
            "checkpoint_sha256": _prov.checkpoint_sha256(getattr(self, "checkpoint_path", None)),
            "code_commit": _prov.code_commit(),
            "code_dirty": _prov.code_dirty(),
            "stage": self.stage,
            "eos": ("EOS-80 / UNESCO (1983); density is COMPUTED from the predicted (T, S), "
                    "not predicted directly") if self.stage == 2 else None,
            "decoder": self.decoder_name,
            "loss": self.meta.get("loss"),
            "trained_on": self.meta.get("trained_on"),
            "channels": [str(c) for c in self.data["channels"]],
            "argo_table": self.argo_table,
        }
        if argo_check is None and not forecast:
            argo_check = self._argo_check_for(lat, lon, target, temp)

        # Phase-6 scales, if they were fitted for THIS model. build_record checks the match and
        # leaves sigma raw with a recorded reason if they were not -- applying another model's
        # scales would rescale the error bar by a factor from a different error distribution and
        # look entirely normal doing it.
        return output.build_record(
            temperature=temp, log_var_t=logvar_deg, valid=valid, seafloor_depth_m=floor,
            provenance=prov, argo_check=None if forecast else argo_check, forecast=forecast,
            salinity=sal, log_var_s=log_var_s, density=density, log_var_rho=log_var_rho,
            calibration=self.calibration,
            last_truth_date=str(self.last_truth_day),
            last_argo_date=None if self.last_argo_day is None else str(self.last_argo_day))

    def _argo_check_for(self, lat: float, lon: float, target, temp) -> dict | None:
        """Nearest INDEPENDENT float beside the prediction -- or None, meaning genuinely none near.

        Any failure to reach the table returns None rather than a fabricated comparison; the record
        then says no float was found, which is the honest reading of "we could not check this".
        """
        try:
            m = self.engine.match_argo(lat, lon, str(target))
        except Exception:
            return None
        if m is None:
            return None
        return output.build_argo_check(
            argo_temperature=m["temperature_profile"], temperature=temp,
            profile_id=f"{m['latitude']:.3f},{m['longitude']:.3f}@{m['datetime']}",
            distance_km=float(m["spatial_offset_km"]),
            days_offset=abs(float(m["temporal_offset_days"])),
            source=f"argopy/{self.argo_table}")
