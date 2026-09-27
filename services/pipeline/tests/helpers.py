"""Shared builders for rule/agent/fraud tests (real extraction, synthetic inputs)."""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from pipeline.extraction import DocumentContent, ExtractedFields, TemplateExtractor
from pipeline.rules import DocEvidence, ScrutinyInput

AS_OF = dt.date(2026, 6, 30)
GOOD_AUTHORITY = "Unique Fictiona Identity Authority"


def doc_text(
    doc_type: str = "aadhaar",
    *,
    name: str = "Anita Baruah",
    aadhaar: str = "4123 8890 1177",
    authority: str = GOOD_AUTHORITY,
    issue: str = "2024-01-05",
    expiry: str | None = "2034-01-05",
    amount: int | None = None,
) -> str:
    lines = [
        "SEWA SETU SYNTHETIC DOCUMENT -- NO REAL PII",
        f"DOC_TYPE: {doc_type}",
        f"ISSUING_AUTHORITY: {authority}",
        f"FULL_NAME: {name}",
        f"AADHAAR_NUMBER: {aadhaar}",
        "DATE_OF_BIRTH: 1990-05-04",
        "GENDER: F",
        "VILLAGE_OR_WARD: Sundarpur",
        "DISTRICT: Midvale",
        "STATE: Fictiona",
        "POSTAL_CODE: 900112",
        f"ISSUE_DATE: {issue}",
    ]
    if expiry:
        lines.append(f"EXPIRY_DATE: {expiry}")
    if amount is not None:
        lines.append(f"AMOUNT_INR: {amount}")
    return "\n".join(lines) + "\n"


def extracted(text: str) -> ExtractedFields:
    return TemplateExtractor().extract(
        DocumentContent(documentId="D", docType="any", fileName="x.txt", text=text)
    )


def make_doc(doc_type: str = "aadhaar", *, text: str | None = None, **template: Any) -> DocEvidence:
    body = text if text is not None else doc_text(doc_type, **template)
    file_name = f"app1-{doc_type}-1.txt"
    return DocEvidence(
        documentId=f"{doc_type}-1",
        docType=doc_type,
        fileName=file_name,
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        uploadedAt=dt.datetime(2026, 6, 1, 10, 30, tzinfo=dt.UTC),
        fields=extracted(body),
    )


def make_blank_doc(doc_type: str = "aadhaar") -> DocEvidence:
    """A document that yields no fields at all (an unreadable scan never reaches rules)."""
    body = "photocopy of a photocopy, nothing legible\n"
    return DocEvidence(
        documentId=f"{doc_type}-blank",
        docType=doc_type,
        fileName=f"app1-{doc_type}-blank.txt",
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        uploadedAt=dt.datetime(2026, 6, 1, 10, 30, tzinfo=dt.UTC),
        fields=ExtractedFields(docType=doc_type, rawText=body),
    )


def make_input(
    docs: list[DocEvidence],
    *,
    required: tuple[str, ...] = ("aadhaar",),
    declared_name: str = "Anita Baruah",
    declared_aadhaar: str = "4123 8890 1177",
    declared_income: int | None = None,
    duplicate_sha256: tuple[str, ...] = (),
) -> ScrutinyInput:
    applicant: dict[str, Any] = {"fullName": declared_name, "aadhaarNumber": declared_aadhaar}
    if declared_income is not None:
        applicant["annualIncomeInr"] = declared_income
    return ScrutinyInput(
        applicationId="APP-1",
        serviceId="income_certificate",
        requiredDocTypes=list(required),
        applicantFields=applicant,
        documents=docs,
        duplicateSha256=list(duplicate_sha256),
        asOf=AS_OF,
    )
