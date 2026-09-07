"""Feature notes 13-17. Every figure is transcribed from PROJECT_RECORD.md, docs/ or a commit."""
from __future__ import annotations

SPECS = []

# ------------------------------------------------------------------ 13
SPECS.append(dict(
    n=13, short="Uncertainty", kicker="WHERE THE MODEL DOES NOT KNOW",
    title="Uncertainty Map",
    subtitle="Colour is the temperature, fade is the confidence - and the page publishes the exact "
             "amount by which its own confidence is overstated.",
    meta=[("Port", "8513"), ("Page file", "app/phase2/uncertainty_page.py"),
          ("Band", "plus-or-minus 2 sigma"), ("Coverage", "91.2% against 95.4% nominal")],
    lead="A reconstruction that reports only a temperature invites a reader to trust every cell "
         "equally, and the cells are not equal. This page shows both numbers the model produces - "
         "what it thinks, and how much it should be believed - and then reports how well that second "
         "number has actually been checked.",
    plain=[
        "The model emits two things at every depth: a temperature, and a variance - its own estimate "
        "of how wrong that temperature might be. This page draws both at once. Colour carries the "
        "temperature; opacity carries the confidence, so an uncertain cell fades toward the "
        "background.",
        "That double encoding has a flaw, and rather than ignore it we measured it and added a "
        "second view. <b>Fading a colour over a dark background pulls every hue toward that "
        "background</b>, so a low-confidence warm cell starts to read as a cool one - the fade "
        "corrupts the very temperature it is drawn on top of. The second mode drops the temperature "
        "entirely and shows uncertainty alone. It is also the more revealing picture: the bright, "
        "uncertain band sits over the Somali Current and the southern Arabian Sea eddy field, and "
        "the quiet Bay of Bengal interior is dark. <b>The model is least sure where the ocean is "
        "most active</b>, which is exactly what you would hope to see.",
        "The raw model uncertainty was too confident, so it is corrected afterwards using a "
        "per-depth scaling fitted on floats from the <b>training</b> window and then reported on "
        "floats from the <b>test</b> window - two sets that do not overlap in time, so the report is "
        "not marking its own homework.",
    ],
    analogy="A weather forecast that says '30 degrees' and one that says '30 degrees, give or take "
            "one' are different products. The second is more useful precisely because it admits its "
            "own limits - and this page goes further by telling you how often that 'give or take' "
            "has actually held.",
    screen_intro="Two view modes and one uncomfortable panel:",
    screen=[
        "<b>Temperature with confidence</b> - colour for the value, opacity for how much to lean on "
        "it.",
        "<b>Uncertainty alone</b> - the sigma field on its own scale, without hue contamination.",
        "The opacity range printed <b>in degrees Celsius</b> under the map, because sigma at 5 m and "
        "sigma at 1000 m are different sizes and a single fixed scale would make whole depths look "
        "uniformly vivid or uniformly faded.",
        "A calibration panel that reports coverage as a <b>range across depths</b>, never as a "
        "single flattering average.",
        "A provenance line stating whether the sigma being shown is calibrated - read from the "
        "record rather than assumed.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/uncertainty_page.py --server.port 8513",
    steps=[
        "Run the command and open <b>http://localhost:8513</b>.",
        "Start in the combined view at 100 m. The audience sees temperature with confidence baked "
        "into it.",
        "Switch to <b>uncertainty alone</b> and point at the Somali Current. Say the sentence: the "
        "model is least sure where the ocean is most active.",
        "Read the printed opacity range in degrees Celsius aloud, and explain why it is per-view.",
        "Open the calibration panel and read the coverage number - 91.2% against a nominal 95.4% - "
        "<b>out loud, before anyone asks</b>.",
        "Move the depth to 100 m and note that both the model's largest uncertainty and its largest "
        "correction factor land there. Two independent signals, one depth.",
    ],
    extra_commands=[
        ("RE-FIT AND RE-REPORT THE CALIBRATION",
         "PYTHONPATH=src python scripts/phase2/calibrate_uncertainty.py"),
    ],
    why=[
        "The problem statement asks for a usable reconstruction, and a number without an error bar "
        "is not usable for a decision. A forecaster deciding on an evacuation needs to know whether "
        "the heat content figure in front of them is solid or shaky.",
        "It is also the project's most direct statement of scientific character. A page about "
        "uncertainty that overstated its own uncertainty would be self-refuting, so this one "
        "publishes the gap between what it claims and what it delivers.",
    ],
    ps_rows=[
        ["Usable, decision-ready output",
         "Every temperature ships with a per-depth uncertainty a user can act on."],
        ["Honest evaluation",
         "Coverage is measured on held-out floats and reported as a range across depths."],
        ["Independent validation",
         "Calibration is fitted on train-window floats and reported on test-window floats - disjoint "
         "in time."],
    ],
    numbers_intro="What is claimed, exactly, and what was measured [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Measurement", "Value", "How it is stated"],
            ["Coverage of the plus-or-minus 2 sigma band",
             "<b>91.2% mean</b>, range <b>80.1% to 95.5%</b> by depth, on 908 held-out profiles",
             "Reported as a <b>range</b>, never as the mean alone - the mean would hide an 80% depth "
             "at 50 m."],
            ["Nominal target", "95.4%",
             "So we are <b>4.2 points short</b>. The band is called 'plus-or-minus 2 sigma' and is "
             "<b>never</b> labelled '95%'."],
            ["Where the model is least certain", "100 m, median sigma <b>1.197 degC</b>",
             "Most certain at 500 m, 0.265 degC."],
            ["Largest correction factor applied", "also at 100 m, x1.4583",
             "Two independent signals pointing at the same depth: the raw model is least sure at the "
             "thermocline <b>and</b> was most overconfident there."],
            ["Calibration fitting set", "3,423 train-window profiles",
             "Coverage reported on 908 <b>test-window</b> profiles - disjoint in time."],
        ],
        widths=[0.24, 0.28, 0.48], font_size=8.0,
    ),
    numbers=[
        "<b>The honest summary, in the project's own words: the uncertainty is <i>improved</i>, not "
        "<i>calibrated</i>.</b> The model remains mildly overconfident, and the freeze script checks "
        "that this claim wording has not been quietly strengthened - it is one of its eighteen "
        "checks.",
        "No plus-or-minus 1 sigma band and no confidence percentage appear anywhere in the interface, "
        "because neither would be defensible.",
        "The page's own acceptance test was found to be comparing two different quantities - "
        "dimensionless scale factors against a sigma in degrees Celsius - so it would have passed or "
        "failed for the wrong reason. It was replaced with a far stronger check that reconstructs "
        "the field twice, with and without calibration, and asserts depth by depth that the ratio "
        "equals the published factor, and that calibration moves sigma and <b>not</b> temperature.",
    ],
    impact_rows=[
        ["Forecasters", "Knowing which parts of a field to act on and which to treat with caution - "
         "the difference between data and a decision."],
        ["Scientists", "A basin map of where a satellite-driven reconstruction is structurally weak, "
         "which is itself a research finding."],
        ["The jury", "A team publishing the exact size of its own overconfidence, before being "
         "asked."],
        ["Observation planners", "One of the two inputs to Feature 16 - you send instruments where "
         "the model is uncertain."],
    ],
    society="Overconfident predictions cause worse decisions than honest uncertain ones. A public "
            "system that says clearly where it is weak lets a forecaster weight it correctly against "
            "other evidence, and lets a community understand why a warning carries the caveats it "
            "does.",
    pitch="The model produces two numbers at every depth - a temperature and how uncertain it is - "
          "and this page draws both. Switch to uncertainty alone and you can see the model is least "
          "sure exactly where the ocean is most active: the Somali Current and the Arabian Sea eddy "
          "field. Now the number I want to give you before you ask: our plus-or-minus 2 sigma band "
          "covers 91.2% of held-out observations against a nominal 95.4%. We are 4.2 points "
          "overconfident. We report coverage as a range by depth, 80.1 to 95.5, because the average "
          "would hide an 80% depth at 50 metres. And we never label the band '95%'.",
    pitch_note="Say the coverage gap unprompted. A page about uncertainty must not overstate its own.",
    qa=[
        ("Your uncertainty is not properly calibrated, then?",
         "Correct, and we use exactly that word. It is <i>improved</i>, not <i>calibrated</i>: "
         "post-hoc per-depth scaling brought us from clearly overconfident to mildly overconfident. "
         "The freeze check verifies that our claim wording has not drifted upward."),
        ("Why not just report the average coverage of 91.2%?",
         "Because it hides the worst depth. Coverage runs from 80.1% at 50 m up to 95.5%, and a user "
         "acting on a 50 m value deserves to know that band is the weakest one. Reporting a range "
         "costs us a nicer headline and gains a defensible one."),
        ("How do you know the calibration is not fitted to the same data it is scored on?",
         "The scaling is fitted on 3,423 profiles from the training window and reported on 908 "
         "profiles from the test window. The two sets are disjoint in time, and the calibration was "
         "fitted against the shipped checkpoint specifically - which the freeze script asserts."),
    ],
    limit=("Two things this uncertainty is not", "It does not come from Monte Carlo dropout - the "
           "Phase-1 dropout uncertainty was measured overconfident by 1.6 to 3.5 times and is not "
           "used here. And it carries <b>no correlation between depths</b>: the model gives a "
           "variance per depth independently, so any quantity integrating across depths - such as "
           "the heat content in Feature 9 - inherits an uncertainty that is a measured lower bound "
           "rather than the true one. Both limits are stated on the pages that depend on them."),
))

# ------------------------------------------------------------------ 14
SPECS.append(dict(
    n=14, short="Acoustics", kicker="HOW FAR SOUND CARRIES",
    title="Acoustics",
    subtitle="Turning a temperature field into the quantity a sonar operator actually acts on - and "
             "refusing the map that cannot honestly be drawn.",
    meta=[("Port", "8514"), ("Page file", "app/phase2/acoustics_page.py"),
          ("Module", "phase2/derived/acoustics.py"), ("Formula", "Mackenzie 1981")],
    lead="Sound speed is the operational reason a navy or a marine agency wants subsurface "
         "temperature in the first place. It decides how far a sonar hears, where its signal bends, "
         "and whether the surface duct is deep enough to be worth using. This page makes that "
         "translation, and states in measured terms why a temperature model is entitled to make it.",
    plain=[
        "Sound travels faster in warmer, saltier, deeper water. Because temperature changes fastest "
        "with depth, the ocean bends sound: a sound ray curves toward whichever layer is slower. "
        "That bending creates two structures that matter operationally.",
        "The <b>sonic layer depth</b> is the top layer where sound speed increases downward, forming "
        "a surface duct that traps sound and lets it travel further than it otherwise would. The "
        "<b>SOFAR axis</b> is the depth where sound speed is at its minimum - a natural waveguide in "
        "which sound can travel thousands of kilometres.",
        "The obvious objection is that sound speed also depends on salinity, and our satellite model "
        "predicts temperature only. So the page <b>measures</b> the answer rather than arguing it. "
        "At this basin's conditions, our temperature error moves sound speed by roughly 2.3 metres "
        "per second, while the salinity error of our experimental salinity model moves it by about "
        "0.30. <b>Temperature is about 89% of the error budget.</b> The page computes this live, so "
        "the audience watches it change with conditions rather than being quoted a fixed number.",
    ],
    analogy="Light bends when it passes between air and water, which is why a straw looks broken in "
            "a glass. Sound does the same thing inside the ocean, continuously, because every layer "
            "has a different speed - and knowing where it bends is the difference between hearing "
            "something and not.",
    screen_intro="Three products and one deliberate refusal:",
    screen=[
        "A sound-speed profile at any point, computed with the Mackenzie 1981 formula whose "
        "coefficients are pinned to the published values by a test.",
        "The <b>sonic layer depth</b> - the surface duct that determines short-range sonar "
        "performance.",
        "A live error budget showing how much of the sound-speed uncertainty comes from temperature "
        "and how much from salinity, recomputed for the conditions on screen.",
        "A source menu whose third option is named for exactly what it is - <i>v2 temperature + "
        "GLORYS salinity</i> - and is <b>never</b> labelled satellite.",
        "A basin map of <b>where the SOFAR axis is resolvable</b>, which on the shipped grid honestly "
        "says <i>nowhere</i>, in words, rather than drawing 24,000 cells of grid edge.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/acoustics_page.py --server.port 8514",
    steps=[
        "Run the command and open <b>http://localhost:8514</b>.",
        "Pick a deep-water point - somewhere in the central Arabian Sea works well - and look at the "
        "sound-speed profile.",
        "Open the error budget and read the split aloud. This is the moment you justify an acoustics "
        "page built on a temperature model, with a measurement rather than an argument.",
        "Show the source menu and point at the third entry. Say plainly: this one mixes reanalysis "
        "salinity in, so it is named for that and is never called satellite.",
        "Finish on the SOFAR panel, where the page reports that the axis is not resolvable anywhere "
        "on this grid, and explain why - <b>this is the strongest slide in the feature</b>.",
    ],
    why=[
        "The problem statement's sponsor operates in a maritime-security and marine-services context "
        "where acoustic conditions matter. This feature is the clearest demonstration that a "
        "subsurface temperature product is not an academic artifact - it feeds a decision somebody "
        "makes at sea.",
        "It also keeps the project's compliance boundary intact in a place where it would have been "
        "easy to blur. The build specification for this feature asked for a hybrid of our "
        "temperature and reanalysis salinity. That hybrid is offered - but as its own clearly-named "
        "source, never as the deliverable.",
    ],
    ps_rows=[
        ["Deliver an operationally useful product",
         "Converts reconstructed temperature into sound speed and sonic layer depth, the quantities "
         "operators consume."],
        ["Satellite-input compliance",
         "Nothing here is ever labelled satellite while containing reanalysis; the hybrid source is "
         "named for what it contains."],
        ["Physically sound treatment",
         "Mackenzie 1981 coefficients pinned to published values, with the valid-range mask computed "
         "rather than assumed."],
    ],
    numbers_intro="Three measurements, and one refusal that a jury should hear in full [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Finding", "Numbers", "What it settles"],
            ["The error budget", "temperature about 2.3 m/s against salinity about 0.30 m/s - "
             "<b>temperature is 89%</b>",
             "A temperature model is entitled to produce sound speed. Measured live, not argued."],
            ["Sensitivity is not intuitive", "4.08 m/s per degC at 5 degC, but only 2.11 at 29 degC",
             "The formula's quadratic term is negative, so <b>cold deep water is more "
             "temperature-dominated than warm surface water</b> - 10.5x against 6.7x."],
            ["A bug found by clicking one cell",
             "Of <b>848</b> cells first reporting 'axis resolved', <b>336 - 40%</b> sat in water "
             "shallower than 300 m, reporting axis depths of 5, 10, 20 and 30 m",
             "It had found a five-metre dip in a ten-metre column in the Palk Strait and called it a "
             "SOFAR channel. A full-column guard now blocks that, and a test proves the guard is "
             "load-bearing."],
            ["What cannot honestly ship",
             "12,168 cells with no water column, 8,973 with the axis below 1000 m, 2,859 too "
             "shallow, and <b>zero resolved</b>",
             "The tropical Indian Ocean's SOFAR axis sits near 1500-2000 m, <b>below our deepest "
             "level</b>. So the page says 'nowhere' in words rather than drawing a basin-wide grid "
             "artifact."],
        ],
        widths=[0.22, 0.36, 0.42], font_size=7.9,
    ),
    numbers=[
        "After the guard, the categories partition exactly: 8,502 below-grid plus 471 resolved = "
        "8,973 full-depth cells, plus 2,859 too shallow = 11,832 ocean cells. The same total the "
        "click map and the export timing both independently produce.",
        "<b>A colour bug worth recording:</b> the first 'unresolved' colour sat on the deep end of "
        "the value ramp and read as <i>deep duct</i>. A resolved absence must be off the value scale "
        "entirely, or the picture asserts the opposite of what it means.",
        "About a sixth of the surface lies outside the sound-speed formula's validated range - "
        "salinity runs 1.64 to 39.98 psu, with 7.64% of surface cells below 30 psu in the "
        "Ganges-Meghna plume - so a separate validity mask is computed rather than assumed.",
    ],
    impact_rows=[
        ["Navy and coast guard", "Daily basin-wide sonar-performance conditions from satellite data, "
         "with no survey vessel required."],
        ["Underwater communications", "Acoustic modems and sensor networks depend on the same "
         "sound-speed structure."],
        ["Marine mammal research", "Whale communication ranges are set by the same waveguides."],
        ["Offshore operations", "Acoustic positioning for survey and drilling depends on the "
         "sound-speed profile."],
    ],
    society="Maritime domain awareness across the Indian Ocean rests on acoustics, and acoustics "
            "rests on subsurface temperature. Producing this from satellites already in orbit - "
            "rather than from dedicated survey vessels - lowers the cost of maritime safety and "
            "search-and-rescue capability across a very large ocean.",
    pitch="Sound speed is the operational reason anyone wants subsurface temperature - it decides "
          "how far a sonar hears and where its signal bends. The obvious objection is that sound "
          "speed also needs salinity, which our satellite model does not predict, so we measured it "
          "instead of arguing: temperature is about 89% of the error budget here, and the page "
          "computes that live. Now the part I want you to notice. The specification asked us for a "
          "basin map of the SOFAR axis. On our grid there are zero resolvable cells, because the "
          "tropical Indian Ocean's axis sits near 1500 to 2000 metres and our deepest level is 1000. "
          "So we ship a map of where it is <i>resolvable</i>, and today it says nowhere - in words, "
          "rather than 24,000 cells of grid edge.",
    pitch_note="The refusal to draw the SOFAR map is a stronger result than the map would have been.",
    qa=[
        ("How can a temperature-only model produce sound speed?",
         "Because we measured the split rather than assuming it. At this basin's conditions "
         "temperature accounts for about 89% of the sound-speed error budget and salinity for the "
         "rest. The page recomputes that live so you can watch it move with conditions."),
        ("Why is there no SOFAR axis map?",
         "Because it would be a grid artifact roughly 95% of the time. The axis in this basin sits "
         "near 1500 to 2000 metres and our deepest level is 1000, so almost every cell would report "
         "'minimum at the deepest level' - which means 'we cannot see it', not 'the axis is at 1000 "
         "metres'. We report where it is resolvable instead, and say so plainly."),
        ("You found a bug in this page yourself. What was it?",
         "The first version reported a resolved SOFAR axis in the Palk Strait - about ten metres of "
         "water. It had found a five-metre dip in a ten-metre column. Across the basin, 40% of its "
         "'resolved' cells were in water shallower than 300 metres. We added a full-column "
         "requirement, and a test now relaxes that guard on purpose and checks the bad result comes "
         "straight back - so the guard cannot be silently removed."),
    ],
    limit=("The deepest level is the binding constraint", "Almost 95% of our full-depth cells have "
           "their sound-speed minimum at 1000 m, which is our deepest level rather than a real "
           "acoustic feature. Extending the product to 2000 m would require re-training against a "
           "deeper target and is not built. The sonic layer depth and the error budget are "
           "defensible on the current grid; a SOFAR axis map is not, and is refused rather than "
           "drawn."),
))

# ------------------------------------------------------------------ 15
SPECS.append(dict(
    n=15, short="Cloud Dropout", kicker="WHAT THE MONSOON DOES TO A SATELLITE MODEL",
    title="Cloud Dropout",
    subtitle="An experiment that set out to test robustness to cloud and instead found a warm bias "
             "in the deliverable.",
    meta=[("Port", "8515"), ("Page file", "app/phase2/dropout_page.py"),
          ("Script", "scripts/phase2/run_cloud_dropout.py"), ("Cost", "about 31 s, no retraining")],
    lead="Our model reads sea-surface temperature as its first channel, and during the monsoon thick "
         "cloud blinds infrared temperature retrieval for days at a time over large parts of this "
         "basin. So the question is not whether the model degrades under cloud. It is how fast - and "
         "the answer turned out to be about something else entirely.",
    plain=[
        "The experiment is simple to describe. Take the shipped model, unchanged. Blank out a "
        "fraction of the sea-surface temperature pixels in the <b>test</b> input, as cloud would. "
        "Score it. Repeat from 0% blanked to 100%, three different random masks at each level, and "
        "draw the curve.",
        "One detail decides whether the whole experiment means anything. The blanking is done in "
        "<b>real physical units, on the raw data, before the model's normalisation step</b>. Do it "
        "the other way round - blank after normalisation, or blank to zero - and every 'missing' "
        "pixel arrives at the network as zero, which after normalisation <i>is the channel average</i>: "
        "a perfectly plausible ordinary-temperature pixel. The error would barely move and the "
        "result would read <i>'robust to 60% cloud cover'</i> having tested precisely nothing.",
        "And then the curve did something nobody expected. <b>Blanking 15% of the sea-surface "
        "temperature made the model better</b> - 0.8950 against the control's 0.9078, with a spread "
        "across random masks of 0.0002, so sixty times the noise. It would have been easy, and "
        "completely wrong, to report that as tolerance of cloud.",
        "It is two errors partially cancelling. The shipped model runs <b>0.1003 degC warm</b>. A "
        "blanked pixel reaches the network as the channel average, which pulls the prediction "
        "cooler. The best score sits essentially where the bias crosses zero, at about 19%. So the "
        "finding is not about cloud at all - <b>it is about the deliverable, and it says a bias "
        "correction is worth about 0.013 degC, free</b>.",
    ],
    analogy="A student who consistently over-estimates every answer will score better on a test "
            "where some questions are removed at random - not because removing questions helps, but "
            "because it accidentally cancels a habit. Reporting that as 'robust to missing questions' "
            "would be the wrong lesson entirely.",
    screen_intro="One curve, and the reasoning that stops it being misread:",
    screen=[
        "Error against fraction of sea-surface temperature blanked, from 0% to 100%, averaged over "
        "three random masks each.",
        "The bias curve on the same axis - which is what makes the dip explicable rather than "
        "mysterious.",
        "The control point, which reproduces the shipped model's recorded score <b>exactly</b>.",
        "A written statement that the dip is a bias cancellation and <b>not</b> robustness to cloud.",
        "A stated caveat that the masking is random, while real cloud is spatially clustered and "
        "persistent - so a genuine overcast should hurt more than this curve shows.",
    ],
    run_intro="This page renders a stored result and runs no inference itself, because a results "
              "page that recomputed its own numbers would be a second definition of them. To "
              "regenerate the result:",
    command="PYTHONPATH=src python scripts/phase2/run_cloud_dropout.py --tag sat_7ch_s42 "
            "--daily-dir data/processed/daily_sat/v001",
    steps=[
        "Run the experiment script above. It takes about 31 seconds for the full ten-point sweep and "
        "requires no retraining.",
        "Note the control check in the output - the script <b>refuses to write its result file</b> "
        "if the 0% point does not reproduce the shipped model's recorded score.",
        "Launch the page with the second command below and open <b>http://localhost:8515</b>.",
        "Show the curve and let the audience see the dip at 15%.",
        "Ask them what it means, then give the real answer: it is a bias cancellation, and it is a "
        "finding about our model rather than about clouds.",
        "Finish on the caveat: real cloud is clustered, not random, so a real overcast should be "
        "worse than this.",
    ],
    extra_commands=[
        ("OPEN THE RESULTS PAGE",
         "PYTHONPATH=src python -m streamlit run app/phase2/dropout_page.py --server.port 8515"),
    ],
    run_note=("The control is the whole experiment", "At 0% blanked the harness must reproduce the "
              "checkpoint's own recorded score, and it does - both read 0.9077608087441584. If it "
              "did not, every degradation measured below it would be harness error rather than "
              "weather, so the script refuses to write anything at all.", "good"),
    why=[
        "The problem statement asks for a satellite-input system over a basin dominated by the "
        "monsoon. Cloud is the single most obvious operational failure mode for such a system, and "
        "not testing it would leave the most likely first question from an operational reviewer "
        "unanswered.",
        "It also produced an actionable finding about the deliverable that no other experiment had "
        "surfaced this cleanly: the model runs warm by a measurable amount, and removing that is "
        "worth about 0.013 degC.",
    ],
    ps_rows=[
        ["Robustness of a satellite-input system",
         "Quantifies degradation from 0% to 100% missing sea-surface temperature, with three mask "
         "draws per point."],
        ["Honest evaluation",
         "The control reproduces the shipped score exactly, and the script refuses to write "
         "otherwise."],
        ["Report bias",
         "Traced the warm bias through an independent route and quantified what correcting it would "
         "be worth."],
    ],
    numbers_intro="The full sweep, on 962 Argo profiles with the shipped checkpoint unmodified "
                  "[VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["SST blanked", "0%", "10%", "15%", "20%", "30%", "50%", "70%", "100%"],
            ["RMSE (degC)", "0.9078", "0.8957", "<b>0.8950</b>", "0.8973", "0.9118", "0.9857",
             "1.1087", "1.4114"],
            ["Bias (degC)", "+0.100", "+0.047", "+0.021", "-0.005", "-0.059", "-0.163", "-0.267",
             "-0.471"],
        ],
        widths=[0.16, 0.105, 0.105, 0.105, 0.105, 0.105, 0.105, 0.105, 0.115],
        font_size=7.6,
    ),
    numbers=[
        "<b>Read the two rows together.</b> The best error is at 15% and the bias crosses zero at "
        "about 19%. That is not a coincidence - it is the mechanism.",
        "Past the minimum the degradation is real and monotone: <b>+0.50 degC by 100% blanked</b>, "
        "with skill against climatology going <b>negative at 90%</b>. Under total blindness the "
        "model is worse than simply quoting the long-term average, which is the correct and "
        "reassuring behaviour.",
        "<b>The bias correction was NOT applied.</b> That is a change to a frozen model and belongs "
        "to the person who owns it - so it is recorded as a decision somebody takes rather than "
        "something nobody noticed.",
    ],
    impact_rows=[
        ["Operational users", "A quantified answer to the first question anyone will ask about a "
         "monsoon-season satellite product."],
        ["The team", "An independent confirmation of the warm bias, and a price tag on fixing it."],
        ["The jury", "A demonstration of what good experimental design looks like - including the "
         "mistake that would have made it meaningless, stated openly."],
        ["Future model work", "A named architectural gap: the encoder has no way to know a pixel is "
         "missing."],
    ],
    society="A monsoon-season ocean product that has never been tested under monsoon-season cloud is "
            "a product that will fail exactly when it is needed most. Measuring the failure mode "
            "before deployment - and reporting that a convenient-looking result was actually "
            "something else - is what separates an operational tool from a demonstration.",
    pitch="We blanked out sea-surface temperature the way monsoon cloud does, and the curve did "
          "something surprising: at 15% blanked the model got <i>better</i>. It would have been very "
          "easy to report that as tolerance of cloud cover. It is not. Our model runs 0.1 degC warm, "
          "a blanked pixel arrives at the network as the channel average which pulls it cooler, and "
          "the best score sits exactly where the bias crosses zero. So this experiment did not find "
          "robustness - it found a warm bias in our own deliverable, and told us that correcting it "
          "is worth about 0.013 degC.",
    pitch_note="This is the best story in the pack about how the team thinks. Tell it in full.",
    qa=[
        ("So your model is robust to cloud cover?",
         "No, and we are careful about that. The improvement at light masking is an accident of "
         "error cancellation. Past about 20% the degradation is real and monotone - half a degree by "
         "total blindness, with skill going negative at 90%. And the real caveat is worse: our "
         "masking is random, while real cloud is clustered and persistent, so a genuine overcast "
         "should hurt more than this curve shows."),
        ("How do you know the improvement is not just noise?",
         "The spread across three independent random masks is 0.0002 degC, and the improvement is "
         "0.0128 - sixty times the noise floor. And the control at 0% reproduces the shipped model's "
         "recorded score to fifteen decimal places, so the harness itself is verified."),
        ("Why not simply apply the bias correction and take the better number?",
         "Because that is a change to a frozen, published model, and it belongs to the person who "
         "owns that model rather than to the person who ran this experiment. It is recorded as a "
         "decision to be taken. Silently improving a frozen artifact is how a project loses the "
         "ability to say what it actually measured."),
    ],
    limit=("The architectural gap, stated rather than softened", "The encoder has <b>no way to know "
           "a pixel is missing</b>. The data loader replaces every missing value with the channel "
           "average, so 'I have no idea' and 'ordinary sea' arrive at the network as the same "
           "number. The code even computes a companion mask marking which values were real - and "
           "then discards it. So this is not graceful degradation; it is degradation while being "
           "told nothing. A test parses the source and <b>fails</b> if that mask ever starts being "
           "returned, at which point this page's framing is out of date and must be rewritten rather "
           "than relaxed."),
))

# ------------------------------------------------------------------ 16
SPECS.append(dict(
    n=16, short="Priority v2", kicker="WHERE THE NEXT MEASUREMENT IS WORTH MOST",
    title="Observation Priority v2",
    subtitle="Ranks the basin by where an additional observation may carry high scientific value - "
             "and enforces, in code, the claim it is not allowed to make.",
    meta=[("Port", "8516"), ("Page file", "app/phase2/priority_page.py"),
          ("Formula", "sqrt(sigma x EKE)"), ("Cells ranked", "8,790")],
    lead="Ocean observation is expensive. If you could deploy one more instrument, where should it "
         "go? This page offers an answer - and is unusually strict about the difference between "
         "offering an answer and claiming authority.",
    plain=[
        "Two things make a location worth measuring. The first is that <b>the model is uncertain</b> "
        "there, because a measurement where the model is already confident teaches it little. The "
        "second is that <b>the water is energetic</b> there - full of eddies and variability - "
        "because that is where a single measurement carries the most information about a rapidly "
        "changing state.",
        "So the score is the geometric mean of those two: the model's own uncertainty, and eddy "
        "kinetic energy. Both are normalised to a common scale first, because uncertainty is in "
        "degrees Celsius and energy is in metres squared per second squared - a raw product would "
        "simply rank on whichever number happens to be larger.",
        "<b>Version 1 used float sparsity instead of energy, and it had a defect that could not be "
        "fixed from inside it.</b> Sparsity asks 'where are there no floats?' - and the places floats "
        "are most absent are frequently the places floats <b>cannot go</b>. Version 1 ranked the "
        "Persian Gulf, about 20 metres deep, at the very top. Energy asks a question about the water "
        "rather than about the observing network, and cannot be maximised by a place no instrument "
        "can reach.",
        "And here is the discipline a jury should notice. Our own literature review marks "
        "observation-priority as <b>already done</b> - it is a simplified version of a formally "
        "optimised research area. So the sanctioned wording lives <b>inside the code</b> and is "
        "rendered verbatim, and a test searches both the module and the page for any phrasing "
        "claiming the model tells anyone where to deploy floats, and fails unless it is negated. "
        "<i>No numerical test can catch a rhetorical error, so the rhetoric is tested too.</i>",
    ],
    analogy="A doctor deciding where to place one more sensor puts it where they are least certain "
            "and where the patient is most variable - not where sensors happen to be scarce, because "
            "some places are scarce for good reasons.",
    screen_intro="A ranked map with its own claim printed on it:",
    screen=[
        "A basin map ranked by priority score, with the top candidate cells highlighted.",
        "The two contributing factors shown separately, so a viewer can see which one is driving any "
        "given cell.",
        "The sanctioned claim and the explicitly disallowed claim, rendered verbatim from the code "
        "rather than typed into the page.",
        "A switch that turns the too-shallow guard <b>off</b>, labelled as reproducing version 1's "
        "failure mode - so the improvement is demonstrable rather than asserted.",
        "The number of days used in the mean-flow window, reported rather than assumed.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/priority_page.py --server.port 8516",
    steps=[
        "Run the command and open <b>http://localhost:8516</b>.",
        "Pick a date in the southwest monsoon for the clearest picture.",
        "Read the claim box at the top out loud. It says <i>regions where additional observations may "
        "provide high scientific value</i> - and it does <b>not</b> say the model tells anyone where "
        "to deploy anything.",
        "Look at the top candidates. They cluster at 7 N, 50-54 E - the Somali Current and its great "
        "eddy, the most energetic field in the basin during the southwest monsoon, and a place where "
        "the model is also uncertain.",
        "Toggle the shallow-water guard off and let the audience watch version 1's failure mode "
        "reappear.",
        "Finish with the honest measurement below - the guard's mechanism matters, but on this date "
        "it rescued nothing, and we say so.",
    ],
    why=[
        "The problem statement's sponsor operates an observing network. A layer that suggests where "
        "additional observations would be most informative is directly relevant to how that network "
        "is planned - and it closes the loop from reconstruction back to observation.",
        "It also demonstrates something a jury rarely sees: a team that found its own idea was "
        "already published, said so in writing, kept the feature because it is useful, and dropped "
        "the novelty claim. That is recorded in the project's novelty matrix, which corrected its "
        "own earlier assessment.",
    ],
    ps_rows=[
        ["Products beyond raw reconstruction",
         "Turns the uncertainty field into an observation-planning layer."],
        ["Honest positioning",
         "The claim is bounded in code and enforced by a test, not left to a presenter's judgement."],
        ["Uses the model's own uncertainty",
         "Consumes the calibrated per-depth sigma from Feature 13 rather than a proxy."],
    ],
    numbers_intro="Four checks, because a plausible-looking map is the easiest thing in this project "
                  "to get wrong [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Check", "Result", "What it rules out"],
            ["Is this just a picture of the fastest currents?",
             "Top-decile energy against top-decile mean speed overlap <b>0.305</b>",
             "The map is <b>not</b> ranking the famous, well-understood strong currents. Energy must "
             "come from the current's <i>anomaly</i>, not its total."],
            ["Does a steady jet score zero?", "A perfectly steady 1.5 m/s jet scores under 1e-20",
             "The cleanest test of the whole idea: a strong but unvarying current carries no "
             "information and must rank at the bottom."],
            ["Is the anomaly really an anomaly?",
             "Maximum time-mean of the anomaly: <b>5.7e-16 m/s</b>",
             "Numerically zero - the mean flow really has been removed."],
            ["Did the shallow-water guard actually rescue the map?",
             "It excludes 3,042 too-shallow cells, and <b>none of them were in the top 200 either "
             "way</b>",
             "<b>The bug's mechanism is gone - the guard did not save this particular map.</b> Both "
             "statements are on the page."],
        ],
        widths=[0.26, 0.32, 0.42], font_size=7.9,
    ),
    numbers=[
        "The mean flow is removed over a <b>rolling 30-day window</b>, not over the whole record. "
        "This basin reverses its circulation seasonally, so subtracting a full-record mean would "
        "leave the monsoon reversal inside the anomaly and the 'energy' would simply be the seasonal "
        "cycle, large almost everywhere.",
        "The two factors are combined by the <b>same</b> geometric-mean method version 1 used, "
        "deliberately - so a version 1 versus version 2 comparison measures the factor swap and not "
        "a change of scaling. A test asserts the two rank identically when version 1 is given a "
        "neutral third factor.",
        "<b>8,790 cells ranked.</b> Top candidates cluster at 7 N, 50-54 E - the Somali Current and "
        "Great Whirl region.",
    ],
    impact_rows=[
        ["Observation-network planners", "A data-driven starting point for where an additional "
         "deployment might be most informative."],
        ["Research cruise planning", "Suggests where ship time would return the most information."],
        ["The modelling team", "Closes the loop - the model's own weaknesses point at what would "
         "most improve it."],
        ["The jury", "A worked example of a team bounding its own claim in code because prose is not "
         "enough."],
    ],
    society="Ocean observation is publicly funded and severely limited by cost. Any tool that helps "
            "place a limited number of instruments where they will teach the most makes that public "
            "money go further - provided it is offered as a suggestion to an expert rather than as "
            "an instruction, which is exactly the line this feature enforces.",
    pitch="If you could deploy one more instrument, where should it go? We rank the basin by two "
          "things: where the model is uncertain, and where the water is energetic. The top "
          "candidates cluster at 7 north, 50 to 54 east - the Somali Current and the Great Whirl. "
          "But I want you to see how carefully this is claimed. Our own literature review says "
          "observation-priority is already done and done better, so the sanctioned wording lives in "
          "the code and is rendered verbatim, and a test greps both the module and the page for any "
          "phrasing saying the model tells anyone where to deploy floats. We test the rhetoric, "
          "because no numerical test can catch a rhetorical error.",
    pitch_note="Testing the wording is a genuinely unusual practice - point it out explicitly.",
    qa=[
        ("Is this not just showing you the Somali Current?",
         "We tested exactly that objection. The overlap between the top decile of our energy field "
         "and the top decile of mean current speed is only 0.305, and a perfectly steady 1.5 m/s jet "
         "scores under 1e-20 in our metric. We rank variability, not speed - a strong but unvarying "
         "current teaches you nothing."),
        ("Are you claiming novelty for this?",
         "No, explicitly. Our novelty matrix marks observation-priority as already done, and names "
         "the formally-optimised prior work. Ours is a simple heuristic with no cost model, no float "
         "drift physics and no budget constraint. We kept it because it is useful and we dropped the "
         "novelty claim because it is not ours."),
        ("What was wrong with the first version?",
         "It used float sparsity - distance to the nearest float - and the places floats are most "
         "absent are often the places floats cannot go. It ranked the Persian Gulf, about 20 metres "
         "deep, at the top. Energy asks about the water rather than about the observing network, so "
         "the failure mode is structurally gone. And the page has a switch to turn the guard off so "
         "you can watch the old failure reappear."),
    ],
    limit=("A heuristic, and it says so", "This is a simplified version of an established research "
           "area with dedicated formal methods - optimising float deployment to minimise mapping "
           "uncertainty, differentiable sensor placement, and more. Ours has no cost model, no float "
           "drift physics and no budget constraint, and one of its two inputs - the model's sigma - "
           "was itself measured to be mildly overconfident. It is a suggestion to an expert, framed "
           "as one, and never as an instruction to an agency."),
))

# ------------------------------------------------------------------ 17
SPECS.append(dict(
    n=17, short="Cyclone Case Study", kicker="A PROCESS NOBODY TAUGHT IT",
    title="Cyclone Case Study",
    subtitle="The reconstruction resolves a cyclone's cold wake - once you ask the question the "
             "right way.",
    meta=[("Port", "8517"), ("Page file", "app/phase2/cyclone_volume_page.py"),
          ("Storm", "SHAKHTI, Arabian Sea, Oct 2025"), ("Result", "cooling at 11 of 12 track points")],
    lead="Every other feature in this pack shows the model matching something it was trained toward. "
         "This one shows it reproducing a physical process that appears nowhere in its training "
         "objective - and that is a stronger statement than any error figure.",
    plain=[
        "When a cyclone crosses the ocean it mixes and upwells cold water from below, leaving a "
        "<b>cold wake</b> along its track that stays visible for a week or more. Our model is driven "
        "only by surface satellite fields and was never taught that cyclones cool the ocean beneath "
        "them. If the reconstruction shows that wake anyway, it is reproducing real physics rather "
        "than reciting a fit.",
        "It does. Along cyclone SHAKHTI's Arabian Sea track in October 2025, the cyclone heat "
        "potential fell at <b>11 of 12 track points - 92%</b>, with a mean drop of 4.26 kJ/cm2.",
        "<b>But the first way we measured it said there was no wake at all, and that half is just as "
        "interesting.</b> Comparing one fixed 'before' date against one fixed 'after' date gave a "
        "mean change of -0.18 kJ/cm2 and cooling at only 7 of 12 points. Same storm, same "
        "reconstruction, same code. Only the question changed.",
        "The reason is physical. A storm takes days to cross a basin, so one pair of dates asks the "
        "wrong question at every point but one: water at 68 east was hit on day one and had already "
        "recovered by the 'after' date, while water at 60 east was hit on day six and its wake was "
        "three days old. Comparing each point against <b>its own passage time</b> is the right "
        "question. <b>The page shows both</b>, because showing only the good number would be asking "
        "to be trusted.",
    ],
    analogy="Photograph a crowd before and after a parade passes and you will conclude nothing "
            "happened - the front of the route has already emptied while the back has not filled "
            "yet. Photograph each spot as the parade reaches it, and the pattern is unmistakable.",
    screen_intro="One storm, two measurements, and a three-dimensional object that is honestly "
                 "labelled:",
    screen=[
        "The storm track with the change in heat potential marked at every track point.",
        "<b>Both</b> measurements side by side - the naive fixed-date pair, and the passage-relative "
        "one - so the contrast is the point rather than a footnote.",
        "A verdict in words, not just a number, so the page cannot render a null result under the "
        "word 'wake'.",
        "An isosurface of the <b>warm layer itself</b> - the body of water above 26 degrees, whose "
        "thickness is D26 - thinning along the track. That is the fuel being spent.",
        "Both agencies' peak wind estimates, with their disagreement stated rather than resolved in "
        "favour of the larger one.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/cyclone_volume_page.py "
            "--server.port 8517",
    steps=[
        "Run the command and open <b>http://localhost:8517</b>.",
        "Select cyclone SHAKHTI, Arabian Sea, 1-7 October 2025.",
        "<b>Read the cost warning before you start the run.</b> A week-long track needs 14 whole-basin "
        "reconstructions - about seven minutes on CPU, two on GPU. The page states this before it "
        "spends it, because a page that goes quiet for seven minutes looks broken.",
        "Show the naive fixed-date result first. It reports essentially nothing.",
        "Then show the passage-relative result: cooling at 11 of 12 points, mean -4.26 kJ/cm2. Let "
        "the contrast land.",
        "Finish on the warm-layer isosurface thinning along the track - this is the picture people "
        "remember.",
    ],
    run_note=("A dimensional point the page insists on", "'A 3-D heat potential volume' is "
              "dimensionally confused: heat potential is a depth <i>integral</i>, measured in kJ per "
              "square centimetre, and a 2-D field has no volume. So this page does not draw one. "
              "What <i>is</i> three-dimensional, and is exactly what a cyclone eats, is the warm "
              "layer itself - and the caption says which is which.", "note"),
    why=[
        "The problem statement is a disaster-management problem statement. Demonstrating that the "
        "reconstruction captures a real cyclone-ocean interaction is the most direct evidence that "
        "it is fit for that purpose - far more so than an aggregate error figure.",
        "It is also the strongest scientific validation in the pack. Matching a training target "
        "shows a model has fitted. Reproducing an untaught physical process, from surface data "
        "alone, shows it has learned something about how the ocean works.",
    ],
    ps_rows=[
        ["Proof of concept over the Arabian Sea",
         "A real named storm, a real track, a real measured ocean response."],
        ["Daily temporal resolution",
         "Passage-relative measurement is only possible with daily fields - a monthly average erases "
         "the entire signal."],
        ["Disaster-management relevance",
         "The cold wake governs whether a following storm finds fuel, and is directly operational."],
    ],
    numbers_intro="The measurement, and the measurement that would have been wrong [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["How the question was asked", "Mean change", "Points that cooled"],
            ["<b>Each point against its own passage time</b>", "<b>-4.26 kJ/cm2</b>, largest -7.4",
             "<b>11 of 12 (92%)</b>"],
            ["One fixed before/after date pair", "-0.18 kJ/cm2", "7 of 12 (58%)"],
        ],
        widths=[0.46, 0.29, 0.25],
    ),
    numbers=[
        "Same storm, same reconstruction, same code. <b>Only the question changed.</b> The function "
        "returns a verdict <i>string</i> as well as a number, so a page structurally cannot render "
        "-0.18 under the word 'wake', and a test asserts that a flat field yields <i>'no clear cold "
        "wake'</i>.",
        "<b>A correction we made about our own reporting.</b> An earlier internal note quoted the "
        "storm's peak wind as 74 knots. The archive carries two agency estimates that disagree: one "
        "gives a peak of 60 knots over 41 rated points, the other 74 knots over 29 - <b>14 knots "
        "apart, spanning a storm-category boundary</b>. The loader now carries both, prefers the "
        "internationally-endorsed figure, and exposes the disagreement rather than quietly picking "
        "the larger number.",
        "<b>An error of our own, caught by rendering the page.</b> One panel reported that a date was "
        "'outside the bundle'. It was not - the date simply had not been reconstructed yet. Reporting "
        "one absence as a different absence, on a page whose whole subject is measuring absences "
        "correctly. The two cases are now distinguished.",
    ],
    impact_rows=[
        ["Cyclone forecasters", "Evidence that the reconstruction tracks the ocean's actual response "
         "to a storm, which is what intensity forecasting depends on."],
        ["Disaster management", "A basis for assessing whether a second storm following a first will "
         "find depleted or replenished fuel."],
        ["Ocean scientists", "Daily basin-wide cold-wake analysis from satellites, for storms where "
         "no float happened to be in the way."],
        ["The jury", "The clearest evidence in the pack that the model learned physics rather than "
         "memorising a target."],
    ],
    society="Cyclones in the North Indian Ocean kill and displace people on a scale few other natural "
            "hazards match in this region. A system that demonstrably captures the ocean's response "
            "to a storm - daily, everywhere, from satellites - contributes directly to the "
            "forecasting chain that decides when a coastal district is told to move.",
    pitch="This is the result I would most like you to remember. A cyclone drags cold water up "
          "behind it, leaving a cold wake. Our model is driven only by surface satellite fields and "
          "was never taught that cyclones cool the ocean. Along SHAKHTI's track, heat potential fell "
          "at 11 of 12 points, mean 4.26 kJ per square centimetre. But look at the first "
          "measurement: comparing one fixed before-and-after pair, we found essentially nothing - "
          "seven of twelve, mean 0.18. Same storm, same code. Only the question changed, because a "
          "storm takes days to cross a basin and one date pair asks the wrong question everywhere "
          "but one point. We show you both, because showing only the good number would be asking to "
          "be trusted.",
    pitch_note="Close the demo with this. It is the strongest scientific claim in the project.",
    qa=[
        ("Could the cold wake simply be in the satellite input already?",
         "The surface cooling is, and that is honest - the model reads sea-surface temperature. What "
         "the model is not told is how that surface signal propagates into a subsurface heat "
         "content change along a moving track. Reproducing the depth-integrated response at 11 of 12 "
         "points, from surface fields alone, is the result."),
        ("Is one storm enough to prove anything?",
         "No, and we do not claim it proves a general capability. It is a case study on one named "
         "storm, and we present it as one. What it does establish is that the mechanism is present "
         "in the reconstruction and that we know how to measure it correctly - including which way "
         "of measuring it would have produced a false negative."),
        ("Why does your naive measurement disagree with your headline one?",
         "Because a storm takes days to cross the basin, so a single before-and-after pair asks the "
         "wrong question at every point but one. That is a physical fact about moving storms, not a "
         "choice of favourable numbers - which is exactly why both results are on the page and the "
         "function returns a verdict in words as well as a number."),
    ],
    limit=("One storm, one basin, one week", "This is a case study, not a validated capability. No "
           "cold-wake climatology was computed, no second storm was analysed, and the Bay of Bengal "
           "counterpart is specified but not run. The measurement also inherits every limit of the "
           "underlying heat-content product, including the model's warm bias - and the cost is real: "
           "14 whole-basin reconstructions, about seven minutes on CPU, which the page states before "
           "it spends it."),
))

# ------------------------------------------------------------------ recaps
_RECAPS = {
    13: ("Both of the model's numbers on one map - what it predicts and how much to believe it - "
         "with the exact size of its own overconfidence published.",
         [("91.2%", "coverage against a 95.4% nominal"),
          ("80.1 to 95.5%", "the range, because the mean hides a bad depth"),
          ("100 m", "least certain AND most overconfident depth")]),
    14: ("Turns temperature into sound speed - the quantity operators act on - and refuses the one "
         "map the grid cannot honestly support.",
         [("89%", "of the sound-speed error budget is temperature"),
          ("336 of 848", "false SOFAR detections the guard removed"),
          ("ZERO", "resolvable axis cells - stated in words")]),
    15: ("Set out to measure robustness to monsoon cloud and instead measured a warm bias in the "
         "deliverable, with the convenient reading explicitly rejected.",
         [("0.8950", "degC at 15% blanked - better, and not robustness"),
          ("60x", "the noise floor, so the dip is real"),
          ("+0.50 degC", "the real degradation at total blindness")]),
    16: ("Ranks where another observation would teach the model most - and enforces the boundary of "
         "that claim with a test on its own wording.",
         [("8,790", "cells ranked"),
          ("0.305", "overlap with mean speed - it is not just the current"),
          ("under 1e-20", "score for a steady jet, as it must be")]),
    17: ("The reconstruction reproduces a cyclone's cold wake it was never taught - and the "
         "measurement that would have found nothing is shown beside it.",
         [("11 of 12", "track points cooled, passage-relative"),
          ("-4.26 kJ/cm2", "mean drop along the track"),
          ("7 of 12", "what the naive question found instead")]),
}
for _s in SPECS:
    _s["recap"], _s["tiles"] = _RECAPS[_s["n"]]
