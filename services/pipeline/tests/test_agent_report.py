"""A5 DoD: contract-valid ScrutinyReports for a clean and an anomalous corpus application.

Reports are assembled from the generated corpus (`data/synthetic/dataset-v1`) and validated
against `shared/contracts/openapi.yaml` in-test via tests/contract.py, so the shape check is
the contract itself rather than a hand-written expectation. No network: every adjudicator is
deterministic, scripted, or an injected stub client.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

generator = pytest.importorskip("generator")

from contract import assert_valid  # noqa: E402
from generator.services import required_doc_types  # noqa: E402
from helpers import make_doc, make_input  # noqa: E402

from pipeline.agent import (  # noqa: E402
    Adjudication,
    DeterministicAdjudicator,
    ScrutinyReport,
    run_scrutiny,
    sha256_of_content,
)
from pipeline.extraction import DocumentContent  # noqa: E402
from pipeline.extraction.models import CallMeta  # noqa: E402
from pipeline.rules import ScrutinyCheck, ScrutinyInput  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "data" / "synthetic" / "dataset-v1"
BUILD = {"n": 200, "anomaly_rate": 0.25, "seed": 42}
CHECK_ORDER = ["C1", "C2", "C3", "C4", "C5"]

CLEAN_APP = "APP-0001"  # income_certificate, no planted anomaly
ANOMALOUS_APP = "APP-0117"  # residence_certificate: expired_doc + name_mismatch
GENERATED_AT = dt.datetime(2026, 7, 1, 9, 30, tzinfo=dt.UTC)


@dataclass(frozen=True)
class Corpus:
    """dataset-v1 in the shape the pipeline consumes."""

    root: Path
    applications: list[dict[str, Any]]
    labels: dict[str, dict[str, Any]]
    owners: dict[str, set[str]]  # document sha256 -> applications carrying it
    as_of: dt.date

    def application(self, app_id: str) -> dict[str, Any]:
        return next(app for app in self.applications if app["id"] == app_id)

    def contents(self, app: dict[str, Any]) -> list[DocumentContent]:
        return [
            DocumentContent(
                documentId=doc["id"],
                docType=doc["docType"],
                fileName=doc["fileName"],
                text=(self.root / "docs" / doc["fileName"]).read_text(encoding="utf-8"),
            )
            for doc in app["documents"]
        ]

    def input_for(self, app: dict[str, Any]) -> ScrutinyInput:
        reused = [
            doc["sha256"] for doc in app["documents"] if self.owners[doc["sha256"]] - {app["id"]}
        ]
        return ScrutinyInput(
            applicationId=app["id"],
            serviceId=app["serviceId"],
            requiredDocTypes=required_doc_types(app["serviceId"]),
            applicantFields=app["applicantFields"],
            duplicateSha256=reused,
            asOf=self.as_of,
        )

    def scrutinize(self, app_id: str, **kwargs: Any) -> ScrutinyReport:
        app = self.application(app_id)
        return run_scrutiny(self.input_for(app), self.contents(app), **kwargs)


class ScriptedAdjudicator:
    """Stands in for a model: answers from a dict keyed by check, and records what it was asked."""

    name = "scripted"

    def __init__(self, verdicts: dict[str, Adjudication] | None = None) -> None:
        self.verdicts = verdicts or {}
        self.asked: list[str] = []
        self._fallback = DeterministicAdjudicator()

    @property
    def last_meta(self) -> CallMeta | None:
        return None

    def adjudicate(self, check: ScrutinyCheck, data: ScrutinyInput) -> Adjudication:
        self.asked.append(check.check_id)
        if check.check_id in self.verdicts:
            return self.verdicts[check.check_id]
        return self._fallback.adjudicate(check, data)


def assert_report_valid(report: ScrutinyReport) -> dict[str, Any]:
    """Validate the report and every check in it; return the payload as it goes on the wire."""
    payload = report.model_dump(mode="json", by_alias=True)
    assert_valid(payload, "ScrutinyReport")
    for check in payload["checks"]:
        assert_valid(check, "ScrutinyCheck")
    return payload


def _write_corpus(target: Path) -> Path:
    """The corpus is generated output and uncommitted, so rebuild it if this clone lacks it."""
    apps = generator.build_dataset(**BUILD)
    labels = generator.ground_truth(apps, seed=BUILD["seed"], anomaly_rate=BUILD["anomaly_rate"])
    return generator.write_dataset(apps, labels, target)


def _load_corpus(root: Path) -> Corpus:
    applications = json.loads((root / "applications.json").read_text(encoding="utf-8"))
    truth = json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {}
    for app in applications:
        for doc in app["documents"]:
            owners.setdefault(doc["sha256"], set()).add(app["id"])
    return Corpus(
        root=root,
        applications=applications,
        labels={entry["applicationId"]: entry for entry in truth["applications"]},
        owners=owners,
        as_of=dt.date.fromisoformat(truth["asOf"]),
    )


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    root = DATASET_DIR if (DATASET_DIR / "ground_truth.json").is_file() else _write_corpus(
        tmp_path_factory.mktemp("dataset-v1")
    )
    return _load_corpus(root)


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
    expected: dict[str, str] = corpus.labels[ANOMALOUS_APP]["expected"]

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
        {**base, "checks": [{**base["checks"][0], "severity": "critical"}]},  # nested violation
    ]
    for broken in rejections:
        with pytest.raises(AssertionError, match="does not conform"):
            assert_valid(broken, "ScrutinyReport")


def test_adjudication_replaces_status_and_wording_but_never_evidence() -> None:
    doc = make_doc("aadhaar", authority="Corner Shop Printers")
    document = DocumentContent(
        documentId=doc.document_id,
        docType=doc.doc_type,
        fileName=doc.file_name,
        text=doc.fields.raw_text,
    )

    overturned = ScriptedAdjudicator(
        {"C2": Adjudication(status="pass", explanation="  ")}
    )
    report = run_scrutiny(make_input([doc]), [document], adjudicator=overturned)
    c2 = next(check for check in report.checks if check.check_id == "C2")

    assert c2.status == "pass"
    assert c2.severity == "low"  # severity follows the final status, not the warn it replaced
    assert "Corner Shop Printers" in c2.evidence
    assert c2.explanation  # blank model wording falls back to the rule's own

    escalated = ScriptedAdjudicator(
        {"C2": Adjudication(status="fail", explanation="The issuer is not a public office.")}
    )
    hardened = run_scrutiny(make_input([doc]), [document], adjudicator=escalated)
    hardened_c2 = next(check for check in hardened.checks if check.check_id == "C2")
    assert hardened_c2.status == "fail"
    assert hardened_c2.severity == "high"
    assert hardened_c2.explanation == "The issuer is not a public office."
    assert hardened.risk_score > report.risk_score
