"""A6 features: each forgery pattern trips exactly one feature, and clean documents trip none."""

from __future__ import annotations

from typing import get_args

import pytest

generator = pytest.importorskip("generator")

from corpus import Corpus, corpus_or_rebuild  # noqa: E402
from helpers import make_blank_doc, make_doc, make_input  # noqa: E402

from pipeline.fraud import FEATURES, FraudFeature, extract_signals  # noqa: E402
from pipeline.fraud.features import (  # noqa: E402
    duplicate_hash,
    expiry_anomalies,
    identity_divergence,
    missing_documents,
    tampered_amount,
)
from pipeline.rules import RuleConfig, ScrutinyInput, load_rule_config  # noqa: E402


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    return corpus_or_rebuild(tmp_path_factory)

CONFIG = load_rule_config()
BANK = "Fictiona Gramin Bank"


def features(data: ScrutinyInput, config: RuleConfig = CONFIG) -> list[str]:
    return [signal.feature for signal in extract_signals(data, config)]


def corpus_features(corpus: Corpus, app: dict[str, object]) -> list[str]:
    return features(corpus.input_with_fields(app))


def test_the_feature_names_are_exactly_the_rules_yaml_weights() -> None:
    assert set(get_args(FraudFeature)) == set(CONFIG.fraud_weights)
    assert len(FEATURES) == len(CONFIG.fraud_weights)


def test_an_ordinary_application_trips_no_feature() -> None:
    assert features(make_input([make_doc("aadhaar")])) == []


def test_a_document_shared_with_another_application_is_a_duplicate_signal() -> None:
    doc = make_doc("aadhaar")
    cloned = make_input([doc], duplicate_sha256=(doc.sha256,))
    signal = duplicate_hash(cloned, CONFIG)

    assert features(make_input([doc])) == []
    assert signal is not None
    assert signal.feature == "duplicateDocumentHash"
    assert signal.weight == CONFIG.fraud_weights["duplicateDocumentHash"]
    assert doc.sha256[:12] in signal.detail


def test_an_amount_padded_with_decimal_zeros_is_a_tampering_signal() -> None:
    docs = [make_doc("aadhaar"), make_doc("bank_statement", authority=BANK, amount=4500000)]
    data = make_input(docs, declared_income=45000)

    assert features(data) == ["tamperedAmount"]
    signal = tampered_amount(data, CONFIG)
    assert signal is not None and "4500000" in signal.detail and "45000" in signal.detail


def test_a_honest_amount_that_simply_differs_is_not_tampering() -> None:
    docs = [make_doc("aadhaar"), make_doc("bank_statement", authority=BANK, amount=90000)]
    assert features(make_input(docs, declared_income=300000)) == []


def test_a_document_naming_someone_else_is_an_identity_signal() -> None:
    docs = [make_doc("aadhaar"), make_doc("bank_statement", authority=BANK, name="Ganesh Baruah")]
    signal = identity_divergence(make_input(docs), CONFIG)

    assert signal is not None
    assert signal.feature == "identityDivergence"
    assert "Ganesh Baruah" in signal.detail


def test_a_diverging_identity_number_alone_counts() -> None:
    odd = make_doc("affidavit", authority="Notary Public", aadhaar="9999 9999 9999")
    docs = [make_doc("aadhaar"), odd]
    signal = identity_divergence(make_input(docs), CONFIG)

    assert signal is not None and "9999 9999 9999" in signal.detail


def test_expired_and_impossible_dates_are_expiry_signals() -> None:
    expired = make_doc("aadhaar", issue="2015-01-31", expiry="2025-01-31")
    forged = make_doc("aadhaar", issue="2030-01-01", expiry=None)
    dated = expiry_anomalies(make_input([expired]), CONFIG)
    forward = expiry_anomalies(make_input([forged]), CONFIG)

    assert dated is not None and "2025-01-31" in dated.detail
    assert forward is not None and "2030-01-01" in forward.detail


def test_a_current_document_is_not_an_expiry_signal() -> None:
    data = make_input([make_doc("aadhaar", issue="2024-01-05", expiry="2034-01-05")])
    assert expiry_anomalies(data, CONFIG) is None


def test_a_missing_required_document_is_a_completeness_signal() -> None:
    data = make_input([make_doc("aadhaar")], required=("aadhaar", "bank_statement"))
    signal = missing_documents(data, CONFIG)

    assert signal is not None
    assert signal.feature == "missingDocument"
    assert "bank_statement" in signal.detail


def test_an_unreadable_attachment_is_also_a_completeness_signal() -> None:
    data = make_input([make_doc("aadhaar"), make_blank_doc("bank_statement")])
    assert features(data) == ["missingDocument"]


def test_a_feature_counts_once_however_many_documents_trip_it() -> None:
    docs = [
        make_doc("aadhaar", issue=f"201{year}-01-31", expiry=f"202{year}-01-31")
        for year in range(0, 4)
    ]
    signals = extract_signals(make_input(docs), CONFIG)

    assert [signal.feature for signal in signals] == ["expiredDocument"]
    assert "and 1 more" in signals[0].detail  # the detail truncates, the weight does not


def test_signals_come_back_heaviest_first() -> None:
    doc = make_doc("aadhaar", issue="2015-01-31", expiry="2025-01-31")
    data = make_input([doc, make_doc("affidavit", authority="Notary Public", expiry=None)])
    data = data.model_copy(update={"duplicate_sha256": [doc.sha256]})

    assert features(data) == ["duplicateDocumentHash", "expiredDocument"]


IMPLIES: dict[str, str | None] = {
    "name_mismatch": "identityDivergence",
    "expired_doc": "expiredDocument",
    "missing_doc": "missingDocument",
    "duplicate_hash": "duplicateDocumentHash",
    "tampered_number": "tamperedAmount",
    # field_mismatch is absent on purpose: a declaration that disagrees with the documents is
    # a C4 finding, and rules.yaml gives it no fraud weight.
    "field_mismatch": None,
}


def test_the_tripped_features_are_exactly_the_planted_anomalies(corpus: Corpus) -> None:
    """Over all 200 applications: no false feature, and no planted anomaly without one."""
    planted = {
        anomaly for app in corpus.applications for anomaly in corpus.labels[app["id"]]["anomalies"]
    }
    assert set(IMPLIES) == planted  # every anomaly type is actually exercised below

    off_signature = []
    for app in corpus.applications:
        anomalies = corpus.labels[app["id"]]["anomalies"]
        wanted = {IMPLIES[anomaly] for anomaly in anomalies} - {None}
        got = {signal.feature for signal in extract_signals(corpus.input_with_fields(app), CONFIG)}
        if got != wanted:
            off_signature.append((app["id"], sorted(anomalies), sorted(got), sorted(wanted)))

    assert off_signature == []
    tripped = {feature for app in corpus.applications for feature in corpus_features(corpus, app)}
    assert tripped == set(IMPLIES.values()) - {None}
