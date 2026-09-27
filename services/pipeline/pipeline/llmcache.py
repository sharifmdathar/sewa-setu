"""Disk cache for model completions, so a re-run of a long eval pass costs zero calls.

Why this exists: a $0 API key allows roughly fifty requests a day, and the corpus is 917
documents. Without a cache, a run that dies on attempt 300 has spent all 300 calls and has
nothing to show for it. With one, the second pass resumes and only pays for what is missing.

Entries are keyed by the full request (model, messages, whether JSON mode was sent), so
changing the prompt or the model can never read someone else's cached answer. A corrupt or
unreadable entry is treated as a miss rather than an error: the cache must never be the
reason a scrutiny run fails.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from pipeline.config import LlmSettings

CACHE_VERSION = 1
_COUNTERS = ("hits", "misses", "writes", "errors")


class CacheStats:
    """Mutable counters, reported in the eval payload so a cached run is visible as one.

    Guarded because documents in one application are now read concurrently, and `x += 1` is a
    read-modify-write that loses increments under a race.
    """

    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.errors = 0
        self._lock = threading.Lock()

    def count(self, name: str) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + 1)

    def as_dict(self) -> dict[str, int]:
        with self._lock:
            return {name: getattr(self, name) for name in _COUNTERS}

    @property
    def calls_avoided(self) -> int:
        return self.hits


class ResponseCache:
    """One JSON file per request key under `directory`."""

    def __init__(self, directory: Path, *, enabled: bool = True) -> None:
        self.directory = Path(directory)
        self.enabled = enabled
        self.stats = CacheStats()

    @staticmethod
    def key_of(
        *, model: str, messages: list[dict[str, Any]], json_mode: bool, temperature: float
    ) -> str:
        blob = json.dumps(
            {
                "v": CACHE_VERSION,
                "model": model,
                "messages": messages,
                "jsonMode": json_mode,
                "temperature": temperature,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> str | None:
        """The cached message content, or None on a miss (including when disabled)."""
        if not self.enabled:
            return None
        try:
            payload = json.loads(self.path_for(key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.stats.count("misses")
            return None
        except (OSError, ValueError):
            self.stats.count("errors")
            return None
        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, str):
            self.stats.count("errors")
            return None
        self.stats.count("hits")
        return content

    def put(self, key: str, *, content: str, model: str) -> None:
        if not self.enabled:
            return
        record = {"key": key, "model": model, "version": CACHE_VERSION, "content": content}
        temp: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(dir=str(self.directory), suffix=".tmp")
            temp = Path(name)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False)
            os.replace(temp, self.path_for(key))
            temp = None
            self.stats.count("writes")
        except OSError:
            self.stats.count("errors")
        finally:
            if temp is not None:
                with contextlib.suppress(OSError):
                    temp.unlink()


_CACHES: dict[str, ResponseCache] = {}
_CACHES_LOCK = threading.Lock()


def cache_for(settings: LlmSettings) -> ResponseCache:
    """The process-wide cache for a settings' directory (one per dir, so stats aggregate)."""
    directory = str(settings.resolved_cache_dir)
    with _CACHES_LOCK:
        found = _CACHES.get(directory)
        if found is None:
            found = ResponseCache(Path(directory), enabled=settings.cache_enabled)
            _CACHES[directory] = found
        return found


def combined_stats() -> dict[str, int]:
    """Summed hit/miss/write counts across every cache this process has used."""
    total = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}
    with _CACHES_LOCK:
        caches = list(_CACHES.values())
    for cache in caches:
        for name, value in cache.stats.as_dict().items():
            total[name] += value
    return total


def reset_caches() -> None:
    """Drop every cached instance (tests, or a settings change mid-process)."""
    with _CACHES_LOCK:
        _CACHES.clear()
