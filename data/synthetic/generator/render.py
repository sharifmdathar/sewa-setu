"""Renders corpus documents to PNG so the vision path has real pixels to read.

SPEC.md section 6 promises `docs/*.txt|png`. This writes that image leg into `docs_img/`
beside the text corpus and never replaces it: `applications.json` and `ground_truth.json` go
on pointing at the `.txt` files, so every existing test and eval pass sees exactly the corpus
it saw before. What the image leg adds is a set of documents whose field values are already
known, which is what turns "did the model read this correctly" into a measured question.

Be honest about what this corpus is: clean text rendered to an image, not a phone photo of a
paper document. It exercises the base64 data-URI path and measures read-back accuracy; it
does not measure skew, glare, or low-DPI robustness, and the submission should not claim that.

Pillow is an optional dependency (`pip install -e data/synthetic[images]`) and is imported
inside the functions that need it, because generating the text corpus must never require a
graphics library.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from generator.model import AppRecord, Doc

IMAGE_DIR = "docs_img"
MANIFEST_FILE = "image_manifest.json"

CANVAS_WIDTH = 880
MARGIN = 48
LINE_HEIGHT = 26
FONT_SIZE = 18


def _font(size: int) -> Any:
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:  # pragma: no cover - older Pillow
        return ImageFont.load_default()


def render_png(content: str) -> bytes:
    """Lay a document's `KEY: value` lines on a white canvas and return PNG bytes."""
    from PIL import Image, ImageDraw

    lines = [line.rstrip() for line in content.splitlines()] or [""]
    height = MARGIN * 2 + LINE_HEIGHT * len(lines)
    canvas = Image.new("RGB", (CANVAS_WIDTH, height), "white")
    draw = ImageDraw.Draw(canvas)
    font = _font(FONT_SIZE)
    for index, line in enumerate(lines):
        draw.text((MARGIN, MARGIN + LINE_HEIGHT * index), line, fill="black", font=font)
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def expected_fields(doc: Doc) -> dict[str, Any]:
    """The values a correct read of this document must return, in the extractor's vocabulary."""
    values = doc.values
    return {
        "docType": values.doc_type,
        "name": values.full_name,
        "idNumber": values.aadhaar_number,
        "issueDate": values.issue_date,
        "expiryDate": values.expiry_date,
        "issuingAuthority": values.authority,
        "amounts": [values.amount_inr] if values.amount_inr is not None else [],
    }


def pick_documents(apps: list[AppRecord], count: int) -> list[tuple[AppRecord, Doc]]:
    """Take documents round-robin across doc types, so a small leg still spans the shapes.

    Deterministic by construction: types are sorted and each type's documents stay in
    application order, so the same corpus and count always select the same files.
    """
    by_type: dict[str, list[tuple[AppRecord, Doc]]] = {}
    for app in apps:
        for doc in app.docs:
            by_type.setdefault(doc.doc_type, []).append((app, doc))
    queues = [by_type[name] for name in sorted(by_type)]
    picked: list[tuple[AppRecord, Doc]] = []
    while len(picked) < count and any(queues):
        for queue in queues:
            if queue and len(picked) < count:
                picked.append(queue.pop(0))
    return picked


def write_image_leg(apps: list[AppRecord], out_dir: str | Path, count: int) -> dict[str, Any]:
    """Render `count` documents into `<out_dir>/docs_img/` and return their manifest."""
    if count <= 0:
        return {"documents": [], "count": 0}
    directory = Path(out_dir) / IMAGE_DIR
    if directory.exists():
        for stale in directory.iterdir():
            if stale.suffix in (".png",):
                stale.unlink()
    directory.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for app, doc in pick_documents(apps, count):
        image_name = Path(doc.file_name).with_suffix(".png").name
        payload = render_png(doc.content)
        (directory / image_name).write_bytes(payload)
        entries.append(
            {
                "applicationId": app.application_id,
                "serviceId": app.service_id,
                "documentId": doc.document_id,
                "docType": doc.doc_type,
                "textFileName": doc.file_name,
                "imageFileName": image_name,
                "sha256": doc.sha256,
                "anomalies": sorted(app.anomalies),
                "expectedFields": expected_fields(doc),
            }
        )

    manifest = {
        "count": len(entries),
        "imageDir": IMAGE_DIR,
        "note": "rendered text, not a scan: measures model read-back, not camera robustness",
        "documents": entries,
    }
    (Path(out_dir) / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
