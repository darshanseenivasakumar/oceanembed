"""The only place `@st.cache_*` touches the v2 model. A helper, not a page. (Unit A / Arjhun.)

Underscore-prefixed and carrying no `st.set_page_config`, so `test_launch_ports` does not treat it
as a runnable page and it needs no launch.json entry.

THE ARGUMENT THAT MUST NEVER BE RENAMED
---------------------------------------
`version` is a plain positional `str`. Streamlit DROPS any cached-function argument whose name
starts with an underscore -- that is how `_version` would silently become no cache key at all, and
the cache would keep serving a field built by a checkpoint that has since been replaced. That trap
is already commented in `cube_page.py:99` and `tscast_page.py:20`; this is the third place it
needed saying, which is why the loader now lives here instead of being pasted a fourth time.

Every science decision -- the lock, the cache key, the device, what `keep` means -- is in
`phase2.tscast_nio.field_cache`. This file is Streamlit plumbing over it and nothing else.
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from phase2.tscast_nio import field_cache as FC          # noqa: E402

DEFAULT_KEEP = FC.DEFAULT_KEEP
ALL_KEYS = FC.ALL_KEYS

#: ~12 MB per cached field at DEFAULT_KEEP. Six dates is ~72 MB, which is a browsing history deep
#: enough to flick between dates without a reload and shallow enough not to grow without bound --
#: 388 dates unbounded would be 4.6 GB.
MAX_CACHED_FIELDS = 6


def version(stage: int = 1) -> str:
    """Pass this into every cached call below. See the module docstring for why it is not `_v`."""
    return FC.cache_version(stage)


@st.cache_resource(show_spinner="Loading the model …")
def predictor(stage: int, version: str):
    return FC.get_predictor(stage)


@st.cache_data(show_spinner=False)
def dates(stage: int, version: str) -> list[str]:
    """The dates this model can answer for -- never another bundle's calendar."""
    return FC.available_dates(stage, predictor=predictor(stage, version))


@st.cache_data(show_spinner="Reconstructing the field (~32 s on CPU) …",
               max_entries=MAX_CACHED_FIELDS)
def field(date_str: str, stage: int, version: str,
          keep: tuple[str, ...] = DEFAULT_KEEP, device: str | None = None) -> dict:
    """One reconstructed field. `keep` is a TUPLE so it is hashable as a cache key."""
    return FC.field_for(date_str, stage=stage, keep=tuple(keep), device=device,
                        predictor=predictor(stage, version))


@st.cache_data(show_spinner="Reconstructing the profile …", max_entries=64)
def point(lat: float, lon: float, date_str: str, stage: int, version: str) -> dict:
    """One point profile, through the same lock the field path uses."""
    return FC.reconstruct_point(lat, lon, date_str, stage=stage,
                                predictor=predictor(stage, version))


def date_picker(stage: int = 1, *, label: str = "date", default: str | None = None,
                key: str | None = None) -> str:
    """A select box over the model's REAL calendar, so an out-of-bundle date cannot be chosen.

    `_time()` is an argmin with no bound: typed into a text box, 1850-01-01 returns bundle index 0
    and a complete, plausible field. A picker is the cheapest place to make that unreachable.
    """
    known = dates(stage, version(stage))
    idx = known.index(default) if default in known else len(known) - 1
    return st.selectbox(label, known, index=idx, key=key)


def device_picker(*, key: str | None = None) -> str | None:
    """Optional CUDA opt-in. Default stays wherever the predictor loaded -- see `FC.device_default`.

    Offered only when torch reports a GPU, because a disabled control a judge cannot use is worse
    than no control.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return FC.device_default()
    except Exception:
        return FC.device_default()

    on = st.sidebar.toggle(
        "reconstruct on GPU", value=(FC.device_default() == "cuda"), key=key,
        help="32 s on CPU vs 7.8 s on this GPU, measured; the two agree to 7e-4 °C. The exported "
             "file is always CPU, so a GPU render can differ from it in the last digits.")
    return "cuda" if on else None
