"""Application state over the JSON store: status, timeline, documents, reports, queue, metrics.

One record per application, holding its documents inline. The stored record is a superset of
the contract's `Application` (which has no documents field), so `application_view` is the only
shape allowed to leave the process - `tests/contract.py` rejects undeclared keys.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import Any

from pipeline.agent import ScrutinyReport
from pipeline.api import catalog
from pipeline.extraction import DocumentContent
from pipeline.ingestion import stored_document, to_content
from pipeline.logs import get_logger, warning
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
LOGGER = get_logger("api.repository")
# How `eval/runner.py` names its output directory; used only as a fallback clock.
EVAL_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})$")
EVAL_STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
EVAL_KEYS = ("evalPrecision", "evalRecall")


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


def _report_clock(report: Path) -> tuple[dt.datetime, str]:
    """When this run happened: its own `generatedAt`, else its timestamp-shaped dir name.

    Sorting the directory names alone looked right while every run was produced by the runner,
    and went wrong the moment a report was copied or renamed by hand - the dashboard then
    served an older run and looked healthy.
    """
    epoch = dt.datetime.fromtimestamp(0, dt.UTC)
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        stamp = payload.get("generatedAt") if isinstance(payload, dict) else None
        if isinstance(stamp, str):
            return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")), report.parent.name
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    named = EVAL_STAMP.match(report.parent.name)
    if named:
        try:
            moment = dt.datetime.strptime(named.group(1), EVAL_STAMP_FORMAT).replace(tzinfo=dt.UTC)
            return moment, report.parent.name
        except ValueError:
            pass
    return epoch, report.parent.name


def newest_eval_report(reports_dir: Path = EVAL_REPORTS_DIR) -> Path | None:
    """The report `eval/gate.py` should judge and `/metrics/summary` should quote - one answer.

    Shared on purpose: a gate that passes on run X while the dashboard quotes run Y is the
    worst kind of wrong, and it is invisible in a demo.
    """
    if not reports_dir.is_dir():
        return None
    candidates = list(reports_dir.glob("*/report.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda report: (_report_clock(report), str(report)))


def latest_eval_metrics(directory: Path | None = None) -> dict[str, float]:
    """evalPrecision / evalRecall from the newest eval report, if one ran and said both.

    Absent is better than wrong: the two fields are optional on MetricsSummary, so a missing or
    malformed eval output drops them and the dashboard falls back, rather than inventing a
    number. A dropped value is logged, because "no eval numbers" and "eval numbers we could not
    read" look identical from the outside and are not the same problem.
    """
    report = newest_eval_report(Path(directory) if directory is not None else EVAL_REPORTS_DIR)
    if report is None:
        return {}
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warning(LOGGER, "eval report unreadable", path=str(report), reason=str(exc))
        return {}
    if not isinstance(payload, dict):
        warning(LOGGER, "eval report is not an object", path=str(report))
        return {}

    numbers = {
        key: float(payload[key])
        for key in EVAL_KEYS
        if isinstance(payload.get(key), (int, float)) and not isinstance(payload.get(key), bool)
    }
    missing = [key for key in EVAL_KEYS if key not in numbers]
    if missing:
        warning(
            LOGGER,
            "eval report lacks usable numbers",
            path=str(report),
            missing=missing,
            seen=[key for key in EVAL_KEYS if key in payload],
        )
    return numbers
