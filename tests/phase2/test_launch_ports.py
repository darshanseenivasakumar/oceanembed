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


def _streamlit_target(cfg):
    """The page a config runs, or None if the config is not a Streamlit page.

    Added 2026-09-05 with the export API, which launches uvicorn and has no `run` token at all --
    `args.index("run")` raised ValueError, which reads like a broken test rather than a config the
    check does not apply to. The alternative was exempting the API from the port map entirely, and
    exempting the new thing is exactly how the map rotted the first time.
    """
    args = cfg["runtimeArgs"]
    if "streamlit" not in args or "run" not in args:
        return None
    return ROOT / args[args.index("run") + 1]


@pytest.mark.parametrize("cfg", _configs(), ids=lambda c: c["name"])
def test_launch_port_matches_the_pages_own_docstring(cfg):
    """launch.json must not become a second, disagreeing source of truth."""
    path = _streamlit_target(cfg)
    if path is None:
        pytest.skip(f"{cfg['name']} is not a Streamlit page; see the API docstring test below")
    assert path.exists(), f"{cfg['name']} points at a missing file: {path}"
    m = RUN_LINE.search(path.read_text(encoding="utf-8"))
    assert m, f"{path.name} has no `streamlit run ... --server.port N` line in its docstring"
    assert int(m.group(2)) == cfg["port"], (
        f"{path.name} docstring says port {m.group(2)}, launch.json says {cfg['port']}")


def test_every_runnable_page_has_a_launch_entry():
    """A page reachable only by a hand-typed command is a page nobody runs."""
    wired = {t.resolve() for t in (_streamlit_target(c) for c in _configs()) if t is not None}
    missing = [p.name for p in _app_pages() if p.resolve() not in wired]
    assert not missing, f"Streamlit pages with no launch.json entry: {missing}"


def test_the_api_config_port_matches_its_module_docstring():
    """The property the skip above gives up, put back for the one non-Streamlit entry.

    Same one-source-of-truth rule as the pages: the port in launch.json must equal the port the
    module's own docstring tells a human to run. Skipped if the API is not registered, so this file
    does not fail on a checkout that predates it.
    """
    cfgs = [c for c in _configs() if _streamlit_target(c) is None]
    if not cfgs:
        pytest.skip("no non-Streamlit configs registered")
    for cfg in cfgs:
        mod = ROOT / "src" / "phase2" / "api" / "app.py"
        assert mod.exists(), f"{cfg['name']} is registered but {mod} does not exist"
        m = re.search(r"--port (\d+)", mod.read_text(encoding="utf-8"))
        assert m, "app.py's docstring does not show the run command with a --port"
        assert int(m.group(1)) == cfg["port"], (
            f"app.py docstring says port {m.group(1)}, launch.json says {cfg['port']}")
