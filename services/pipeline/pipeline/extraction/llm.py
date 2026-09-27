"""LLMExtractor: VLM/LLM document extraction over any OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from typing import Any

from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction.base import ExtractionError
from pipeline.extraction.models import CallMeta, DocumentContent, ExtractedFields
from pipeline.extraction.prompts import EXTRACTION_SYSTEM_PROMPT, extraction_user_prompt
from pipeline.llmcall import (
    EndpointNotConfigured,
    ModelCallFailed,
    complete_json,
    new_client,
)


class LLMExtractor:
    """Reads documents through a vision-capable model.

    The client is injected in tests; in production it is built lazily from the LLM_*
    environment variables. Backoff, the JSON-mode fallback and the disk cache all live in
    `pipeline.llmcall`, shared with the adjudicator.
    """

    name = "llm-vlm"

    def __init__(self, settings: LlmSettings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_llm_settings()
        self._client = client
        self._last_meta: CallMeta | None = None

    @property
    def last_meta(self) -> CallMeta | None:
        return self._last_meta

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                self._client = new_client(self.settings)
            except EndpointNotConfigured as exc:
                raise ExtractionError(f"{exc}, so LLM extraction is unavailable") from exc
        return self._client

    def extract(self, document: DocumentContent) -> ExtractedFields:
        parts = self._content_parts(document)
        client = self._ensure_client()
        try:
            result = complete_json(
                self.settings,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": parts},
                ],
                component="extractor",
                parse=lambda content: self._to_fields(content, document),
                client=client,
            )
        except ModelCallFailed as exc:
            raise ExtractionError(f"{document.file_name}: {exc}") from exc

        self._last_meta = CallMeta(
            component="extractor",
            model=result.model,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
        )
        return result.value

    def _content_parts(self, document: DocumentContent) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": extraction_user_prompt(document.doc_type)}
        ]
        if document.has_image:
            mime = document.mime_type
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{document.content_base64}"},
                }
            )
        elif document.text:
            parts.append({"type": "text", "text": f"DOCUMENT CONTENT:\n{document.text}"})
        else:
            raise ExtractionError(f"{document.file_name}: nothing to send to the model")
        return parts

    def _to_fields(self, content: str, document: DocumentContent) -> ExtractedFields:
        fields = ExtractedFields.model_validate(json.loads(content))
        return fields.model_copy(
            update={
                "raw_text": document.text or "",
                "doc_type": fields.doc_type or document.doc_type,
            }
        )
