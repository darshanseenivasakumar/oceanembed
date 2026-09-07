"""One shared end-of-page 'About this panel' block, so every Phase-2 page explains itself the same
way: what it shows, the formula behind it, how to read it, and its caveats -- in plain language a
judge or scientist can follow cold.

OWNER: shared (Phase-2 viz). Generalises the st.expander pattern already at the bottom of
app/phase2/validation_page.py so pages do not each invent their own explainer.
"""
from __future__ import annotations


def render_explainer(st, title: str, formula: str, plain: str, how_to_read: str,
                     caveats: list[str] | None = None) -> None:
    """Call LAST on a Streamlit page. `st` is the streamlit module (passed in so this module has no
    Streamlit import of its own and stays trivially testable). `formula` is a raw LaTeX string, or ""
    to skip the equation."""
    st.divider()
    st.subheader(f"About this panel — {title}")
    if formula:
        st.latex(formula)
    st.markdown(plain)
    st.markdown(f"**How to read it:** {how_to_read}")
    if caveats:
        with st.expander("Caveats and limitations"):
            for c in caveats:
                st.markdown(f"- {c}")
