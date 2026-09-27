"""Anomaly planting: each planted type maps to exactly one expected check verdict.

Check ownership (SPEC.md section 5):
  name_mismatch    -> C1 identity_match (documents disagree with each other)
  expired_doc      -> C2 doc_validity
  missing_doc      -> C3 completeness
  field_mismatch   -> C4 cross_field_consistency (declaration vs documents)
  tampered_number  -> C5 fraud_signals (extra-zero amount forgery)
  duplicate_hash   -> C5 fraud_signals (same document bytes in two applications)
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import replace

from generator.documents import AS_OF_DATE, MONETARY_DOC_TYPES, VALIDITY_YEARS, add_years
from generator.model import AppRecord, Doc
from generator.pools import FIRST_NAMES_F, FIRST_NAMES_M, SURNAMES
from generator.services import required_doc_types

ANOMALY_TO_CHECK = {
    "name_mismatch": "C1",
    "expired_doc": "C2",
    "missing_doc": "C3",
    "field_mismatch": "C4",
    "tampered_number": "C5",
    "duplicate_hash": "C5",
}
ANOMALY_TYPES = list(ANOMALY_TO_CHECK)
CHECKS = ["C1", "C2", "C3", "C4", "C5"]


def is_power_of_ten_ratio(a: int, b: int) -> bool:
    """True when one value is the other shifted by whole decimal zeros (10, 100, ...)."""
    if a <= 0 or b <= 0 or a == b:
        return False
    high, low = (a, b) if a > b else (b, a)
    if high % low:
        return False
    ratio = high // low
    while ratio % 10 == 0:
        ratio //= 10
    return ratio == 1


def _docs_of_type_in(app: AppRecord, doc_types) -> list[Doc]:
    return [doc for doc in app.docs if doc.doc_type in doc_types]


def eligible_types(app: AppRecord) -> list[str]:
    """Anomaly types this application can carry without confusing another check."""
    required = set(required_doc_types(app.service_id))
    droppable = [
        doc
        for doc in app.docs
        if doc.doc_type in required and doc.doc_type not in MONETARY_DOC_TYPES
    ]
    candidates = {
        "name_mismatch": len(app.docs) >= 2,
        "expired_doc": any(doc.values.expiry_date for doc in app.docs),
        "missing_doc": bool(droppable) and len(app.docs) > 2,
        "field_mismatch": bool(app.amounts) and app.declared_amount() is not None,
        "tampered_number": bool(_docs_of_type_in(app, MONETARY_DOC_TYPES)),
        "duplicate_hash": True,
    }
    return [a_type for a_type in ANOMALY_TYPES if candidates[a_type]]


def plant_name_mismatch(rng: random.Random, app: AppRecord) -> None:
    """One document carries a different personal name than the rest of the set."""
    doc = rng.choice(app.docs)
    other = rng.choice(FIRST_NAMES_F + FIRST_NAMES_M)
    surname = rng.choice([s for s in SURNAMES if s != doc.values.full_name.split()[-1]])
    doc.values.full_name = f"{other} {surname}"


def plant_expired_doc(rng: random.Random, app: AppRecord) -> None:
    """Move one document's issue+expiry pair fully into the past."""
    expiring = [doc for doc in app.docs if doc.values.expiry_date]
    doc = rng.choice(expiring)
    expiry = AS_OF_DATE - dt.timedelta(days=rng.randint(30, 900))
    validity = VALIDITY_YEARS.get(doc.doc_type) or 1
    doc.values.expiry_date = expiry.isoformat()
    doc.values.issue_date = add_years(expiry, -validity).isoformat()


def plant_missing_doc(rng: random.Random, app: AppRecord) -> None:
    """Required document simply was not attached."""
    required = set(required_doc_types(app.service_id))
    droppable = [
        doc
        for doc in app.docs
        if doc.doc_type in required and doc.doc_type not in MONETARY_DOC_TYPES
    ]
    app.docs.remove(rng.choice(droppable))


def plant_field_mismatch(rng: random.Random, app: AppRecord) -> None:
    """Citizen-declared income disagrees with every document, by a non-decimal shift."""
    true_amount = app.amounts[0]
    declared = app.declared_amount() or true_amount
    for _ in range(12):
        shift = rng.choice([-30, -22, -15, -8, 8, 15, 22, 30])
        candidate = int(round(declared * (100 + shift) / 100))
        if not is_power_of_ten_ratio(candidate, true_amount):
            app.applicant_fields["annualIncomeInr"] = candidate
            return
    app.applicant_fields["annualIncomeInr"] = declared + 1111


def plant_tampered_number(rng: random.Random, app: AppRecord) -> None:
    """One document's amount has whole zeros appended (classic 10x / 100x forgery)."""
    monetary = [doc for doc in app.docs if doc.doc_type in MONETARY_DOC_TYPES]
    doc = rng.choice(monetary)
    doc.values.amount_inr = doc.values.amount_inr * rng.choice([10, 100])


def shared_identity_doc_type(donor: AppRecord, recipient: AppRecord) -> str | None:
    """A non-monetary document type both applications have (identity-bearing)."""

    def types(app: AppRecord) -> list[str]:
        return sorted(
            {doc.doc_type for doc in app.docs if doc.doc_type not in MONETARY_DOC_TYPES}
        )

    shared = sorted(set(types(donor)) & set(types(recipient)))
    if not shared:
        return None
    return "aadhaar" if "aadhaar" in shared else shared[0]


def plant_duplicate_hash(donor: AppRecord, recipient: AppRecord, doc_type: str) -> None:
    """Same document bytes submitted under two applications (clone submission).

    The recipient adopts the donor's *identity* everywhere, so C1-C4 stay clean and
    only the shared document hash (C5) is suspicious. Monetary and service-specific
    declaration fields stay the recipient's own.
    """
    source = next(doc for doc in donor.docs if doc.doc_type == doc_type)
    identity_doc = {
        "full_name": source.values.full_name,
        "guardian_name": source.values.guardian_name,
        "aadhaar_number": source.values.aadhaar_number,
        "date_of_birth": source.values.date_of_birth,
        "gender": source.values.gender,
        "village_or_ward": source.values.village_or_ward,
        "district": source.values.district,
        "state": source.values.state,
        "postal_code": source.values.postal_code,
    }
    for doc in recipient.docs:
        for name, value in identity_doc.items():
            setattr(doc.values, name, value)
    recipient.applicant_fields.update(
        {
            "fullName": source.values.full_name,
            "guardianName": source.values.guardian_name,
            "aadhaarNumber": source.values.aadhaar_number,
            "dateOfBirth": source.values.date_of_birth,
            "gender": source.values.gender,
            "villageOrWard": source.values.village_or_ward,
            "district": source.values.district,
            "state": source.values.state,
            "postalCode": source.values.postal_code,
        }
    )
    target = next(doc for doc in recipient.docs if doc.doc_type == doc_type)
    target.values = replace(source.values)
    target.content = ""


def apply(rng: random.Random, a_type: str, app: AppRecord) -> None:
    planters = {
        "name_mismatch": plant_name_mismatch,
        "expired_doc": plant_expired_doc,
        "missing_doc": plant_missing_doc,
        "field_mismatch": plant_field_mismatch,
        "tampered_number": plant_tampered_number,
    }
    if a_type in planters:
        planters[a_type](rng, app)
        app.anomalies.append(a_type)
    else:
        raise ValueError(f"unknown anomaly type {a_type!r}")


def expected_verdicts(app: AppRecord) -> dict[str, str]:
    """Ground-truth C1-C5 labels implied by the anomalies planted in this app."""
    failed = {ANOMALY_TO_CHECK[a] for a in app.anomalies}
    return {check: ("fail" if check in failed else "pass") for check in CHECKS}
