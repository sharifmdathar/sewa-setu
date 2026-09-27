"""A9 error paths: every failure answers with the same envelope, and never with a 500 by accident.

The contract only documents the success shapes, so "contract-consistent" here means: a real
HTTP status, `{"detail": <str>, "code": <stable slug>}`, JSON content type, and no leaked
internal text. Track B branches on `code`; humans read `detail`.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api import repository as repository_module
from pipeline.api.errors import ApiError
from pipeline.api.main import create_app

GOOD_B64 = base64.b64encode(doc_text("aadhaar").encode("utf-8")).decode("ascii")


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def application_id(client: TestClient) -> str:
    response = client.post(
        "/applications",
        json={
            "serviceId": "income_certificate",
            "applicantFields": {"fullName": "Anita Baruah", "annualIncomeInr": 180000},
        },
    )
    return str(response.json()["id"])


def assert_envelope(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["code"] == code
    assert isinstance(payload["detail"], str) and payload["detail"]
    return payload


def test_an_unknown_service_is_a_400_with_a_code(client: TestClient) -> None:
    response = client.post(
        "/applications", json={"serviceId": "birth_certificate", "applicantFields": {}}
    )

    payload = assert_envelope(response, 400, "unknown_service")
    assert "birth_certificate" in payload["detail"]


def test_a_new_application_with_no_documents_cannot_be_scrutinized(client: TestClient) -> None:
    application_id_value = application_id(client)

    response = client.post(f"/applications/{application_id_value}/scrutiny/run")

    assert_envelope(response, 409, "documents_required")
    assert client.get(f"/applications/{application_id_value}").json()["status"] == "submitted"


@pytest.mark.parametrize(
    ("content_base64", "file_name", "reason"),
    [
        ("not!base64", "aadhaar.txt", "not valid base64"),
        (base64.b64encode(b"\xff\xfe binary").decode(), "aadhaar.txt", "must be valid UTF-8"),
        ("", "aadhaar.txt", "the upload is empty"),
    ],
)
def test_undecodable_uploads_are_refused_with_a_code(
    client: TestClient, content_base64: str, file_name: str, reason: str
) -> None:
    application_id_value = application_id(client)

    response = client.post(
        f"/applications/{application_id_value}/documents",
        json={"docType": "aadhaar", "fileName": file_name, "contentBase64": content_base64},
    )

    payload = assert_envelope(response, 422, "invalid_document")
    assert file_name in payload["detail"]
    assert reason in payload["detail"]


def test_a_binary_upload_is_accepted_and_later_reads_as_unreadable(
    client: TestClient,
) -> None:
    """Unknown types are stored, not refused: a scan the extractor cannot read is C3's finding."""
    application_id_value = application_id(client)

    response = client.post(
        f"/applications/{application_id_value}/documents",
        json={
            "docType": "aadhaar",
            "fileName": "mystery-file",
            "contentBase64": base64.b64encode(b"\x00\x01\x02").decode(),
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["sha256"]


def test_a_rejected_upload_leaves_the_application_untouched(
    client: TestClient, tmp_path: Path
) -> None:
    application_id_value = application_id(client)

    client.post(
        f"/applications/{application_id_value}/documents",
        json={"docType": "aadhaar", "fileName": "a.txt", "contentBase64": "!!!"},
    )

    stored = repository_module.Repository(tmp_path).get(application_id_value)
    assert stored is not None and stored["documents"] == []
    assert stored["status"] == "submitted"  # no documents_uploaded event was fired


@pytest.mark.parametrize(
    ("method", "suffix", "code"),
    [
        ("get", "", "unknown_application"),
        ("post", "/documents", "unknown_application"),
        ("post", "/scrutiny/run", "unknown_application"),
        ("get", "/scrutiny", "unknown_application"),
    ],
)
def test_every_id_carrying_path_reports_the_same_code(
    client: TestClient, method: str, suffix: str, code: str
) -> None:
    body: dict[str, Any] | None = (
        {"docType": "aadhaar", "fileName": "a.txt", "contentBase64": GOOD_B64}
        if suffix == "/documents"
        else None
    )
    call = getattr(client, method)
    response = call("/applications/APP-MISSING" + suffix, json=body) if body else call(
        "/applications/APP-MISSING" + suffix
    )

    assert_envelope(response, 404, code)


def test_deciding_an_unknown_application_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/officer/decisions",
        json={"applicationId": "APP-MISSING", "decision": "approve", "officerNotes": "x"},
    )

    assert_envelope(response, 404, "unknown_application")


def test_scrutiny_that_has_not_run_is_a_distinct_404(client: TestClient) -> None:
    application_id_value = application_id(client)
    client.post(
        f"/applications/{application_id_value}/documents",
        json={
            "docType": "aadhaar",
            "fileName": "aadhaar.txt",
            "contentBase64": GOOD_B64,
        },
    )

    response = client.get(f"/applications/{application_id_value}/scrutiny")

    assert_envelope(response, 404, "scrutiny_not_run")


def test_a_body_missing_contract_fields_reports_which_fields(
    client: TestClient,
) -> None:
    response = client.post("/applications", json={"applicantFields": {}})

    payload = assert_envelope(response, 422, "invalid_request")
    assert [entry["field"] for entry in payload["fields"]] == ["serviceId"]
    assert all(isinstance(entry["message"], str) for entry in payload["fields"])


def test_a_wrong_typed_body_is_rejected_before_any_record_is_written(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post(
        "/applications", json={"serviceId": 17, "applicantFields": "not an object"}
    )

    assert_envelope(response, 422, "invalid_request")
    assert len({entry["field"] for entry in response.json()["fields"]}) == 2
    assert repository_module.Repository(tmp_path).all() == []


def test_an_unexpected_internal_failure_never_leaks_its_traceback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("store disk is on fire")

    monkeypatch.setattr(repository_module.Repository, "create", explode)
    strict = TestClient(create_app(), raise_server_exceptions=False)

    response = strict.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": {}}
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "internal_error"
    assert "store disk is on fire" not in payload["detail"]
    assert "Traceback" not in response.text


def test_api_error_carries_its_three_fields() -> None:
    error = ApiError(418, "teapot", "no coffee here")

    assert (error.status, error.code, str(error)) == (418, "teapot", "no coffee here")
    assert ApiError.documents_required("APP-1").status == 409
