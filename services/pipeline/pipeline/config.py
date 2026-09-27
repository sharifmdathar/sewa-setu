"""Environment configuration. Secrets come from the environment only (never committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LLM_TIMEOUT_SECONDS = 30
LLM_MAX_RETRIES = 2

# Exponential backoff between attempts: 1 s, 2 s, 4 s ... capped at 30 s, plus jitter.
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0

# Documents in one application are read concurrently, because each read is a network round trip
# and an application averages 4.6 of them. Bounded so one big filing cannot monopolise a
# rate-limited free-tier key.
MAX_CONCURRENCY = 4

# Lives under the var/ dir on purpose: cached model output is derived data, never a source
# file, and it can be several hundred entries. `store.jsonstore` keeps the JSON store there.
VAR_DIR_ENV_VAR = "PIPELINE_VAR_DIR"
DEFAULT_VAR_DIR = Path(__file__).resolve().parents[1] / "var"
DEFAULT_CACHE_DIR_NAME = "llm-cache"
_CACHE_DISABLE_VALUES = frozenset({"0", "false", "no", "off"})


def default_cache_dir(env: dict[str, str] | None = None) -> Path:
    """<var dir>/llm-cache, where <var dir> honours PIPELINE_VAR_DIR like the JSON store."""
    source = os.environ if env is None else env
    root = Path(source.get(VAR_DIR_ENV_VAR) or DEFAULT_VAR_DIR)
    return root / DEFAULT_CACHE_DIR_NAME



@dataclass(frozen=True)
class LlmSettings:
    """OpenAI-compatible endpoint settings (ARCHITECTURE.md: 30 s timeout, 2 retries)."""

    base_url: str | None
    api_key: str | None
    model: str
    timeout_seconds: float = LLM_TIMEOUT_SECONDS
    max_retries: int = LLM_MAX_RETRIES
    backoff_base_seconds: float = BACKOFF_BASE_SECONDS
    backoff_cap_seconds: float = BACKOFF_CAP_SECONDS
    max_concurrency: int = MAX_CONCURRENCY
    cache_dir: Path | None = None
    cache_enabled: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def resolved_cache_dir(self) -> Path:
        """Resolved lazily so a test that sets PIPELINE_VAR_DIR after import still works."""
        return self.cache_dir or default_cache_dir()


def _number(source: dict[str, str], name: str, default: float) -> float:
    raw = (source.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _integer(source: dict[str, str], name: str, default: int) -> int:
    return max(1, int(_number(source, name, float(default))))


def get_llm_settings(env: dict[str, str] | None = None) -> LlmSettings:
    source = os.environ if env is None else env
    override = (source.get("LLM_CACHE_DIR") or "").strip()
    return LlmSettings(
        base_url=source.get("LLM_BASE_URL") or None,
        api_key=source.get("LLM_API_KEY") or None,
        model=source.get("LLM_MODEL") or "gpt-4o-mini",
        backoff_base_seconds=_number(
            source, "LLM_BACKOFF_BASE_SECONDS", BACKOFF_BASE_SECONDS
        ),
        backoff_cap_seconds=_number(source, "LLM_BACKOFF_CAP_SECONDS", BACKOFF_CAP_SECONDS),
        max_concurrency=_integer(source, "LLM_MAX_CONCURRENCY", MAX_CONCURRENCY),
        cache_dir=Path(override) if override else None,
        cache_enabled=(source.get("LLM_CACHE") or "1").strip().lower()
        not in _CACHE_DISABLE_VALUES,
    )
