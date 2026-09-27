"""The contract paths that only make sense as a journey: states, queue order, decisions, metrics.

Helpers are local to this file on purpose - the same way A3's LLM stubs stayed local - so the
two API test files can be read and run independently. Each application gets its own applicant:
two applicants who really are different people must not be flagged as document duplicates.
"""

from __future__ import annotations

import base64
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from contract import assert_valid, schema
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api import repository as repository_module
from pipeline.api.main import create_app

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

    # CR-2: a decided application stays listed, with its status - filtering is the UI's job.
    decide(client, fraud, "reject", "Forged bank statement.")
    after = client.get("/officer/queue").json()
    assert {item["applicationId"]: item["status"] for item in after} == {
        fraud: "decided",
        clean: "scrutiny_done",
    }
    assert [item["riskScore"] for item in after] == [fraud_score, 0]

    # The divergence CR-2 closes: the dashboard's "pending" is the queue's open count.
    metrics = client.get("/metrics/summary").json()
    assert metrics["pending"] == sum(1 for item in after if item["status"] != "decided") == 1
    assert metrics["decided"] == 1


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


def test_metrics_carry_chart_ready_series_without_losing_the_scalars(client: TestClient) -> None:
    """CR-3: the dashboard's two charts come from getMetrics, not from bucketing the queue."""
    scored = [filed_application(client, 0), filed_application(client, 1)]
    new_application(client, 2)
    for app_id in scored:
        client.post(f"/applications/{app_id}/scrutiny/run")

    payload = client.get("/metrics/summary").json()

    assert_valid(payload, "MetricsSummary")
    days = payload["applicationsByDay"]
    bands = payload["riskDistribution"]
    assert sum(int(day["count"]) for day in days) == payload["applicationsTotal"] == 3
    assert [day["date"] for day in days] == sorted(day["date"] for day in days)
    dt.date.fromisoformat(days[0]["date"])  # the contract types it `format: date`
    assert {band["band"] for band in bands} <= {"low", "medium", "high"}
    # once anything is scored all three bands appear, so the chart's axis stays stable
    assert len(bands) == 3
    # only scrutinized applications have a band; the third one is deliberately not counted
    assert sum(int(band["count"]) for band in bands) == len(scored)
    assert all(int(band["count"]) >= 0 for band in bands)


def test_a_fresh_store_omits_both_series_rather_than_reporting_zero(
    client: TestClient,
) -> None:
    """CR-3: the fields are optional, and 'nothing to plot' is shown by their absence."""
    payload = client.get("/metrics/summary").json()

    assert_valid(payload, "MetricsSummary")
    assert "applicationsByDay" not in payload
    assert "riskDistribution" not in payload
    assert payload["applicationsTotal"] == 0 and payload["flagRate"] == 0.0


def test_metrics_report_real_scrutiny_time_not_a_rounded_zero(
    client: TestClient, tmp_path: Path
) -> None:
    """`modelMeta.latencyMs` is an integer ms; sub-millisecond work rounded away to 0.0 s."""
    application_id = filed_application(client)
    client.post(f"/applications/{application_id}/scrutiny/run")

    metrics = client.get("/metrics/summary").json()
    stored = repository_module.Repository(tmp_path).get(application_id)
    payload = client.get(f"/applications/{application_id}").json()

    assert metrics["avgScrutinySeconds"] > 0.0
    assert stored["scrutinyMs"] > 0
    assert "scrutinyMs" not in payload  # internal bookkeeping; the contract does not declare it


def test_an_older_record_falls_back_to_the_latency_it_did_record() -> None:
    """Records written before the timing fix must still produce a number, not zero."""
    record: dict[str, object] = {"id": "APP-0001"}
    report = {"modelMeta": {"latencyMs": 37}}

    assert repository_module.scrutiny_ms(record, report) == 37.0
    assert repository_module.scrutiny_ms({"scrutinyMs": 0.42}, report) == 0.42
    assert repository_module.scrutiny_ms({"scrutinyMs": True}, report) == 37.0  # not a number
    assert repository_module.scrutiny_ms({}, {"modelMeta": {}}) == 0.0
