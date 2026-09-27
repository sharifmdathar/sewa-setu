"""dataset-v1 as the pipeline consumes it, shared by the agent, fraud and eval tests.

The corpus is generated output and deliberately uncommitted, so `corpus_or_rebuild` rebuilds
it into a temp dir when a fresh clone has not run the generator yet. That costs ~1 s once per
session instead of silently skipping the tests that are Track A's definition of done.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

generator = pytest.importorskip("generator")

from generator.services import required_doc_types  # noqa: E402

from pipeline.agent import ScrutinyReport, run_scrutiny, sha256_of_content  # noqa: E402
from pipeline.extraction import (  # noqa: E402
    DocumentContent,
    ExtractedFields,
    ExtractionError,
    TemplateExtractor,
)
from pipeline.rules import DocEvidence, ScrutinyInput  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "data" / "synthetic" / "dataset-v1"
BUILD = {"n": 200, "anomaly_rate": 0.25, "seed": 42}

CHECK_ORDER = ["C1", "C2", "C3", "C4", "C5"]
CLEAN_APP = "APP-0001"  # income_certificate, nothing planted
ANOMALOUS_APP = "APP-0117"  # residence_certificate: expired_doc + name_mismatch
WORST_APP = "APP-0026"  # caste_certificate: duplicate_hash + field_mismatch + missing_doc
GENERATED_AT = dt.datetime(2026, 7, 1, 9, 30, tzinfo=dt.UTC)


def _evidence(document: DocumentContent) -> DocEvidence:
    """run_scrutiny's extraction step on its own, for tests that score without a report."""
    try:
        fields = TemplateExtractor().extract(document)
    except ExtractionError:
        fields = ExtractedFields(docType=document.doc_type)
    return DocEvidence(
        documentId=document.document_id,
        docType=document.doc_type,
        fileName=document.file_name,
        sha256=sha256_of_content(document),
        fields=fields,
    )


@dataclass(frozen=True)
class Corpus:
    """The generated applications, their labels and the corpus-wide document hash index."""

    root: Path
    applications: list[dict[str, Any]]
    labels: dict[str, dict[str, Any]]
    owners: dict[str, set[str]]  # document sha256 -> applications carrying it
    as_of: dt.date

    def application(self, app_id: str) -> dict[str, Any]:
        return next(app for app in self.applications if app["id"] == app_id)

    def expected(self, app_id: str) -> dict[str, str]:
        entry: dict[str, str] = self.labels[app_id]["expected"]
        return entry

    def is_clean(self, app_id: str) -> bool:
        return bool(self.labels[app_id]["clean"])

    def anomaly_count(self, app_id: str) -> int:
        return len(self.labels[app_id]["anomalies"])

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
        """The application's own fields plus the hashes its documents share with others."""
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

    def input_with_fields(self, app: dict[str, Any]) -> ScrutinyInput:
        """`input_for` with the documents already extracted: what rules and features are given."""
        with_docs = [_evidence(doc) for doc in self.contents(app)]
        return self.input_for(app).model_copy(update={"documents": with_docs})

    def scrutinize(self, app_id: str, **kwargs: Any) -> ScrutinyReport:
        app = self.application(app_id)
        return run_scrutiny(self.input_for(app), self.contents(app), **kwargs)


def write_corpus(target: Path) -> Path:
    apps = generator.build_dataset(**BUILD)
    labels = generator.ground_truth(apps, seed=BUILD["seed"], anomaly_rate=BUILD["anomaly_rate"])
    return generator.write_dataset(apps, labels, target)


def load_corpus(root: Path) -> Corpus:
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


def corpus_or_rebuild(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    on_disk = DATASET_DIR if (DATASET_DIR / "ground_truth.json").is_file() else write_corpus(
        tmp_path_factory.mktemp("dataset-v1")
    )
    return load_corpus(on_disk)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    return corpus_or_rebuild(tmp_path_factory)
