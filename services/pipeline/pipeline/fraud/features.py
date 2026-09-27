"""Mechanical fraud features, read straight off the documents (no model involved).

Each feature deliberately mirrors one rule predicate in `pipeline/rules/checks.py`, so the
score corroborates the officer-facing check rather than quietly disagreeing with it: a feature
answers "did the bytes say so", the check answers "what should the officer read". A test over
dataset-v1 asserts the two stay aligned per planted anomaly type.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

from pipeline.fraud.models import FraudFeature, FraudSignal
from pipeline.rules.models import DocEvidence, RuleConfig, ScrutinyInput
from pipeline.rules.numeric import is_power_of_ten_ratio, short_hash

_MAX_DETAIL_ITEMS = 3

Extractor = Callable[[ScrutinyInput, RuleConfig], FraudSignal | None]


def _signal(
    config: RuleConfig, feature: FraudFeature, items: Sequence[str], noun: str
) -> FraudSignal | None:
    """One signal per feature kind: three shared files are one duplicate, not three."""
    if not items:
        return None
    shown = list(items[:_MAX_DETAIL_ITEMS])
    extra = f"; and {len(items) - len(shown)} more" if len(items) > len(shown) else ""
    return FraudSignal(
        feature=feature,
        weight=config.fraud_weights[feature],
        detail=f"{noun}: {', '.join(shown)}{extra}",
    )


def _values(documents: Sequence[DocEvidence], getter: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for document in documents:
        value = getattr(document.fields, getter)
        if value:
            pairs.append((document.file_name, str(value)))
    return pairs


def _divergent(pairs: Sequence[tuple[str, str]], reference: str | None) -> list[str]:
    """Against the declaration when there is one, otherwise against the document majority."""
    if reference is None:
        reference = Counter(value for _, value in pairs).most_common(1)[0][0] if pairs else None
    if reference is None:
        return []
    return [
        f"{file_name} reads '{value}', not '{reference}'"
        for file_name, value in pairs
        if value != reference
    ]


def duplicate_hash(data: ScrutinyInput, config: RuleConfig) -> FraudSignal | None:
    reused = set(data.duplicate_sha256)
    files = [
        f"{document.file_name} ({short_hash(document.sha256)})"
        for document in data.documents
        if document.sha256 in reused
    ]
    return _signal(
        config, "duplicateDocumentHash", files, "document bytes shared with another application"
    )


def tampered_amount(data: ScrutinyInput, config: RuleConfig) -> FraudSignal | None:
    declared = data.declared_amount()
    if declared is None:
        return None
    padded = [
        f"{document.file_name} states {amount} against the declared {declared}"
        for document in data.documents
        for amount in document.fields.amounts
        if is_power_of_ten_ratio(amount, declared)
    ]
    return _signal(config, "tamperedAmount", padded, "amount padded by whole decimal zeros")


def identity_divergence(data: ScrutinyInput, config: RuleConfig) -> FraudSignal | None:
    offenders = _divergent(_values(data.documents, "name"), data.declared_name())
    offenders += _divergent(_values(data.documents, "id_number"), data.declared_id_number())
    return _signal(config, "identityDivergence", offenders, "identity value disagrees")


def expiry_anomalies(data: ScrutinyInput, config: RuleConfig) -> FraudSignal | None:
    problems: list[str] = []
    for document in data.documents:
        fields = document.fields
        if fields.issue_date and fields.issue_date > data.as_of:
            problems.append(f"{document.file_name} issued {fields.issue_date} after {data.as_of}")
        elif fields.expiry_date and fields.issue_date and fields.expiry_date < fields.issue_date:
            problems.append(
                f"{document.file_name} expires {fields.expiry_date} before it was issued"
            )
        elif fields.expiry_date and fields.expiry_date < data.as_of:
            problems.append(f"{document.file_name} expired {fields.expiry_date}")
    return _signal(config, "expiredDocument", problems, "expired or impossible dating")


def missing_documents(data: ScrutinyInput, config: RuleConfig) -> FraudSignal | None:
    attached = {document.doc_type for document in data.documents}
    gaps = [
        f"required document type '{doc_type}' is not attached"
        for doc_type in data.required_doc_types
        if doc_type not in attached
    ]
    gaps += [
        f"{document.file_name} yielded no readable fields"
        for document in data.documents
        if not document.fields.legible
    ]
    return _signal(config, "missingDocument", gaps, "required evidence absent")


FEATURES: tuple[Extractor, ...] = (
    duplicate_hash,
    tampered_amount,
    identity_divergence,
    expiry_anomalies,
    missing_documents,
)


def extract_signals(data: ScrutinyInput, config: RuleConfig) -> list[FraudSignal]:
    """Every feature this application trips, heaviest first (the scorer's top signals)."""
    found = [
        signal
        for signal in (feature(data, config) for feature in FEATURES)
        if signal is not None
    ]
    return sorted(found, key=lambda signal: -signal.weight)
