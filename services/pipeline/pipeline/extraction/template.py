"""TemplateExtractor: reads the strict `KEY: value` synthetic document templates."""

from __future__ import annotations

import datetime as dt

from pipeline.extraction.base import ExtractionError
from pipeline.extraction.models import CallMeta, DocumentContent, ExtractedFields

FIELD_KEYS = {
    "DOC_TYPE": "doc_type",
    "FULL_NAME": "name",
    "AADHAAR_NUMBER": "id_number",
    "ISSUE_DATE": "issue_date",
    "EXPIRY_DATE": "expiry_date",
    "ISSUING_AUTHORITY": "issuing_authority",
}
AMOUNT_KEY = "AMOUNT_INR"


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_amount(value: str) -> int | None:
    cleaned = value.replace(",", "").replace("\u20b9", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def iter_keyed_lines(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().upper()
        if key in FIELD_KEYS or key == AMOUNT_KEY:
            pairs.append((key, value.strip()))
    return pairs


class TemplateExtractor:
    """Deterministic extractor for templated text documents (no model calls)."""

    name = "template"

    def __init__(self) -> None:
        self._last_meta: CallMeta | None = None

    @property
    def last_meta(self) -> CallMeta | None:
        return self._last_meta

    def extract(self, document: DocumentContent) -> ExtractedFields:
        if not document.text:
            raise ExtractionError(f"{document.file_name}: no text layer to template-parse")

        raw: dict[str, object] = {}
        amounts: list[int] = []
        for key, value in iter_keyed_lines(document.text):
            if key == AMOUNT_KEY:
                amount = parse_amount(value)
                if amount is not None:
                    amounts.append(amount)
                continue
            field_name = FIELD_KEYS[key]
            if field_name in {"issue_date", "expiry_date"}:
                raw[field_name] = parse_date(value)
            elif field_name not in raw:
                raw[field_name] = value

        fields = ExtractedFields(
            doc_type=str(raw.get("doc_type") or document.doc_type),
            name=raw.get("name"),
            id_number=raw.get("id_number"),
            issue_date=raw.get("issue_date"),
            expiry_date=raw.get("expiry_date"),
            issuing_authority=raw.get("issuing_authority"),
            amounts=amounts,
            raw_text=document.text,
        )
        if not fields.legible:
            raise ExtractionError(f"{document.file_name}: unreadable document (no identity fields)")
        return fields
