"""Extraction input/output models."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DocumentContent(BaseModel):
    """One uploaded document as the pipeline receives it (before/after ingestion)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    document_id: str
    doc_type: str
    file_name: str
    mime_type: str = "text/plain"
    text: str | None = None
    content_base64: str | None = None

    @property
    def has_image(self) -> bool:
        return self.content_base64 is not None and self.mime_type.startswith("image/")


class ExtractedFields(BaseModel):
    """Fields read out of one document. Optional because partial reads are real:
    a missing value is a finding for the rules engine, not an extraction crash.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_type: str | None = None
    name: str | None = None
    id_number: str | None = None
    issue_date: dt.date | None = None
    expiry_date: dt.date | None = None
    issuing_authority: str | None = None
    amounts: list[int] = Field(default_factory=list)
    raw_text: str = ""

    @property
    def legible(self) -> bool:
        """True when the document yielded at least an identity value worth checking."""
        return bool(self.name or self.id_number)

    def as_json(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude={"raw_text"})


class CallMeta(BaseModel):
    """Bookkeeping for one LLM call, folded into the report's modelMeta."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    component: str
    model: str
    latency_ms: int
    attempts: int = 1
