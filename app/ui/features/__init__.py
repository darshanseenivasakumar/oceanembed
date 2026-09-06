"""Feature registry. One module per feature, imported only when it is selected.

OWNER: Unit A (Arjhun). NOT pages -- nothing under here calls st.set_page_config.

LAZY ON PURPOSE. Importing all eight at startup would pay every feature's import cost before the
first paint, and a single broken feature would take the whole instrument down with it. Here a
failure is contained to the stage it happens on, and the other seven still work.

Every feature exposes exactly one entry point:

    def render(ctx) -> None

`ctx` carries the four global choices -- date, source, device, model version -- so a feature never
reads a widget it did not draw.
"""
from __future__ import annotations

import importlib

#: feature key -> module name in this package.
MODULES = {
    "ocean3d": "ocean3d",
    "clickpoint": "clickpoint",
    "confidence": "confidence",
    "cyclone": "cyclone",
    "transect": "transect",
    "acoustics": "acoustics",
    "validation": "validation",
    "priority": "priority",
}


def render_feature(key: str, ctx) -> None:
    name = MODULES.get(key)
    if name is None:
        raise KeyError(f"no feature registered under {key!r}")
    mod = importlib.import_module(f".{name}", __name__)
    mod.render(ctx)
