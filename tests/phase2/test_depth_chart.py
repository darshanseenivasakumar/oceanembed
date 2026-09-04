"""The depth-error chart: the one plot a jury reads. Owner: Unit A (Arjhun).

WHY A TEST FOR A CHART
This chart was already on the Benchmark tab and its numbers were always right, but it rendered as
a zigzag through itself and was effectively unreadable. Altair sorts a line by its X encoding
unless given `order`, and RMSE is not monotonic in depth (0.40 surface, 1.19 at 50 m, 1.08 at
75 m, 1.22 at 100 m), so the line was drawn in ascending-RMSE order. Nothing failed; it just
looked like an unstable model.

A chart bug that produces a plausible-looking picture is exactly the class this project tests for
everywhere else, so it is tested here too.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

pytest.importorskip("altair")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def page():
    return _load("tscast_page_chart", "app/phase2/tscast_page.py")


DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
#: The shipped per-depth numbers. Climatology WINS at 1000 m (0.293 vs 0.305) -- kept in the
#: fixture on purpose so the crossover path is the one under test.
RMSE = [0.403, 0.468, 0.523, 0.780, 0.973, 1.187, 1.084, 1.218,
        1.201, 1.063, 1.030, 0.986, 0.585, 0.406, 0.305]
CLIM = [0.750, 1.004, 0.994, 1.129, 1.308, 1.295, 1.320, 1.550,
        1.628, 1.530, 1.592, 1.268, 0.642, 0.432, 0.293]


def _labels(spec: dict) -> list[str]:
    """Every text label in the chart. Altair hoists layer data into top-level `datasets` and
    references it by name, so reading `layer[i].data.values` alone finds nothing."""
    out = []
    for rows in (spec.get("datasets") or {}).values():
        for v in rows:
            if isinstance(v, dict) and "label" in v:
                out.append(v["label"])
    for layer in spec.get("layer", []):
        for v in (layer.get("data", {}).get("values") or []):
            if isinstance(v, dict) and "label" in v:
                out.append(v["label"])
    return out


def _line_layer(spec: dict) -> dict:
    for layer in spec["layer"]:
        mark = layer.get("mark")
        if (mark.get("type") if isinstance(mark, dict) else mark) == "line":
            return layer
    raise AssertionError("no line layer in the chart")


def test_the_line_follows_depth_not_ascending_rmse(page):
    """THE REGRESSION. Without `order`, altair connects points in ascending-x (RMSE) order and the
    profile crosses itself."""
    spec = page._depth_error_chart(DEPTHS, RMSE, CLIM).to_dict()
    enc = _line_layer(spec)["encoding"]
    assert "order" in enc, "line has no `order` -- it will be drawn in ascending-RMSE order"
    assert enc["order"]["field"] == "depth"


def test_depth_axis_increases_downward(page):
    """Oceanographic convention. A depth axis running upward misreads at a glance."""
    enc = _line_layer(page._depth_error_chart(DEPTHS, RMSE, CLIM).to_dict())["encoding"]
    assert enc["y"]["scale"]["reverse"] is True


def test_the_one_depth_climatology_wins_is_labelled(page):
    """The model beats climatology at 14 of 15 depths, not 15. The exception must be on the chart,
    not left for a jury to find in the table."""
    spec = page._depth_error_chart(DEPTHS, RMSE, CLIM).to_dict()
    texts = _labels(spec)
    assert any("climatology wins" in t for t in texts), texts

    # ...and when the model really does win everywhere, that label must NOT appear.
    clean = page._depth_error_chart(DEPTHS, RMSE, [c + 1.0 for c in CLIM]).to_dict()
    texts_clean = _labels(clean)
    assert not any("climatology wins" in t for t in texts_clean), texts_clean


def test_annotation_ink_is_not_the_vega_default_black(page):
    """Streamlit themes AXIS text but not free `mark_text`, which defaults to black. Measured on
    the running page: rgb(0,0,0) on rgb(14,17,23) -- 1.11:1, invisible. No theme is pinned, so the
    ink must be legible on BOTH surfaces."""
    assert page.INK_ANNOTATION.lower() not in ("#000", "#000000", "black")

    def contrast(hex_a: str, hex_b: str) -> float:
        def lum(h):
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
        a, b = lum(hex_a), lum(hex_b)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)

    for surface in ("#fcfcfb", "#0e1117"):          # streamlit light and dark
        assert contrast(page.INK_ANNOTATION, surface) >= 3.0, surface


def test_both_pages_order_their_depth_lines():
    """validation_page carried the identical defect in both of its panels."""
    src = open(os.path.join(ROOT, "app/phase2/validation_page.py"), encoding="utf-8").read()
    start = src.index("def _chart_per_depth")
    body = src[start:src.index("\ndef ", start + 10)]
    assert body.count('alt.Order("depth:Q")') == 2, "both panels need an explicit line order"


# --------------------------------------------------------------------------- the Argo overlay


@pytest.fixture(scope="module")
def overlay_page():
    return _load("validate_page_chart", "app/phase2/validate_page.py")


#: A profile with a temperature INVERSION -- warmer water beneath cooler. Not a contrived case:
#: 67.1% of the 11,832 ocean profiles on 2026-05-15 contain one, because barrier-layer inversions
#: are a real feature of this basin. On such a column a line sorted by temperature crosses itself.
INVERTED = [30.35, 30.36, 30.32, 30.52, 30.48, 29.96, 28.63,
            26.99, 24.57, 21.71, 17.27, 13.36, 11.40, 10.03, 7.86]
BAND = {"lo": [v - 1.0 for v in INVERTED], "hi": [v + 1.0 for v in INVERTED]}
FLOAT = [v + 0.3 for v in INVERTED]


def test_overlay_line_follows_depth_not_temperature(overlay_page):
    """Same defect class as the benchmark chart. It looks fine on a monotonically cooling column
    and breaks on the two-thirds of profiles that carry an inversion."""
    spec = overlay_page._overlay_chart(DEPTHS, INVERTED, BAND, FLOAT).to_dict()
    enc = _line_layer(spec)["encoding"]
    assert "order" in enc, "overlay line has no `order` -- it follows temperature, not depth"
    assert enc["order"]["field"] == "depth"
    assert enc["y"]["scale"]["reverse"] is True


def test_overlay_has_a_legend_naming_both_series(overlay_page):
    """It had none: three visual elements explained only by the title. A jury should not have to
    infer that the orange dots are the ground truth."""
    spec = overlay_page._overlay_chart(DEPTHS, INVERTED, BAND, FLOAT).to_dict()
    coloured = [L for L in spec["layer"] if "color" in L.get("encoding", {})]
    assert len(coloured) >= 2, "line and float must both carry the colour encoding that legends it"
    domain = coloured[0]["encoding"]["color"]["scale"]["domain"]
    assert overlay_page.NAME_MODEL in domain and overlay_page.NAME_FLOAT in domain


def test_the_float_is_not_drawn_in_alarm_red(overlay_page):
    """It was #d62728. The float is ground truth -- the thing that validates the model, not a
    fault -- and red told a jury the opposite."""
    assert overlay_page.CLR_FLOAT.lower() not in ("#d62728", "#ff0000", "red")
    assert overlay_page.CLR_MODEL != overlay_page.CLR_FLOAT


def test_overlay_labels_the_largest_disagreement(overlay_page):
    """The weakest depth is pointed at, not left to be found."""
    spec = overlay_page._overlay_chart(DEPTHS, INVERTED, BAND, FLOAT).to_dict()
    assert any("largest gap" in t for t in _labels(spec)), _labels(spec)


def test_both_jury_charts_share_one_colour_language(overlay_page, page):
    """Blue is always our model; orange is always what we are measured against. Two demo pages
    using different blues for 'us' would read as two different systems."""
    assert overlay_page.CLR_MODEL == page.CLR_MODEL
    assert overlay_page.CLR_FLOAT == page.CLR_CLIM
    assert overlay_page.INK_ANNOTATION == page.INK_ANNOTATION
