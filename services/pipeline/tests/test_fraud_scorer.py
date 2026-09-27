"""A6 DoD: riskScore rises with every planted anomaly, and clean applications stay low.

The score is SPEC.md section 5's two halves - weighted check outcomes plus fraud signals - so
these tests pin both halves, the rules.yaml bands that turn a score into a recommendation, and
the two corpus claims the prompt asks for (monotonicity, clean apps under the ceiling).
"""

from __future__ import annotations

from typing import Any

import pytest

generator = pytest.importorskip("generator")

from contract import assert_valid  # noqa: E402
from corpus import ANOMALOUS_APP, CLEAN_APP, WORST_APP, Corpus, corpus_or_rebuild  # noqa: E402
from helpers import ScriptedAdjudicator, make_doc, make_input  # noqa: E402

from pipeline.agent import Adjudication, run_scrutiny  # noqa: E402
from pipeline.extraction import DocumentContent  # noqa: E402
from pipeline.fraud import FraudScore, check_points, recommend, score_fraud  # noqa: E402
from pipeline.rules import DocEvidence, ScrutinyCheck, load_rule_config, run_rules  # noqa: E402


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    return corpus_or_rebuild(tmp_path_factory)

CONFIG = load_rule_config()
THREE_DOC_TYPES = ("aadhaar", "bank_statement", "revenue_record")
BANK = "Fictiona Gramin Bank"
TEHSILDAR = "Tehsildar Office"
INCOME = 180000


def score_of(
    docs: list[DocEvidence], *, declared_income: int = INCOME, **kwargs: Any
) -> FraudScore:
    data = make_input(docs, declared_income=declared_income, **kwargs)
    return score_fraud(data, run_rules(data, CONFIG), CONFIG)


def clean_docs() -> list[DocEvidence]:
    return [make_doc("aadhaar"), make_doc("bank_statement", authority=BANK, amount=INCOME)]


def check_of(check_id: str, status: str, severity: str) -> ScrutinyCheck:
    return ScrutinyCheck(
        checkId=check_id,
        label=CONFIG.checks[check_id].label,
        status=status,
        severity=severity,
        evidence="quoted values",
        explanation="what it means",
    )


def corpus_score(corpus: Corpus, app_id: str) -> FraudScore:
    data = corpus.input_with_fields(corpus.application(app_id))
    return score_fraud(data, run_rules(data, CONFIG), CONFIG)


def test_nothing_wrong_scores_nothing() -> None:
    score = score_of(clean_docs())

    assert (score.risk_score, score.signals, score.recommendation, score.flagged) == (
        0,
        [],
        "approve",
        False,
    )


def test_the_score_rises_with_every_planted_anomaly() -> None:
    """0 -> a wrong declaration -> plus a missing document -> plus an expired one."""
    affidavit = make_doc(
        "affidavit", authority="Notary Public", issue="2014-01-31", expiry="2024-01-31"
    )
    plain = score_of(clean_docs())
    misdeclared = score_of(clean_docs(), declared_income=300000)
    short = score_of(clean_docs(), declared_income=300000, required=THREE_DOC_TYPES)
    expired = score_of(
        [*clean_docs(), affidavit], declared_income=300000, required=THREE_DOC_TYPES
    )

    assert plain.risk_score == 0
    assert misdeclared.risk_score < short.risk_score < expired.risk_score < 100
    assert misdeclared.signals == []  # a wrong declaration costs check points, not a fraud signal
    assert [signal.feature for signal in expired.signals] == ["expiredDocument", "missingDocument"]


def test_an_application_tripping_every_signal_saturates_at_one_hundred() -> None:
    forged = make_doc("aadhaar", name="Ganesh Baruah", issue="2014-01-31", expiry="2024-01-31")
    score = score_of(
        [forged, make_doc("bank_statement", authority=BANK, amount=4500000)],
        declared_income=45000,
        required=THREE_DOC_TYPES,
        duplicate_sha256=(forged.sha256,),
    )

    assert score.risk_score == 100
    assert score.signal_points > 100  # the cap, not the arithmetic, is what bound it
    assert score.recommendation == "reject"


def test_the_score_is_the_sum_of_its_two_halves(corpus: Corpus) -> None:
    score = corpus_score(corpus, ANOMALOUS_APP)

    assert score.check_points > 0 and score.signal_points > 0
    assert score.risk_score == round(score.check_points + score.signal_points)
    assert [signal.weight for signal in score.signals] == sorted(
        (signal.weight for signal in score.signals), reverse=True
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "approve"),
        (29, "approve"),
        (30, "request_info"),
        (59, "request_info"),
        (60, "manual_review"),
        (84, "manual_review"),
        (85, "manual_review"),  # high enough to reject, but nothing high-severity failed
        (100, "manual_review"),
    ],
)
def test_recommendation_bands_come_from_rules_yaml(score: int, expected: str) -> None:
    assert recommend(score, [check_of("C1", "pass", "low")], CONFIG) == expected


def test_only_a_high_severity_fail_can_earn_a_reject() -> None:
    high = [check_of("C1", "fail", "high")]
    soft = [check_of("C3", "fail", "medium")]

    assert recommend(90, high, CONFIG) == "reject"
    assert recommend(90, soft, CONFIG) == "manual_review"
    assert recommend(84, high, CONFIG) == "manual_review"


def test_the_checks_half_follows_severity_not_status() -> None:
    points = CONFIG.checks["C2"].weight * CONFIG.severity_multipliers["medium"]

    assert check_points([check_of("C2", "warn", "medium")], CONFIG) == points
    assert check_points([check_of("C2", "fail", "medium")], CONFIG) == points
    assert check_points([check_of("C2", "fail", "high")], CONFIG) > points
    assert check_points([check_of("C2", "pass", "high")], CONFIG) == 0
    assert check_points([check_of("C2", "info", "high")], CONFIG) == 0


def test_clean_corpus_applications_all_score_below_the_clean_ceiling(corpus: Corpus) -> None:
    clean = [app["id"] for app in corpus.applications if corpus.is_clean(app["id"])]
    scores = {app_id: corpus_score(corpus, app_id).risk_score for app_id in clean}

    assert len(clean) == 150
    assert max(scores.values()) < CONFIG.clean_ceiling


def test_more_planted_anomalies_score_higher_on_real_data(corpus: Corpus) -> None:
    single = next(app["id"] for app in corpus.applications if corpus.anomaly_count(app["id"]) == 1)
    ladder = {
        count: corpus_score(corpus, app_id).risk_score
        for count, app_id in [(1, single), (2, ANOMALOUS_APP), (3, WORST_APP)]
    }

    assert corpus.anomaly_count(WORST_APP) == 3
    assert ladder[1] < ladder[2] < ladder[3] < 100


def test_every_flagged_application_is_an_anomalous_one(corpus: Corpus) -> None:
    flagged = [app["id"] for app in corpus.applications if corpus_score(corpus, app["id"]).flagged]

    assert flagged, "nothing reaches the flag threshold, so the queue ordering is untested"
    assert all(not corpus.is_clean(app_id) for app_id in flagged)
    assert all(corpus.scrutinize(app_id).risk_score >= CONFIG.flag_threshold for app_id in flagged)


def test_settling_a_warn_to_pass_lowers_the_risk_and_still_validates(corpus: Corpus) -> None:
    doc = make_doc("aadhaar", authority="Corner Shop Printers")
    upload = DocumentContent(
        documentId=doc.document_id,
        docType=doc.doc_type,
        fileName=doc.file_name,
        text=doc.fields.raw_text,
    )

    warned = run_scrutiny(make_input([doc]), [upload])
    settled = run_scrutiny(
        make_input([doc]),
        [upload],
        adjudicator=ScriptedAdjudicator({"C2": Adjudication(status="pass", explanation="Fine.")}),
    )

    assert warned.checks[1].status == "warn"
    assert settled.checks[1].status == "pass"
    assert settled.risk_score < warned.risk_score
    for report in (warned, settled):
        payload = report.model_dump(mode="json", by_alias=True)
        assert_valid(payload, "ScrutinyReport")
        assert "signals" not in payload  # the scorer's detail stays off the contract wire


def test_a_clean_report_keeps_a_zero_score_after_scoring(corpus: Corpus) -> None:
    report = corpus.scrutinize(CLEAN_APP)

    assert report.risk_score == 0
    assert report.recommendation == "approve"
    assert_valid(report.model_dump(mode="json", by_alias=True), "ScrutinyReport")
