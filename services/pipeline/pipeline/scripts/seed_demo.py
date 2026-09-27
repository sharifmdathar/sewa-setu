"""Seed a deterministic demo slice of dataset-v1 into the JSON store (integration step I2).

    python -m pipeline.scripts.seed_demo [--root VAR_DIR] [--limit 20] [--dataset PATH]

Goes through the same objects the live API uses - `Repository` for the record and timeline,
`run_scrutiny` for extraction, rules, adjudication and scoring - so a seeded store is
indistinguishable from one the citizen UI filled in by hand. No HTTP and no model: with
`LLM_API_KEY` unset this is the template extractor plus the deterministic adjudicator, which is
the same configuration the eval numbers were produced with.

Determinism: application ids, document ids, `createdAt` and each document's `uploadedAt` come
from the corpus, and `asOf` defaults to the corpus's own date (its labels were computed against
it), so checks, evidence, `riskScore` and `recommendation` are identical between runs. Two
timestamps still follow the clock - the report's `generatedAt` and the record's final
`updatedAt` - because they record *when the seeding ran*.

Idempotency: only generator-shaped ids (`APP-0001` .. `APP-00NN`) are cleared first, so re-seeding
replaces the demo set - including a previously larger one - while anything submitted through the
API (`APP-<10 hex>`) is left alone.

Reads the corpus itself rather than importing `eval/dataset.py`: the eval harness may depend on
the pipeline, never the other way round, and `pipeline` is installed while `eval` is not.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.agent import run_scrutiny
from pipeline.api.catalog import get as service_for
from pipeline.api.repository import Repository
from pipeline.extraction import DocumentContent
from pipeline.ingestion import stored_document
from pipeline.logs import configure, event, get_logger
from pipeline.rules import ScrutinyInput, load_rule_config

LOGGER = get_logger("scripts.seed_demo")

DEMO_LIMIT = 20
DEMO_ID = re.compile(r"^APP-\d{4}$")
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATASET = REPO_ROOT / "data" / "synthetic" / "dataset-v1"


class DatasetMissing(RuntimeError):
    """The corpus was never generated, so there is nothing to seed from."""


@dataclass(frozen=True)
class DemoCase:
    """One corpus application, shaped for the pipeline plus the labels it should reproduce."""

    application_id: str
    service_id: str
    applicant_fields: dict[str, Any]
    created_at: str
    documents: list[DocumentContent]
    uploads: list[tuple[str, str]]  # (docType, uploadedAt) by position, matching documents
    clean: bool
    anomalies: tuple[str, ...]


@dataclass
class SeedResult:
    """What the run wrote, so the caller and the test can assert on it."""

    root: Path
    seeded: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)
    high_risk: list[tuple[str, int]] = field(default_factory=list)
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def flagged(self) -> list[str]:
        return [app_id for app_id, _ in self.high_risk]


def load_cases(dataset: Path = DEFAULT_DATASET, limit: int = DEMO_LIMIT) -> list[DemoCase]:
    """The first `limit` corpus applications, with their document text read in."""
    missing = not (dataset / "applications.json").is_file()
    missing = missing or not (dataset / "ground_truth.json").is_file()
    if missing:
        raise DatasetMissing(
            f"{dataset} has no applications.json/ground_truth.json - generate it with:"
            "\n  python -m generator --n 200 --anomaly-rate 0.25 --seed 42 "
            "--out data/synthetic/dataset-v1"
        )

    applications = json.loads((dataset / "applications.json").read_text(encoding="utf-8"))
    labels = {
        entry["applicationId"]: entry
        for entry in json.loads((dataset / "ground_truth.json").read_text(encoding="utf-8"))[
            "applications"
        ]
    }
    cases: list[DemoCase] = []
    for app in applications[:limit]:
        app_id = str(app["id"])
        documents: list[DocumentContent] = []
        uploads: list[tuple[str, str]] = []
        for document in app["documents"]:
            file_name = str(document["fileName"])
            documents.append(
                DocumentContent(
                    documentId=str(document["id"]),
                    docType=str(document["docType"]),
                    fileName=file_name,
                    text=(dataset / "docs" / file_name).read_text(encoding="utf-8"),
                )
            )
            uploads.append((str(document["docType"]), str(document["uploadedAt"])))
        entry = labels.get(app_id, {})
        cases.append(
            DemoCase(
                application_id=app_id,
                service_id=str(app["serviceId"]),
                applicant_fields=dict(app["applicantFields"]),
                created_at=str(app["createdAt"]),
                documents=documents,
                uploads=uploads,
                clean=bool(entry.get("clean", True)),
                anomalies=tuple(entry.get("anomalies", ())),
            )
        )
    return cases


def clear_demo_records(repository: Repository) -> list[str]:
    """Delete every generator-shaped application and its report; API-created ids are untouched."""
    removed: list[str] = []
    for record in repository.all():
        app_id = str(record["id"])
        if not DEMO_ID.match(app_id):
            continue
        repository.store.delete("reports", app_id)
        if repository.store.delete("applications", app_id):
            removed.append(app_id)
    return removed


def _stored_documents(case: DemoCase) -> list[dict[str, Any]]:
    """The intake record for each document, exactly as an upload would have written it."""
    return [
        stored_document(
            document.document_id,
            doc_type,
            document.file_name,
            base64.b64encode(str(document.text or "").encode("utf-8")).decode("ascii"),
            uploaded_at,
        )
        for document, (doc_type, uploaded_at) in zip(case.documents, case.uploads, strict=True)
    ]


def _input_for(
    case: DemoCase,
    repository: Repository,
    stored: list[dict[str, Any]],
    as_of: dt.date,
) -> ScrutinyInput:
    """The declaration, plus the hashes this application shares with others already in the store."""
    service = service_for(case.service_id)
    mine = [str(record["sha256"]) for record in stored]
    elsewhere = {
        str(document["sha256"])
        for other in repository.all()
        if str(other["id"]) != case.application_id
        for document in other.get("documents", [])
    }
    return ScrutinyInput(
        applicationId=case.application_id,
        serviceId=case.service_id,
        requiredDocTypes=list(service.required_doc_types) if service else [],
        applicantFields=case.applicant_fields,
        duplicateSha256=[sha for sha in mine if sha in elsewhere],
        asOf=as_of,
    )


def corpus_as_of(dataset: Path) -> dt.date:
    """The date the corpus labels were computed against; scoring against today would move them."""
    truth = json.loads((dataset / "ground_truth.json").read_text(encoding="utf-8"))
    return dt.date.fromisoformat(str(truth["asOf"]))


def seed(
    root: str | Path | None = None,
    limit: int = DEMO_LIMIT,
    dataset: Path = DEFAULT_DATASET,
    as_of: dt.date | None = None,
) -> SeedResult:
    """Replace the demo slice in the store at `root` and scrutinize every application."""
    configure()
    repository = Repository(root)
    result = SeedResult(root=repository.store.root)
    result.cleared = clear_demo_records(repository)

    cases = load_cases(dataset, limit)
    stamp = as_of if as_of is not None else corpus_as_of(dataset)
    threshold = load_rule_config().flag_threshold

    # Two passes on purpose: every application must see the whole demo slice in the store before
    # any of them is scored, or a duplicate pair is flagged for whichever twin was written last.
    uploaded = [
        (case, _stored_documents(case))
        for case in cases
    ]
    for case, stored in uploaded:
        repository.seed_application(
            application_id=case.application_id,
            service_id=case.service_id,
            applicant_fields=case.applicant_fields,
            documents=stored,
            created_at=case.created_at,
        )

    for case, stored in uploaded:
        data = _input_for(case, repository, stored, stamp)
        started = time.perf_counter()
        report = run_scrutiny(data, case.documents)
        repository.save_report(report, scrutiny_ms=(time.perf_counter() - started) * 1000)
        result.seeded.append(case.application_id)
        result.reports[case.application_id] = repository.get_report(case.application_id) or {}
        if report.risk_score >= threshold:
            result.high_risk.append((case.application_id, report.risk_score))
        event(
            LOGGER,
            "demo application seeded",
            applicationId=case.application_id,
            riskScore=report.risk_score,
            recommendation=report.recommendation,
            documents=len(stored),
            sharedDocuments=len(data.duplicate_sha256),
            planted=list(case.anomalies),
        )

    event(
        LOGGER,
        "demo seed complete",
        root=str(result.root),
        seeded=len(result.seeded),
        cleared=len(result.cleared),
        highRisk=len(result.high_risk),
        asOf=stamp.isoformat(),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the JSON store with a dataset-v1 demo slice")
    parser.add_argument("--root", type=Path, default=None, help="store directory (default: var/)")
    parser.add_argument("--limit", type=int, default=DEMO_LIMIT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    arguments = parser.parse_args(argv)

    try:
        result = seed(arguments.root, arguments.limit, arguments.dataset)
    except DatasetMissing as exc:
        print(f"error: {exc}")
        return 2

    threshold = load_rule_config().flag_threshold
    print(
        f"seeded {len(result.seeded)} applications into {result.root} "
        f"(cleared {len(result.cleared)} from a previous demo seed)"
    )
    print(f"  high risk (>={threshold}): {', '.join(result.flagged) or 'none'}")
    for app_id, score in result.high_risk:
        print(f"    {app_id}  riskScore {score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
