"""A5 DoD: contract-valid ScrutinyReports for a clean and an anomalous corpus application.

Reports are assembled from the generated corpus (`data/synthetic/dataset-v1`) and validated
against `shared/contracts/openapi.yaml` in-test via tests/contract.py, so the shape check is
the contract itself rather than a hand-written expectation. No network: every adjudicator is
deterministic, scripted, or an injected stub client.
"""

from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from typing import Any

import pytest

generator = pytest.importorskip("generator")

from contract import assert_valid  # noqa: E402
from corpus import (  # noqa: E402
    ANOMALOUS_APP,
    CHECK_ORDER,
    CLEAN_APP,
    GENERATED_AT,
    Corpus,
    corpus_or_rebuild,
)
from helpers import ScriptedAdjudicator, make_doc, make_input  # noqa: E402

from pipeline.agent import (  # noqa: E402
    Adjudication,
    ModelMeta,
    ScrutinyReport,
    run_scrutiny,
    sha256_of_content,
)
from pipeline.extraction import DocumentContent  # noqa: E402


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    return corpus_or_rebuild(tmp_path_factory)


def assert_report_valid(report: ScrutinyReport) -> dict[str, Any]:
    """Validate the report and every check in it; return the payload as it goes on the wire."""
    payload = report.model_dump(mode="json", by_alias=True)
    assert_valid(payload, "ScrutinyReport")
    for check in payload["checks"]:
        assert_valid(check, "ScrutinyCheck")
    return payload


def test_clean_application_yields_a_contract_valid_approvable_report(corpus: Corpus) -> None:
    report = corpus.scrutinize(CLEAN_APP, generated_at=GENERATED_AT)
    payload = assert_report_valid(report)

    assert [check.check_id for check in report.checks] == CHECK_ORDER
    assert [check.status for check in report.checks] == ["pass"] * 5
    assert report.recommendation == "approve"
    assert report.risk_score == 0
    assert report.application_id == CLEAN_APP
    assert payload["generatedAt"] == "2026-07-01T09:30:00Z"
    assert payload["modelMeta"] == {
        "extractor": "template",
        "adjudicator": "deterministic",
        "latencyMs": payload["modelMeta"]["latencyMs"],
        "versions": {"rules": "1", "extractor": "code", "adjudicator": "code"},
    }
    assert payload["modelMeta"]["latencyMs"] >= 0
    assert set(payload["extractedFields"]) == {
        doc["id"] for doc in corpus.application(CLEAN_APP)["documents"]
    }
    assert all(check.evidence and check.explanation for check in report.checks)


def test_content_hash_matches_the_generator_for_text_and_decoded_bytes_for_images(
    corpus: Corpus,
) -> None:
    """C5 only means anything if our hash is the generator's hash."""
    app = corpus.application(CLEAN_APP)
    for document, entry in zip(corpus.contents(app), app["documents"], strict=True):
        assert sha256_of_content(document) == entry["sha256"]

    scan = DocumentContent(
        documentId="D1",
        docType="aadhaar",
        fileName="aadhaar.png",
        mimeType="image/png",
        contentBase64=base64.b64encode(b"card scan").decode("ascii"),
    )
    assert sha256_of_content(scan) == hashlib.sha256(b"card scan").hexdigest()


def test_anomalous_application_reports_exactly_the_planted_failures(corpus: Corpus) -> None:
    report = corpus.scrutinize(ANOMALOUS_APP)
    payload = assert_report_valid(report)
    expected = corpus.expected(ANOMALOUS_APP)

    assert [check.check_id for check in report.checks if check.status == "fail"] == [
        check_id for check_id in CHECK_ORDER if expected[check_id] == "fail"
    ]
    assert all(check.severity == "low" for check in report.checks if check.status == "pass")

    c1 = next(check for check in report.checks if check.check_id == "C1")
    declared = corpus.application(ANOMALOUS_APP)["applicantFields"]["fullName"]
    divergent = {fields["name"] for fields in payload["extractedFields"].values()} - {declared}
    assert divergent and next(iter(divergent)) in c1.evidence
    assert c1.severity == "high"

    c2 = next(check for check in report.checks if check.check_id == "C2")
    expired = [
        fields["expiryDate"]
        for fields in payload["extractedFields"].values()
        if fields["expiryDate"] and fields["expiryDate"] < corpus.as_of.isoformat()
    ]
    assert expired and expired[0] in c2.evidence


def test_anomalous_report_scores_above_a_clean_one_and_is_not_approvable(corpus: Corpus) -> None:
    flagged = corpus.scrutinize(ANOMALOUS_APP)
    clean = corpus.scrutinize(CLEAN_APP)
    assert 0 < flagged.risk_score <= 100
    assert flagged.risk_score > clean.risk_score
    assert flagged.recommendation != "approve"


def test_only_ambiguous_checks_reach_the_adjudicator(corpus: Corpus) -> None:
    adjudicator = ScriptedAdjudicator()
    report = corpus.scrutinize(ANOMALOUS_APP, adjudicator=adjudicator)

    statuses = {check.check_id: check.status for check in report.checks}
    assert adjudicator.asked == [
        check_id for check_id, status in statuses.items() if status in ("warn", "info")
    ]
    assert statuses["C4"] == "info"
    c4 = next(check for check in report.checks if check.check_id == "C4")
    assert c4.explanation and c4.explanation != c4.evidence


def test_an_unreadable_upload_fails_completeness_instead_of_crashing(corpus: Corpus) -> None:
    app = corpus.application(CLEAN_APP)
    scan = DocumentContent(
        documentId="SCAN-1",
        docType="fee_receipt",
        fileName="blurry-scan.png",
        mimeType="image/png",
        contentBase64=base64.b64encode(b"not a legible card").decode("ascii"),
    )
    report = run_scrutiny(
        corpus.input_for(app), [*corpus.contents(app), scan], adjudicator=ScriptedAdjudicator()
    )
    payload = assert_report_valid(report)

    c3 = next(check for check in report.checks if check.check_id == "C3")
    assert c3.status == "fail"
    assert "blurry-scan.png" in c3.evidence
    assert payload["extractedFields"]["SCAN-1"]["name"] is None


def test_adjudication_replaces_status_and_wording_but_never_evidence() -> None:
    doc = make_doc("aadhaar", authority="Corner Shop Printers")
    document = DocumentContent(
        documentId=doc.document_id,
        docType=doc.doc_type,
        fileName=doc.file_name,
        text=doc.fields.raw_text,
    )

    overturned = run_scrutiny(
        make_input([doc]),
        [document],
        adjudicator=ScriptedAdjudicator({"C2": Adjudication(status="pass", explanation="  ")}),
    )
    c2 = next(check for check in overturned.checks if check.check_id == "C2")

    assert c2.status == "pass"
    assert c2.severity == "low"  # severity follows the final status, not the warn it replaced
    assert "Corner Shop Printers" in c2.evidence
    assert c2.explanation  # blank model wording falls back to the rule's own

    hardened = run_scrutiny(
        make_input([doc]),
        [document],
        adjudicator=ScriptedAdjudicator(
            {"C2": Adjudication(status="fail", explanation="The issuer is not a public office.")}
        ),
    )
    hardened_c2 = next(check for check in hardened.checks if check.check_id == "C2")
    assert hardened_c2.status == "fail"
    assert hardened_c2.severity == "high"
    assert hardened_c2.explanation == "The issuer is not a public office."
    assert hardened.risk_score > overturned.risk_score


def test_a_hand_built_report_is_the_pinned_contract_shape() -> None:
    """Independent of the corpus: this is exactly what openapi.yaml demands on the wire."""
    report = ScrutinyReport(
        applicationId="APP-1",
        generatedAt=GENERATED_AT,
        extractedFields={"D1": {"name": "Anita Baruah"}},
        checks=[],
        riskScore=0,
        recommendation="approve",
        modelMeta=ModelMeta(extractor="template", adjudicator="deterministic", latencyMs=12),
    )
    payload = report.model_dump(mode="json", by_alias=True)

    assert_valid(payload, "ScrutinyReport")
    assert payload == {
        "applicationId": "APP-1",
        "generatedAt": "2026-07-01T09:30:00Z",
        "extractedFields": {"D1": {"name": "Anita Baruah"}},
        "checks": [],
        "riskScore": 0,
        "recommendation": "approve",
        "modelMeta": {
            "extractor": "template",
            "adjudicator": "deterministic",
            "latencyMs": 12,
            "versions": {},
        },
    }


def test_the_contract_validator_actually_rejects_bad_reports(corpus: Corpus) -> None:
    """A green `assert_report_valid` is only worth something if it can also go red."""
    base = corpus.scrutinize(CLEAN_APP).model_dump(mode="json", by_alias=True)

    missing = deepcopy(base)
    del missing["riskScore"]
    snake_case = deepcopy(base)
    snake_case["risk_score"] = 0
    rejections = [
        missing,  # a required key is gone
        snake_case,  # an undeclared key arrived on the wire
        {**base, "recommendation": "auto_approve"},  # outside the contract enum
        {**base, "riskScore": 101},  # above the declared maximum
        {**base, "generatedAt": "2026-07-01T09:30:00"},  # a date-time without an offset
        {**base, "modelMeta": {**base["modelMeta"], "extractor": 7}},  # wrong nested type
        {**base, "checks": [{**base["checks"][0], "severity": "critical"}]},  # nested violation
    ]
    for broken in rejections:
        with pytest.raises(AssertionError, match="does not conform"):
            assert_valid(broken, "ScrutinyReport")
