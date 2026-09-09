"""Fifty-plus viva questions with answers that hold up.

Headline numbers are READ from artifacts/frozen_manifest.json at build time. Nothing is typed --
the scoring protocol changed twice in two days and every hardcoded 0.9078 in the repo went stale.
"""
from __future__ import annotations

import json
import os

from engine import Spacer, _p, build, callout, cover, heading, kvstrip, table

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAND = "OceanEmbed  |  SIH26066  |  Viva pack - 52 questions"


def F() -> dict:
    with open(os.path.join(ROOT, "artifacts", "frozen_manifest.json"), encoding="utf-8") as f:
        c = json.load(f)["claims"]
    d, g = c["deliverable_satellite"], c["glorys_comparator_stage1_embargoed"]
    return {
        "rmse": d["overall_rmse"], "bias": d["overall_bias"], "corr": d["overall_correlation"],
        "skill": d["overall_skill_rmse_ratio"], "clim": d["overall_rmse_climatology"],
        "n": d["overall_n"], "profiles": d["argo_profiles"],
        "protocol": d.get("scoring_protocol"), "sha": d["checkpoint_sha256"][:12],
        "glorys": g["overall_rmse"], "cost": d["overall_rmse"] - g["overall_rmse"],
    }


#: Every question added, counted as it is rendered. The cover says how many there are, and a
#: typed count is a claim that goes stale the moment somebody adds a question.
COUNT = []


def qa(section, blurb, items):
    COUNT.extend(items)
    out = list(heading(section))
    if blurb:
        out.append(_p(f"<i>{blurb}</i>"))
    for q, a in items:
        out.append(_p(f"<b>Q. {q}</b>"))
        out.append(_p(f"<b>A.</b>  {a}"))
        out.append(Spacer(1, 1))
    return out


def build_note(path):
    f = F()
    COUNT.clear()
    s = []
    head = []

    head.append(kvstrip([
        ("Deliverable", f"{f['rmse']:.4f} degC"),
        ("Independent profiles", f"{f['profiles']}"),
        ("Bias", f"{f['bias']:+.4f} degC"),
        ("Protocol", f["protocol"]),
    ]))

    head.append(callout(
        "Three rules before you answer anything",
        "<b>1.</b> Quote <b>{r:.4f} degC against {p} profiles</b> - not 0.9078, which is an older "
        "scoring protocol still sitting in several of our own documents. <b>2.</b> If you do not "
        "know, say <i>'I do not know'</i> or <i>'that is not verified'</i>. Both are consistent "
        "with everything else in this project. <b>3.</b> Never invent a number. One invented "
        "figure discredits every true one.".format(r=f["rmse"], p=f["profiles"]), "warn"))

    # ------------------------------------------------------------------ A
    s += qa("A.  The headline result", "Eight questions you will certainly get.", [
        ("What exactly is your result, and against what?",
         f"RMSE <b>{f['rmse']:.4f} degC</b>, correlation {f['corr']:.4f}, bias "
         f"{f['bias']:+.4f} degC, and <b>{f['skill']*100:.1f}% better than climatology</b>, "
         f"measured on <b>{f['profiles']} independent Argo profiles</b> and {f['n']:,} depth "
         f"comparisons, using satellite inputs only."),
        ("Is 0.9 degrees good?",
         f"Three anchors. It is {f['skill']*100:.0f}% better than the long-term average and beats "
         f"it at 14 of 15 depths. At the thermocline it is within about 0.02 degC of the error the "
         f"GLORYS reanalysis itself makes against the same floats - so at the hardest depth we have "
         f"essentially reached the ceiling our training target sets. And we do it from satellite "
         f"data alone, daily, at 24,000 locations."),
        ("What does 'independent' mean here?",
         "The floats come from a test window the model never trained on, enforced by a split "
         "assertion plus an embargo that drops training days whose 11-day input window would touch "
         "the test block. Train ends 2026-03-26; test runs 2026-04-01 to 2026-06-23."),
        ("Could the same physical float appear in both training and test?",
         "<b>We cannot rule it out.</b> Our float table carries latitude, longitude, date and "
         "depth - there is no float or WMO identifier in it. So our independence is in time, not "
         "by instrument. That is a real gap and we would fix it by re-fetching with platform IDs."),
        ("Why is your bias positive?",
         f"The model runs warm by {f['bias']:+.4f} degC on average. We found it twice by "
         f"independent routes - once in the per-depth table, once in the cloud-dropout experiment, "
         f"where blanking part of the input accidentally cancelled it. We have not applied a "
         f"correction because that changes a frozen model, and that is a decision to be taken "
         f"deliberately rather than quietly."),
        ("Where is the model worst?",
         "At the thermocline, around 100 m, where a surface measurement constrains the water least. "
         "Most of that error is inherited from the reanalysis we trained on. The error that is "
         "genuinely ours is shallower, in the mixed layer, where we are measurably worse than that "
         "reanalysis."),
        ("Your numbers changed between documents. Why?",
         "Same checkpoint, different scoring protocol. We tightened it twice: first declining "
         "comparisons below the sea floor, then correcting the float depth axis from "
         "pressure-read-as-metres to true depth. Older documents say 0.9078. The current protocol "
         f"is <b>{f['protocol']}</b> and the number is {f['rmse']:.4f}. Both are recorded; we never "
         f"compare across protocols."),
        ("Which depth does climatology beat you at?",
         "1000 m, by a small margin, and the chart labels it. Also worth volunteering: our surface "
         "level rests on only 21 profiles, and our own code sets a 100-profile minimum before a "
         "depth may set a headline. Applying our own rule strictly it is 13 of 14, not 14 of 15."),
    ])

    # ------------------------------------------------------------------ B
    s += qa("B.  Method and architecture", "", [
        ("Explain the architecture in one minute.",
         "Seven satellite channels over an 11-day window go into a 3-D convolutional encoder, "
         "which compresses them to 128 numbers - the compact satellite embedding the problem "
         "statement asks for. A small head turns those into 15 temperatures and 15 uncertainties. "
         f"About {550502:,} parameters in total."),
        ("Why a 3-D CNN and not something else?",
         "A bake-off. Four encoders - a centre-cell-only control, a 3-D CNN, a CNN with attention "
         "and a vision transformer - all sharing an identical prediction head, so the encoder was "
         "the only variable. The 3-D CNN won."),
        ("The paper you re-implemented feeds climatology into the decoder. Yours does not. Why?",
         "We built that decoder, scored it, and it was worse at our data scale, so we ship the head "
         "that was actually validated. We verified the shipped model ignores climatology entirely "
         "by running it with the climatology zeroed and randomised - the output is bit-identical."),
        ("Why an 11-day input window?",
         "Measured. At our data scale 11 days beats both 1 day and the paper's 31 days. The paper "
         "used finer data and far more profiles; at our sample budget a shorter window wins. We "
         "report it as a measured disagreement, not a reimplementation failure."),
        ("Your model is small. Is it underfitting?",
         "It is deliberate. At the paper's widths it would be about 7.1 million parameters - "
         "roughly 13 times the capacity for our sample count - and it overfits within a few epochs "
         "regardless of the loss. We kept their widths in the config for the record."),
        ("Did adding physics to the loss help?",
         "No, and we measured it on three seeds rather than one. Then we measured why: the model "
         "already reproduces essentially all of the observed thermocline gradient, so the term was "
         "protecting structure that was never being lost. A null result, reported as one."),
        ("Why predict a variance as well as a temperature?",
         "Because a number without an error bar is not usable for a decision. The variance comes "
         "out of the network itself rather than being bolted on, which is why our uncertainty "
         "feature exists at all."),
        ("How do you handle land and the sea floor?",
         "They are refused, never filled. A cell below the sea floor returns nothing rather than a "
         "value, and the three kinds of blank - land, below-seafloor, off-grid - are named "
         "separately because they are different facts."),
    ])

    # ------------------------------------------------------------------ C
    s += qa("C.  Data and inputs", "", [
        ("What exactly goes in?",
         "Seven channels from five satellite products: sea-surface temperature (OSTIA), salinity, "
         "sea-surface height (DUACS altimetry), two surface current components (GLOBCURRENT) and "
         "two wind components. All from Copernicus Marine."),
        ("How do we know those are really satellite, not reanalysis?",
         "A bundle verifier runs 44 provenance and lineage checks, and it includes a negative test "
         "that deliberately injects reanalysis into all five channels and confirms the check "
         "catches it. The freeze script also asserts the shipped artifact's input source reads "
         "'satellite'."),
        ("What is your training target, and is that not circular?",
         "The GLORYS reanalysis. It is not circular but it is a ceiling: we can never be more "
         "accurate than our teacher. That is why we measured the teacher's own error against the "
         "same independent floats - so we can say which part of our error is inherited and which "
         "is ours."),
        ("How much data?",
         "388 consecutive daily steps, 1 June 2025 to 23 June 2026, with zero gaps, on a 100 x 240 "
         "grid at 0.25 degrees - 24,000 cells, 15 standard depths."),
        ("What about cloud during the monsoon?",
         "Tested deliberately. We blanked sea-surface temperature the way cloud does; past about "
         "20% the degradation is real and steady, reaching roughly half a degree when fully blind, "
         "with skill going negative before that. The honest caveat: our masking is random while "
         "real cloud is clustered and persistent, so a genuine overcast should hurt more."),
        ("Does the model know when data is missing?",
         "No, and that is an architectural gap we state. The loader replaces a missing value with "
         "the channel average, so 'I have no idea' and 'ordinary sea' reach the network as the same "
         "number. The code even computes a mask marking which values were real and then discards "
         "it. A test fails if that ever changes, so the page's wording cannot go stale."),
        ("Is your data current?",
         "No. The record ends 23 June 2026. Extending it is pipeline work, not a re-run: the "
         "builder requires a reanalysis target for every day and would drop every live day."),
    ])

    # ------------------------------------------------------------------ D
    s += qa("D.  Uncertainty", "", [
        ("Is your uncertainty calibrated?",
         "It is <i>improved</i>, not <i>calibrated</i>, and we use exactly those words. Post-hoc "
         "per-depth scaling took us from clearly overconfident to mildly overconfident. The freeze "
         "script checks that this wording has not been strengthened."),
        ("Why report a range instead of one coverage number?",
         "Because the average hides the worst depth. We report coverage as a range across depths so "
         "a user acting on a mid-depth value knows that band is the weakest one. It costs us a "
         "nicer headline and buys a defensible one."),
        ("How do you know the calibration is not fitted to the data it is scored on?",
         "The scaling is fitted on training-window floats and reported on test-window floats. The "
         "two sets are disjoint in time, and it was fitted against the shipped checkpoint "
         "specifically."),
        ("Why not Monte Carlo dropout?",
         "We measured it in Phase 1 and it was overconfident at every depth, worst in the mixed "
         "layer. It is not used in the shipped system."),
        ("Does your uncertainty have correlation between depths?",
         "No, and that matters. The model emits a variance per depth independently, so anything "
         "that integrates across depths - heat content, for instance - inherits an uncertainty "
         "that is a measured <b>lower bound</b> rather than the true one. We label it as such."),
    ])

    # ------------------------------------------------------------------ E
    s += qa("E.  Physics and derived products", "", [
        ("Why can you not give mixed-layer depth from satellite input?",
         "Density needs salinity at depth, and the shipped model predicts temperature only. The "
         "reanalysis salinity is sitting in the same file and would have produced a beautiful map, "
         "which is exactly why we show a refusal box instead. A test asserts the code neither reads "
         "nor returns that salinity."),
        ("But your stability feature uses salinity. Is that a contradiction?",
         "No, and it is worth stating precisely. The shipped stage-1 model predicts temperature "
         "only. A second-stage model that also predicts salinity exists but is <b>not promoted</b> "
         "- it does not beat stage 1 on temperature. The stability work is measured on that "
         "unpromoted model, and we say so rather than implying it applies to the deliverable."),
        ("How do you compute density?",
         "EOS-80, the UNESCO 1983 formulation, checked against published reference values to better "
         "than a thousandth of a kilogram per cubic metre."),
        ("How can a temperature model produce sound speed?",
         "We measured the split rather than assuming it. At this basin's conditions temperature "
         "accounts for roughly 89% of the sound-speed error budget and salinity for the rest. The "
         "page recomputes that live so you can watch it move with conditions."),
        ("Why is there no SOFAR axis map?",
         "Because it would be a grid artifact almost everywhere. The axis in this basin sits near "
         "1500-2000 m and our deepest level is 1000 m, so nearly every cell would report 'minimum "
         "at the deepest level' - which means 'we cannot see it', not 'the axis is at 1000 m'. We "
         "map where it is resolvable instead, and today that is nowhere."),
        ("What is Tropical Cyclone Heat Potential and why do you produce it?",
         "The heat stored above the 26 degC isotherm - the fuel a storm can actually reach. It "
         "decides intensification, it has always needed subsurface observations, and we produce it "
         "daily across the basin from satellites alone. It needs no salinity, so it sits entirely "
         "inside our compliance boundary."),
    ])

    # ------------------------------------------------------------------ F
    s += qa("F.  Novelty and prior art",
            "The area where overclaiming loses a panel fastest.", [
        ("What is novel here?",
         "The system, not the reconstruction method. AI reconstruction of subsurface temperature "
         "from surface data is established prior art and our own novelty matrix says so. What we "
         "added is a hard physical guarantee where the field uses a soft penalty, a map of which "
         "satellite measurement informs which depth, and feeding a float back into the frozen model "
         "at run time."),
        ("So you just re-implemented a paper?",
         "We re-implemented a published description - their code was never released - and then "
         "measured where it does not hold at our data scale. Three of their choices cost us "
         "accuracy: the 31-day window, the density constraint, and the climatology-conditioned "
         "decoder. We built each, measured each, and shipped none of them."),
        ("Have you read the papers you cite?",
         "Abstracts and landing pages. Our literature matrix is tagged ABSTRACT-ONLY for exactly "
         "that reason - which is enough to position the work and not enough to quote a "
         "hyperparameter or assert a numerical comparison, and we do neither."),
        ("Have you compared against any published method on your data?",
         "No. That is a genuine gap. Our anchors are climatology and the reanalysis we trained on. "
         "Running a published method over this basin is the right next step and we have not done "
         "it."),
        ("Does your observation-priority feature tell INCOIS where to deploy floats?",
         "No, and that boundary is enforced rather than remembered. The sanctioned wording lives in "
         "the code and is rendered verbatim, and a test searches both the module and the page for "
         "any phrasing claiming to tell anyone where to deploy - and fails unless it is negated."),
        ("Is your priority map novel?",
         "No. Our own review found it is a simplified version of a formally optimised research "
         "area. Ours is a heuristic with no cost model, no float drift physics and no budget "
         "constraint. We kept it because it is useful and dropped the novelty claim because it is "
         "not ours."),
    ])

    # ------------------------------------------------------------------ G
    s += qa("G.  Verification and reproducibility", "", [
        ("How do we know the model on screen is the one you scored?",
         f"Run the freeze check. It re-verifies eighteen properties of the shipped artifact rather "
         f"than trusting the manifest, including the checkpoint's SHA-256 - ours begins "
         f"<b>{f['sha']}</b> - the input source, and the claim wording used for uncertainty."),
        ("How much of this is tested?",
         "Over 950 tests. More usefully, several are falsification tests: they relax a guard on "
         "purpose and confirm the bad behaviour returns, so a guard cannot be quietly removed. One "
         "parses the source code and fails if a particular mask ever starts being returned."),
        ("Can we reproduce your numbers?",
         "Yes, and every feature note carries the exact command. The seed and configuration are "
         "saved with each run, and each experiment refuses to write its result file if a control "
         "re-score does not reproduce the checkpoint's own recorded number."),
        ("Has that control ever caught anything?",
         "Yes, and it is worth telling. It refused on its first run: 0.9297 against a recorded "
         "0.9078. The cause was that the encoder's construction parameter is not the same as the "
         "input window length, and both constructions load the same weights without complaint. It "
         "produced a plausible wrong number with no error raised anywhere."),
        ("What is your biggest engineering risk?",
         "Model checkpoints and the data bundle - about 31 GB - live outside version control and "
         "move between machines by zip. The checksum manifests are the only proof that the files on "
         "one machine are the ones that were scored."),
        ("Are all your reported comparators actually on this machine?",
         "Not all. Two stage-2 reanalysis comparators are recorded with checkpoint_present false - "
         "we can show the scores but not re-run them here. The stage-1 reanalysis comparator "
         f"<b>is</b> present, which is why we quote that one: {f['glorys']:.4f} degC."),
    ])

    # ------------------------------------------------------------------ H
    s += qa("H.  Impact and deployment", "", [
        ("Who would actually use this?",
         "INCOIS and MoES as the sponsor; IMD and cyclone forecasters for the subsurface heat that "
         "drives intensification; fisheries for thermocline and front information; the navy for "
         "acoustics; and climate monitoring for ocean heat content."),
        ("What is the single most important application?",
         "Cyclone heat potential. It decides whether a storm intensifies, it has always required "
         "subsurface observations, and we produce it daily basin-wide from satellites. In a region "
         "where storms meet a low-lying, crowded coast, intensification lead time becomes "
         "evacuation lead time."),
        ("Is this production-ready?",
         "No. The science and the interfaces are ready; the operations are not. The service runs on "
         "one machine with no authentication, a whole-field export takes about 34 seconds with no "
         "caching, and the data record ends in June 2026."),
        ("What would it cost to run operationally?",
         "The inputs are already-funded satellite products, so the marginal data cost is zero. "
         "Inference is seconds per field on a single GPU. The real cost is engineering: a live "
         "ingest path, caching, monitoring and someone accountable for the output."),
        ("What would you do with three more months?",
         "Fix the mixed layer, because our own diagnostics say it is the one error genuinely "
         "available to us to improve. Give the encoder a missing-data channel. And get validation "
         "through time from moored buoys."),
    ])

    # ------------------------------------------------------------------ I
    s += qa("I.  Hostile and trap questions",
            "Rehearse these. They are the ones that decide a viva.", [
        ("Your model just memorised the reanalysis, did it not?",
         "At the thermocline it has essentially reached that reanalysis's accuracy, and we say so. "
         "But it does that from satellite surface inputs the reanalysis does not use, daily, at "
         "24,000 cells. And our cyclone-wake feature shows it reproducing a physical process that "
         "appears nowhere in its training - which memorisation cannot do."),
        ("Blanking part of your input makes the model better. Is your input useless?",
         "No - it means we have a warm bias. Blanked pixels arrive as the channel average, which "
         "pulls the prediction cooler, and the best score sits where the bias crosses zero. Past "
         "that the degradation is real and monotone. We rejected the flattering reading of our own "
         "curve in writing."),
        ("You claim a 'guarantee' on a model you do not even ship. Is that not misleading?",
         "It is a fair hit and here is the honest answer. Static stability needs density, density "
         "needs salinity, and our shipped model predicts temperature only - so the property is not "
         "measurable on the deliverable at all. We say that rather than enforcing a "
         "temperature-only substitute, which would delete real Bay of Bengal temperature "
         "inversions and buy a guarantee by destroying a physical signal."),
        ("You have an error you cannot explain. Should we trust the rest?",
         "The Arabian Sea penalty, consistent across three seeds, cause unknown after four tested "
         "hypotheses. It is a small fraction of our headline error. We report it as unexplained "
         "because the alternative is offering a story we have not verified - and this project has "
         "already retracted numbers that were believed and wrong."),
        ("Two of your screens show different headline numbers. Explain.",
         "You are right, and it is a known open item rather than a surprise. Our validation lab "
         "reports a Phase-1 satellite-driven figure while the model page reports the shipped "
         "Phase-2 model. We have flagged the discrepancy as untraced rather than explaining it "
         "away, and it is on our own open-items list."),
        ("Why should we score you well if you admit you invented nothing?",
         "Because the problem statement asks for a working, validated, satellite-input "
         "reconstruction system for this basin, and that is what we built and verified end to end. "
         "We would rather be the team whose numbers survive scrutiny than the team with the larger "
         "claim. Every weakness you might find, we have already named."),
    ])

    # ------------------------------------------------------------------ the decision
    s += heading("The one decision to rehearse until it is automatic")
    s.append(table([
        ["Configuration", "RMSE", "Input", "On this machine?"],
        ["<b>Shipped deliverable</b>", f"<b>{f['rmse']:.4f}</b>", "satellite", "<b>yes</b>"],
        ["Same model, reanalysis input", f"{f['glorys']:.4f}", "reanalysis", "<b>yes</b>"],
        ["Stage-2, reanalysis, no density term", "0.8548", "reanalysis", "<b>NO</b>"],
        ["Stage-2, reanalysis, density term on", "0.8593", "reanalysis", "<b>NO</b>"],
    ], widths=[0.36, 0.16, 0.24, 0.24], bold_col0=True, font_size=8.4))
    s.append(callout(
        "Quote the second row, never the third or fourth",
        f"The line to use: <i>\"Feed the same architecture reanalysis instead of satellite and it "
        f"scores {f['glorys']:.4f}. We do not ship it, because the problem statement asks for "
        f"satellite observations - real observations cost us {f['cost']:+.4f} degC, and that cost "
        f"is itself one of our results.\"</i>  Both those checkpoints are on this machine, so you "
        f"can prove it. The 0.8548 and 0.8593 figures are <b>not</b> - their checkpoints are "
        f"recorded as absent, so if a juror asks you to demonstrate them you cannot.", "jury"))

    n = len(COUNT)
    front = cover(
        badge=str(n), badge_sub="QUESTIONS",
        kicker="OCEANEMBED  ·  SIH26066  ·  VIVA PREPARATION",
        title="Questions They Will Ask",
        subtitle=f"{n} questions across nine areas, with answers that survive follow-up - "
                 f"including the ones we would rather not be asked.",
    )
    build(path, BRAND.replace("52 questions", f"{n} questions"), front + head + s,
          doc_title=f"OceanEmbed - {n} viva questions with answers")
    return path


if __name__ == "__main__":
    print(build_note(os.path.join(ROOT, "JURY_NOTES", "OceanEmbed_Viva57.pdf")))
