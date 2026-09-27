"""LLMExtractor: VLM/LLM document extraction over any OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import ValidationError

from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction.base import ExtractionError
from pipeline.extraction.models import CallMeta, DocumentContent, ExtractedFields
from pipeline.extraction.prompts import EXTRACTION_SYSTEM_PROMPT, extraction_user_prompt


class LLMExtractor:
    """Reads documents through a vision-capable model.

    The client is injected in tests; in production it is built lazily from the
    LLM_* environment variables with a 30 s timeout and 2 SDK retries.
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
        if self._client is not None:
            return self._client
        if not self.settings.enabled:
            raise ExtractionError("LLM_API_KEY is not set, so LLM extraction is unavailable")
        from openai import OpenAI

        self._client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            timeout=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
        )
        return self._client

    def extract(self, document: DocumentContent) -> ExtractedFields:
        parts = self._content_parts(document)
        client = self._ensure_client()
        last_error = "no response"

        for attempt in range(1, self.settings.max_retries + 2):
            started = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=self.settings.model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": parts},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
            except Exception as exc:  # openai raises many unrelated error types
                raise ExtractionError(f"{document.file_name}: LLM call failed: {exc}") from exc

            latency_ms = int(round((time.perf_counter() - started) * 1000))
            try:
                fields = self._to_fields(response, document)
            except (json.JSONDecodeError, ValidationError, AttributeError, TypeError) as exc:
                last_error = str(exc)
                continue

            self._last_meta = CallMeta(
                component="extractor",
                model=getattr(response, "model", None) or self.settings.model,
                latency_ms=latency_ms,
                attempts=attempt,
            )
            return fields

        raise ExtractionError(f"{document.file_name}: unusable LLM payload ({last_error})")

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

    def _to_fields(self, response: Any, document: DocumentContent) -> ExtractedFields:
        payload = json.loads(response.choices[0].message.content)
        fields = ExtractedFields.model_validate(payload)
        return fields.model_copy(
            update={
                "raw_text": document.text or "",
                "doc_type": fields.doc_type or document.doc_type,
            }
        )
