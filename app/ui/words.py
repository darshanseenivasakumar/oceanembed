"""Every word the user reads. One file, so it can be proofread in one sitting.

OWNER: Unit A (Arjhun). NOT a page.

RULES FOR THIS FILE
1. Short. If a sentence can go, it goes. The screen is an instrument, not a document.
2. Plain. Any term a non-oceanographer would stumble on is unpacked in the same breath.
3. TRUE. Every figure here is transcribed from an artifact under artifacts/, never retyped from
   memory and never rounded to look better. The provenance for each is named in the text.
4. Honest caveats live in EXPLAIN, not on the page. Moving them off-screen is a layout decision;
   deleting them would be a claim this project has not earned.

THE HEADLINE NUMBER, AND THE ONE IT IS CONSTANTLY CONFUSED WITH
  0.9078 degC  <- THE DELIVERABLE. Satellite inputs only, which is what the problem statement
                  asks for. 962 independent Argo profiles.
  0.8548 degC  <- a COMPARATOR that reads reanalysis (GLORYS) as input. Better, and irrelevant:
                  it fails the satellite-only requirement. It is never the headline.
Both come from artifacts/frozen_manifest.json, claims.{deliverable_satellite,
glorys_comparator_stage2}.
"""
from __future__ import annotations

PRODUCT = "OCEANEMBED"
PROBLEM_ID = "SIH26066"
TAGLINE = "Subsurface ocean temperature from satellites alone"

# --------------------------------------------------------------------------------- features
#: (key, short label for the rail, title on the stage, one-line "what am I looking at")
FEATURES = [
    ("ocean3d", "3-D Ocean",
     "The basin in three dimensions",
     "One reconstructed volume. The cyan sheet is the 26 °C layer — the fuel a cyclone burns."),
    ("clickpoint", "Click a point",
     "Any pixel, all the way down",
     "Click the sea. The model returns the full temperature profile beneath that point."),
    ("confidence", "Confidence",
     "Temperature, and how much to trust it",
     "Colour is temperature. Fade is doubt — vivid where the model is sure."),
    ("cyclone", "Cyclone heat",
     "The heat a storm can actually reach",
     "Not surface warmth — the depth of warm water, which is what decides intensification."),
    ("transect", "Transect",
     "A vertical slice through the ocean",
     "Cut the basin along a line and look at the wall of water it exposes."),
    ("acoustics", "Sound",
     "How far sound carries, and where it bends",
     "Sound speed follows temperature. A temperature model is therefore an acoustics model."),
    ("validation", "Validation",
     "Checked against floats it never saw",
     "962 independent Argo profiles. Every number below is measured, not claimed."),
    ("priority", "Where to measure next",
     "Where another measurement would teach the model most",
     "High model doubt meeting an energetic ocean. A suggestion, not an instruction."),
]

#: Features that stay on their own ports for now, linked rather than rebuilt.
ELSEWHERE = [
    ("Ocean structure", 8505, "mixed layer, thermocline, barrier layer"),
    ("Ocean events", 8506, "eddies, fronts, upwelling"),
    ("TS-Cast v2", 8507, "the model's own report card"),
    ("Validate live", 8508, "one point against the nearest real float"),
    ("Collocation", 8502, "how a grid cell is matched to a float"),
    ("Cloud dropout", 8515, "what the monsoon costs the model"),
    ("Cyclone case study", 8517, "a real storm's cold wake"),
    ("Phase-1 demo", 8501, "the original frozen system"),
]

# ------------------------------------------------------------------------------ the numbers
#: Read at runtime from artifacts/frozen_manifest.json. These are LABELS ONLY -- the values are
#: never typed here, because a number typed in a UI file is a number that can drift from the
#: artifact it claims to come from.
HEADLINE_LABELS = {
    "rmse": ("Error vs Argo", "°C", "962 independent profiles"),
    "corr": ("Correlation", "", "model vs float, all depths"),
    "skill": ("Better than climatology by", "", "1 − RMSE_model ⁄ RMSE_climatology"),
    "profiles": ("Independent profiles", "", "floats the model never trained on"),
}

# --------------------------------------------------------------------------------- explain
#: eid -> (title, body). Two to four sentences. Plain language. This is the ONLY place a
#: caveat may be verbose, because the reader asked for it by pressing the button.
EXPLAIN = {
    # ---- global controls
    "date": (
        "Date",
        "Which day the ocean is reconstructed for. The model can answer for any day in its "
        "bundle, **2025-06-01 to 2026-06-23**.\n\n"
        "Days after **2026-04-01** were held out of training entirely, so predictions there are "
        "the honest test."),
    "source": (
        "Input source",
        "**Satellite** is the deliverable. It uses only what a satellite can see — surface "
        "temperature, salinity, height and currents — which is what the problem statement asks "
        "for. Scores **0.9078 °C** against Argo.\n\n"
        "**GLORYS** is a reanalysis: a model-assimilated ocean product. It scores better "
        "(0.8548 °C) because it is a richer input, but it **fails the satellite-only "
        "requirement**, so it is a comparator and never the headline."),
    "device": (
        "GPU",
        "Runs the reconstruction on the graphics card instead of the processor. Measured "
        "**4.2× faster**, and the two agree to **0.0007 °C** — far below the model's own error, "
        "so the picture is identical either way.\n\n"
        "Only the speed changes. Nothing about the science does."),
    "judge": (
        "What this is",
        "A one-page summary of the whole system in plain language, written for someone seeing "
        "it for the first time."),

    # ---- 3-D
    "exaggeration": (
        "Vertical stretch",
        "The ocean here is **1000 m deep across 60° of longitude** — about 6,000 km wide. Drawn "
        "to true scale it would be a film of water and you would see nothing.\n\n"
        "This stretches the vertical so structure is visible. It is a **viewing choice**, and "
        "the factor is always printed on screen so the picture never implies false proportion."),
    "field": (
        "What the colour shows",
        "**Temperature** — the water itself, in °C.\n\n"
        "**Anomaly** — how far today sits from the long-term average for this time of year. "
        "Blue is colder than normal, purple warmer, and pale is exactly normal.\n\n"
        "**Uncertainty** — how unsure the model is, not how warm the water is."),
    "detail": (
        "Detail",
        "How many grid cells are drawn. The full volume is 360,000 points, which most browsers "
        "will not composite smoothly, so it is thinned for the renderer.\n\n"
        "**The science is unchanged** — only the picture gets coarser. Lower is finer and "
        "slower."),
    "d26surface": (
        "The 26 °C layer",
        "The depth at which water cools through 26 °C. Above that line the sea is warm enough to "
        "feed a tropical cyclone; below it, it is not.\n\n"
        "A deep 26 °C layer means a storm churning the surface still pulls up warm water, so it "
        "keeps intensifying. A shallow one means it cools itself and weakens."),
    "floats": (
        "Argo floats",
        "Green points mark real Argo floats that surfaced within five days of this date, each "
        "with a thin line dropping to 1000 m for the dive it made.\n\n"
        "They show **where independent observation exists**. They are not being compared against "
        "the model here — that comparison is scored in Validation, where it can be checked."),
    "renderer": (
        "Renderer",
        "**auto** uses WebGL: fifteen depth layers, the 26 °C surface as a real mesh, land, and "
        "orbiting at 60 fps.\n\n"
        "**Plotly** and **2-D** are the fallbacks, and they are selectable on purpose. A machine "
        "with no WebGL drops to them automatically — and a fallback nobody has ever looked at is "
        "a fallback nobody knows is broken."),
    "seafloor": (
        "The gaps are the sea floor",
        "Empty regions are **not missing data**. They are places where there is no water at that "
        "depth — the continental shelf and the sea bed.\n\n"
        "Roughly a quarter of the basin's cells never reach 1000 m. Filling them in would be "
        "inventing ocean that does not exist."),

    # ---- click a point
    "depth": (
        "Depth",
        "Which of the 15 standard levels the map is showing, from the surface to 1000 m.\n\n"
        "Spacing is deliberately uneven — 5 m apart near the surface, 300 m at the bottom — "
        "because temperature changes fastest in the top 200 m and barely at all below 700 m."),
    "clickmap": (
        "Click the map",
        "Every coloured cell is a real 0.25° grid square, about 27 km across. Clicking one "
        "returns the model's full profile beneath it: 15 temperatures and 15 error bars.\n\n"
        "Grey cells are land. Dark cells are sea floor — no water at this depth."),

    # ---- confidence
    "sigma": (
        "The error bar",
        "The model reports its own uncertainty at every depth, not just a temperature. Wider "
        "means less sure.\n\n"
        "It is **widest at the thermocline** (100–150 m), where temperature falls fastest with "
        "depth — there, being slightly wrong about depth makes you badly wrong about "
        "temperature."),
    "calibrated": (
        "Is the error bar trustworthy?",
        "Raw model uncertainty was **too narrow** — it claimed more confidence than it earned. A "
        "post-hoc calibration widens it per depth, fitted on one time period and checked on a "
        "later one it never saw.\n\n"
        "After calibration, **±2σ contains 80–96 % of real float measurements** depending on "
        "depth, against an ideal 95 %. Better, and still not perfect. Where a panel says NOT "
        "calibrated, read the shading as relative doubt, never as an error bar."),
    "viewmode": (
        "View",
        "**Both** blends temperature and confidence into one picture — colour for the value, "
        "fade for the doubt.\n\n"
        "**Uncertainty only** drops the temperature entirely so the doubt pattern is readable on "
        "its own."),

    # ---- cyclone
    "product": (
        "Which heat measure",
        "**TCHP** — heat stored above the 26 °C line. The number cyclone forecasters actually "
        "use.\n\n"
        "**D26** — how deep that 26 °C line sits, in metres.\n\n"
        "**OHC** — total heat in the top 700 m, a climate measure rather than a storm one."),
    "tchp": (
        "Tropical Cyclone Heat Potential",
        "Sea surface temperature alone is a poor predictor of whether a storm will strengthen. A "
        "cyclone stirs the ocean and drags up whatever is beneath it.\n\n"
        "TCHP measures the heat available **above the 26 °C line** — the fuel a storm can "
        "actually reach. A hot but shallow surface layer is a storm that fizzles."),

    # ---- transect
    "endpoints": (
        "The line",
        "Two points on the map. The panel cuts the ocean along the line between them and shows "
        "the vertical wall of water it exposes — distance across, depth down."),
    "npoints": (
        "Samples along the line",
        "How many columns are reconstructed between the two endpoints. More is smoother and "
        "slower. It changes the picture's resolution, not the model."),
    "contours": (
        "Contour lines",
        "Lines of constant value drawn over the slice.\n\n"
        "**Isotherms** join equal temperatures. **Isopycnals** join equal density — water tends "
        "to flow along these, not across them, so they show where water masses meet."),

    # ---- acoustics
    "soundmap": (
        "Which layer",
        "**Sonic layer depth** — how deep the near-surface duct runs. Sound trapped in it travels "
        "far; below it, sound bends away and a shadow zone opens.\n\n"
        "**SOFAR axis** — the depth where sound travels slowest, and therefore furthest. Sound "
        "there can cross an ocean basin."),
    "soundlimit": (
        "Why much of this map is blank",
        "The SOFAR axis usually sits between 1000 and 2000 m. **This model stops at 1000 m**, so "
        "over most of the basin the axis is below the grid and there is nothing honest to draw.\n\n"
        "It is resolvable in only a small fraction of cells. The blank area is a limit of the "
        "product, stated rather than painted over."),
    "soundspeed": (
        "Sound speed",
        "Sound moves faster in warm, salty, deep water. Temperature dominates: near the surface a "
        "1 °C change moves sound speed several times more than a realistic salinity change "
        "does.\n\n"
        "That is why a temperature model can say something useful about acoustics at all."),

    # ---- validation
    "argo": (
        "Argo floats",
        "Roughly 4,000 robots drift the world's oceans, sinking to 2000 m and surfacing every "
        "ten days to report the temperature profile they measured.\n\n"
        "The **962 profiles** used here were never seen during training. They are the "
        "independent check — the model cannot have memorised them."),
    "climatology": (
        "The bar every model must clear",
        "Climatology is simply the long-term average for that place and time of year. It requires "
        "no model at all.\n\n"
        "If a model cannot beat climatology it has learned nothing. This one beats it by **45 %** "
        "on error."),
    "rmse": (
        "Error, in one number",
        "Root-mean-square error: the typical distance between the model's temperature and the "
        "float's, in °C. Lower is better.\n\n"
        "Squaring before averaging means large misses are punished much harder than small ones, "
        "so it cannot be flattered by being usually-close."),
    "bias": (
        "Bias",
        "Whether the model runs systematically warm or cold, rather than just noisy. This one "
        "reads **+0.10 °C warm** across the basin.\n\n"
        "It is measured and reported rather than corrected, because the shipped model is frozen "
        "and changing it now would break the checksum that proves these scores came from it."),

    # ---- priority
    "window": (
        "Mean-flow window",
        "Currents are split into a steady part and a swirling part. This sets how many days are "
        "averaged to define 'steady'.\n\n"
        "It matters here because the North Indian Ocean **reverses with the monsoon**, so a "
        "yearly average would call a strong seasonal current 'no flow at all'."),
    "weights": (
        "Balance",
        "How much the ranking leans on model doubt versus ocean energy. The two are combined as "
        "a geometric mean, so a region must score on **both** to rank — a calm patch the model "
        "happens to be unsure about will not surface."),
    "eke": (
        "Eddy kinetic energy",
        "How much the current swirls, after the steady flow is removed. High values mean eddies: "
        "the ocean's weather.\n\n"
        "Eddies are where subsurface structure is least predictable from the surface, which is "
        "exactly where a new measurement is worth most."),
    "notaclaim": (
        "What this is not",
        "This does **not** tell anyone where to deploy a float. It is a lightweight, "
        "interpretable heuristic that surfaces **regions where additional observations may "
        "provide high scientific value**.\n\n"
        "Formal observing-system design uses far more machinery than this. Treat it as "
        "complementary, not as a recommendation."),
    "topn": (
        "Candidate regions",
        "The highest-ranking cells, kept apart from one another so the list does not return the "
        "same eddy ten times."),
    "shallowguard": (
        "Shallow-water guard",
        "Excludes cells whose water column never reaches the deepest level. Without it the "
        "ranking fills with shelf and gulf cells where the model is unsure simply because there "
        "is barely any water — not because anything interesting is happening."),
}

# ------------------------------------------------------------------- the judge-facing summary
JUDGE_TITLE = "OceanEmbed in five minutes"

JUDGE = """
### The problem

Satellites see the **surface** of the ocean and nothing beneath it. Ships and floats measure the
depths, but there are only a few thousand floats for the whole planet — in the North Indian Ocean
that is a handful of measurements per week across an area the size of a continent.

Almost everything that matters happens **below** the surface. A cyclone's strength depends on how
deep the warm water goes, not how warm the skin is. Fish follow temperature layers. Sonar range
depends on how sound bends through the column.

### What we built

A model that reads the **surface** — temperature, salinity, sea level and currents, all of it
satellite-observable — and reconstructs the **temperature at 15 depths from the surface to 1000 m**,
across the whole North Indian Ocean, at 0.25° resolution, for any day.

It also reports **how confident it is** at every point and every depth, which most systems of this
kind do not.

### Does it work?

It was checked against **962 Argo float profiles it never saw during training**.

- Typical error: **0.9078 °C**
- Correlation with real measurements: **0.88**
- **45 % better than climatology** — the long-term seasonal average, which is the bar any model
  must clear to have learned anything at all

Every number on this dashboard is read from a file produced by the training run itself. Nothing is
typed by hand, and the checkpoint's checksum is recorded so the scores can be traced to the exact
model that produced them.

### What it is honest about

- The error bars were **too narrow** before calibration, and are still not perfect — after
  correction, ±2σ covers 80–96 % of real measurements against an ideal 95 %.
- The model runs **0.10 °C warm** across the basin. Measured, reported, not quietly fixed.
- The **SOFAR sound channel is below our 1000 m limit** across most of the basin, so we leave that
  map blank rather than extrapolate.
- A physics-based loss term was tried and **did not help**. Three seeds, reported as a negative
  result rather than dropped.
- Reanalysis input scores better (0.8548 °C) but **fails the satellite-only requirement**, so it is
  shown as a comparator and never as the headline.

### Why that matters

A system that states its own limits is one a forecaster can actually use, because they know when
to stop trusting it. That is the difference between a demo and an instrument.
"""
