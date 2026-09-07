"""Build OceanEmbed_SIH26066_IDEA.pptx -- the official SIH idea-submission deck.

Five slides, in the structure and visual language of the reference winning deck:
Proposed Solution / Technical Approach / Feasibility and Viability / Impact and Benefits /
Research and References.

This is a SECOND artifact. OceanEmbed_SIH26066.pptx (the 12-slide pitch deck) is untouched.

EVERY HEADLINE NUMBER IS READ FROM artifacts/frozen_manifest.json, never typed here. A re-freeze
that moves a number therefore moves the slide too, and _guard() refuses to write a deck that
quotes a retracted result or the GLORYS-fed comparator's metrics.

Design spec: docs/superpowers/specs/2026-09-07-sih-idea-deck-design.md
Run:  python scripts/deck/build_idea_slides.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

import diagrams

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANIFEST = os.path.join(REPO, "artifacts", "frozen_manifest.json")
DECK = os.path.join(REPO, "OceanEmbed_SIH26066_IDEA.pptx")

# ---------------------------------------------------------------- the two placeholders
#: The reference deck's oval reads "Tech Pioneers". Nothing in this repo records ours.
TEAM_NAME = ("TEAM", "NAME")
PROJECT = "OceanEmbed"
PS_ID = "SIH26066"

# ---------------------------------------------------------------- palette
INK = RGBColor.from_string("12232B")
HEAD_BLUE = RGBColor.from_string("1F4E79")
VIOLET = RGBColor.from_string("7030A0")
GREY = RGBColor.from_string("6B7C87")
BLACK = RGBColor.from_string("000000")
TEAL = RGBColor.from_string("1D7874")

BODY_FONT = "Calibri"
TITLE_FONT = "Times New Roman"
SYM_FONT = "Segoe UI Symbol"  # has ❖ (U+2756) and ➤ (U+27A4)

#: Numbers this deck must never contain. Same list test_presentation_claims.py guards the old deck
#: with: the three pre-embargo T_SEQ legs, and the GLORYS-fed comparator's metrics.
FORBIDDEN = {
    "0.9267": "pre-embargo T_SEQ 31 leg (INVALID_PRE_EMBARGO.md, 'never quote')",
    "0.8529": "pre-embargo T_SEQ leg, checkpoint overwritten",
    "0.9096": "pre-embargo T_SEQ leg, checkpoint overwritten",
    "0.8873": "tscast_stage1_embargo_withUV_s42 -- the GLORYS comparator, not the deliverable",
    "0.8548": "stage-2 GLORYS run -- reanalysis inputs, fails the PS satellite-only clause",
}


# ================================================================ numbers
def load_numbers() -> dict[str, str]:
    """Read every quotable figure straight out of the frozen manifest."""
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    c = m["claims"][m["deliverable_key"]]
    assert c["deliverable"] is True, "manifest deliverable_key does not point at the deliverable"
    assert c["input_source"] == "satellite", "the deliverable must be the satellite-input model"

    # Per-depth claims come from the metrics artifact the manifest names, so "14 of 15" and the
    # thermocline peak cannot survive a rescore that changes them.
    with open(os.path.join(REPO, "artifacts", c["metrics_file"]), encoding="utf-8") as f:
        per_all = json.load(f)
    per = per_all["metrics"]
    depths, rmse, clim = per["depths_m"], per["rmse"], per["rmse_climatology"]
    wins = sum(1 for r, k in zip(rmse, clim) if r < k)
    band = [(d, r) for d, r in zip(depths, rmse) if 50 <= d <= 150]
    peak_d, peak_r = max(band, key=lambda t: t[1])

    return {
        "rmse": f"{c['overall_rmse']:.2f}",
        "bias": f"+{c['overall_bias']:.2f}",
        "corr": f"{c['overall_correlation']:.2f}",
        "skill": f"{c['overall_skill_rmse_ratio'] * 100:.0f}%",
        "n": f"{c['overall_n']:,}",
        "profiles": f"{c['argo_profiles']:,}",
        "depths": str(c["n_depths"]),
        "tseq": str(c["T_SEQ"]),
        "channels": str(len(c["channels"])),
        "leak": f"{c['selection_leak']['measured_cost_degC']:.2f}",
        "wins": str(wins),
        "peak_rmse": f"{peak_r:.2f}",
        "peak_depth": str(peak_d),
        "band_lo": f"{min(r for _, r in band):.2f}",
        "params": f"{round((per_all['n_params_encoder'] + per_all['n_params_decoder']) / 1000)}k",
        "train_min": f"{per_all['train_seconds'] / 60:.0f}",
        "device": "GPU" if per_all["device"] == "cuda" else per_all["device"].upper(),
    }


def _collect_test_count() -> str | None:
    """How many tests the suite actually collects, right now.

    A hardcoded count is the exact kind of claim this repo keeps getting burned by -- "530
    passing" came from a freeze block and was already 500 short. Collection takes ~15 s and is
    worth it. Returns None if pytest cannot run, and the slide then makes no numeric claim.
    """
    import subprocess

    py = os.path.join(REPO, ".venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = sys.executable
    try:
        out = subprocess.run([py, "-m", "pytest", "tests", "-q", "--collect-only"],
                             cwd=REPO, capture_output=True, text=True, timeout=180).stdout
    except Exception:
        return None
    hit = re.search(r"(\d+) tests? collected", out)
    return f"{int(hit.group(1)):,}" if hit else None


N = load_numbers()
TESTS = _collect_test_count()
TESTS = f"{TESTS} tests" if TESTS else None

# ================================================================ content
SOLUTION = [
    ("Comprehensive OceanEmbed Subsurface Platform:",
     f"A web dashboard and reproducible pipeline that reconstructs daily ocean temperature at "
     f"{N['depths']} depths from 0 to 1000 m across the North Indian Ocean, using surface "
     f"observations alone."),
    ("Satellite-Only Input:",
     "Runs on OSTIA sea-surface temperature, DUACS altimetry, SMOS-blended salinity, GLOBCURRENT "
     "surface currents and observational winds — no in-situ float is needed at prediction time, "
     "which is what makes it operational every single day."),
    ("TS-Cast-NIO Model:",
     f"A 3-D CNN compresses an {N['tseq']}-day window of {N['channels']} surface maps into a "
     f"128-number ocean embedding, and a decoder expands it into a full temperature profile — "
     f"{N['params']} parameters, kept deliberately small for the data available."),
    ("Uncertainty on Every Value:",
     "The model predicts a spread alongside each temperature, so the product states where it "
     "should not be trusted, instead of showing one confident number everywhere."),
    ("Independent Validation:",
     f"Scored against {N['profiles']} Argo float profiles never seen in training — {N['rmse']} °C "
     f"RMSE over {N['n']} comparisons, {N['skill']} better than climatology, and better at "
     f"{N['wins']} of the {N['depths']} depths."),
    ("Derived Ocean Products:",
     "Mixed-layer depth, thermocline depth, cyclone heat potential (TCHP / D26), eddy and "
     "upwelling detection, and anomaly maps — all computed from the reconstructed profile, "
     "never assumed."),
    ("Observation-Priority Map:",
     "The uncertainty field ranks where the ocean is least known, turning a gap in knowledge into "
     "a concrete answer to where the next Argo float should be deployed."),
]

STACK = [
    ("Languages & Core:", "Python 3.12, NumPy, pandas, PyArrow, PyYAML."),
    ("Ocean Data:", "xarray, netCDF4, SciPy, copernicusmarine (CMEMS), argopy, erddapy."),
    ("AI / ML:", f"PyTorch — 3-D CNN encoder + depth decoder, {N['params']} parameters; scikit-learn; "
                 "LightGBM baseline and quantile uncertainty; CUDA."),
    ("Frontend & Visualisation:", "Streamlit — 15 feature modules behind one lazy registry; "
                                  "Plotly; Matplotlib."),
    ("API & Export:", "FastAPI, Uvicorn, and NetCDF / CSV / Parquet export."),
    ("Reproducibility & Testing:", f"pytest — {TESTS or 'a suite'} covering the code and the "
                                   f"claims; Git; ruff; seeded configs; and a SHA-256-verified "
                                   f"frozen checkpoint manifest."),
]

FEAS_LEFT = [
    ("head", "Feasibility", "2E75B6"),
    ("1.", "Technical:", "Already built end-to-end — 388 gap-free days of satellite input, a "
                         "trained model, and a running instrument. Not a proposal."),
    ("2.", "Economic:", f"Every input is free and open. CMEMS and Argo cost nothing, training "
                        f"takes about {N['train_min']} minutes on one {N['device']}, and "
                        f"inference runs on a laptop."),
    ("3.", "Operational:", "The satellite L4 products are published daily and operationally, so "
                           "the pipeline runs forward in near-real-time with no in-situ input."),
    ("head", "Viability", "2E9E5B"),
    ("4.", "Scales beyond the pilot:", "The architecture is region-agnostic — retargeting to "
                                       "another basin is a data-bundle change, not a redesign."),
    ("5.", "Reproducible and auditable:", f"Seed, config and a SHA-256-verified checkpoint are "
                                          f"frozen in a manifest, with {TESTS or 'a test suite'} "
                                          f"that guard the claims as well as the code."),
    ("head", "Challenges", "C55A11"),
    ("6.", "The thermocline is the hard layer:", f"Error runs {N['band_lo']}–{N['peak_rmse']} °C "
                                                 f"through 50–150 m, peaking at {N['peak_depth']} m "
                                                 f"where temperature falls fastest with depth."),
    ("7.", "Uncertainty is improved, not calibrated:", "Coverage runs below nominal in the mixed "
                                                       "layer. We report the shortfall rather "
                                                       "than widening the band to hide it."),
    ("8.", "Epoch selection was not independent:", f"The shipped epoch was chosen on the test "
                                                   f"period; a leak-free protocol costs "
                                                   f"+{N['leak']} °C over three seeds, and we "
                                                   f"say so."),
    ("9.", "INCOIS gridded Argo is unreachable:", "Their data layer is down, so validation uses "
                                                  "individual argopy floats instead."),
    ("head", "Use Cases", "7030A0"),
    ("10.", "Cyclone intensity:", "upper-100 m heat content, the fuel term a surface map cannot "
                                  "see."),
    ("11.", "Monsoon & fisheries:", "Bay of Bengal stratification and Arabian Sea upwelling, "
                                    "both subsurface."),
    ("12.", "Next-float targeting & assimilation:", "an uncertainty-ranked map of where the ocean "
                                                    "is least known."),
]

FEAS_RIGHT = [
    ("head", "Deployment Potential", "2E75B6"),
    ("1.", "Hand-off to INCOIS / IMD:", "Output is a daily NetCDF field on a standard grid — "
                                        "directly ingestible by existing forecast and "
                                        "assimilation chains."),
    ("2.", "Zero licence cost:", "Open Copernicus and Argo data on an open-source stack. Nothing "
                                 "proprietary to renew."),
    ("3.", "Fisheries & naval advisories:", "The same profile drives potential-fishing-zone and "
                                            "sonar-range products Indian agencies already issue."),
    ("4.", "Research platform:", "Frozen seeds, checkpoints and an export API make it a base "
                                 "others extend, not a one-off demo."),
    ("head", "Solutions", "2E9E5B"),
    ("5.", "Robust data & protocol:", f"388 gap-free days, a 5-day embargo between train and "
                                      f"test, scored on {N['profiles']} floats never seen in "
                                      f"training."),
    ("6.", "Modular integration:", "15 lazily-loaded feature modules behind one registry — a "
                                   "broken feature contains itself instead of downing the "
                                   "instrument."),
    ("7.", "Refusal over invention:", "Below the seafloor the model returns nothing rather than a "
                                      "number, and the scorer declines those depths too."),
]

AUDIENCE = [
    ("INCOIS & IMD:", "A daily subsurface field with an uncertainty band — an input their cyclone "
                      "and ocean-state forecasts currently lack at this cadence."),
    ("Fisheries & coastal communities:", "Thermocline and mixed-layer depth drive fishing zones; "
                                         "a daily profile sharpens advisories that today rest on "
                                         "surface temperature alone."),
    ("Indian Navy & shipping:", "Sound-speed structure follows the temperature profile, feeding "
                                "sonar-range and routing decisions directly."),
    ("Ocean researchers & the Argo programme:", "A quantitative, defensible answer to where the "
                                                "next float is worth deploying."),
    ("Disaster management agencies:", "Upper-ocean heat is the fuel term in rapid cyclone "
                                      "intensification — the failure mode that costs the most "
                                      "lives on this coast."),
]

BENEFITS = [
    ("Social:", "6E8B5E", [
        "Better cyclone-intensity input for the most densely populated cyclone basin.",
        "Sharper fishing-zone advisories for small-scale fishers who cannot afford a wasted trip.",
        "Uncertainty shown on screen, so an advisory can state its own confidence instead of "
        "implying certainty.",
    ]),
    ("Scientific / Technological:", "C0504D", [
        "Targets the North Indian Ocean, where most published work targets the Pacific.",
        "An uncertainty head trained jointly with temperature, not bolted on afterwards.",
        "Negative results published beside positive ones — the FiLM decoder and the density loss "
        "were both measured harmful and dropped.",
    ]),
    ("Economic:", "7C61A8", [
        "Zero data-licensing cost: Copernicus and Argo are open, and so is the stack.",
        f"About {N['train_min']} minutes of {N['device']} training and laptop-class inference — "
        f"no cluster required.",
        "Targets Argo deployment, the most expensive part of ocean observation, at the cells "
        "where information is scarcest.",
    ]),
    ("Environmental:", "3E8E4F", [
        "Monitors ocean heat content, the dominant store of excess planetary heat.",
        "Sees subsurface heat and upwelling structure that surface-only monitoring is blind to.",
        "Reduces redundant ship survey by targeting where observation actually adds information.",
    ]),
]

PAPERS = [
    ("Meng et al., 2021.", "Reconstruction of Three-Dimensional Temperature and Salinity Fields "
                           "From Satellite Observations. JGR: Oceans. doi:10.1029/2021JC017605"),
    ("TS-Cast, 2026.", "Deep Learning for Subsurface Ocean Reconstruction from Satellite "
                       "Observations in the Northwestern Pacific. Ocean Science 22, 2161."),
    ("DORS, 2022.", "Subsurface Temperature Reconstruction for the Global Ocean from 1993 to 2020 "
                    "Using Satellite Observations and Deep Learning. Remote Sensing 14(13), 3198. "
                    "doi:10.3390/rs14133198"),
    ("FFPG-net, 2025.", "Feature fusion with physical guidance for subsurface thermal structure "
                        "reconstruction."),
    ("NeSPReSO, 2025.", "PCA + neural network subsurface prediction, Gulf of Mexico."),
]

SOURCES = [
    ("Surface inputs (Copernicus Marine):", "OSTIA sea-surface temperature; DUACS L4 altimetry "
                                            "(cmems_obs-sl_glo_phy-ssh); SMOS-blended salinity "
                                            "(cmems_obs-mob_glo_phy-sss); GLOBCURRENT total "
                                            "currents (cmems_obs-mob_glo_phy-cur); L4 wind "
                                            "(cmems_obs-wind_glo_phy)."),
    ("Training target:", "GLORYS12V1 reanalysis, cmems_mod_glo_phy_my_0.083deg_P1D."),
    ("Independent validation:", f"Argo float profiles via argopy — {N['profiles']} profiles, "
                                f"{N['n']} depth comparisons, never seen in training."),
    ("Problem statement:", f"{PS_ID}, Ministry of Earth Sciences — subsurface temperature from "
                           f"daily surface observations, North Indian Ocean, 0.25°."),
]

CAVEAT = ("Citation discipline: the five papers above are reviewed at abstract level "
          "(docs/LITERATURE_MATRIX.md). They are cited here for existence and general approach "
          "only. No numerical comparison against their published results appears anywhere in "
          "this deck.")


# ================================================================ drawing helpers
def _tb(slide, x, y, w, h):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def _p(tf, first, *, space_after=6, space_before=0, indent=0.0, line=1.0):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(space_after)
    p.space_before = Pt(space_before)
    p.line_spacing = line
    if indent:
        # python-pptx has no paragraph_format; a hanging indent is marL + a negative indent on
        # the <a:pPr> element itself, in EMU.
        emu = int(Inches(indent))
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(emu))
        pPr.set("indent", str(-emu))
    return p


def _r(p, text, *, size, bold=False, color=INK, font=BODY_FONT, underline=False):
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    run.font.underline = underline
    return run


def _chrome(slide, title):
    """Border, team oval, centred serif title, SIH logo placeholder. On every slide."""
    border = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.10), Inches(0.10),
                                    Inches(13.13), Inches(7.30))
    border.fill.background()
    border.line.color.rgb = BLACK
    border.line.width = Pt(1.75)
    border.shadow.inherit = False

    oval = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.32), Inches(0.20),
                                  Inches(1.62), Inches(0.80))
    oval.fill.background()
    oval.line.color.rgb = VIOLET
    oval.line.width = Pt(1.5)
    oval.shadow.inherit = False
    tf = oval.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, word in enumerate(TEAM_NAME):
        p = _p(tf, i == 0, space_after=0)
        p.alignment = PP_ALIGN.CENTER
        _r(p, word, size=11.5, bold=True)

    t = _tb(slide, 2.10, 0.22, 9.13, 0.85)
    p = _p(t, True, space_after=0)
    p.alignment = PP_ALIGN.CENTER
    _r(p, title, size=36, bold=True, font=TITLE_FONT)

    logo = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.30), Inches(0.20),
                                  Inches(1.83), Inches(0.92))
    logo.fill.background()
    logo.line.color.rgb = RGBColor.from_string("BFBFBF")
    logo.line.width = Pt(1.0)
    logo.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    logo.shadow.inherit = False
    tf = logo.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = _p(tf, True, space_after=0, line=0.95)
    p.alignment = PP_ALIGN.CENTER
    _r(p, "PASTE OFFICIAL\nSIH 2026 LOGO", size=8.5, bold=True,
       color=RGBColor.from_string("A6A6A6"))


def _section(slide, x, y, text, *, size=24, w=8.0):
    tf = _tb(slide, x, y, w, 0.48)
    p = _p(tf, True, space_after=0)
    _r(p, "❖", size=size, bold=True, color=HEAD_BLUE, font=SYM_FONT)
    _r(p, " " + text, size=size, bold=True, color=HEAD_BLUE, underline=True)


def _bullets(tf, items, *, size, marker="➤", indent=0.30, space=8, lead_size=None):
    """The reference deck's bullet: marker, bold lead-in label, then a regular sentence."""
    for i, (lead, rest) in enumerate(items):
        p = _p(tf, i == 0, space_after=space, indent=indent)
        _r(p, marker + "  ", size=size * 0.85, color=INK, font=SYM_FONT)
        _r(p, lead + " ", size=lead_size or size, bold=True)
        _r(p, rest, size=size)


def _numbered(tf, rows, *, size, space=4):
    """Grouped, continuously numbered items with a coloured group heading -- slide 3's pattern."""
    first = True
    for kind, a, b in rows:
        if kind == "head":
            p = _p(tf, first, space_after=3, space_before=0 if first else 8)
            _r(p, "■ ", size=size + 1.5, color=RGBColor.from_string(b), font=SYM_FONT)
            _r(p, a, size=size + 1.5, bold=True, color=RGBColor.from_string(b))
        else:
            p = _p(tf, first, space_after=space, indent=0.26)
            _r(p, kind + " ", size=size, bold=True, color=GREY)
            _r(p, a + " ", size=size, bold=True)
            _r(p, b, size=size)
        first = False


def _pic(slide, name, x, y, w):
    path = os.path.join(REPO, "artifacts", "deck", name)
    return slide.shapes.add_picture(path, Inches(x), Inches(y), width=Inches(w))


# ================================================================ slides
def slide_solution(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _chrome(s, PROJECT)
    _section(s, 0.42, 1.12, "Proposed Solution")
    _bullets(_tb(s, 0.52, 1.68, 7.35, 5.58), SOLUTION, size=12.0)
    _pic(s, "arch.png", 8.15, 1.22, 4.85)
    return s


def slide_technical(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _chrome(s, "TECHNICAL APPROACH")
    _section(s, 0.42, 1.10, "Technology Stack")
    tf = _tb(s, 0.52, 1.68, 6.95, 4.30)
    for i, (lead, rest) in enumerate(STACK):
        p = _p(tf, i == 0, space_after=11)
        _r(p, lead + " ", size=13, bold=True)
        _r(p, rest, size=13)
    _pic(s, "chips.png", 7.75, 1.45, 5.25)

    cap = _tb(s, 0.42, 5.92, 12.55, 0.26)
    p = _p(cap, True, space_after=0)
    _r(p, "METHODOLOGY AND PROCESS FOR IMPLEMENTATION", size=9.5, bold=True, color=GREY)
    _pic(s, "flow.png", 0.42, 6.22, 12.55)
    return s


def slide_feasibility(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _chrome(s, "FEASIBILITY AND VIABILITY")
    _numbered(_tb(s, 0.35, 1.10, 6.30, 6.15), FEAS_LEFT, size=9.5)
    _numbered(_tb(s, 6.85, 1.10, 6.25, 3.60), FEAS_RIGHT, size=9.5)
    _pic(s, "facts.png", 6.85, 4.78, 6.25)
    return s


def slide_impact(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _chrome(s, "IMPACT AND BENEFITS")
    _pic(s, "tree.png", 0.40, 1.08, 6.20)

    _section(s, 0.40, 3.66, "Potential impact on the target audience:", size=16, w=6.4)
    _bullets(_tb(s, 0.45, 4.14, 6.15, 3.10), AUDIENCE, size=10, marker="•", indent=0.20,
             space=6)

    _section(s, 6.85, 1.08, "Benefits of the solution", size=20, w=6.2)
    tf = _tb(s, 6.90, 1.64, 6.15, 5.60)
    first = True
    for head, col, lines in BENEFITS:
        p = _p(tf, first, space_after=3, space_before=0 if first else 7)
        _r(p, head, size=12, bold=True, color=RGBColor.from_string(col))
        first = False
        for line in lines:
            q = _p(tf, False, space_after=2, indent=0.18)
            _r(q, "•  ", size=9.5, color=GREY)
            _r(q, line, size=9.5)
    return s


def slide_references(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _chrome(s, "RESEARCH AND REFERENCES")
    _section(s, 0.42, 1.10, "Key literature", size=19, w=6.0)
    tf = _tb(s, 0.52, 1.66, 6.30, 4.60)
    for i, (lead, rest) in enumerate(PAPERS):
        p = _p(tf, i == 0, space_after=10, indent=0.22)
        _r(p, "▸  ", size=10, color=TEAL, font=SYM_FONT)
        _r(p, lead + " ", size=10.5, bold=True)
        _r(p, rest, size=10.5)

    _section(s, 7.05, 1.10, "Data and problem statement", size=19, w=6.0)
    tf = _tb(s, 7.15, 1.66, 5.90, 4.10)
    for i, (lead, rest) in enumerate(SOURCES):
        p = _p(tf, i == 0, space_after=10, indent=0.22)
        _r(p, "▸  ", size=10, color=TEAL, font=SYM_FONT)
        _r(p, lead + " ", size=10.5, bold=True)
        _r(p, rest, size=10.5)

    note = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.52), Inches(6.20),
                              Inches(12.51), Inches(0.92))
    note.fill.solid()
    note.fill.fore_color.rgb = RGBColor.from_string("FFF6E8")
    note.line.color.rgb = RGBColor.from_string("E0913A")
    note.shadow.inherit = False
    tf = note.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.16)
    p = _p(tf, True, space_after=0)
    _r(p, CAVEAT, size=10.5, color=RGBColor.from_string("6B4415"))
    return s


# ================================================================ guard + build
def _guard(prs):
    """Refuse to write a deck that quotes a retracted number or the wrong model's metrics."""
    text = []
    for s in prs.slides:
        for sh in s.shapes:
            if sh.has_text_frame:
                text.append(sh.text_frame.text)
    blob = "\n".join(text)

    for bad, why in FORBIDDEN.items():
        if bad in blob:
            raise AssertionError(f"deck quotes {bad} -- {why}")

    for key, val in (("rmse", N["rmse"]), ("profiles", N["profiles"]), ("n", N["n"])):
        if val not in blob:
            raise AssertionError(f"deck never states the manifest {key} ({val}) -- guard vacuous")

    if f"{N['wins']} of the {N['depths']} depths" not in blob:
        raise AssertionError("the depth-win qualifier is missing or stale")
    if int(N["wins"]) >= int(N["depths"]):
        raise AssertionError("climatology beaten at every depth -- verify before claiming it")
    return blob


def main() -> int:
    diagrams.build_all()

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for fn in (slide_solution, slide_technical, slide_feasibility, slide_impact,
               slide_references):
        fn(prs)

    blob = _guard(prs)
    prs.save(DECK)

    print(f"wrote {DECK}")
    print(f"  {len(prs.slides)} slides  ·  {os.path.getsize(DECK):,} bytes")
    print(f"  headline from manifest: RMSE {N['rmse']} °C, skill {N['skill']}, "
          f"{N['profiles']} profiles, n={N['n']}")
    print(f"  {len(blob):,} characters of slide text, no forbidden figure present")
    print(f"  PLACEHOLDERS TO FILL: team name {TEAM_NAME!r}, and the SIH logo on all 5 slides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
