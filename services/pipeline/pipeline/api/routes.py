"""The contract routes: every path in shared/contracts/openapi.yaml, implemented exactly.

Responses are always explicit models rather than store records, so nothing the contract does
not declare - a stored document's bytes, an internal id - can reach the wire. Failures raise
`ApiError` (see pipeline/api/errors.py), which is the only way a non-2xx leaves this router, so
every error carries a status, a machine-readable code and a string detail.
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from pipeline.agent import ScrutinyReport
from pipeline.agent import run_scrutiny as run_pipeline
from pipeline.api import catalog
from pipeline.api.errors import ApiError
from pipeline.api.models import (
    Application,
    ApplicationCreate,
    Decision,
    DecisionResult,
    Document,
    DocumentUpload,
    MetricsSummary,
    QueueItem,
    Service,
)
from pipeline.api.repository import Repository, now
from pipeline.ingestion import UploadError
from pipeline.logs import event, get_logger
from pipeline.rules import load_rule_config

LOGGER = get_logger("api")

router = APIRouter()
APPLICATION_FIELDS = (
    "id",
    "serviceId",
    "status",
    "applicantFields",
    "createdAt",
    "updatedAt",
    "timeline",
)
DOCUMENT_FIELDS = ("id", "docType", "fileName", "uploadedAt", "sha256")


def repository(request: Request) -> Repository:
    return request.app.state.repository  # type: ignore[no-any-return]

# Annotated rather than a Depends() default, which flake8-bugbear rightly flags (B008).
Repo = Annotated[Repository, Depends(repository)]


def require_record(repo: Repository, application_id: str) -> dict[str, Any]:
    record = repo.get(application_id)
    if record is None:
        raise ApiError.unknown_application(application_id)
    return record


def application_view(record: dict[str, Any]) -> Application:
    return Application.model_validate({key: record[key] for key in APPLICATION_FIELDS})


def document_view(document: dict[str, Any]) -> Document:
    return Document.model_validate({key: document[key] for key in DOCUMENT_FIELDS})


@router.get("/services", response_model=list[Service])
def list_services() -> list[Service]:
    return catalog.services()


@router.post("/applications", response_model=Application, status_code=201)
def create_application(
    body: ApplicationCreate, repo: Repo
) -> Application:
    if catalog.get(body.service_id) is None:
        raise ApiError.unknown_service(body.service_id)
    return application_view(repo.create(body.service_id, body.applicant_fields))


@router.get("/applications/{application_id}", response_model=Application)
def get_application(
    application_id: str, repo: Repo
) -> Application:
    return application_view(require_record(repo, application_id))


@router.post(
    "/applications/{application_id}/documents",
    response_model=Document,
    status_code=201,
)
def upload_document(
    application_id: str,
    body: DocumentUpload,
    repo: Repo,
) -> Document:
    record = require_record(repo, application_id)
    try:
        updated = repo.add_document(record, body.doc_type, body.file_name, body.content_base64)
    except UploadError as exc:
        raise ApiError.invalid_document(body.file_name, str(exc)) from exc
    return document_view(updated["documents"][-1])


@router.post("/applications/{application_id}/scrutiny/run", response_model=ScrutinyReport)
def run_scrutiny_for(
    application_id: str, repo: Repo
) -> ScrutinyReport:
    """Ingestion -> extraction -> rules -> adjudication -> scoring, then persisted."""
    started = time.perf_counter()  # the whole handler: intake, extraction, rules, scoring, save
    record = require_record(repo, application_id)
    if not record["documents"]:
        raise ApiError.documents_required(application_id)
    pending = repo.mark_scrutiny_pending(record)
    data, documents = repo.scrutiny_request(pending, now().date())
    report = run_pipeline(data, documents, generated_at=now())
    repo.save_report(report, scrutiny_ms=(time.perf_counter() - started) * 1000)
    event(
        LOGGER,
        "scrutiny completed",
        applicationId=report.application_id,
        riskScore=report.risk_score,
        recommendation=report.recommendation,
        checks={check.check_id: check.status for check in report.checks},
        flags=[check.check_id for check in report.checks if check.status == "fail"],
        documents=len(documents),
        extractor=report.model_meta.extractor,
        adjudicator=report.model_meta.adjudicator,
    )
    return report


@router.get("/applications/{application_id}/scrutiny", response_model=ScrutinyReport)
def latest_scrutiny(
    application_id: str, repo: Repo
) -> dict[str, Any]:
    require_record(repo, application_id)
    report = repo.get_report(application_id)
    if report is None:
        raise ApiError.scrutiny_not_run(application_id)
    return report


@router.get("/officer/queue", response_model=list[QueueItem])
def officer_queue(repo: Repo) -> list[dict[str, Any]]:
    return repo.queue()


@router.post("/officer/decisions", response_model=DecisionResult)
def record_decision(
    body: Decision, repo: Repo
) -> DecisionResult:
    record = require_record(repo, body.application_id)
    updated = repo.decide(record, body.decision, body.officer_notes)
    # The officer's verdict is the human-in-the-loop record: the agent only ever recommended.
    event(
        LOGGER,
        "officer decision",
        applicationId=body.application_id,
        decision=body.decision,
        status=updated["status"],
        riskScore=(repo.get_report(body.application_id) or {}).get("riskScore"),
    )
    return DecisionResult(applicationId=updated["id"], status=updated["status"])


@router.get(
    "/metrics/summary",
    response_model=MetricsSummary,
    # The two eval fields are optional on the contract and typed `number`, so an absent eval
    # run must drop them rather than send null.
    response_model_exclude_none=True,
)
def metrics_summary(repo: Repo) -> dict[str, Any]:
    return repo.metrics(load_rule_config(), now())
