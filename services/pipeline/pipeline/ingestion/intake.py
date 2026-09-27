"""Document intake: turn an upload into what the store keeps and what the extractors read.

The store keeps the bytes the citizen sent (`contentBase64`), so the document's `sha256` is
computed once here and re-derived identically at scrutiny time - the two must agree or the
cross-application duplicate check in C5 is fiction.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import PurePosixPath
from typing import Any

from pipeline.agent import sha256_of_content
from pipeline.extraction import DocumentContent

TEXT_MIMES = {
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/plain",
    ".json": "text/plain",
}
IMAGE_MIMES = {".png": "image/png", ".jpg": "image/png", ".jpeg": "image/png", ".webp": "image/png"}


class UploadError(ValueError):
    """The upload cannot be stored at all - as opposed to a stored file that reads as blank."""


def mime_for(file_name: str) -> str:
    suffix = PurePosixPath(file_name).suffix.lower()
    return TEXT_MIMES.get(suffix) or IMAGE_MIMES.get(suffix) or "application/octet-stream"


def is_textual(mime: str) -> bool:
    return mime.startswith("text/")


def decode_upload(file_name: str, content_base64: str) -> bytes:
    """The document's real bytes, or an UploadError a caller turns into a 4xx."""
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadError(f"{file_name}: contentBase64 is not valid base64") from exc
    if not raw:
        raise UploadError(f"{file_name}: the upload is empty")
    if is_textual(mime_for(file_name)):
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadError(f"{file_name}: a text document must be valid UTF-8") from exc
    return raw


def stored_document(
    document_id: str, doc_type: str, file_name: str, content_base64: str, uploaded_at: str
) -> dict[str, Any]:
    """One record in the shape the store keeps: the contract Document plus its content."""
    raw = decode_upload(file_name, content_base64)
    content = _content(document_id, doc_type, file_name, content_base64, raw)
    return {
        "id": document_id,
        "docType": doc_type,
        "fileName": file_name,
        "uploadedAt": uploaded_at,
        "sha256": sha256_of_content(content),
        "contentBase64": content_base64,
    }


def to_content(document: dict[str, Any]) -> DocumentContent:
    """Rebuild one stored document for the extraction stage."""
    encoded = str(document["contentBase64"])
    raw = base64.b64decode(encoded)
    return _content(
        str(document["id"]), str(document["docType"]), str(document["fileName"]), encoded, raw
    )


def _content(
    document_id: str, doc_type: str, file_name: str, encoded: str, raw: bytes
) -> DocumentContent:
    mime = mime_for(file_name)
    text = raw.decode("utf-8") if is_textual(mime) else None
    return DocumentContent(
        documentId=document_id,
        docType=doc_type,
        fileName=file_name,
        mimeType=mime,
        text=text,
        contentBase64=encoded,
    )
