"""Rules engine tests (prompt A4 DoD: >=2 cases per check, incl. each fail edge)."""

from __future__ import annotations

from typing import Any

from helpers import make_blank_doc, make_doc, make_input

from pipeline.rules import DocEvidence, load_rule_config, run_rules
from pipeline.rules.checks import (
    check_completeness,
    check_cross_field_consistency,
    check_document_validity,
    check_fraud_signals,
    check_identity_match,
)

CONFIG = load_rule_config()


def bank(amount: int | None = None, **template: Any) -> DocEvidence:
    """A bank statement with a plausible issuer and an optional stated amount."""
    return make_doc("bank_statement", authority="Fictiona Gramin Bank", amount=amount, **template)


# --- C1 identity_match ----------------------------------------------------------------------------


def test_c1_passes_when_documents_and_declaration_agree() -> None:
    data = make_input([make_doc("aadhaar"), make_doc("bank_statement", authority="X")])
    result = check_identity_match(data, CONFIG)
    assert result.status == "pass"
    assert result.check_id == "C1"


def test_c1_fails_and_quotes_the_mismatched_name() -> None:
    odd = bank(name="Ganesh Baruah")
    data = make_input([make_doc("aadhaar"), odd])
    result = check_identity_match(data, CONFIG)
    assert result.status == "fail"
    assert result.severity == "high"
    assert "Ganesh Baruah" in result.evidence
    assert "Anita Baruah" in result.evidence


def test_c1_fails_on_diverging_identity_number() -> None:
    odd = make_doc("affidavit", aadhaar="9999 9999 9999", authority="Notary Public, Midvale")
    data = make_input([make_doc("aadhaar"), odd])
    result = check_identity_match(data, CONFIG)
    assert result.status == "fail"
    assert "9999 9999 9999" in result.evidence


def test_c1_is_info_when_nothing_was_readable() -> None:
    data = make_input([make_blank_doc("aadhaar")])
    result = check_identity_match(data, CONFIG)
    assert result.status == "info"
    assert result.explanation


# --- C2 doc_validity ------------------------------------------------------------------------------


def test_c2_passes_for_a_current_document() -> None:
    data = make_input([make_doc("aadhaar")])
    assert check_document_validity(data, CONFIG).status == "pass"


def test_c2_fails_on_an_expired_document_and_quotes_the_date() -> None:
    expired = make_doc("aadhaar", expiry="2025-01-31", issue="2015-01-31")
    result = check_document_validity(make_input([expired]), CONFIG)
    assert result.status == "fail"
    assert "2025-01-31" in result.evidence
    assert "expired" in result.evidence.lower()


def test_c2_fails_when_expiry_precedes_issue() -> None:
    twisted = make_doc("aadhaar", issue="2030-01-01", expiry="2020-01-01")
    result = check_document_validity(make_input([twisted]), CONFIG)
    assert result.status == "fail"
    assert "before it was issued" in result.evidence


def test_c2_warns_when_the_issuer_does_not_match() -> None:
    dodgy = make_doc("aadhaar", authority="Corner Shop Printers")
    result = check_document_validity(make_input([dodgy]), CONFIG)
    assert result.status == "warn"
    assert "Corner Shop Printers" in result.evidence


# --- C3 completeness -----------------------------------------------------------------------------


def test_c3_passes_when_every_required_type_is_attached() -> None:
    data = make_input(
        [make_doc("aadhaar"), bank()],
        required=("aadhaar", "bank_statement"),
    )
    assert check_completeness(data, CONFIG).status == "pass"


def test_c3_fails_and_names_the_missing_document_type() -> None:
    data = make_input([make_doc("aadhaar")], required=("aadhaar", "bank_statement"))
    result = check_completeness(data, CONFIG)
    assert result.status == "fail"
    assert "bank_statement" in result.evidence


def test_c3_fails_when_an_attached_document_is_unreadable() -> None:
    data = make_input([make_doc("aadhaar"), make_blank_doc("bank_statement")])
    result = check_completeness(data, CONFIG)
    assert result.status == "fail"
    assert "app1-bank_statement-blank.txt" in result.evidence


# --- C4 cross_field_consistency -------------------------------------------------------------------


def test_c4_passes_when_declared_income_matches_documents() -> None:
    docs = [make_doc("aadhaar"), bank(amount=180000)]
    data = make_input(docs, declared_income=180000)
    assert check_cross_field_consistency(data, CONFIG).status == "pass"


def test_c4_fails_and_quotes_both_conflicting_amounts() -> None:
    docs = [make_doc("aadhaar"), bank(amount=90000)]
    data = make_input(docs, declared_income=300000)
    result = check_cross_field_consistency(data, CONFIG)
    assert result.status == "fail"
    assert "300000" in result.evidence and "90000" in result.evidence


def test_c4_is_info_for_services_without_a_declared_amount() -> None:
    data = make_input([make_doc("aadhaar")])
    assert check_cross_field_consistency(data, CONFIG).status == "info"


def test_c4_defers_whole_decimal_zero_gaps_to_the_fraud_check() -> None:
    docs = [make_doc("aadhaar"), bank(amount=3000000)]
    data = make_input(docs, declared_income=300000)
    assert check_cross_field_consistency(data, CONFIG).status == "pass"


# --- C5 fraud_signals ----------------------------------------------------------------------------


def test_c5_passes_for_an_ordinary_application() -> None:
    data = make_input([make_doc("aadhaar")])
    assert check_fraud_signals(data, CONFIG).status == "pass"


def test_c5_fails_on_a_duplicate_document_hash_across_applications() -> None:
    doc = make_doc("aadhaar")
    data = make_input([doc], duplicate_sha256=(doc.sha256,))
    result = check_fraud_signals(data, CONFIG)
    assert result.status == "fail"
    assert result.severity == "high"
    assert doc.sha256[:12] in result.evidence


def test_c5_fails_on_a_padded_amount_and_quotes_it() -> None:
    docs = [make_doc("aadhaar"), bank(amount=4500000)]
    data = make_input(docs, declared_income=45000)
    result = check_fraud_signals(data, CONFIG)
    assert result.status == "fail"
    assert "4500000" in result.evidence and "45000" in result.evidence


# --- engine --------------------------------------------------------------------------------------


def test_run_rules_returns_all_five_checks_in_order() -> None:
    docs = [make_doc("aadhaar"), bank()]
    checks = run_rules(make_input(docs, required=("aadhaar", "bank_statement")), CONFIG)
    assert [check.check_id for check in checks] == ["C1", "C2", "C3", "C4", "C5"]
    assert all(check.evidence and check.explanation for check in checks)
    assert all(check.label == CONFIG.checks[check.check_id].label for check in checks)


def test_every_check_carries_evidence_and_explanation_on_a_fraudulent_application() -> None:
    forged = bank(name="Rani Verma", amount=7000000)
    expired = make_doc(
        "revenue_record",
        issue="2014-02-02",
        expiry="2024-02-02",
        authority="Tehsildar Office",
    )
    data = make_input(
        [make_doc("aadhaar"), forged, expired],
        required=("aadhaar", "bank_statement", "revenue_record"),
        declared_income=70000,
        duplicate_sha256=(forged.sha256,),
    )
    checks = run_rules(data, CONFIG)
    statuses = {check.check_id: check.status for check in checks}
    assert statuses == {"C1": "fail", "C2": "fail", "C3": "pass", "C4": "pass", "C5": "fail"}
    for check in checks:
        assert len(check.evidence) > 20, check.check_id
        assert check.severity in {"low", "medium", "high"}
