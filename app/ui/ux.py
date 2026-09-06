"""The component kit: top bar, stat tiles, section headers, and the explain button.

OWNER: Unit A (Arjhun). NOT a page -- no st.set_page_config here.

THE EXPLAIN BUTTON IS THE POINT OF THIS FILE
Every control on the instrument carries a small round `?`. Pressing it opens a short summary of
what that control does and what it changes -- two or three sentences, plain language, no jargon
that is not immediately unpacked.

That is not decoration. It is what lets the surface be CLEAN. The honest caveats this project
lives by -- "this sigma is not calibrated", "GLORYS is a comparator, not the deliverable",
"gaps are the sea floor, not missing data" -- used to sit on screen as paragraphs, which is what
made the pages read as documents rather than instruments. They are not deleted; they move in
here. Nothing true is lost, and the screen gets quiet.

Every string a user can read lives in app/ui/words.py, never inline in a feature. One file to
proofread, and no feature can quietly grow a wall of text.
"""
from __future__ import annotations

from contextlib import contextmanager

import streamlit as st

from . import words as C


# --------------------------------------------------------------------------- explain
def explain(eid: str, *, label: str = "?") -> None:
    """The `?` beside a control. Opens copy.EXPLAIN[eid] as a popover.

    An unknown id is shown as a visible amber note rather than silently skipped: a control whose
    explanation was never written is a gap in the product, and hiding it is how it ships.
    """
    item = C.EXPLAIN.get(eid)
    if item is None:
        st.caption(f":orange[no explainer for `{eid}`]")
        return
    title, body = item
    with st.popover(label, use_container_width=False):
        st.markdown(f"**{title}**")
        st.markdown(body)


@contextmanager
def control(eid: str, ratio: tuple = (7, 1)):
    """Lay out one widget with its `?` beside it.

        with ux.control("depth"):
            depth = st.select_slider(...)

    The widget is bound in the enclosing scope as usual -- `with` does not open one.
    """
    try:
        a, b = st.columns(ratio, vertical_alignment="bottom")
    except TypeError:                      # older signature, no vertical_alignment
        a, b = st.columns(ratio)
    with b:
        explain(eid)
    with a:
        yield a


# ------------------------------------------------------------------------- structure
def section(number: str, title: str, subtitle: str = "") -> None:
    """A numbered section header. Used for the three parts every feature carries."""
    st.html(
        f'<div class="oe-h"><span class="oe-h-n">{number}</span>'
        f'<span class="oe-h-t">{title}</span></div>'
        + (f'<div class="oe-h-s">{subtitle}</div>' if subtitle else "")
    )


def tiles(items) -> None:
    """A row of stat tiles. `items` is (label, value, unit, sub) with unit/sub optional.

    Values arrive already formatted -- this renders, it never rounds. A component that formats
    numbers is a component that can quietly change one.
    """
    cells = []
    for it in items:
        label, value = it[0], it[1]
        unit = it[2] if len(it) > 2 else ""
        sub = it[3] if len(it) > 3 else ""
        cells.append(
            f'<div class="oe-tile"><div class="oe-tile-l">{label}</div>'
            f'<div class="oe-tile-v">{value}'
            + (f'<span class="oe-tile-u">{unit}</span>' if unit else "")
            + "</div>"
            + (f'<div class="oe-tile-s">{sub}</div>' if sub else "")
            + "</div>"
        )
    st.html(f'<div class="oe-tiles">{"".join(cells)}</div>')


def chips(items) -> str:
    """Inline pills. `items` is (text, kind) with kind in live/cached/ok/warn/plain."""
    kind_cls = {"live": "oe-chip oe-chip-live", "cached": "oe-chip oe-chip-cached",
                "ok": "oe-chip oe-chip-ok", "warn": "oe-chip oe-chip-warn",
                "plain": "oe-chip"}
    out = []
    for text, kind in items:
        dot = '<span class="oe-dot"></span>' if kind == "live" else ""
        out.append(f'<span class="{kind_cls.get(kind, "oe-chip")}">{dot}{text}</span>')
    return "".join(out)


def skeleton(height: int = 420) -> None:
    """Shown while a field reconstructs. A blank page for 32 seconds reads as broken."""
    st.html(f'<div class="oe-skel" style="height:{height}px"></div>')


@contextmanager
def stage(key: str = "oe_stage"):
    """Wrap the feature body so the entrance transition fires when the feature changes.

    A KEYED container: Streamlit tags it in the DOM with class `st-key-<key>`, which is the only
    stable hook CSS has on a Streamlit subtree. st.html cannot be used for this -- it injects an
    isolated element and cannot wrap the elements that come after it, so it would animate an
    empty div while the content it was meant to carry sat still.
    """
    with st.container(key=key):
        yield


def caveat(text: str) -> None:
    """The amber inline note. Reserved for things that change how a number may be READ."""
    st.warning(text, icon=":material/warning:")


# ------------------------------------------------------- the three-part contract
def instrument(subtitle: str = "") -> None:
    """Part 1 header. The controls and the picture go under this and nothing else."""
    section("01", "The instrument", subtitle)


def maths(formula: str, symbols, note: str = "") -> None:
    """Part 2: the equation, then every symbol in it named, with units and provenance.

    `symbols` is (symbol, meaning, units, source). The source column is the point of the table:
    a judge reading rho*cp*integral wants to know that rho is 1026 kg/m3 and WHERE that came
    from. A formula whose constants have no stated origin is decoration.
    """
    section("02", "The mathematics")
    with st.container(border=True):
        if formula:
            st.latex(formula)
        if symbols:
            rows = "".join(
                f'<tr><td class="oe-sym">{s}</td><td>{m}</td>'
                f'<td class="oe-dim">{u or "—"}</td><td class="oe-dim">{src}</td></tr>'
                for s, m, u, src in symbols)
            st.html(
                '<table class="oe-tbl"><thead><tr><th>symbol</th><th>meaning</th>'
                f'<th>units</th><th>from</th></tr></thead><tbody>{rows}</tbody></table>')
        if note:
            st.caption(note)


def inference(what: str, conclude: str, limits=()) -> None:
    """Part 3: what it shows, what to conclude, and what it cannot tell you.

    Three fixed blocks, never a blob. The third is not optional padding -- it is the block that
    makes the other two believable.
    """
    section("03", "The inference")
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown(f"**What you are looking at**  \n{what}")
    with b:
        st.markdown(f"**What you can conclude**  \n{conclude}")
    if limits:
        with st.expander(f"What this cannot tell you  ·  {len(limits)}"):
            for claim_, evidence in limits:
                st.markdown(f"— {claim_}")
                st.caption(f"evidence: `{evidence}`")
