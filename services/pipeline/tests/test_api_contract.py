"""A7 DoD: every contract path answered, each response validated against openapi.yaml itself.

`tests/contract.py` reads the frozen YAML, so these tests fail if a route grows a field the
contract does not declare, drops one it does, or leaks a store-internal key. The officer-queue,
state-machine and metrics behaviours are in tests/test_api_journey.py.
"""

from __future__ import annotations

import base64
import hashlib
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from contract import assert_valid, schema
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api import catalog
from pipeline.api.main import create_app

INCOME = 180000
FIELDS: dict[str, Any] = {
    "fullName": "Anita Baruah",
    "aadhaarNumber": "4123 8890 1177",
    "annualIncomeInr": INCOME,
}
REQUIRED_FOR_INCOME = (
    ("aadhaar", "aadhaar.txt", "Unique Fictiona Identity Authority"),
    ("bank_statement", "bank.txt", "Fictiona Gramin Bank"),
    ("revenue_record", "revenue.txt", "Tehsildar Office"),
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def new_application(client: TestClient, service_id: str = "income_certificate") -> str:
    response = client.post(
        "/applications", json={"serviceId": service_id, "applicantFields": FIELDS}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def upload(
    client: TestClient,
    application_id: str,
    doc_type: str,
    file_name: str,
    authority: str,
    *,
    amount: int | None = None,
    expiry: str | None = "2034-01-05",
    raw_text: str | None = None,
    encoding: str | None = None,
) -> dict[str, Any]:
    text = raw_text if raw_text is not None else doc_text(
        doc_type, authority=authority, amount=amount, expiry=expiry
    )
    body = {
        "docType": doc_type,
        "fileName": file_name,
        "contentBase64": encoding
        if encoding is not None
        else base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }
    response = client.post(f"/applications/{application_id}/documents", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def complete_application(client: TestClient) -> str:
    """A clean income-certificate application: all three required documents attached."""
    application_id = new_application(client)
    for doc_type, file_name, authority in REQUIRED_FOR_INCOME:
        amount = None if doc_type == "aadhaar" else INCOME
        upload(client, application_id, doc_type, file_name, authority, amount=amount)
    return application_id


def test_healthz_answers() -> None:
    client = TestClient(create_app(Path("/tmp/unused-by-healthz")))

    assert client.get("/healthz").json() == {"status": "ok"}


def test_services_are_contract_services(client: TestClient) -> None:
    response = client.get("/services")

    assert response.status_code == 200
    payload = response.json()
    assert [service["id"] for service in payload] == [
        "income_certificate",
        "caste_certificate",
        "residence_certificate",
    ]
    for service in payload:
        assert_valid(service, "Service")


def test_the_api_catalog_matches_the_generator(client: TestClient) -> None:
    """The generator plants anomalies against these document sets, so the two must agree."""
    from generator.services import SERVICES as GENERATED

    mine = {service["id"]: service for service in client.get("/services").json()}

    for service in GENERATED:
        assert mine[service["id"]] == service
    assert set(mine) == {service["id"] for service in GENERATED}


def test_a_new_application_is_submitted_with_a_timeline(client: TestClient) -> None:
    payload = client.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": FIELDS}
    ).json()

    assert_valid(payload, "Application")
    assert payload["status"] == "submitted"
    assert payload["applicantFields"] == FIELDS
    assert payload["timeline"][0]["actor"] == "citizen"


def test_an_unknown_service_is_refused(client: TestClient) -> None:
    response = client.post(
        "/applications", json={"serviceId": "birth_certificate", "applicantFields": {}}
    )

    assert response.status_code == 400
    assert "birth_certificate" in response.json()["detail"]


def test_the_document_response_is_a_contract_document(client: TestClient) -> None:
    application_id = new_application(client)
    text = doc_text("aadhaar", authority="Unique Fictiona Identity Authority")

    payload = upload(client, application_id, "aadhaar", "a.txt", "ignored", raw_text=text)

    assert_valid(payload, "Document")
    assert payload["fileName"] == "a.txt"
    assert payload["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "contentBase64" not in payload  # the bytes stay in the store


@pytest.mark.parametrize(
    ("encoding", "file_name"),
    [("not!base64", "a.txt"), (base64.b64encode(b"\xff\xfe").decode(), "a.txt")],
)
def test_an_undecodable_upload_is_refused_and_not_stored(
    client: TestClient, tmp_path: Path, encoding: str, file_name: str
) -> None:
    application_id = new_application(client)

    response = client.post(
        f"/applications/{application_id}/documents",
        json={"docType": "aadhaar", "fileName": file_name, "contentBase64": encoding},
    )

    assert response.status_code == 422
    from pipeline.api.repository import Repository

    assert Repository(tmp_path).get(application_id)["documents"] == []  # type: ignore[index]


def test_scrutiny_run_returns_a_contract_report(client: TestClient) -> None:
    application_id = complete_application(client)

    response = client.post(f"/applications/{application_id}/scrutiny/run")
    payload = response.json()

    assert response.status_code == 200
    assert_valid(payload, "ScrutinyReport")
    for check in payload["checks"]:
        assert_valid(check, "ScrutinyCheck")
    assert payload["applicationId"] == application_id
    assert [check["checkId"] for check in payload["checks"]] == ["C1", "C2", "C3", "C4", "C5"]
    assert [check["status"] for check in payload["checks"]] == ["pass"] * 5
    assert payload["riskScore"] == 0
    assert payload["recommendation"] == "approve"
    assert payload["modelMeta"]["extractor"] == "template"
    assert len(payload["extractedFields"]) == 3


def test_the_report_survives_the_store_roundtrip(client: TestClient) -> None:
    application_id = complete_application(client)
    ran = client.post(f"/applications/{application_id}/scrutiny/run").json()

    fetched = client.get(f"/applications/{application_id}/scrutiny")

    assert fetched.status_code == 200
    assert_valid(fetched.json(), "ScrutinyReport")
    assert fetched.json()["riskScore"] == ran["riskScore"]
    assert [check["explanation"] for check in fetched.json()["checks"]] == [
        check["explanation"] for check in ran["checks"]
    ]


def test_listing_documents_returns_what_was_filed_in_upload_order(client: TestClient) -> None:
    """CR-1: GET on the same path the citizen uploads to, so the officer sees the filing."""
    application_id = complete_application(client)

    response = client.get(f"/applications/{application_id}/documents")
    payload = response.json()

    assert response.status_code == 200
    for document in payload:
        assert_valid(document, "Document")
    assert [document["fileName"] for document in payload] == [
        file_name for _, file_name, _ in REQUIRED_FOR_INCOME
    ]
    assert [document["docType"] for document in payload] == [
        doc_type for doc_type, _, _ in REQUIRED_FOR_INCOME
    ]
    assert all("contentBase64" not in document for document in payload)


def test_an_unfiled_application_lists_no_documents(client: TestClient) -> None:
    application_id = new_application(client)

    response = client.get(f"/applications/{application_id}/documents")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/applications/APP-NOPE"),
        ("post", "/applications/APP-NOPE/documents"),
        ("get", "/applications/APP-NOPE/documents"),
        ("post", "/applications/APP-NOPE/scrutiny/run"),
        ("get", "/applications/APP-NOPE/scrutiny"),
        ("post", "/officer/decisions"),
    ],
)
def test_every_application_path_404s_for_an_unknown_id(
    client: TestClient, method: str, path: str
) -> None:
    body: dict[str, Any] = (
        {"docType": "aadhaar", "fileName": "a.txt", "contentBase64": "eA=="}
        if path.endswith("documents")
        else {"applicationId": "APP-NOPE", "decision": "approve", "officerNotes": "x"}
    )
    client_method = getattr(client, method)
    response = client_method(path, json=body) if method == "post" else client_method(path)

    assert response.status_code == 404
    assert "APP-NOPE" in response.json()["detail"]


def test_scrutiny_has_not_run_yet_is_a_404_not_an_empty_report(client: TestClient) -> None:
    application_id = complete_application(client)

    response = client.get(f"/applications/{application_id}/scrutiny")

    assert response.status_code == 404
    assert "not been run" in response.json()["detail"]


@pytest.mark.parametrize(
    ("model_path", "component"),
    [
        ("pipeline.api.models:Application", "Application"),
        ("pipeline.api.models:Document", "Document"),
        ("pipeline.api.models:Service", "Service"),
        ("pipeline.api.models:TimelineEvent", "TimelineEvent"),
        ("pipeline.api.models:QueueItem", "QueueItem"),
        ("pipeline.api.models:Decision", "Decision"),
        ("pipeline.api.models:MetricsSummary", "MetricsSummary"),
        ("pipeline.agent.models:ScrutinyReport", "ScrutinyReport"),
        ("pipeline.rules.models:ScrutinyCheck", "ScrutinyCheck"),
    ],
)
def test_models_declare_exactly_the_contract_fields(model_path: str, component: str) -> None:
    module_name, _, class_name = model_path.partition(":")

    model = getattr(import_module(module_name), class_name)
    wire = model.model_json_schema(by_alias=True)
    declared = schema(component)

    assert set(wire["properties"]) == set(declared["properties"])
    assert set(wire.get("required", [])) == set(declared.get("required", []))


def test_the_service_catalog_is_the_only_writer_of_required_doc_types() -> None:
    assert catalog.get("income_certificate") is not None
    assert catalog.get("not_a_service") is None
    assert [service.id for service in catalog.services()] == [
        "income_certificate",
        "caste_certificate",
        "residence_certificate",
    ]
