"""Adjudicators: settle warn/ambiguous rule verdicts and rewrite them in plain language."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from pipeline.agent.models import Adjudication
from pipeline.agent.prompts import ADJUDICATION_SYSTEM_PROMPT, adjudication_user_prompt
from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction.models import CallMeta
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
    """Asks an OpenAI-compatible model for a structured verdict on one ambiguous check."""

    name = "llm-adjudicator"

    def __init__(self, settings: LlmSettings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_llm_settings()
        self._client = client
        self._last_meta: CallMeta | None = None

    @property
    def last_meta(self) -> CallMeta | None:
        return self._last_meta

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.settings.enabled:
            raise AdjudicationError("LLM_API_KEY is not set, so LLM adjudication is unavailable")
        from openai import OpenAI

        self._client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            timeout=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
        )
        return self._client

    def adjudicate(self, check: ScrutinyCheck, data: ScrutinyInput) -> Adjudication:
        client = self._ensure_client()
        messages = [
            {"role": "system", "content": ADJUDICATION_SYSTEM_PROMPT},
            {"role": "user", "content": adjudication_user_prompt(check, data)},
        ]
        last_error = "no response"

        for attempt in range(1, self.settings.max_retries + 2):
            started = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=self.settings.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
            except Exception as exc:  # openai raises many unrelated error types
                raise AdjudicationError(f"{check.check_id}: LLM call failed: {exc}") from exc

            latency_ms = int(round((time.perf_counter() - started) * 1000))
            try:
                verdict = self._to_verdict(response)
            except (json.JSONDecodeError, ValidationError, AttributeError, TypeError) as exc:
                last_error = str(exc)
                continue

            self._last_meta = CallMeta(
                component="adjudicator",
                model=getattr(response, "model", None) or self.settings.model,
                latency_ms=latency_ms,
                attempts=attempt,
            )
            return verdict

        raise AdjudicationError(f"{check.check_id}: unusable adjudicator payload ({last_error})")

    def _to_verdict(self, response: Any) -> Adjudication:
        payload = json.loads(response.choices[0].message.content)
        # `status` is a contract Literal, so pydantic already rejects non-enum values.
        return Adjudication.model_validate(payload)
