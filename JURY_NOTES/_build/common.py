"""Shared layout for the seventeen feature notes.

A feature note is written as a plain dict; this module turns it into a story.
Keeping the layout in one place means all seventeen read identically, so a
presenter who has rehearsed one has rehearsed all of them.
"""
from __future__ import annotations

from engine import (
    PageBreak, Spacer, _p, build, bullets, callout, cmd, cover, heading,
    kvstrip, quote, recap, steps, table,
)

BRAND = "OceanEmbed  |  SIH26066  |  Subsurface temperature from satellites"


def feature_note(out_path, spec):
    """spec keys -> the fixed nine-section note."""
    n = spec["n"]
    story = []

    story += cover(
        badge=f"{n:02d}",
        badge_sub="FEATURE",
        kicker=f"FEATURE {n} OF 17   -   {spec['kicker']}",
        title=spec["title"],
        subtitle=spec["subtitle"],
    )

    story.append(kvstrip(spec["meta"]))

    story.append(_p(spec["lead"], "lead"))

    # 1 -----------------------------------------------------------------
    story += heading("1.  What this feature is, in plain words")
    for para in spec["plain"]:
        story.append(_p(para))
    if spec.get("analogy"):
        story.append(callout("The everyday picture", spec["analogy"], "teal"))

    # 2 -----------------------------------------------------------------
    story += heading("2.  What you actually see on the screen")
    if spec.get("screen_intro"):
        story.append(_p(spec["screen_intro"]))
    story.append(bullets(spec["screen"]))

    # 3 -----------------------------------------------------------------
    story += heading("3.  How to run it, step by step")
    if spec.get("run_intro"):
        story.append(_p(spec["run_intro"]))
    story.append(cmd(spec["command"], spec.get("command_label", "RUN THIS")))
    story.append(steps(spec["steps"]))
    for extra in spec.get("extra_commands", []):
        story.append(cmd(extra[1], extra[0]))
    if spec.get("run_note"):
        story.append(callout(spec["run_note"][0], spec["run_note"][1], spec["run_note"][2]))

    # 4 -----------------------------------------------------------------
    story += heading("4.  Why the problem statement needs this")
    for para in spec["why"]:
        story.append(_p(para))
    if spec.get("ps_rows"):
        story.append(table(
            [["PS requirement", "How this feature answers it"]] + spec["ps_rows"],
            widths=[0.33, 0.67], bold_col0=True,
        ))

    # 5 -----------------------------------------------------------------
    story += heading("5.  The measured numbers behind it")
    if spec.get("numbers_intro"):
        story.append(_p(spec["numbers_intro"]))
    if spec.get("numbers_table"):
        story.append(table(
            spec["numbers_table"]["rows"],
            widths=spec["numbers_table"].get("widths"),
            bold_col0=True,
            align=spec["numbers_table"].get("align"),
            font_size=spec["numbers_table"].get("font_size"),
        ))
    if spec.get("numbers"):
        story.append(bullets(spec["numbers"]))

    # 6 -----------------------------------------------------------------
    story += heading("6.  The impact - and who it is for")
    for para in spec.get("impact_intro", []):
        story.append(_p(para))
    story.append(table(
        [["Who", "What changes for them"]] + spec["impact_rows"],
        widths=[0.27, 0.73], bold_col0=True,
    ))
    if spec.get("society"):
        story.append(callout("Why society gains from this", spec["society"], "good"))

    # 7 -----------------------------------------------------------------
    story += heading("7.  Say this to the jury")
    story.append(quote(spec["pitch"], spec.get("pitch_note")))

    # 8 -----------------------------------------------------------------
    story += heading("8.  Questions the jury will ask")
    for q, a in spec["qa"]:
        story.append(_p(f"<b>Q. {q}</b>"))
        story.append(_p(f"<b>A.</b>  {a}"))
        story.append(Spacer(1, 2))

    # 9 -----------------------------------------------------------------
    story += heading("9.  The honest limit - say it before they find it")
    story.append(callout(spec["limit"][0], spec["limit"][1], "warn"))

    # closing recap ------------------------------------------------------
    tail = (f"Feature {n} of 17.  Next: Feature {n + 1}." if n < 17
            else "Feature 17 of 17.  Next: the closing note - conclusion, limitations and viva "
                 "questions.")
    story += recap(spec["recap"], spec["tiles"], tail)

    build(out_path, f"{BRAND}   -   Feature {n}: {spec['short']}", story,
          doc_title=f"OceanEmbed Feature {n} - {spec['title']}")
    return out_path
