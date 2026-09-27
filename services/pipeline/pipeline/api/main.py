"""FastAPI application entry point.

Only /healthz exists at this stage; contract routes arrive with prompt A7.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Sewa Setu Pipeline", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
