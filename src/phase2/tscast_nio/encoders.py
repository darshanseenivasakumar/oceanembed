"""The four bake-off candidates for the satellite embedding encoder (PS requirement 9).

Every encoder maps (x_patch, x_geo) -> a latent vector of the SAME width, and the bake-off bolts
the SAME decoding head onto each. So the only thing that varies between candidates is the encoder,
which is the only way the comparison means anything.

GNN is deliberately absent. Our grid is a uniform 0.25 deg lat/lon lattice, not an irregular mesh
or a sensor network, so message passing over it reduces to convolution with extra machinery and no
graph structure to exploit. Stated plainly rather than built to tick a box.

  MLPControl  -- centre cell only, NO spatial context. The incumbent's information set, and the
                 control that answers "does a spatial embedding help AT ALL?"
  CNN3D       -- the paper's: 3-D residual blocks, Mish activation, average pooling.
  CNNAttention-- CNN stem, then self-attention across the surviving spatial tokens.
  ViT         -- patchify to tokens, CLS token, transformer encoder.
"""
from __future__ import annotations

import torch
import torch.nn as nn


def _with_geo(x: torch.Tensor, x_geo: torch.Tensor) -> torch.Tensor:
    """(B,C,T,P,P) + (B,3,1,P,P) -> (B,C+3,T,P,P); geo is constant along the time axis."""
    return torch.cat([x, x_geo.expand(-1, -1, x.shape[2], -1, -1)], dim=1)


class _Res3D(nn.Module):
    """3-D residual block: conv -> Mish -> conv -> +skip -> Mish. The paper's building block."""

    def __init__(self, c_in: int, c_out: int):
        super().__init__()
        self.a = nn.Conv3d(c_in, c_out, 3, padding=1)
        self.b = nn.Conv3d(c_out, c_out, 3, padding=1)
        self.skip = nn.Conv3d(c_in, c_out, 1) if c_in != c_out else nn.Identity()
        self.act = nn.Mish()
        self.norm = nn.GroupNorm(1, c_out)

    def forward(self, x):
        h = self.act(self.a(x))
        h = self.norm(self.b(h))
        return self.act(h + self.skip(x))


class MLPControl(nn.Module):
    """Centre cell only. No neighbours, no spatial structure -- the incumbent's information."""

    def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128):
        super().__init__()
        self.c = p // 2
        d = (c_in + 3) * t_seq
        # Deliberately WIDE. The control must lose on INFORMATION (no neighbours), never on
        # capacity -- otherwise "spatial context helps" is indistinguishable from "bigger helps".
        self.net = nn.Sequential(nn.Linear(d, 512), nn.Mish(),
                                 nn.Linear(512, 512), nn.Mish(),
                                 nn.Linear(512, latent))

    def forward(self, x, x_geo):
        z = _with_geo(x, x_geo)[:, :, :, self.c, self.c]      # (B, C+3, T)
        return self.net(z.flatten(1))


class CNN3D(nn.Module):
    """The paper's satellite feature encoder, at bake-off scale."""

    def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128,
                 widths=(24, 48, 96)):
        super().__init__()
        blocks, c, t, s = [], c_in + 3, t_seq, p
        for w in widths:
            blocks.append(_Res3D(c, w))
            pt = 2 if t >= 2 else 1
            ps = 2 if s >= 2 else 1
            blocks.append(nn.AvgPool3d((pt, ps, ps)))
            c, t, s = w, max(1, t // pt), max(1, s // ps)
        self.body = nn.Sequential(*blocks)
        self.pool = nn.AdaptiveAvgPool3d(1)
        self.out = nn.Linear(widths[-1], latent)

    def forward(self, x, x_geo):
        h = self.body(_with_geo(x, x_geo))
        return self.out(self.pool(h).flatten(1))


class CNNAttention(nn.Module):
    """CNN stem, then self-attention over the remaining spatial tokens."""

    def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128,
                 widths=(32, 96), heads: int = 4):
        super().__init__()
        blocks, c, t, s = [], c_in + 3, t_seq, p
        for w in widths:
            blocks.append(_Res3D(c, w))
            pt = 2 if t >= 2 else 1
            ps = 2 if s >= 2 else 1
            blocks.append(nn.AvgPool3d((pt, ps, ps)))
            c, t, s = w, max(1, t // pt), max(1, s // ps)
        self.body = nn.Sequential(*blocks)
        self.dim = widths[-1]
        self.attn = nn.MultiheadAttention(self.dim, heads, batch_first=True)
        self.norm = nn.LayerNorm(self.dim)
        self.out = nn.Linear(self.dim, latent)

    def forward(self, x, x_geo):
        h = self.body(_with_geo(x, x_geo))                    # (B, D, t, s, s)
        b, d = h.shape[0], h.shape[1]
        tok = h.flatten(2).transpose(1, 2)                    # (B, N, D)
        a, _ = self.attn(tok, tok, tok, need_weights=False)
        return self.out(self.norm(tok + a).mean(1))


class ViT(nn.Module):
    """Patchify -> tokens -> transformer encoder. Global attention from layer one."""

    def __init__(self, c_in: int, t_seq: int, p: int, latent: int = 128,
                 dim: int = 96, depth: int = 3, heads: int = 4, patch: int = 4):
        super().__init__()
        self.stem = nn.Conv3d(c_in + 3, dim, kernel_size=(t_seq, patch, patch),
                              stride=(1, patch, patch))
        n_tok = (p // patch) ** 2
        self.cls = nn.Parameter(torch.zeros(1, 1, dim))
        self.pos = nn.Parameter(torch.zeros(1, n_tok + 1, dim))
        nn.init.trunc_normal_(self.pos, std=0.02)
        nn.init.trunc_normal_(self.cls, std=0.02)
        layer = nn.TransformerEncoderLayer(dim, heads, dim * 4, batch_first=True,
                                           norm_first=True, dropout=0.0)
        self.enc = nn.TransformerEncoder(layer, depth, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(dim)
        self.out = nn.Linear(dim, latent)

    def forward(self, x, x_geo):
        h = self.stem(_with_geo(x, x_geo))                    # (B, dim, 1, p', p')
        tok = h.flatten(2).transpose(1, 2)                    # (B, N, dim)
        tok = torch.cat([self.cls.expand(tok.shape[0], -1, -1), tok], 1) + self.pos
        return self.out(self.norm(self.enc(tok))[:, 0])


class ProfileHead(nn.Module):
    """Shared decoding head. IDENTICAL across candidates so the encoder is the only variable."""

    def __init__(self, latent: int, n_depths: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(latent, 256), nn.Mish(), nn.Linear(256, n_depths))

    def forward(self, z):
        return self.net(z)


class Candidate(nn.Module):
    def __init__(self, encoder: nn.Module, latent: int, n_depths: int):
        super().__init__()
        self.encoder = encoder
        self.head = ProfileHead(latent, n_depths)

    def forward(self, x, x_geo):
        return self.head(self.encoder(x, x_geo))


ENCODERS = {"mlp_control": MLPControl, "cnn3d": CNN3D,
            "cnn_attention": CNNAttention, "vit": ViT}


def build(name: str, c_in: int, t_seq: int, p: int, n_depths: int, latent: int = 128) -> Candidate:
    if name not in ENCODERS:
        raise KeyError(f"unknown encoder {name!r}; have {sorted(ENCODERS)}")
    return Candidate(ENCODERS[name](c_in, t_seq, p, latent=latent), latent, n_depths)


def n_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)
