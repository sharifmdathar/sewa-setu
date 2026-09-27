"""FastAPI application entry point: the frozen contract surface.

`create_app` takes a store root so tests (and the eval harness) get an isolated instance; the
module-level `app` uses the default `var/` directory that `pipeline.store.jsonstore` documents.

Every request is logged as one JSON line by the middleware below, so run uvicorn with
`--no-access-log` and avoid two lines per call. `PIPELINE_LOG_LEVEL` (debug|info|warning) and
`PIPELINE_VAR_DIR` are read from the environment; see the runbook.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response

from pipeline.api.errors import install_handlers
from pipeline.api.repository import Repository
from pipeline.api.routes import router
from pipeline.logs import configure, event, get_logger

LEVEL_ENV_VAR = "PIPELINE_LOG_LEVEL"
LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
LOGGER = get_logger("api.request")


def log_level() -> int:
    return LEVELS.get(os.environ.get(LEVEL_ENV_VAR, "").strip().lower(), 20)


def create_app(store_root: str | Path | None = None) -> FastAPI:
    """Build the API over a JSON store rooted at `store_root` (default: services/pipeline/var)."""
    configure(log_level())
    app = FastAPI(title="Sewa Setu Pipeline", version="0.1.0")
    app.state.repository = Repository(store_root)
    app.include_router(router)
    install_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.middleware("http")
    async def log_request(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        event(
            LOGGER,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            durationMs=round((time.perf_counter() - started) * 1000, 2),
        )
        return response

    return app


app = create_app()
