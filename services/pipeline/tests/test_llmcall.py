"""`pipeline.llmcall` and `pipeline.llmcache`, driven by a stub client (no network).

These are the behaviours that make a $0 key usable for a 917-document pass: a transient failure
retries instead of aborting the run, a model without JSON mode still gets used, and a question
that was already answered is never asked twice.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.config import LlmSettings
from pipeline.llmcache import ResponseCache, cache_for, combined_stats, reset_caches
from pipeline.llmcall import (
    ModelCallFailed,
    backoff_seconds,
    complete_json,
    is_retryable,
    new_client,
    rejects_json_mode,
)

MESSAGES = [{"role": "user", "content": "answer in json"}]
PAYLOAD = {"answer": "ok", "checks": ["a"]}


class _Completions:
    """Returns the scripted items in order; an Exception item raises."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        item = self.items[min(len(self.requests) - 1, len(self.items) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def stub_client(items: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions(items)))


def _response(content: str, model: str = "stub-1") -> SimpleNamespace:
    return SimpleNamespace(
        model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _ok(model: str = "stub-1") -> SimpleNamespace:
    return _response(json.dumps(PAYLOAD), model)


class APIConnectionError(Exception):
    """Named like the openai transport error, which is how `llmcall` recognises it."""


class StatusError(Exception):
    def __init__(self, message: str, status_code: int, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {})


def _settings(**overrides: Any) -> LlmSettings:
    values: dict[str, Any] = {
        "base_url": "http://stub.test/v1",
        "api_key": "test-key",
        "model": "stub-model",
        "timeout_seconds": 1,
        "max_retries": 2,
        "cache_enabled": False,
    }
    return LlmSettings(**{**values, **overrides})


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    reset_caches()
    yield
    reset_caches()


@pytest.mark.parametrize(
    "exc,expected",
    [
        (APIConnectionError("reset"), True),
        (StatusError("slow down", 429), True),
        (StatusError("bad gateway", 502), True),
        (StatusError("invalid api key", 401), False),
        (StatusError("no such model", 404), False),
        (ValueError("programmer error"), False),
    ],
)
def test_only_failures_that_could_clear_themselves_are_retried(
    exc: Exception, expected: bool
) -> None:
    assert is_retryable(exc) is expected


def test_json_mode_rejection_is_recognised_from_a_400_that_names_it() -> None:
    assert rejects_json_mode(StatusError("'response_format' is not supported", 400)) is True
    assert rejects_json_mode(StatusError("temperature out of range", 400)) is False


def test_backoff_grows_and_is_capped() -> None:
    settings = _settings(backoff_base_seconds=2.0, backoff_cap_seconds=5.0)
    assert backoff_seconds(1, settings) == 2.0
    assert backoff_seconds(2, settings) == 4.0
    assert backoff_seconds(9, settings) == 5.0


def test_a_transient_failure_retries_and_reports_the_wait() -> None:
    client = stub_client([APIConnectionError("connection reset"), _ok()])
    delays: list[float] = []

    result = complete_json(
        _settings(), messages=MESSAGES, component="probe", client=client,
        sleeper=delays.append, rng=lambda: 0.0,
    )

    assert result.value == PAYLOAD and result.attempts == 2
    assert len(delays) == 1 and delays[0] > 0


def test_a_rate_limit_wait_told_to_us_by_the_server_is_honoured() -> None:
    limited = StatusError("too many requests", 429, headers={"retry-after": "9"})
    client = stub_client([limited, _ok()])
    delays: list[float] = []

    complete_json(
        _settings(backoff_cap_seconds=100.0), messages=MESSAGES, component="probe",
        client=client, sleeper=delays.append, rng=lambda: 0.0,
    )

    assert delays == [9.0]


def test_a_request_the_server_rejects_never_retries() -> None:
    client = stub_client([StatusError("invalid api key", 401)])

    with pytest.raises(ModelCallFailed, match="LLM call failed") as caught:
        complete_json(_settings(), messages=MESSAGES, component="probe", client=client)

    assert caught.value.kind == "transport"
    assert len(client.chat.completions.requests) == 1


def test_a_model_without_json_mode_is_asked_again_without_it() -> None:
    refused = StatusError("400 response_format json_object is not supported here", 400)
    client = stub_client([refused, _ok()])
    delays: list[float] = []

    result = complete_json(
        _settings(), messages=MESSAGES, component="probe", client=client,
        sleeper=delays.append, rng=lambda: 0.0,
    )

    assert result.json_mode is False
    assert "response_format" in client.chat.completions.requests[0]
    assert "response_format" not in client.chat.completions.requests[1]


def test_unusable_answers_exhaust_the_documented_attempt_budget() -> None:
    client = stub_client([_response("prose, not json")])

    with pytest.raises(ModelCallFailed, match="unusable probe payload") as caught:
        complete_json(
            _settings(max_retries=2), messages=MESSAGES, component="probe", client=client,
            sleeper=lambda _: None,
        )

    assert caught.value.kind == "payload"
    assert len(client.chat.completions.requests) == 3


def test_no_key_means_no_client_rather_than_a_hang() -> None:
    with pytest.raises(RuntimeError, match="LLM_API_KEY is not set"):
        new_client(LlmSettings(base_url=None, api_key=None, model="m"))


def test_an_answered_request_is_served_from_disk_without_calling_again(tmp_path: Path) -> None:
    settings = _settings(cache_enabled=True, cache_dir=tmp_path / "cache")
    client = stub_client([_ok(), _ok()])

    first = complete_json(settings, messages=MESSAGES, component="probe", client=client)
    second = complete_json(settings, messages=MESSAGES, component="probe", client=client)

    assert first.cached is False and second.cached is True
    assert len(client.chat.completions.requests) == 1
    assert second.value == PAYLOAD and second.model == "stub-model"
    assert combined_stats()["hits"] == 1 and combined_stats()["writes"] == 1


def test_a_different_model_never_reads_another_models_answer(tmp_path: Path) -> None:
    settings = _settings(cache_enabled=True, cache_dir=tmp_path / "cache")
    client = stub_client([_ok("first"), _ok("second")])

    complete_json(settings, messages=MESSAGES, component="probe", client=client)
    other = complete_json(
        replace(settings, model="other-model"),
        messages=MESSAGES,
        component="probe",
        client=client,
    )

    assert other.model == "second" and len(client.chat.completions.requests) == 2


def test_a_corrupt_cache_entry_reads_as_a_miss(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    cache = cache_for(_settings(cache_enabled=True, cache_dir=directory))
    key = ResponseCache.key_of(
        model="m", messages=list(MESSAGES), json_mode=True, temperature=0
    )
    directory.mkdir(parents=True)
    cache.path_for(key).write_text("{ not json", encoding="utf-8")

    assert cache.get(key) is None
    assert cache.stats.errors == 1 and cache.stats.misses == 0


def test_an_unwritable_cache_degrades_the_call_instead_of_failing_it(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where a directory belongs", encoding="utf-8")
    settings = _settings(cache_enabled=True, cache_dir=blocker / "cache")
    client = stub_client([_ok()])

    result = complete_json(settings, messages=MESSAGES, component="probe", client=client)

    assert result.value == PAYLOAD and result.cached is False
