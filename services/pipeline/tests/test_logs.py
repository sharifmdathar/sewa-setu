"""A9 structured logging: one JSON object per line, with context - and never the applicant.

The privacy half matters more than the format half. The pipeline handles names, identity
numbers and document bodies end to end, so a log stream that made those convenient to print
would be the easiest way to leak them; these tests fail if the call sites start doing it.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api.main import create_app
from pipeline.logs import JsonFormatter, configure, event, get_logger, warning

FORBIDDEN = ("Anita Baruah", "4123 8890 1177", "ISSUING_AUTHORITY", "FULL_NAME", "annualIncome")


@contextmanager
def capture(level: int = logging.INFO) -> Iterator[list[logging.LogRecord]]:
    """Collect what the pipeline logger would emit, without touching stdout."""
    logger = configure(level)
    collected: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    handler = Collector()
    logger.addHandler(handler)
    try:
        yield collected
    finally:
        logger.removeHandler(handler)


def as_json(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
    formatter = JsonFormatter()
    return [json.loads(formatter.format(record)) for record in records]


def test_configure_is_idempotent_and_does_not_double_print() -> None:
    logger = configure()
    handlers_before = len(logger.handlers)

    configure()
    configure(logging.WARNING)

    assert len(logger.handlers) == handlers_before
    assert logger.propagate is False
    logger.setLevel(logging.INFO)  # leave the level where the rest of the suite expects it


def test_records_render_as_one_json_object_with_their_context() -> None:
    logger = get_logger("test")

    with capture() as records:
        event(logger, "something happened", applicationId="APP-1", riskScore=42)
        warning(logger, "a fallback was taken", reason="no model")

    lines = as_json(records)
    assert [line["message"] for line in lines] == [
        "something happened",
        "a fallback was taken",
    ]
    assert lines[0]["level"] == "INFO" and lines[1]["level"] == "WARNING"
    assert lines[0]["logger"].endswith("pipeline.test")
    assert (lines[0]["applicationId"], lines[0]["riskScore"]) == ("APP-1", 42)
    assert lines[1]["reason"] == "no model"
    assert all(line["ts"].endswith("Z") for line in lines)


def test_a_disabled_level_costs_nothing() -> None:
    logger = get_logger("test")

    with capture(logging.WARNING) as records:
        event(logger, "this should not appear")
        warning(logger, "this should")

    assert [record.getMessage() for record in records] == ["this should"]


def test_a_logged_exception_becomes_a_traceback_field_not_part_of_the_message() -> None:
    logger = get_logger("test")

    with capture() as records:
        try:
            raise ValueError("boom")
        except ValueError as exc:
            logger.error(
                "extraction failed",
                extra={"context": {"phase": "extraction"}},
                exc_info=exc,
            )

    line = json.loads(JsonFormatter().format(records[0]))

    assert line["level"] == "ERROR"
    assert line["message"] == "extraction failed"
    assert line["phase"] == "extraction"
    assert "ValueError: boom" in line["traceback"]


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def run_one_journey(client: TestClient) -> str:
    """A whole application: create, upload an unreadable doc plus a good one, scrutinize, decide."""
    created = client.post(
        "/applications",
        json={
            "serviceId": "income_certificate",
            "applicantFields": {
                "fullName": "Anita Baruah",
                "aadhaarNumber": "4123 8890 1177",
                "annualIncomeInr": 180000,
            },
        },
    )
    application_id = str(created.json()["id"])
    client.post(
        f"/applications/{application_id}/documents",
        json={
            "docType": "aadhaar",
            "fileName": "aadhaar.txt",
            "contentBase64": base64.b64encode(doc_text("aadhaar").encode()).decode(),
        },
    )
    client.post(
        f"/applications/{application_id}/documents",
        json={
            "docType": "affidavit",
            "fileName": "blurry.txt",
            "contentBase64": base64.b64encode(b"a photocopy of a sign\n").decode(),
        },
    )
    client.post(f"/applications/{application_id}/scrutiny/run")
    client.post(
        "/officer/decisions",
        json={"applicationId": application_id, "decision": "approve", "officerNotes": "ok"},
    )
    return application_id


def test_the_request_log_carries_status_and_duration(client: TestClient) -> None:
    with capture() as records:
        application_id = run_one_journey(client)

    requests = [line for line in as_json(records) if line["message"] == "request"]
    by_path = {(line["method"], line["status"]) for line in requests}

    assert application_id
    assert ("POST", 201) in by_path and ("POST", 200) in by_path
    assert all(line["durationMs"] >= 0 for line in requests)
    assert all(line["logger"].endswith("api.request") for line in requests)


def test_a_fallen_back_document_and_a_completed_run_are_logged(client: TestClient) -> None:
    with capture() as records:
        run_one_journey(client)

    lines = as_json(records)
    unreadable = [line for line in lines if line["message"] == "document unreadable"]
    completed = [line for line in lines if line["message"] == "scrutiny completed"]

    assert [line["fileName"] for line in unreadable] == ["blurry.txt"]
    assert unreadable[0]["extractor"] == "template"
    assert len(completed) == 1
    assert set(completed[0]["checks"]) == {"C1", "C2", "C3", "C4", "C5"}
    assert completed[0]["adjudicator"] == "deterministic"
    assert any(
        line["message"] == "officer decision" and line["decision"] == "approve" for line in lines
    )


def test_no_log_line_contains_applicant_data(client: TestClient) -> None:
    with capture() as records:
        run_one_journey(client)

    rendered = [JsonFormatter().format(record) for record in records]

    assert rendered, "the journey should have logged something"
    for line in rendered:
        for secret in FORBIDDEN:
            assert secret not in line, f"{secret!r} leaked into {line[:120]}"
        assert "contentBase64" not in line
