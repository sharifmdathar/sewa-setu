"""Dataset writer: applications.json, ground_truth.json and docs/*.txt."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from generator.model import AppRecord

APPLICATIONS_FILE = "applications.json"
GROUND_TRUTH_FILE = "ground_truth.json"
DOCS_DIR = "docs"


def _dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_dataset(
    apps: list[AppRecord], ground_truth: dict[str, Any], out_dir: str | Path
) -> Path:
    """Write the corpus under out_dir (replacing any previous corpus) and return it."""
    out = Path(out_dir)
    docs_dir = out / DOCS_DIR
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    for app in apps:
        for doc in app.docs:
            target = docs_dir / doc.file_name
            target.write_text(doc.content, encoding="utf-8")
            if hashlib.sha256(target.read_bytes()).hexdigest() != doc.sha256:
                raise AssertionError(f"written doc {doc.file_name} does not match its hash")

    _dump(out / APPLICATIONS_FILE, [app.as_application() for app in apps])
    _dump(out / GROUND_TRUTH_FILE, ground_truth)
    return out
