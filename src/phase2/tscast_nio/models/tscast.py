"""TS-Cast-NIO stage 1: satellite encoder -> FiLM-conditioned climatology decoder -> T + log-var.

Reimplemented from the published description of TS-Cast (Chae, Donohue & Park, Ocean Sci. 22,
2161-2177, 2026). Their code was never released; nothing here is copied from it.

The architecture, and where we knowingly differ:

  encoder        the bake-off winner (see artifacts/architecture_feasibility.json) -> h in R^latent

  decoder        A 1-D U-Net whose INPUT is the monthly climatology, not the satellite data. This
                 is the paper's central idea: the network adjusts a physically-grounded average
                 rather than guessing a profile from scratch.

  FiLM (eq. 2)   gamma_i,c * x_i,c + beta_i,c, injected at EVERY encode and decode step. gamma and
                 beta come from a per-step MLP with two residual blocks, hidden width equal to that
                 step's channel count -- the satellite latent modulates the prior.

  heads          Two, in parallel. The temperature head reads ALL intermediate U-Net features. The
                 log-variance head reads only the climatology embedding, because the paper derives
                 uncertainty "from the input monthly climatological profiles to capture seasonal
                 and depth-dependent uncertainty" -- regional variability, not the day's satellite
                 image. That means predicted sigma does NOT depend on the satellite input, which is
                 the paper's design and is worth stating rather than quietly 'fixing'.

DELIBERATE DEVIATIONS, all forced by our frozen contract or our data:

  * 15 depths, not their 128. Four stride-2 downsamples need far more than 15 levels, so the U-Net
    runs on an internal 64-level grid and a fixed linear-interpolation matrix maps 15 -> 64 on the
    way in and 64 -> 15 on the way out. The output contract (PS req 11) is untouched.
  * Stage 1 predicts TEMPERATURE only. Salinity and the eq. 5 density constraint are stage 2, and
    stage 2 does not start until stage 1 is validated against real Argo.
  * RESIDUAL output. `residual=True` makes the network predict a CORRECTION to the current month's
    climatology instead of the profile outright. The paper does not state this; it is our reading
    of "adjust the average rather than guess", and it is a flag so the claim stays testable.
    Note the paper's own ablation found the climatology prior contributes only modestly to RMSE
    and mainly stabilises training -- we should claim it the same honest way.

Loss is the paper's eq. 3 (NOT eq. 5, which is the stage-2 density term).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from phase2.physics import seawater
from phase2.tscast_nio import config, encoders as E

# Applied to log_var_t, log_var_s AND log_var_rho. The first two are in Z-SPACE (so the
# physical sigma depends on y_std / s_std), but log_var_rho is in PHYSICAL kg m-3 because
# eq. 5 is evaluated on unscaled density. Same bounds, different units: sigma_rho is pinned
# to roughly [0.030, 33.1] kg m-3, which is plausible for this basin but is a different
# quantity from the degC the T head ends up in.
LOGVAR_MIN, LOGVAR_MAX = -7.0, 7.0


def depth_interp_matrix(src_depths, dst_depths) -> np.ndarray:
    """(n_dst, n_src) linear-interpolation matrix. Fixed, differentiable, and it makes the
    15 <-> 64 resampling an explicit auditable object rather than a hidden reshape."""
    src = np.asarray(src_depths, dtype="float64")
    dst = np.asarray(dst_depths, dtype="float64")
    M = np.zeros((len(dst), len(src)))
    for k, d in enumerate(dst):
        if d <= src[0]:
            M[k, 0] = 1.0
        elif d >= src[-1]:
            M[k, -1] = 1.0
        else:
            j = int(np.searchsorted(src, d) - 1)
            w = (d - src[j]) / (src[j + 1] - src[j])
            M[k, j], M[k, j + 1] = 1.0 - w, w
    return M


class FiLM(nn.Module):
    """Paper eq. 2. gamma/beta from an MLP with two residual blocks, hidden width = C."""

    def __init__(self, latent: int, channels: int):
        super().__init__()
        self.c = channels
        self.inp = nn.Linear(latent, channels)
        self.r1a, self.r1b = nn.Linear(channels, channels), nn.Linear(channels, channels)
        self.r2a, self.r2b = nn.Linear(channels, channels), nn.Linear(channels, channels)
        self.out = nn.Linear(channels, 2 * channels)
        self.act = nn.Mish()
        # NEAR-identity at init, deliberately not EXACT identity.
        #
        # Zero-initialising this weight makes gamma and beta exactly 0, so FiLM is the identity
        # and training starts from the pure climatology -- which is attractive. But d(gamma)/dh is
        # then also exactly zero, so NO GRADIENT REACHES THE ENCODER on the first step. The
        # satellite embedding would be frozen at initialisation, and because the layer heals
        # itself once `out.weight` moves, the symptom is a slow start rather than an error.
        # Exact-zero output and gradient flow to h are mutually exclusive here, so we take a small
        # random weight: gamma, beta ~ 0 (still effectively the prior) and gradients flow at once.
        # tests/phase2/test_tscast_model.py::test_gradients_reach_the_encoder guards this.
        nn.init.normal_(self.out.weight, std=1e-3)
        nn.init.zeros_(self.out.bias)

    def forward(self, x, h):
        z = self.act(self.inp(h))
        z = z + self.r1b(self.act(self.r1a(z)))
        z = z + self.r2b(self.act(self.r2a(z)))
        gb = self.out(z)
        gamma, beta = gb[:, :self.c], gb[:, self.c:]
        return (1.0 + gamma).unsqueeze(-1) * x + beta.unsqueeze(-1)


class Res1D(nn.Module):
    def __init__(self, c_in: int, c_out: int):
        super().__init__()
        self.a = nn.Conv1d(c_in, c_out, 3, padding=1)
        self.b = nn.Conv1d(c_out, c_out, 3, padding=1)
        self.n = nn.GroupNorm(1, c_out)
        self.skip = nn.Conv1d(c_in, c_out, 1) if c_in != c_out else nn.Identity()
        self.act = nn.Mish()

    def forward(self, x):
        h = self.act(self.a(x))
        return self.act(self.n(self.b(h)) + self.skip(x))


class ClimatologyUNet(nn.Module):
    """1-D U-Net over the monthly climatology, FiLM-conditioned by the satellite latent."""

    def __init__(self, latent: int, n_months: int = 12, levels: int = None,
                 widths=None, n_out_channels: int = 1):
        super().__init__()
        self.L = int(config.INTERNAL_LEVELS if levels is None else levels)
        widths = tuple(config.UNET_CHANNELS if widths is None else widths)
        self.widths = widths

        # kernel spanning all 12 months == a 1-D conv with 12*C input channels (paper 2.3.2)
        self.stem = Res1D(n_months * n_out_channels, widths[0])

        self.down_blocks = nn.ModuleList()
        self.down_films = nn.ModuleList()
        c = widths[0]
        for w in widths:
            self.down_blocks.append(Res1D(c, w))
            self.down_films.append(FiLM(latent, w))
            c = w

        # One up step per down step, mirroring exactly. Channel counts are enumerated rather
        # than derived: an off-by-one here concatenates tensors of different LENGTH, which torch
        # catches, or of the same length and wrong DEPTH, which it does not.
        self.up_blocks = nn.ModuleList()
        self.up_films = nn.ModuleList()
        rev = list(reversed(widths))                       # e.g. 512,256,128,64
        up_out = rev[1:] + [widths[0]]                     # e.g. 256,128,64,64
        c_up = rev[0]
        for k in range(len(widths)):
            c_skip = widths[len(widths) - 1 - k]           # skip at this resolution
            self.up_blocks.append(Res1D(c_up + c_skip, up_out[k]))
            self.up_films.append(FiLM(latent, up_out[k]))
            c_up = up_out[k]
        self.up_out = up_out

        # temperature head reads ALL intermediate decoder features (paper 2.3.4)
        mu_in = sum(up_out) + widths[-1]
        self.mu_head = nn.Sequential(nn.Conv1d(mu_in, 128, 1), nn.Mish(), nn.Conv1d(128, 1, 1))
        # log-variance head reads only the climatology embedding (paper 2.3.4)
        self.logvar_head = nn.Sequential(nn.Conv1d(widths[0], 64, 1), nn.Mish(),
                                         nn.Conv1d(64, 1, 1))

    def forward(self, clim, h):
        """clim: (B, 12*C, L). h: (B, latent). -> mu (B, L), logvar (B, L)."""
        x = self.stem(clim)
        clim_embed = x

        skips = []
        for blk, film in zip(self.down_blocks, self.down_films):
            x = film(blk(x), h)
            skips.append(x)
            x = F.avg_pool1d(x, 2)

        feats = []
        for k, (blk, film) in enumerate(zip(self.up_blocks, self.up_films)):
            x = F.interpolate(x, scale_factor=2, mode="linear", align_corners=False)
            skip = skips[len(skips) - 1 - k]
            x = film(blk(torch.cat([x, skip], dim=1)), h)
            feats.append(x)

        L = clim.shape[-1]
        up = [F.interpolate(f, size=L, mode="linear", align_corners=False) for f in feats]
        up.append(F.interpolate(skips[-1], size=L, mode="linear", align_corners=False))
        mu = self.mu_head(torch.cat(up, dim=1)).squeeze(1)
        logvar = self.logvar_head(clim_embed).squeeze(1).clamp(LOGVAR_MIN, LOGVAR_MAX)
        return mu, logvar


class TSCastNIO(nn.Module):
    """7 (or 5) surface channels + climatology prior -> 15 depths + per-depth log-var.

    stage 1 -> (mu_T, logvar_T)
    stage 2 -> (mu_T, logvar_T, mu_S, logvar_S, logvar_rho), the paper's eq. 3/4/5 heads.
    Stage 1's architecture is byte-identical to before stage 2 existed, so every stage-1
    checkpoint still loads and the shipped 0.8612 degC result stays reproducible.
    """

    def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None,
                 doy_channels: bool = False,
                 latent: int = None, residual: bool = True, unet_channels=None,
                 decoder: str = "film", stage: int = 1):
        super().__init__()
        if stage not in (1, 2):
            raise ValueError(f"stage must be 1 or 2, got {stage!r}")
        self.stage = int(stage)
        t_seq = int(config.T_SEQ if t_seq is None else t_seq)
        # The value this network was BUILT with, kept so a checkpoint can be checked against
        # it exactly. The pool signature alone cannot separate t_seq=11 from t_seq=31 -- both
        # pool [2,2,2] -- so the signature is the fallback and this is the precise test.
        self.built_t_seq = int(t_seq)
        p = int(config.P if p is None else p)
        latent = int(config.LATENT_DIM if latent is None else latent)

        # Geo channels: 3 (lat/lon unit vector, paper eq. 1) plus 2 for day-of-year when
        # the season is fed in (E-INV-00 leg L1). Routed through the geo path, not c_in,
        # so the input-width guard and input_channels() are untouched.
        self.doy_channels = bool(doy_channels)
        self.n_geo = 3 + (2 if self.doy_channels else 0)
        self.encoder = E.ENCODERS[encoder_name](c_in, t_seq, p, latent=latent, n_geo=self.n_geo)
        #: The input width this network was BUILT for, so a checkpoint can be checked against it.
        self.c_in = int(c_in)
        self.encoder_name = encoder_name
        self.decoder_name = decoder
        if decoder == "film":
            self.decoder = ClimatologyUNet(latent, widths=unet_channels)
        elif decoder == "simple":
            # The bake-off's head, verbatim: latent -> 15 depths, no climatology, no FiLM. This is
            # the ONLY decoder that has been scored against Argo (0.9891 degC). Keeping it here as a
            # switch is what lets the loss be varied INDEPENDENTLY of the decoder -- going from the
            # bake-off model to the TS-Cast model changed both at once, and three rounds of tuning
            # inside that confound could not attribute the regression to either.
            self.decoder = None
            # Stage 1: mu_T, logvar_T.
            # Stage 2 adds mu_S, logvar_S and logvar_rho -- five blocks of 15.
            # logvar_rho is its OWN output, not derived from the T and S variances, because the
            # paper is explicit that T/S error covariance is non-negligible (2.3.4), so
            # propagating the two variances analytically would understate the density error.
            n_blocks = 2 if self.stage == 1 else 5
            self.n_head_blocks = n_blocks
            self.simple_head = nn.Sequential(
                nn.Linear(latent, 256), nn.Mish(),
                nn.Linear(256, n_blocks * config.N_DEPTHS))
        else:
            raise ValueError(f"decoder must be 'film' or 'simple', got {decoder!r}")
        if self.stage == 2 and decoder != "simple":
            raise NotImplementedError(
                "stage 2 is implemented on the 'simple' decoder only. FiLM was MEASURED to cost "
                "~0.18 degC at our data scale under either loss (AGENT_SYNC 2026-08-29 section 1), "
                "so it is not the head we ship, and adding three untested outputs to it would put "
                "an unvalidated path in the checkpoint. Use --decoder simple.")
        self.residual = bool(residual)

        lo, hi = config.INTERNAL_DEPTH_RANGE
        internal = np.linspace(lo, hi, config.INTERNAL_LEVELS)
        self.register_buffer("up_M", torch.tensor(
            depth_interp_matrix(config.DEPTHS, internal), dtype=torch.float32))
        self.register_buffer("down_M", torch.tensor(
            depth_interp_matrix(internal, config.DEPTHS), dtype=torch.float32))

    def forward(self, x, x_geo, clim, month):
        """clim: (B, 12, 15) z-scored. month: (B,) int index of the target month."""
        h = self.encoder(x, x_geo)

        if self.decoder is None:                                       # 'simple': the bake-off head
            out = self.simple_head(h)
            d = config.N_DEPTHS
            blocks = out.split(d, dim=1)
            if self.stage == 1:
                mu, logvar = blocks
                return mu, logvar.clamp(LOGVAR_MIN, LOGVAR_MAX)
            mu_t, logvar_t, mu_s, logvar_s, logvar_rho = blocks
            return (mu_t, logvar_t.clamp(LOGVAR_MIN, LOGVAR_MAX),
                    mu_s, logvar_s.clamp(LOGVAR_MIN, LOGVAR_MAX),
                    logvar_rho.clamp(LOGVAR_MIN, LOGVAR_MAX))

        c_int = torch.einsum("ls,bms->bml", self.up_M, clim)          # (B,12,64)
        mu_i, logvar_i = self.decoder(c_int, h)

        mu = torch.einsum("dl,bl->bd", self.down_M, mu_i)             # (B,15)
        logvar = torch.einsum("dl,bl->bd", self.down_M, logvar_i)

        if self.residual:
            prior = clim.gather(1, month.view(-1, 1, 1).expand(-1, 1, clim.shape[-1])).squeeze(1)
            mu = prior + mu
        return mu, logvar.clamp(LOGVAR_MIN, LOGVAR_MAX)


def gaussian_nll(mu, logvar, y, mask, beta: float = 0.0):
    """Paper eq. 3 (beta=0), with the beta-NLL correction of Seitzer et al. 2022 for beta>0.

    Plain NLL is  0.5*exp(-logvar)*(y-mu)^2 + 0.5*logvar.  The +0.5*logvar term stops the network
    inflating its variance -- but nothing stops the opposite, and that is what bit us:

        MEASURED on the first real stage-1 run. Train NLL fell to -1.0610 while held-out NLL rose
        to +0.6732, and the best held-out epoch was 3 of 20. The gradient of the squared-error term
        is scaled by 1/sigma^2, so the cheapest way for the model to cut the loss is to SHRINK
        sigma on training points rather than improve the mean. Capacity goes into collapsing
        variance instead of learning temperature. Argo RMSE came out at 1.1861 -- worse than the
        0.9891 the same encoder reached under plain MSE in the bake-off.

    beta-NLL multiplies the per-point loss by a STOP-GRADIENT sigma^(2*beta), cancelling that
    1/sigma^2 weighting:

        beta = 0  -> plain NLL (the paper's eq. 3)
        beta = 1  -> the gradient w.r.t. mu is exactly the MSE gradient, while the variance head
                     still trains
        beta = 0.5-> the authors' recommended middle, and our default

    The weight is detached, so it re-weights the loss without becoming a second path through which
    the network can game sigma.

    Masked, because ~24% of cells are below the sea floor: a masked level must contribute nothing,
    not contribute a zero.
    """
    m = mask.float()
    n = m.sum().clamp(min=1.0)
    per = 0.5 * torch.exp(-logvar) * (y - mu) ** 2 + 0.5 * logvar
    if beta:
        per = per * (torch.exp(logvar).detach() ** beta)
    return (per * m).sum() / n


# Practical salinity floor for the density polynomial. EOS-80's S**1.5 term is NaN below zero,
# and one NaN poisons every gradient in the batch rather than just its own element. An untrained
# salinity head does emit negatives in the first few hundred steps, so this is not hypothetical.
# 0 psu is the physical floor (fresh water); the UNESCO fit is quoted valid over S 0.5-43.
S_FLOOR = 0.0


def density_nll(mu_t, mu_s, logvar_rho, y_t, y_s, mask,
                y_mean, y_std, s_mean, s_std, beta: float = 0.0):
    """TS-Cast eq. 5 -- the physical constraint, as a Gaussian NLL on density.

        L_rho = mean_i [ (1 / (2 sigma_rho,i^2)) (rho_i - rho_hat_i)^2 + 0.5 log sigma_rho,i^2 ]

    rho_hat is EOS-80 density computed from the model's PREDICTED (T, S); rho is the same
    polynomial on the ground truth. The network never outputs density directly -- exactly as the
    paper states -- so gradients reach both heads only through the polynomial, which is why
    `density_torch` exists and why nothing here round-trips through numpy.

    sigma_rho is a SEPARATE predicted head, not propagated from the T and S variances. The paper
    is explicit (2.3.4) that T/S error covariance is non-negligible, so an analytic propagation
    would understate the density error.

    UNITS -- the thing that makes this term wrong if you skip it. The heads emit z-scored values;
    EOS-80 is a polynomial in degC and PSS-78. Feeding z-scores to it produces a number with no
    physical meaning that still back-propagates happily. So both predictions and truth are
    returned to physical units here, using the SAME train-only statistics the targets were scaled
    with, before either touches the polynomial.

    beta: the same beta-NLL correction as eq. 3/4. The paper uses plain NLL (beta=0), but on our
    data that was MEASURED to collapse the variance (train NLL -1.0610 vs held-out +0.6732), so
    the deviation is deliberate and is recorded rather than silently adopted.
    """
    t_pred = mu_t * y_std + y_mean
    s_pred_raw = mu_s * s_std + s_mean
    s_pred = s_pred_raw.clamp(min=S_FLOOR)
    t_true = y_t * y_std + y_mean
    s_true = (y_s * s_std + s_mean).clamp(min=S_FLOOR)

    # How many predicted salinities were unphysical. The clamp is necessary -- S**1.5 on a
    # negative base is NaN and would kill the run -- but it is NOT free, and the counter is here
    # so a run leaning on it is visible rather than silent.
    #
    # MEASURED: the clamp zeroes the gradient EXACTLY (grad through mu_s 0.0 vs mu_t 32.87 on a
    # clamped batch). So L_rho cannot push a negative salinity back into range; only L_S can.
    # A density term that appears to be training while its salinity input is pinned at the floor
    # is doing nothing, and this number is the only way to notice.
    density_nll.last_n_clamped = int((s_pred_raw < S_FLOOR).sum())

    rho_pred = seawater.density_torch(s_pred, t_pred)
    rho_true = seawater.density_torch(s_true, t_true)

    m = mask.float()
    n = m.sum().clamp(min=1.0)
    per = 0.5 * torch.exp(-logvar_rho) * (rho_true - rho_pred) ** 2 + 0.5 * logvar_rho
    if beta:
        per = per * (torch.exp(logvar_rho).detach() ** beta)
    return (per * m).sum() / n


def build(encoder_name: str, c_in: int, **kw) -> TSCastNIO:
    return TSCastNIO(encoder_name, c_in, **kw)


def temporal_pool_signature(model: nn.Module) -> list[int]:
    """The TIME-axis kernel of every 3-D pool in the model, in order.

    THE BUG THIS EXISTS TO CATCH
    `cnn3d` sizes its `AvgPool3d` from the `t_seq` passed at CONSTRUCTION, not from the input it
    receives. Building with the wrong `t_seq` therefore produces a structurally different network
    that `load_state_dict` accepts WITHOUT COMPLAINT -- conv weights do not encode temporal extent,
    so no shape mismatch is raised -- and that then predicts differently on identical input.

    That happened. `score_by_basin` and `calibrate_uncertainty` both rebuilt with `ck["T_SEQ"]`
    (the DATA window) instead of `built_t_seq` (the construction value). The scorer disagreed with
    a checkpoint's own recorded RMSE by 0.02 degC, and the uncertainty scales in
    `uncertainty_calibration.json` were fitted through a model the project does not ship. Neither
    failed loudly; both produced plausible numbers.

    A pool signature separates the two architectures where a state_dict cannot. Built at t_seq=11
    the kernels read [2, 2, 2]; at t_seq=1 they read [1, 1, 1].
    """
    sig: list[int] = []
    for m in model.modules():
        if isinstance(m, (nn.AvgPool3d, nn.MaxPool3d)):
            k = m.kernel_size
            sig.append(int(k[0] if isinstance(k, (tuple, list)) else k))
    return sig


def assert_architecture_matches(model: nn.Module, ck: dict, where: str = "") -> None:
    """Refuse a model whose temporal pooling differs from the checkpoint being loaded into it.

    Checkpoints written before 2026-09-02 carry no `pool_signature`; there is nothing to compare
    against, so this passes rather than inventing a constraint. Silence there is honest -- the
    field's absence is why the bug went unnoticed, and back-filling a guess would hide that.
    """
    built = ck.get("built_t_seq")
    if built is not None and getattr(model, "built_t_seq", None) is not None:
        if int(model.built_t_seq) != int(built):
            raise ValueError(
                f"architecture mismatch{' in ' + where if where else ''}: this model was built with "
                f"t_seq={model.built_t_seq}, the checkpoint was trained at built_t_seq={built}. "
                f"load_state_dict would ACCEPT this silently. Note T_SEQ={ck.get('T_SEQ')} is the "
                f"DATA window and is NOT the construction value.")

    # Input width. A checkpoint trained with presence masks (audit #13) takes 2C channels;
    # building for C loads NOTHING silently -- load_state_dict rejects the first conv -- but the
    # error it raises names a tensor shape, not the cause. Say the cause.
    chans = ck.get("channels")
    if chans is not None and getattr(model, "c_in", None) is not None:
        want_c = len(chans) * (2 if ck.get("mask_channels") else 1)
        if int(model.c_in) != want_c:
            raise ValueError(
                f"architecture mismatch{' in ' + where if where else ''}: this model takes "
                f"{model.c_in} input channels, the checkpoint was trained on {len(chans)} value "
                f"channel(s){' plus a presence mask for each' if ck.get('mask_channels') else ''} "
                f"= {want_c}. Build with c_in=dataset.input_channels(ck['channels'], "
                f"ck.get('mask_channels', False)) and a GriddedPatches with the same "
                f"mask_channels.")

    # Day-of-year geo channels (E-INV-00 leg L1). A checkpoint written before this field carries
    # no `doy_channels` key -- nothing to compare, so this passes rather than inventing a
    # constraint, exactly as the pool_signature block above does.
    want_doy = ck.get("doy_channels")
    if want_doy is not None and getattr(model, "doy_channels", None) is not None:
        if bool(model.doy_channels) != bool(want_doy):
            raise ValueError(
                f"architecture mismatch{' in ' + where if where else ''}: this model was built "
                f"with doy_channels={model.doy_channels} ({model.n_geo} geo channels), the "
                f"checkpoint was trained with doy_channels={bool(want_doy)}. The geo-channel width "
                f"differs, so load_state_dict would reject the first conv with a shape error whose "
                f"cause is this flag. Build the model with doy_channels=ck['doy_channels'].")

    want = ck.get("pool_signature")
    if want is None:
        return
    got = temporal_pool_signature(model)
    if list(want) != list(got):
        raise ValueError(
            f"architecture mismatch{' in ' + where if where else ''}: this model pools time as "
            f"{got}, the checkpoint was trained as {list(want)}. load_state_dict would ACCEPT this "
            f"silently and the model would predict differently on identical input. Rebuild with "
            f"t_seq=ck['built_t_seq'] ({ck.get('built_t_seq')}), not ck['T_SEQ'] "
            f"({ck.get('T_SEQ')}) -- T_SEQ is the DATA window, not the construction value.")


# --------------------------------------------------------------- physics-informed terms


def gradient_loss(mu, y, mask, y_mean, y_std, depths, max_depth_m=None):
    """Error in the VERTICAL GRADIENT of temperature, degC^2 per m^2. Optional, off by default.

    A model can hit the right temperature at every level and still be wrong about the thing an
    oceanographer reads a profile for: it can smear a sharp thermocline into a gentle slope and
    lose almost nothing on RMSE, because RMSE scores levels independently and never asks whether
    the SHAPE between them survived. This term asks.

        L_grad = mean[ (dT_hat/dz - dT/dz)^2 ]

    IN PHYSICAL UNITS, AND THE REASON IS NOT COSMETIC
    `dataset.py:94-96` computes y_mean and y_std PER DEPTH. So a z-scored difference between two
    levels is not a scaled physical gradient -- it mixes two different scalings -- and a term built
    on it would weight depths by the ratio of their standard deviations, which is meaningless. Both
    prediction and truth are returned to degC first, exactly as `density_nll` does and for exactly
    the same reason.

    AND THE SPACING IS DIVIDED OUT
    `config.DEPTHS` runs 5 m apart at the surface and 300 m apart at the bottom. A bare
    `diff(T)` penalty would be ~60x more sensitive across the 700-1000 m gap than across 0-5 m,
    purely because of where the levels happen to sit. Dividing by dz makes it a gradient rather
    than a difference.

    A level pair counts only when BOTH its levels are valid: a gradient spanning the seafloor is
    not a gradient.
    """
    t_pred = mu * y_std + y_mean
    t_true = y * y_std + y_mean
    dz = depths[1:] - depths[:-1]
    g_pred = (t_pred[..., 1:] - t_pred[..., :-1]) / dz
    g_true = (t_true[..., 1:] - t_true[..., :-1]) / dz
    m = (mask[..., 1:] & mask[..., :-1]).float()
    if max_depth_m is not None:
        # Count a level pair only when its SHALLOWER level is at or above the cap. This is leg L2:
        # A27 measured the flattening in the top ~30 m, so protecting the whole 0-1000 m column with
        # one weight lets the deep thermocline (which is already faithful) dominate the term.
        shallow = (depths[:-1] <= float(max_depth_m)).float()
        m = m * shallow
    n = m.sum().clamp(min=1.0)
    return (((g_pred - g_true) ** 2) * m).sum() / n


def sign_loss(mu, y, mask, y_mean, y_std, depths, max_depth_m=100.0, min_step=0.2):
    """Penalise predicting the WRONG SIGN of the vertical temperature gradient near the surface.

    This is the inversion term (E-INV-00 leg L3). RMSE and even `gradient_loss` are both symmetric:
    they punish a gradient that is too steep exactly as much as one that points the wrong way. But
    the Bay of Bengal's winter signature is a matter of DIRECTION -- cold water sitting on warm --
    and a model that has learned "warm surface implies warm below" fails by getting the sign
    backwards, not the magnitude. This term asks only the direction question, and only where the
    truth has a real gradient to have a direction.

        for each valid level pair above max_depth_m whose TRUTH step |dT| >= min_step degC:
            L += ReLU( - sign(dT_true) * dT_pred/dz )      # >0 only when the signs disagree
        L_sign = mean over those pairs

    Physical degC/m, de-normalised per depth for the same reason as `gradient_loss`. A pair counts
    only when both levels are valid (never across the seafloor) and its shallower level is at or
    above the cap (the inversion lives in the top ~100 m; below it the ordinary thermocline would
    swamp the signal). `min_step` gates out flat, noise-level gradients whose sign is meaningless.
    """
    t_pred = mu * y_std + y_mean
    t_true = y * y_std + y_mean
    dz = depths[1:] - depths[:-1]
    g_pred = (t_pred[..., 1:] - t_pred[..., :-1]) / dz
    dt_true = t_true[..., 1:] - t_true[..., :-1]
    g_true = dt_true / dz

    pair = (mask[..., 1:] & mask[..., :-1]).float()
    pair = pair * (depths[:-1] <= float(max_depth_m)).float()
    pair = pair * (dt_true.abs() >= float(min_step)).float()      # a real gradient to get right

    wrong = torch.relu(-torch.sign(g_true) * g_pred)              # 0 unless the signs disagree
    n = pair.sum().clamp(min=1.0)
    return (wrong * pair).sum() / n


def stability_penalty(mu_t, mu_s, mask, y_mean, y_std, s_mean, s_std, depths):
    """Penalise a predicted column where density DECREASES with depth. Stage 2 only.

        L_stab = mean[ ReLU( -d(rho_hat)/dz ) ]

    In a resting ocean water gets denser downward. A profile with lighter water beneath heavier is
    not a subtle error -- it is a column that would overturn immediately, and no amount of RMSE can
    say so because each level is individually plausible. This term says it directly.

    IT USES ONLY THE PREDICTION. There is no truth term: static stability is a property the answer
    must have, not a quantity to match. That also means it can be non-zero on a model whose RMSE is
    excellent, which is the entire point of measuring it.

    STAGE 2 ONLY, because density needs salinity at depth and stage 1 predicts temperature alone.
    The same S_FLOOR clamp `density_nll` documents applies: EOS-80's S**1.5 is NaN below zero, one
    NaN poisons every gradient in the batch, and an untrained salinity head does emit negatives.
    `stability_penalty.last_n_clamped` is recorded for the same reason -- a term leaning on the
    clamp is doing less than it appears to.
    """
    t_pred = mu_t * y_std + y_mean
    s_raw = mu_s * s_std + s_mean
    s_pred = s_raw.clamp(min=S_FLOOR)
    stability_penalty.last_n_clamped = int((s_raw < S_FLOOR).sum())

    rho = seawater.density_torch(s_pred, t_pred)
    dz = depths[1:] - depths[:-1]
    drho = (rho[..., 1:] - rho[..., :-1]) / dz
    m = (mask[..., 1:] & mask[..., :-1]).float()
    n = m.sum().clamp(min=1.0)
    # ReLU of the NEGATIVE gradient: zero wherever density increases downward, positive exactly
    # where it does not. A signed mean would let a strongly stable column pay for an unstable one.
    return (torch.relu(-drho) * m).sum() / n


stability_penalty.last_n_clamped = 0
