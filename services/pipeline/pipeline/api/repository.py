"""Application state over the JSON store: status, timeline, documents, reports, queue, metrics.

One record per application, holding its documents inline. The stored record is a superset of
the contract's `Application` (which has no documents field), so `application_view` is the only
shape allowed to leave the process - `tests/contract.py` rejects undeclared keys.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Any

from pipeline.agent import ScrutinyReport
from pipeline.api import catalog, readmodel
from pipeline.extraction import DocumentContent
from pipeline.ingestion import stored_document, to_content
from pipeline.rules import RuleConfig, ScrutinyInput
from pipeline.store.jsonstore import JsonStore

APPLICATIONS = "applications"
REPORTS = "reports"


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _stamp(moment: dt.datetime) -> str:
    return moment.isoformat()


def _event(moment: dt.datetime, actor: str, event: str, message: str) -> dict[str, Any]:
    return {"at": _stamp(moment), "actor": actor, "event": event, "message": message}


def new_application_id() -> str:
    return f"APP-{uuid.uuid4().hex[:10].upper()}"


class Repository:
    """Everything the contract routes need from the store, and nothing HTTP."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.store = JsonStore(root)

    # --- applications ---------------------------------------------------------------

    def get(self, application_id: str) -> dict[str, Any] | None:
        record = self.store.get(APPLICATIONS, application_id)
        return record if isinstance(record, dict) else None

    def all(self) -> list[dict[str, Any]]:
        return self.store.list(APPLICATIONS)

    def create(self, service_id: str, applicant_fields: dict[str, Any]) -> dict[str, Any]:
        moment = now()
        return self.store.put(
            APPLICATIONS,
            {
                "id": new_application_id(),
                "serviceId": service_id,
                "status": "submitted",
                "applicantFields": dict(applicant_fields),
                "createdAt": _stamp(moment),
                "updatedAt": _stamp(moment),
                "timeline": [
                    _event(moment, "citizen", "submitted", "Application submitted by the citizen.")
                ],
                "documents": [],
            },
        )

    def seed_application(
        self,
        application_id: str,
        service_id: str,
        applicant_fields: dict[str, Any],
        documents: list[dict[str, Any]],
        created_at: str,
    ) -> dict[str, Any]:
        """Write a complete, already-uploaded application under a caller-chosen id.

        The demo seeder needs corpus ids and the corpus's own submission timestamps so that
        re-seeding is reproducible; `create` gives neither, and back-dating a document by
        stamping it `now()` would put a false time in the citizen's timeline.
        """
        submitted = dt.datetime.fromisoformat(created_at)
        timeline = [
            _event(submitted, "citizen", "submitted", "Application submitted by the citizen.")
        ]
        timeline += [
            _event(
                dt.datetime.fromisoformat(str(document["uploadedAt"])),
                "citizen",
                "document_uploaded",
                f"Uploaded {document['fileName']} as {document['docType']}.",
            )
            for document in documents
        ]
        return self.store.put(
            APPLICATIONS,
            {
                "id": application_id,
                "serviceId": service_id,
                "status": "documents_uploaded",
                "applicantFields": dict(applicant_fields),
                "createdAt": created_at,
                "updatedAt": str(documents[-1]["uploadedAt"]) if documents else created_at,
                "timeline": timeline,
                "documents": documents,
            },
        )

    def _transition(
        self, record: dict[str, Any], status: str, actor: str, event: str, message: str
    ) -> dict[str, Any]:
        moment = now()
        updated = {
            **record,
            "status": status,
            "updatedAt": _stamp(moment),
            "timeline": [*record["timeline"], _event(moment, actor, event, message)],
        }
        return self.store.put(APPLICATIONS, updated)

    # --- documents ------------------------------------------------------------------

    def add_document(
        self, record: dict[str, Any], doc_type: str, file_name: str, content_base64: str
    ) -> dict[str, Any]:
        moment = now()
        document = stored_document(
            f"{record['id']}-D{len(record['documents']) + 1}",
            doc_type,
            file_name,
            content_base64,
            _stamp(moment),
        )
        with_docs = {**record, "documents": [*record["documents"], document]}
        self.store.put(APPLICATIONS, with_docs)
        return self._transition(
            with_docs,
            "documents_uploaded",
            "citizen",
            "document_uploaded",
            f"Uploaded {file_name} as {doc_type}.",
        )

    def shared_hashes(self, record: dict[str, Any]) -> list[str]:
        """Hashes this application's documents also appear under in *other* applications."""
        owners: dict[str, set[str]] = {}
        for other in self.all():
            for document in other.get("documents", []):
                owners.setdefault(document["sha256"], set()).add(other["id"])
        return [
            document["sha256"]
            for document in record["documents"]
            if owners[document["sha256"]] - {record["id"]}
        ]

    def scrutiny_request(
        self, record: dict[str, Any], as_of: dt.date
    ) -> tuple[ScrutinyInput, list[DocumentContent]]:
        """Wire one stored application into A3-A6's entry point."""
        service = catalog.get(str(record["serviceId"]))
        data = ScrutinyInput(
            applicationId=str(record["id"]),
            serviceId=str(record["serviceId"]),
            requiredDocTypes=list(service.required_doc_types) if service else [],
            applicantFields=dict(record["applicantFields"]),
            duplicateSha256=self.shared_hashes(record),
            asOf=as_of,
        )
        return data, [to_content(document) for document in record["documents"]]

    # --- scrutiny and decisions --------------------------------------------------------

    def mark_scrutiny_pending(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._transition(
            record,
            "scrutiny_pending",
            "system",
            "scrutiny_started",
            "Automated scrutiny started.",
        )

    def save_report(
        self, report: ScrutinyReport, scrutiny_ms: float | None = None
    ) -> dict[str, Any]:
        record = self.get(report.application_id)
        if record is None:  # the report names an application that is not in the store
            raise KeyError(report.application_id)
        self.store.put(REPORTS, report.model_dump(mode="json", by_alias=True))
        if scrutiny_ms is not None:
            record = self.store.put(APPLICATIONS, {**record, "scrutinyMs": scrutiny_ms})
        return self._transition(
            record,
            "scrutiny_done",
            "system",
            "scrutiny_done",
            f"Automated scrutiny finished with a risk score of {report.risk_score} "
            f"and a recommendation to {report.recommendation}.",
        )

    def get_report(self, application_id: str) -> dict[str, Any] | None:
        report = self.store.get(REPORTS, application_id)
        return report if isinstance(report, dict) else None

    def decide(
        self, record: dict[str, Any], decision: str, officer_notes: str
    ) -> dict[str, Any]:
        status = "info_requested" if decision == "request_info" else "decided"
        return self._transition(
            record,
            status,
            "officer",
            f"decision_{decision}",
            f"Officer decision: {decision}. {officer_notes}".strip(),
        )

    # --- queue and metrics ---------------------------------------------------------------

    def queue(self) -> list[dict[str, Any]]:
        """Every application with its status and risk score, highest risk first (CR-2)."""
        return readmodel.queue_items(self.all(), self.get_report)

    def metrics(self, config: RuleConfig, generated_at: dt.datetime) -> dict[str, Any]:
        """`MetricsSummary`, the two chart series and the harness's own numbers included."""
        return readmodel.metrics(self.all(), self.get_report, config, generated_at)

