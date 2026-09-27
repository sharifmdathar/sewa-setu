"""Contract-consistent error responses.

The frozen contract only describes the success cases (plus two 404s), so every failure is
shaped here instead: an HTTP status, a machine-readable `code`, and a `detail` that is always a
string. Track B can branch on `code` without parsing prose, and no path can answer with a raw
traceback - the catch-all handler turns an unexpected exception into the same envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pipeline.logs import get_logger, warning

LOGGER = get_logger("api.errors")


class ApiError(Exception):
    """An error the client can act on: status + code + a sentence."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail

    @classmethod
    def unknown_service(cls, service_id: str) -> ApiError:
        return cls(400, "unknown_service", f"unknown serviceId '{service_id}'")

    @classmethod
    def unknown_application(cls, application_id: str) -> ApiError:
        return cls(404, "unknown_application", f"application '{application_id}' not found")

    @classmethod
    def scrutiny_not_run(cls, application_id: str) -> ApiError:
        return cls(404, "scrutiny_not_run", f"scrutiny has not been run for '{application_id}'")

    @classmethod
    def documents_required(cls, application_id: str) -> ApiError:
        return cls(
            409,
            "documents_required",
            f"application '{application_id}' has no documents to scrutinize yet",
        )

    @classmethod
    def invalid_document(cls, file_name: str, reason: str) -> ApiError:
        return cls(422, "invalid_document", f"{file_name}: {reason}")


def body(error: ApiError) -> dict[str, Any]:
    return {"detail": error.detail, "code": error.code}


def field_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Pydantic's per-field complaints, named by their path inside the JSON body."""
    return [
        {
            "field": ".".join(
                part for part in (str(step) for step in item.get("loc", ())) if part != "body"
            ),
            "message": str(item.get("msg", "invalid value")),
        }
        for item in exc.errors()
    ]


def install_handlers(app: FastAPI) -> None:
    """Register the envelope handlers; called by `create_app` so tests get them too."""

    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError) -> JSONResponse:
        if exc.status < 500:
            warning(
                LOGGER,
                "request rejected",
                code=exc.code,
                status=exc.status,
                path=request.url.path,
            )
        return JSONResponse(body(exc), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = field_errors(exc)
        first = fields[0]["field"] if fields else "body"
        error = ApiError(
            422, "invalid_request", f"request body did not match the contract ({first})"
        )
        payload = body(error)
        payload["fields"] = fields
        warning(LOGGER, "request rejected", code=error.code, status=422, path=request.url.path)
        return JSONResponse(payload, status_code=422)

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        error = ApiError(500, "internal_error", "the request could not be completed")
        LOGGER.error(
            "unhandled failure",
            extra={"context": {"path": request.url.path}},
            exc_info=exc,
        )
        return JSONResponse(body(error), status_code=500)
