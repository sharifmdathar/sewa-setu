"""Thread-safe JSON file store for applications and scrutiny reports.

Layout under the store root (default: ``services/pipeline/var``):

    var/applications/<id>.json
    var/reports/<applicationId>.json

Each record is one file, written atomically, so concurrent readers never see a
partially written document.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

COLLECTIONS = ("applications", "reports")
_KEY_FIELD = {"applications": "id", "reports": "applicationId"}

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "var"
ROOT_ENV_VAR = "PIPELINE_VAR_DIR"


def _default_root() -> Path:
    return Path(os.environ.get(ROOT_ENV_VAR) or DEFAULT_ROOT)


class JsonStore:
    """File-backed key/value store, safe for use from multiple threads."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        for name in COLLECTIONS:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        # One process-wide lock is enough at POC scale; file writes are tiny.
        self._lock = threading.RLock()

    def _directory(self, collection: str) -> Path:
        if collection not in COLLECTIONS:
            raise ValueError(f"unknown collection {collection!r}, expected one of {COLLECTIONS}")
        return self.root / collection

    def _path(self, collection: str, record_id: str) -> Path:
        directory = self._directory(collection)
        if not record_id or Path(record_id).name != record_id:
            raise ValueError(f"invalid record id {record_id!r}")
        return directory / f"{record_id}.json"

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        """Return one record, or None when it does not exist."""
        path = self._path(collection, record_id)
        with self._lock:
            if not path.is_file():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def put(self, collection: str, record: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a record, keyed by its contract id field."""
        key_field = _KEY_FIELD[collection]
        record_id = record.get(key_field)
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"record is missing non-empty string field {key_field!r}")
        path = self._path(collection, record_id)
        payload = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True)
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        return record

    def list(self, collection: str) -> list[dict[str, Any]]:
        """Return every record in a collection, ordered by file name."""
        directory = self._directory(collection)
        with self._lock:
            records = [
                json.loads(file.read_text(encoding="utf-8"))
                for file in sorted(directory.glob("*.json"))
            ]
        return records

    def delete(self, collection: str, record_id: str) -> bool:
        """Remove a record; returns whether anything was deleted."""
        path = self._path(collection, record_id)
        with self._lock:
            if not path.is_file():
                return False
            path.unlink()
            return True
