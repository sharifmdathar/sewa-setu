"""The contract paths that only make sense as a journey: states, queue order, decisions, metrics.

Helpers are local to this file on purpose - the same way A3's LLM stubs stayed local - so the
two API test files can be read and run independently. Each application gets its own applicant:
two applicants who really are different people must not be flagged as document duplicates.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from contract import assert_valid, schema
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api import repository as repository_module
from pipeline.api.main import create_app
from pipeline.api.repository import latest_eval_metrics

INCOME = 180000
APPLICANTS = (
    ("Anita Baruah", "4123 8890 1177"),
    ("Bilal Negi", "5231 9908 2266"),
    ("Chandra Rao", "6342 1109 3377"),
)
DOC_TYPES = (
    ("aadhaar", "Unique Fictiona Identity Authority"),
    ("bank_statement", "Fictiona Gramin Bank"),
    ("revenue_record", "Tehsildar Office"),
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def upload_text(
    client: TestClient, application_id: str, doc_type: str, text: str
) -> dict[str, Any]:
    response = client.post(
        f"/applications/{application_id}/documents",
        json={
            "docType": doc_type,
            "fileName": f"{doc_type}.txt",
            "contentBase64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def new_application(client: TestClient, who: int = 0) -> str:
    name, aadhaar = APPLICANTS[who]
    response = client.post(
        "/applications",
        json={
            "serviceId": "income_certificate",
            "applicantFields": {
                "fullName": name,
                "aadhaarNumber": aadhaar,
                "annualIncomeInr": INCOME,
            },
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def filed_application(client: TestClient, who: int = 0, *, forged: bool = False) -> str:
    """A new income-certificate application carrying all three required documents."""
    name, aadhaar = APPLICANTS[who]
    application_id = new_application(client, who)
    for doc_type, authority in DOC_TYPES:
        tampered = forged and doc_type != "aadhaar"
        upload_text(
            client,
            application_id,
            doc_type,
            doc_text(
                doc_type,
                authority=authority,
                name="Ganesh Baruah" if forged and doc_type == "bank_statement" else name,
                aadhaar=aadhaar,
                amount=10 * INCOME if tampered else INCOME,
                expiry="2020-01-05" if forged and doc_type == "revenue_record" else "2034-01-05",
            ),
        )
    return application_id


def view(client: TestClient, application_id: str) -> tuple[str, list[str]]:
    payload = client.get(f"/applications/{application_id}").json()
    assert_valid(payload, "Application")
    return str(payload["status"]), [
        f"{event['actor']}:{event['event']}" for event in payload["timeline"]
    ]


def decide(client: TestClient, application_id: str, decision: str, notes: str) -> dict[str, Any]:
    response = client.post(
        "/officer/decisions",
        json={"applicationId": application_id, "decision": decision, "officerNotes": notes},
    )
    assert response.status_code == 200, response.text
    return response.json()


def c5_status(report: dict[str, Any]) -> str:
    return next(check for check in report["checks"] if check["checkId"] == "C5")["status"]


def test_an_application_walks_every_status_it_needs_to(client: TestClient) -> None:
    application_id = new_application(client)

    assert view(client, application_id) == ("submitted", ["citizen:submitted"])
    upload_text(client, application_id, "aadhaar", doc_text("aadhaar"))
    assert view(client, application_id)[0] == "documents_uploaded"

    client.post(f"/applications/{application_id}/scrutiny/run")
    status, timeline = view(client, application_id)
    assert status == "scrutiny_done"
    assert timeline == [
        "citizen:submitted",
        "citizen:document_uploaded",
        "system:scrutiny_started",
        "system:scrutiny_done",
    ]

    result = decide(client, application_id, "request_info", "Re-submit the bank statement.")
    # This response has no named component (it is inline in the contract), so it is pinned by
    # its keys and by the AppStatus enum the contract does declare.
    assert result == {"applicationId": application_id, "status": "info_requested"}
    assert result["status"] in schema("AppStatus")["enum"]
    assert view(client, application_id)[1][-1] == "officer:decision_request_info"


def test_the_officer_note_reaches_the_citizen_timeline(client: TestClient) -> None:
    application_id = filed_application(client)
    client.post(f"/applications/{application_id}/scrutiny/run")

    decide(client, application_id, "approve", "Verified in person.")
    last = client.get(f"/applications/{application_id}").json()["timeline"][-1]

    assert last["actor"] == "officer"
    assert last["event"] == "decision_approve"
    assert "Verified in person." in last["message"]


def test_the_queue_ranks_by_risk_and_empties_as_officers_decide(client: TestClient) -> None:
    clean = filed_application(client, 0)
    fraud = filed_application(client, 1, forged=True)

    assert client.post(f"/applications/{clean}/scrutiny/run").json()["riskScore"] == 0
    fraud_score = client.post(f"/applications/{fraud}/scrutiny/run").json()["riskScore"]
    assert fraud_score >= 60

    queue = client.get("/officer/queue").json()
    for item in queue:
        assert_valid(item, "QueueItem")
    assert [item["applicationId"] for item in queue] == [fraud, clean]
    assert [item["riskScore"] for item in queue] == [fraud_score, 0]

    decide(client, fraud, "reject", "Forged bank statement.")
    assert [item["applicationId"] for item in client.get("/officer/queue").json()] == [clean]


def test_two_different_applicants_are_not_duplicates_of_each_other(client: TestClient) -> None:
    first, second = filed_application(client, 0), filed_application(client, 1)

    reports = [client.post(f"/applications/{i}/scrutiny/run").json() for i in (first, second)]

    assert [report["riskScore"] for report in reports] == [0, 0]
    assert [c5_status(report) for report in reports] == ["pass", "pass"]


def test_a_reused_document_raises_the_second_application_score(client: TestClient) -> None:
    """C5's duplicate check spans applications, so the API must index what is already stored."""
    first = new_application(client, 0)
    aadhaar = doc_text("aadhaar", amount=INCOME)
    upload_text(client, first, "aadhaar", aadhaar)
    first_report = client.post(f"/applications/{first}/scrutiny/run").json()

    second = new_application(client, 1)
    upload_text(client, second, "aadhaar", aadhaar)  # the very same file, re-uploaded
    second_report = client.post(f"/applications/{second}/scrutiny/run").json()

    assert c5_status(first_report) == "pass"
    assert c5_status(second_report) == "fail"
    assert second_report["riskScore"] > first_report["riskScore"]
    duplicate = next(check for check in second_report["checks"] if check["checkId"] == "C5")
    assert "another application" in duplicate["evidence"]


def test_re_running_scrutiny_keeps_one_report_and_one_queue_row(client: TestClient) -> None:
    application_id = filed_application(client)
    client.post(f"/applications/{application_id}/scrutiny/run")
    second = client.post(f"/applications/{application_id}/scrutiny/run").json()

    fetched = client.get(f"/applications/{application_id}/scrutiny").json()
    queue = client.get("/officer/queue").json()

    assert fetched == second
    assert [item["applicationId"] for item in queue] == [application_id]
    assert view(client, application_id)[1].count("system:scrutiny_done") == 2


def test_metrics_describe_the_store(client: TestClient) -> None:
    clean, fraud = filed_application(client, 0), filed_application(client, 1, forged=True)
    client.post(f"/applications/{clean}/scrutiny/run")
    client.post(f"/applications/{fraud}/scrutiny/run")
    decide(client, fraud, "reject", "No.")

    payload = client.get("/metrics/summary").json()

    assert_valid(payload, "MetricsSummary")
    assert payload["applicationsTotal"] == 2
    assert payload["pending"] == 1
    assert payload["decided"] == 1
    assert 0.0 <= payload["flagRate"] <= 1.0
    assert payload["avgScrutinySeconds"] >= 0.0


def test_an_info_request_stays_pending_rather_than_becoming_a_decision(
    client: TestClient,
) -> None:
    application_id = filed_application(client)
    client.post(f"/applications/{application_id}/scrutiny/run")
    decide(client, application_id, "request_info", "Attach the revenue record.")

    payload = client.get("/metrics/summary").json()

    assert view(client, application_id)[0] == "info_requested"
    assert payload["pending"] == 1
    assert payload["decided"] == 0


def test_metrics_omit_the_eval_fields_until_the_harness_has_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(repository_module, "EVAL_REPORTS_DIR", tmp_path / "no-eval-yet")

    payload = client.get("/metrics/summary").json()

    assert_valid(payload, "MetricsSummary")
    assert "evalPrecision" not in payload and "evalRecall" not in payload


def test_metrics_read_eval_numbers_from_the_newest_report(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "reports"
    for stamp, content in {
        "2026-09-01T00-00-00": {"evalPrecision": 0.5, "evalRecall": 0.5},
        "2026-09-26T09-30-00": {"evalPrecision": 0.94, "evalRecall": 0.88},
    }.items():
        directory = root / stamp
        directory.mkdir(parents=True)
        (directory / "report.json").write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr(repository_module, "EVAL_REPORTS_DIR", root)

    assert latest_eval_metrics() == {"evalPrecision": 0.94, "evalRecall": 0.88}
    payload = client.get("/metrics/summary").json()

    assert_valid(payload, "MetricsSummary")
    assert (payload["evalPrecision"], payload["evalRecall"]) == (0.94, 0.88)


def test_a_malformed_eval_report_never_breaks_the_metrics_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "reports" / "2026-09-26T00-00-00"
    broken.mkdir(parents=True)
    (broken / "report.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(repository_module, "EVAL_REPORTS_DIR", tmp_path / "reports")

    assert latest_eval_metrics() == {}
    assert_valid(client.get("/metrics/summary").json(), "MetricsSummary")
