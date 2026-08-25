"""Unit C tests for the four Streamlit panels. Owner: Mitun + Niru.

Panels are what a judge actually looks at, so these RENDER them through Streamlit's AppTest
harness rather than only importing them. A panel that imports fine and throws on render is
exactly the failure that shows up on stage.

Every case feeds data the panels will genuinely meet: land points, missing climatology, absent
ARGO, an all-NaN priority grid, and no logged experiment run.
"""
from __future__ import annotations

import textwrap

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from oceanembed import config

D = config.N_DEPTHS
H, W = config.N_LAT, config.N_LON

PRELUDE = """
import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('src'))
import numpy as np, pandas as pd
"""


def types_of(at: AppTest) -> dict:
    """Element-type counts. AppTest exposes no typed accessor for charts/images."""
    counts: dict = {}
    for e in at.main:
        counts[type(e).__name__] = counts.get(type(e).__name__, 0) + 1
    return counts


def n_charts(at: AppTest) -> int:
    return types_of(at).get("UnknownElement", 0)


def n_images(at: AppTest) -> int:
    return types_of(at).get("Image", 0)


def run(body: str, timeout: int = 60) -> AppTest:
    """Run a snippet as a Streamlit app; fail loudly if the panel raised."""
    at = AppTest.from_string(textwrap.dedent(PRELUDE + body), default_timeout=timeout)
    at.run()
    assert not at.exception, f"panel raised: {[str(e) for e in at.exception]}"
    return at


RECON = """
from app.panels.profile_panel import render
depths = np.array({depths}, dtype='float32')
mean = np.linspace(28.5, 9.0, len(depths)).astype('float32')
std  = np.linspace(0.26, 0.05, len(depths)).astype('float32')
out = dict(lat=15.0, lon=88.0, date='2022-06-15', is_land={is_land},
           depths=list(depths), profile_mean={mean}, profile_std={std},
           reliability=['high']*len(depths), climatology={clim}, anomaly=None,
           surface=dict(sst=28.5, sss=34.0, ssh=0.1, u=0.2, v=-0.1))
render(out, argo_df={argo})
"""


def _recon(is_land="False", clim="mean - 0.4", argo="None",
           mean="mean", std="std") -> str:
    return RECON.format(depths=list(config.DEPTHS), is_land=is_land, clim=clim,
                        argo=argo, mean=mean, std=std)


# --- profile panel ----------------------------------------------------------
def test_profile_renders_a_chart():
    at = run(_recon())
    assert n_charts(at) >= 1, "expected an altair chart"


def test_profile_handles_a_land_point_without_crashing():
    at = run(_recon(is_land="True", mean="None", std="None"))
    assert len(at.info) >= 1, "land points should explain themselves, not render an empty chart"


def test_profile_survives_missing_climatology():
    run(_recon(clim="None"))


def test_profile_overlays_a_nearby_argo_profile():
    argo = ("pd.DataFrame({'lat':[15.05]*len(depths),'lon':[88.05]*len(depths),"
            "'depth_idx':list(range(len(depths))),'temp':(mean+0.3).tolist()})")
    at = run(_recon(argo=argo))
    assert any("ARGO" in c.value for c in at.caption), "nearby ARGO should be reported in the caption"


def test_profile_says_so_when_no_argo_is_nearby():
    argo = "pd.DataFrame({'lat':[-20.0],'lon':[20.0],'depth_idx':[0],'temp':[5.0]})"
    at = run(_recon(argo=argo))
    assert any("no ARGO" in c.value for c in at.caption)


def test_profile_warns_that_narrowing_sigma_is_not_confidence():
    """D-016: the band narrows with depth; a reader must not take that as certainty."""
    at = run(_recon())
    assert any("D-016" in c.value or "overconfident" in c.value for c in at.caption), (
        "a narrowing uncertainty band must carry the D-016 caveat"
    )


# --- map panel --------------------------------------------------------------
GRID = """
from app.panels.map_panel import render
H, W, D = {H}, {W}, {D}
rng = np.random.default_rng(0)
temp = (np.linspace(28, 9, D)[None, None, :] + rng.normal(0, .5, (H, W, D))).astype('float32')
land = np.zeros((H, W), bool); land[80:, :40] = True
temp[land] = np.nan
g = dict(date='2022-06-15', temp=temp, land_mask=land,
         uncertainty={unc}, anomaly={anom}, priority={prio})
render(g)
"""


def test_map_renders_temperature():
    at = run(GRID.format(H=H, W=W, D=D, unc="None", anom="None", prio="None"))
    assert n_images(at) >= 1, "expected a rendered map image"


def test_map_offers_anomaly_and_uncertainty_layers_when_present():
    at = run(GRID.format(H=H, W=W, D=D,
                         unc="np.abs(rng.normal(.2,.05,(H,W,D))).astype('float32')",
                         anom="rng.normal(0,.8,(H,W,D)).astype('float32')", prio="None"))
    labels = at.radio[0].options
    assert any("Anomaly" in o for o in labels) and any("Uncertainty" in o for o in labels)


def test_map_land_is_not_coloured_as_data():
    """Land painted from the temperature scale would read as a real (wrong) measurement."""
    from app.panels._viz import LAND_RGB, colorize
    field = np.linspace(9, 28, H * W).reshape(H, W).astype("float32")
    land = np.zeros((H, W), bool)
    land[:20, :30] = True
    field[land] = np.nan
    img = colorize(field, land_mask=land)
    assert tuple(img[-1, 0]) == LAND_RGB, "land must be painted the reserved grey"


def test_map_is_north_up():
    """Row 0 of our arrays is the SOUTHERNMOST latitude; images draw row 0 at the top."""
    from app.panels._viz import colorize
    field = np.zeros((H, W), dtype="float32")
    field[-1, :] = 100.0                      # northernmost row is hottest
    img = colorize(field, robust=False)
    assert img[0, 0].sum() > img[-1, 0].sum(), "north must appear at the top of the image"


# --- priority panel ---------------------------------------------------------
PRIO = """
from app.panels.priority_panel import render
H, W, D = {H}, {W}, {D}
land = np.zeros((H, W), bool); land[80:, :40] = True
prio = {prio}
g = dict(date='2022-06-15', temp=np.zeros((H,W,D),'float32'), land_mask=land, priority=prio)
render(g)
"""


def test_priority_renders_and_lists_locations():
    at = run(PRIO.format(H=H, W=W, D=D,
                         prio="np.random.default_rng(0).random((H,W)).astype('float32')"))
    assert n_images(at) >= 1
    assert len(at.dataframe) >= 1, "expected a top-K location table"


def test_priority_absent_is_explained_not_crashed():
    at = run(PRIO.format(H=H, W=W, D=D, prio="None"))
    assert len(at.info) >= 1


def test_priority_all_nan_is_explained_not_shown_as_a_map():
    """All-NaN means nothing could be ranked -- showing a map would imply a result."""
    at = run(PRIO.format(H=H, W=W, D=D, prio="np.full((H,W), np.nan, 'float32')"))
    assert len(at.warning) >= 1
    assert n_images(at) == 0, "an unrankable grid must not be drawn as a map"


def test_priority_copy_never_claims_deployment_authority():
    at = run(PRIO.format(H=H, W=W, D=D,
                         prio="np.random.default_rng(1).random((H,W)).astype('float32')"))
    text = " ".join(m.value for m in at.markdown).lower()
    assert "may add scientific value" in text or "may provide high scientific value" in text
    assert "not a deployment recommendation" in text
    for banned in ("tells moes", "where to deploy", "should deploy"):
        assert banned not in text, f"copy claims deployment authority: {banned!r}"


def test_top_k_picks_separated_locations_not_one_blob():
    from app.panels.priority_panel import _top_k
    p = np.zeros((H, W), dtype="float32")
    p[50, 100] = 1.0                       # one hot blob
    p[48:53, 98:103] = 0.99
    p[20, 200] = 0.98                      # a genuinely separate site
    picked = _top_k(p, k=2)
    assert len(picked) == 2
    lat_gap = abs(picked["lat (°N)"].iloc[0] - picked["lat (°N)"].iloc[1])
    lon_gap = abs(picked["lon (°E)"].iloc[0] - picked["lon (°E)"].iloc[1])
    assert max(lat_gap, lon_gap) > 1.0, "top-K returned neighbouring cells of the same blob"


# --- validation panel -------------------------------------------------------
def test_validation_says_nothing_rather_than_inventing_numbers(tmp_path):
    missing = tmp_path / "no_such_EXPERIMENT_LOG.md"
    at = run(f"""
from app.panels import validation_panel
validation_panel.LOG_PATH = r'{missing}'
validation_panel.render()
""")
    assert len(at.info) >= 1, "with no logged run the panel must say so, not show placeholders"


def test_validation_renders_a_metrics_dict():
    at = run("""
from app.panels.validation_panel import render
from oceanembed import config
render(dict(rmse=0.21, mae=0.17, r2=0.999, skill_vs_clim=0.85,
            rmse_by_depth=[0.2]*config.N_DEPTHS, r2_by_depth=[0.4]*config.N_DEPTHS))
""")
    assert len(at.metric) >= 3
    assert n_charts(at) >= 1, "expected the per-depth error chart"


def test_validation_flags_a_synthetic_run(tmp_path):
    log = tmp_path / "EXPERIMENT_LOG.md"
    log.write_text(
        "## slice 2026-08-25 12:37\n"
        "model: MLPProfile | dataset: SYNTHETIC (illustrative) | split: t | seed: 42\n"
        "metrics: RMSE=0.156 MAE=0.118 R2=0.999 skill_vs_clim=+0.369\n",
        encoding="utf-8")
    at = run(f"""
from app.panels import validation_panel
validation_panel.LOG_PATH = r'{log}'
validation_panel.render()
""")
    assert len(at.error) >= 1, "a synthetic run must be flagged, loudly"
    assert any("SYNTHETIC" in e.value for e in at.error)


def test_validation_caveats_a_high_pooled_r2(tmp_path):
    """R2=0.999 sits on a ~0.95 floor climatology already reaches -- the panel must say so."""
    log = tmp_path / "EXPERIMENT_LOG.md"
    log.write_text(
        "## run 2026-08-25 12:00\n"
        "model: MLPProfile | dataset: real-glorys | seed: 42\n"
        "metrics: RMSE=0.156 MAE=0.118 R2=0.999 skill_vs_clim=+0.369\n",
        encoding="utf-8")
    at = run(f"""
from app.panels import validation_panel
validation_panel.LOG_PATH = r'{log}'
validation_panel.render()
""")
    assert any("climatology alone" in c.value for c in at.caption), (
        "a high pooled R2 must carry the inflation caveat"
    )
