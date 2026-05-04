"""Per-domain ``APIRouter`` modules carved out of the legacy
``app.py`` monolith.

Each module here registers a focused FastAPI router and is included
back into the application via ``app.include_router(...)`` in
``leadgen.adapters.web_api.app``. Goals:

* Keep ``app.py`` to its real responsibilities — startup / lifespan,
  CORS, dependency wiring, mounting routers.
* Group endpoints by domain so navigating the codebase doesn't
  require ``Ctrl-F`` through 9 000 lines.
* Pre-existing import paths (``from leadgen.adapters.web_api.app import
  create_app``) keep working; the split is internal.
"""
