"""Deterministic dataset construction (SPEC.md section 6).

Everything is driven by one random.Random(seed) drawn in a fixed order, so the same
flags always produce byte-identical documents, labels and JSON files.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

from generator.anomalies import (
    ANOMALY_TYPES,
    CHECKS,
    apply,
    eligible_types,
    expected_verdicts,
    plant_duplicate_hash,
    shared_identity_doc_type,
)
from generator.documents import (
    AS_OF_DATE,
    MONETARY_DOC_TYPES,
    VALIDITY_YEARS,
    DocValues,
    add_years,
    authority_for,
    render_document,
)
from generator.model import AppRecord, Doc
from generator.pools import (
    CASTE_CATEGORIES,
    FIRST_NAMES_F,
    FIRST_NAMES_M,
    OCCUPATIONS,
    PLACES,
    SURNAMES,
)
from generator.services import (
    ALWAYS_ATTACHED_DOC_TYPES,
    OPTIONAL_DOC_TYPES,
    SERVICES,
    required_doc_types,
)

DUPLICATE_HASH_SHARE = 0.3  # of anomalous applications, as clone submissions
MULTI_ANOMALY_CHANCE = 0.25
VOTER_ID_CHANCE = 0.35
MIN_ANOMALIES = 1


def _random_date(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    return dt.date.fromordinal(rng.randint(start.toordinal(), end.toordinal()))


def _utc_stamp(day: dt.date, rng: random.Random) -> str:
    moment = dt.datetime(
        day.year, day.month, day.day, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
    )
    return moment.replace(tzinfo=dt.UTC).isoformat()


def _person(rng: random.Random, index: int) -> dict[str, Any]:
    """Canonical (truthful) identity of one fictional applicant."""
    gender = rng.choice(["F", "M"])
    first = rng.choice(FIRST_NAMES_F if gender == "F" else FIRST_NAMES_M)
    surname = rng.choice(SURNAMES)
    guardian_first = rng.choice(FIRST_NAMES_F + FIRST_NAMES_M)
    suffix = "D/O" if gender == "F" else "S/O"
    village, district = rng.choice(PLACES)
    digits = f"{rng.randint(4, 9)}{index:011d}"
    return {
        "fullName": f"{first} {surname}",
        "guardianName": f"{suffix} {guardian_first} {surname}",
        "aadhaarNumber": f"{digits[:4]} {digits[4:8]} {digits[8:]}",
        "dateOfBirth": _random_date(rng, dt.date(1962, 1, 1), dt.date(2002, 12, 31)).isoformat(),
        "gender": gender,
        "villageOrWard": village,
        "district": district,
        "state": "Fictiona",
        "postalCode": f"9{rng.randint(0, 99999):05d}",
        "annualIncomeInr": rng.randrange(30, 601) * 1000,
        "occupation": rng.choice(OCCUPATIONS),
        "casteCategory": rng.choice(CASTE_CATEGORIES),
        "yearsInResidence": rng.randint(3, 40),
    }


def _applicant_fields(service_id: str, person: dict[str, Any]) -> dict[str, Any]:
    fields = {
        key: person[key]
        for key in (
            "fullName",
            "aadhaarNumber",
            "dateOfBirth",
            "gender",
            "guardianName",
            "villageOrWard",
            "district",
            "state",
            "postalCode",
        )
    }
    if service_id == "income_certificate":
        fields.update(occupation=person["occupation"], annualIncomeInr=person["annualIncomeInr"])
    elif service_id == "caste_certificate":
        income = person["annualIncomeInr"]
        fields.update(casteCategory=person["casteCategory"], annualIncomeInr=income)
    else:
        fields.update(yearsInResidence=person["yearsInResidence"])
    return fields


def _doc_types(rng: random.Random, service_id: str) -> list[str]:
    types = list(dict.fromkeys(required_doc_types(service_id) + ALWAYS_ATTACHED_DOC_TYPES))
    optional = [name for name in OPTIONAL_DOC_TYPES if name not in types]
    if optional and rng.random() < VOTER_ID_CHANCE:
        types.append(rng.choice(optional))
    return types


def _make_doc(
    app_id: str, seq: int, doc_type: str, person: dict[str, Any], rng: random.Random
) -> Doc:
    validity = VALIDITY_YEARS.get(doc_type)
    if validity:
        window_start = AS_OF_DATE - dt.timedelta(days=validity * 365 - 60)
        window_end = AS_OF_DATE - dt.timedelta(days=20)
        issue = _random_date(rng, window_start, window_end)
        expiry = add_years(issue, validity).isoformat()
    else:
        recent_start = AS_OF_DATE - dt.timedelta(days=300)
        issue = _random_date(rng, recent_start, AS_OF_DATE - dt.timedelta(days=20))
        expiry = None
    values = DocValues(
        doc_type=doc_type,
        authority=authority_for(doc_type, person["district"]),
        full_name=person["fullName"],
        guardian_name=person["guardianName"],
        aadhaar_number=person["aadhaarNumber"],
        date_of_birth=person["dateOfBirth"],
        gender=person["gender"],
        village_or_ward=person["villageOrWard"],
        district=person["district"],
        state=person["state"],
        postal_code=person["postalCode"],
        certificate_no=f"{doc_type[:3].upper()}-{rng.randint(100000, 999999)}",
        issue_date=issue.isoformat(),
        expiry_date=expiry,
        amount_inr=person["annualIncomeInr"] if doc_type in MONETARY_DOC_TYPES else None,
    )
    return Doc(
        document_id=f"{app_id}-D{seq}",
        doc_type=doc_type,
        file_name=f"{app_id}-{doc_type}-{seq}.txt",
        uploaded_at=_utc_stamp(issue, rng),
        values=values,
    )


def _build_app(index: int, rng: random.Random) -> AppRecord:
    service = SERVICES[index % len(SERVICES)]
    person = _person(rng, index)
    app_id = f"APP-{index + 1:04d}"
    created = _random_date(
        rng, AS_OF_DATE - dt.timedelta(days=180), AS_OF_DATE - dt.timedelta(days=1)
    )
    app = AppRecord(
        application_id=app_id,
        service_id=service["id"],
        created_at=_utc_stamp(created, rng),
        applicant_fields=_applicant_fields(service["id"], person),
    )
    for seq, doc_type in enumerate(_doc_types(rng, service["id"]), start=1):
        app.docs.append(_make_doc(app_id, seq, doc_type, person, rng))
    return app


def build_dataset(*, n: int = 200, anomaly_rate: float = 0.25, seed: int = 42) -> list[AppRecord]:
    if not 0.0 <= anomaly_rate <= 1.0:
        raise ValueError("anomaly-rate must be between 0.0 and 1.0")
    if n < 1:
        raise ValueError("n must be >= 1")

    rng = random.Random(seed)
    apps = [_build_app(index, rng) for index in range(n)]
    _plant_anomalies(rng, apps, anomaly_rate)
    _finalize(apps)
    return apps


def _plant_anomalies(rng: random.Random, apps: list[AppRecord], anomaly_rate: float) -> None:
    n = len(apps)
    target = max(MIN_ANOMALIES, int(round(n * anomaly_rate))) if anomaly_rate > 0 else 0
    anomalous = sorted(rng.sample(range(n), min(target, n)))
    for index in anomalous:
        app = apps[index]
        pool = [a_type for a_type in eligible_types(app) if a_type != "duplicate_hash"]
        wanted = 2 if (len(pool) > 1 and rng.random() < MULTI_ANOMALY_CHANCE) else 1
        picked = []
        for _ in range(min(wanted, len(pool))):
            # Amount-vs-declaration anomalies interact: C4 and C5 could not attribute
            # a deviation to one of them, so an application carries at most one.
            if any(a in _AMOUNT_ANOMALIES for a in picked):
                pool = [a_type for a_type in pool if a_type not in _AMOUNT_ANOMALIES]
            if not pool:
                break
            chosen = rng.choice(pool)
            pool.remove(chosen)
            picked.append(chosen)
        for a_type in sorted(picked, key=_PLANT_ORDER.index):
            apply(rng, a_type, app)

    # Clone submissions overwrite identity (and one document's) data, so pairs are only
    # formed between applications whose own anomalies live elsewhere (amounts / docs),
    # and always inside the already-anomalous set so --anomaly-rate stays exact.
    compatible = [
        index
        for index in anomalous
        if not ({"name_mismatch", "expired_doc"} & set(apps[index].anomalies))
    ]
    pairs = min(int(round(len(anomalous) * DUPLICATE_HASH_SHARE)), len(compatible) // 2)
    for slot in range(pairs):
        donor = apps[compatible[2 * slot]]
        recipient = apps[compatible[2 * slot + 1]]
        doc_type = shared_identity_doc_type(donor, recipient)
        if doc_type is None:
            continue
        plant_duplicate_hash(donor, recipient, doc_type)
        donor.anomalies.append("duplicate_hash")
        recipient.anomalies.append("duplicate_hash")


_PLANT_ORDER = ["missing_doc", "expired_doc", "name_mismatch", "field_mismatch", "tampered_number"]
_AMOUNT_ANOMALIES = frozenset({"field_mismatch", "tampered_number"})


def _finalize(apps: list[AppRecord]) -> None:
    for app in apps:
        for doc in app.docs:
            if not doc.content:
                doc.content = render_document(doc.values)


def ground_truth(apps: list[AppRecord], *, seed: int, anomaly_rate: float) -> dict[str, Any]:
    """Labels for every application, plus corpus counts for the eval harness."""
    entries = [
        {
            "applicationId": app.application_id,
            "serviceId": app.service_id,
            "clean": not app.anomalies,
            "anomalies": sorted(app.anomalies),
            "expected": expected_verdicts(app),
        }
        for app in apps
    ]
    by_service: dict[str, int] = {}
    by_anomaly = {a_type: 0 for a_type in ANOMALY_TYPES}
    by_check = {check: 0 for check in CHECKS}
    for app, entry in zip(apps, entries, strict=True):
        by_service[app.service_id] = by_service.get(app.service_id, 0) + 1
        for a_type in app.anomalies:
            by_anomaly[a_type] += 1
        for check, verdict in entry["expected"].items():
            if verdict == "fail":
                by_check[check] += 1
    return {
        "asOf": AS_OF_DATE.isoformat(),
        "seed": seed,
        "requestedAnomalyRate": anomaly_rate,
        "checks": CHECKS,
        "anomalyTypes": ANOMALY_TYPES,
        "counts": {
            "applications": len(apps),
            "clean": sum(1 for entry in entries if entry["clean"]),
            "anomalous": sum(1 for entry in entries if not entry["clean"]),
            "documents": sum(len(app.docs) for app in apps),
            "byService": by_service,
            "failByCheck": by_check,
            "byAnomalyType": by_anomaly,
        },
        "applications": entries,
    }
