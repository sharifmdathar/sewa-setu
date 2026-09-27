"""The service catalog, in the contract's `Service` shape.

Field names are written here in camelCase, exactly as `shared/contracts/openapi.yaml` and
`data/synthetic/generator/services.py` spell them; tests/test_api_services.py asserts the two
catalogues agree, because the generator plants anomalies against these required document types.
"""

from __future__ import annotations

from pipeline.api.models import Service

_IDENTITY_FIELDS = {
    "fullName": "string",
    "aadhaarNumber": "string",
    "dateOfBirth": "date",
    "gender": "string",
    "guardianName": "string",
    "villageOrWard": "string",
    "district": "string",
    "state": "string",
}

SERVICES: tuple[Service, ...] = (
    Service(
        id="income_certificate",
        name="Income Certificate",
        requiredDocTypes=["aadhaar", "bank_statement", "revenue_record"],
        fieldSchema={
            **_IDENTITY_FIELDS,
            "occupation": "string",
            "annualIncomeInr": "integer",
        },
    ),
    Service(
        id="caste_certificate",
        name="Caste Certificate",
        requiredDocTypes=[
            "aadhaar",
            "school_certificate",
            "parent_caste_certificate",
            "self_income_declaration",
        ],
        fieldSchema={
            **_IDENTITY_FIELDS,
            "casteCategory": "string",
            "annualIncomeInr": "integer",
        },
    ),
    Service(
        id="residence_certificate",
        name="Residence Certificate (Domicile)",
        requiredDocTypes=["aadhaar", "electricity_bill", "affidavit"],
        fieldSchema={**_IDENTITY_FIELDS, "yearsInResidence": "integer"},
    ),
)

_BY_ID = {service.id: service for service in SERVICES}


def services() -> list[Service]:
    return list(SERVICES)


def get(service_id: str) -> Service | None:
    return _BY_ID.get(service_id)
