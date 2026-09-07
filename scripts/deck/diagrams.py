"""Render the five diagrams for the SIH idea-submission deck.

Every figure is written to artifacts/deck/ as a PNG and placed by build_idea_slides.py.

WHY MATPLOTLIB AND NOT POWERPOINT SHAPES
The user chose raster diagrams. They are faster to iterate on and match how the reference deck
was made (its architecture panel is plainly an exported drawing). The cost is that they are not
editable in PowerPoint -- re-run this script to change one.

There is no Office renderer on this machine, so these PNGs are also the only part of the deck that
can be inspected visually. They are ordinary images; the slides around them are checked
programmatically.
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "deck"))

# ---------------------------------------------------------------- palette
NAVY = "#0B3C5D"
TEAL = "#1D7874"
BLUE = "#4A90B8"
PALE = "#EDF3F7"
GREY = "#5A6B76"
INK = "#12232B"
LINE = "#9FB3C0"


def _font() -> str:
    """First installed font from our preference list. Calibri matches the reference deck."""
    have = {f.name for f in fm.fontManager.ttflist}
    for name in ("Calibri", "Segoe UI", "Arial", "DejaVu Sans"):
        if name in have:
            return name
    return "DejaVu Sans"


FONT = _font()


def _fig(w: float, h: float):
    fig = plt.figure(figsize=(w, h), dpi=220)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _box(ax, x0, y0, x1, y1, *, fc, ec, lw=1.2, r=0.018, z=2):
    p = FancyBboxPatch(
        (x0, y0),
        x1 - x0,
        y1 - y0,
        boxstyle="round,pad=0,rounding_size=%s" % r,
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        zorder=z,
    )
    ax.add_patch(p)
    return p


def _txt(ax, x, y, s, *, size, color=INK, weight="normal", ha="center", va="center", z=4):
    ax.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va,
            family=FONT, zorder=z)


def _circle(ax, fig, x, y, ry, *, fc, ec, lw=1.6, z=5):
    """A visually round circle. The axes are 0-1 on both sides, so x must be squashed by the
    figure's own aspect or the result is an ellipse."""
    w, h = fig.get_size_inches()
    from matplotlib.patches import Ellipse
    e = Ellipse((x, y), width=2 * ry * (h / w), height=2 * ry,
                facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z)
    ax.add_patch(e)
    return e


def _arrow(ax, x0, y0, x1, y1, *, color=GREY, lw=1.4, z=1):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                 mutation_scale=11, color=color, linewidth=lw, zorder=z))


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, facecolor="white", edgecolor="none")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- 1. architecture
def architecture() -> str:
    """Sources -> preprocess -> model -> output -> validate -> serve -> three outcome cards.

    Same read as the reference deck's panel: inputs at the top, one highlighted processing block
    in the middle, a user-facing surface at the bottom, outcome cards last.
    """
    fig, ax = _fig(4.85, 5.75)

    _box(ax, 0.02, 0.885, 0.98, 0.975, fc=PALE, ec=BLUE, lw=1.0)
    _txt(ax, 0.5, 0.955, "SATELLITE OBSERVATIONS  ·  daily L4", size=7.4, color=NAVY,
         weight="bold")

    srcs = ["SST", "SSH", "SSS", "CURRENTS", "WIND"]
    xs = [0.115, 0.295, 0.475, 0.665, 0.875]
    for x, s in zip(xs, srcs):
        w = 0.085 if len(s) <= 4 else 0.105
        _box(ax, x - w, 0.897, x + w, 0.938, fc="white", ec=BLUE, lw=1.0, r=0.012)
        _txt(ax, x, 0.9175, s, size=6.6, color=NAVY, weight="bold")
        _arrow(ax, x, 0.893, x, 0.864, lw=1.0)

    ax.plot([0.115, 0.875], [0.862, 0.862], color=LINE, lw=1.2, zorder=1)
    _arrow(ax, 0.5, 0.862, 0.5, 0.826)

    _box(ax, 0.05, 0.745, 0.95, 0.822, fc="white", ec=LINE)
    _txt(ax, 0.5, 0.799, "PREPROCESS", size=6.8, color=GREY, weight="bold")
    _txt(ax, 0.5, 0.771, "regrid to 0.25°  ·  11-day window  ·  5-day embargo", size=7.2)
    _arrow(ax, 0.5, 0.743, 0.5, 0.700)

    _box(ax, 0.03, 0.565, 0.97, 0.697, fc=TEAL, ec=TEAL, lw=1.6)
    _txt(ax, 0.5, 0.664, "TS-Cast-NIO", size=10.4, color="white", weight="bold")
    _txt(ax, 0.5, 0.628, "3-D CNN encoder  →  128-number embedding", size=7.4, color="#D9F0EE")
    _txt(ax, 0.5, 0.600, "→  depth decoder  ·  549k parameters", size=7.4, color="#D9F0EE")
    _arrow(ax, 0.5, 0.563, 0.5, 0.520)

    _box(ax, 0.05, 0.435, 0.95, 0.517, fc="white", ec=NAVY, lw=1.4)
    _txt(ax, 0.5, 0.494, "OUTPUT", size=6.8, color=GREY, weight="bold")
    _txt(ax, 0.5, 0.464, "15 depths, 0–1000 m  ·  T ± σ  ·  100 × 240 cells",
         size=7.2, weight="bold")
    _arrow(ax, 0.5, 0.433, 0.5, 0.390)

    _box(ax, 0.05, 0.305, 0.95, 0.387, fc="#FFF6E8", ec="#E0913A", lw=1.2)
    _txt(ax, 0.5, 0.364, "INDEPENDENT VALIDATION", size=6.8, color="#A9631B", weight="bold")
    _txt(ax, 0.5, 0.334, "962 Argo profiles never seen in training", size=7.2)
    _arrow(ax, 0.5, 0.303, 0.5, 0.262)

    _box(ax, 0.05, 0.180, 0.95, 0.259, fc=NAVY, ec=NAVY, lw=1.4)
    _txt(ax, 0.5, 0.219, "Streamlit instrument  +  NetCDF / CSV export API", size=7.6,
         color="white", weight="bold")

    cards = [("Cyclone heat", "TCHP · D26"), ("Validation lab", "per-depth error"),
             ("Priority map", "where to sample")]
    cx = [0.055, 0.365, 0.675]
    for x0, (head, sub) in zip(cx, cards):
        _arrow(ax, x0 + 0.135, 0.178, x0 + 0.135, 0.145, lw=1.0)
        _box(ax, x0, 0.030, x0 + 0.270, 0.140, fc=PALE, ec=BLUE, lw=1.0)
        ax.plot([x0 + 0.012, x0 + 0.012], [0.044, 0.126], color=TEAL, lw=2.6, zorder=3)
        _txt(ax, x0 + 0.148, 0.100, head, size=7.0, color=NAVY, weight="bold")
        _txt(ax, x0 + 0.148, 0.066, sub, size=6.4, color=GREY)

    return _save(fig, "arch.png")


# ---------------------------------------------------------------- 2. tech chips
CHIPS = [
    ("Python", "#3776AB"), ("PyTorch", "#EE4C2C"), ("NumPy", "#4D77CF"), ("pandas", "#3B1E63"),
    ("xarray", "#1E7B8C"), ("SciPy", "#5A7FC4"), ("scikit-learn", "#E07B15"),
    ("LightGBM", "#5E9A28"), ("Streamlit", "#E63A3A"), ("Plotly", "#3F4F75"),
    ("Matplotlib", "#11557C"), ("FastAPI", "#059486"), ("Uvicorn", "#3E5A5A"),
    ("netCDF4", "#1F6FEB"), ("Copernicus", "#0B5394"), ("Argo", "#D2691E"),
    ("pytest", "#0B84C4"), ("Git", "#E24329"), ("CUDA", "#5E9400"),
]


def chips() -> str:
    """A grid of brand-coloured chips. Stands in for the reference deck's logo cloud.

    Deliberately not real logos: they are trademarks we hold no licensed copy of, and a drawn
    lookalike would be worse than a clean label.
    """
    fig, ax = _fig(5.05, 4.45)

    # 7 rows of 3, sized to fill the panel top to bottom rather than trailing off two-thirds down.
    cols, gap_x = 3, 0.325
    top, bottom, ch = 0.955, 0.045, 0.100
    rows = -(-len(CHIPS) // cols)
    pitch = (top - bottom - ch) / (rows - 1)
    for i, (name, col) in enumerate(CHIPS):
        r, c = divmod(i, cols)
        lx = 0.030 + c * gap_x
        ly = top - r * pitch
        _box(ax, lx, ly - ch, lx + 0.295, ly, fc=col + "1F", ec=col, lw=1.6, r=0.016)
        ax.plot([lx + 0.022, lx + 0.022], [ly - ch + 0.020, ly - 0.020], color=col, lw=3.6,
                zorder=3)
        size = 9.4 if len(name) <= 10 else 8.3
        _txt(ax, lx + 0.040, ly - ch / 2, name, size=size, color=col, weight="bold", ha="left")

    return _save(fig, "chips.png")


# ---------------------------------------------------------------- 3. methodology strip
STEPS = ["Download\nCMEMS + Argo", "Regrid to\n0.25° daily", "Window 11 d\n5-day embargo",
         "Train 3-D CNN\nseed 42", "Score vs\n962 Argo", "Freeze checkpoint\nSHA-256",
         "Serve dashboard\n+ export API"]


def flow() -> str:
    """The implementation pipeline as chevrons. The rubric asks for this; the reference omits it."""
    # Short on purpose: the official template's content band stops at y=6.88 (the footer bar
    # starts at 6.95), so a taller strip would sit under the footer.
    fig, ax = _fig(12.40, 0.75)

    n = len(STEPS)
    pad, notch, edge = 0.006, 0.020, 0.004
    span = 1.0 - 2 * edge
    w = (span - pad * (n - 1)) / n
    for i, label in enumerate(STEPS):
        left = edge + i * (w + pad)
        right = left + w
        fc = "#12506E" if i / (n - 1) < 0.5 else TEAL
        pts = [(left, 0.88), (right - notch, 0.88), (right, 0.5), (right - notch, 0.12),
               (left, 0.12), (left + (notch if i else 0), 0.5)]
        ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor="white", lw=1.4, zorder=2))
        _txt(ax, (left + right) / 2 + 0.004, 0.50, label, size=7.5, color="white", weight="bold")

    return _save(fig, "flow.png")


# ---------------------------------------------------------------- 4. supporting facts
FACTS = [
    "Argo delivers ~962 profiles per quarter across a basin that needs ~24,000 values every "
    "single day\n— a coverage gap only reconstruction can close.",
    "Our own heat-content field peaks at 173 kJ/cm² with the 26 °C isotherm at 105 m "
    "— cyclone fuel\nthat lives entirely below the surface, where a satellite cannot see it.",
    "Surface-to-subsurface deep learning is established (Meng 2021, TS-Cast 2026, DORS 2022).\n"
    "The contribution here is a validated, uncertainty-carrying system for the North Indian Ocean.",
]


def facts() -> str:
    """The green supporting-facts card, mirroring the reference deck's."""
    fig, ax = _fig(6.05, 2.10)

    _box(ax, 0.060, 0.04, 0.985, 0.96, fc="#2F9E5E", ec="#25804B", lw=1.4, r=0.05)
    _txt(ax, 0.535, 0.888, "Supporting facts for feasibility and viability",
         size=9.4, color="white", weight="bold")

    _circle(ax, fig, 0.060, 0.50, 0.150, fc="white", ec="#25804B")
    ax.text(0.060, 0.487, "✓", fontsize=17, color="#2F9E5E", fontweight="bold",
            ha="center", va="center", family="DejaVu Sans", zorder=6)

    for i, line in enumerate(FACTS):
        _txt(ax, 0.150, 0.755 - i * 0.226, line, size=6.6, color="white", ha="left", va="top")

    return _save(fig, "facts.png")


# ---------------------------------------------------------------- 5. benefits tree
BRANCHES = [("Social", "safer coasts,\nsharper advisories", "#6E8B5E"),
            ("Scientific", "open method,\nnegative results kept", "#D9736B"),
            ("Economic", "zero licence cost,\ntargeted float spend", "#8E76B0"),
            ("Environmental", "ocean heat content,\nless redundant survey", "#4F9E5C")]


def tree() -> str:
    """Benefits-of-the-solution tree: one root, four branches."""
    fig, ax = _fig(6.0, 2.35)

    _box(ax, 0.275, 0.760, 0.725, 0.960, fc="#E8853C", ec="#C96A26", lw=1.4, r=0.045)
    _txt(ax, 0.5, 0.860, "Benefits of the solution", size=10.4, color="white", weight="bold")

    ax.plot([0.5, 0.5], [0.758, 0.660], color=GREY, lw=1.4, zorder=1)
    ax.plot([0.135, 0.865], [0.660, 0.660], color=GREY, lw=1.4, zorder=1)

    for i, (name, sub, col) in enumerate(BRANCHES):
        cx = 0.135 + i * (0.730 / 3)
        _arrow(ax, cx, 0.660, cx, 0.545, lw=1.3)
        _box(ax, cx - 0.113, 0.075, cx + 0.113, 0.540, fc=col, ec=col, lw=1.2, r=0.040)
        _txt(ax, cx, 0.405, name, size=9.6, color="white", weight="bold")
        _txt(ax, cx, 0.215, sub, size=6.8, color="#F2F6F1")

    return _save(fig, "tree.png")


def build_all() -> list[str]:
    return [architecture(), chips(), flow(), facts(), tree()]


if __name__ == "__main__":
    for p in build_all():
        print("wrote", p)
