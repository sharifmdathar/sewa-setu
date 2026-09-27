"""The live benchmark's own parts: the statistics, and its two HTTP helpers.

`main()` needs a socket, so it is exercised by hand (`docs/track-a/i4-demo-rehearsal.md`); what is
tested here is everything the numbers are built from. A `TestClient` keeps that in-process: the
same route code, no port and no network.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from contract import assert_valid
from fastapi.testclient import TestClient
from helpers import doc_text

from pipeline.api.main import create_app
from pipeline.scripts.bench_scrutiny import NoServer, Sample, filing, run, summarise

FIELDS: dict[str, Any] = {
    "fullName": "Anita Baruah",
    "aadhaarNumber": "4123 8890 1177",
    "annualIncomeInr": 180000,
}


def sample(seconds: float, application_id: str = "APP-1") -> Sample:
    return Sample(application_id, 3, seconds, "approve")


def test_the_summary_is_a_distribution_and_a_verdict() -> None:
    summary = summarise([sample(1.0) for _ in range(9)] + [sample(50.0)])

    assert summary["runs"] == 10 and summary["applications"] == 1
    assert summary["minSeconds"] == 1.0 and summary["maxSeconds"] == 50.0
    assert summary["p50Seconds"] == 1.0 and summary["p95Seconds"] == 50.0
    assert summary["meanSeconds"] == 5.9
    assert summary["applicationsPerMinute"] == round(60 / 5.9)
    assert summary["targetMet"] is True  # the target is per application, not per batch


def test_one_run_over_the_target_fails_the_whole_measurement() -> None:
    summary = summarise([sample(0.5), sample(61.0)], target_seconds=60.0)

    assert summary["targetMet"] is False and summary["p50Seconds"] == 0.5


def test_the_counted_applications_are_the_distinct_ones(tmp_path: Path) -> None:
    summary = summarise([sample(1.0, "APP-1"), sample(1.0, "APP-2"), sample(1.0, "APP-1")])

    assert summary["runs"] == 3 and summary["applications"] == 2


@pytest.fixture()
def asgi(tmp_path: Path) -> TestClient:
    """A `TestClient` is an `TestClient`, which is all the bench's helpers ask for."""
    return TestClient(create_app(tmp_path))


def file_application(client: TestClient, documents: int) -> str:
    created = client.post(
        "/applications", json={"serviceId": "income_certificate", "applicantFields": FIELDS}
    )
    application_id = str(created.json()["id"])
    for number in range(documents):
        client.post(
            f"/applications/{application_id}/documents",
            json={
                "docType": "aadhaar",
                "fileName": f"a{number}.txt",
                "contentBase64": base64.b64encode(
                    doc_text("aadhaar", authority="Unique Fictiona Identity Authority").encode(
                        "utf-8"
                    )
                ).decode("ascii"),
            },
        )
    return application_id


def test_filing_keeps_only_applications_with_documents(asgi: TestClient) -> None:
    with_docs = file_application(asgi, 2)
    without_docs = file_application(asgi, 0)

    assert filing(asgi, [without_docs, with_docs]) == [(with_docs, 2)]


def test_run_times_every_scrutiny_and_carries_the_verdict(asgi: TestClient) -> None:
    with_docs = file_application(asgi, 1)

    samples = run(asgi, [(with_docs, 1)], repeat=2)

    assert len(samples) == 2
    assert {sample.documents for sample in samples} == {1}
    assert all(sample.seconds > 0 for sample in samples)
    assert all(sample.application_id == with_docs for sample in samples)
    assert {sample.recommendation for sample in samples} <= {
        "approve",
        "request_info",
        "reject",
    }
    assert summarise(samples)["targetMet"] is True


def test_an_application_that_cannot_be_scrutinized_stops_the_bench(asgi: TestClient) -> None:
    empty = file_application(asgi, 0)

    with pytest.raises(NoServer):
        run(asgi, [(empty, 0)], repeat=1)


def test_the_bench_reports_a_real_contract_scrutiny(asgi: TestClient) -> None:
    """The artifact's `measured` block is a ScrutinyReport, not a summary of its own."""
    from pipeline.scripts.bench_scrutiny import report

    with_docs = file_application(asgi, 1)
    samples = run(asgi, [(with_docs, 1)], repeat=1)

    measured = report(asgi, samples)

    stored = asgi.get(f"/applications/{with_docs}/scrutiny").json()
    assert_valid(stored, "ScrutinyReport")  # ModelMeta is inline on the contract, not a component
    assert measured["modelMeta"] == stored["modelMeta"]
    assert measured["applicationId"] == with_docs
    assert measured["modelMeta"]["extractor"] == "template"
    assert set(measured["checks"]) == {"C1", "C2", "C3", "C4", "C5"}
    assert measured["serverAvgScrutinySeconds"] > 0.0
