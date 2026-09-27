"""I1 self-conformance: the frozen contract judged against a *running* server.

The other API tests use FastAPI's in-process TestClient, which cannot catch a mismatch between
what the code returns and what a real ASGI server puts on the wire (content negotiation,
serialisation, status lines). This module boots - or reuses - `uvicorn pipeline.api.main:app`
on port 8000 and validates every response against the schema its own path declares in
`shared/contracts/openapi.yaml`, including the 404s and `getScrutiny` before a run.

If something is already serving the port (the demo instance), it is reused rather than killed,
and any record this suite writes there is removed at teardown. Override with
`SEWA_CONFORMANCE_PORT` to force this suite to boot its own server on another port.
"""

from __future__ import annotations

import base64
import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from contract import assert_valid, assert_valid_response, contract_paths, response_schema
from helpers import doc_text

from pipeline.store.jsonstore import DEFAULT_ROOT

PORT = int(os.environ.get("SEWA_CONFORMANCE_PORT") or 8000)
BASE_URL = f"http://127.0.0.1:{PORT}"
PIPELINE_DIR = Path(__file__).resolve().parents[1]
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


def _health(client: httpx.Client) -> bool:
    try:
        return client.get("/healthz").status_code == 200
    except Exception:  # any transport or protocol failure means "no API here"
        return False


def _wait_ready(client: httpx.Client, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if _health(client):
            return
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited with {process.returncode}")
        time.sleep(0.25)
    raise RuntimeError("uvicorn did not answer /healthz within 25s")


def _track_created(client: httpx.Client, created: list[str]) -> None:
    """Remember every application this suite submits, so teardown deletes exactly those.

    Diffing the store directory instead would also delete anything a *real* client submitted
    while the suite ran - the demo instance is shared, so that is not a trade to make.
    """

    def hook(response: httpx.Response) -> None:
        request = response.request
        if (
            request.method == "POST"
            and request.url.path == "/applications"
            and response.status_code == 201
        ):
            # An event hook sees the response before its body is streamed in, so read first.
            with contextlib.suppress(ValueError, KeyError, httpx.ResponseNotRead):
                response.read()
                created.append(str(response.json()["id"]))

    client.event_hooks["response"].append(hook)


def _remove(root: Path, app_id: str) -> None:
    for collection in ("applications", "reports"):
        (root / collection / f"{app_id}.json").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[httpx.Client]:
    """A real HTTP client against port 8000, spawning the server only when nobody else has it."""
    created: list[str] = []
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    _track_created(client, created)
    borrowed = _health(client)
    process: subprocess.Popen[str] | None = None
    cleanup_root: Path | None = Path(DEFAULT_ROOT)

    if borrowed:
        # Only clean up a shared server we can positively identify as ours (default store, and
        # the contract's own service catalog answering) - never someone else's data directory.
        known_services = {str(entry["id"]) for entry in client.get("/services").json()}
        if known_services != {"income_certificate", "caste_certificate", "residence_certificate"}:
            cleanup_root = None
    else:
        store = tmp_path_factory.mktemp("live-api-store")
        environment = {**os.environ, "PIPELINE_VAR_DIR": str(store)}
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "pipeline.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--no-access-log",
            ],
            cwd=str(PIPELINE_DIR),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_ready(client, process)
        except Exception:
            process.terminate()
            raise

    yield client

    client.close()
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    elif cleanup_root is not None:  # exactly the applications this suite submitted
        for app_id in created:
            _remove(cleanup_root, app_id)


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


def test_metrics_summary_matches_its_schema(live: httpx.Client) -> None:
    response = live.get("/metrics/summary")

    assert response.status_code == 200
    assert_valid_response(response.json(), "get", "/metrics/summary", "200")


#: (method, contract path) pairs this module judges; {id} is filled by the fixtures above.
COVERED = {
    ("get", "/healthz"),
    ("get", "/services"),
    ("post", "/applications"),
    ("get", "/applications/{id}"),
    ("post", "/applications/{id}/documents"),
    ("post", "/applications/{id}/scrutiny/run"),
    ("get", "/applications/{id}/scrutiny"),
    ("get", "/officer/queue"),
    ("post", "/officer/decisions"),
    ("get", "/metrics/summary"),
}


def _success_status(method: str, path: str) -> str:
    responses = contract_paths()[path][method]["responses"]
    return next(str(code) for code in responses if str(code).startswith("2"))


def test_no_contract_path_goes_unjudged() -> None:
    """A path added to the contract without a test here must fail this, not pass silently."""
    declared = {
        (method, path)
        for path, operations in contract_paths().items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }

    untested = declared - COVERED
    vanished = COVERED - declared
    assert not untested, f"contract paths with no live test - add one each: {sorted(untested)}"
    assert not vanished, f"tests judge paths no longer in the contract: {sorted(vanished)}"
    for method, path in sorted(COVERED - {("get", "/healthz")}):
        status = _success_status(method, path)
        assert isinstance(response_schema(method, path, status), dict), (method, path, status)
