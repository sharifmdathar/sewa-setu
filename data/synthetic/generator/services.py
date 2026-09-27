"""Service catalog mirroring the frozen contract's Service schema.

shared/contracts/openapi.yaml -> components/schemas/Service
{ id, name, requiredDocTypes, fieldSchema }
"""

from __future__ import annotations

SERVICES = [
    {
        "id": "income_certificate",
        "name": "Income Certificate",
        "requiredDocTypes": ["aadhaar", "bank_statement", "revenue_record"],
        "fieldSchema": {
            "fullName": "string",
            "aadhaarNumber": "string",
            "dateOfBirth": "date",
            "gender": "string",
            "guardianName": "string",
            "villageOrWard": "string",
            "district": "string",
            "state": "string",
            "occupation": "string",
            "annualIncomeInr": "integer",
        },
    },
    {
        "id": "caste_certificate",
        "name": "Caste Certificate",
        "requiredDocTypes": [
            "aadhaar",
            "school_certificate",
            "parent_caste_certificate",
            "self_income_declaration",
        ],
        "fieldSchema": {
            "fullName": "string",
            "aadhaarNumber": "string",
            "dateOfBirth": "date",
            "gender": "string",
            "guardianName": "string",
            "villageOrWard": "string",
            "district": "string",
            "state": "string",
            "casteCategory": "string",
            "annualIncomeInr": "integer",
        },
    },
    {
        "id": "residence_certificate",
        "name": "Residence Certificate (Domicile)",
        "requiredDocTypes": ["aadhaar", "electricity_bill", "affidavit"],
        "fieldSchema": {
            "fullName": "string",
            "aadhaarNumber": "string",
            "dateOfBirth": "date",
            "gender": "string",
            "guardianName": "string",
            "villageOrWard": "string",
            "district": "string",
            "state": "string",
            "yearsInResidence": "integer",
        },
    },
]

# Extra documents citizens sometimes attach; fee_receipt is always attached.
ALWAYS_ATTACHED_DOC_TYPES = ["fee_receipt"]
OPTIONAL_DOC_TYPES = ["voter_id"]

SERVICE_BY_ID = {service["id"]: service for service in SERVICES}


def service_ids() -> list[str]:
    return [service["id"] for service in SERVICES]


def required_doc_types(service_id: str) -> list[str]:
    return list(SERVICE_BY_ID[service_id]["requiredDocTypes"])
