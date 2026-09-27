"""The preflight probe, with its one network call stubbed out.

What matters here is that the probe *reports* correctly: it is the only thing standing between
a free-tier key and a batch run that dies on request 51.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.config import LlmSettings
from pipeline.llmcall import CallResult, ModelCallFailed
from pipeline.scripts import probe_llm


def _settings(**overrides: Any) -> LlmSettings:
    values: dict[str, Any] = {
        "base_url": "http://stub.test/v1",
        "api_key": "test-key",
        "model": "stub-model",
    }
    return LlmSettings(**{**values, **overrides})


def _result(**overrides: Any) -> CallResult:
    values: dict[str, Any] = {
        "value": {"answer": "ok", "checks": []},
        "model": "served-model",
        "latency_ms": 4200,
        "attempts": 1,
        "cached": False,
        "json_mode": True,
    }
    return CallResult(**{**values, **overrides})


def test_no_key_means_the_probe_refuses_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe_llm, "get_llm_settings", lambda: _settings(api_key=None))
    assert probe_llm.main([]) == 2


def test_a_model_that_answers_in_json_is_reported_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe_llm, "complete_json", lambda *a, **k: _result())
    usable, detail, facts = probe_llm.probe_json_mode(_settings())
    assert usable and "4200 ms" in detail and facts["jsonMode"] is True


def test_a_model_that_needed_the_json_mode_fallback_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe_llm, "complete_json", lambda *a, **k: _result(json_mode=False))
    usable, detail, _ = probe_llm.probe_json_mode(_settings())
    assert usable and "without response_format" in detail


def test_a_reply_that_is_not_an_object_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe_llm, "complete_json", lambda *a, **k: _result(value=["prose"]))
    usable, detail, _ = probe_llm.probe_json_mode(_settings())
    assert not usable and "not a JSON object" in detail


def test_a_transport_failure_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_a: Any, **_k: Any) -> CallResult:
        raise ModelCallFailed("LLM call failed: 401 unauthorized", kind="transport")

    monkeypatch.setattr(probe_llm, "complete_json", refuse)
    usable, detail, _ = probe_llm.probe_json_mode(_settings())
    assert not usable and "401" in detail


def test_probes_never_read_or_write_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[LlmSettings] = []

    def record(settings: LlmSettings, **_kwargs: Any) -> CallResult:
        seen.append(settings)
        return _result()

    monkeypatch.setattr(probe_llm, "complete_json", record)
    probe_llm.probe_json_mode(_settings(cache_enabled=True))
    assert seen and seen[0].cache_enabled is False


def test_the_budget_note_shows_how_many_days_a_corpus_pass_needs(capsys: Any) -> None:
    probe_llm.print_budget(applications=200, documents=917)
    printed = capsys.readouterr().out
    assert "917 documents = 917 extraction calls" in printed
    assert "19 day(s) per pass" in printed  # 917 / 50 requests a day, rounded up


def test_a_missing_image_file_stops_before_any_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(probe_llm, "get_llm_settings", lambda: _settings())
    assert probe_llm.main(["--image", str(tmp_path / "absent.png")]) == 2
