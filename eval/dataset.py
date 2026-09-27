"""Load dataset-v1 as pipeline input, offline.

Deliberately separate from `services/pipeline/tests/corpus.py`: that helper exists to assert
things about the pipeline, this one is the eval harness's own view of the corpus and must not
import test code. The required document types come from `pipeline.api.catalog`, the same
catalogue the live API serves, so the harness and the service can never disagree about them.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.api.catalog import get as service_for
from pipeline.extraction import DocumentContent
from pipeline.rules import ScrutinyInput

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "dataset-v1"
CHECKS = ("C1", "C2", "C3", "C4", "C5")


@dataclass(frozen=True)
class Case:
    """One application: what the pipeline is given and what the generator says is wrong with it."""

    application_id: str
    service_id: str
    clean: bool
    anomalies: tuple[str, ...]
    expected: dict[str, str]
    data: ScrutinyInput
    documents: list[DocumentContent]

    @property
    def expected_fails(self) -> list[str]:
        return [check for check in CHECKS if self.expected[check] == "fail"]


@dataclass(frozen=True)
class Dataset:
    root: Path
    as_of: dt.date
    seed: int
    requested_anomaly_rate: float
    counts: dict[str, Any]
    cases: list[Case]

    @property
    def size(self) -> int:
        return len(self.cases)

    @property
    def anomalous(self) -> list[str]:
        return [case.application_id for case in self.cases if not case.clean]


def load(root: Path | str = DEFAULT_DATASET) -> Dataset:
    """Read applications.json, ground_truth.json and the document files into runnable cases."""
    directory = Path(root)
    applications = json.loads((directory / "applications.json").read_text(encoding="utf-8"))
    truth = json.loads((directory / "ground_truth.json").read_text(encoding="utf-8"))
    labels = {entry["applicationId"]: entry for entry in truth["applications"]}
    owners: dict[str, set[str]] = {}
    for app in applications:
        for document in app["documents"]:
            owners.setdefault(document["sha256"], set()).add(app["id"])

    as_of = dt.date.fromisoformat(truth["asOf"])
    cases = [
        _case(app, labels[app["id"]], directory, owners, as_of) for app in applications
    ]
    return Dataset(
        root=directory,
        as_of=as_of,
        seed=int(truth["seed"]),
        requested_anomaly_rate=float(truth["requestedAnomalyRate"]),
        counts=dict(truth["counts"]),
        cases=cases,
    )


def _case(
    app: dict[str, Any],
    label: dict[str, Any],
    root: Path,
    owners: dict[str, set[str]],
    as_of: dt.date,
) -> Case:
    service = service_for(str(app["serviceId"]))
    documents = [
        DocumentContent(
            documentId=str(document["id"]),
            docType=str(document["docType"]),
            fileName=str(document["fileName"]),
            text=(root / "docs" / str(document["fileName"])).read_text(encoding="utf-8"),
        )
        for document in app["documents"]
    ]
    data = ScrutinyInput(
        applicationId=str(app["id"]),
        serviceId=str(app["serviceId"]),
        requiredDocTypes=list(service.required_doc_types) if service else [],
        applicantFields=dict(app["applicantFields"]),
        duplicateSha256=[
            document["sha256"]
            for document in app["documents"]
            if owners[document["sha256"]] - {app["id"]}
        ],
        asOf=as_of,
    )
    return Case(
        application_id=str(app["id"]),
        service_id=str(app["serviceId"]),
        clean=bool(label["clean"]),
        anomalies=tuple(label["anomalies"]),
        expected={check: str(label["expected"][check]) for check in CHECKS},
        data=data,
        documents=documents,
    )
