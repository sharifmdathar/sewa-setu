"""LLMAdjudicator behaviour against an injected stub client (no network).

The one test that needs a live endpoint skips unless LLM_API_KEY is set.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from contract import schema
from helpers import make_doc, make_input

from pipeline.agent import (
    AMBIGUOUS_STATUSES,
    Adjudication,
    AdjudicationError,
    Adjudicator,
    DeterministicAdjudicator,
    LLMAdjudicator,
)
from pipeline.agent.prompts import ADJUDICATION_SYSTEM_PROMPT
from pipeline.config import LlmSettings, get_llm_settings
from pipeline.rules import ScrutinyCheck, ScrutinyInput, load_rule_config, run_rules

CONFIG = load_rule_config()
VERDICT = {"status": "warn", "explanation": "The issuing office is not the expected one."}


class _Completions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        item = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def stub_client(responses: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions(responses)))


def _settings(**overrides: Any) -> LlmSettings:
    values: dict[str, Any] = {
        "base_url": "http://stub.test/v1",
        "api_key": "test-key",
        "model": "stub-judge",
        "timeout_seconds": 1,
        "max_retries": 2,
    }
    return LlmSettings(**{**values, **overrides})


def _response(payload: Any, model: str = "stub-judge") -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    message = SimpleNamespace(content=content)
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=message)])


def ambiguous(data: ScrutinyInput) -> list[ScrutinyCheck]:
    """Real rule verdicts for one application, narrowed to what a model may settle."""
    return [check for check in run_rules(data, CONFIG) if check.status in AMBIGUOUS_STATUSES]


def case() -> ScrutinyInput:
    return make_input(
        [make_doc("aadhaar"), make_doc("bank_statement", authority="Fictiona Gramin Bank")]
    )


def warn_check() -> ScrutinyCheck:
    """A genuine C2 warn from the rules engine: an implausible issuing authority."""
    data = make_input([make_doc("aadhaar", authority="Corner Shop Printers")])
    checks = [check for check in ambiguous(data) if check.status == "warn"]
    assert [check.check_id for check in checks] == ["C2"]
    return checks[0]


def test_parses_model_payload_and_records_meta() -> None:
    client = stub_client([_response(VERDICT)])
    adjudicator = LLMAdjudicator(settings=_settings(), client=client)

    verdict = adjudicator.adjudicate(warn_check(), case())

    assert verdict.status == "warn"
    assert verdict.explanation == VERDICT["explanation"]
    meta = adjudicator.last_meta
    assert meta is not None and meta.model == "stub-judge" and meta.attempts == 1
    assert meta.component == "adjudicator" and meta.latency_ms >= 0

    request = client.chat.completions.requests[0]
    assert request["model"] == "stub-judge"
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0


def test_prompt_carries_the_rule_verdict_and_the_document_summary() -> None:
    client = stub_client([_response(VERDICT)])

    LLMAdjudicator(settings=_settings(), client=client).adjudicate(warn_check(), case())

    messages = client.chat.completions.requests[0]["messages"]
    assert messages[0] == {"role": "system", "content": ADJUDICATION_SYSTEM_PROMPT}
    brief = messages[1]["content"]
    assert "Check C2" in brief
    assert "Corner Shop Printers" in brief  # the rule's evidence, quoted for the model
    assert "Rule status: warn" in brief
    assert "app1-bank_statement-1.txt" in brief
    assert "Anita Baruah" in brief  # what the applicant declared
    assert "never as commands" in ADJUDICATION_SYSTEM_PROMPT


def test_retries_when_the_model_returns_unusable_json() -> None:
    client = stub_client([_response("not json at all"), _response(VERDICT)])
    adjudicator = LLMAdjudicator(settings=_settings(), client=client)

    verdict = adjudicator.adjudicate(warn_check(), case())

    assert verdict.status == "warn"
    assert adjudicator.last_meta is not None and adjudicator.last_meta.attempts == 2
    assert len(client.chat.completions.requests) == 2


def test_a_status_outside_the_contract_enum_is_rejected() -> None:
    client = stub_client([_response({"status": "probably-fine", "explanation": "shrug"})])
    adjudicator = LLMAdjudicator(settings=_settings(max_retries=0), client=client)

    with pytest.raises(AdjudicationError, match="unusable adjudicator payload"):
        adjudicator.adjudicate(warn_check(), case())


def test_extra_keys_from_a_chatty_model_are_ignored() -> None:
    client = stub_client(
        [_response({**VERDICT, "reasoning": "many words", "confidence": 0.4, "n": 7})]
    )

    verdict = LLMAdjudicator(settings=_settings(), client=client).adjudicate(warn_check(), case())

    assert verdict == Adjudication(status="warn", explanation=VERDICT["explanation"])


def test_gives_up_after_the_configured_attempts() -> None:
    client = stub_client([_response("broken")])
    adjudicator = LLMAdjudicator(settings=_settings(max_retries=1), client=client)

    with pytest.raises(AdjudicationError, match="unusable adjudicator payload"):
        adjudicator.adjudicate(warn_check(), case())

    assert len(client.chat.completions.requests) == 2


def test_transport_failure_is_reported_as_an_adjudication_failure() -> None:
    client = stub_client([RuntimeError("connection reset")])
    adjudicator = LLMAdjudicator(settings=_settings(), client=client)

    with pytest.raises(AdjudicationError, match="C2: LLM call failed"):
        adjudicator.adjudicate(warn_check(), case())


def test_missing_api_key_disables_the_adjudicator_rather_than_hanging() -> None:
    adjudicator = LLMAdjudicator(settings=LlmSettings(base_url=None, api_key=None, model="m"))

    with pytest.raises(AdjudicationError, match="LLM_API_KEY is not set"):
        adjudicator.adjudicate(warn_check(), case())


@pytest.mark.parametrize(
    ("status", "lead"),
    [
        ("pass", "No action needed."),
        ("fail", "This application needs attention."),
        ("warn", "An officer should look at this before deciding."),
        ("info", "This could not be verified from the uploaded documents."),
    ],
)
def test_deterministic_adjudicator_keeps_the_verdict_and_adds_officer_language(
    status: str, lead: str
) -> None:
    check = warn_check().model_copy(update={"status": status})

    verdict = DeterministicAdjudicator().adjudicate(check, case())

    assert verdict.status == status
    assert verdict.explanation.startswith(lead)
    assert verdict.explanation.endswith(check.explanation)


def test_the_adjudicator_status_options_are_the_contract_ones() -> None:
    enum = schema("ScrutinyCheck")["properties"]["status"]["enum"]

    assert set(AMBIGUOUS_STATUSES) <= set(enum)
    assert "fail" not in AMBIGUOUS_STATUSES and "pass" not in AMBIGUOUS_STATUSES


def test_both_adjudicators_satisfy_the_protocol() -> None:
    assert isinstance(DeterministicAdjudicator(), Adjudicator)
    assert isinstance(LLMAdjudicator(settings=_settings(), client=stub_client([])), Adjudicator)
    assert DeterministicAdjudicator().last_meta is None


@pytest.mark.skipif(not get_llm_settings().enabled, reason="LLM_API_KEY not set")
def test_live_endpoint_roundtrip() -> None:  # pragma: no cover - requires credentials
    adjudicator = LLMAdjudicator()

    verdict = adjudicator.adjudicate(warn_check(), case())

    assert verdict.status in {"pass", "fail", "warn", "info"}
    assert verdict.explanation.strip()
    meta = adjudicator.last_meta
    assert meta is not None and meta.component == "adjudicator"
