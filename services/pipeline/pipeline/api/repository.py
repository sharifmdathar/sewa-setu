"""Application state over the JSON store: status, timeline, documents, reports, queue, metrics.

One record per application, holding its documents inline. The stored record is a superset of
the contract's `Application` (which has no documents field), so `application_view` is the only
shape allowed to leave the process - `tests/contract.py` rejects undeclared keys.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

from pipeline.agent import ScrutinyReport
from pipeline.api import catalog
from pipeline.extraction import DocumentContent
from pipeline.ingestion import stored_document, to_content
from pipeline.rules import ScrutinyInput
from pipeline.store.jsonstore import JsonStore

APPLICATIONS = "applications"
REPORTS = "reports"
QUEUE_STATUS = "scrutiny_done"
# `info_requested` is still open work - the ball is with the citizen, and the contract keeps
# it distinct from `decided` for that reason - so it counts as pending, not decided.
OPEN_STATUSES = (
    "submitted",
    "documents_uploaded",
    "scrutiny_pending",
    "scrutiny_done",
    "info_requested",
)
EVAL_REPORTS_DIR = Path(__file__).resolve().parents[4] / "eval" / "reports"


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

    def save_report(self, report: ScrutinyReport) -> dict[str, Any]:
        record = self.get(report.application_id)
        if record is None:  # the report names an application that is not in the store
            raise KeyError(report.application_id)
        self.store.put(REPORTS, report.model_dump(mode="json", by_alias=True))
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
        """Applications awaiting an officer, highest risk first (SPEC.md J3)."""
        items = []
        for record in self.all():
            if record["status"] != QUEUE_STATUS:
                continue
            report = self.get_report(str(record["id"]))
            items.append(
                {
                    "applicationId": record["id"],
                    "serviceId": record["serviceId"],
                    "status": record["status"],
                    "riskScore": int(report["riskScore"]) if report else 0,
                    "updatedAt": record["updatedAt"],
                }
            )
        return sorted(items, key=lambda item: (-int(item["riskScore"]), str(item["applicationId"])))

    def metrics(self, flag_threshold: int, generated_at: dt.datetime) -> dict[str, Any]:
        records = self.all()
        scores = [
            int(report["riskScore"])
            for report in (self.get_report(str(record["id"])) for record in records)
            if report
        ]
        latencies = [
            int(report["modelMeta"]["latencyMs"])
            for report in (self.store.list(REPORTS))
            if isinstance(report.get("modelMeta"), dict)
        ]
        evaluated = [
            record for record in records if self.get_report(str(record["id"])) is not None
        ]
        summary: dict[str, Any] = {
            "applicationsTotal": len(records),
            "pending": sum(1 for record in records if record["status"] in OPEN_STATUSES),
            "decided": sum(1 for record in records if record["status"] not in OPEN_STATUSES),
            "avgScrutinySeconds": round(sum(latencies) / len(latencies) / 1000, 3)
            if latencies
            else 0.0,
            "flagRate": round(sum(s >= flag_threshold for s in scores) / len(evaluated), 3)
            if evaluated
            else 0.0,
            "generatedAt": _stamp(generated_at),
        }
        summary.update(latest_eval_metrics())
        return summary


def latest_eval_metrics(directory: Path | None = None) -> dict[str, float]:
    """evalPrecision / evalRecall from the newest `eval/reports/<ts>/report.json`, if A8 ran.

    Silent when absent: those two fields are optional on MetricsSummary, and reading eval
    output must never break the metrics endpoint.
    """
    root = directory or EVAL_REPORTS_DIR
    reports = sorted(root.glob("*/report.json")) if root.is_dir() else []
    if not reports:
        return {}
    try:
        payload = json.loads(reports[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: float(payload[key])
        for key in ("evalPrecision", "evalRecall")
        if isinstance(payload.get(key), (int, float))
    }
