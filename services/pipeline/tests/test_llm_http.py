"""The model path over real HTTP, against `tests/fake_endpoint.py`.

Everything else in this directory injects a stub client, which means the socket layer, the SDK's
own error types, and whether a cached answer really avoids a request were never exercised. Those
are exactly the things that fail on a rate-limited free key at two in the afternoon, so they get
tested here instead of at the demo.

No test in this file needs `LLM_API_KEY` or any network beyond a loopback port.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from fake_endpoint import FakeEndpoint
from helpers import doc_text, make_input

from pipeline.agent import DeterministicAdjudicator, run_scrutiny
from pipeline.agent.adjudicator import AdjudicationError, LLMAdjudicator
from pipeline.config import LlmSettings
from pipeline.extraction import DocumentContent, ExtractionError, LLMExtractor
from pipeline.llmcache import reset_caches
from pipeline.rules.models import ScrutinyCheck

SERVED = "fake-vlm-1"
EXTRACTION_REPLY: dict[str, Any] = {
    "docType": "aadhaar",
    "name": "Anita Baruah",
    "idNumber": "4123 8890 1177",
    "issueDate": "2024-01-05",
    "expiryDate": "2034-01-05",
    "issuingAuthority": "Unique Fictiona Identity Authority",
    "amounts": [],
}
ADJUDICATION_REPLY = {"status": "fail", "explanation": "The stated amount cannot be reconciled."}


@pytest.fixture(autouse=True)
def _no_stale_caches() -> Any:
    reset_caches()
    yield
    reset_caches()


def _settings(endpoint: FakeEndpoint, **overrides: Any) -> LlmSettings:
    values: dict[str, Any] = {
        "base_url": endpoint.base_url,
        "api_key": "local-test-key",
        "model": "requested-model",
        "timeout_seconds": 5,
        "max_retries": 2,
        "cache_enabled": False,
        "backoff_base_seconds": 0.0,
    }
    return LlmSettings(**{**values, **overrides})


def _text_document(body: str | None = None) -> DocumentContent:
    return DocumentContent(
        documentId="DOC-1",
        docType="aadhaar",
        fileName="app1-aadhaar-1.txt",
        text=body if body is not None else doc_text(),
    )


def _check(status: str = "warn") -> ScrutinyCheck:
    return ScrutinyCheck(
        checkId="C4",
        label="Cross-field consistency",
        status=status,  # type: ignore[arg-type]
        severity="medium",  # type: ignore[arg-type]
        evidence="Declared 424000; the bank statement states 42400.",
        explanation="The declared amount and the document disagree.",
    )


def test_the_extractor_reads_a_document_over_real_http() -> None:
    with FakeEndpoint(reply=EXTRACTION_REPLY, served_model=SERVED) as endpoint:
        fields = LLMExtractor(settings=_settings(endpoint)).extract(_text_document())

    assert fields.name == "Anita Baruah" and fields.doc_type == "aadhaar"
    assert endpoint.count == 1
    assert endpoint.json_mode_seen, "the request should still ask for JSON mode"


def test_a_rate_limited_endpoint_is_waited_out_rather_than_fatal() -> None:
    # Two rejections leave the loop's third and final attempt to succeed, which only works
    # because this module - not the SDK underneath it - owns the retry policy.
    with FakeEndpoint(reply=EXTRACTION_REPLY, fail_first=2) as endpoint:
        fields = LLMExtractor(settings=_settings(endpoint)).extract(_text_document())

    assert fields.id_number == "4123 8890 1177"
    assert endpoint.count == 3, "the run survived the limiter instead of aborting"


def test_a_model_without_json_mode_is_asked_again_without_it() -> None:
    with FakeEndpoint(reply=EXTRACTION_REPLY, reject_json_mode=True) as endpoint:
        extractor = LLMExtractor(settings=_settings(endpoint))
        fields = extractor.extract(_text_document())

    assert fields.name == "Anita Baruah"
    assert endpoint.count == 2
    assert "response_format" in endpoint.requests[0]
    assert "response_format" not in endpoint.requests[1]
    assert extractor.last_meta is not None and extractor.last_meta.attempts == 2


def test_a_second_identical_read_costs_no_second_request(tmp_path: Path) -> None:
    with FakeEndpoint(reply=EXTRACTION_REPLY) as endpoint:
        settings = _settings(endpoint, cache_enabled=True, cache_dir=tmp_path)
        document = _text_document()
        first = LLMExtractor(settings=settings).extract(document)
        second = LLMExtractor(settings=settings).extract(document)

    assert first.name == second.name == "Anita Baruah"
    assert endpoint.count == 1, "the cache should have answered the second read"


def test_an_auth_failure_fails_fast_instead_of_retrying() -> None:
    with FakeEndpoint(hard_status=401) as endpoint, pytest.raises(
        ExtractionError, match="LLM call failed"
    ):
        LLMExtractor(settings=_settings(endpoint)).extract(_text_document())

    assert endpoint.count == 1, "a 401 will not fix itself; retrying burns the quota"


def test_prose_where_json_was_asked_exhausts_the_attempt_budget() -> None:
    with FakeEndpoint(raw_content="I am unable to help with that.") as endpoint, pytest.raises(
        ExtractionError, match="unusable extractor payload"
    ):
        LLMExtractor(settings=_settings(endpoint)).extract(_text_document())

    assert endpoint.count == 3, "the documented budget is max_retries + 1 attempts"


def test_image_documents_reach_the_endpoint_as_a_data_uri() -> None:
    pixels = base64.b64encode(b"\x89PNG\r\n\x1a\n synthetic").decode("ascii")
    document = DocumentContent(
        documentId="SCAN-1",
        docType="aadhaar",
        fileName="scan.png",
        mimeType="image/png",
        contentBase64=pixels,
    )

    with FakeEndpoint(reply=EXTRACTION_REPLY) as endpoint:
        LLMExtractor(settings=_settings(endpoint)).extract(document)

    assert endpoint.image_seen
    assert f"data:image/png;base64,{pixels}" in str(endpoint.requests)


def test_the_adjudicator_settles_a_check_over_http() -> None:
    with FakeEndpoint(reply=ADJUDICATION_REPLY, served_model="fake-judge-1") as endpoint:
        adjudicator = LLMAdjudicator(settings=_settings(endpoint))
        verdict = adjudicator.adjudicate(_check(), make_input([]))

    assert verdict.status == "fail"
    assert verdict.explanation.startswith("The stated amount")
    assert endpoint.count == 1
    assert "Cross-field consistency" in str(endpoint.requests)


def test_an_outage_is_retried_within_the_documented_budget_not_the_square_of_it() -> None:
    with FakeEndpoint(hard_status=503) as endpoint, pytest.raises(AdjudicationError, match="C4"):
        LLMAdjudicator(settings=_settings(endpoint)).adjudicate(_check(), make_input([]))

    assert endpoint.count == 3, "max_retries + 1 requests; a second retry layer doubles that"


def test_a_full_scrutiny_run_names_the_model_that_answered() -> None:
    with FakeEndpoint(reply=EXTRACTION_REPLY, served_model=SERVED) as endpoint:
        report = run_scrutiny(
            make_input([], required=("aadhaar",)),
            [_text_document()],
            extractor=LLMExtractor(settings=_settings(endpoint)),
            adjudicator=DeterministicAdjudicator(),
        )

    assert [check.check_id for check in report.checks] == ["C1", "C2", "C3", "C4", "C5"]
    assert all(check.evidence and check.explanation for check in report.checks)
    assert report.model_meta.extractor == "llm-vlm"
    assert report.model_meta.versions["extractor"] == SERVED, "the served model, not the requested"
    assert endpoint.count == 1
    assert 0 <= report.risk_score <= 100
