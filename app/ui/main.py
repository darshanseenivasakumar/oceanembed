"""OceanEmbed — the instrument. One page, every feature, no reloads.

OWNER: Unit A (Arjhun). PHASE-2. The frozen demo (app/streamlit_app.py, app/panels/) is
READ-ONLY and is neither edited nor imported here.

    streamlit run app/ui/main.py --server.port 8500

WHY ONE PAGE
Sixteen features on sixteen ports reads as sixteen prototypes. A judge will not open sixteen
tabs. Here the feature rail swaps the stage in place: no navigation, no reload, and because the
whole-field reconstruction is cached on (date, stage, version, device), switching between
features on the same date costs nothing after the first.

WHY THE PAGE IS QUIET
Every control carries a `?`. The caveats this project refuses to drop -- uncalibrated sigma, the
GLORYS comparator, sea floor versus missing data -- live behind those buttons instead of as
paragraphs on screen. Nothing true was removed; it was moved to where it is read on demand.

THE ONE THING THIS FILE MUST DO ALONE
It is the only file under app/ui/ that may call st.set_page_config. tests/phase2/
test_launch_ports.py AST-parses every file under app/ for that call and demands a matching
docstring run-line, a launch.json entry and a unique port for each one it finds.
"""
from __future__ import annotations

import os
import sys
import traceback

import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", ".."), os.path.join(_HERE, "..", "..", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

st.set_page_config(page_title="OceanEmbed — subsurface ocean temperature",
                   page_icon="🌊", layout="wide",
                   initial_sidebar_state="collapsed")

from app.ui import words as C          # noqa: E402
from app.ui import data as D          # noqa: E402
from app.ui import theme, ux          # noqa: E402
from app.ui.features import render_feature  # noqa: E402

theme.inject()

KEYS = [f[0] for f in C.FEATURES]
LABELS = {f[0]: f[1] for f in C.FEATURES}
TITLES = {f[0]: (f[2], f[3]) for f in C.FEATURES}


class Ctx:
    """What every feature is handed. Deliberately tiny and explicit."""

    def __init__(self, date, source, device, stage, version):
        self.date = date
        self.source = source
        self.device = device
        self.stage = stage
        self.version = version

    @property
    def is_satellite(self) -> bool:
        return self.source == "Satellite"


@st.dialog(C.JUDGE_TITLE, width="large")
def _judge_dialog():
    st.markdown(C.JUDGE)


def _topbar(head: dict) -> None:
    live = "live" if head else "warn"
    text = "LIVE MODEL" if head else "MANIFEST NOT FOUND"
    st.html(
        '<div class="oe-bar">'
        f'<span class="oe-word">{C.PRODUCT}</span>'
        f'{ux.chips([(C.PROBLEM_ID, "plain"), (C.TAGLINE, "plain"), (text, live)])}'
        "</div>"
    )


def _controls() -> Ctx:
    """The four global controls, on one line, each with its own explainer."""
    c = st.columns([2.4, 2.0, 1.5, 1.3, 1.4], vertical_alignment="bottom")

    version = D.version(1)
    try:
        all_dates = D.dates(1, version)
    except Exception as e:
        st.error(f"The model bundle could not be opened: {type(e).__name__}: {e}")
        st.stop()

    with c[0]:
        with ux.control("date", ratio=(6, 1)):
            date = st.selectbox("Date", all_dates, index=max(0, len(all_dates) - 40),
                                key="g_date")
    with c[1]:
        with ux.control("source", ratio=(6, 1)):
            source = st.segmented_control(
                "Input", ["Satellite", "GLORYS"], default="Satellite", key="g_source")
    with c[2]:
        with ux.control("device", ratio=(5, 2)):
            gpu = st.toggle("GPU", value=False, key="g_gpu",
                            disabled=not D.cuda_available(),
                            help=None if D.cuda_available() else "no CUDA device on this machine")
    with c[3]:
        st.write("")
        if st.button("Summary", use_container_width=True, type="primary"):
            _judge_dialog()
    with c[4]:
        st.write("")
        ux.explain("judge", label="What is this?")

    source = source or "Satellite"
    if source == "GLORYS":
        st.warning(
            "**GLORYS is a comparator, not the deliverable.** It reads reanalysis as input, which "
            "the problem statement does not allow. Scores shown under it are an upper bound.",
            icon=":material/info:")
    return Ctx(date, source, "cuda" if gpu else None, 1, version)


def _rail() -> str:
    sel = st.pills("Feature", KEYS, default=st.session_state.get("g_feature", KEYS[0]),
                   format_func=lambda k: LABELS[k], key="g_feature",
                   label_visibility="collapsed")
    return sel or KEYS[0]


def _elsewhere() -> None:
    with st.expander("Other features, still on their own ports"):
        st.caption("These are built and working; they have not yet been rebuilt into this shell. "
                   "Each runs standalone with the command shown.")
        for name, port, what in C.ELSEWHERE:
            st.markdown(f"**{name}** · :gray[{what}] — `localhost:{port}`")


def main() -> None:
    head = D.headline()
    _topbar(head)
    ctx = _controls()
    key = _rail()

    title, subtitle = TITLES[key]
    ux.section(f"{KEYS.index(key) + 1:02d}", title, subtitle)

    with ux.stage():
        try:
            render_feature(key, ctx)
        except Exception as e:
            st.error(f"**This panel could not be drawn** — {type(e).__name__}: {e}")
            with st.expander("Detail"):
                st.code(traceback.format_exc())

    st.divider()
    _elsewhere()
    if head:
        st.caption(
            f"Deliverable: satellite inputs, {head['profiles']} independent Argo profiles, "
            f"RMSE {head['rmse']} °C. Checkpoint `{head['sha']}`. "
            "Every figure read from artifacts/frozen_manifest.json.")


if __name__ == "__main__":
    main()
