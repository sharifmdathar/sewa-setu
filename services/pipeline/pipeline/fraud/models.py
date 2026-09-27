"""Fraud scoring models: the mechanical signals behind riskScore.

These are pipeline-internal, not contract schemas: `ScrutinyReport` has no place for a signal
list, so the score reaches the officer as `riskScore` plus the C1-C5 checks' own evidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pipeline.rules.models import CamelModel

# Feature keys mirror rules.yaml -> fraudWeights, exactly; tests assert the two agree.
FraudFeature = Literal[
    "duplicateDocumentHash",
    "tamperedAmount",
    "identityDivergence",
    "expiredDocument",
    "missingDocument",
]

# Enum string copied from shared/contracts/openapi.yaml (FROZEN) - do not retype.
# Duplicated from pipeline.agent.models on purpose: pipeline/fraud must stay a leaf so
# importing it never re-enters the partially-initialised pipeline.agent package.
Recommendation = Literal["approve", "request_info", "manual_review", "reject"]


class FraudSignal(CamelModel):
    """One forgery feature the scorer found, with the values that triggered it."""

    feature: FraudFeature
    weight: int = Field(ge=0)
    detail: str


class FraudScore(CamelModel):
    """riskScore split into the two halves SPEC.md section 5 describes."""

    risk_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    flagged: bool
    check_points: float = Field(ge=0)
    signal_points: int = Field(ge=0)
    signals: list[FraudSignal] = Field(default_factory=list)
