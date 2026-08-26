"""F2a -- OceanCube: one reconstructed 3-D volume, with the sea floor enforced.

OWNER: Unit A (Arjhun), transferred from Unit B 2026-08-26.
Schema: `docs/phase2/data-model.md` -- SHARED, change it there first.

    from phase2.cube import OceanCube
    cube = OceanCube.reconstruct("2022-07-15", source="satellite")
    cube.depth_slice(100)          # one level, with coverage
    cube.section(lat=18.0)         # vertical section
    cube.profile(18.0, 88.0)       # one column, sea floor stated
    cube.value_at(26.0, 52.5, 1000)  # raises BelowSeafloorError -- the Persian Gulf is 30 m here
"""
from . import volume  # noqa: F401
from .ocean_cube import BelowSeafloorError, CubeShapeError, OceanCube  # noqa: F401

__all__ = ["OceanCube", "BelowSeafloorError", "CubeShapeError", "volume"]
