"""I1 self-conformance: the frozen contract judged against a running server.

Every response is validated against the schema its own path declares in
shared/contracts/openapi.yaml - including the 404s, getScrutiny before a run, the 409 on an
application with no documents, and the three inline response shapes (/services, /officer/queue,
/officer/decisions) that have no named component. The server fixture and the bookkeeping that
keeps cleanup precise live in conftest.py.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from contract import assert_valid, assert_valid_response
from helpers import doc_text

INCOME = 180000
DOC_TYPES = (
    ("aadhaar", "Unique Fictiona Identity Authority", None),
    ("bank_statement", "Fictiona Gramin Bank", INCOME),
    ("revenue_record", "Tehsildar Office", INCOME),
)
APPLICANT = {
    "fullName": "Anita Baruah",
    "aadhaarNumber": "4123 8890 1177",
    "annualIncomeInr": INCOME,
}


@pytest.fixture(scope="module")
def scrutinized(live: httpx.Client) -> dict[str, object]:
    """One complete application: created, fully filed, scrutinized, decided by the end."""
    created = live.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
    )
    assert created.status_code == 201, created.text
    app_id = str(created.json()["id"])

    uploads = [
        live.post(
            f"/applications/{app_id}/documents",
            json={
                "docType": doc_type,
                "fileName": f"{app_id}-{doc_type}.txt",
                "contentBase64": base64.b64encode(
                    doc_text(doc_type, authority=authority, amount=amount).encode("utf-8")
                ).decode("ascii"),
            },
        )
        for doc_type, authority, amount in DOC_TYPES
    ]
    assert [response.status_code for response in uploads] == [201, 201, 201]

    run = live.post(f"/applications/{app_id}/scrutiny/run")
    assert run.status_code == 200, run.text
    return {"applicationId": app_id, "report": run.json()}


def test_healthz_answers_without_a_declared_schema(live: httpx.Client) -> None:
    response = live.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_services_matches_its_path_schema(live: httpx.Client) -> None:
    response = live.get("/services")

    assert response.status_code == 200
    assert_valid_response(response.json(), "get", "/services", "200")
    assert len(response.json()) >= 1


def test_post_applications_matches_its_path_schema(live: httpx.Client) -> None:
    response = live.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
    )

    assert response.status_code == 201
    assert_valid_response(response.json(), "post", "/applications", "201")
    assert response.json()["status"] == "submitted"


def test_get_application_and_its_404(live: httpx.Client, scrutinized: dict[str, object]) -> None:
    app_id = str(scrutinized["applicationId"])

    found = live.get(f"/applications/{app_id}")
    missing = live.get("/applications/APP-NOT-HERE")

    assert_valid_response(found.json(), "get", "/applications/{id}", "200")
    assert found.status_code == 200 and missing.status_code == 404
    assert found.json()["id"] == app_id


def test_documents_upload_response_and_404(live: httpx.Client) -> None:
    created = live.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
    )
    app_id = str(created.json()["id"])

    uploaded = live.post(
        f"/applications/{app_id}/documents",
        json={
            "docType": "aadhaar",
            "fileName": "aadhaar.txt",
            "contentBase64": base64.b64encode(doc_text("aadhaar").encode("utf-8")).decode("ascii"),
        },
    )
    missing = live.post(
        "/applications/APP-NOT-HERE/documents",
        json={"docType": "aadhaar", "fileName": "a.txt", "contentBase64": "eA=="},
    )

    assert uploaded.status_code == 201
    assert_valid_response(uploaded.json(), "post", "/applications/{id}/documents", "201")
    assert missing.status_code == 404


def test_documents_listing_matches_its_path_schema(
    live: httpx.Client, scrutinized: dict[str, object]
) -> None:
    """CR-1 live: the GET the contract now declares, judged by the contract itself."""
    app_id = str(scrutinized["applicationId"])

    response = live.get(f"/applications/{app_id}/documents")
    missing = live.get("/applications/APP-NOT-HERE/documents")

    assert response.status_code == 200
    assert_valid_response(response.json(), "get", "/applications/{id}/documents", "200")
    assert [document["docType"] for document in response.json()] == [
        doc_type for doc_type, _, _ in DOC_TYPES
    ]
    assert all("contentBase64" not in document for document in response.json())
    assert missing.status_code == 404


def test_scrutiny_run_returns_a_full_contract_report(
    live: httpx.Client, scrutinized: dict[str, object]
) -> None:
    report = scrutinized["report"]  # type: ignore[index]

    assert_valid_response(report, "post", "/applications/{id}/scrutiny/run", "200")
    assert [check["checkId"] for check in report["checks"]] == ["C1", "C2", "C3", "C4", "C5"]
    for check in report["checks"]:
        assert_valid(check, "ScrutinyCheck")
    assert {check["status"] for check in report["checks"]} == {"pass"}
    assert report["riskScore"] == 0 and report["recommendation"] == "approve"
    assert report["modelMeta"]["latencyMs"] >= 0


def test_get_scrutiny_after_a_run_and_404_before_one(live: httpx.Client) -> None:
    app_id = str(
        live.post(
            "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
        ).json()["id"]
    )
    live.post(
        f"/applications/{app_id}/documents",
        json={
            "docType": "aadhaar",
            "fileName": "aadhaar.txt",
            "contentBase64": base64.b64encode(doc_text("aadhaar").encode("utf-8")).decode("ascii"),
        },
    )

    not_yet = live.get(f"/applications/{app_id}/scrutiny")
    live.post(f"/applications/{app_id}/scrutiny/run")
    ran = live.get(f"/applications/{app_id}/scrutiny")
    missing_id = live.get("/applications/APP-NOT-HERE/scrutiny")

    assert not_yet.status_code == 404
    assert ran.status_code == 200
    assert_valid_response(ran.json(), "get", "/applications/{id}/scrutiny", "200")
    assert missing_id.status_code == 404


def test_running_without_documents_is_refused(live: httpx.Client) -> None:
    app_id = str(
        live.post(
            "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
        ).json()["id"]
    )

    response = live.post(f"/applications/{app_id}/scrutiny/run")

    assert response.status_code == 409
    assert response.json()["code"] == "documents_required"


def test_officer_queue_lists_the_scrutinized_application(
    live: httpx.Client, scrutinized: dict[str, object]
) -> None:
    response = live.get("/officer/queue")

    assert response.status_code == 200
    items = response.json()
    assert_valid_response(items, "get", "/officer/queue", "200")
    app_id = str(scrutinized["applicationId"])
    assert app_id in [item["applicationId"] for item in items]
    assert [int(item["riskScore"]) for item in items] == sorted(
        (int(item["riskScore"]) for item in items), reverse=True
    )


def test_officer_decision_matches_its_inline_schema(
    live: httpx.Client, scrutinized: dict[str, object]
) -> None:
    app_id = str(scrutinized["applicationId"])

    response = live.post(
        "/officer/decisions",
        json={
            "applicationId": app_id,
            "decision": "approve",
            "officerNotes": "I1 conformance run.",
        },
    )
    missing = live.post(
        "/officer/decisions",
        json={"applicationId": "APP-NOT-HERE", "decision": "approve", "officerNotes": "x"},
    )

    assert response.status_code == 200
    assert_valid_response(response.json(), "post", "/officer/decisions", "200")
    assert response.json() == {"applicationId": app_id, "status": "decided"}
    assert missing.status_code == 404


def test_queue_lists_applications_that_have_not_been_scrutinized_yet(
    live: httpx.Client,
) -> None:
    """CR-2 live: the queue is the officer's whole workload, not only the scored part of it."""
    app_id = str(
        live.post(
            "/applications", json={"serviceId": "income_certificate", "applicantFields": APPLICANT}
        ).json()["id"]
    )

    items = live.get("/officer/queue").json()

    assert_valid_response(items, "get", "/officer/queue", "200")
    fresh = [item for item in items if item["applicationId"] == app_id]
    assert fresh == [
        {
            "applicationId": app_id,
            "serviceId": "income_certificate",
            "status": "submitted",
            "riskScore": 0,
            "updatedAt": fresh[0]["updatedAt"],
        }
    ]


def test_metrics_summary_matches_its_schema(live: httpx.Client) -> None:
    response = live.get("/metrics/summary")

    assert response.status_code == 200
    assert_valid_response(response.json(), "get", "/metrics/summary", "200")
