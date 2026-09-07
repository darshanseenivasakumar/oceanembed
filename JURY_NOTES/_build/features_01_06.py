"""Feature notes 1-6. Every figure is transcribed from PROJECT_RECORD.md, docs/ or a commit."""
from __future__ import annotations

SPECS = []

# ------------------------------------------------------------------ 1
SPECS.append(dict(
    n=1, short="Phase-1 App", kicker="THE FIRST WORKING SYSTEM",
    title="Phase-1 App",
    subtitle="The original end-to-end demo, deliberately frozen so it can never be quietly improved.",
    meta=[("Port", "8501"), ("Page file", "app/streamlit_app.py"),
          ("Engine", "MLP + LightGBM + climatology"), ("Status", "FROZEN, read-only")],
    lead="Before anything clever was attempted, one question had to be answered: can a satellite "
         "surface picture be turned into a full temperature profile down to 1000 m at all? The "
         "Phase-1 App is the answer to that question, and it has been sealed shut ever since.",
    plain=[
        "The Phase-1 App is a small web dashboard. You open it in a browser, you pick a point in the "
        "North Indian Ocean and a date, and it draws the temperature of the water underneath that "
        "point at fifteen standard depths, from the surface down to one kilometre.",
        "Underneath it are three separate methods that all answer the same question, so the answers "
        "can be compared: a small neural network that reads eleven surface numbers and writes out "
        "fifteen depth temperatures; a LightGBM model built as a deliberate rival; and plain "
        "climatology, which is simply the long-term average for that month. Climatology is the bar "
        "every model must clear - if a model cannot beat the average, it has learned nothing.",
        "The important word in this note is <b>frozen</b>. This app is marked read-only in the "
        "project's own rules. No later work is allowed to edit it. That is not laziness; it is how "
        "we can still prove today what the system could genuinely do on the day it was first "
        "demonstrated, without anyone retrofitting a better result into it.",
    ],
    analogy="Think of a doctor who can only take your skin temperature, but has to report your core "
            "temperature. Phase 1 is the first working version of that instrument for the ocean - "
            "rough, honest, and sealed in a glass case so nobody can adjust it after the fact.",
    screen_intro="Four panels, each one answering a different kind of question:",
    screen=[
        "<b>Map panel</b> - the whole basin at one chosen depth, coloured by temperature, so you see "
        "the shape of the water and not just a number.",
        "<b>Profile panel</b> - one point, fifteen depths, drawn as a vertical line down the page. "
        "This is the shape an oceanographer actually reads.",
        "<b>Priority panel</b> - the first version of 'where would another measurement be worth "
        "most', built from anomaly, uncertainty and float sparsity combined as a geometric mean.",
        "<b>Validation panel</b> - the model's own report card against real Argo floats it never saw "
        "during training.",
    ],
    run_intro="One command. It needs no GPU and no network; everything it reads is already on disk.",
    command="PYTHONPATH=src python -m streamlit run app/streamlit_app.py --server.port 8501",
    steps=[
        "Open a terminal in the project folder and activate the project's virtual environment.",
        "Run the command above. Streamlit prints a local address, normally "
        "<b>http://localhost:8501</b>.",
        "Open that address in a browser. The map panel loads first.",
        "Use the depth selector to move between the fifteen standard depths, and watch the basin "
        "change shape as you go deeper.",
        "Switch to the profile panel and enter a latitude and longitude inside 5-30 N, 45-105 E to "
        "get the full column at that point.",
        "Finish on the validation panel - that is where the model is shown being checked, which is "
        "the panel a jury will care about most.",
    ],
    run_note=("If a panel looks plain", "The shell has a deliberate fallback: if a specialist panel "
              "is unavailable it draws a simpler built-in version rather than crashing. A demo that "
              "always renders something is worth more than one that renders beautifully or not at "
              "all.", "note"),
    why=[
        "The problem statement asks for a system that reconstructs subsurface temperature from "
        "surface satellite observations and reports RMSE, correlation and bias. Phase 1 is the first "
        "complete pass through that entire chain - download, preprocess, train, predict, validate, "
        "display - with nothing faked in the middle.",
        "It also settled the project's engineering rules, and those rules are why the later numbers "
        "can be trusted. Normalisation values ride inside the model file itself, so a checkpoint can "
        "never be scored with the wrong scaling. One data loader is shared by training and "
        "evaluation, so the two can never drift apart. The comparison between models uses a fixed "
        "tie rule agreed in advance, so nobody picks the winner after seeing the scores.",
    ],
    ps_rows=[
        ["Reconstruct profile from surface", "One forward pass returns all 15 standard depths for a "
         "chosen point and date."],
        ["Evaluate RMSE, correlation, bias", "The validation panel reports all three, per depth, "
         "against independent Argo floats."],
        ["15 standard depths, 0-1000 m", "The depth list is a frozen constant in "
         "<font face='Consolas' size='8'>src/oceanembed/config.py</font> and is imported everywhere, "
         "never retyped."],
        ["Proof of concept over the NIO", "The grid is exactly 5-30 N, 45-105 E at 0.25 degrees - "
         "100 x 240 = 24,000 cells."],
    ],
    numbers_intro="Measured against 879 independent Argo profiles that were never used in training "
                  "[VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["What was measured", "Value", "Reading"],
            ["RMSE against independent Argo", "0.9638 degC", "average error across all depths"],
            ["Skill against climatology", "+0.387", "39% better than the long-term average"],
            ["Training data", "48 monthly GLORYS steps, 2019-2022", "monthly, not daily - the "
             "Phase-2 limit this exposed"],
            ["Model size", "11 inputs -> 128 -> 128 -> 15 outputs", "small on purpose"],
        ],
        widths=[0.35, 0.28, 0.37],
    ),
    numbers=[
        "It works, and it is modest. 0.9638 degC is a real result on real held-out floats, and it is "
        "the number Phase 2 was built to beat.",
        "The monthly cadence was the binding limit. Averaging a whole month erases cyclones, eddies "
        "and fronts - which is precisely the motivation for the daily Phase-2 system in Feature 7.",
    ],
    impact_intro=["A first version that is honest about being a first version is worth more to a "
                  "reviewer than a polished one with no history."],
    impact_rows=[
        ["The jury", "A visible before-and-after. They can watch the project improve from 0.9638 to "
         "0.9063 degC and see exactly what bought the improvement."],
        ["The sponsor (INCOIS / MoES)", "Proof the full pipeline exists and runs on their region, "
         "their depths and their grid - not on a toy problem."],
        ["The team", "A frozen reference point. Any later regression is instantly visible because "
         "this one cannot move."],
        ["A future maintainer", "The engineering rules that keep the later numbers honest were all "
         "written here, and are documented as numbered decisions."],
    ],
    society="Every operational forecast system starts as somebody's first working version. Freezing "
            "it, publishing its worst numbers and refusing to edit it afterwards is the difference "
            "between a research demo and something a public agency could eventually rely on.",
    pitch="This is where we started, and we have not touched it since. It reconstructs the full "
          "water column from surface data, it scores 0.9638 degC against 879 floats it never saw, "
          "and it is locked read-only so you can see exactly how far the project moved afterwards. "
          "Everything else we will show you today had to beat this.",
    pitch_note="30-second opener - use this to set up the improvement story.",
    qa=[
        ("Why show us an old version at all?",
         "Because it is the control. Without it, our final number is just a number. With it, we can "
         "show a measured improvement from 0.9638 to 0.9063 degC on independent floats - different "
         "years, grids and scoring protocols, so a comparison of eras rather than a controlled one - "
         "and name what changed: daily data instead of monthly, and a 3-D encoder over an 11-day "
         "window instead of a per-column MLP. The climatology-anchored decoder we built was measured "
         "to cost accuracy and is NOT shipped."),
        ("Is climatology not a very weak baseline?",
         "It is the standard one in this field, and it is not weak everywhere. At 1000 m climatology "
         "still beats our shipped model by 0.024 degC. We label that on the chart rather than hide "
         "it - our model wins at 14 of 15 depths, not 15."),
        ("How do you know the floats were really held out?",
         "The Argo profiles are never in the training set, and the train/test split is a frozen "
         "constant in the config file with an assertion that runs at import time in the tests. The "
         "split cannot be changed by editing a script."),
    ],
    limit=("Two known problems, both stated", "The Phase-1 out-of-distribution detector is not "
           "validated - it flags 99.18% of the real test set, because the reference file it compares "
           "against is a stale synthetic one. The detector logic is correct; its input file is "
           "wrong. Separately, the Phase-1 MC-dropout uncertainty was measured overconfident at "
           "every depth, worst at 3.54x at 20 m. Both are recorded in the project decisions log, "
           "and neither is used by the shipped Phase-2 system, which has its own calibrated "
           "uncertainty - see Feature 13."),
))

# ------------------------------------------------------------------ 2
SPECS.append(dict(
    n=2, short="Collocation", kicker="ONE POINT, EVERY SOURCE, ONE ANSWER",
    title="Collocation Engine",
    subtitle="Ask one point of the ocean what every instrument says about it - and how far away each "
             "of those instruments actually was.",
    meta=[("Port", "8502"), ("Page file", "app/phase2/collocation_page.py"),
          ("Module", "phase2/data/collocation.py"), ("Tests", "test_collocation.py")],
    lead="Every other feature in this project eventually asks the same question: what did each "
         "source report here? Answering it once, in one place, with one set of rules, is what stops "
         "five different features from quietly inventing five slightly different answers.",
    plain=[
        "You give it a latitude, a longitude and a date. It returns a single record listing what the "
        "satellite saw, what the GLORYS reanalysis says, what our model reconstructed, what the wind "
        "was doing, and - if a real Argo float happened to be nearby - what that float actually "
        "measured in the water.",
        "The part that makes it trustworthy is the second half of every record: <b>how far away each "
        "match really was</b>, in kilometres and in days. A float 2 km away and on the same day is "
        "strong evidence. A float 60 km away and four days later is weak evidence. Both are useful; "
        "pretending they are the same is not.",
        "So the engine never hands you a bare label. It measures the offsets first and derives the "
        "quality from them: HIGH within 2 days, MEDIUM within 5, LOW within 10, and REJECT beyond "
        "that or outside the grid. You can always see the number the label came from.",
    ],
    analogy="It is the ocean's version of a witness statement that also records where the witness "
            "was standing. Two people can both say they saw the accident - one from the pavement, "
            "one from four streets away. A serious investigator writes down the distance.",
    screen_intro="One point in, one complete evidence card out:",
    screen=[
        "The value each source reports at that point, side by side, each keeping its own numbers "
        "verbatim - no source is ever overwritten or substituted for another.",
        "The measured spatial offset in kilometres and the temporal offset in days, for every match.",
        "A colour-coded quality flag - green HIGH, amber MEDIUM or LOW, red REJECT - derived from "
        "those offsets, never asserted.",
        "An era switch: the Phase-1 record of 48 monthly fields (2019-2022), or the Phase-2 record "
        "of 388 consecutive daily fields (1 June 2025 to 23 June 2026).",
        "Full provenance: which files were read, which grid cell was used, which offsets applied.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/collocation_page.py --server.port 8502",
    steps=[
        "Run the command above and open <b>http://localhost:8502</b>.",
        "Choose the era. Pick <b>daily</b> to work in the shipped model's own time window, or "
        "<b>phase1</b> to reproduce the originally published Phase-1 collocation numbers.",
        "Type a latitude and longitude inside the basin - 15.0 N, 65.0 E in the Arabian Sea is a "
        "good demonstration point.",
        "Pick a date inside the chosen era's range.",
        "Read the quality flag first, then the offsets, then the values. That order is deliberate: "
        "it teaches the audience to check the evidence before reading the number.",
        "Try a point on land, such as 21.75 N, 47.50 E, to see the engine refuse rather than invent "
        "a value.",
    ],
    run_note=("An empty result is a real answer", "If no float was near that point on that date, the "
              "engine reports a gap in the float table - not an empty ocean. Those are completely "
              "different claims, and confusing them once cost this project a wrong conclusion, which "
              "is recorded in the corrections log.", "warn"),
    why=[
        "The problem statement requires preprocessing and harmonisation of multiple data sources, "
        "and independent validation against float observations. Both of those are collocation "
        "problems: you cannot harmonise or validate anything until you can say, defensibly, that two "
        "measurements refer to the same piece of ocean at the same time.",
        "It also protects every downstream number. The validation lab, the Argo overlay, the "
        "transect and the cyclone study all consume this engine rather than writing their own "
        "matching rule, so a single, reviewable definition of 'nearby' governs the whole project.",
    ],
    ps_rows=[
        ["Preprocessing and harmonisation", "Seven channels from five distinct products answered at "
         "one point, each keeping its own units and provenance."],
        ["Independent validation with Argo", "Provides the matched float pairs every validation "
         "surface in the project uses."],
        ["Report bias honestly", "Records the offsets that any bias estimate depends on, so a "
         "reviewer can weigh the match quality themselves."],
    ],
    numbers_intro="The design was forced by measurements taken on 26 August 2026, not chosen by "
                  "preference [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Measurement", "Result", "What it forced"],
            ["Distance from an Argo float to the nearest grid centre",
             "median 10.8 km, 95th percentile 16.1 km, max 19.0 km",
             "Space is easy - a 0.25 degree cell is about 27 km wide, so nearest-neighbour is always "
             "inside half a cell."],
            ["Time from a float to the nearest gridded date (2,455 profiles)",
             "within 1 day: 9.5% / 3 days: 22.6% / 5 days: 36.5% / 7 days: 50.3% / 15 days: 99.7%",
             "Time is the hard decision. Tighter matching means less data; looser matching means "
             "weaker evidence. There is no free choice."],
            ["Chosen thresholds", "HIGH 2 days, MEDIUM 5 days, LOW 10 days, reject beyond 10 days or "
             "beyond 20 km", "Stated openly and configurable, so a reviewer can move them and "
             "re-run."],
        ],
        widths=[0.28, 0.32, 0.40], font_size=8.0,
    ),
    numbers=[
        "Because the offsets are recorded on every record rather than averaged away, any later "
        "result can be re-checked at a stricter tolerance. That is how the project separated real "
        "reanalysis error from collocation mismatch in Feature 3.",
    ],
    impact_rows=[
        ["Ocean scientists", "A single defensible answer to 'do these two measurements describe the "
         "same water', instead of a per-study convention."],
        ["The jury", "Direct evidence that our validation is not cherry-picked - the match quality "
         "is on screen beside every comparison."],
        ["INCOIS / MoES", "A reusable harmonisation layer. Any new instrument - a buoy, a glider, a "
         "new satellite - plugs in as another source with its own measured offsets."],
        ["The team", "One matching rule to review instead of five, and therefore one place a "
         "mistake could hide instead of five."],
    ],
    society="Ocean data arrives from instruments that never agree on where or when to measure. A "
            "public agency merging them for a public forecast needs the merge itself to be "
            "auditable. This is that audit trail, and it refuses to hide a weak match behind a "
            "confident label.",
    pitch="Ask it about any point in the basin and it tells you what every instrument says there - "
          "and, crucially, how far each of those instruments actually was in kilometres and days. We "
          "measured that a random float sits a median 10.8 km from a grid centre but a median 7 days "
          "from a gridded date, so space is easy and time is the real scientific decision. Rather "
          "than pick a tolerance silently, we record the offset on every single record and derive "
          "the quality from it.",
    qa=[
        ("Why not just use a weighted score combining distance and time?",
         "Because there is no defensible exchange rate between kilometres and days, and inventing "
         "one would bury an assumption inside a number. We rank by distance first and use time to "
         "break ties, and we show both."),
        ("What happens if no float is nearby?",
         "The record says the float table has no rows for that point and date. It never returns "
         "zero, and it never returns a neighbour's value. In this project an absence is reported as "
         "an absence."),
        ("Could a bad match still slip into your headline result?",
         "The headline validation uses a 5-day tolerance and the record carries the collocation "
         "statistics - max 18.7 km, mean 10.5 km. The reanalysis comparison was also re-run at a "
         "tighter 3-day, 25-km match and the numbers barely moved, which is how we know the error we "
         "report is real error and not mismatch."),
    ],
    limit=("It cannot fix sparse data", "Collocation makes match quality visible; it does not create "
           "floats where there are none. In the Phase-1 era the float table holds 2022 rows only, so "
           "a query in 2019 correctly returns an empty match - and reading that as 'the ocean was "
           "empty' rather than 'the table has no rows' is exactly the error this engine now blocks "
           "by reporting coverage explicitly."),
))

# ------------------------------------------------------------------ 3
SPECS.append(dict(
    n=3, short="Validation Lab", kicker="THE PAGE THAT SHOWS OUR WORST NUMBERS",
    title="Validation Lab",
    subtitle="Separates the error we caused from the error we inherited - the single most useful "
             "diagnostic this project produced.",
    meta=[("Port", "8503"), ("Page file", "app/phase2/validation_page.py"),
          ("Module", "phase2/validation/lab.py"), ("Design", "shows the worst number on purpose")],
    lead="Any team can report an error figure. The harder and far more valuable question is: whose "
         "error is it? Our model was trained to reproduce a reanalysis, so it can never be more "
         "accurate than that reanalysis. This page measures the reanalysis itself, and then subtracts.",
    plain=[
        "Our model learns from GLORYS, a physics-based ocean reanalysis. GLORYS is very good, but it "
        "is not perfect - it has its own error against real floats. If GLORYS is 1.1 degC wrong at a "
        "given depth, then a model that copies GLORYS perfectly is also 1.1 degC wrong there, and no "
        "amount of extra training will fix it.",
        "So the Validation Lab measures three separate things and refuses to let their names blur "
        "together: <b>our model on real satellite input</b> (the actual deliverable), <b>our model "
        "fed reanalysis input</b> (its own ceiling), and <b>the reanalysis itself against floats</b> "
        "(the ceiling nobody else in this project had ever measured).",
        "The result is a map of where effort would actually pay. It tells us which parts of the "
        "error are ours to fix and which are baked into the training target - and we publish both, "
        "including the parts that make us look worse.",
    ],
    analogy="A student scoring 82% looks average until you learn the textbook they studied from has "
            "errors on 15% of its pages. This page grades the textbook first, then grades the "
            "student against what was actually learnable.",
    screen_intro="Three comparisons, deliberately never merged:",
    screen=[
        "Per-depth error for the model on satellite inputs - the deliverable, and the number that "
        "must be quoted.",
        "Per-depth error for the same model fed reanalysis inputs - a comparator only, never the "
        "headline.",
        "Per-depth error of the GLORYS reanalysis itself against independent Argo - the ceiling.",
        "A skill-versus-climatology chart that labels the crossover point outright, including the "
        "depth where climatology wins.",
        "The inherited-versus-ours split, using a stated tolerance that a reviewer can move.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/validation_page.py --server.port 8503",
    steps=[
        "Run the command and open <b>http://localhost:8503</b>.",
        "Start on the per-depth error chart. Point out the bulge at 100 m - that is the thermocline, "
        "the hardest depth in the whole problem.",
        "Switch on the reanalysis line. The audience sees our error and the training target's error "
        "almost touching through the thermocline.",
        "Move to the inherited-versus-ours panel, which states which depths we could still improve.",
        "Finish on the skill chart, and point at 1000 m where climatology beats us. Saying that out "
        "loud before a judge finds it is the most persuasive thing on this page.",
    ],
    extra_commands=[
        ("REPRODUCE THE REANALYSIS CEILING",
         "PYTHONPATH=src python scripts/phase2/glorys_vs_argo.py"),
    ],
    why=[
        "The problem statement asks for evaluation by RMSE, correlation and bias against independent "
        "observations. This page does that, and then does the thing the requirement implies but does "
        "not spell out: it establishes what a perfect answer would even look like given the training "
        "target available.",
        "For a jury, it is also the credibility feature. A team that has measured its own ceiling and "
        "publishes the depth where a trivial baseline beats it is a team whose other numbers can be "
        "believed.",
    ],
    ps_rows=[
        ["Evaluate RMSE, correlation, bias", "All three, per depth, with the independent-Argo sample "
         "size shown beside every value."],
        ["Independent validation", "Scored against Argo profiles never used in training, matched "
         "through the Feature 2 engine."],
        ["Training target: GLORYS reanalysis", "Measures that target's own accuracy, so the "
         "deliverable's error can be attributed rather than merely reported."],
    ],
    numbers_intro="The reanalysis was measured against independent floats with no model involved at "
                  "all - 2,455 profiles reduced to 888 usable matches, 11,761 depth comparisons, "
                  "within 5 days, distances max 18.7 km / mean 10.5 km / 95th percentile 16.5 km "
                  "[VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Depth band", "Finding", "Whose error is it?"],
            ["100-150 m (thermocline)", "The <b>Phase-1</b> model sat within <b>0.023 degC</b> of "
             "the reanalysis's own error", "<b>Mostly inherited.</b> On the SHIPPED v2 model the "
             "gap at 100 m is <b>0.178 degC</b> - still mostly inherited, but not 0.023."],
            ["20-50 m (mixed layer)", "<b>0.31 to 0.38 degC worse</b> than the reanalysis in "
             "Phase 1; <b>0.23 to 0.38</b> on the shipped v2 model",
             "<b>Ours.</b> This is the one place effort would clearly pay."],
            ["1000 m", "Climatology beats the shipped model by <b>0.024 degC</b>",
             "Ours, small, and labelled on the chart. We win at 14 of 15 depths, not 15."],
        ],
        widths=[0.22, 0.42, 0.36], font_size=8.2,
    ),
    numbers=[
        "<b>These are the PHASE-1 figures, which is what this page displays.</b> The Lab reads the "
        "2022 monthly record - 879 profiles, RMSE 0.9638 degC - not the v2 deliverable. Both "
        "columns are given above so the two are never confused: the inherited/ours split is "
        "qualitatively the same on v2, but the thermocline number is 0.178 degC, not 0.023.",
        "Tightening the match to 3 days and 25 km barely moved the reanalysis figures, which is how "
        "we know these are real reanalysis errors and not collocation mismatch.",
        "This single diagnostic redirected the project's remaining effort: a better mixed layer is "
        "available to us, a better thermocline is not.",
    ],
    impact_rows=[
        ["The jury", "The clearest possible evidence of scientific honesty - a page built "
         "specifically to display the project's worst numbers."],
        ["Research teams", "A method they can copy: measure your training target's own error before "
         "claiming your model's error is yours."],
        ["INCOIS / MoES", "Realistic expectations. Knowing an error is inherited stops an agency "
         "funding work that cannot possibly succeed."],
        ["The team", "A priority list backed by measurement rather than intuition."],
    ],
    society="Public money follows published accuracy claims. A system that distinguishes 'we could "
            "improve this' from 'nobody could improve this without better source data' lets funding "
            "go where it can actually change an outcome.",
    pitch="This page exists to show you our worst numbers. Our model was trained on the GLORYS "
          "reanalysis, so we measured GLORYS itself against independent floats first. Through the "
          "thermocline most of our error is inherited - at 100 m the reanalysis scores 1.042 degC "
          "against the same floats while the shipped model scores 1.218, so 0.178 degC of that gap "
          "is ours. In the mixed layer we are 0.23 to 0.38 degC worse than the reanalysis, and that "
          "one is squarely ours. And at 1000 m plain climatology beats us by 0.024 degC, which we "
          "label on the chart. We beat climatology at 14 of 15 depths, not 15. The figures on the "
          "page itself are the Phase-1 measurement; the v2 equivalents are in the table.",
    pitch_note="Deliver this before the jury asks. Volunteering the weak number is the point.",
    qa=[
        ("Is your model just copying GLORYS?",
         "It is trained to reproduce GLORYS, so through the thermocline it is close to that "
         "ceiling - 0.178 degC above it at 100 m, against a reanalysis error of 1.042 degC at the "
         "same depth. But it does so from satellite surface inputs alone, "
         "which GLORYS does not use, and it runs daily on a 0.25 degree grid. Reaching the ceiling "
         "from cheaper inputs is the contribution."),
        ("Why is the thermocline the worst depth?",
         "Because that is where a surface measurement constrains the water least. Our RMSE peaks at "
         "1.22 degC at 100 m and correlation falls to 0.776 there. The reanalysis peaks at almost "
         "exactly the same depth, which is why we call that error inherited."),
        ("A crossover where climatology wins - is that not a failure?",
         "It is a limit, at one depth of fifteen, worth 0.024 degC, and a test asserts the chart "
         "label appears on real data and does not appear when a model genuinely wins everywhere. We "
         "would rather be the team that labels it than the team that is caught by it."),
    ],
    limit=("A disagreement that WAS open, now traced", "The Validation Lab headline (0.9638 "
           "degC over 879 profiles) and the freeze manifest (0.9063 degC over 963 profiles) are two "
           "different models on two different records: <b>lab.py reads "
           "artifacts/argo_error_by_depth.json</b>, the Phase-1 satellite-driven model scored "
           "against 2022 floats on the monthly grid, while the manifest records the v2 daily model "
           "against 2025-26 floats under the seafloor_masked_v1 protocol. Confirmed by reading the "
           "code on 2026-09-07, not inferred."),
))

# ------------------------------------------------------------------ 4
SPECS.append(dict(
    n=4, short="3-D Cube", kicker="THE OCEAN AS A SOLID OBJECT",
    title="OceanCube 3-D",
    subtitle="The reconstruction as a three-dimensional body of water - where the gaps are the sea "
             "floor, not missing data.",
    meta=[("Port", "8504"), ("Page file", "app/phase2/cube_page.py"),
          ("Module", "phase2/cube/ocean_cube.py"), ("Fallback", "2-D slice if 3-D is unavailable")],
    lead="A profile is one line. A map is one depth. The cube is the whole reconstructed volume at "
         "once - and it is the fastest way to make a non-specialist audience understand that this "
         "project outputs a body of water, not a chart.",
    plain=[
        "The model produces a temperature at every one of 24,000 surface cells and at each of 15 "
        "depths. Stack those and you have a solid block of ocean. This page draws that block and "
        "lets you rotate it.",
        "The single most important thing on the page is what the holes mean. Large parts of the "
        "basin are shallower than 1000 m, so those cells simply have no water at the deeper levels. "
        "Roughly a quarter of ocean cells never reach 1000 m at all. Those gaps are the sea floor - "
        "they are a fact about the Earth, not a failure of the model - and the page is built to say "
        "so rather than let a viewer assume the model gave up there.",
        "The vertical axis is deliberately exaggerated, and the caption states by how much. One "
        "kilometre of depth stretched across sixty degrees of longitude is a film of water thinner "
        "than a sheet of paper; drawn honestly to scale you would see nothing at all.",
    ],
    analogy="It is an MRI scan of a sea. A single slice is useful to a specialist; the rotating "
            "volume is what makes everyone else in the room understand what was actually built.",
    screen_intro="The good case and the safe case, in the same page:",
    screen=[
        "A rotatable 3-D volume of reconstructed temperature across the whole basin and all 15 "
        "depths.",
        "Gaps where the sea floor rises above the depth being drawn, labelled as bathymetry and not "
        "as missing output.",
        "A stated vertical exaggeration factor, so nobody reads the shape as a true aspect ratio.",
        "A coarser horizontal sampling for the renderer, with the caption saying the science is "
        "unchanged and only the picture is coarser.",
        "An automatic fallback to a flat 2-D depth slice, with the reason printed, if the 3-D "
        "renderer is missing or the volume is too large for a browser.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/cube_page.py --server.port 8504",
    steps=[
        "Run the command and open <b>http://localhost:8504</b>.",
        "Pick a date inside the model's bundle window.",
        "Let the volume build, then drag to rotate. Turn it until the audience is looking up from "
        "below - the shape of the continental shelf appears immediately.",
        "Point at a hole and say the sentence out loud: that is the sea floor, not missing data.",
        "Change the vertical exaggeration and let the audience watch the basin flatten. This is the "
        "moment they understand the true proportions of the problem.",
        "If the 3-D view is unavailable on the demo machine, the page draws the 2-D slice and prints "
        "why - use that as an example of designed-in graceful degradation.",
    ],
    run_note=("Why the fallback exists", "The 3-D view needs an optional plotting library that is "
              "not guaranteed on a demo machine, and this project has already had a page fail that "
              "way once on this very laptop. A plainer chart that always renders beats a beautiful "
              "one that might not.", "note"),
    why=[
        "The problem statement asks for a depth-resolved reconstruction across a region, not a "
        "point forecast. The cube is the direct visual proof that the output really is "
        "three-dimensional and complete - every ocean cell, every standard depth, one date.",
        "It also demonstrates a discipline that runs through the whole project: an absence is never "
        "drawn as a value. A cell below the sea floor is refused rather than filled, because a "
        "filled cell would silently assert that water exists where there is rock.",
    ],
    ps_rows=[
        ["Depth-wise reconstruction across the region",
         "Renders all 15 depths across all 24,000 grid cells as a single object."],
        ["0.25 degree spatial resolution",
         "The volume is built on the frozen 100 x 240 grid; only the on-screen sampling is coarsened."],
        ["Proof of concept over BoB and Arabian Sea",
         "Both basins are visible in one view, with the shelf structure of each clearly different."],
    ],
    numbers_intro="The classification behind the picture is arithmetic that must add up exactly, and "
                  "it does [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Check", "Numbers", "Why it matters"],
            ["Cell classification at 100 m", "9,763 water + 2,069 below sea floor + 12,168 land = "
             "<b>24,000</b>", "Exactly the grid size. No cell is unclassified or double-counted."],
            ["Cell classification at 1000 m", "8,973 water + 2,859 below sea floor + 12,168 land",
             "Land is unchanged and water is strictly fewer, as physics requires."],
            ["Ocean cells at both depths", "water + sea floor = <b>11,832</b> at both",
             "The same ocean-cell count the export timing artifact independently records."],
            ["Cells with water at all 15 levels", "<b>8,973</b>",
             "About 24% of ocean cells never reach 1000 m - which is what the gaps in the cube are."],
        ],
        widths=[0.26, 0.36, 0.38], font_size=8.0,
    ),
    impact_rows=[
        ["The jury", "The single most memorable image in the demo, and the one that makes the scale "
         "of the output obvious without any explanation."],
        ["Non-specialist stakeholders", "A way to understand a subsurface product without reading a "
         "depth-profile chart."],
        ["Ocean scientists", "Immediate visual sanity-checking of basin-scale structure that a "
         "single profile would hide."],
        ["Educators and students", "A rotatable, real-data object for teaching how the ocean is "
         "layered - built from genuine satellite-driven reconstruction, not an illustration."],
    ],
    society="Public understanding of the ocean is limited by the fact that nobody can see into it. A "
            "truthful, rotatable picture built from real reconstruction - one that draws the sea "
            "floor as the sea floor - is a genuine public-communication asset for a national ocean "
            "agency.",
    pitch="This is the whole output as one object: every ocean cell, every one of fifteen depths, "
          "one day, rotatable. The holes are not missing data - they are the sea floor, and about a "
          "quarter of our ocean cells never reach 1000 m. Our classification adds up to exactly "
          "24,000 cells at every depth, which is how we know nothing is being quietly filled in. And "
          "the vertical scale is exaggerated, with the factor printed, because at true scale a "
          "kilometre of depth across this basin is thinner than paper.",
    qa=[
        ("Are those gaps places your model failed?",
         "No - they are bathymetry. At 1000 m, 2,859 ocean cells are below the sea floor. We refuse "
         "to produce a value there rather than fill it, because a filled cell would assert that "
         "water exists where there is rock."),
        ("The ocean looks far deeper than it is in that picture.",
         "Correct, and that is stated on the page. The vertical axis is exaggerated and the factor "
         "is printed. Drawn to true scale the entire 1000 m column would be invisible across sixty "
         "degrees of longitude."),
        ("Is the science computed at this coarse resolution?",
         "No. The reconstruction is on the full 0.25 degree grid - 100 by 240. Only the on-screen "
         "sampling is reduced so a browser can render it, and the caption says so."),
    ],
    limit=("A picture, not a measurement", "The cube is a rendering of output that is measured "
           "elsewhere. No accuracy claim in this project rests on it. Its own honesty checks are "
           "structural - that the cell classification sums exactly to the grid and that sea-floor "
           "cells are refused rather than filled - and the horizontal sampling shown on screen is "
           "deliberately coarser than the science underneath it."),
))

# ------------------------------------------------------------------ 5
SPECS.append(dict(
    n=5, short="Physics", kicker="THE STRUCTURE INSIDE THE WATER",
    title="Ocean Physics & Structure",
    subtitle="Mixed layer, barrier layer, thermocline and heat content - computed with real seawater "
             "physics, and refused outright where the inputs cannot support them.",
    meta=[("Port", "8505"), ("Page file", "app/phase2/physics_page.py"),
          ("Modules", "phase2/physics/{seawater, layers, ohc}.py"), ("Equation of state", "EOS-80")],
    lead="A temperature profile is raw material. What an oceanographer, a fisherman or a cyclone "
         "forecaster actually needs are the structures inside it: how deep the well-mixed surface "
         "layer goes, where the sharp temperature drop sits, and how much heat the column is "
         "storing. This page computes those, and says no when it cannot.",
    plain=[
        "The <b>mixed layer</b> is the top of the ocean that wind and waves have stirred into a "
        "single uniform slab. Its depth controls how quickly the surface warms, how nutrients reach "
        "the light, and how much heat a storm can draw on.",
        "The <b>thermocline</b> is the sharp drop underneath it, where temperature falls fastest. "
        "The <b>barrier layer</b> is a North Indian Ocean speciality: fresh river water sits on top "
        "of saltier water and forms a lid that stops mixing, which is one reason the Bay of Bengal "
        "intensifies cyclones so effectively. <b>Ocean heat content</b> is the total heat stored "
        "down to a chosen depth.",
        "All of these are computed with genuine seawater physics rather than rules of thumb. The "
        "equation of state used to turn temperature and salinity into density was checked against "
        "four published reference values and agrees to better than one thousandth of a kilogram per "
        "cubic metre - including the standard check value, 1023.343.",
        "And here is the part that a jury should be told deliberately: <b>the page refuses to "
        "compute two of these from satellite input.</b> Density needs salinity at depth, and our "
        "satellite-driven model predicts temperature only. The reanalysis salinity is sitting right "
        "there in the same file and would produce a plausible-looking number - so the page shows a "
        "'refused, not approximated' box instead, and a test asserts the code neither reads nor "
        "returns that salinity.",
    ],
    analogy="Temperature alone is like knowing a patient's temperature at fifteen points down their "
            "body. Structure is the diagnosis: where the layers are, how thick the insulating one "
            "is, and how much energy is stored. This page is the diagnosis step.",
    screen_intro="One date, one grid, three selectable sources:",
    screen=[
        "<b>Mixed layer depth</b> by the density criterion - a 0.03 kg/m3 change from 10 m, the "
        "standard published definition.",
        "<b>Isothermal layer depth</b>, its temperature-only counterpart, and the difference between "
        "the two, which is the barrier layer.",
        "<b>Thermocline depth</b> - where the vertical temperature gradient is steepest.",
        "<b>Ocean heat content</b>, computed with real density from temperature and salinity where "
        "the source allows it.",
        "A source toggle - GLORYS reanalysis, or the shipped satellite model - reading the same day "
        "from the same bundle, so it is a true model-versus-truth comparison and not two different "
        "eras.",
        "A live bias table with a warning printed above the maps when a comparison is not "
        "defensible.",
        "A vertical-gradient consistency panel showing how faithfully the model reproduces the real "
        "shape of the temperature drop.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/physics_page.py --server.port 8505",
    steps=[
        "Run the command and open <b>http://localhost:8505</b>.",
        "Leave the source on <b>glorys</b> first and pick a date. All four structure fields appear, "
        "computed with real density.",
        "Switch the source to <b>v2 satellite</b>. Thermocline and isothermal layer depth still "
        "compute; mixed layer by density and barrier layer are replaced by an explicit refusal box. "
        "<b>Stop and read that box aloud</b> - it is one of the strongest honesty moments in the "
        "demo.",
        "Open the bias table underneath. It is computed live on the date the viewer chose, not "
        "quoted from a stored file.",
        "Finish on the gradient-consistency panel, which shows the model reproducing the thermocline "
        "shape at essentially 100% of the observed gradient.",
    ],
    extra_commands=[
        ("MEASURE THE GRADIENT CONSISTENCY YOURSELF",
         "PYTHONPATH=src python scripts/phase2/measure_physical_consistency.py"),
    ],
    why=[
        "The problem statement is sponsored by a ministry whose users are forecasters and marine "
        "operators. Those users do not act on a temperature at 75 m; they act on mixed layer depth, "
        "on heat content, on where the thermocline sits. This feature is the translation layer "
        "between a research output and an operational one.",
        "It is also where the project's compliance boundary is enforced in code rather than in "
        "prose. The requirement is a satellite-input system. Quietly borrowing reanalysis salinity "
        "to make a prettier map would break that requirement while looking like a feature.",
    ],
    ps_rows=[
        ["Satellite-observation inputs only",
         "Refuses any structure field that would need reanalysis salinity, and a test asserts the "
         "refusal is real."],
        ["Depth-resolved output that is useful downstream",
         "Turns 15 temperatures into the four structural quantities operational users actually "
         "request."],
        ["Physically sound treatment",
         "EOS-80 density and Mackenzie sound speed, both pinned to published reference values by "
         "tests."],
    ],
    numbers_intro="Two independent measurements, both run on this machine [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Measurement", "Result", "Reading"],
            ["Vertical gradient, model vs independent Argo (ratio pred/obs)",
             "8 m: 0.42 &nbsp; 25 m: 0.69 &nbsp; 40 m: 0.81 &nbsp; <b>75-125 m: 1.006</b> &nbsp; "
             "850 m: 1.00",
             "<b>The thermocline is not smoothed</b> - the model reproduces 100.6% of the observed "
             "gradient there. The flattening is in the top ~30 m only."],
            ["Stage-2 structure fields vs GLORYS (bias / RMSE, metres)",
             "MLD -14.12 / 21.34 &nbsp; barrier +8.88 / 19.00 &nbsp; ILD -5.85 / 16.44 &nbsp; "
             "thermocline -1.80 / 24.12",
             "Two of these are <b>not</b> trustworthy, and the page says so on screen."],
            ["Stage-2 heat content 0-300 m vs GLORYS", "bias -0.024 GJ/m2, RMSE 0.664",
             "<b>Heat content survives.</b> An integral is far less sensitive than a threshold "
             "crossing."],
        ],
        widths=[0.27, 0.40, 0.33], font_size=8.0,
    ),
    numbers=[
        "The cause of the mixed-layer failure was traced rather than guessed: surface salinity "
        "carries +0.19 psu of bias, which is roughly 0.15 kg/m3 of density - about <b>five times</b> "
        "the 0.03 kg/m3 threshold the mixed-layer criterion uses. A threshold crossing five times "
        "smaller than the bias will trip at the wrong depth systematically.",
        "The standing instruction inside the project is explicit: do not use the stage-2 mixed layer "
        "or barrier layer for any claim; its heat content is defensible.",
        "A physics-based gradient penalty was added to the training objective and tested across "
        "three seeds. <b>It did not help</b> - and the gradient measurement above explains why: it "
        "was designed to protect structure that was never being lost.",
    ],
    impact_rows=[
        ["Cyclone forecasters", "Mixed layer and barrier layer are direct inputs to intensification "
         "forecasting - the Bay of Bengal barrier layer is a known amplifier."],
        ["Fisheries", "The thermocline sets where many commercially important species concentrate; "
         "its depth is an operational planning variable."],
        ["Climate monitoring", "Ocean heat content is the primary measure of how much heat the "
         "planet is absorbing, and this produces it daily from satellites."],
        ["The jury", "A visible, code-enforced compliance boundary - the page refuses to produce a "
         "number rather than approximate it."],
    ],
    society="Barrier layers in the Bay of Bengal are part of why cyclones there intensify so "
            "dangerously close to one of the most densely populated coastlines on Earth. Producing "
            "these structural fields daily, from satellites, with the untrustworthy ones clearly "
            "marked, is directly relevant to coastal warning.",
    pitch="A temperature profile is raw material; this turns it into the structures forecasters "
          "actually use - mixed layer, barrier layer, thermocline and heat content, with real "
          "seawater physics checked against published reference values. And notice what it does not "
          "do: on satellite input it refuses to compute mixed layer by density, because that needs "
          "salinity at depth that our satellite model does not predict. The reanalysis salinity is "
          "in the very same file and would have produced a beautiful map. We show a refusal box "
          "instead, and a test enforces it.",
    pitch_note="The refusal box is the strongest single moment in the whole demo. Do not rush it.",
    qa=[
        ("Why not just use the reanalysis salinity to fill the gap?",
         "Because the deliverable is a satellite-input system, and that would put a reanalysis field "
         "inside a number labelled satellite. It would look like a feature and function as a "
         "violation. It is a compliance boundary, not a missing capability."),
        ("You said your stage-2 mixed layer is biased by 14 metres. Is that not a serious failure?",
         "It is a measured failure and we publish it. We traced the cause: +0.19 psu of surface "
         "salinity bias against a 0.03 kg/m3 threshold. That is why the standing recommendation "
         "inside the project is not to use that field, while the heat content from the same model - "
         "bias 0.024 GJ/m2 - is defensible. Integrals tolerate bias; threshold crossings do not."),
        ("Did adding physics to the loss function improve the model?",
         "No, and we measured it on three seeds rather than one. At one weight it was clearly worse; "
         "at another the mean sat inside the seed noise and the sign did not hold. We then measured "
         "why: the thermocline gradient was already at 100.6% of the observed value, so the term was "
         "protecting structure that was never being lost. A null result, reported as one."),
    ],
    limit=("Nothing predicts salinity at depth from satellites", "The seven satellite channels carry "
           "a surface salinity only. That single limit is why two of the four structure fields are "
           "refused in satellite mode, and it is a sensor limitation rather than a modelling gap. "
           "Separately, the seasonal barrier-layer comparison shown on this page still rests on the "
           "Phase-1 2019-2022 monthly record and says so, because a four-year seasonal signal cannot "
           "be recomputed on a 388-day bundle without silently changing its magnitude."),
))

# ------------------------------------------------------------------ 6
SPECS.append(dict(
    n=6, short="Events", kicker="FINDING THE THINGS THAT MOVE",
    title="Ocean Events",
    subtitle="Eddies, fronts and upwelling detected from real satellite fields - with a clear line "
             "drawn between what is detected and what is merely encouraging.",
    meta=[("Port", "8506"), ("Page file", "app/phase2/events_page.py"),
          ("Modules", "phase2/events/{eddy, fronts, upwelling}.py"), ("Mode", "detection, not tracking")],
    lead="The ocean is not a smooth field. It is full of spinning eddies, sharp fronts and rising "
         "cold water, and these features are where fisheries concentrate, where cyclones gain or "
         "lose energy, and where the model is least certain. This page finds them.",
    plain=[
        "An <b>eddy</b> is a rotating body of water, often a hundred kilometres or more across, that "
        "can persist for months and carries its own heat and nutrients with it. Detection uses the "
        "Okubo-Weiss criterion, a standard method that separates regions dominated by rotation from "
        "regions dominated by stretching.",
        "A <b>front</b> is a sharp horizontal temperature boundary - the ocean's equivalent of a "
        "weather front. Fish gather along them, and so do fishing fleets.",
        "<b>Upwelling</b> is cold, nutrient-rich water rising from below, usually driven by wind "
        "pushing surface water away from a coast. It is the engine of some of the world's most "
        "productive fisheries, including along the Somali and Indian coasts.",
        "Everything on this page is computed from genuine surface observations: satellite currents "
        "and satellite sea-surface temperature. You can switch to the reanalysis of the same days to "
        "see how closely the two agree.",
    ],
    analogy="Weather radar for the sea surface. It does not tell you the temperature everywhere - it "
            "tells you where something is happening.",
    screen_intro="Three detectors, one date, one source toggle:",
    screen=[
        "An eddy map with each detected feature's centre, rotation sense and approximate diameter.",
        "A front map showing the strongest horizontal temperature gradients, with the detection "
        "threshold and the field's mean gradient both printed - so a flat field is visible as flat.",
        "An upwelling panel combining the surface signature with Ekman pumping from wind.",
        "A source toggle - <b>satellite</b> (genuine observations, the deliverable's own inputs) or "
        "<b>glorys</b> (the reanalysis of the same days).",
        "A clear on-screen statement that the upwelling panel's subsurface term uses reanalysis in "
        "both modes, and is therefore a signature rather than an attribution.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/events_page.py --server.port 8506",
    steps=[
        "Run the command and open <b>http://localhost:8506</b>.",
        "Choose a date in the southwest monsoon - August is ideal, because the Somali Current is at "
        "its most energetic.",
        "Keep the source on <b>satellite</b>. Point out that the eddies on screen are being found in "
        "real satellite currents, with no model reconstruction involved.",
        "Open the eddy panel and look at 7.5 N, 53 E. A large anticyclone holds station there.",
        "Switch the source to <b>glorys</b> and let the audience compare. Agreement between an "
        "independent observation product and a reanalysis is itself evidence.",
        "Move to the fronts panel and read the printed threshold and mean gradient aloud - that pair "
        "is what stops a percentile detector from always claiming to have found something.",
    ],
    why=[
        "The problem statement asks for a daily, eddy-resolving reconstruction that is useful over "
        "the Bay of Bengal and the Arabian Sea. Detecting the features themselves proves the daily "
        "product is being used for what daily data is uniquely good for - a monthly average erases "
        "every one of these.",
        "It also gives the project a physical cross-check that does not depend on Argo. If the "
        "detectors find the basin's known circulation features in the right places at the right "
        "season, the underlying fields are behaving.",
    ],
    ps_rows=[
        ["Daily temporal resolution", "Only daily data can resolve features that move a few "
         "kilometres per day; this page is where that pays off."],
        ["Satellite-observation inputs", "Eddies and fronts are computed from GLOBCURRENT currents "
         "and OSTIA SST - genuine observations."],
        ["Proof of concept over BoB and Arabian Sea", "Both basins are covered, and their event "
         "regimes are visibly different."],
    ],
    numbers_intro="What was found, with each claim carrying its own evidence tag - this feature is "
                  "where the project is most careful about the difference:",
    numbers_table=dict(
        rows=[
            ["Finding", "Evidence tag", "What that means"],
            ["A ~243 km anticyclone holds station at 7.5 N, 53 E in August",
             "<b>[VERIFIED]</b>", "It is genuinely in the data and was measured here."],
            ["That eddy is the Great Whirl",
             "<b>[INFERRED]</b>", "It matches the standard description, but no paper was re-read on "
             "this machine, so we do not assert it as fact."],
            ["July's strongest gradient is 11.4 degC per 100 km at 11.4 N, 51.5 E",
             "<b>[VERIFIED]</b>, and it sits in the Somali upwelling front region",
             "Encouraging - and explicitly <b>not</b> evidence, because no front climatology was "
             "checked."],
            ["Upwelling is attributed to wind", "<b>Not claimed</b> - the flag literally reads "
             "wind_attributed: False", "The wind-stress product covers 2019-2022 and cannot reach "
             "our 2025-26 window."],
        ],
        widths=[0.36, 0.24, 0.40], font_size=8.0,
    ),
    numbers=[
        "The fronts detector uses a percentile threshold, which by construction <b>always</b> returns "
        "the sharpest gradients present and can therefore never report 'no fronts'. Because that is "
        "a real weakness, the detector also returns the threshold and the mean gradient, so a flat "
        "field is visible as one.",
    ],
    impact_rows=[
        ["Fishing communities", "Fronts and upwelling zones are where fish aggregate. Daily maps of "
         "them have direct, immediate livelihood value."],
        ["Cyclone forecasters", "A warm-core eddy under a storm track is a known intensification "
         "hazard; a cold eddy is the opposite."],
        ["Navy and marine operations", "Eddies bend sound and shift currents, affecting both "
         "acoustics and routing."],
        ["Ocean researchers", "A daily, basin-wide, satellite-driven event census over a region "
         "where such products are scarce."],
    ],
    society="Small-scale fishers in India, Sri Lanka and the Gulf spend fuel searching for fish. Daily "
            "front and upwelling maps reduce that search, which cuts cost and risk for people going "
            "to sea in small boats. That is a direct, tangible benefit from a satellite product.",
    pitch="This finds the things that move - eddies, fronts, upwelling - from real satellite "
          "currents and real satellite temperature, daily. In August we find a 243-kilometre "
          "anticyclone holding station at 7.5 north, 53 east, exactly where the Somali Current's "
          "great eddy is described. Notice how we phrase that: the eddy is VERIFIED in the data, but "
          "calling it the Great Whirl is tagged INFERRED, because we have not re-read the paper on "
          "this machine. We tag every claim that way.",
    qa=[
        ("Can you track an eddy over time, not just detect it?",
         "Not yet, and we are precise about why. Until recently our data was monthly and tracking "
         "was genuinely impossible, because an eddy moves a few kilometres per day and consecutive "
         "months cannot be assumed to show the same feature. We now have 388 consecutive days, so "
         "tracking is <b>unbuilt rather than impossible</b>. We changed the wording when the data "
         "changed, rather than letting an old justification stand."),
        ("Are your fronts validated?",
         "No, and we say so. The detector runs and its strongest July gradient lands in a region "
         "where a front is expected, but no front climatology or published census was checked. That "
         "is encouraging, and it is not evidence."),
        ("Does upwelling detection prove the wind caused it?",
         "No. The wind-stress product we hold runs 2019 to 2022 and cannot reach our 2025-26 window, "
         "so the panel produces a signature and the attribution flag is literally set to false on "
         "screen."),
    ],
    limit=("Detection only, and one detector cannot fail", "Nothing on this page joins one date to "
           "the next, so there is no eddy tracking and no marine-heatwave product - both are "
           "unbuilt, not impossible. And the front detector's percentile threshold means it can "
           "never return an empty result, which is exactly why the threshold and the mean gradient "
           "are printed beside every map."),
))

# ------------------------------------------------------------------ recaps
_RECAPS = {
    1: ("The first complete surface-to-subsurface system, scored on independent floats and then "
        "sealed read-only so the improvement that followed is measurable rather than asserted.",
        [("0.9638 degC", "RMSE vs 879 independent floats"),
         ("+0.387", "skill over climatology"),
         ("FROZEN", "read-only by project rule")]),
    2: ("One point of ocean, every source's answer, and the measured distance in kilometres and days "
        "behind each of those answers.",
        [("10.8 km", "median float-to-grid distance"),
         ("7 days", "median float-to-date offset"),
         ("4 flags", "HIGH / MEDIUM / LOW / REJECT")]),
    3: ("The page that measures our training target's own error first, so the deliverable's error "
        "can be attributed instead of merely reported.",
        [("0.178 degC", "of the thermocline error that is ours, not the target's"),
         ("+0.23 to +0.38", "degC that are genuinely ours, in the mixed layer"),
         ("14 of 15", "depths where we beat climatology")]),
    4: ("The whole reconstruction as one rotatable body of water, where every hole is the sea floor "
        "and the classification adds up to the grid exactly.",
        [("24,000", "cells classified, exactly, at every depth"),
         ("11,832", "ocean cells, consistent across two depths"),
         ("~24%", "of ocean cells never reach 1000 m")]),
    5: ("Turns fifteen temperatures into the four structures forecasters use - and refuses two of "
        "them on satellite input rather than borrowing reanalysis salinity.",
        [("100.6%", "of the observed thermocline gradient reproduced"),
         ("2 fields", "refused rather than approximated"),
         ("-0.024 GJ/m2", "heat-content bias: the field that survives")]),
    6: ("Finds the moving features - eddies, fronts, upwelling - in genuine satellite fields, with "
        "every claim carrying its own evidence tag.",
        [("243 km", "anticyclone at 7.5 N, 53 E [VERIFIED]"),
         ("11.4 degC", "per 100 km, July's strongest front"),
         ("388 days", "of consecutive daily fields available")]),
}
for _s in SPECS:
    _s["recap"], _s["tiles"] = _RECAPS[_s["n"]]
