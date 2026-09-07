"""Feature notes 7-12. Every figure is transcribed from PROJECT_RECORD.md, docs/ or a commit."""
from __future__ import annotations

SPECS = []

# ------------------------------------------------------------------ 7
SPECS.append(dict(
    n=7, short="TS-Cast v2", kicker="THE DELIVERABLE ITSELF",
    title="TS-Cast-NIO v2",
    subtitle="The shipped model: a 3-D satellite encoder compressing eleven days into 128 numbers, "
             "and a compact head turning those into fifteen depths with an uncertainty on each.",
    meta=[("Port", "8507"), ("Page file", "app/phase2/tscast_page.py"),
          ("Model", "548,582 parameters"), ("Input", "7 satellite channels, 11 days")],
    lead="This is the feature the problem statement actually asked for, and everything else in this "
         "pack either feeds it, checks it or uses its output. It reconstructs fifteen depths of "
         "temperature across the entire North Indian Ocean, every day, from satellite observations "
         "alone.",
    plain=[
        "The model sees a stack of seven satellite pictures - sea-surface temperature, salinity, "
        "height, two current components and two wind components - for eleven consecutive days around "
        "the date you ask about. A 3-D convolutional encoder compresses that stack into 128 numbers: "
        "a compact description of what the surface is doing there.",
        "Those 128 numbers are the <b>compact satellite embedding</b> the problem statement asks "
        "for, and they are the whole of what the network knows about that place and day. A small "
        "head then turns them into fifteen temperatures and fifteen uncertainties. Nothing else "
        "enters: no climatology, no reanalysis, no in-situ float.",
        "<b>That last point is a measured departure from the paper we re-implemented, and it is "
        "worth stating plainly.</b> TS-Cast's design feeds the monthly climatology into the decoder "
        "so the network only has to learn a correction to a physically sensible average. We built "
        "that decoder, scored it, and it was <b>worse</b> at our data scale - so it is not shipped, "
        "and the shipped network predicts the profile directly from the satellite latent. Verified "
        "by running the model with the climatology set to zero and to noise and getting "
        "bit-identical output.",
        "Alongside every temperature it emits a second number: how uncertain it is at that depth. "
        "That is why Feature 13 exists at all - the uncertainty is produced by the model itself, not "
        "bolted on afterwards.",
        "It is a re-implementation from the published description of TS-Cast (Chae, Donohue and "
        "Park, <i>Ocean Science</i> 22, 2026). Their code was never released; nothing is copied. And "
        "we depart from the paper in several places - each departure measured, not assumed.",
    ],
    analogy="Squeeze eleven days of satellite imagery over a patch of sea into 128 numbers - about "
            "the size of a short sentence - and that sentence has to contain everything needed to "
            "describe the kilometre of water underneath. The encoder writes the sentence; the head "
            "reads it back out as a temperature profile.",
    screen_intro="The model's own dashboard, with the ground-truth check beside every number:",
    screen=[
        "Reconstructed temperature at any depth across the basin, for any date in the bundle.",
        "The per-depth error table: RMSE, correlation and bias against 962 independent Argo profiles.",
        "The skill-against-climatology chart, with <b>both</b> skill definitions always shown and "
        "always labelled, because they read very differently and mixing them would be misleading.",
        "The provenance block - which checkpoint, which data bundle, which commit, and the "
        "checkpoint's own cryptographic hash.",
        "An explicit <b>input_source</b> field that reads <b>satellite</b>, which is the field the "
        "freeze script asserts before it will accept the model as the deliverable.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/tscast_page.py --server.port 8507",
    steps=[
        "Run the command and open <b>http://localhost:8507</b>.",
        "Read the provenance block first, out loud. It names the exact checkpoint and says "
        "<b>input_source: satellite</b>. This is the moment you prove the deliverable is what it "
        "claims to be.",
        "Pick a date and a depth, and let the basin render.",
        "Open the per-depth error table and walk down it. Point at 100 m - the hardest depth - and "
        "at 200 m, where the model gains most over climatology.",
        "Show the skill chart with both definitions side by side and explain why you never quote one "
        "beside the other.",
        "To prove the model file has not drifted, run the freeze check in a second terminal.",
    ],
    extra_commands=[
        ("VERIFY THE SHIPPED MODEL - 18 CHECKS",
         "PYTHONPATH=src python scripts/phase2/freeze.py --check"),
        ("RE-SCORE THE CHECKPOINT FROM DISK, TRUSTING NO SIBLING FILE",
         "PYTHONPATH=src python scripts/phase2/rescore_checkpoint.py --checkpoint "
         "artifacts/tscast_stage1.pt"),
        ("RETRAIN IT - the --daily-dir flag is NOT optional",
         ["PYTHONPATH=src python -m phase2.tscast_nio.train.train_stage1 \\",
          "  --daily-dir data/processed/daily_sat/v001 --t-seq 11 --epochs 25 \\",
          "  --train-samples 60000 --test-samples 12000 --patience 5 \\",
          "  --encoder cnn3d --decoder simple --tag sat_7ch_s42"]),
    ],
    run_note=("Why --daily-dir is not optional", "Omitting it silently trains on the reanalysis "
              "instead of on satellite data, which would produce a better-looking number that does "
              "not satisfy the problem statement. The flag is required, and the freeze script "
              "asserts input_source == satellite on the shipped artifact so this cannot regress "
              "unnoticed.", "warn"),
    why=[
        "It is the requirement. The problem statement asks for a compact satellite embedding "
        "produced by deep learning, feeding a reconstruction to fifteen standard depths at 0.25 "
        "degrees, daily, over the North Indian Ocean, evaluated by RMSE, correlation and bias "
        "against independent observations. This feature is all of that in one artifact.",
        "There is also a decision here that a jury should hear explicitly, because it is where "
        "scientific integrity cost us accuracy. Our <b>most accurate</b> configuration scores 0.8548 "
        "degC - but it is fed reanalysis inputs, and the problem statement asks for satellite "
        "observations. We do not ship it and we do not quote it as our result. The shipped model "
        "scores 0.9006 degC on genuine satellite input. Against the reanalysis-fed stage-1 "
        "comparator, real observations read +0.026, +0.027 and -0.003 degC on seeds 42, 43 and 44 "
        "- a mean of +0.017 degC whose <b>sign does not hold</b>, so by our own three-seed rule the "
        "cost is not an established effect: the two inputs are within seed noise of each other, "
        "and the satellite model retains about 94% of the comparator's skill.",
    ],
    ps_rows=[
        ["Compact satellite embedding via deep learning",
         "A 3-D CNN encoder producing a 128-dimensional latent, chosen over four competing "
         "architectures in a controlled bake-off."],
        ["Reconstruct surface -> full profile",
         "One forward pass returns all 15 depths for every grid cell."],
        ["0.25 degrees, daily, 5-30 N / 45-105 E",
         "100 x 240 grid, 388 consecutive daily steps, zero gaps."],
        ["RMSE, correlation and bias",
         "All three at all 15 of 15 depths against 962 independent Argo profiles."],
        ["Training target: GLORYS reanalysis",
         "GLORYS12V1 daily, with the target's own error separately measured in Feature 3."],
    ],
    numbers_intro="The shipped result, on 962 independent Argo profiles never used in training, "
                  "12,736 depth comparisons [VERIFIED, scoring protocol seafloor_masked_v1]. The "
                  "962 are the profiles within 5 days of the test window; 908 fall strictly inside "
                  "it, and scoring those alone reads 0.8978 degC. The scorer declines the 93 "
                  "comparisons (0.7%) at depths where the training target has no water and the "
                  "product itself returns nothing, plus one profile on a land cell; scored WITH "
                  "them, as every artifact before 2026-09-07 was, the same checkpoint read 0.9078 "
                  "degC and skill +0.2595:",
    numbers_table=dict(
        rows=[
            ["Metric", "Value", "How to read it"],
            ["RMSE", "<b>0.9006 degC</b>", "The headline. Average error across all depths."],
            ["Correlation", "0.8809", "Mean of the 15 per-depth values."],
            ["Bias", "+0.1066 degC", "Positive means the model runs warm. See Feature 15."],
            ["Skill vs climatology", "+0.2400", "1 - RMSE/RMSE_clim, where RMSE_clim = 1.1850. "
             "<b>Where the cell has a REAL per-cell climatology (895 of 962 profiles) it is "
             "+0.1494</b>; the other 67 sit on a basin-mean fill, and beating a fill is not skill."],
            ["Murphy skill", "+0.4225", "1 - MSE/MSE_clim. <b>Never quote one beside the other.</b>"],
            ["Depths beaten climatology", "14 of 15", "At 1000 m climatology wins by 0.055 degC, and "
             "the chart says so."],
        ],
        widths=[0.29, 0.22, 0.49],
    ),
    numbers=[
        "<b>The error has a shape, and the shape is the story.</b> It is small at the surface (0.47 "
        "degC at 5 m), bulges through the thermocline (peak <b>1.22 degC at 100 m</b>, where a "
        "surface field constrains depth least), and collapses below 500 m (0.31 degC at 1000 m). The "
        "widest gain over climatology is <b>+0.53 degC at 5 m</b>.",
        "<b>Two measured disagreements with the paper we re-implemented, and one withdrawn.</b> "
        "Its density constraint costs accuracy (0.8593 against 0.8548 with it off), and its FiLM "
        "decoder was measured to cost accuracy, so it is built, tested and deliberately <b>not "
        "shipped</b> - the code refuses to run stage 2 on it with an explicit error message saying "
        "why. Both rest on <b>one seed each</b>, which by this project's own three-seed rule is "
        "suggestive rather than settled. <b>The input-window comparison is WITHDRAWN:</b> all three "
        "legs predate our leakage fix, the 31-day leg is on our own do-not-quote list, and the two "
        "shorter legs' checkpoints were overwritten. We ship an 11-day window and cannot presently "
        "prove it is the best one.",
        "<b>The model is deliberately small.</b> At the paper's widths it would be 7,118,474 "
        "parameters - 13.1x the capacity for our 100,000 samples - and it overfits by epoch 3 "
        "regardless of the loss function. We ship 548,582 parameters.",
    ],
    impact_rows=[
        ["INCOIS / MoES", "Daily basin-wide subsurface temperature from satellites already in "
         "operational use - no new instrument, no new deployment."],
        ["Cyclone forecasting", "The subsurface heat field that drives intensification, available "
         "the same day rather than after a float surfaces."],
        ["Fisheries and shipping", "Thermocline and layer structure everywhere, every day, instead "
         "of only where a float happens to be."],
        ["Ocean research", "A reproducible, frozen, independently-validated reconstruction over a "
         "basin where such products are scarce."],
    ],
    society="Argo floats measure this basin roughly every five to ten days, and only where a float "
            "happens to be. This produces the same quantity at 24,000 locations every single day "
            "from satellites that already exist. For a coastline where tens of millions of people "
            "live inside a cyclone's reach, the difference between 'somewhere, sometimes' and "
            "'everywhere, daily' is the entire point of the project.",
    pitch="This is the deliverable. Seven satellite channels over eleven days go in; fifteen depths "
          "of temperature across the whole basin come out, with an uncertainty on every one. Against "
          "962 Argo floats it never saw, it scores 0.9006 degC and beats climatology at fourteen of "
          "fifteen depths. And I want to be explicit about one choice: our most accurate model "
          "scores 0.8548, but it is fed reanalysis, and the problem statement asks for satellite "
          "observations. We do not ship it and we do not quote it. Across three seeds, real "
          "observations read between -0.003 and +0.027 degC against it - a mean of +0.017 whose sign "
          "does not hold, so we do not claim a cost either: the two are within seed noise.",
    pitch_note="The refusal to quote 0.8548 is the single most credible thing you can say.",
    qa=[
        ("Why is your headline number not your best number?",
         "Because our best number is fed reanalysis input and the problem statement asks for "
         "satellite observations. Quoting it would present a reanalysis-fed model as satisfying a "
         "satellite requirement. Our freeze script asserts input_source == satellite on the shipped "
         "artifact, so this cannot regress silently even if someone wanted it to."),
        ("The paper anchors its decoder on the climatology. Why does yours not?",
         "Because we measured it and it was worse at our data scale. We built the paper's "
         "climatology-prior decoder, scored it against Argo, and it cost accuracy - so we ship the "
         "head that was actually validated. It is one of three measured disagreements with that "
         "paper, and we can show the evidence for each. A useful side effect: because no "
         "climatology enters the shipped network, the sensitivity analysis in our observability "
         "work measures the satellite dependence and nothing else."),
        ("You re-implemented a 2026 paper. What is your own contribution?",
         "Three things, and we are careful not to overclaim. First, the region: the model, the "
         "climatology and the validation are all built for the North Indian Ocean. Second, the "
         "measured disagreements - the density constraint and the FiLM decoder both hurt at our "
         "data scale, on one seed each, and the input-window comparison is withdrawn because it "
         "predates our own leakage fix. Third, the system "
         "around it. We claim a system-level contribution, not a new reconstruction method, and our "
         "own novelty matrix says so in writing."),
        ("How do we know the checkpoint on screen is the one you scored?",
         "Run <font face='Consolas' size='8'>freeze.py --check</font>. It re-verifies eighteen "
         "properties of the shipped artifact rather than trusting the manifest, including the "
         "checkpoint's SHA-256 hash and the claim wording used for uncertainty."),
    ],
    limit=("Where it is weakest, in its own words", "It runs <b>warm</b> - bias +0.1003 degC "
           "overall, peaking at +0.657 degC at 50 m - but that average is <b>inherited</b>: the "
           "GLORYS target is +0.1078 degC warm against the same floats, and the model is -0.007 "
           "against its own target. What is ours is the shape, and at 50 m the model adds "
           "<b>+0.447 degC</b> on top of the target's +0.213. Its mixed layer (20-50 m) is genuinely "
           "worse than the reanalysis by <b>0.23 to 0.38 degC</b>. At the thermocline <b>most</b> of "
           "the error is inherited - the reanalysis itself scores 1.042 degC at 100 m against our "
           "1.218 - but <b>0.178 degC of it is ours</b>, not the 0.023 an earlier draft carried "
           "over from a Phase-1 measurement. And there is an Arabian Sea satellite penalty of "
           "+0.0341 degC whose sign holds across all three seeds and whose <b>cause is UNKNOWN after "
           "four tested hypotheses</b> - we report it as unexplained rather than offering a story."),
))

# ------------------------------------------------------------------ 8
SPECS.append(dict(
    n=8, short="Argo Overlay", kicker="THE MODEL, CHECKED IN FRONT OF YOU",
    title="Live Argo Overlay",
    subtitle="Pick a point, and watch the model's prediction land on top of a real float it has "
             "never seen.",
    meta=[("Port", "8508"), ("Page file", "app/phase2/validate_page.py"),
          ("Module", "phase2/validation/argo_overlay.py"), ("Network", "none - fully offline")],
    lead="Every accuracy number in this pack is an average over thousands of comparisons. This page "
         "does the opposite: it shows one comparison, in full, live, at a point the audience picks. "
         "It is the page built to answer the question a judge is going to ask anyway.",
    plain=[
        "An <b>Argo float</b> is a real instrument drifting in the ocean. Every few days it sinks to "
        "a kilometre, then rises while measuring temperature the whole way up, and transmits the "
        "profile by satellite. Those measurements are the ground truth in this field.",
        "This page takes a point you choose, runs the <b>same frozen model</b> the main dashboard "
        "uses - not a second copy, not a re-trained version - and draws its predicted profile with "
        "its uncertainty band. Then it drops a real, independent float profile on top and prints the "
        "error at every depth.",
        "The float is independent in the strict sense: it comes from the 962 profiles held out of "
        "training entirely. Nothing on this page has ever been shown to the model during learning.",
        "The matching is deliberately simple and deliberately explained. Candidates within one "
        "degree and five days are ranked by distance first, with time breaking ties. There is no "
        "clever weighted score, because there is no defensible exchange rate between kilometres and "
        "days, and inventing one would hide an assumption inside a number.",
    ],
    analogy="A weather model claiming 31 degrees is one thing. Holding a thermometer up beside it, "
            "in front of the room, is another. This page is the thermometer.",
    screen_intro="One point, one float, one honest comparison:",
    screen=[
        "The model's predicted profile down 15 depths, drawn with its calibrated plus-or-minus 2 "
        "sigma band.",
        "A real independent Argo float profile drawn on top of it.",
        "The per-depth error printed live, plus an RMSE and bias summary for that single comparison.",
        "The float's distance in kilometres and its time offset in days - so the audience can weigh "
        "how strong this particular check is.",
        "A top-k picker, so if several floats are nearby you can step through them rather than being "
        "shown only the most flattering one.",
        "A small map showing where the chosen point landed.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/validate_page.py --server.port 8508",
    steps=[
        "Run the command and open <b>http://localhost:8508</b>.",
        "Enter a latitude and longitude in the basin. Ask a judge to choose it - that is the whole "
        "point of this page, and it is safe because nothing here is cached per point.",
        "Pick a date inside the model's window (1 June 2025 to 23 June 2026).",
        "Read the float's distance and time offset before reading the error. A float 2 km and same "
        "day is a strong check; 60 km and four days is a weaker one, and the page tells you which "
        "you have.",
        "Step through the top-k floats to show you are not selecting the best one.",
        "Point at the plus-or-minus 2 sigma band and note where the float falls inside it and where "
        "it does not - Feature 13 explains why that band is honest rather than flattering.",
    ],
    run_note=("Why the point is typed, not clicked", "A click-handler that misfires on demo day is "
              "worse than a plain input box that always works. The whole page is offline too - no "
              "live float download - so it cannot fail on a conference-hall network.", "note"),
    why=[
        "The problem statement requires independent validation against float observations. An "
        "aggregate RMSE satisfies that requirement on paper; this page satisfies it in the room, "
        "where a reviewer can choose the test point themselves.",
        "It also closes the most common objection to any machine-learning result - that the model "
        "memorised its training data. A float the model has never seen, at a point the audience "
        "picked, is the cleanest available answer to that.",
    ],
    ps_rows=[
        ["Independent validation with Argo",
         "Uses the 962 held-out profiles directly, one at a time, with the match quality on screen."],
        ["Report bias and error honestly",
         "Per-depth error is printed live for the single comparison being shown - no aggregation to "
         "hide behind."],
        ["Reconstruct profile from surface",
         "Runs the shipped inference path itself, so the overlay cannot diverge from the deliverable."],
    ],
    numbers_intro="Design properties that make the check defensible [VERIFIED from the module and "
                  "its tests]:",
    numbers_table=dict(
        rows=[
            ["Property", "How it is guaranteed"],
            ["Same model as the dashboard", "The prediction call is a thin wrapper over the shipped "
             "predictor. <b>No second model-load path exists</b>, so the overlay cannot silently "
             "diverge."],
            ["Floats never used in training", "Matched against the held-out table of <b>962</b> "
             "independent profiles - the same set the headline number is scored on."],
            ["No hidden interpolation", "The float table is pre-binned to the project's 15 standard "
             "depths, so model and float already share one depth axis. A depth is scored only where "
             "<b>both</b> are finite; the comparison never extrapolates past the float's deepest "
             "level."],
            ["Deterministic ordering", "Ranked by (distance, then absolute time offset, then "
             "position and date), so the same query always returns the same float."],
            ["Cannot fail on the venue network", "Matching is fully offline - 13 tests, all offline, "
             "no bundle and no network required."],
        ],
        widths=[0.28, 0.72], font_size=8.3,
    ),
    impact_rows=[
        ["The jury", "The single most convincing live demonstration available - they choose the "
         "point, and the model is checked against reality on the spot."],
        ["INCOIS / MoES", "A routine spot-check tool. Any operator can verify the product against "
         "the nearest float before acting on it."],
        ["Ocean scientists", "Per-depth residuals at a chosen location, which is how model error is "
         "actually diagnosed in practice."],
        ["The team", "A regression alarm: if a checkpoint change breaks something, it shows up here "
         "as a visible mismatch rather than a shifted average."],
    ],
    society="Trust in a public forecast product is built by letting people check it. A page where "
            "anybody can pick a point and see the prediction measured against a real instrument is "
            "the difference between asking the public to believe a system and letting them test it.",
    pitch="Please choose a point anywhere in the basin. This runs the same frozen model you have "
          "already seen, draws its profile with its uncertainty band, and drops a real Argo float on "
          "top - one of the 962 profiles the model has never seen. The per-depth error appears live. "
          "And notice we show the float's distance and time offset, because a float 2 km away and on "
          "the same day is a much stronger check than one 60 km away and four days later. We show "
          "you which one you are getting.",
    pitch_note="Hand this one to the jury. Let them pick the coordinates.",
    qa=[
        ("Is this the same model, or a special demo version?",
         "The same one. The prediction call is a thin wrapper over the shipped predictor, and there "
         "is deliberately no second model-loading path in the codebase - so this page structurally "
         "cannot show you a different model from the dashboard."),
        ("Could you be picking the float that makes you look best?",
         "The ranking is by distance first and time second, fully deterministic, and there is a "
         "top-k picker so you can step through every nearby float yourself. You are welcome to pick "
         "the worst one."),
        ("What if the float falls outside your uncertainty band?",
         "It sometimes does, and that is expected and published. Our plus-or-minus 2 sigma band "
         "covers 91.2% of held-out observations against a nominal 95.4%, so we are mildly "
         "overconfident and we report the coverage as a range by depth rather than as a flattering "
         "average. Feature 13 covers that in full."),
    ],
    limit=("One float is one float", "A single overlay is a demonstration, not a statistic. The "
           "defensible accuracy claim is the aggregate over 962 profiles and 12,736 depth "
           "comparisons in Feature 7; this page makes that aggregate tangible but cannot replace it. "
           "It is also limited to the held-out window and to points where a float was genuinely "
           "nearby - and where none was, it says so rather than showing an empty comparison."),
))

# ------------------------------------------------------------------ 9
SPECS.append(dict(
    n=9, short="Cyclone Heat", kicker="THE FUEL A CYCLONE BURNS",
    title="Cyclone Heat Potential",
    subtitle="Daily TCHP, D26 and ocean heat content over the Bay of Bengal and Arabian Sea, from "
             "satellites alone.",
    meta=[("Port", "8509"), ("Page file", "app/phase2/cyclone_heat_page.py"),
          ("Module", "phase2/derived/heat_content.py"), ("Units", "kJ/cm2, metres, GJ/m2")],
    lead="This is the feature that makes the project nationally relevant rather than merely "
         "accurate. Sea-surface temperature alone does not tell you whether a cyclone will "
         "intensify; the depth of the warm water underneath it does. That quantity is what this "
         "page produces, every day, without a single in-situ float.",
    plain=[
        "A cyclone does not just take heat from the surface. Its own winds churn the sea, dragging "
        "up cooler water from below. If the warm layer is thin, the storm quickly pulls up cold "
        "water and cools its own fuel supply. If the warm layer is deep, the churning brings up more "
        "warm water and the storm keeps intensifying.",
        "<b>Tropical Cyclone Heat Potential</b> (TCHP) measures exactly that: the heat stored above "
        "the 26 degrees Celsius isotherm - 26 being the accepted threshold below which tropical "
        "cyclones do not sustain themselves. <b>D26</b> is the depth of that isotherm, meaning how "
        "thick the warm layer is. <b>Ocean heat content</b> is the total heat down to a chosen depth.",
        "Until now, producing TCHP over this basin needed subsurface observations - floats, or a "
        "reanalysis that runs days behind. We produce it daily, from satellite inputs, everywhere in "
        "the basin, because the model underneath supplies the full temperature column.",
        "Every value also carries an uncertainty, propagated through the integral by sampling. And "
        "the page states, on screen, that this uncertainty is a <b>lower bound</b> - the model "
        "provides per-depth variance with no cross-depth correlation, and adjacent depths are "
        "physically likely to be correlated, so the true spread is wider than the number shown.",
    ],
    analogy="Surface temperature tells you the fuel tank is warm. TCHP tells you how deep the tank "
            "is. A storm crossing a thin warm layer runs out of fuel; one crossing a deep warm layer "
            "does not - and that is often the difference between a storm and a disaster.",
    screen_intro="Three related products, one date, one basin:",
    screen=[
        "A daily <b>TCHP</b> map in kJ/cm2 across the Bay of Bengal and the Arabian Sea.",
        "A <b>D26</b> map - the depth of the 26 degree isotherm, computed by linear interpolation "
        "between the last warm level and the first cold one.",
        "An <b>ocean heat content</b> map to a chosen reference depth.",
        "A point inspector giving all three values with a plus-or-minus 1 sigma range beside each.",
        "Land drawn as blank rather than as zero - because a zero would read as 'cold', which is a "
        "false claim about a place with no water at all.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/cyclone_heat_page.py --server.port 8509",
    steps=[
        "Run the command and open <b>http://localhost:8509</b>.",
        "Pick a date in the pre-monsoon or post-monsoon cyclone season - October and November are "
        "the Bay of Bengal's dangerous months.",
        "Show the TCHP map first. Point at the deep-warm-pool regions and say plainly: a storm "
        "crossing there will find fuel; one crossing the thin areas will not.",
        "Switch to D26 and explain that this is the thickness of that fuel layer in metres.",
        "Use the point inspector on a specific location and read the plus-or-minus 1 sigma range "
        "aloud, then say it is a lower bound and why.",
        "To produce the same fields as files for another system, use the export script below.",
    ],
    extra_commands=[
        ("WRITE THE FIELDS TO NETCDF FOR ONE DATE OR A RANGE",
         "PYTHONPATH=src python scripts/phase2/make_heat_content.py --date 2025-10-02"),
    ],
    why=[
        "The problem statement sits under a disaster-management theme with INCOIS as the sponsor. "
        "TCHP is the single most directly operational quantity this project can produce: it is what "
        "cyclone-intensity forecasters actually consume, and India's cyclone exposure is among the "
        "highest in the world.",
        "It also demonstrates that a temperature-only model is genuinely useful. TCHP needs no "
        "salinity, so it lies entirely inside our compliance boundary - it is a satellite-derived "
        "product with no reanalysis smuggled in, which is exactly why Feature 5 refuses the fields "
        "that would need salinity while this one proceeds.",
    ],
    ps_rows=[
        ["Daily, basin-wide output", "TCHP, D26 and OHC for every ocean cell, every day in the "
         "bundle."],
        ["Satellite inputs only", "Derived from the shipped temperature field, which needs no "
         "salinity - so nothing reanalysis-based enters the product."],
        ["Useful over the Bay of Bengal and Arabian Sea", "Both basins covered, and their seasonal "
         "heat structures are visibly different."],
        ["Uncertainty reported", "Model per-depth sigma propagated through the integral by sampling, "
         "labelled as a lower bound."],
    ],
    numbers_intro="Constants, conventions and guards - all chosen explicitly and tested [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Choice", "Value", "Why it is stated rather than assumed"],
            ["TCHP constants", "cp = 4000 J/(kg degC), rho = 1026 kg/m3",
             "The TCHP-literature convention (Leipper and Volgenau 1972). Our climate-budget module "
             "uses 3985 / 1025 - they differ by ~0.4% and are kept as each field's own convention, "
             "not silently unified."],
            ["Realistic range", "about 20-120 kJ/cm2 for a tropical column",
             "A test guards this range explicitly. A result near 1,000,000 would be a unit bug, and "
             "the unit conversion is a factor of 1e-7."],
            ["Surface colder than 26 degC", "TCHP = 0", "There is genuinely no warm layer. Zero is "
             "the correct answer here."],
            ["Land or an all-missing column", "<b>NaN, never 0</b>",
             "A zero would read as 'cold water'. An absence is not a value."],
            ["A warm layer below a cold one", "excluded",
             "The warm layer is the <b>surface-connected</b> one, so a deep re-warming is correctly "
             "left out rather than counted as fuel."],
        ],
        widths=[0.20, 0.24, 0.56], font_size=8.0,
    ),
    numbers=[
        "The whole-basin field and the single-point calculation call the <b>same</b> unit-tested "
        "function, and a test asserts field value equals scalar value at each cell. There is no "
        "second implementation of TCHP that could drift from the first.",
    ],
    impact_rows=[
        ["IMD / INCOIS cyclone forecasters", "The subsurface intensification variable, daily and "
         "basin-wide, without waiting for a float to surface."],
        ["Coastal district administrations", "Earlier and better-founded signals about whether an "
         "approaching system has fuel to intensify."],
        ["Disaster-response planners", "A physical basis for evacuation timing, which is the "
         "decision that saves the most lives."],
        ["Fishers and port operators", "Advance warning tied to the ocean's actual energy state "
         "rather than to surface temperature alone."],
    ],
    society="The Bay of Bengal produces a small share of the world's tropical cyclones and a very "
            "large share of its cyclone deaths, because the storms meet a low-lying, densely "
            "populated coast. Any improvement in intensification forecasting converts directly into "
            "evacuation lead time. This feature is the project's clearest line from a satellite "
            "pixel to a life saved.",
    pitch="Surface temperature does not tell you whether a cyclone will intensify - the depth of the "
          "warm water underneath does, because the storm's own winds drag up whatever is below. That "
          "quantity is Tropical Cyclone Heat Potential, and producing it has always required "
          "subsurface observations. We produce it daily, everywhere in the basin, from satellites "
          "alone. And every value carries an uncertainty which we label a lower bound, because our "
          "model gives per-depth variance without cross-depth correlation and we will not present "
          "that as if it were the full story.",
    pitch_note="This is the feature to lead with if the jury asks 'why does this matter to India'.",
    qa=[
        ("Is TCHP not already available operationally?",
         "It is, from products built on floats and reanalysis, which are sparse in space or lag in "
         "time. Our contribution is producing it from satellite inputs, daily, at every one of "
         "24,000 grid cells in this basin - and being explicit that our temperature error propagates "
         "into it."),
        ("Why is your uncertainty a lower bound rather than the real one?",
         "Because the model emits a variance per depth with no covariance between depths, so our "
         "sampling draws each depth independently. Real errors at adjacent depths are almost "
         "certainly correlated, which would widen the spread. We state that on screen rather than "
         "presenting the narrower number as complete."),
        ("What happens over land or on the shelf?",
         "Land returns NaN, never zero, because zero would read as cold water. A column that does "
         "not reach the reference depth returns NaN rather than a partial integral labelled as a "
         "full one - that exact failure occurred once in Phase 1 and was fixed."),
    ],
    limit=("Its accuracy is inherited from the temperature field", "TCHP is an integral of our "
           "reconstructed temperature, so it carries our temperature error - including the +0.1003 "
           "degC warm bias, which will tend to overstate heat content slightly. Integrals are far "
           "more tolerant of bias than threshold crossings are, which is why the equivalent "
           "stage-2 heat content survived validation (bias -0.024 GJ/m2) while the mixed-layer depth "
           "from the same model did not. The uncertainty shown is a measured lower bound, not the "
           "true uncertainty."),
))

# ------------------------------------------------------------------ 10
SPECS.append(dict(
    n=10, short="Transect", kicker="A VERTICAL SLICE THROUGH THE SEA",
    title="Transect / Cross-section",
    subtitle="Draw a line across the basin and see the water beneath it - depth against distance, "
             "with contours and real floats on top.",
    meta=[("Port", "8510"), ("Page file", "app/phase2/transect_page.py"),
          ("Module", "phase2/derived/transect.py"), ("Sampling", "bilinear, gaps preserved")],
    lead="This is how an oceanographer actually reads structure. A tilting thermocline, an eddy's "
         "subsurface core, a coastal upwelling gradient - all of them are obvious in a vertical "
         "slice and nearly invisible in a map or a single profile.",
    plain=[
        "You give it two points. It cuts a vertical wall through the ocean between them and colours "
        "it by temperature: distance along the bottom, depth down the side. Everything the model "
        "knows along that line appears at once.",
        "Two honesty rules are enforced in the mathematics rather than in a caption. First, the "
        "slice is sampled by <b>bilinear interpolation</b>, because the point predictor snaps to the "
        "nearest grid centre and sampling it directly would draw a staircase that looks like real "
        "structure. Second, land and the sea floor are <b>gaps</b>, never values smoothed across - "
        "an interpolated cell touching a missing corner is itself missing. So a blank in the section "
        "is the coast or the bottom, never a hole in the model output.",
        "The upgraded version puts the model and the reanalysis side by side, scatters real "
        "independent floats on top coloured by the model's error against them, and lets you slide "
        "the whole track east or west to watch a front move.",
    ],
    analogy="A map is a photograph of the sea's skin. A transect is the cut through a layer cake - "
            "and the layers are the entire point.",
    screen_intro="One line, several ways of checking it:",
    screen=[
        "The model's temperature section - distance along the track against depth.",
        "The GLORYS reanalysis section beside it, on the same colour scale.",
        "Real independent Argo floats scattered on the section, coloured by model-minus-float error, "
        "each carrying its distance in kilometres and its time offset in days into the tooltip.",
        "<b>Isopycnal</b> (constant density) and <b>sound-speed</b> contours, where the chosen source "
        "carries salinity.",
        "A sliding control that sweeps the same track sideways, preserving its length exactly.",
        "A date picker over the model's real calendar - not a free-text box.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/transect_page.py --server.port 8510",
    steps=[
        "Run the command and open <b>http://localhost:8510</b>.",
        "Enter two endpoints. A good demonstration track runs 8 N, 68 E to 20 N, 88 E - it crosses "
        "the Arabian Sea, the tip of India and into the Bay of Bengal.",
        "Pick a date from the calendar picker.",
        "Read the model section, then reveal the GLORYS section beside it. State clearly that GLORYS "
        "is the training target, so agreement there is agreement with what we were fitted to - not "
        "independent proof.",
        "Turn on the Argo scatter. <b>These</b> are the independent checks, and each one shows how "
        "far away it was.",
        "Use the slider to sweep the track and let the audience watch the structure move. Point out "
        "that the track length never changes as it slides.",
    ],
    run_note=("Three real bugs this page fixed, worth mentioning", "Its cache key was never actually "
              "passed, so the page would not refresh when the model changed - the exact mechanism "
              "behind an 8 degC dashboard error earlier in the project. Its date box accepted "
              "1850-01-01 and silently returned a plausible section. And its legend <i>understated</i> "
              "the model's uncertainty by saying the band was uncalibrated when it was calibrated - "
              "the only honesty bug in this project that claimed less rather than more.", "warn"),
    why=[
        "The problem statement asks for a depth-resolved product. A transect is the standard "
        "scientific way to present one, and it is the view an oceanographer on a review panel will "
        "look for first.",
        "It is also where model and reanalysis can be compared like for like, with independent "
        "floats scattered on top as the tie-breaker - three sources on one picture, each labelled "
        "for what it is.",
    ],
    ps_rows=[
        ["Depth-resolved reconstruction",
         "Renders the full 0-1000 m column continuously along any track the user draws."],
        ["Independent validation",
         "Floats are overlaid with their real distance and time offsets, so a weak check cannot pass "
         "as a strong one."],
        ["0.25 degree resolution",
         "Bilinear sampling of the frozen grid, with land and sea floor preserved as gaps."],
    ],
    numbers_intro="Measured on the default track [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Comparison", "Result", "How to read it"],
            ["Model against GLORYS along the section",
             "bias +0.011 degC, RMSE 0.560 degC over 747 section points",
             "GLORYS is the <b>training target</b>, so this is agreement with what we were fitted to. "
             "The caption says so, which stops the smaller number standing as the better one."],
            ["Model against 3 independent Argo floats",
             "pooled RMSE 0.795 degC, float offsets 2-60 km",
             "<b>This</b> is the independent check - and the 60 km float is a weaker one than the 2 "
             "km float, which is why every offset is shown."],
            ["Isopycnal contour resolution", "24 kg/m3 surface resolved at <b>26 of 60</b> points by "
             "the density contour, and <b>0 of 60</b> by the isotherm method",
             "The shared-foundation work paying for itself, now pinned by a test."],
        ],
        widths=[0.24, 0.34, 0.42], font_size=8.0,
    ),
    numbers=[
        "Asking the sampler for a quantity the field does not carry <b>raises an error</b> rather "
        "than returning an all-missing section, because an all-missing density overlay is "
        "indistinguishable from 'there are no isopycnals here'.",
        "The sliding control clips the <b>shift</b> rather than each endpoint independently. Clipping "
        "the endpoints separately lets one end stop at the boundary while the other keeps moving, so "
        "the track silently shortens - a control that promises to hold a line's shape and quietly "
        "deforms it. The span is now preserved by construction.",
    ],
    impact_rows=[
        ["Ocean scientists", "The standard diagnostic view, on a daily satellite-driven product - "
         "including features a monthly average would erase entirely."],
        ["Naval and acoustic planners", "Sound-speed structure along a chosen route, which is "
         "exactly how an acoustic path is assessed."],
        ["The jury", "Three sources on one picture, each labelled for what it is, with the weakest "
         "check shown rather than hidden."],
        ["Educators", "The clearest teaching image for ocean layering, built from real "
         "reconstruction rather than a textbook schematic."],
    ],
    society="Structure, not average temperature, is what determines where fish gather, how far sound "
            "travels and how a storm draws energy. A tool that renders that structure daily along "
            "any line, from freely available satellite data, lowers the cost of asking those "
            "questions from a research cruise to a browser tab.",
    pitch="Draw any line across the basin and this cuts a vertical wall through the ocean beneath "
          "it. The model is on the left, the reanalysis on the right, and real independent floats "
          "are scattered on top coloured by our error against them. Note what the captions say: "
          "against GLORYS we score 0.560 degC, but GLORYS is our training target, so that is "
          "agreement with what we were fitted to. Against the independent floats we score 0.795, and "
          "each float shows how far away it was - because a float 60 km off is a weaker check than "
          "one 2 km off, and hiding that would overstate our validation.",
    qa=[
        ("Why is your error against GLORYS smaller than against floats?",
         "Because GLORYS is what we were trained to reproduce. Agreement with your own training "
         "target is not independent evidence, and the caption on the page says exactly that. The "
         "0.795 degC against real floats is the number that means something."),
        ("Are those blank areas model failures?",
         "No - they are land and the sea floor. Interpolation here is designed so that any cell "
         "touching a missing corner is itself missing, so a blank is always the coast or the bottom, "
         "never a gap in our output."),
        ("Why bilinear sampling instead of just reading the grid?",
         "Because the point predictor snaps to the nearest grid centre, and sampling it directly "
         "along a diagonal track would draw a staircase that a viewer would read as real structure. "
         "Bilinear sampling of the field is the honest rendering of what the model actually says."),
    ],
    limit=("It inherits the grid's resolution", "At 0.25 degrees - roughly 25 km - sub-mesoscale "
           "structure simply cannot be resolved, and a smooth section should not be read as evidence "
           "that the ocean is smooth. The density and sound-speed contours also need salinity, so "
           "they are only available on sources that carry it, and the page names which source is "
           "active rather than blending them."),
))

# ------------------------------------------------------------------ 11
SPECS.append(dict(
    n=11, short="Export & API", kicker="GETTING THE DATA OUT",
    title="NetCDF Export & HTTP API",
    subtitle="The feature that turns a demo into infrastructure - standard files and a live "
             "programmatic interface other systems can call.",
    meta=[("Port", "8511"), ("Service", "phase2.api.app (uvicorn)"),
          ("Formats", "NetCDF + JSON"), ("Routes", "4, with live docs")],
    lead="Before this existed there was no way to get a reconstruction out of the system at all - "
         "verified by searching the codebase and finding zero web framework, zero download button. "
         "A dashboard nobody can extract data from is a demonstration. This is what makes it a "
         "service.",
    plain=[
        "Two ways out. <b>NetCDF</b> is the standard scientific data format for gridded ocean and "
        "atmosphere fields - every serious ocean tool reads it, so exporting to NetCDF means our "
        "output drops straight into an existing workflow. <b>The HTTP API</b> lets another program "
        "ask for a profile or a whole field over the network, with automatically generated "
        "documentation any developer can read.",
        "Getting a file format right is mostly about getting absences right, and three decisions "
        "here are worth stating to a jury because each one prevents a specific false claim. Missing "
        "values are marked explicitly, because left to a reader's default a land cell becomes a "
        "<b>0 degrees measurement</b>. A temperature-only file <b>omits</b> the salinity variables "
        "entirely rather than writing a grid full of blanks, because a blank grid asserts 'this file "
        "has salinity, missing everywhere' - a different and false claim. And masks are stored as "
        "integer flags with their meanings attached, because NetCDF has no boolean type and a silent "
        "conversion to float is how a mask stops being a mask.",
        "Two implementation choices in the API are load-bearing rather than stylistic, and both are "
        "enforced by tests that parse the source code. The request handlers are deliberately "
        "synchronous, because an asynchronous handler calling the predictor would freeze the entire "
        "service for over thirty seconds. And every prediction runs inside a lock, because the "
        "predictor is shared and two simultaneous requests would otherwise return <b>plausible wrong "
        "answers</b> rather than raising an error.",
    ],
    analogy="A weather app that shows you a forecast is useful. A weather API that other apps can "
            "call is infrastructure. This is the step from one to the other.",
    screen_intro="Four routes, all verified live:",
    screen=[
        "<b>/health</b> - is the service up, and which checkpoint is it serving.",
        "<b>/coverage</b> - which dates the model can actually answer for.",
        "<b>/profile</b> - the 15-depth profile at a point and date, as JSON, in about 1.1 seconds.",
        "<b>/field.nc</b> - the whole basin for one date as a NetCDF file, 3.29 MB in about 34 "
        "seconds.",
        "<b>/docs</b> - interactive, automatically generated documentation for all four routes.",
        "Every response carries a ten-key provenance block, including the checkpoint's hash and the "
        "code commit - and a test asserts that contract holds rather than trusting it.",
    ],
    run_intro="Start the service, then call it. It binds to localhost only.",
    command="PYTHONPATH=src python -m uvicorn phase2.api.app:app --host 127.0.0.1 --port 8511 "
            "--workers 1",
    steps=[
        "Run the command above. The service starts on <b>http://127.0.0.1:8511</b>.",
        "Open <b>http://127.0.0.1:8511/docs</b> in a browser. All four routes render with a Try It "
        "button - this is the most impressive thirty seconds of this feature.",
        "Call <b>/coverage</b> first to see the valid date range.",
        "Call <b>/profile</b> with a latitude, longitude and date. Point out that the response body "
        "contains no null tokens and carries the checkpoint hash.",
        "Ask for a date <b>outside</b> the range on purpose. It returns a 422 error that names the "
        "valid range - it refuses rather than quietly snapping to the nearest date.",
        "Call <b>/field.nc</b> to download a real NetCDF file, then reopen it to show it carries "
        "input_source = satellite.",
    ],
    extra_commands=[
        ("EXPORT ONE DAY TO NETCDF WITHOUT THE SERVICE",
         "PYTHONPATH=src python scripts/phase2/export_field.py --date 2026-06-23 --out field.nc"),
    ],
    why=[
        "A national agency cannot consume a Streamlit page. It consumes files and endpoints. This "
        "feature is what makes the output usable by IMD, by a forecast model, by a downstream "
        "application, or by a researcher who wants to check our work in their own tools.",
        "It is also the feature that makes reproducibility real: every exported file carries the "
        "checkpoint hash and code commit that produced it, so a number quoted from one of our files "
        "can always be traced back to the exact model that generated it.",
    ],
    ps_rows=[
        ["Deliver a usable product",
         "Standard NetCDF plus a documented HTTP interface - both formats a sponsor can actually "
         "integrate."],
        ["Reproducibility and provenance",
         "Ten provenance keys on every response, asserted by a test rather than assumed."],
        ["Satellite-input compliance",
         "The exported file carries input_source = satellite and the checkpoint hash, so the claim "
         "travels with the data."],
    ],
    numbers_intro="Measured live, on this machine, rather than estimated [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Operation", "Measured cost", "Note"],
            ["/profile", "about 1.1 s, 15 depths", "No null tokens in the body."],
            ["/field.nc", "3.29 MB in 34.3 s", "Reopens as valid NetCDF carrying input_source = "
             "satellite and the checkpoint hash."],
            ["Whole-field prediction", "32.09 s median of 4 runs, 11,832 ocean cells, batch 512",
             "This replaced an estimate that said 'seconds on GPU, under a minute on CPU' - an "
             "estimate standing where a reader takes a cost figure."],
            ["Predictor load", "7.20 s, paid once", "Total warm 32.84 s, total cold 39.90 s."],
            ["Out-of-range date", "HTTP 422, <b>naming the valid range</b>",
             "It refuses rather than snapping to the nearest available date."],
        ],
        widths=[0.24, 0.30, 0.46], font_size=8.0,
    ),
    numbers=[
        "<b>The measurement found a real bug.</b> Timing the export revealed that a GPU was "
        "available and the inference path had never used it - the predictor loaded onto the CPU and "
        "was never moved. After the fix: <b>CPU 37.57 s against CUDA 8.86 s, a 4.24x speedup</b>, "
        "with a maximum difference of 6.9e-04 degC across 153,291 cells - float noise against a "
        "0.9006 degC headline.",
        "The export is deliberately kept on the CPU anyway, so that a downloaded file cannot differ "
        "in its last digits from the page displayed beside it.",
    ],
    impact_rows=[
        ["INCOIS / MoES", "A path from our output into their existing systems, in the format their "
         "tools already read."],
        ["Forecast modellers", "Programmatic access to subsurface fields as an input to their own "
         "models."],
        ["Independent reviewers", "The ability to download our actual output and check it in their "
         "own software rather than trusting our screenshots."],
        ["Downstream developers", "Self-documenting endpoints, so building on this needs no "
         "conversation with us."],
    ],
    society="Open, standard-format, provenance-carrying data is what lets research outside the "
            "original team happen at all. A state fisheries department, a university group or a "
            "startup can build on this without permission and without re-implementing anything - and "
            "can trace any number they publish back to the exact model that produced it.",
    pitch="Before this, there was no way to get data out of the system - we checked, and there was "
          "no web framework and no download button anywhere in the codebase. Now there is a NetCDF "
          "export and a documented HTTP API. Ask it for a date outside our range and it returns an "
          "error naming the valid range, rather than quietly giving you the nearest date - which "
          "would have been a wrong answer that looked right. And every file carries the checkpoint "
          "hash and the code commit that made it, so any number taken from our output can be traced "
          "back to the exact model that produced it.",
    qa=[
        ("Why is a whole-field export 34 seconds? That seems slow.",
         "It is 11,832 ocean cells, each with a full profile, and we measured it rather than "
         "estimating it. We also measured a 4.24x GPU speedup and deliberately did not switch the "
         "export to GPU, so that a downloaded file cannot differ in its last digits from the page "
         "beside it. That is a considered trade, and the measurement is on file."),
        ("What stops two simultaneous requests corrupting each other?",
         "A lock around every prediction. The predictor is shared process-wide, and without the lock "
         "two concurrent requests would return plausible wrong answers instead of raising - which is "
         "far more dangerous than a crash. A test using real threads checks this."),
        ("Why omit salinity from the file rather than write an empty grid?",
         "Because an all-blank salinity grid asserts that the file has salinity and it happens to be "
         "missing everywhere. That is a different and false claim. The stage-1 file omits those "
         "variables entirely, which correctly says the product does not contain them."),
    ],
    limit=("Localhost, single worker, and no authentication", "This is a demonstration service bound "
           "to 127.0.0.1 with one worker and no access control. Operational deployment would need "
           "authentication, rate limiting, horizontal scaling and a caching layer in front of the "
           "34-second field endpoint. None of that is built, and we would rather say so than imply "
           "the service is production-ready."),
))

# ------------------------------------------------------------------ 12
SPECS.append(dict(
    n=12, short="Click Map", kicker="TEST IT YOURSELF, ANYWHERE",
    title="Click Map",
    subtitle="Click any one of 24,000 cells in the basin and get the model's full profile "
             "underneath it.",
    meta=[("Port", "8512"), ("Page file", "app/phase2/clickmap_page.py"),
          ("Cells", "24,000, all clickable"), ("Depths", "15 per cell")],
    lead="This is the whole claim of the project reduced to one interaction. An Argo float answers "
         "'what is it like at 500 metres' only where a float happens to be, every five to ten days. "
         "This answers it everywhere, every day - and it is the only page where a viewer can test "
         "that themselves.",
    plain=[
        "A map of the basin at a chosen depth. Every cell is clickable. Click one and the model's "
        "full 15-depth profile for that exact cell appears beside it, with its uncertainty band.",
        "The profile is taken from the map's own array rather than re-running the model. That is "
        "deliberate: a second prediction call would cost another inference and, worse, would let the "
        "number in the side panel drift away from the colour under the cursor if the two paths ever "
        "disagreed. A test pins the field and point paths to be identical, precisely so this "
        "shortcut is sound.",
        "<b>There are three kinds of blank on this map and they are not the same thing.</b> A cell "
        "can be land; it can be ocean whose sea floor sits above the depth you asked for; or it can "
        "be outside the grid. Each says something different, and the page names which one you "
        "clicked instead of going silent.",
    ],
    analogy="Most ocean data is a scatter of pinpricks - wherever an instrument happened to be. This "
            "is the same information as a continuous surface you can probe anywhere, and it invites "
            "the audience to try to catch it out.",
    screen_intro="One map, one profile, and no place to hide:",
    screen=[
        "The full basin at a selected depth, drawn as 24,000 individually clickable cells.",
        "The clicked cell's complete profile - all 15 depths - with its calibrated plus-or-minus 2 "
        "sigma band.",
        "An explicit message when you click land: <i>that cell is land</i>, rather than a phantom "
        "profile.",
        "An explicit message when the sea floor is above your chosen depth.",
        "A GPU toggle, which is how a device bug that had existed since the parameter was written "
        "was finally discovered.",
    ],
    command="PYTHONPATH=src python -m streamlit run app/phase2/clickmap_page.py --server.port 8512",
    steps=[
        "Run the command and open <b>http://localhost:8512</b>.",
        "Choose a depth - 100 m is a good choice, because it is the hardest depth in the problem.",
        "Invite a judge to click anywhere in the water. The profile appears immediately.",
        "Now click on India, or on the Arabian peninsula. The page says <b>that cell is land</b>. "
        "Show this deliberately - it is the difference between a system that knows what it does not "
        "know and one that guesses.",
        "Click a shallow shelf cell with the depth set to 1000 m to see the sea-floor message.",
        "Compare the number in the side panel with the colour under the cursor, and explain that "
        "they come from the same array by construction.",
    ],
    run_note=("Four bugs that only rendering could find", "The cells first drew as a handful of "
              "enormous blocks; the basin drew at the wrong aspect ratio, so the Bay of Bengal was "
              "the wrong shape; the profile chart forced a zero baseline, squeezing a real 0.83 degC "
              "uncertainty band into 2% of the plot - an uncertainty band drawn so thin it reads as "
              "certainty; and land was silently dropped, so a click on India selected nothing while "
              "the panel still said 'click any cell'. <b>None of those was visible from a test. All "
              "four were found by opening the page.</b>", "warn"),
    why=[
        "The problem statement asks for a gridded, basin-wide reconstruction. This page is the "
        "direct demonstration that the output really is complete - not a handful of validated "
        "points, but every cell, every depth, ready to be interrogated at random.",
        "It is also the page that proves the system knows its own boundaries. A model that produces "
        "a confident-looking profile for a point in the Thar Desert has learned nothing useful; this "
        "one refuses.",
    ],
    ps_rows=[
        ["0.25 degree spatial resolution",
         "All 24,000 cells of the 100 x 240 grid are individually addressable."],
        ["15 standard depths",
         "Every clicked ocean cell returns all 15 levels, or names the reason it cannot."],
        ["Daily reconstruction",
         "Any date in the 388-day bundle, and the map redraws for it."],
    ],
    numbers_intro="Verified live in the browser on real data [VERIFIED]:",
    numbers_table=dict(
        rows=[
            ["Test", "Result"],
            ["Ocean cell at 17.50 N, 57.50 E",
             "15 of 15 levels returned - <b>28.27 degC at the surface falling to 9.11 degC at 1000 "
             "m</b>, with a plus-or-minus 2 sigma band of 0.83 to 3.63 degC, calibrated."],
            ["Land cell at 21.75 N, 47.50 E",
             "<b>'That cell is land'</b> - and no phantom profile."],
            ["Cell classification at 100 m",
             "9,763 water + 2,069 below sea floor + 12,168 land = <b>exactly 24,000</b>."],
            ["Cell classification at 1000 m",
             "8,973 water + 2,859 below sea floor + 12,168 land - land unchanged, water strictly "
             "fewer, as physics demands."],
            ["Cross-check against an independent count",
             "water + sea floor = <b>11,832</b> at both depths, matching the ocean-cell count "
             "recorded independently by the export timing measurement."],
        ],
        widths=[0.27, 0.73], font_size=8.2,
    ),
    numbers=[
        "The order of the two classification checks is load-bearing: asking 'is the value finite' "
        "before asking 'is it land' would label the entire coastline as being below the sea floor, "
        "which is a claim about bathymetry the data never made.",
    ],
    impact_rows=[
        ["The jury", "An open invitation to try to break the system, which is the strongest possible "
         "statement of confidence."],
        ["Operational users", "A point-query interface anyone can use without knowing anything about "
         "the model."],
        ["Fishers and mariners", "The most direct route from 'where am I' to 'what is the water "
         "under me doing'."],
        ["The team", "The page that found four rendering bugs no test could have caught, including "
         "one that made uncertainty look like certainty."],
    ],
    society="Subsurface ocean information has historically been available only to institutions with "
            "ships and floats. A map anybody can click, covering an entire basin every day, changes "
            "who is able to ask the question at all - which matters most for the small operators who "
            "were never going to have their own instruments.",
    pitch="Please click anywhere. That is the whole demonstration. An Argo float can tell you what "
          "500 metres looks like only where a float happens to be, every five to ten days - this "
          "answers it at all 24,000 cells, every day. Now click on land. It says 'that cell is "
          "land', because at 100 metres our classification is 9,763 water plus 2,069 sea floor plus "
          "12,168 land, which is exactly 24,000. Nothing is being quietly filled in.",
    pitch_note="Best used immediately after the accuracy numbers - it makes them tangible.",
    qa=[
        ("Is the profile in the panel really the same as the colour on the map?",
         "Yes, by construction - it is read from the same array rather than re-predicted, and a test "
         "pins the whole-field and single-point paths to be identical. A second prediction call "
         "would let the two drift apart, and we removed that possibility rather than monitoring it."),
        ("What happens if I click somewhere impossible?",
         "You get told which impossible thing it was. Land, sea floor above your chosen depth, or "
         "outside the grid - those are three different facts and the page names the right one. A "
         "bare blank would conflate them."),
        ("How do you know your land mask is right?",
         "It cross-checks three ways. The classification sums to exactly 24,000 at every depth; land "
         "stays constant as depth increases while water strictly decreases; and the ocean-cell total "
         "of 11,832 matches a count produced independently by a completely different part of the "
         "system."),
    ],
    limit=("It shows the model, not the truth", "Clicking a cell shows what the model says, not what "
           "the ocean is. The uncertainty band is the honest guide to how much to trust each value, "
           "and Feature 8 is where the same prediction is checked against a real float. Note also "
           "that the map draws one depth at a time - the vertical relationships between depths are "
           "better read in the transect (Feature 10) or the cube (Feature 4)."),
))

# ------------------------------------------------------------------ recaps
_RECAPS = {
    7: ("The deliverable: seven satellite channels over eleven days in, fifteen depths of "
        "temperature with uncertainty out, straight from a 128-number satellite embedding - and the "
        "more accurate reanalysis-fed model deliberately not shipped.",
        [("0.9006 degC", "RMSE vs 962 independent profiles"),
         ("+0.2400", "skill over climatology (+0.1494 where the baseline is real)"),
         ("548,582", "parameters - 13x smaller than the paper's")]),
    8: ("The audience picks the point; the model is measured against a real float it has never seen, "
        "with the strength of that check shown on screen.",
        [("962", "held-out profiles available"),
         ("2 to 60 km", "float offsets, always displayed"),
         ("0", "second model-load paths - it cannot diverge")]),
    9: ("The cyclone-intensification variable - heat above the 26 degree isotherm - produced daily "
        "from satellites alone, with its uncertainty labelled a lower bound.",
        [("26 degC", "the isotherm that defines the fuel layer"),
         ("20-120", "kJ/cm2, the guarded realistic range"),
         ("NaN", "over land - never a zero that reads as cold")]),
    10: ("A vertical wall cut through the ocean along any line, with the model, the reanalysis and "
         "independent floats on one picture and each labelled for what it is.",
         [("0.560 degC", "vs GLORYS - our training target"),
          ("0.795 degC", "vs independent floats - the real check"),
          ("26 of 60", "isopycnal points the density contour resolves")]),
    11: ("Standard NetCDF files and a documented HTTP service, each carrying the checkpoint hash "
         "that produced it - the step from demonstration to infrastructure.",
         [("3.29 MB", "a whole basin-day as NetCDF"),
          ("1.1 s", "a single profile over HTTP"),
          ("HTTP 422", "for a bad date - refuses rather than snaps")]),
    12: ("Every one of 24,000 cells is clickable, and the three kinds of blank are named rather than "
         "left silent.",
         [("24,000", "cells, and the classification sums to it exactly"),
          ("11,832", "ocean cells, cross-checked independently"),
          ("4 bugs", "found only by opening the page")]),
}
for _s in SPECS:
    _s["recap"], _s["tiles"] = _RECAPS[_s["n"]]
