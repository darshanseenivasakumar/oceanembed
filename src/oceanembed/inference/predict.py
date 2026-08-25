"""THE integration seam: one public reconstruct() that ties A's model + C's climatology/anomaly + A's priority.

OWNER: Unit B (Darshan). Consumes frozen signatures from A and C (imported lazily so the repo imports even
while those are still stubs). Returns the frozen output dict used by app/panels.
"""
from __future__ import annotations
import numpy as np
from oceanembed import config


def reconstruct(lat: float, lon: float, date) -> dict:
    """Single-point reconstruction.

    Returns {depths[11], profile_mean[11], profile_std[11], reliability[11], anomaly[11], argo[11|None]}.
    """
    # lazy imports keep the package importable before A/C implement their modules
    # from oceanembed.models.mlp_profile import load_mlp, predict_mlp
    # from oceanembed.inference.uncertainty import mc_dropout_predict
    # from oceanembed.climatology import climatology_predict
    # from oceanembed.products.anomaly import anomaly
    raise NotImplementedError("Unit B (Day 4): assemble X for the cell/date, call model+uncertainty+climatology+anomaly.")


def reconstruct_grid(date) -> dict:
    """Whole-grid reconstruction for maps.

    Returns {temp(100,240,11), uncertainty(100,240,11), anomaly(100,240,11), priority(100,240)}.
    """
    raise NotImplementedError("Unit B (Day 4): batch over all cells; call observation_priority for the priority map.")
