"""Tests for the daily-bundle verifier.

A verifier that passes everything is worse than no verifier, so each test builds a bundle with a
KNOWN defect and asserts it is caught. The defects are the ones that have actually bitten this
project or would be invisible downstream:

  * depth capped so 1000 m is EXTRAPOLATED past the last real level (already happened once)
  * temperature in Kelvin (trains perfectly, wrong by 273 everywhere)
  * depth axis reversed (trains perfectly, inverts the water column)
  * a missing day inside the range (silent discontinuity the model learns through)
  * a forecast product mixed into a reanalysis archive
"""
import subprocess
import sys

import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from oceanembed import config

SCRIPT = "scripts/phase2/verify_daily_bundle.py"
# GLORYS' real discrete levels around the bottom of our range.
GOOD_LEVELS = [0.5, 5.1, 10.5, 21.6, 29.4, 47.4, 77.9, 92.3, 130.7, 155.9, 222.5, 318.1,
               541.1, 763.3, 1062.4]
CAPPED_LEVELS = GOOD_LEVELS[:-3] + [453.9]          # a 520 m cap stops here


def _write(dirpath, dates, levels=GOOD_LEVELS, kelvin=False, reverse=False, attrs=None):
    lat = np.arange(5.0, 30.0, 0.25)
    lon = np.arange(45.0, 105.0, 0.25)
    lev = np.array(levels, dtype="float64")
    if reverse:
        lev = lev[::-1]
    for d in dates:
        # warm surface, cold deep, monotonic
        prof = 29.0 - 25.0 * (1 - np.exp(-np.abs(lev) / 250.0))
        if reverse:
            prof = prof[::-1]
        t = np.broadcast_to(prof, (1, len(lat), len(lon), len(lev))).copy()
        if kelvin:
            t = t + 273.15
        ds = xr.Dataset(
            {v: (("time", "latitude", "longitude", "depth"), t.copy() if v == "thetao"
                  else np.full_like(t, 35.0))
             for v in ("thetao", "so")},
            coords={"time": [np.datetime64(d)], "latitude": lat, "longitude": lon, "depth": lev},
            attrs=attrs or {},
        )
        ds["zos"] = (("time", "latitude", "longitude"), np.zeros((1, len(lat), len(lon))))
        ds["uo"] = ds["thetao"] * 0.0
        ds["vo"] = ds["thetao"] * 0.0
        ds.to_netcdf(dirpath / f"glorys_{d.replace('-', '')}.nc")


def _run(dirpath, full=True):
    cmd = [sys.executable, SCRIPT, "--dir", str(dirpath)] + (["--full"] if full else [])
    p = subprocess.run(cmd, capture_output=True, text=True,
                       env={"PYTHONPATH": "src", "PATH": ""} | dict(__import__("os").environ))
    return p.returncode, p.stdout + p.stderr


DATES = ["2025-06-01", "2025-06-02", "2025-06-03"]


def test_a_good_bundle_is_accepted(tmp_path):
    _write(tmp_path, DATES)
    rc, out = _run(tmp_path)
    assert rc == 0 and "ACCEPTED" in out, out


def test_a_depth_capped_bundle_is_REJECTED(tmp_path):
    """The defect that already bit this project: a 520 m cap stops the data at 453.9 m and every
    500/700/1000 m value in the contract is then extrapolated past the last real level."""
    _write(tmp_path, DATES, levels=CAPPED_LEVELS)
    rc, out = _run(tmp_path)
    assert rc == 1 and "REJECTED" in out
    assert "EXTRAPOLATED" in out and "maximum_depth=1100" in out


def test_kelvin_is_REJECTED(tmp_path):
    """~300 K trains perfectly and is wrong by 273 degrees everywhere."""
    _write(tmp_path, DATES, kelvin=True)
    rc, out = _run(tmp_path)
    assert rc == 1 and "KELVIN" in out


def test_a_reversed_depth_axis_is_REJECTED(tmp_path):
    """Also trains perfectly, and inverts the entire water column."""
    _write(tmp_path, DATES, reverse=True)
    rc, out = _run(tmp_path)
    assert rc == 1 and "REVERSED" in out


def test_a_missing_day_is_REJECTED(tmp_path):
    _write(tmp_path, ["2025-06-01", "2025-06-02", "2025-06-04"])
    rc, out = _run(tmp_path)
    assert rc == 1 and "MISSING DAYS" in out


def test_a_forecast_product_in_a_reanalysis_archive_is_REJECTED(tmp_path):
    _write(tmp_path, DATES, attrs={"title": "GLOBAL ANALYSIS FORECAST PHY"})
    rc, out = _run(tmp_path)
    assert rc == 1 and "forecast" in out.lower()


def test_the_contract_depths_are_read_from_config_not_hardcoded(tmp_path):
    src = open(SCRIPT, encoding="utf-8").read()
    assert "DEPTHS = list(config.DEPTHS)" in src
    assert str(config.DEPTHS) not in src, "contract depths are hardcoded in the verifier"
