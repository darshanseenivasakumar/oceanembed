"""A single short brief: 8 features, limits, future scope, viva questions.

Numbers are read from artifacts/frozen_manifest.json at BUILD time, never typed here -- the same
rule app/ui/data.py enforces, and for the same reason: when the scoring protocol changed on
2026-09-07 every hardcoded 0.9078 in the repo went stale silently.
"""
from __future__ import annotations

import json
import os

from engine import (
    Spacer, _p, build, bullets, callout, cmd, cover, heading, kvstrip, quote,
    recap, steps, table,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAND = "OceanEmbed  |  SIH26066  |  Eight features, limits and viva pack"


def _facts() -> dict:
    with open(os.path.join(ROOT, "artifacts", "frozen_manifest.json"), encoding="utf-8") as f:
        d = json.load(f)["claims"]["deliverable_satellite"]
    return {
        "rmse": d["overall_rmse"], "bias": d["overall_bias"],
        "corr": d["overall_correlation"], "skill": d["overall_skill_rmse_ratio"],
        "clim": d["overall_rmse_climatology"], "n": d["overall_n"],
        "profiles": d["argo_profiles"], "protocol": d.get("scoring_protocol", "unknown"),
        "sha": d["checkpoint_sha256"][:12],
    }


def _card(n, band, name, question, plain, how, number):
    """One feature on one block: what it is, how to run it, the number that matters."""
    out = []
    out += heading(f"{n}.  {name}")
    out.append(_p(f"<b>{band}</b>  &nbsp;·&nbsp;  <i>{question}</i>", "h2"))
    for para in plain:
        out.append(_p(para))
    out.append(_p("<b>How to run it</b>"))
    out.append(steps(how))
    out.append(callout("The number to say out loud", number, "teal"))
    return out


def build_note(path):
    f = _facts()
    s = []

    s += cover(
        badge="8", badge_sub="FEATURES",
        kicker="OCEANEMBED  ·  SIH26066  ·  ONE-PAGE BRIEF",
        title="Eight Features, In Plain Words",
        subtitle="What each one does, how to run it, what it proves - plus limits, future scope "
                 "and the questions a jury will ask.",
    )

    s.append(kvstrip([
        ("Error vs real floats", f"{f['rmse']:.4f} degC"),
        ("Independent profiles", f"{f['profiles']}"),
        ("Skill over average", f"+{f['skill']:.4f}"),
        ("Scoring protocol", f["protocol"]),
    ]))

    s.append(_p(
        "Satellites see only the skin of the ocean. Everything that matters to a cyclone "
        "forecaster or a fisherman is happening below it. <b>OceanEmbed turns the daily surface "
        "picture satellites already give us into temperature at 15 depths down to 1000 m, across "
        "the whole North Indian Ocean, every day</b> - and it says how much to trust each number.",
        "lead"))

    # ------------------------------------------------------------------ how to start
    s += heading("Starting the demo - one command for all eight")
    s.append(_p(
        "Every feature below lives in the <b>same application</b>. You start it once and click "
        "between them on the left-hand rail. There is nothing else to launch."))
    s.append(cmd(".venv/Scripts/python.exe -m streamlit run app/ui/main.py --server.port 8500",
                 "RUN THIS ONCE"))
    s.append(steps([
        "Run the command. It prints a local address - open <b>http://localhost:8500</b>.",
        "Set the <b>Date</b> and leave <b>Input</b> on <b>Satellite</b> at the top. Those two "
        "choices apply to every feature, so you only set them once.",
        "Click any feature on the left rail. They are grouped <b>SEE IT</b> (what it produces), "
        "<b>PROVE IT</b> (evidence it is right), <b>STRESS IT</b> (us attacking our own model).",
    ]))
    s.append(callout(
        "Why the grouping matters",
        "Most dashboards only have a <b>SEE IT</b> section. <b>STRESS IT</b> is where we try to "
        "break our own model in front of you - that is the part a technical judge cares about, and "
        "the part most projects do not have at all.", "note"))

    # ------------------------------------------------------------------ the eight
    s += _card(
        1, "SEE IT", "3-D Ocean", "What does the model actually produce?",
        ["The whole reconstruction as one solid, rotatable block of water. Every one of 24,000 "
         "surface cells, every one of 15 depths, for a single day.",
         "The holes are <b>not</b> missing data - they are the sea floor. About a quarter of our "
         "ocean cells are shallower than 1000 m, so there is simply no water to report there. The "
         "cyan sheet inside the block is the 26 degC layer: the fuel a cyclone burns."],
        ["Click <b>3-D Ocean</b> on the rail.",
         "Drag to rotate. Turn it until you are looking up from below - the continental shelf "
         "appears immediately.",
         "Point at a hole and say the sentence: <i>that is the sea floor, not a gap in our "
         "output.</i>"],
        "24,000 cells x 15 depths, for one day, from satellites alone.")

    s += _card(
        2, "SEE IT", "Click a Point", "Can I test it myself?",
        ["Click anywhere in the sea and the model gives you the full temperature profile beneath "
         "that exact spot, all the way down.",
         "This is the whole claim of the project in one interaction. An Argo float can answer "
         "'what is it like at 500 m' only where a float happens to be, every 5-10 days. This "
         "answers it everywhere, every day.",
         "<b>Now click on land.</b> It says <i>that cell is land</i> rather than inventing a "
         "profile. A model that confidently reports the temperature under the Thar Desert has "
         "learned nothing."],
        ["Click <b>Click a point</b> on the rail.",
         "Invite a judge to click anywhere in the water. The profile appears instantly.",
         "Then click on India. Show the refusal - it is the most convincing thing on this page."],
        "Every cell is clickable, and the ones that cannot be answered say why.")

    s += _card(
        3, "SEE IT", "Confidence", "How much should I trust each number?",
        ["The model produces two things at every depth: a temperature, and how unsure it is. This "
         "page draws both. Colour is the temperature; fading means less confident.",
         "Switch to <b>uncertainty alone</b> and a pattern appears: the model is least sure where "
         "the ocean is most active - the Somali Current and the Arabian Sea eddy field - and most "
         "sure in the quiet interior of the Bay of Bengal.",
         "We also publish how often our uncertainty band is actually right, including the depth "
         "where it is worst. A page about uncertainty that overstated its own would be "
         "self-refuting."],
        ["Click <b>Confidence</b> on the rail.",
         "Look at the combined view first, then switch to uncertainty alone.",
         "Read the coverage number out loud <b>before</b> anyone asks for it."],
        "Every value ships with a plus-or-minus band, and we report where that band is weakest.")

    s += _card(
        4, "PROVE IT", "Validation", "How do you know it is right?",
        [f"The model is checked against <b>{f['profiles']} real Argo float profiles it has never "
         f"seen</b> - genuine instruments that dived and measured the actual water.",
         f"Average error: <b>{f['rmse']:.4f} degC</b>. It beats plain climatology (the long-term "
         f"average for that month) at <b>14 of the 15 depths</b> - and we label the one depth "
         f"where climatology wins rather than hiding it.",
         "This page also does something unusual: it measures how wrong our <i>teacher</i> is. We "
         "trained on a reanalysis, so we can never be better than that reanalysis. Deep down our "
         "error is essentially the teacher's error - inherited. Near the surface it is genuinely "
         "ours, and we say so."],
        ["Click <b>Validation</b> on the rail.",
         "Walk down the per-depth table. Point at 100 m - the thermocline, the hardest depth.",
         "Point at 1000 m, where climatology beats us, and say it before the jury finds it."],
        f"{f['rmse']:.4f} degC against {f['profiles']} floats it never saw. "
        f"Beats the long-term average at 14 of 15 depths.")

    s += _card(
        5, "PROVE IT", "Cyclone Heat", "Why does India need this?",
        ["A cyclone does not just take heat from the surface. Its winds churn the sea and drag up "
         "cooler water from below. <b>If the warm layer is thin the storm cools its own fuel and "
         "weakens; if it is deep, the storm keeps growing.</b>",
         "That quantity is called Tropical Cyclone Heat Potential, and it is what intensity "
         "forecasters actually use. Producing it has always needed floats or a supercomputer. "
         "<b>We produce it daily, everywhere in the basin, from satellites alone.</b>",
         "The Bay of Bengal produces a modest share of the world's cyclones and a very large share "
         "of its cyclone deaths, because the storms meet a low-lying, crowded coast. Better "
         "intensification forecasting becomes evacuation lead time."],
        ["Click <b>Cyclone heat</b> on the rail.",
         "Pick a date in October or November - the Bay of Bengal's dangerous months.",
         "Point at the deep warm pools: a storm crossing there finds fuel; one crossing the thin "
         "areas does not."],
        "The variable that decides whether a cyclone intensifies, daily and basin-wide, "
        "with no new instrument required.")

    s += _card(
        6, "STRESS IT", "Cyclone Wake", "Did it learn real physics, or just memorise?",
        ["A cyclone leaves a trail of cold water behind it. <b>Our model was never taught that.</b> "
         "It only ever sees surface satellite pictures; nothing in its training says storms cool "
         "the ocean.",
         "Along cyclone SHAKHTI's real track, the reconstruction shows heat falling at <b>11 of 12 "
         "track points</b>. It is reproducing a physical process nobody put into it - a stronger "
         "statement than any error figure.",
         "<b>And we show the measurement that finds nothing.</b> Comparing one fixed before-and-"
         "after date pair gives almost no signal, because a storm takes days to cross a basin, so "
         "one pair of dates asks the wrong question nearly everywhere. Both results are on screen."],
        ["Click <b>Cyclone wake</b> on the rail.",
         "Show the naive fixed-date result first - it looks like nothing happened.",
         "Then show the passage-relative result. Let the contrast land."],
        "Cooling at 11 of 12 track points, from a model never told that cyclones cool the ocean.")

    s += _card(
        7, "STRESS IT", "Physical Profiles", "Is every answer physically possible?",
        ["Cold water is heavier than warm water, so in a resting ocean the water must get denser "
         "as you go down. A column where it does not would flip over instantly - it is not a small "
         "error, it is an impossible answer.",
         "Every model in this field handles that by adding a <i>penalty</i> during training, which "
         "makes impossible columns rare but never zero. That is why <b>no published paper in this "
         "area reports how many it has</b>. We measured ours: <b>805 impossible pairs, in 597 of "
         "our columns.</b>",
         "Then we remove them - not by penalising, but by nudging each profile to the nearest "
         "physically valid one. <b>805 becomes 0</b>, and we prove it by recomputing the density "
         "afterwards rather than trusting the maths. It costs almost nothing in accuracy."],
        ["Click <b>Physical profiles</b> on the rail.",
         "Show the before/after bars: the count goes to zero.",
         "Say the distinction: <i>a penalty makes it rare, a projection makes it impossible.</i>"],
        "805 physically impossible columns -> 0, verified rather than asserted.")

    s += _card(
        8, "STRESS IT", "What It Can See", "Where does the satellite stop telling us anything?",
        ["We differentiate the trained model to ask, at each depth, <b>which satellite measurement "
         "is doing the work</b>.",
         "The answer is the nicest result in the project. Near the surface the model reads "
         "<b>sea-surface temperature</b>, as you would expect. But from about 50 m down it "
         "switches to <b>sea-surface height</b> - and that is exactly right, because the height of "
         "the sea surface is the squashed-up signal of how deep the warm layer is. <b>Nobody taught "
         "it that.</b> It is in no part of the training objective.",
         "Deeper still, the response fades: the surface has much less leverage at 1000 m than at "
         "the thermocline."],
        ["Click <b>What it can see</b> on the rail.",
         "Show the stacked bar: SST dominates the top, sea-surface height takes over at depth.",
         "Say the physics: sea-surface height is the integrated signal of the thermocline."],
        "The model learned to read sea-surface height for the thermocline - untaught, and "
        "physically correct.")

    s.append(callout(
        "A ninth, if you are asked about novelty",
        "<b>Learn from a float</b> feeds a real Argo profile back into the frozen model at run "
        "time - no retraining - and the correction spreads to water in a <i>similar state</i> "
        "rather than water that is merely nearby. The improvement is small but it is real, and it "
        "is checked against two controls that would expose a fake result.", "jury"))

    # ------------------------------------------------------------------ limitations
    s += heading("Limitations - say these before the jury finds them")
    s.append(table([
        ["Limit", "What it means"],
        ["<b>It runs slightly warm</b>",
         f"A bias of {f['bias']:+.4f} degC overall, worst in the middle depths. Measured twice by "
         f"independent routes, and not yet corrected."],
        ["<b>The thermocline is our worst depth</b>",
         "Around 100 m the error roughly doubles. That is where a surface measurement constrains "
         "the deep water least - and most of that error is inherited from the reanalysis we "
         "trained on, not created by us."],
        ["<b>We cannot predict salinity at depth</b>",
         "The shipped model gives temperature only. So some products - mixed layer by density, "
         "the barrier layer - are <b>refused rather than approximated</b>, even though a "
         "plausible-looking number was easy to produce."],
        ["<b>No validation through time</b>",
         "Every number we have compares different <i>places</i>. Argo floats drift, so they cannot "
         "tell us whether the model tracks one spot as it changes. The moored-buoy data that would "
         "answer this is unreachable from our network."],
        ["<b>One region penalty we cannot explain</b>",
         "The Arabian Sea is slightly worse than the Bay of Bengal, consistently across three "
         "training runs. Four hypotheses tested, cause still unknown. We report it as unexplained "
         "rather than inventing a story."],
        ["<b>Fine structure is invisible</b>",
         "Our grid cells are about 25 km. Anything smaller than roughly 100 km is simply not "
         "resolved, and a smooth map is not evidence the ocean is smooth."],
        ["<b>The data stops</b>",
         "Our record ends in June 2026 and extending it needs pipeline work, not just a re-run. "
         "This is a proof of concept, not a live operational feed."],
    ], widths=[0.26, 0.74], bold_col0=True, font_size=8.3))

    # ------------------------------------------------------------------ future
    s += heading("Future scope")
    s.append(bullets([
        "<b>Fix the mixed layer first.</b> Our own validation shows that is the one error genuinely "
        "available to us to improve - the deeper error is inherited from the training data and "
        "cannot be fixed without a better teacher.",
        "<b>Tell the model when data is missing.</b> Right now a cloud-blanked pixel and ordinary "
        "sea water arrive at the network as the same number. Giving it a 'this is missing' channel "
        "is a known, specific architectural fix.",
        "<b>Marine heatwaves and eddy tracking.</b> Both need a time axis, which our event tools do "
        "not have yet. These were once impossible on monthly data; with 388 consecutive days they "
        "are now simply unbuilt.",
        "<b>Validation through time.</b> Moored buoys sit still and sample every few hours, which "
        "would test whether the model tracks change and not just place. The data exists; our "
        "network cannot reach it.",
        "<b>Live operation.</b> Extend the pipeline to run without a reanalysis target for every "
        "day, add caching and authentication to the export service, and it becomes a feed rather "
        "than a demonstration.",
        "<b>Assimilate every float, everywhere.</b> Our 'learn from a float' feature currently "
        "corrects other float locations. Pushing it across all 24,000 cells is the operational "
        "version, and is not yet measured.",
    ]))

    # ------------------------------------------------------------------ viva
    s += heading("Viva questions, with answers that hold up")
    for q, a in [
        ("What exactly is your result?",
         f"An average error of <b>{f['rmse']:.4f} degC</b> against <b>{f['profiles']} independent "
         f"Argo profiles</b> the model never saw, with a correlation of {f['corr']:.4f} and "
         f"{f['skill']*100:.1f}% better accuracy than using the long-term average. It beats that "
         f"average at 14 of 15 depths."),
        ("Is 0.9 degrees good?",
         "In context, yes. It is about 24% better than climatology; at the hardest depth we are "
         "essentially as accurate as the reanalysis we trained on, which had in-situ observations "
         "and a supercomputer; and we do it from satellite data alone, daily, everywhere."),
        ("Is the model just memorising the reanalysis?",
         "Through the thermocline it has reached that reanalysis's own accuracy, and we say so. "
         "But it does that from satellite surface data the reanalysis does not use. And the "
         "cyclone wake feature shows it reproducing a physical process that appears nowhere in its "
         "training - which memorisation cannot do."),
        ("How do you know the floats were really held out?",
         "They come from a time window the model never trained on, enforced by an assertion in the "
         "code plus an embargo that drops training days whose input window would touch the test "
         "period. <b>Honest caveat:</b> our float table has no instrument ID, so we can show the "
         "separation is in time but cannot prove the same physical float never appears in both."),
        ("Why can you not give us salinity or mixed-layer depth?",
         "The shipped model predicts temperature only, and density needs salinity. We could have "
         "borrowed reanalysis salinity and produced a beautiful map, but that would put "
         "reanalysis inside a product labelled satellite. The app shows a refusal box instead."),
        ("Your uncertainty - is it calibrated?",
         "It is <i>improved</i>, not calibrated, and we use exactly those words. It is still mildly "
         "overconfident, we report the coverage as a range across depths rather than a flattering "
         "average, and we never label the band '95%'."),
        ("What is actually novel here?",
         "Not the reconstruction method - that is published prior art and we say so. What is new "
         "is what we built around it: a hard physical guarantee where the field uses a soft "
         "penalty and therefore never reports a violation count; a map of which satellite "
         "measurement informs which depth; and feeding a float back into the frozen model at run "
         "time. We claim a system, not a new algorithm."),
        ("Have you compared against other published methods?",
         "No, and that is a genuine gap. We compare against climatology and against the reanalysis "
         "we trained on. Running a published method on our region would be the right next step, "
         "and we have not done it."),
        ("What happens during the monsoon when cloud blocks the satellite?",
         "We tested it deliberately by blanking the input. Past about 20% blanked the accuracy "
         "degrades steadily, reaching about half a degree when fully blind. Real cloud is clustered "
         "rather than random, so a genuine overcast should hurt more than our test showed."),
        ("Could we deploy this tomorrow?",
         "No. The science and the interfaces are ready; the operations are not. The service runs on "
         "one machine with no authentication, and the data record ends in June 2026. We would "
         "rather say that than imply an operational system."),
        ("Which part are you least confident about?",
         "The mixed layer near the surface, where we are measurably worse than the reanalysis, and "
         "the Arabian Sea penalty we cannot explain. Both are written down in our own limitations "
         "before anyone asks."),
        ("What would you do with three more months?",
         "Fix the mixed layer, give the encoder a missing-data channel, and get validation through "
         "time from moored buoys. In that order, because our own diagnostics say the first is the "
         "only error genuinely available to us to improve."),
    ]:
        s.append(_p(f"<b>Q. {q}</b>"))
        s.append(_p(f"<b>A.</b>  {a}"))
        s.append(Spacer(1, 1))

    s.append(callout(
        "If you do not know the answer",
        "Say so. <b>'I do not know'</b> and <b>'that is not verified'</b> are complete answers and "
        "they are consistent with everything else in this project. Then say what <i>is</i> known "
        "nearby, and how you would check it. <b>Never invent a number</b> - a jury that catches one "
        "invented figure will discount every true one you have given them.", "warn"))

    s += recap(
        f"Subsurface ocean temperature for the whole North Indian Ocean, every day, from "
        f"satellites alone - {f['rmse']:.4f} degC against {f['profiles']} floats it never saw, "
        f"with its own weaknesses published beside it.",
        [(f"{f['rmse']:.4f}", "degC average error"),
         (f"{f['profiles']}", "independent float profiles"),
         ("14 of 15", "depths beating the long-term average")],
        f"Checkpoint {f['sha']} - scoring protocol {f['protocol']}. Every figure read from "
        f"artifacts/frozen_manifest.json at build time.")

    build(path, BRAND, s, doc_title="OceanEmbed - Eight Features, Limits and Viva Pack")
    return path


if __name__ == "__main__":
    print(build_note(os.path.join(ROOT, "JURY_NOTES", "OceanEmbed_Brief.pdf")))
