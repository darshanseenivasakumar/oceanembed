"""The end-of-page "what this is and how to read it" block. Owner: Unit A (Arjhun).

WHY A SHARED MODULE RATHER THAN A BLOCK PER PAGE
------------------------------------------------
Every phase-2 page already ends in a hand-written `st.expander`, fourteen of them across nine
pages, each with its own title and its own idea of what belongs inside. `validation_page.py:283`
is the one that got it right -- it iterates `lab.known_weaknesses()`, which returns
`{what, detail, evidence}` triples, so its caveats carry a citation and cannot be written from
memory. This module generalises THAT shape, not the other thirteen.

The audience is a judge or a scientist opening one page cold, with no context and no intention of
reading the repo. So the contract is: what it shows, the formula, what the formula's symbols mean,
how to read the picture, and what it cannot tell you.

WHY THE STREAMLIT IMPORT IS INSIDE THE FUNCTION
-----------------------------------------------
`grep "import streamlit" src/` returns zero matches, and that is deliberate: `src/` is imported by
tests that must run on a machine with no Streamlit and no checkpoint. `tscast_nio/ui_tables.py` is
the existing precedent -- it builds the exact tables the UI renders, using numpy only, so the
numbers are testable without starting a server. This module follows it: the CONTENT is a plain
dataclass anyone can assert on, and only `render()` touches Streamlit.

WHY THE DATACLASS VALIDATES INSTEAD OF TRUSTING THE CALLER
-----------------------------------------------------------
A formula whose symbols are never named is decoration, not an explanation, and this project has
already shipped a caption that was more confident than the thing it described. So a formula
without a `formula_note` raises, and an empty `plain` or `how_to_read` raises. The failure happens
when the page is written, not when a judge is reading it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

#: Text a placeholder would plausibly contain. A footer that survives to the demo with "TODO" in
#: it is worse than no footer, because it reads as an answer.
_PLACEHOLDERS = ("tbd", "todo", "fixme", "xxx", "lorem ipsum", "...")


def _check(name: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{name} is empty -- a panel with no {name} cannot be read cold")
    if v.lower() in _PLACEHOLDERS:
        raise ValueError(f"{name} is the placeholder {v!r}")
    return v


@dataclass(frozen=True)
class Caveat:
    """One limitation, with the evidence behind it.

    `evidence` mirrors `validation.lab.known_weaknesses()` exactly, so one renderer serves both and
    the existing weakness list needs no adapter beyond `caveats_from`. Prefer a path, an artifact
    key, a script, or a `docs/DECISIONS.md D-0NN` reference -- a caveat with prose where its
    evidence should be is one somebody wrote from memory.
    """
    what: str
    detail: str
    evidence: str

    def __post_init__(self):
        for name in ("what", "detail", "evidence"):
            object.__setattr__(self, name, _check(name, getattr(self, name)))


@dataclass(frozen=True)
class Explainer:
    """Everything the end of a page needs to say.

    title        : the panel's name, as a reader would refer to it
    plain        : 2-3 sentences, no jargon. What is this and why would anyone want it?
    how_to_read  : what the colours, axes and GAPS mean on this specific chart
    formula      : LaTeX body for `st.latex`, no $$ delimiters. None when there is no formula --
                   a UI feature does not need one, and inventing one is worse than omitting it.
    formula_note : every symbol named, in words. REQUIRED whenever `formula` is set, and rendered
                   beside it rather than instead of it: `st.latex` appears nowhere else in this
                   repo, so a KaTeX failure must degrade to a readable sentence rather than to a
                   blank expander nobody notices.
    caveats      : what this panel cannot tell you.
    references   : full citations, for anything taken from the literature.
    """
    title: str
    plain: str
    how_to_read: str
    formula: str | None = None
    formula_note: str | None = None
    caveats: tuple[Caveat, ...] = ()
    references: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("title", "plain", "how_to_read"):
            object.__setattr__(self, name, _check(name, getattr(self, name)))
        # An EMPTY formula means "this panel has no equation", which is a legitimate and common
        # case -- a UI feature, or a methodology like the cloud-dropout sweep. The build spec
        # writes it as `formula = ""`. Treating that as a validation failure made a finished page
        # render its results and then die on its own footer. Normalised to None here so both
        # spellings mean the same thing; a formula that is present still has to name its symbols.
        if self.formula is not None and not str(self.formula).strip():
            object.__setattr__(self, "formula", None)
        if self.formula is not None:
            object.__setattr__(self, "formula", _check("formula", self.formula))
            if not (self.formula_note or "").strip():
                raise ValueError(
                    f"{self.title!r}: a formula without a formula_note names no symbols, which is "
                    f"decoration rather than an explanation")
            object.__setattr__(self, "formula_note", _check("formula_note", self.formula_note))
        elif self.formula_note:
            raise ValueError(f"{self.title!r}: formula_note with no formula to annotate")
        object.__setattr__(self, "caveats", tuple(self.caveats))
        object.__setattr__(self, "references", tuple(self.references))


def caveats_from(weaknesses: Iterable[dict]) -> tuple[Caveat, ...]:
    """Adapter for `validation.lab.known_weaknesses()`, which already returns the right triple."""
    return tuple(Caveat(w["what"], w["detail"], w["evidence"]) for w in weaknesses)


def render(explainer: Explainer, *, extra_caveats: Iterable[Caveat] = ()) -> None:
    """Draw the block. Call it LAST on the page. Imports Streamlit lazily -- see the module head.

    `extra_caveats` is for a limitation that depends on what the reader selected -- an
    uncalibrated stage-2 sigma, a date outside the validated window -- which a static Explainer
    cannot know.
    """
    import streamlit as st

    st.divider()
    st.subheader(f"About this panel — {explainer.title}")
    st.markdown(explainer.plain)
    if explainer.formula:
        st.latex(explainer.formula)
        st.caption(explainer.formula_note)
    st.markdown(f"**How to read it:** {explainer.how_to_read}")

    caveats = tuple(explainer.caveats) + tuple(extra_caveats)
    if caveats:
        with st.expander(f"What this panel cannot tell you ({len(caveats)})"):
            for c in caveats:
                st.markdown(f"**⚠ {c.what}** — {c.detail}")
                st.caption(f"Evidence: `{c.evidence}`")
    if explainer.references:
        with st.expander("References"):
            for r in explainer.references:
                st.markdown(f"- {r}")


def render_explainer(title: str, formula: str, plain: str, how_to_read: str,
                     caveats: list[str] | None = None) -> None:
    """The signature the build spec asked for, kept so a page written against it still works.

    Prefer `render(Explainer(...))`: a caveat here is a bare string, so it carries no evidence, and
    an unevidenced caveat is the one kind this project has repeatedly had to go back and check.
    """
    import streamlit as st

    exp = Explainer(title=title, plain=plain, how_to_read=how_to_read,
                    formula=formula or None,
                    formula_note=("Symbols are defined in the text above." if formula else None))
    st.divider()
    st.subheader(f"About this panel — {exp.title}")
    if exp.formula:
        st.latex(exp.formula)
    st.markdown(exp.plain)
    st.markdown(f"**How to read it:** {exp.how_to_read}")
    if caveats:
        with st.expander("Caveats and limitations"):
            for c in caveats:
                st.markdown(f"- {c}")
