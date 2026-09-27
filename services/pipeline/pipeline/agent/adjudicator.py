"""Adjudicators: settle warn/ambiguous rule verdicts and rewrite them in plain language."""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from pipeline.agent.models import Adjudication
from pipeline.agent.prompts import ADJUDICATION_SYSTEM_PROMPT, adjudication_user_prompt
from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction.models import CallMeta
from pipeline.llmcall import (
    EndpointNotConfigured,
    ModelCallFailed,
    complete_json,
    new_client,
)
from pipeline.rules.models import CheckStatus, ScrutinyCheck, ScrutinyInput

# Statuses the rules engine is allowed to hand to the adjudicator.
AMBIGUOUS_STATUSES: tuple[CheckStatus, ...] = ("warn", "info")


class AdjudicationError(RuntimeError):
    """Raised when the adjudicator could not produce a usable verdict."""


@runtime_checkable
class Adjudicator(Protocol):
    """Something that turns one ambiguous check into a final status + wording."""

    name: str

    @property
    def last_meta(self) -> CallMeta | None: ...

    def adjudicate(self, check: ScrutinyCheck, data: ScrutinyInput) -> Adjudication: ...


class DeterministicAdjudicator:
    """No-model fallback: keeps the rule's status and states it in officer language.

    It never overturns a verdict - with no adjudication model configured, the only
    honest answer is the deterministic one the rules engine already produced.
    """

    name = "deterministic"

    @property
    def last_meta(self) -> CallMeta | None:
        return None

    def adjudicate(self, check: ScrutinyCheck, data: ScrutinyInput) -> Adjudication:
        return Adjudication(status=check.status, explanation=plain_language(check))


def plain_language(check: ScrutinyCheck) -> str:
    """Prefix the rule's own explanation with what it means for the officer."""
    lead = {
        "pass": "No action needed.",
        "fail": "This application needs attention.",
        "warn": "An officer should look at this before deciding.",
        "info": "This could not be verified from the uploaded documents.",
    }[check.status]
    return f"{lead} {check.explanation}"


class LLMAdjudicator:
    """Asks an OpenAI-compatible model for a structured verdict on one ambiguous check.

    Retrying, the JSON-mode fallback and the disk cache live in `pipeline.llmcall`, shared
    with the extractor, so a rate-limited endpoint degrades the same way in both places.
    """

    name = "llm-adjudicator"

    def __init__(self, settings: LlmSettings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_llm_settings()
        self._client = client
        self._last_meta: CallMeta | None = None

    @property
    def last_meta(self) -> CallMeta | None:
        return self._last_meta

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                self._client = new_client(self.settings)
            except EndpointNotConfigured as exc:
                raise AdjudicationError(f"{exc}, so LLM adjudication is unavailable") from exc
        return self._client

    def adjudicate(self, check: ScrutinyCheck, data: ScrutinyInput) -> Adjudication:
        client = self._ensure_client()
        try:
            result = complete_json(
                self.settings,
                messages=[
                    {"role": "system", "content": ADJUDICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": adjudication_user_prompt(check, data)},
                ],
                component="adjudicator",
                parse=verdict_from_json,
                client=client,
            )
        except ModelCallFailed as exc:
            raise AdjudicationError(f"{check.check_id}: {exc}") from exc

        self._last_meta = CallMeta(
            component="adjudicator",
            model=result.model,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
        )
        return result.value


def verdict_from_json(content: str) -> Adjudication:
    """`status` is a contract Literal, so pydantic already rejects non-enum values."""
    return Adjudication.model_validate(json.loads(content))
