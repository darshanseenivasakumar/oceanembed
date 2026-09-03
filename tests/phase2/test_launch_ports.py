"""Every Streamlit app has exactly one port, and everyone agrees on which.

WHY THIS EXISTS
The ports lived in two places that could disagree: each page's module docstring (the command a
human copies) and `.claude/launch.json` (the command tooling runs). They did disagree --
`tscast_page.py` and `cube_page.py` both claimed 8504 while DARSHAN_BUILD_SPEC.md:1733 had already
assigned tscast 8507 -- so starting the dashboard could silently serve the 3-D cube instead, or
fail to bind at all. Three more ports were documented in docstrings and absent from launch.json
entirely, which is why they were always started by hand.

A port map is exactly the kind of thing that rots quietly, so it is a check that fails rather than
a table in a doc.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAUNCH = ROOT / ".claude" / "launch.json"
RUN_LINE = re.compile(r"streamlit run (\S+\.py) --server\.port (\d+)")


def _configs() -> list[dict]:
    with open(LAUNCH, encoding="utf-8") as f:
        return json.load(f)["configurations"]


def _app_pages() -> list[pathlib.Path]:
    """Every Streamlit entry point: a page that configures itself is one someone can run."""
    return sorted(p for p in ROOT.glob("app/**/*.py")
                  if "set_page_config" in p.read_text(encoding="utf-8"))


def test_no_two_configurations_share_a_port():
    ports = [c["port"] for c in _configs()]
    dupes = sorted({p for p in ports if ports.count(p) > 1})
    assert not dupes, f"launch.json has colliding ports: {dupes}"


def test_no_two_pages_document_the_same_port():
    claimed: dict[int, list[str]] = {}
    for page in _app_pages():
        m = RUN_LINE.search(page.read_text(encoding="utf-8"))
        if m:
            claimed.setdefault(int(m.group(2)), []).append(page.name)
    clashes = {p: names for p, names in claimed.items() if len(names) > 1}
    assert not clashes, f"pages claiming the same port in their docstrings: {clashes}"


@pytest.mark.parametrize("cfg", _configs(), ids=lambda c: c["name"])
def test_launch_port_matches_the_pages_own_docstring(cfg):
    """launch.json must not become a second, disagreeing source of truth."""
    args = cfg["runtimeArgs"]
    path = ROOT / args[args.index("run") + 1]
    assert path.exists(), f"{cfg['name']} points at a missing file: {path}"
    m = RUN_LINE.search(path.read_text(encoding="utf-8"))
    assert m, f"{path.name} has no `streamlit run ... --server.port N` line in its docstring"
    assert int(m.group(2)) == cfg["port"], (
        f"{path.name} docstring says port {m.group(2)}, launch.json says {cfg['port']}")


def test_every_runnable_page_has_a_launch_entry():
    """A page reachable only by a hand-typed command is a page nobody runs."""
    wired = {(ROOT / c["runtimeArgs"][c["runtimeArgs"].index("run") + 1]).resolve()
             for c in _configs()}
    missing = [p.name for p in _app_pages() if p.resolve() not in wired]
    assert not missing, f"Streamlit pages with no launch.json entry: {missing}"
