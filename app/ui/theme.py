"""Colour tokens and the motion layer for the OceanEmbed instrument.

OWNER: Unit A (Arjhun). NOT a page -- it must never call st.set_page_config, or
tests/phase2/test_launch_ports.py will class it as one and demand a port.

WHY THERE IS CSS HERE AT ALL
.streamlit/config.toml already carries the palette, radii, borders and fonts, so every port
inherits the theme without a line of CSS. What config.toml cannot express is MOTION and a few
typographic details that separate an instrument from a dashboard template:

  * tabular figures on every number, so digits stop jittering as a date is scrubbed
  * the entrance transition that makes switching features feel like one application
    rather than sixteen pages
  * the skeleton shimmer that covers a 32-second field reconstruction

MOTION HAS ONE RULE HERE AND IT IS NOT NEGOTIABLE
Containers animate. NUMBERS DO NOT. A metric that counts up to its value looks like it is being
invented, which is precisely the impression this project cannot afford in front of a domain
judge. So every keyframe below moves opacity and position; none of them touches a digit.
"""
from __future__ import annotations

# ---- ground ---------------------------------------------------------------------------
ABYSS = "#060B14"     # page
DEEP = "#0D1526"      # card / panel
SHELF = "#141F35"     # elevated, hover
EDGE = "#1E2C47"      # 1px borders

# ---- ink ------------------------------------------------------------------------------
INK = "#E6EDF7"
INK_DIM = "#8B9BB4"
INK_FAINT = "#56657F"

# ---- signal: at most TWO visible on one screen ----------------------------------------
CYAN = "#22D3EE"      # live / interactive / primary
AZURE = "#38BDF8"     # selection, focus
AMBER = "#FB923C"     # attention, uncertainty, caveat
MINT = "#34D399"      # pass / verified
CORAL = "#F87171"     # fail / high anomaly

#: Non-data ground. Land and sea floor are not low values -- they are ABSENCES, and
#: painting them from the value scale makes the map claim a temperature where there is
#: no water. Flat, distinct, and outside every colour ramp used for data.
LAND = "#1A2333"
FLOOR = "#0A1220"

#: Sequential, for temperature. Plotly's built-in Thermal -- cmocean is NOT installed on this
#: machine, so naming cmocean.thermal here would be a dependency that fails on demo day.
SEQ_TEMPERATURE = "Thermal"

#: Sequential, for uncertainty. Distinct from temperature on purpose: the two are shown side by
#: side and must never be mistaken for one another.
SEQ_UNCERTAINTY = "Magma"

#: Diverging, for anomaly ONLY. The pale midpoint MUST be pinned to zero (cmid=0) or "neutral"
#: lands on whatever the data's midpoint happens to be -- measured at -2.40 degC on one real
#: field, which would have painted a 2.4 degC cold anomaly as normal.
#:
#: Redefined here rather than imported from app/phase2/cube_page.py, which calls
#: st.set_page_config at import time and would fire it during shell construction.
BLUE_PURPLE_DIVERGING = [
    [0.00, "rgb(8,48,107)"],
    [0.25, "rgb(66,146,198)"],
    [0.50, "rgb(247,247,247)"],
    [0.75, "rgb(140,107,177)"],
    [1.00, "rgb(74,20,134)"],
]

#: Altair's equivalent of the above, for the fallback 2-D views.
DIVERGING_RANGE = ["rgb(8,48,107)", "rgb(247,247,247)", "rgb(74,20,134)"]

#: Categorical, for "model vs Argo vs climatology" style series. Cyan first because the model is
#: the subject; mint for observed truth; amber for a comparator.
CATEGORICAL = [CYAN, MINT, AMBER, AZURE, CORAL, INK_DIM]


CSS = """
<style>
/* ---------------------------------------------------------------- motion */
@keyframes oe-rise   { from { opacity:0; transform: translateY(14px); }
                       to   { opacity:1; transform: translateY(0); } }
@keyframes oe-fade   { from { opacity:0; } to { opacity:1; } }
@keyframes oe-sweep  { from { background-position: -420px 0; }
                       to   { background-position:  420px 0; } }
@keyframes oe-breathe{ 0%,100% { opacity:.55; } 50% { opacity:1; } }

/* The stage: every time a feature is selected Streamlit rebuilds this subtree, so the
   entrance transition re-fires for free and switching reads as one application. */
.st-key-oe_stage { animation: oe-rise .42s cubic-bezier(.22,.61,.36,1) both; }

/* Staggered reveal. Depth 1..6 is plenty -- beyond that the delay is felt as lag. */
.st-key-oe_stage > div > div:nth-child(1) { animation: oe-rise .40s .02s cubic-bezier(.22,.61,.36,1) both; }
.st-key-oe_stage > div > div:nth-child(2) { animation: oe-rise .40s .06s cubic-bezier(.22,.61,.36,1) both; }
.st-key-oe_stage > div > div:nth-child(3) { animation: oe-rise .40s .10s cubic-bezier(.22,.61,.36,1) both; }
.st-key-oe_stage > div > div:nth-child(4) { animation: oe-rise .40s .14s cubic-bezier(.22,.61,.36,1) both; }
.st-key-oe_stage > div > div:nth-child(5) { animation: oe-rise .40s .18s cubic-bezier(.22,.61,.36,1) both; }
.st-key-oe_stage > div > div:nth-child(6) { animation: oe-rise .40s .22s cubic-bezier(.22,.61,.36,1) both; }

/* ------------------------------------------------------- numbers hold still */
/* Tabular figures everywhere a value is shown. Digits that change width as a date scrubs are
   the cheapest tell of an amateur dashboard, and no theme option can express this. */
[data-testid="stMetricValue"], [data-testid="stMetric"], .oe-num, code,
[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; font-feature-settings:"tnum"; }

/* Explicitly NOT animated: a metric that transitions to its new value looks fabricated. */
[data-testid="stMetricValue"] { transition: none !important; }

/* ---------------------------------------------------------------- chrome */
/* Reclaim the dead band above the title -- this is a dense instrument, not a landing page. */
.block-container { padding-top: 2.2rem !important; padding-bottom: 3rem !important; }
[data-testid="stAppDeployButton"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }

/* --------------------------------------------------------------- top bar */
.oe-bar { display:flex; align-items:center; gap:14px; flex-wrap:wrap;
          padding:10px 16px; margin:0 0 14px 0;
          border:1px solid #1E2C47; border-radius:10px; background:#0D1526;
          animation: oe-fade .5s both; }
.oe-word { font-weight:650; letter-spacing:.14em; font-size:15px; color:#E6EDF7; }
.oe-chip { font-size:11px; letter-spacing:.09em; padding:3px 9px; border-radius:999px;
           border:1px solid #1E2C47; color:#8B9BB4; white-space:nowrap; }
.oe-chip-live { color:#060B14; background:#22D3EE; border-color:#22D3EE; font-weight:650; }
.oe-chip-cached { color:#38BDF8; border-color:#38BDF8; }
.oe-chip-warn { color:#FB923C; border-color:#FB923C; }
.oe-chip-ok { color:#34D399; border-color:#34D399; }
.oe-dot { display:inline-block; width:6px; height:6px; border-radius:50%;
          background:#22D3EE; margin-right:6px; animation: oe-breathe 2.4s infinite; }

/* ------------------------------------------------------------ stat tiles */
.oe-tiles { display:flex; gap:10px; flex-wrap:wrap; margin:2px 0 6px 0; }
.oe-tile { flex:1 1 150px; padding:12px 14px; border:1px solid #1E2C47; border-radius:10px;
           background:#0D1526; transition: background .15s ease, border-color .15s ease;
           animation: oe-rise .45s both; }
.oe-tile:hover { background:#141F35; border-color:#22D3EE; }
.oe-tile-l { font-size:11px; letter-spacing:.08em; color:#8B9BB4; margin-bottom:6px; }
.oe-tile-v { font-size:30px; font-weight:500; letter-spacing:-.02em; color:#E6EDF7;
             font-variant-numeric: tabular-nums; line-height:1.1;
             font-family:'JetBrains Mono','Cascadia Mono',Consolas,monospace; }
.oe-tile-u { font-size:12px; color:#8B9BB4; margin-left:5px; font-weight:400; }
.oe-tile-s { font-size:11px; color:#56657F; margin-top:5px; }

/* --------------------------------------------------------------- section */
.oe-h { display:flex; align-items:baseline; gap:10px; margin:20px 0 2px 0; }
.oe-h-n { font-size:11px; letter-spacing:.14em; color:#22D3EE; font-weight:650; }
.oe-h-t { font-size:17px; font-weight:600; color:#E6EDF7; }
.oe-h-s { font-size:13px; color:#8B9BB4; margin:0 0 10px 0; }

/* -------------------------------------------------------------- skeleton */
.oe-skel { border-radius:10px; border:1px solid #1E2C47;
           background:#0D1526 linear-gradient(90deg,#0D1526 0%,#1B2740 50%,#0D1526 100%);
           background-size:420px 100%; animation: oe-sweep 1.25s linear infinite; }

/* ------------------------------------------------------------ feature rail */
/* Active chip marked by a cyan left border, never a filled background -- a filled pill on a
   dark ground competes with the data for attention. */
div[data-testid="stButton"] > button { transition: all .15s ease; }
div[data-testid="stButton"] > button:hover { border-color:#22D3EE; color:#22D3EE; }

/* ---------------------------------------------------------------- respect */
@media (prefers-reduced-motion: reduce) {
  .st-key-oe_stage, .st-key-oe_stage > div > div, .oe-tile, .oe-bar { animation: none !important; }
  .oe-skel { animation: none !important; }
  .oe-dot  { animation: none !important; }
}
</style>
"""


def inject() -> None:
    """Apply the motion layer. Called ONCE, from main.py, right after set_page_config."""
    import streamlit as st
    st.html(CSS)


def plotly_layout(height: int = 620) -> dict:
    """Layout that makes a Plotly figure belong to the page instead of sitting on it.

    Plotly's default is a white card with its own font; dropped into a dark instrument it reads
    as a screenshot pasted in from somewhere else.
    """
    return dict(
        height=height,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK_DIM, size=12,
                  family="Inter, -apple-system, Segoe UI, sans-serif"),
        legend=dict(bgcolor="rgba(13,21,38,.8)", bordercolor=EDGE, borderwidth=1),
    )


def scene_axes(x: str, y: str, z: str, aspect: dict) -> dict:
    """3-D scene styling: real tick labels on every axis.

    A 3-D plot without axis labels is decoration, not science -- a judge cannot tell a basin
    from a blob without knowing which way is north and how deep the bottom is.
    """
    # `titlefont` was REMOVED in plotly 6; this machine runs 7.0. The nested form below is the
    # only one that works, and the old spelling raises rather than being ignored.
    ax = dict(showbackground=True, backgroundcolor=DEEP, gridcolor=EDGE,
              zerolinecolor=EDGE, color=INK_DIM)
    font = dict(color=INK_DIM, size=11)
    return dict(
        xaxis=dict(title=dict(text=x, font=font), **ax),
        yaxis=dict(title=dict(text=y, font=font), **ax),
        zaxis=dict(title=dict(text=z, font=font), **ax),
        aspectmode="manual",
        aspectratio=dict(x=aspect["x"], y=aspect["y"], z=aspect["z"]),
        # Oblique and CLOSE. Far-away default framing left the basin as a small block in a
        # large empty canvas; a low eye also reads as a volume rather than a map.
        camera=dict(eye=dict(x=1.35, y=-1.5, z=0.52),
                    center=dict(x=0, y=0, z=-0.08)),
    )


def altair_theme() -> dict:
    """Registered as the default Altair theme so 2-D charts match without per-chart styling."""
    return {
        "config": {
            "background": "transparent",
            "font": "Inter, -apple-system, Segoe UI, sans-serif",
            "view": {"stroke": "transparent"},
            "axis": {"domainColor": EDGE, "gridColor": EDGE, "gridOpacity": 0.45,
                     "tickColor": EDGE, "labelColor": INK_DIM, "titleColor": INK_DIM,
                     "labelFontSize": 11, "titleFontSize": 12, "titleFontWeight": 500},
            "legend": {"labelColor": INK_DIM, "titleColor": INK_DIM,
                       "labelFontSize": 11, "titleFontSize": 11},
            "title": {"color": INK, "fontSize": 14, "fontWeight": 600},
            "range": {"category": CATEGORICAL},
        }
    }

CSS += """
<style>
.oe-tbl { width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }
.oe-tbl th { text-align:left; font-size:11px; letter-spacing:.08em; color:#56657F;
             font-weight:500; padding:6px 10px 6px 0; border-bottom:1px solid #1E2C47; }
.oe-tbl td { padding:7px 10px 7px 0; border-bottom:1px solid rgba(30,44,71,.5);
             color:#E6EDF7; vertical-align:top; }
.oe-tbl tr:last-child td { border-bottom:none; }
.oe-tbl tr { transition: background .12s ease; }
.oe-tbl tr:hover td { background:rgba(20,31,53,.6); }
.oe-sym { font-family:'JetBrains Mono','Cascadia Mono',Consolas,monospace; color:#22D3EE;
          white-space:nowrap; font-size:13px; }
.oe-dim { color:#8B9BB4; font-size:12px; }
</style>
"""
