"""Extractor protocol shared by the template and LLM implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline.extraction.models import CallMeta, DocumentContent, ExtractedFields


class ExtractionError(RuntimeError):
    """Raised when a document cannot be read at all (corrupt, empty, unusable)."""


@runtime_checkable
class DocumentExtractor(Protocol):
    """Turns one document into ExtractedFields.

    `last_meta` reports the most recent model call (None for pure-code extractors)
    so the adjudicator can assemble the report's modelMeta.
    """

    name: str

    @property
    def last_meta(self) -> CallMeta | None: ...

    def extract(self, document: DocumentContent) -> ExtractedFields: ...
