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
from pipeline.api import catalog
from pipeline.api.evalfeed import latest_eval_metrics
from pipeline.extraction import DocumentContent
from pipeline.ingestion import stored_document, to_content
from pipeline.rules import RuleConfig, ScrutinyInput
from pipeline.store.jsonstore import JsonStore

APPLICATIONS = "applications"
REPORTS = "reports"
# `info_requested` is still open work - the ball is with the citizen, and the contract keeps
# it distinct from `decided` for that reason - so it counts as pending, not decided.
OPEN_STATUSES = (
    "submitted",
    "documents_uploaded",
    "scrutiny_pending",
    "scrutiny_done",
    "info_requested",
)


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
        """Every application with its status and risk score, highest risk first (CR-2).

        Decided and not-yet-scrutinized applications are included rather than hidden: the
        officer page filters by status, and a queue that drops closed work can never agree
        with `metrics.pending`. `OPEN_STATUSES` is the single definition of "still open" for
        both. An application with no report yet scores 0, because QueueItem requires the field.
        """
        items = []
        for record in self.all():
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

    @staticmethod
    def _by_day(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Applications per calendar day of `createdAt`, oldest first (CR-3 series)."""
        counts: dict[str, int] = {}
        for record in records:
            counts[str(record["createdAt"])[:10]] = counts.get(str(record["createdAt"])[:10], 0) + 1
        return [{"date": day, "count": counts[day]} for day in sorted(counts)]

    @staticmethod
    def _risk_bands(scores: list[int], config: RuleConfig) -> list[dict[str, Any]]:
        """low < cleanCeiling, medium < flagThreshold, high >= it (SPEC.md section 7).

        Only scrutinized applications appear: an unscored one has no band, and `flagRate` uses
        the same denominator, so the two figures can be read together. All three bands are always
        emitted (a chart wants a stable axis), unlike `_by_day`, which reports only observed days.
        """
        bands = {"low": 0, "medium": 0, "high": 0}
        for score in scores:
            if score >= config.flag_threshold:
                bands["high"] += 1
            elif score >= config.clean_ceiling:
                bands["medium"] += 1
            else:
                bands["low"] += 1
        return [{"band": name, "count": count} for name, count in bands.items()]

    @staticmethod
    def open_count(records: list[dict[str, Any]]) -> int:
        """Applications still awaiting someone - the queue's and the dashboard's one definition."""
        return sum(1 for record in records if record["status"] in OPEN_STATUSES)

    def metrics(self, config: RuleConfig, generated_at: dt.datetime) -> dict[str, Any]:
        records = self.all()
        scores = [
            int(report["riskScore"])
            for report in (self.get_report(str(record["id"])) for record in records)
            if report
        ]
        reports = [
            (record, self.get_report(str(record["id"])))
            for record in records
        ]
        evaluated = [record for record, report in reports if report is not None]
        latencies = [
            scrutiny_ms(record, report) for record, report in reports if report is not None
        ]
        summary: dict[str, Any] = {
            "applicationsTotal": len(records),
            "pending": self.open_count(records),
            "decided": len(records) - self.open_count(records),
            "avgScrutinySeconds": round(sum(latencies) / len(latencies) / 1000, 5)
            if latencies
            else 0.0,
            "flagRate": round(sum(s >= config.flag_threshold for s in scores) / len(evaluated), 3)
            if evaluated
            else 0.0,
            "applicationsByDay": self._by_day(records),
            "riskDistribution": self._risk_bands(scores, config),
            "generatedAt": _stamp(generated_at),
        }
        summary.update(latest_eval_metrics())
        return summary


def scrutiny_ms(record: dict[str, Any], report: dict[str, Any]) -> float:
    """Milliseconds of the last run as measured at the route, not inside the pipeline.

    Kept as a float because the work is sub-millisecond: the contract types
    `modelMeta.latencyMs` as an *integer*, so every fast scrutiny rounds to 0 and the
    dashboard reports "0.0 s" for work that plainly happened. Milliseconds stay in the
    store and never reach the wire.
    """
    measured = record.get("scrutinyMs")
    if _is_count(measured):
        return float(measured)
    meta = report.get("modelMeta")
    latency = meta.get("latencyMs") if isinstance(meta, dict) else None
    return float(latency) if _is_count(latency) else 0.0


def _is_count(value: object) -> bool:
    """A real, non-negative number - and a bool is not one, however much Python argues."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


