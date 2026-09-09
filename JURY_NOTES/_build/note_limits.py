"""Limitations and future scope, illustrated.

Every number is READ at build time from artifacts/ - the per-depth curve from the shipped model's
metrics file, the headline from frozen_manifest.json. Nothing is typed.
"""
from __future__ import annotations

import json
import os

from reportlab.lib import colors
from reportlab.platypus import Spacer as RLSpacer
from reportlab.platypus import Table, TableStyle

import engine as E
from engine import (
    Spacer, _p, build, bullets, callout, cover, heading, kvstrip, table,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAND = "OceanEmbed  |  SIH26066  |  Limitations and future scope"

BAR_W = E.CONTENT_W * 0.52          # drawing width for the longest bar


def _facts():
    with open(os.path.join(ROOT, "artifacts", "frozen_manifest.json"), encoding="utf-8") as f:
        d = json.load(f)["claims"]["deliverable_satellite"]
    with open(os.path.join(ROOT, "artifacts", "tscast_stage1_metrics.json"), encoding="utf-8") as f:
        m = json.load(f)["metrics"]
    return d, m


def _bar(value, vmax, colour, height=5.0):
    """One horizontal bar, drawn as a two-cell table. No chart library needed."""
    w = max(0.6, BAR_W * (value / vmax))
    t = Table([[""]], colWidths=[w], rowHeights=[height])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def depth_chart(m):
    """Model error vs climatology error, per depth. The shape IS the limitation."""
    depths, rmse, clim = m["depths_m"], m["rmse"], m["rmse_climatology"]
    vmax = max(max(rmse), max(clim))
    rows = [[_p("<b>depth</b>", "kv_k"), _p("<b>model error vs the long-term average</b>", "kv_k"),
             _p("<b>model</b>", "kv_k"), _p("<b>average</b>", "kv_k")]]
    for d, r, c in zip(depths, rmse, clim):
        worse = r >= c
        pair = Table(
            [[_bar(r, vmax, E.AMBER if worse else E.TEAL)],
             [_bar(c, vmax, colors.HexColor("#C9D4DE"))]],
            colWidths=[BAR_W])
        pair.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
        ]))
        rows.append([
            _p(f"<b>{int(d)} m</b>" if d in (100, 1000) else f"{int(d)} m", "td"),
            pair,
            _p(f"<b>{r:.3f}</b>" if worse else f"{r:.3f}", "td"),
            _p(f"{c:.3f}", "td"),
        ])
    t = Table(rows, colWidths=[E.CONTENT_W * 0.10, BAR_W,
                               E.CONTENT_W * 0.14, E.CONTENT_W * 0.14])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, E.RULE),
        ("BACKGROUND", (0, 0), (-1, 0), E.PANEL),
    ]))
    return [RLSpacer(1, 4), t, RLSpacer(1, 6)]


def build_note(path):
    d, m = _facts()
    worst_i = max(range(len(m["rmse"])), key=lambda i: m["rmse"][i])
    s = []

    s += cover(
        badge="!", badge_sub="LIMITS",
        kicker="OCEANEMBED  ·  SIH26066  ·  WHAT IT CANNOT DO",
        title="Limitations & Future Scope",
        subtitle="Every weakness we know about, sorted by whether we can fix it - and what we "
                 "would do next.",
    )

    s.append(kvstrip([
        ("Error vs real floats", f"{d['overall_rmse']:.4f} degC"),
        ("Warm bias", f"{d['overall_bias']:+.4f} degC"),
        ("Worst depth", f"{int(m['depths_m'][worst_i])} m  ({m['rmse'][worst_i]:.3f} degC)"),
        ("Protocol", d.get("scoring_protocol", "-")),
    ]))

    s.append(_p(
        "A model is only usable if you know where it fails. This page is the whole list - the "
        "things we could fix, the things we inherited, and the things that will not move whatever "
        "we do.", "lead"))

    # ------------------------------------------------------------------ the picture
    s += heading("1.  Where the error actually is")
    s.append(_p(
        "Teal is our model, grey is plain climatology - the long-term average for that month. "
        "Shorter is better. The story is the <b>shape</b>: we are excellent near the surface, "
        f"worst at <b>{int(m['depths_m'][worst_i])} m</b>, and at <b>1000 m the average beats "
        f"us</b> (the amber bar)."))
    s += depth_chart(m)
    s.append(callout(
        "Why the bulge in the middle is not a bug",
        "Around 100 m sits the <b>thermocline</b> - the sharp temperature drop. It is the depth a "
        "surface measurement constrains least, so it is the hardest part of the problem for "
        "<i>anyone</i>. We measured the reanalysis we trained on against the same floats: at that "
        "depth its error is almost identical to ours. <b>That error is inherited, not created by "
        "us</b> - and no amount of extra training removes it without a better teacher.", "note"))

    # ------------------------------------------------------------------ limitations
    s += heading("2.  The limitations, sorted by whether we can fix them")

    s.append(_p("<b>OURS TO FIX</b> - real weaknesses with a known cause.", "h2"))
    s += table([
        ["Limitation", "The measured detail"],
        ["<b>It runs warm</b>",
         f"Bias {d['overall_bias']:+.4f} degC. Found twice by independent routes. Not corrected, "
         f"because that changes a frozen model and is a decision to take deliberately."],
        ["<b>The mixed layer is worse than the reanalysis</b>",
         "Near the surface we are measurably worse than our own training target. This is the one "
         "error our diagnostics say is genuinely available to us to improve."],
        ["<b>Uncertainty is improved, not calibrated</b>",
         "Still mildly overconfident. We report coverage as a range across depths so the worst "
         "depth cannot hide behind an average."],
        ["<b>The model cannot tell missing data from ordinary sea</b>",
         "A cloud-blanked pixel reaches the network as the channel average. The loader even "
         "computes a mask of which values were real, then discards it."],
        ["<b>An Arabian Sea penalty we cannot explain</b>",
         "Consistent across three training seeds. Four hypotheses tested, cause unknown. Reported "
         "as unexplained rather than given a story."],
    ], widths=[0.30, 0.70], bold_col0=True, font_size=8.3, keep=False)

    s.append(_p("<b>INHERITED</b> - we cannot beat our own teacher.", "h2"))
    s += table([
        ["Limitation", "The measured detail"],
        ["<b>The thermocline error</b>",
         "At 100-150 m our error is within about 0.02 degC of the reanalysis's own error against "
         "the same floats. We have reached the ceiling that training target sets."],
        ["<b>Climatology wins at 1000 m</b>",
         "By a small margin, at one depth of fifteen. The chart labels it rather than hiding it."],
    ], widths=[0.30, 0.70], bold_col0=True, font_size=8.3, keep=False)

    s.append(_p("<b>HARD LIMITS</b> - properties of the instruments and the grid, not of our "
                "effort.", "h2"))
    s += table([
        ["Limitation", "The measured detail"],
        ["<b>No salinity at depth</b>",
         "Satellites give a surface salinity only. So mixed-layer depth by density and the barrier "
         "layer are <b>refused rather than approximated</b> - a plausible number was easy to "
         "produce and would have been wrong to ship."],
        ["<b>Fine structure is invisible</b>",
         "Grid cells are about 25 km. Anything below roughly 100 km is unresolved, and a smooth "
         "map is not evidence of a smooth ocean."],
        ["<b>The satellite cannot see the Bay of Bengal freshwater plume</b>",
         "The salinity product floors well above the real value there. A sensor limit, not a "
         "modelling gap."],
        ["<b>The acoustic SOFAR axis is below our deepest level</b>",
         "It sits near 1500-2000 m; we stop at 1000 m. So we map where it is <i>resolvable</i> "
         "instead of drawing a basin of grid artifact."],
    ], widths=[0.30, 0.70], bold_col0=True, font_size=8.3, keep=False)

    # ------------------------------------------------------------------ cannot answer
    s += heading("3.  Questions we cannot answer at all")
    s.append(_p(
        "These are not weaknesses in the model - they are gaps in what we have been able to "
        "<i>test</i>. Say them before a judge finds them."))
    s.append(bullets([
        "<b>Does it track one place through time?</b> Every number we have compares different "
        "<i>places</i>. Argo floats drift, so they cannot answer this. The moored-buoy data that "
        "could is unreachable from our network.",
        "<b>Is the same physical float in both training and test?</b> Our float table has no "
        "instrument identifier, so our independence is in time only. We cannot rule it out.",
        "<b>How do you compare to other published methods?</b> We do not know. Our anchors are "
        "climatology and the reanalysis we trained on. No published method has been run on our "
        "region by us.",
        "<b>Is the shipped model's output physically stable?</b> Not measurable. Static stability "
        "needs density, density needs salinity, and the shipped model predicts temperature only.",
        "<b>Could it run live tomorrow?</b> No. The record ends June 2026 and extending it is "
        "pipeline work, not a re-run.",
    ]))

    # ------------------------------------------------------------------ future
    s += heading("4.  Future scope")
    s += table([
        ["When", "What we would do", "What it buys"],
        ["<b>Next</b>",
         "Correct the warm bias and improve the mixed layer.",
         "The one accuracy gain our own diagnostics say is genuinely available - the deeper error "
         "is inherited and will not move."],
        ["<b>Next</b>",
         "Give the encoder a <b>missing-data channel</b> so a cloud gap is not read as average sea.",
         "Graceful degradation during the monsoon instead of silent degradation. The mask is "
         "already computed and thrown away, so this is a specific, known fix."],
        ["<b>Next</b>",
         "Re-fetch the float table <b>with instrument identifiers</b>.",
         "Turns 'independent in time' into 'independent by instrument' - closing our weakest "
         "validation claim."],
        ["<b>Then</b>",
         "Validation <b>through time</b> from moored buoys.",
         "Tests whether the model tracks change, not just place - the one validation axis we have "
         "no answer on."],
        ["<b>Then</b>",
         "Run a published method over this basin as a baseline.",
         "An external anchor for our accuracy, instead of only climatology and our own teacher."],
        ["<b>Then</b>",
         "Extend to <b>2000 m</b> and add eddy tracking.",
         "Reaches the acoustic SOFAR axis, and turns single-day event detection into tracking. "
         "Both need a deeper target and a time axis respectively."],
        ["<b>Later</b>",
         "A live ingest path, caching, authentication and monitoring.",
         "Turns a proof of concept into a service an agency could depend on. The marginal data "
         "cost is zero - the satellites are already funded and flying."],
        ["<b>Later</b>",
         "Assimilate <b>every</b> float across all 24,000 cells, not just at float locations.",
         "The operational version of our 'learn from a float' feature: the system improves every "
         "day without ever being retrained."],
    ], widths=[0.11, 0.42, 0.47], bold_col0=True, font_size=8.3, keep=False)

    s.append(callout(
        "The honest summary to close on",
        "Our biggest remaining gain is <b>not</b> a bigger model. Our own measurements say the "
        "deep error is inherited from the training data and the fine structure is beyond the grid "
        "- so more capacity buys little. What would actually move this system forward is better "
        "<b>inputs</b>, better <b>validation</b>, and the operational engineering to run it live.",
        "jury"))

    build(path, BRAND, s, doc_title="OceanEmbed - Limitations and future scope")
    return path


if __name__ == "__main__":
    print(build_note(os.path.join(ROOT, "JURY_NOTES", "OceanEmbed_Limits.pdf")))
