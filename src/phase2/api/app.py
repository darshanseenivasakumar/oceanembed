"""FastAPI adapter over `service.py`. A thin shell -- no decisions live here. (Unit A / Arjhun.)

    PYTHONPATH=src python -m uvicorn phase2.api.app:app --host 127.0.0.1 --port 8511 --workers 1

`--workers 1` and `127.0.0.1` are both deliberate:

  * each worker loads a checkpoint plus a ~485 MB bundle, and the lock in `service.py` does not span
    processes -- a second worker would be a second predictor with its own unsynchronised `ds.index`
  * this is an unauthenticated model server on a demo laptop; binding 0.0.0.0 on a venue network
    gains nothing and exposes it to the room

EVERY HANDLER IS `def`, NOT `async def`. FastAPI runs a sync handler in its threadpool; an async one
calling `predict_field` would block the event loop for ~32 seconds (measured -- see
`artifacts/export_timing.json`). `tests/phase2/test_api_http.py` asserts `async def` never appears.
"""
from __future__ import annotations

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

from phase2.api import service


def _default_predictor():
    from phase2.tscast_nio.inference import TSCastPredictor
    return TSCastPredictor()


def build_app(predictor_factory=None) -> FastAPI:
    """The app, with the predictor injectable.

    The seam exists for the tests: a fake predictor lets the HTTP layer be exercised in seconds with
    no checkpoint and no 485 MB bundle, so the route behaviour is covered on any machine.
    """
    factory = predictor_factory or _default_predictor
    api = FastAPI(
        title="OceanEmbed — subsurface temperature from satellite observations",
        version="2.0",
        description=("Reconstructs temperature at 15 standard depths over the North Indian Ocean "
                     "from surface satellite observations. Dates outside the reconstruction "
                     "bundle are refused, not approximated — see /coverage."),
    )
    state: dict = {}

    def predictor():
        if "p" not in state:                     # loaded once, on first use, not at import
            state["p"] = factory()
        return state["p"]

    def _json(pair):
        status, payload = pair
        return JSONResponse(status_code=status, content=payload)

    @api.get("/health", summary="Is the model loaded, and which one")
    def health():
        return _json(service.health(predictor()))

    @api.get("/coverage", summary="Which dates this deployment can answer for")
    def coverage():
        return _json(service.coverage(predictor()))

    @api.get("/profile", summary="One reconstructed profile with its uncertainty")
    def profile(lat: float = Query(..., ge=-90, le=90),
                lon: float = Query(..., ge=-180, le=360),
                date: str = Query(..., description="YYYY-MM-DD, inside the bundle")):
        return _json(service.profile(predictor(), lat, lon, date))

    @api.get("/field.nc", summary="The whole reconstructed field for one date, as NetCDF")
    def field_nc(date: str = Query(..., description="YYYY-MM-DD, inside the bundle")):
        status, payload = service.field_netcdf_bytes(predictor(), date)
        if status != 200:
            return JSONResponse(status_code=status, content=payload)
        return Response(
            content=payload, media_type="application/x-netcdf",
            headers={"Content-Disposition": f'attachment; filename="oceanembed_{date}.nc"'})

    return api


app = build_app()
