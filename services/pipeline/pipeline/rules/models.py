"""Rule engine data models: contract check objects plus the engine's input."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from pipeline.extraction.models import ExtractedFields

# Enum strings copied from shared/contracts/openapi.yaml (FROZEN) - do not retype.
CheckStatus = Literal["pass", "fail", "warn", "info"]
CheckSeverity = Literal["low", "medium", "high"]


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase on the wire (contract style)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ScrutinyCheck(CamelModel):
    """openapi.yaml -> ScrutinyCheck."""

    check_id: str
    label: str
    status: CheckStatus
    severity: CheckSeverity
    evidence: str
    explanation: str


class DocEvidence(CamelModel):
    """One document's metadata together with what the extractor read from it."""

    document_id: str
    doc_type: str
    file_name: str
    sha256: str
    uploaded_at: dt.datetime | None = None
    fields: ExtractedFields


class ScrutinyInput(CamelModel):
    """Everything the pure rule functions need for one application."""

    application_id: str
    service_id: str
    required_doc_types: list[str] = Field(default_factory=list)
    applicant_fields: dict[str, Any] = Field(default_factory=dict)
    documents: list[DocEvidence] = Field(default_factory=list)
    # sha256 values also present in *other* applications (corpus-wide index).
    duplicate_sha256: list[str] = Field(default_factory=list)
    as_of: dt.date

    def declared_amount(self) -> int | None:
        value = self.applicant_fields.get("annualIncomeInr")
        if value is None:
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return None

    def declared_name(self) -> str | None:
        value = self.applicant_fields.get("fullName")
        return str(value) if value else None

    def declared_id_number(self) -> str | None:
        value = self.applicant_fields.get("aadhaarNumber")
        return str(value) if value else None


class CheckConfig(CamelModel):
    """Per-check weight and severity, read from rules.yaml."""

    label: str
    weight: int
    fail_severity: CheckSeverity = "medium"
    warn_severity: CheckSeverity = "low"


class RuleConfig(CamelModel):
    """openapi-free tuning file (rules/rules.yaml)."""

    version: int
    flag_threshold: int
    clean_ceiling: int
    checks: dict[str, CheckConfig]
    fraud_weights: dict[str, int]
    severity_multipliers: dict[str, float]
    recommendation_thresholds: dict[str, int]
    authority_expectations: dict[str, str] = Field(default_factory=dict)
