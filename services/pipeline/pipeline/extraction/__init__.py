"""Document extraction: template parsing and VLM-backed extraction."""

from __future__ import annotations

from pipeline.extraction.base import DocumentExtractor, ExtractionError
from pipeline.extraction.llm import LLMExtractor
from pipeline.extraction.models import CallMeta, DocumentContent, ExtractedFields
from pipeline.extraction.template import TemplateExtractor

__all__ = [
    "CallMeta",
    "DocumentContent",
    "DocumentExtractor",
    "ExtractionError",
    "ExtractedFields",
    "LLMExtractor",
    "TemplateExtractor",
]
