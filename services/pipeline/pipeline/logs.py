"""Structured JSON logging: one object per line on stdout.

Every record carries `ts`, `level`, `logger`, `message` and whatever context the call site
passes. `applicationId` and a check summary are safe to log; `applicantFields` and document
text are not - they are the identity-bearing part of this system even when the data is
synthetic, and a log stream is exactly where that habit slips.

`configure()` is idempotent so importing the package never fights uvicorn's own handlers. Run
the server with `--no-access-log` (see the runbook) because the API middleware already logs
every request as JSON.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

LOGGER_NAME = "pipeline"
_FORMATTER_KEY = "_sewa_setu_json"


class JsonFormatter(logging.Formatter):
    """Renders a record as one JSON object, merging any `extra={"context": {...}}` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(context)
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(level: int | None = None) -> logging.Logger:
    """Attach the JSON handler to the `pipeline` logger once; safe to call repeatedly."""
    logger = logging.getLogger(LOGGER_NAME)
    if level is None:
        level = logging.INFO
    logger.setLevel(level)
    if not any(getattr(handler, _FORMATTER_KEY, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        setattr(handler, _FORMATTER_KEY, True)
        logger.addHandler(handler)
    logger.propagate = False  # never double-print through the root logger's text handler
    return logger


def get_logger(suffix: str) -> logging.Logger:
    """A child logger named `pipeline.<suffix>`; configures on first use."""
    return configure().getChild(suffix)


def _emit(logger: logging.Logger, level: int, message: str, context: dict[str, Any]) -> None:
    if logger.isEnabledFor(level):
        logger.log(level, message, extra={"context": dict(context)})


def event(logger: logging.Logger, message: str, **context: Any) -> None:
    """One INFO line: something worth recording, nothing wrong."""
    _emit(logger, logging.INFO, message, context)


def warning(logger: logging.Logger, message: str, **context: Any) -> None:
    """One WARNING line: a fallback was taken, or a client sent something unusable."""
    _emit(logger, logging.WARNING, message, context)
