"""The one place that talks to an OpenAI-compatible endpoint.

Extraction and adjudication both used to carry their own copy of this loop, and both aborted
on the first transport error: one HTTP 429 from a rate-limited key ended a 917-document eval
pass with nothing written. Here a transport failure backs off and retries, a model that
refuses `response_format: json_object` is retried without it, and successful responses go
through the disk cache (`pipeline.llmcache`) so a re-run only pays for what it is missing.

The attempt budget is unchanged: `max_retries + 1` calls per document. Falling back out of
JSON mode costs one of those attempts rather than adding one, so a model that lacks JSON mode
cannot make a run longer than the documented behaviour.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import ValidationError

from pipeline.config import LlmSettings
from pipeline.llmcache import cache_for

T = TypeVar("T")

# Statuses that mean "the request never got answered", so asking again is legitimate.
RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# openai and httpx error classes, matched by name so this module imports neither.
RETRYABLE_ERROR_NAMES = frozenset(
    {
        "APIConnectionError",
        "APIConnectionClosedError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "InternalServerError",
        "PoolTimeout",
        "RateLimitError",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
    }
)

# A 400 that names response_format is the model telling us it has no JSON mode, not that the
# request is wrong. Retrying it without JSON mode is what makes most free-tier models usable.
JSON_MODE_MARKERS = ("response_format", "json_object", "json mode")

PARSE_ERRORS = (json.JSONDecodeError, ValidationError, AttributeError, TypeError, ValueError)


class EndpointNotConfigured(RuntimeError):
    """No API key, so no model call is possible."""


class ModelCallFailed(RuntimeError):
    """The endpoint stayed unreachable, or only ever answered with something unusable.

    `kind` is "transport" or "payload", which is what lets each component keep its own
    established error wording instead of string-matching this one.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class CallResult:
    """One settled model call: the parsed value plus the bookkeeping the report carries."""

    value: Any
    model: str
    latency_ms: int
    attempts: int
    cached: bool
    json_mode: bool


def new_client(settings: LlmSettings) -> Any:
    """Build the SDK client. Raises before any network attempt if the key is absent."""
    if not settings.enabled:
        raise EndpointNotConfigured("LLM_API_KEY is not set")
    from openai import OpenAI

    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def retry_after_seconds(exc: BaseException) -> float | None:
    """A `Retry-After` header beats our own backoff, because the server said when to return."""
    headers: Mapping[str, Any] = getattr(getattr(exc, "response", None), "headers", {}) or {}
    raw = headers.get("retry-after")
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def is_retryable(exc: BaseException) -> bool:
    if type(exc).__name__ in RETRYABLE_ERROR_NAMES:
        return True
    return status_of(exc) in RETRYABLE_STATUSES


def rejects_json_mode(exc: BaseException) -> bool:
    if status_of(exc) != 400:
        return False
    text = str(exc).lower()
    return any(marker in text for marker in JSON_MODE_MARKERS)


def backoff_seconds(
    attempt: int, settings: LlmSettings, *, jitter: float = 0.0, forced: float | None = None
) -> float:
    """Exponential and capped; a server's `Retry-After` wins when it is the longer wait."""
    base = settings.backoff_base_seconds * (2 ** max(0, attempt - 1))
    delay = min(settings.backoff_cap_seconds, max(base, forced or 0.0))
    return delay + delay * 0.25 * max(0.0, min(1.0, jitter))


def message_content(response: Any) -> str:
    """The assistant message text, for both chat and JSON-mode shaped replies."""
    return response.choices[0].message.content


def _content_of(response: Any) -> tuple[str, str | None]:
    try:
        return message_content(response), None
    except (AttributeError, IndexError, TypeError) as exc:
        return "", str(exc)


def _parse(content: str, parse: Callable[[str], Any] | None) -> tuple[Any, str | None]:
    """The value, or the reason there is none. No `parse` still means the reply must be JSON."""
    try:
        return (parse(content) if parse is not None else json.loads(content)), None
    except PARSE_ERRORS as exc:
        return None, f"{type(exc).__name__}: {exc}"


def complete_json(
    settings: LlmSettings,
    *,
    messages: Sequence[dict[str, Any]],
    component: str,
    parse: Callable[[str], T] | None = None,
    client: Any | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> CallResult:
    """Ask for one JSON object and hand back the parsed value, or raise `ModelCallFailed`.

    `parse` turns the message text into a typed value; when it raises, the attempt counts as
    unusable and the loop asks again. With no `parse`, the reply is validated as plain JSON.
    """
    cache = cache_for(settings)
    http = client if client is not None else new_client(settings)
    json_mode = True
    last_error = "no response"
    forced_delay: float | None = None

    for attempt in range(1, settings.max_retries + 2):
        if attempt > 1:
            sleeper(backoff_seconds(attempt - 1, settings, jitter=rng(), forced=forced_delay))
            forced_delay = None
        key = cache.key_of(
            model=settings.model, messages=list(messages), json_mode=json_mode, temperature=0
        )
        hit = cache.get(key)
        if hit is not None:
            value, error = _parse(hit, parse)
            if error is None:
                return CallResult(
                    value=value,
                    model=settings.model,
                    latency_ms=0,
                    attempts=attempt,
                    cached=True,
                    json_mode=json_mode,
                )
            last_error = error
            continue

        kwargs = {"model": settings.model, "messages": list(messages), "temperature": 0}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            response = http.chat.completions.create(**kwargs)
        except Exception as exc:  # openai raises many unrelated error types
            if rejects_json_mode(exc):
                json_mode = False
                continue
            if is_retryable(exc):
                last_error = str(exc)
                forced_delay = retry_after_seconds(exc)
                continue
            raise ModelCallFailed(f"LLM call failed: {exc}", kind="transport") from exc

        latency_ms = int(round((time.perf_counter() - started) * 1000))
        content, read_error = _content_of(response)
        if read_error is not None:
            last_error = read_error
            continue

        cache.put(key, content=content, model=settings.model)
        value, parse_error = _parse(content, parse)
        if parse_error is not None:
            last_error = parse_error
            continue

        return CallResult(
            value=value,
            model=getattr(response, "model", None) or settings.model,
            latency_ms=latency_ms,
            attempts=attempt,
            cached=False,
            json_mode=json_mode,
        )

    raise ModelCallFailed(f"unusable {component} payload ({last_error})", kind="payload")
