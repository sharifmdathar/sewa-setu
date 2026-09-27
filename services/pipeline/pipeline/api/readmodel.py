"""The contract's two read paths over stored records: the officer queue and the dashboard.

Both are pure functions of (the application records, a report lookup), so they can be judged
without a store, a server or a pipeline run - `Repository` supplies both arguments and nothing
here writes anything anywhere. Kept apart from `repository.py` because that file is about state
transitions; this one is about reporting on them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pipeline.api.evalfeed import latest_eval_metrics
from pipeline.rules import RuleConfig

ReportLookup = Callable[[str], "dict[str, Any] | None"]

# `info_requested` is still open work - the ball is with the citizen, and the contract keeps
# it distinct from `decided` for that reason - so it counts as pending, not decided.
OPEN_STATUSES = (
    "submitted",
    "documents_uploaded",
    "scrutiny_pending",
    "scrutiny_done",
    "info_requested",
)


def open_count(records: list[dict[str, Any]]) -> int:
    """Applications still awaiting someone - the queue's and the dashboard's one definition."""
    return sum(1 for record in records if record["status"] in OPEN_STATUSES)


def queue_items(records: list[dict[str, Any]], report_of: ReportLookup) -> list[dict[str, Any]]:
    """Every application with its status and risk score, highest risk first (CR-2).

    Decided and not-yet-scrutinized applications are included rather than hidden: the officer
    page filters by status, and a queue that drops closed work can never agree with
    `metrics.pending`. An application with no report yet scores 0, because QueueItem requires
    the field.
    """
    items = []
    for record in records:
        report = report_of(str(record["id"]))
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


def metrics(
    records: list[dict[str, Any]],
    report_of: ReportLookup,
    config: RuleConfig,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    """`MetricsSummary` as the contract types it, including the two chart series (CR-3)."""
    reports = [(record, report_of(str(record["id"]))) for record in records]
    scored = [(record, report) for record, report in reports if report is not None]
    scores = [int(report["riskScore"]) for _, report in scored]
    latencies = [scrutiny_ms(record, report) for record, report in scored]
    summary: dict[str, Any] = {
        "applicationsTotal": len(records),
        "pending": open_count(records),
        "decided": len(records) - open_count(records),
        "avgScrutinySeconds": round(sum(latencies) / len(latencies) / 1000, 5)
        if latencies
        else 0.0,
        "flagRate": round(sum(s >= config.flag_threshold for s in scores) / len(scored), 3)
        if scored
        else 0.0,
        # Absent rather than empty: the UI feature-detects, and `[]` would draw a blank
        # chart where "no data yet" is the truth (CR-3, both fields optional).
        "applicationsByDay": _by_day(records) or None,
        "riskDistribution": _risk_bands(scores, config) if scores else None,
        "generatedAt": generated_at.isoformat(),
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


def _by_day(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Applications per calendar day of `createdAt`, oldest first (CR-3 series)."""
    counts: dict[str, int] = {}
    for record in records:
        counts[str(record["createdAt"])[:10]] = counts.get(str(record["createdAt"])[:10], 0) + 1
    return [{"date": day, "count": counts[day]} for day in sorted(counts)]


def _risk_bands(scores: list[int], config: RuleConfig) -> list[dict[str, Any]]:
    """low < cleanCeiling, medium < flagThreshold, high >= it (SPEC.md section 7).

    Only scrutinized applications appear: an unscored one has no band, and `flagRate` uses
    the same denominator, so the two figures can be read together. Whenever any score exists
    all three bands are emitted, so the chart axis is stable at zero as well as at three.
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


def _is_count(value: object) -> bool:
    """A real, non-negative number - and a bool is not one, however much Python argues."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
