"""FastAPI application entry point: the frozen contract surface.

`create_app` takes a store root so tests (and the eval harness) get an isolated instance; the
module-level `app` uses the default `var/` directory that `pipeline.store.jsonstore` documents.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from pipeline.api.repository import Repository
from pipeline.api.routes import router


def create_app(store_root: str | Path | None = None) -> FastAPI:
    """Build the API over a JSON store rooted at `store_root` (default: services/pipeline/var)."""
    app = FastAPI(title="Sewa Setu Pipeline", version="0.1.0")
    app.state.repository = Repository(store_root)
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
