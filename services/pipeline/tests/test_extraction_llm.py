"""LLMExtractor behaviour, driven by an injected stub client (no network).

The single test that needs a live endpoint skips unless LLM_API_KEY is set.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction import DocumentContent, ExtractionError, LLMExtractor

VALID_PAYLOAD = {
    "docType": "aadhaar",
    "name": "Anita Baruah",
    "idNumber": "4123 8890 1177",
    "issueDate": "2019-04-02",
    "expiryDate": "2039-04-01",
    "issuingAuthority": "Unique Fictiona Identity Authority",
    "amounts": [],
}


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
        "model": "stub-vlm",
        "timeout_seconds": 1,
        "max_retries": 2,
        # Stubbed responses share one prompt, so an enabled cache would answer the next test
        # from disk instead of from its own stub. Backoff is zero for the same reason: retries
        # are what these tests assert, and waiting for them would only slow the suite down.
        "cache_enabled": False,
        "backoff_base_seconds": 0.0,
    }
    return LlmSettings(**{**values, **overrides})


def _document(
    text: str | None = "FULL_NAME: Anita Baruah", base64: str | None = None
) -> DocumentContent:
    return DocumentContent(
        documentId="D1",
        docType="aadhaar",
        fileName="aadhaar.txt",
        mime_type="image/png" if base64 else "text/plain",
        text=text,
        content_base64=base64,
    )


def _response(payload: Any, model: str = "stub-vlm") -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    message = SimpleNamespace(content=content)
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=message)])


def test_parses_model_payload_and_records_meta() -> None:
    client = stub_client([_response(VALID_PAYLOAD)])
    extractor = LLMExtractor(settings=_settings(), client=client)

    fields = extractor.extract(_document())

    assert fields.name == "Anita Baruah"
    assert fields.id_number == "4123 8890 1177"
    assert fields.expiry_date is not None and fields.expiry_date.year == 2039
    assert fields.raw_text == "FULL_NAME: Anita Baruah"
    meta = extractor.last_meta
    assert meta is not None and meta.model == "stub-vlm" and meta.attempts == 1
    assert meta.component == "extractor" and meta.latency_ms >= 0

    request = client.chat.completions.requests[0]
    assert request["model"] == "stub-vlm"
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0


def test_retries_when_the_model_returns_unusable_json() -> None:
    client = stub_client([_response("not json at all"), _response(VALID_PAYLOAD)])
    extractor = LLMExtractor(settings=_settings(), client=client)

    fields = extractor.extract(_document())

    assert fields.name == "Anita Baruah"
    assert extractor.last_meta is not None and extractor.last_meta.attempts == 2
    assert len(client.chat.completions.requests) == 2


def test_gives_up_after_the_configured_attempts() -> None:
    client = stub_client([_response("broken")])
    extractor = LLMExtractor(settings=_settings(max_retries=1), client=client)

    with pytest.raises(ExtractionError, match="unusable extractor payload"):
        extractor.extract(_document())

    assert len(client.chat.completions.requests) == 2


def test_transport_failure_is_reported_as_an_extraction_failure() -> None:
    client = stub_client([RuntimeError("connection reset")])
    extractor = LLMExtractor(settings=_settings(), client=client)

    with pytest.raises(ExtractionError, match="LLM call failed"):
        extractor.extract(_document())


def test_image_documents_are_sent_as_data_uris() -> None:
    client = stub_client([_response(VALID_PAYLOAD)])
    extractor = LLMExtractor(settings=_settings(), client=client)

    extractor.extract(_document(text=None, base64="cGxhY2Vob2xkZXI="))

    parts = client.chat.completions.requests[0]["messages"][1]["content"]
    expected = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cGxhY2Vob2xkZXI="},
    }
    assert expected in parts


def test_document_with_no_content_at_all_is_rejected() -> None:
    extractor = LLMExtractor(settings=_settings(), client=stub_client([_response(VALID_PAYLOAD)]))
    with pytest.raises(ExtractionError, match="nothing to send"):
        extractor.extract(_document(text=None))


def test_missing_api_key_disables_the_extractor_rather_than_hanging() -> None:
    extractor = LLMExtractor(settings=LlmSettings(base_url=None, api_key=None, model="m"))
    with pytest.raises(ExtractionError, match="LLM_API_KEY is not set"):
        extractor.extract(_document())


@pytest.mark.skipif(not get_llm_settings().enabled, reason="LLM_API_KEY not set")
def test_live_endpoint_roundtrip() -> None:  # pragma: no cover - requires credentials
    extractor = LLMExtractor()
    fields = extractor.extract(_document())
    assert fields.doc_type == "aadhaar"
