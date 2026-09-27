"""Mutable in-memory model of one generated application and its documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from generator.documents import DocValues


def sha256_of(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class Doc:
    """A generated document; duplicate submissions share identical content (same hash)."""

    document_id: str
    doc_type: str
    file_name: str
    uploaded_at: str
    values: DocValues
    content: str = ""

    @property
    def sha256(self) -> str:
        return sha256_of(self.content)


@dataclass
class AppRecord:
    """One application: declared fields, attached documents, planted anomalies."""

    application_id: str
    service_id: str
    created_at: str
    applicant_fields: dict[str, Any]
    docs: list[Doc] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)

    def of_type(self, doc_type: str) -> list[Doc]:
        return [doc for doc in self.docs if doc.doc_type == doc_type]

    @property
    def doc_types(self) -> list[str]:
        return [doc.doc_type for doc in self.docs]

    @property
    def amounts(self) -> list[int]:
        return [doc.values.amount_inr for doc in self.docs if doc.values.amount_inr is not None]

    def declared_amount(self) -> int | None:
        return self.applicant_fields.get("annualIncomeInr")

    def as_application(self) -> dict[str, Any]:
        """Contract-shaped Application (openapi.yaml -> Application) plus documents.

        The `documents` key is an extension allowed by the schema (OpenAPI does not
        restrict additional properties); dataset consumers need per-doc sha256.
        """
        return {
            "id": self.application_id,
            "serviceId": self.service_id,
            "status": "documents_uploaded",
            "applicantFields": dict(self.applicant_fields),
            "createdAt": self.created_at,
            "updatedAt": self.created_at,
            "timeline": [
                {
                    "at": self.created_at,
                    "actor": "citizen",
                    "event": "submitted",
                    "message": "Application and documents submitted by the citizen.",
                }
            ],
            "documents": [
                {
                    "id": doc.document_id,
                    "docType": doc.doc_type,
                    "fileName": doc.file_name,
                    "uploadedAt": doc.uploaded_at,
                    "sha256": doc.sha256,
                }
                for doc in self.docs
            ],
        }
