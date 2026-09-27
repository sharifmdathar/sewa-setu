"""Templated text documents with a strict `KEY: value` line format.

TemplateExtractor (pipeline.extraction) parses these by key, so every field that
a rule needs must be present as its own line.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from generator.pools import AS_OF, ISSUING_AUTHORITIES

AS_OF_DATE = dt.date.fromisoformat(AS_OF)

# Documents that state the applicant's declared monetary value.
MONETARY_DOC_TYPES = frozenset({"bank_statement", "revenue_record", "self_income_declaration"})

# Years of validity per doc type; None means the document never expires.
VALIDITY_YEARS: dict[str, int | None] = {
    "aadhaar": 20,
    "bank_statement": 1,
    "revenue_record": 2,
    "school_certificate": 10,
    "parent_caste_certificate": 5,
    "self_income_declaration": 1,
    "electricity_bill": 1,
    "affidavit": 3,
    "fee_receipt": None,
    "voter_id": 15,
}


@dataclass
class DocValues:
    """One rendered document's field values (mutated in place when anomalies are planted)."""

    doc_type: str
    authority: str
    full_name: str
    guardian_name: str
    aadhaar_number: str
    date_of_birth: str
    gender: str
    village_or_ward: str
    district: str
    state: str
    postal_code: str
    certificate_no: str
    issue_date: str
    expiry_date: str | None
    amount_inr: int | None


def add_years(day: dt.date, years: int) -> dt.date:
    """Add whole years, clamping Feb 29 -> Feb 28 in non-leap years."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(month=2, day=28, year=day.year + years)


def issue_date_for(doc_type: str, day: dt.date) -> dt.date:
    """Issue date that keeps `day` inside the document's validity window."""
    validity = VALIDITY_YEARS.get(doc_type)
    if validity is None:
        return day
    return add_years(day, -validity)


def expiry_for(doc_type: str, issue: dt.date) -> str | None:
    validity = VALIDITY_YEARS.get(doc_type)
    if validity is None:
        return None
    return add_years(issue, validity).isoformat()


def authority_for(doc_type: str, district: str) -> str:
    template = ISSUING_AUTHORITIES.get(doc_type, "Fictiona Revenue Department, {district}")
    return template.format(district=district)


def render_document(values: DocValues) -> str:
    """Render one document body. Keys are stable and machine-parseable."""
    lines = [
        "SEWA SETU SYNTHETIC DOCUMENT -- NO REAL PII",
        f"TEMPLATE_ID: {values.doc_type}-v1",
        f"DOC_TYPE: {values.doc_type}",
        f"ISSUING_AUTHORITY: {values.authority}",
        f"CERTIFICATE_NO: {values.certificate_no}",
        f"FULL_NAME: {values.full_name}",
        f"GUARDIAN_NAME: {values.guardian_name}",
        f"AADHAAR_NUMBER: {values.aadhaar_number}",
        f"DATE_OF_BIRTH: {values.date_of_birth}",
        f"GENDER: {values.gender}",
        f"VILLAGE_OR_WARD: {values.village_or_ward}",
        f"DISTRICT: {values.district}",
        f"STATE: {values.state}",
        f"POSTAL_CODE: {values.postal_code}",
        f"ISSUE_DATE: {values.issue_date}",
    ]
    if values.expiry_date is not None:
        lines.append(f"EXPIRY_DATE: {values.expiry_date}")
    if values.amount_inr is not None:
        lines.append(f"AMOUNT_INR: {values.amount_inr}")
    lines.append("END OF DOCUMENT")
    return "\n".join(lines) + "\n"
