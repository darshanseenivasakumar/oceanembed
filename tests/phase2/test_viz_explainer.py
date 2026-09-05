"""The shared page footer. Owner: Unit A (Arjhun).

The content is a plain dataclass precisely so it can be checked here without Streamlit, a running
server, or a checkpoint. The rendering is exercised against a recording stub, so "it renders" is a
measured fact rather than an assumption.
"""
from __future__ import annotations

import ast
import os
import sys
import types

import pytest

from phase2 import viz_explainer as V

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def an_explainer(**over):
    kw = dict(title="Sound speed", plain="How fast sound travels at each depth.",
              how_to_read="Bunched contours mean sound bends there.")
    kw.update(over)
    return V.Explainer(**kw)


# ==================================================== the src/ invariant

def test_streamlit_is_never_imported_at_module_level():
    """`src/` is imported by tests that run with no Streamlit installed. A top-level import here
    would make the whole package unimportable on such a machine, and the failure would look like a
    broken test suite rather than a broken import. Parsed with ast, not grepped -- the module
    DOCUMENTS this rule in prose and a text search finds the rule as readily as a violation.
    """
    tree = ast.parse(open(os.path.join(ROOT, "src/phase2/viz_explainer.py"), encoding="utf-8").read())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = [a.name for n in top if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in top if isinstance(n, ast.ImportFrom)]
    assert not any("streamlit" in n for n in names), names


def test_the_whole_src_tree_still_has_no_module_level_streamlit_import():
    """The invariant this module had to obey, asserted for everyone -- so the next shared helper
    cannot quietly be the first to break it."""
    offenders = []
    for base, _, files in os.walk(os.path.join(ROOT, "src")):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(base, f)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue
            for n in tree.body:
                if isinstance(n, ast.Import) and any("streamlit" in a.name for a in n.names):
                    offenders.append(path)
                if isinstance(n, ast.ImportFrom) and "streamlit" in (n.module or ""):
                    offenders.append(path)
    assert offenders == []


# ==================================================== validation is the point

def test_a_formula_without_its_symbols_named_is_refused():
    """A formula nobody can read is decoration. The failure happens when the page is written."""
    with pytest.raises(ValueError, match="formula_note"):
        an_explainer(formula=r"c = 1448.96 + 4.591T")


def test_a_formula_note_with_no_formula_is_also_refused():
    with pytest.raises(ValueError, match="no formula"):
        an_explainer(formula_note="T is temperature")


def test_a_formula_with_its_note_is_accepted():
    e = an_explainer(formula=r"c = 1448.96 + 4.591T", formula_note="T is temperature in degC.")
    assert e.formula_note.startswith("T is")


@pytest.mark.parametrize("field", ["title", "plain", "how_to_read"])
def test_an_empty_field_is_refused_rather_than_rendered_blank(field):
    with pytest.raises(ValueError, match=field):
        an_explainer(**{field: "   "})


@pytest.mark.parametrize("placeholder", ["TODO", "tbd", "FIXME", "..."])
def test_a_placeholder_that_survived_to_the_demo_is_refused(placeholder):
    """A footer reading 'TODO' is worse than no footer: it renders in the same slot as an answer."""
    with pytest.raises(ValueError):
        an_explainer(plain=placeholder)


def test_a_caveat_must_carry_evidence():
    with pytest.raises(ValueError, match="evidence"):
        V.Caveat("Uses GLORYS salinity", "The deliverable predicts temperature only.", "")


def test_an_explainer_is_frozen_so_a_page_cannot_edit_a_shared_one_in_place():
    e = an_explainer()
    with pytest.raises(Exception):
        e.title = "something else"


# ==================================================== the adapter to the existing weakness list

def test_caveats_from_consumes_the_real_known_weaknesses_list():
    """`lab.known_weaknesses()` already returns {what, detail, evidence}. If that ever changes
    shape, this fails here rather than on a page at demo time."""
    from phase2.validation import lab

    weaknesses = lab.known_weaknesses()
    assert weaknesses, "the weakness list is empty -- that is itself worth knowing"
    caveats = V.caveats_from(weaknesses)
    assert len(caveats) == len(weaknesses)
    assert all(isinstance(c, V.Caveat) and c.evidence for c in caveats)


# ==================================================== rendering, against a recording stub

class _Recorder(types.ModuleType):
    """The smallest Streamlit that answers this module's calls, recording what it was asked to do."""

    def __init__(self):
        super().__init__("streamlit")
        self.calls: list[tuple[str, str]] = []
        for name in ("divider", "subheader", "markdown", "latex", "caption"):
            setattr(self, name, self._record(name))

    def _record(self, name):
        def fn(*a, **k):
            self.calls.append((name, str(a[0]) if a else ""))
        return fn

    def expander(self, label, *a, **k):
        self.calls.append(("expander", str(label)))
        rec = self

        class _Ctx:
            def __enter__(self_inner):
                return rec

            def __exit__(self_inner, *exc):
                return False
        return _Ctx()


@pytest.fixture
def st_stub(monkeypatch):
    stub = _Recorder()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    return stub


def test_render_emits_the_plain_text_the_formula_and_the_how_to_read(st_stub):
    V.render(an_explainer(formula=r"c(T,S,z)", formula_note="T is temperature."))
    kinds = [k for k, _ in st_stub.calls]
    body = " ".join(v for _, v in st_stub.calls)
    assert "latex" in kinds
    assert "How to read it:" in body
    assert "How fast sound travels" in body


def test_the_formula_note_is_rendered_beside_the_latex_not_instead_of_it(st_stub):
    """st.latex appears nowhere else in this repo, so KaTeX is unexercised ground. If it fails, the
    reader must still get a sentence rather than a gap."""
    V.render(an_explainer(formula=r"\sigma_\theta = \rho - 1000", formula_note="rho is density."))
    idx = {k: i for i, (k, _) in enumerate(st_stub.calls)}
    assert idx["caption"] == idx["latex"] + 1
    assert "rho is density." in [v for k, v in st_stub.calls if k == "caption"]


def test_a_panel_with_no_caveats_draws_no_empty_expander(st_stub):
    """An empty 'Caveats' expander reads as 'we checked and there are none', which is a claim."""
    V.render(an_explainer())
    assert "expander" not in [k for k, _ in st_stub.calls]


def test_extra_caveats_reach_the_reader_and_are_counted(st_stub):
    V.render(an_explainer(caveats=(V.Caveat("a", "b", "c"),)),
             extra_caveats=(V.Caveat("d", "e", "artifacts/x.json"),))
    labels = [v for k, v in st_stub.calls if k == "expander"]
    assert labels == ["What this panel cannot tell you (2)"]
    assert "Evidence: `artifacts/x.json`" in [v for k, v in st_stub.calls if k == "caption"]


def test_the_spec_signature_still_works_for_a_page_written_against_it(st_stub):
    V.render_explainer(title="Transect", formula="", plain="A vertical slice.",
                       how_to_read="Blank means land.", caveats=["Uses GLORYS salinity."])
    body = " ".join(v for _, v in st_stub.calls)
    assert "A vertical slice." in body and "Blank means land." in body
    assert "latex" not in [k for k, _ in st_stub.calls], "an empty formula must not render as one"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_panel_with_no_equation_is_allowed_and_needs_no_symbol_note(blank):
    """`formula=""` is the build spec's own spelling for a panel that has no equation -- a UI
    feature, or a methodology sweep. Rejecting it made a finished page render all of its results
    and then die on its own footer, which is a worse failure than the one the check guards.
    """
    e = an_explainer(formula=blank)
    assert e.formula is None
    assert e.formula_note is None


def test_an_empty_formula_still_refuses_a_dangling_symbol_note():
    """Normalising "" to None must not open a hole: a note describing an equation that is not
    there is still an explanation of nothing."""
    with pytest.raises(ValueError, match="no formula"):
        an_explainer(formula="", formula_note="T is temperature")


def test_a_real_formula_still_has_to_name_its_symbols(st_stub):
    with pytest.raises(ValueError, match="formula_note"):
        an_explainer(formula=r"c = 1448.96 + 4.591T")
    V.render(an_explainer(formula=r"c = 1448.96", formula_note="T is temperature."))
    assert "latex" in [k for k, _ in st_stub.calls]
