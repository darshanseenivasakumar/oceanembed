"""The 10-minute walkthrough: eight features and the novelty, in the order to show them.

Deliberately NOT a detailed note. The seventeen feature notes already explain what each thing is
and why it is defensible; this one answers a different question -- what do I click, in what order,
and what do I say while it is on screen. Written for someone who has never opened the app.

Every number here is copied from an artifact this repository produced, and every click path is the
real rail in app/ui/main.py. Nothing is illustrative.
"""
from __future__ import annotations

from reportlab.platypus import PageBreak

import engine as E

BAND = {"see": "SEE IT", "prove": "PROVE IT", "stress": "STRESS IT"}


def _card(n, name, band, click, shows, say, careful):
    """One feature, four lines, always in the same order so the eye learns the shape."""
    return E.table(
        [["", f"<b>{n}. {name}</b>"],
         ["Click", f"<b>{BAND[band]}</b> &rarr; <b>{click}</b>"],
         ["Shows", shows],
         ["Say", say],
         ["Careful", careful]],
        widths=[0.13, 0.87], bold_col0=True, font_size=8.2)


def build_note(out_path: str) -> str:
    s = []

    s += E.cover(
        "OE", "DEMO", "SIH26066 &middot; OceanEmbed &middot; subsurface ocean temperature",
        "The 10-Minute Walkthrough",
        "Eight features and the novelty, in the order to show them.")

    # ---------------------------------------------------------------- start here
    s += (E.heading("Start here"))
    s.append(E.bullets([
        "OceanEmbed reconstructs ocean <b>temperature at 15 depths, from the surface down to "
        "1000 m</b>, over the North Indian Ocean, using <b>only what a satellite can see</b>.",
        "Everything below runs in <b>one page</b>. Nothing to install between features, no "
        "second tab to open.",
    ]))
    s.append(E.cmd([
        "cd oceanembed",
        ".venv\\Scripts\\python.exe -m streamlit run app/ui/main.py --server.port 8500",
    ], label="RUN THIS ONCE, BEFORE THE JURY WALKS IN"))
    s.append(E.bullets([
        "It opens at <b>http://localhost:8500</b>. Allow about a minute on the first feature -- "
        "the reconstruction is cached per date, so every feature after it is instant.",
        "Leave <b>Input</b> on <b>Satellite</b>. The GLORYS setting is a comparator that reads "
        "reanalysis, which the problem statement does not allow. The app warns you if it is on.",
    ]))

    s.append(E.callout(
        "What is on screen",
        "A <b>top bar</b> -- date, input, GPU, and a <b>Summary</b> button -- and then three rows "
        "of buttons: <b>SEE IT</b>, <b>PROVE IT</b>, <b>STRESS IT</b>. Clicking a button swaps "
        "what is on the stage. It never reloads the page, so you can move back and forth freely "
        "while answering a question. Every control has a <b>?</b> next to it holding the caveat "
        "for that number.", "note"))

    # ---------------------------------------------------------------- the eight
    s += (E.heading("The eight, in order"))
    s.append(E.bullets([
        "<b>SEE IT</b> shows what the system produces, <b>PROVE IT</b> shows it is right, "
        "<b>STRESS IT</b> shows what happens when you attack it. Walk them in that order and the "
        "jury never has to ask &lsquo;but is it real?&rsquo; -- you get there first.",
    ]))

    s.append(_card(
        1, "3-D Ocean", "see", "3-D Ocean",
        "The whole basin as a solid volume you can spin, with a cyan sheet floating inside it. "
        "That sheet is the <b>26 &deg;C layer</b> -- the depth of warm water a cyclone burns.",
        "&ldquo;This is one day of ocean, reconstructed from satellite alone. Nothing here was "
        "measured below the surface.&rdquo;",
        "It is a reconstruction, not an observation. Say so first, before anyone asks."))

    s.append(_card(
        2, "Click a point", "see", "Click a point",
        "Click anywhere on the sea and the full temperature profile under that point appears -- "
        "all 15 depths, surface to 1000 m.",
        "&ldquo;Any pixel in the basin, any day, all the way down. This is the product.&rdquo;",
        "Click on land or outside 5&ndash;30&deg;N, 45&ndash;105&deg;E and it refuses rather than "
        "guessing. That refusal is deliberate -- show it if you have a spare ten seconds."))

    s.append(_card(
        3, "Confidence", "see", "Confidence",
        "The same field, but colour is temperature and <b>fade is doubt</b>. Vivid where the "
        "model is sure, washed out where it is not.",
        "&ldquo;Every value ships with an uncertainty band. We report its coverage as a "
        "<b>range, 79.7% to 96.2% by depth</b>, not as a single average, because the average "
        "would hide the worst depth.&rdquo;",
        "Do not call it calibrated. It is <b>improved, not calibrated</b> -- at 50 m the band "
        "covers 80% where a perfect band would cover 95%."))

    s.append(_card(
        4, "Validation", "prove", "Validation",
        "The model's answers next to <b>963 real Argo float profiles it never trained on</b>, "
        "depth by depth.",
        "&ldquo;<b>0.9063 &deg;C</b> average error against 963 independent floats, over 12,727 "
        "depth comparisons. It beats the seasonal average at <b>14 of 15 depths</b>.&rdquo;",
        "At 1000 m the seasonal average wins by 0.024 &deg;C. Volunteer it -- the chart labels it "
        "anyway, and a jury that finds it themselves stops believing the other fourteen."))

    s.append(_card(
        5, "Cyclone heat", "prove", "Cyclone heat",
        "Not surface warmth but the <b>heat stored in the column</b> -- the quantity that decides "
        "whether a storm intensifies.",
        "&ldquo;A satellite sees a warm surface. It cannot see whether the warmth is two metres "
        "deep or two hundred. That difference is what this gives you, and it is what forecasters "
        "actually need.&rdquo;",
        "The argument for the whole project. If you show only one PROVE IT feature after "
        "Validation, make it this one."))

    s.append(_card(
        6, "Where to measure next", "prove", "Where to measure next",
        "A map of where another float or buoy would teach the model the most: <b>high model "
        "doubt meeting an energetic ocean</b>.",
        "&ldquo;The system does not just answer questions. It tells you where its own answer is "
        "weakest, so the next measurement is not wasted.&rdquo;",
        "Call it <b>a suggestion, not an instruction</b>. It is a heuristic, and the app says so."))

    s.append(_card(
        7, "Cloud cover", "stress", "Cloud cover",
        "Infrared cannot see through monsoon cloud, so this <b>blanks part of the input on "
        "purpose</b> and measures what the loss costs.",
        "&ldquo;We hid 15% of the sea-surface temperature and the score did not fall -- "
        "<b>0.8950 against 0.9078</b>. The model leans on sea-surface height and salinity too, so "
        "cloud does not blind it.&rdquo;",
        "Those two figures are from an older scoring protocol than the 0.9063 headline. Compare "
        "them with each other, never with the headline."))

    s.append(_card(
        8, "Cyclone wake", "stress", "Cyclone wake",
        "A real storm's track laid over the reconstructed heat, before and after it passed.",
        "&ldquo;Cyclone Shakhti, October 2025. The ocean cooled at <b>11 of 12 track points</b>, "
        "on average <b>4.26 kJ/cm&sup2;</b>. Nobody taught the model that storms cool the ocean "
        "-- it was never given a storm. It reproduced the wake from satellite input "
        "alone.&rdquo;",
        "This is the strongest single moment in the demo. Slow down here."))

    # ---------------------------------------------------------------- novelty
    s += (E.heading("The novelty, in one page"))
    s.append(E.bullets([
        "Reconstructing subsurface temperature from the surface is <b>not new</b>, and we say so "
        "in writing. These three are ours, and all run on the <b>frozen shipped model</b>.",
    ]))

    s.append(E.table(
        [["", "<b>What it is</b>", "<b>The number</b>"],
         ["Physical profiles<br/><font size=7>STRESS IT &rarr; Physical profiles</font>",
          "Water must get denser with depth, or the column would turn over. Everyone else adds a "
          "penalty that makes breaking it <i>rare</i>. We <b>project</b> the answer so breaking "
          "it is <i>impossible</i>, then recompute the density to check.",
          "<b>805 violations &rarr; 0</b>, verified by recomputing rather than asserted. "
          "Costs 0.0002 &deg;C."],
         ["What it can see<br/><font size=7>STRESS IT &rarr; What it can see</font>",
          "We differentiate the model to ask which surface signal it actually reads at each "
          "depth. It uses sea-surface temperature for the shallow layer and sea-surface height "
          "for the thermocline -- <b>which nobody taught it</b>.",
          "Signal reaches a median depth of <b>1000 m</b>; the weakest quarter of profiles fade "
          "by <b>500 m</b>."],
         ["Learn from a float<br/><font size=7>PROVE IT &rarr; Learn from a float</font>",
          "A float surfaces with a real measurement. We correct the model's internal state and "
          "the fix travels to water in a <b>similar state</b> -- not to water that merely happens "
          "to be nearby. <b>No retraining.</b>",
          "Error falls <b>0.0150 &deg;C</b> at similar states and <b>rises 0.2477</b> at "
          "dissimilar ones -- which is the control that proves it is the similarity doing the "
          "work."]],
        widths=[0.22, 0.52, 0.26], font_size=7.9))

    s.append(E.callout(
        "If a juror asks what is genuinely new",
        "&ldquo;The reconstruction itself is published prior art and we cite it. What is ours is "
        "a <b>guarantee</b> instead of a penalty, a <b>measurement of what the model can and "
        "cannot see</b>, and a way to <b>use a new observation without retraining</b>. Our claim "
        "is system-level, and it is written down that way.&rdquo;", "good"))

    # ---------------------------------------------------------------- ending
    s.append(PageBreak())
    s += (E.heading("How to finish"))
    s.append(E.steps([
        "Press <b>Summary</b> in the top bar. It opens the one-screen account of what was built "
        "and what it scores -- read from the frozen artifact, not typed into a slide.",
        "Close on the honest limit, before they ask for it: <b>&ldquo;the model runs slightly "
        "warm, the thermocline is our hardest depth, and one depth of fifteen is beaten by the "
        "seasonal average. All three are on the charts.&rdquo;</b>",
        "Then the one sentence to leave in the room.",
    ]))

    s.append(E.quote(
        "It reconstructs the ocean underneath a satellite image, it tells you how much to trust "
        "each value, and it tells you where to measure next."))

    s += (E.recap(
        "If you remember nothing else: one command, three bands, eight clicks.",
        [("8500", "the only port"),
         ("0.9063 &deg;C", "against 963 floats it never saw"),
         ("14 of 15", "depths beaten")],
        tail="Detail for any single feature lives in its own note, 02 to 18. The limitations and "
             "the viva answers are in note 19."))

    return E.build(out_path, "OceanEmbed · SIH26066 · the 10-minute walkthrough", s,
                   doc_title="OceanEmbed - the 10-minute walkthrough")
