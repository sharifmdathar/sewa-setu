"""Report models: the contract's ScrutinyReport plus its modelMeta block."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from pipeline.rules.models import CamelModel, CheckStatus, ScrutinyCheck

# Enum strings copied from shared/contracts/openapi.yaml (FROZEN) - do not retype.
Recommendation = Literal["approve", "request_info", "manual_review", "reject"]


class ModelMeta(CamelModel):
    """openapi.yaml -> ScrutinyReport.modelMeta."""

    extractor: str
    adjudicator: str
    latency_ms: int = Field(ge=0)
    versions: dict[str, str] = Field(default_factory=dict)


class ScrutinyReport(CamelModel):
    """openapi.yaml -> ScrutinyReport."""

    application_id: str
    generated_at: dt.datetime
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    checks: list[ScrutinyCheck]
    risk_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    model_meta: ModelMeta


class Adjudication(BaseModel):
    """One adjudicator verdict: the final status plus the officer-facing wording."""

    status: CheckStatus
    explanation: str
