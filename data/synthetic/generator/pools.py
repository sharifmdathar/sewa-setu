"""Fictional pools for synthetic data. No real PII: every value is invented."""

from __future__ import annotations

FIRST_NAMES_F = [
    "Anita", "Beena", "Chitra", "Deepa", "Geeta", "Hema", "Indu", "Kavita",
    "Lata", "Meena", "Nisha", "Pooja", "Rani", "Sunita", "Usha", "Vidya",
]

FIRST_NAMES_M = [
    "Arun", "Bhola", "Dinesh", "Ganesh", "Hari", "Inder", "Jagdish", "Kishan",
    "Mahesh", "Narayan", "Prakash", "Ramesh", "Suresh", "Vijay", "Yogesh", "Zile",
]

SURNAMES = [
    "Baruah", "Chaudhary", "Das", "Dev Sharma", "Ghosh", "Iyer", "Joshi",
    "Kamboj", "Lohar", "Mandvi", "Nair", "Pande", "Qureshi", "Rauthat",
    "Sahni", "Thakur", "Uppal", "Verma", "Yadav", "Zutri",
]

GUARDIAN_SUFFIX = ["D/O", "S/O"]

# Fictional district / village pairs (state is always FICTIONA).
PLACES = [
    ("Sundarpur", "Midvale"),
    ("Chandgaon", "Northfield"),
    ("Bahradanda", "Rivermouth"),
    ("Kalipur", "Southgate"),
    ("Newtola", "Hillcrest"),
    ("Bansgaon", "Lakeside"),
    ("Haripur", "Westplain"),
    ("Motibennur", "Eastwood"),
]

OCCUPATIONS = [
    "Agricultural labourer", "Carpenter", "Daily wage worker", "Farmer",
    "Handicraft artisan", "Milk supplier", "Potter", "School teacher",
    "Shop assistant", "Tailor",
]

CASTE_CATEGORIES = ["General", "OBC", "SC", "ST"]

ISSUING_AUTHORITIES = {
    "aadhaar": "Unique Fictiona Identity Authority",
    "bank_statement": "Fictiona Gramin Bank, {district} Branch",
    "revenue_record": "Tehsildar Office, {district}",
    "school_certificate": "District Education Office, {district}",
    "parent_caste_certificate": "Taluka Social Welfare Office, {district}",
    "self_income_declaration": "Applicant self-declaration, {district}",
    "electricity_bill": "Fictiona Power Distribution Co, {district}",
    "affidavit": "Notary Public, {district} Court",
    "fee_receipt": "Fictiona Seva Kendra, {district}",
    "voter_id": "Chief Electoral Officer, Fictiona",
}

# Fixed reference date so regenerated datasets are byte-identical forever.
AS_OF = "2026-06-30"

NAME_POOLS = (FIRST_NAMES_F, FIRST_NAMES_M)
