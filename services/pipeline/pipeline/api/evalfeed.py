"""Reading the eval harness's output, for the metrics endpoint and the gate.

Separate from `repository.py` because it is a different kind of truth: application state this
service writes, versus a report another Track A program produced. `/metrics/summary` must quote
the very run `eval.gate` judged, so the notion of 'newest' lives here once and both read it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from pipeline.logs import get_logger, warning

LOGGER = get_logger("api.evalfeed")
EVAL_REPORTS_DIR = Path(__file__).resolve().parents[4] / "eval" / "reports"
# How `eval/runner.py` names its output directory; used only as a fallback clock.
EVAL_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})$")
EVAL_STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
EVAL_KEYS = ("evalPrecision", "evalRecall")


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


def judged_nothing(payload: dict) -> bool:
    """True when a run had nothing at stake: no planted check failures, and none predicted.

    `eval.runner --limit 2` over a slice with no anomaly reports precision 1.00 and recall 1.00
    built on zero evidence, and both numbers are otherwise indistinguishable from the real thing.
    That is enough to pass the SPEC §7 gate and to headline the dashboard, so the two readers ask
    this question together - `eval/gate.py` treats it as a breach, `/metrics/summary` as no news.

    A report that does not say gets no opinion here: the fields still have to be numbers, and
    "the report does not say what it judged" is the gate's complaint, not a reason to drop a
    dashboard field that a hand-written report never had.
    """
    flags = payload.get("failFlags")
    if not isinstance(flags, dict):
        return False
    planted, predicted = flags.get("support"), flags.get("predicted")
    if not (_is_number(planted) and _is_number(predicted)):
        return False
    return int(planted) == 0 and int(predicted) == 0


def _is_number(value: object) -> bool:
    """A real number, and a bool is not one - `True` would read as a count of one."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
    if judged_nothing(payload):
        warning(
            LOGGER,
            "eval report judged nothing",
            path=str(report),
            applications=payload.get("dataset", {}).get("applications"),
            planted=payload.get("failFlags", {}).get("support"),
        )
        return {}
    if missing:
        warning(
            LOGGER,
            "eval report lacks usable numbers",
            path=str(report),
            missing=missing,
            seen=[key for key in EVAL_KEYS if key in payload],
        )
    return numbers
