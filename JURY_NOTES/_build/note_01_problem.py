"""Note 01 - the problem statement, the solution, and who it is for."""
from __future__ import annotations

from engine import (
    Spacer, _p, build, bullets, callout, cmd, cover, heading, kvstrip, quote,
    recap, steps, table,
)

BRAND = ("OceanEmbed  |  SIH26066  |  Subsurface temperature from satellites   -   "
         "The problem and the solution")


def build_note(path):
    s = []

    s += cover(
        badge="PS", badge_sub="SIH26066",
        kicker="NOTE 1 OF 19   -   READ THIS ONE FIRST",
        title="The Problem, and What We Built",
        subtitle="What SIH26066 actually asks for, what OceanEmbed produces in answer, and who "
                 "that answer is for.",
    )

    s.append(kvstrip([
        ("Problem statement", "SIH26066"),
        ("Sponsor", "Ministry of Earth Sciences / INCOIS"),
        ("Region", "North Indian Ocean, 5-30 N / 45-105 E"),
        ("Grid", "0.25 deg - 100 x 240 = 24,000 cells"),
    ]))

    s.append(_p(
        "The ocean is opaque. Satellites, for all their power, only ever see its skin - the top "
        "millimetre or so of the surface. Almost everything that matters to a fisherman, a cyclone "
        "forecaster, a naval officer or a climate scientist is happening below that skin, where no "
        "satellite can look. SIH26066 asks us to close that gap.", "lead"))

    # 1 --------------------------------------------------------------
    s += heading("1.  What the problem statement asks for")
    s.append(_p(
        "In its own terms, SIH26066 asks for a system that reconstructs <b>depth-wise subsurface "
        "ocean temperature</b> from <b>daily surface satellite observations</b>, at <b>0.25 degree "
        "resolution</b> over the <b>North Indian Ocean</b>, at <b>15 standard depths from the "
        "surface to 1000 metres</b> - evaluated by RMSE, correlation and bias, using the GLORYS "
        "reanalysis as a training target and gridded Argo float data as independent validation."))
    s.append(_p(
        "Unpacked into plain requirements, that is seven distinct obligations, and a solution has "
        "to satisfy all of them at once rather than picking the convenient ones:"))
    s.append(bullets([
        "<b>Inputs must be satellite observations</b> - sea-surface temperature, salinity, height, "
        "and surface currents and winds. Not reanalysis. Not model output. Observations.",
        "<b>Output must be a full profile</b> - 15 fixed standard depths, not a single number and "
        "not a smooth curve fitted afterwards.",
        "<b>Resolution must be 0.25 degrees</b> - roughly 25 kilometres, fine enough to resolve "
        "eddies.",
        "<b>Cadence must be daily</b> - because a monthly average erases cyclones, eddies and "
        "fronts, which are the events anybody actually needs.",
        "<b>The method must involve deep learning</b>, producing a compact satellite embedding that "
        "the reconstruction reads.",
        "<b>Evaluation must be quantitative</b> - RMSE, correlation and bias, against observations "
        "the model never saw.",
        "<b>It must work over the Bay of Bengal and the Arabian Sea</b>, which behave very "
        "differently from one another.",
    ]))

    # 2 --------------------------------------------------------------
    s += heading("2.  Why this problem exists at all")
    s.append(_p(
        "There are two ways to know the temperature a kilometre below the sea surface today, and "
        "both of them fall short."))
    s.append(table([
        ["The existing option", "What it gives you", "Where it fails"],
        ["<b>Argo floats</b> - about 4,000 robotic instruments drifting worldwide, diving and "
         "surfacing on a cycle",
         "Genuine, high-quality measurements of the real water column.",
         "<b>Sparse and slow.</b> A float reports from wherever it happens to have drifted, roughly "
         "every 5 to 10 days. Over an entire basin, on any given day, almost every location has no "
         "float anywhere near it."],
        ["<b>Ocean reanalysis</b> - a physics model constrained by every observation available",
         "A complete, physically consistent picture everywhere.",
         "<b>Expensive and delayed.</b> It requires supercomputing, it lags real time, and it is "
         "itself an estimate - our own measurements show it carries around 1.1 degC of error at the "
         "thermocline."],
        ["<b>Satellites</b>", "Complete coverage, every day, already paid for and already in orbit.",
         "<b>They only see the surface.</b> Nothing an imaging satellite measures comes from below "
         "the skin of the ocean."],
    ], widths=[0.27, 0.30, 0.43], bold_col0=True, font_size=8.1))
    s.append(_p(
        "So the question SIH26066 poses is genuinely a good one: <b>can the daily, complete surface "
        "picture that satellites already provide be turned into the depth-resolved picture that "
        "only sparse floats and expensive models can currently give?</b> The physical basis for "
        "hoping so is real - the surface and the subsurface are dynamically coupled, and sea-surface "
        "height in particular is an integrated signal of what the whole water column is doing. The "
        "engineering question is how far that coupling can be pushed, and how honestly the "
        "remaining error can be reported."))

    s.append(callout(
        "The one-sentence version of this project",
        "Argo floats answer 'what is the temperature at 500 metres' only where a float happens to "
        "be, every five to ten days. <b>OceanEmbed answers it at 24,000 locations, every single "
        "day, from satellites that are already in orbit</b> - and it reports how much to trust each "
        "answer.", "teal"))

    # 3 --------------------------------------------------------------
    s += heading("3.  What we actually produce")
    s.append(_p(
        "OceanEmbed is a complete system, not a single model. At its centre is <b>TS-Cast-NIO</b>: "
        "a 3-D convolutional encoder that compresses eleven days of seven satellite channels into a "
        "128-number description of the surface state, feeding a compact head that turns those 128 "
        "numbers into fifteen depths - and which emits an uncertainty alongside every temperature "
        "it predicts."))
    s.append(_p(
        "Around that model sit seventeen working surfaces - each one a running dashboard or "
        "service on its own port - covering validation, physics, events, export, acoustics, "
        "cyclone analysis, robustness testing and observation planning. Each of the following "
        "seventeen notes covers exactly one of them."))

    s.append(table([
        ["What SIH26066 asks", "What OceanEmbed delivers"],
        ["Satellite inputs", "<b>7 channels harmonised from 5 distinct satellite products</b> - "
         "OSTIA sea-surface temperature, a multi-mission salinity blend, DUACS sea-surface height, "
         "GLOBCURRENT surface currents and a CMEMS wind product. Verified by a 44-check bundle "
         "verifier that includes a negative test which deliberately injects reanalysis and confirms "
         "the check catches it."],
        ["15 standard depths", "<b>0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700 and "
         "1000 metres</b> - frozen as a constant in the code, imported everywhere, never retyped."],
        ["0.25 degrees, daily",
         "<b>100 x 240 = 24,000 cells, 388 consecutive daily steps</b> from 1 June 2025 to 23 June "
         "2026, with <b>zero gaps</b>."],
        ["Deep-learning embedding",
         "<b>A 3-D CNN producing a 128-dimensional latent</b>, chosen over four competing "
         "architectures in a controlled bake-off where the prediction head was held identical so "
         "the encoder was the only variable."],
        ["RMSE, correlation, bias",
         "<b>All three at all 15 depths</b>, against <b>962 independent Argo profiles</b> and "
         "12,829 depth comparisons."],
        ["Both basins",
         "Scored separately per basin across three random seeds, with an Arabian Sea penalty "
         "reported as unexplained rather than smoothed over."],
    ], widths=[0.24, 0.76], bold_col0=True, font_size=8.2))

    s.append(_p("<b>The headline result, on floats the model has never seen</b> [VERIFIED]:"))
    s.append(table([
        ["RMSE", "Correlation", "Bias", "Skill over climatology", "Independent profiles"],
        ["<b>0.9078 degC</b>", "<b>0.8812</b>", "+0.1003 degC", "<b>+0.2595</b>", "962 (n = 12,829)"],
    ], widths=[0.19, 0.18, 0.17, 0.24, 0.22],
        align=["CENTER"] * 5))

    s.append(_p(
        "And the system is audited against the problem statement clause by clause, by a script that "
        "opens an artifact for every row rather than trusting a hand-written table: "
        "<b>16 requirements PASS, 0 FAIL, 1 BLOCKED</b>. The blocked one is independent validation "
        "against the INCOIS gridded Argo product specifically - their catalogue is reachable and "
        "carries exactly the right dataset, but their data-serving backend returns errors and empty "
        "responses. We validated against 962 independent float profiles from another source instead, "
        "documented the deviation, and call it BLOCKED rather than quietly counting it either way."))

    s.append(callout(
        "BLOCKED is a real answer, not a softer word for FAIL",
        "It means the requirement is understood, our side of the work is done, and an external "
        "dependency is unavailable. We wrote no downloader for it, because <i>a downloader that has "
        "never once retrieved a byte is not evidence of anything</i>. This must be stated to a jury "
        "as exactly that.", "warn"))

    # 4 --------------------------------------------------------------
    s += heading("4.  The one decision that defines this project")
    s.append(_p(
        "This is the most important thing on any of these nineteen pages, and it should be said out "
        "loud early in any presentation."))
    s.append(table([
        ["Configuration", "RMSE vs Argo", "Input source", "Status"],
        ["Stage 1, satellite inputs", "<b>0.9078 degC</b>", "OSTIA / DUACS / salinity blend / "
         "GLOBCURRENT / wind", "<b>SHIPPED - the deliverable</b>"],
        ["Stage 1, reanalysis inputs", "0.8789 degC", "reanalysis", "comparator only"],
        ["Stage 2, reanalysis inputs", "<b>0.8548 degC</b>", "reanalysis",
         "comparator only - <b>the best number in the project, and NOT our result</b>"],
        ["Stage 2, satellite inputs", "0.8854 / 0.9095 / 0.9158 across three seeds", "satellite",
         "not promoted, not frozen - the sign does not hold"],
    ], widths=[0.24, 0.20, 0.28, 0.28], bold_col0=True, font_size=8.1))
    s.append(_p(
        "Our most accurate configuration scores <b>0.8548 degC</b>. We do not ship it and we do not "
        "quote it as our result, because its inputs are reanalysis and the problem statement asks "
        "for satellite observations. Presenting it would be presenting a reanalysis-fed model as "
        "satisfying a satellite-input requirement. The freeze script <b>asserts</b> that the shipped "
        "artifact's input source reads <i>satellite</i>, so this cannot silently regress even if "
        "somebody wanted it to."))
    s.append(quote(
        "Real satellite observations cost us +0.019 degC against a reanalysis-fed comparator - "
        "measured across three seeds on identical points - and retain about 92% of its skill. That "
        "difference is not an excuse. It is itself one of our measured results.",
        "The framing to use in front of a jury."))

    # 5 --------------------------------------------------------------
    s += heading("5.  The impact this creates")
    s.append(_p(
        "The change OceanEmbed makes is not that subsurface temperature becomes knowable - it "
        "already is, from floats and reanalysis. The change is in <b>coverage, cadence and cost</b>. "
        "The same quantity becomes available everywhere in the basin, every day, from data that has "
        "already been paid for and is already being collected."))
    s.append(table([
        ["Domain", "What changes on the ground"],
        ["<b>Cyclone forecasting</b>",
         "Tropical Cyclone Heat Potential - the subsurface heat that decides whether a storm "
         "intensifies - becomes available daily across the whole basin rather than only where a "
         "float surfaced. The Bay of Bengal produces a modest share of the world's cyclones and a "
         "very large share of its cyclone deaths, because the storms meet a low-lying, densely "
         "populated coast. Intensification lead time converts directly into evacuation lead time."],
        ["<b>Fisheries and coastal livelihoods</b>",
         "Thermocline depth, fronts and upwelling zones govern where fish concentrate. Daily maps of "
         "them reduce the fuel and the time small-boat fishers spend searching - and reduce the risk "
         "they take in doing so."],
        ["<b>Maritime operations and security</b>",
         "Sound speed decides how far a sonar hears and where its signal bends. Producing it daily "
         "from satellites rather than from survey vessels lowers the cost of maritime domain "
         "awareness and search-and-rescue capability across a very large ocean."],
        ["<b>Climate monitoring</b>",
         "Ocean heat content is the single most direct measure of how much heat the planet is "
         "absorbing. Producing it daily over a basin with historically sparse observation adds to "
         "the record where the record is thinnest."],
        ["<b>Research capacity</b>",
         "A reproducible, frozen, independently-validated reconstruction over a region where such "
         "products are scarce - exported as standard NetCDF and served over a documented API, so "
         "other groups can build on it without asking permission or re-implementing anything."],
    ], widths=[0.22, 0.78], font_size=8.2))

    # 6 --------------------------------------------------------------
    s += heading("6.  Who this is for, and why it matters to them")
    s.append(table([
        ["Who", "Why it is important to them specifically"],
        ["<b>INCOIS and the Ministry of Earth Sciences</b>",
         "The sponsor. They operate India's ocean observation and services mandate. This gives them "
         "a daily basin-wide subsurface product from satellites they already receive - no new "
         "instrument, no new deployment, no new launch."],
        ["<b>IMD and cyclone forecasters</b>",
         "The subsurface heat field is a direct input to intensity forecasting, and it is currently "
         "the part they have least of."],
        ["<b>Coastal district administrations</b>",
         "Evacuation timing is the decision that saves the most lives in a cyclone, and it depends "
         "on how confident the intensity forecast is."],
        ["<b>Fishing communities across India, Sri Lanka and the Gulf</b>",
         "Small operators who will never own an instrument gain access to information that "
         "previously required a research vessel."],
        ["<b>The Indian Navy and Coast Guard</b>",
         "Acoustic conditions across the basin, daily, without a survey vessel."],
        ["<b>Ocean and climate researchers</b>",
         "An open, provenance-carrying dataset over an under-observed basin, with the model's own "
         "error honestly characterised so it can be used correctly."],
        ["<b>Students and educators</b>",
         "A rotatable, clickable, real-data picture of a layered ocean - built from genuine "
         "reconstruction rather than illustration."],
    ], widths=[0.28, 0.72], font_size=8.2))

    # 7 --------------------------------------------------------------
    s += heading("7.  How to see the whole system in ten minutes")
    s.append(_p(
        "Seventeen surfaces is a lot to demonstrate. This running order tells the strongest story, "
        "and each note in this pack contains the full instructions for its own feature."))
    s.append(steps([
        "<b>Feature 7 - the model itself (port 8507).</b> Show the provenance block and the headline "
        "numbers. State the satellite-versus-reanalysis decision immediately.",
        "<b>Feature 12 - the click map (8512).</b> Hand it to the jury. Let them click. Then click "
        "on land and show the refusal.",
        "<b>Feature 8 - the Argo overlay (8508).</b> Let them choose a point, and check the model "
        "against a real float in front of them.",
        "<b>Feature 3 - the Validation Lab (8503).</b> Show the worst numbers on purpose: the "
        "inherited error, the mixed layer that is genuinely ours, the depth where climatology wins.",
        "<b>Feature 9 - cyclone heat (8509).</b> This is where the project becomes nationally "
        "relevant rather than merely accurate.",
        "<b>Feature 17 - the cyclone case study (8517).</b> Close here. The model reproduces a cold "
        "wake nobody taught it, and the naive measurement that would have found nothing is shown "
        "beside it.",
    ]))
    s.append(callout(
        "If you only have three minutes",
        "Feature 7 for the result, Feature 12 to let them test it, and Feature 17 for the finding "
        "that no error figure can substitute for.", "note"))

    # 8 --------------------------------------------------------------
    s += heading("8.  What we do NOT claim")
    s.append(_p(
        "This belongs in the opening note rather than buried at the end, because a jury that hears "
        "the boundaries early trusts everything that follows."))
    s.append(bullets([
        "<b>We do not claim a novel reconstruction method.</b> AI reconstruction of subsurface "
        "temperature from surface data is established prior art, and our own literature matrix names "
        "the papers.",
        "<b>We do not claim novelty for uncertainty-aware reconstruction.</b> The paper we "
        "re-implemented does it, and does it better than we do.",
        "<b>We do not claim novelty for observation targeting.</b> Our own review found it is a "
        "formally-optimised research area; ours is a simple heuristic and we say so on the page "
        "itself.",
        "<b>We do not claim to be first in this basin.</b> Global methods already include the North "
        "Indian Ocean.",
        "<b>We never say the model tells anyone where to deploy floats.</b> The sanctioned wording "
        "is stored in the code and a test fails if either the module or the page drifts into a "
        "stronger claim.",
    ]))
    s.append(quote(
        "The claim that survives is a system-level one: a North-Indian-Ocean-focused, "
        "independently-validated reconstruction <i>system</i> - surface to subsurface temperature "
        "with uncertainty, anomaly and an observation-priority layer - built and verified end to "
        "end. We are not proposing a new method, and we do not need to be.",
        "From the project's own novelty matrix, which corrected its own earlier assessment."))

    s += recap(
        "SIH26066 asks whether the surface picture satellites already give us can be turned into "
        "the depth-resolved picture only sparse floats can currently provide. OceanEmbed answers "
        "yes, at 0.9078 degC against 962 independent floats - and refuses to quote the more "
        "flattering number that came from the wrong inputs.",
        [("16 / 0 / 1", "PS requirements: pass / fail / blocked"),
         ("24,000 x 15", "cells x depths, every day"),
         ("962", "independent profiles behind the headline")],
        "Note 1 of 19.  Next: Feature 1 - the Phase-1 App.")

    build(path, BRAND, s, doc_title="OceanEmbed - The Problem and What We Built (SIH26066)")
    return path
