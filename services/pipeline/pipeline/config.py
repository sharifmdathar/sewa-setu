"""Environment configuration. Secrets come from the environment only (never committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass

LLM_TIMEOUT_SECONDS = 30
LLM_MAX_RETRIES = 2


@dataclass(frozen=True)
class LlmSettings:
    """OpenAI-compatible endpoint settings (ARCHITECTURE.md: 30 s timeout, 2 retries)."""

    base_url: str | None
    api_key: str | None
    model: str
    timeout_seconds: float = LLM_TIMEOUT_SECONDS
    max_retries: int = LLM_MAX_RETRIES

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def get_llm_settings(env: dict[str, str] | None = None) -> LlmSettings:
    source = os.environ if env is None else env
    return LlmSettings(
        base_url=source.get("LLM_BASE_URL") or None,
        api_key=source.get("LLM_API_KEY") or None,
        model=source.get("LLM_MODEL") or "gpt-4o-mini",
    )
