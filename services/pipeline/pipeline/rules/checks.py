"""Pure C1-C5 rule functions (SPEC.md section 5).

Every function is total: it always returns a ScrutinyCheck carrying quoted offending
values in `evidence` and a plain-language `explanation` for the officer.

Check ownership, so a single defect never lights up two checks:
  C1 identity_match            - name and ID number across documents and declaration
  C2 doc_validity              - issue/expiry dates and issuing authority plausibility
  C3 completeness              - required document types present and readable
  C4 cross_field_consistency   - stated amounts vs the declared annual income
  C5 fraud_signals             - duplicate document hashes and extra-zero amounts
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from pipeline.rules.models import (
    CheckConfig,
    CheckSeverity,
    CheckStatus,
    RuleConfig,
    ScrutinyCheck,
    ScrutinyInput,
)
from pipeline.rules.numeric import is_power_of_ten_ratio, short_hash

CHECK_IDS = ("C1", "C2", "C3", "C4", "C5")
_MAX_EVIDENCE_ITEMS = 4


def _severity_for(rule: CheckConfig, status: CheckStatus) -> CheckSeverity:
    if status == "fail":
        return rule.fail_severity
    if status == "warn":
        return rule.warn_severity
    return "low"


def _build(
    check_id: str, config: RuleConfig, status: CheckStatus, evidence: str, why: str
) -> ScrutinyCheck:
    rule = config.checks[check_id]
    return ScrutinyCheck(
        checkId=check_id,
        label=rule.label,
        status=status,
        severity=_severity_for(rule, status),
        evidence=evidence,
        explanation=why,
    )


def _quote(items: list[str]) -> str:
    shown = items[:_MAX_EVIDENCE_ITEMS]
    extra = f"; and {len(items) - len(shown)} more" if len(items) > len(shown) else ""
    return "; ".join(shown) + extra


def _field_values(documents: Any, getter: Callable[..., str | None]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for document in documents:
        value = getter(document.fields)
        if value:
            pairs.append((document.file_name, value))
    return pairs


def _consensus(values: list[str]) -> str | None:
    """Most common value, so one forged document cannot redefine the truth."""
    return Counter(values).most_common(1)[0][0] if values else None


def check_identity_match(data: ScrutinyInput, config: RuleConfig) -> ScrutinyCheck:
    """C1: the person named on the documents must be one person, matching the application."""
    names = _field_values(data.documents, lambda fields: fields.name)
    ids = _field_values(data.documents, lambda fields: fields.id_number)
    offenders: list[str] = []

    for source, pairs, declared in (
        ("FULL_NAME", names, data.declared_name()),
        ("AADHAAR_NUMBER", ids, data.declared_id_number()),
    ):
        reference = declared or _consensus([value for _, value in pairs])
        if reference is None:
            continue
        for file_name, value in pairs:
            if value != reference:
                offenders.append(f"{source} on {file_name} reads '{value}', not '{reference}'")

    if offenders:
        return _build(
            "C1",
            config,
            "fail",
            f"Identity values disagree: {_quote(offenders)}.",
            "The documents do not all belong to the same person as the application, so "
            "the claim cannot be verified automatically. An officer should compare the "
            "name and identity number printed on each document.",
        )
    if not names and not ids:
        return _build(
            "C1",
            config,
            "info",
            "No document in this application printed a name or identity number.",
            "Identity could not be compared because nothing readable was extracted. "
            "Ask the applicant for a legible identity document.",
        )
    compared = len(names) + len(ids)
    return _build(
        "C1",
        config,
        "pass",
        f"{compared} identity value(s) across {len(data.documents)} document(s) all read "
        f"'{names[0][1] if names else data.declared_name()}'.",
        "Every document names the same person as the application, so identity is consistent.",
    )


def check_document_validity(data: ScrutinyInput, config: RuleConfig) -> ScrutinyCheck:
    """C2: dates must be internally possible and the document must not be expired."""
    problems: list[str] = []
    warnings: list[str] = []
    dated = 0

    for document in data.documents:
        fields = document.fields
        if fields.issue_date:
            dated += 1
            if fields.issue_date > data.as_of:
                problems.append(
                    f"{document.file_name}: issued {fields.issue_date.isoformat()}, "
                    f"which is after {data.as_of.isoformat()}"
                )
        if fields.expiry_date and fields.issue_date and fields.expiry_date < fields.issue_date:
            problems.append(
                f"{document.file_name}: expires {fields.expiry_date.isoformat()} before it "
                f"was issued on {fields.issue_date.isoformat()}"
            )
        if fields.expiry_date:
            dated += 1
            if fields.expiry_date < data.as_of:
                days = (data.as_of - fields.expiry_date).days
                problems.append(
                    f"{document.file_name}: expired {fields.expiry_date.isoformat()}, "
                    f"{days} day(s) before {data.as_of.isoformat()}"
                )
        expected = config.authority_expectations.get(document.doc_type)
        if fields.issuing_authority is None:
            warnings.append(f"{document.file_name}: no issuing authority could be read")
        elif expected and expected.lower() not in fields.issuing_authority.lower():
            warnings.append(
                f"{document.file_name}: authority '{fields.issuing_authority}' does not match "
                f"the expected issuer '{expected}'"
            )

    if problems:
        return _build(
            "C2",
            config,
            "fail",
            f"Invalid document dating: {_quote(problems)}.",
            "At least one document is expired or carries impossible dates, so the supporting "
            "evidence is not currently valid.",
        )
    if warnings:
        return _build(
            "C2",
            config,
            "warn",
            f"Dating or issuer concerns: {_quote(warnings)}.",
            "The dates are possible but the issuing authority looks doubtful, so the document "
            "should be eyeballed before approval.",
        )
    if dated == 0:
        return _build(
            "C2",
            config,
            "info",
            f"None of the {len(data.documents)} document(s) printed an issue or expiry date.",
            "Validity could not be assessed from dates; these documents may lack expiry dates.",
        )
    return _build(
        "C2",
        config,
        "pass",
        f"All {dated} date value(s) fall on or before {data.as_of.isoformat()} and every "
        "printed authority matched the expected issuer.",
        "The documents are within their validity period and appear to come from the right office.",
    )


def check_completeness(data: ScrutinyInput, config: RuleConfig) -> ScrutinyCheck:
    """C3: the service's required document set must be present and readable."""
    if not data.required_doc_types:
        return _build(
            "C3",
            config,
            "info",
            f"Service '{data.service_id}' declares no required document types.",
            "There is nothing to check for completeness for this service.",
        )

    attached = {document.doc_type for document in data.documents}
    missing = [doc_type for doc_type in data.required_doc_types if doc_type not in attached]
    unreadable = [
        document.file_name for document in data.documents if not document.fields.legible
    ]

    if missing or unreadable:
        detail = []
        if missing:
            detail.append(f"missing required document type(s): {', '.join(missing)}")
        if unreadable:
            detail.append(f"unreadable file(s): {', '.join(unreadable)}")
        attached_list = ", ".join(sorted(attached)) or "none"
        return _build(
            "C3",
            config,
            "fail",
            f"Incomplete application ({'; '.join(detail)}). "
            f"Required: {', '.join(data.required_doc_types)}; attached: {attached_list}.",
            "The evidence set is incomplete, so the claim cannot be verified without another "
            "document from the applicant.",
        )
    return _build(
        "C3",
        config,
        "pass",
        f"All {len(data.required_doc_types)} required document type(s) "
        f"({', '.join(data.required_doc_types)}) are attached and readable, out of "
        f"{len(data.documents)} submitted file(s).",
        "The applicant attached every document this service asks for and each one could be read.",
    )


def check_cross_field_consistency(data: ScrutinyInput, config: RuleConfig) -> ScrutinyCheck:
    """C4: what the applicant declared must match what the documents state."""
    declared = data.declared_amount()
    stated = [
        (document.file_name, amount)
        for document in data.documents
        for amount in document.fields.amounts
    ]

    if declared is None or not stated:
        return _build(
            "C4",
            config,
            "info",
            f"Declared annual income: {declared if declared is not None else 'not declared'}; "
            f"amounts stated on documents: {[amount for _, amount in stated] or 'none'}.",
            "This service declares no monetary field, so there is nothing to cross-check here.",
        )

    deviations = [(name, amount) for name, amount in stated if amount != declared]
    # An order-of-magnitude gap is a forgery signal (C5), not a declaration mismatch.
    mismatches = [
        (n, amount) for n, amount in deviations if not is_power_of_ten_ratio(amount, declared)
    ]

    if mismatches:
        return _build(
            "C4",
            config,
            "fail",
            f"Declared annual income is {declared}, but "
            f"{_quote([f'{name} states {amount}' for name, amount in mismatches])}.",
            "The income the applicant declared does not agree with the documents they supplied, "
            "so one of them is wrong or out of date.",
        )
    note = ""
    if deviations:
        note = (f" {len(deviations)} amount(s) differ by whole decimal zeros and were routed to "
                "the fraud check instead.")
    return _build(
        "C4",
        config,
        "pass",
        f"Declared annual income {declared} matches the documents"
        f" ({_quote([f'{name}: {amount}' for name, amount in stated])}).{note}",
        "The figures the applicant declared are the same figures the documents state.",
    )


def check_fraud_signals(data: ScrutinyInput, config: RuleConfig) -> ScrutinyCheck:
    """C5: mechanical forgery signals - shared document bytes and padded amounts."""
    duplicates = set(data.duplicate_sha256)
    signals: list[str] = []

    for document in data.documents:
        if document.sha256 in duplicates:
            signals.append(
                f"{document.file_name} has hash {short_hash(document.sha256)} which also appears "
                "in another application"
            )

    declared = data.declared_amount()
    if declared is not None:
        for document in data.documents:
            for amount in document.fields.amounts:
                if is_power_of_ten_ratio(amount, declared):
                    signals.append(
                        f"{document.file_name} states {amount}, exactly an order of ten away "
                        f"from the declared {declared}"
                    )

    if signals:
        return _build(
            "C5",
            config,
            "fail",
            f"Forgery signals: {_quote(signals)}.",
            "These patterns (identical document files across applicants, or amounts with added "
            "zeros) are typical of fabricated paperwork and need officer review.",
        )
    return _build(
        "C5",
        config,
        "pass",
        f"Checked {len(data.documents)} document hash(es) for reuse and "
        f"{sum(len(d.fields.amounts) for d in data.documents)} stated amount(s) for "
        "decimal-zero padding; none matched a known forgery pattern.",
        "No reused document files or suspiciously padded amounts were found in this application.",
    )
