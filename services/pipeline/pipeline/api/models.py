"""Request and response models, one per component of shared/contracts/openapi.yaml.

Every enum string below is copied from the frozen contract rather than retyped from memory,
and the shapes are asserted against the YAML itself in tests/test_api_contract.py. Field names
are snake_case in Python and camelCase on the wire (`CamelModel`), which is the contract's style.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from pipeline.rules.models import CamelModel

# Enum strings copied from shared/contracts/openapi.yaml (FROZEN) - do not retype.
AppStatus = Literal[
    "submitted",
    "documents_uploaded",
    "scrutiny_pending",
    "scrutiny_done",
    "decided",
    "info_requested",
]
TimelineActor = Literal["citizen", "system", "officer"]
OfficerDecision = Literal["approve", "reject", "request_info"]


class Service(CamelModel):
    """openapi.yaml -> Service. `field_schema` drives the citizen form's dynamic fields."""

    id: str
    name: str
    required_doc_types: list[str]
    field_schema: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(CamelModel):
    """openapi.yaml -> TimelineEvent."""

    at: dt.datetime
    actor: TimelineActor
    event: str
    message: str


class Application(CamelModel):
    """openapi.yaml -> Application, as returned by GET /applications/{id}."""

    id: str
    service_id: str
    status: AppStatus
    applicant_fields: dict[str, Any]
    created_at: dt.datetime
    updated_at: dt.datetime
    timeline: list[TimelineEvent]


class Document(CamelModel):
    """openapi.yaml -> Document. The bytes themselves stay in the store, never on the wire."""

    id: str
    doc_type: str
    file_name: str
    uploaded_at: dt.datetime
    sha256: str


class ApplicationCreate(CamelModel):
    """openapi.yaml -> POST /applications request body."""

    service_id: str
    applicant_fields: dict[str, Any]


class DocumentUpload(CamelModel):
    """openapi.yaml -> POST /applications/{id}/documents request body."""

    doc_type: str
    file_name: str
    content_base64: str


class Decision(CamelModel):
    """openapi.yaml -> Decision."""

    application_id: str
    decision: OfficerDecision
    officer_notes: str


class DecisionResult(CamelModel):
    """openapi.yaml -> POST /officer/decisions response ({applicationId, status})."""

    application_id: str
    status: AppStatus


class QueueItem(CamelModel):
    """openapi.yaml -> QueueItem, one application waiting on an officer."""

    application_id: str
    service_id: str
    status: AppStatus
    risk_score: int
    updated_at: dt.datetime


class DailyCount(CamelModel):
    """openapi.yaml -> MetricsSummary.applicationsByDay item."""

    date: dt.date
    count: int = Field(ge=0)


class RiskBandCount(CamelModel):
    """openapi.yaml -> MetricsSummary.riskDistribution item (SPEC.md section 7 bands)."""

    band: Literal["low", "medium", "high"]
    count: int = Field(ge=0)


class MetricsSummary(CamelModel):
    """openapi.yaml -> MetricsSummary. evalPrecision/Recall appear once A8's report exists."""

    applications_total: int
    pending: int
    decided: int
    avg_scrutiny_seconds: float
    flag_rate: float
    generated_at: dt.datetime
    eval_precision: float | None = None
    eval_recall: float | None = None
    applications_by_day: list[DailyCount] | None = None
    risk_distribution: list[RiskBandCount] | None = None
