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

from phase2.tscast_nio import config, encoders as E

LOGVAR_MIN, LOGVAR_MAX = -7.0, 7.0     # sigma in roughly [0.03, 33] degC after unscaling


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
    """Stage 1: 7 (or 5) surface channels + climatology prior -> 15 depths + per-depth log-var."""

    def __init__(self, encoder_name: str, c_in: int, t_seq: int = None, p: int = None,
                 latent: int = None, residual: bool = True, unet_channels=None):
        super().__init__()
        t_seq = int(config.T_SEQ if t_seq is None else t_seq)
        p = int(config.P if p is None else p)
        latent = int(config.LATENT_DIM if latent is None else latent)

        self.encoder = E.ENCODERS[encoder_name](c_in, t_seq, p, latent=latent)
        self.encoder_name = encoder_name
        self.decoder = ClimatologyUNet(latent, widths=unet_channels)
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


def build(encoder_name: str, c_in: int, **kw) -> TSCastNIO:
    return TSCastNIO(encoder_name, c_in, **kw)
