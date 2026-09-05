"""HTTP surface for the shipped reconstruction. (Unit A / Arjhun.)

`service.py` holds every decision and imports no web framework; `app.py` is a thin adapter. That
split exists so the framework is replaceable: FastAPI is used for its OpenAPI page, but starlette
alone can serve the same routes if FastAPI ever conflicts with the version Streamlit pins.
"""
