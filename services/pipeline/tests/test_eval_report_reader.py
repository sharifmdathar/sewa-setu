"""I3: the metrics endpoint and the eval gate must judge the *same* run, or say nothing.

`/metrics/summary` reads real numbers out of `eval/reports/<ts>/report.json` - nothing is
hardcoded - so what needs pinning is which report counts as newest, what happens when its
numbers are unusable, and that `eval/gate.py` cannot disagree with the dashboard.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pipeline.api.repository import latest_eval_metrics, newest_eval_report

NEWER = {"evalPrecision": 0.94, "evalRecall": 0.88, "generatedAt": "2026-09-26T09:30:00+00:00"}
OLDER = {"evalPrecision": 0.5, "evalRecall": 0.5, "generatedAt": "2026-09-01T00:00:00+00:00"}


def write_report(root: Path, directory: str, payload: dict[str, Any]) -> Path:
    target = root / directory
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(json.dumps(payload), encoding="utf-8")
    return target


@pytest.fixture()
def capture_warnings() -> Any:
    """Collect WARNING records from the pipeline logger without touching stdout."""
    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                records.append(record)

    handler = Collector()
    logger = logging.getLogger("pipeline")
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


def test_the_newest_run_wins_even_when_its_directory_name_sorts_first(
    tmp_path: Path,
) -> None:
    """A hand-copied directory must not silently resurrect an older eval."""
    write_report(tmp_path, "2026-09-01T00-00-00", OLDER)
    write_report(tmp_path, "zz-hand-copied", NEWER)

    assert latest_eval_metrics(tmp_path) == {"evalPrecision": 0.94, "evalRecall": 0.88}
    chosen = newest_eval_report(tmp_path)
    assert chosen is not None and chosen.parent.name == "zz-hand-copied"


def test_the_directory_timestamp_is_the_fallback_clock(tmp_path: Path) -> None:
    write_report(tmp_path, "2026-09-26T09-30-00", {"evalPrecision": 0.9, "evalRecall": 0.9})
    write_report(tmp_path, "2026-09-27T08-00-00", {"evalPrecision": 0.7, "evalRecall": 0.7})

    assert latest_eval_metrics(tmp_path) == {"evalPrecision": 0.7, "evalRecall": 0.7}


def test_no_reports_at_all_yields_no_keys_rather_than_zero(tmp_path: Path) -> None:
    assert latest_eval_metrics(tmp_path) == {}
    assert newest_eval_report(tmp_path) is None
    assert latest_eval_metrics(tmp_path / "does-not-exist") == {}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"evalPrecision": 0.9, "evalRecall": 0.9}, {"evalPrecision": 0.9, "evalRecall": 0.9}),
        ({"evalPrecision": 1, "evalRecall": 0}, {"evalPrecision": 1.0, "evalRecall": 0.0}),
        ({"evalPrecision": 0.9}, {"evalPrecision": 0.9}),  # partial beats invented
        ({"evalPrecision": "0.9", "evalRecall": "0.9"}, {}),
        ({"evalPrecision": True, "evalRecall": True}, {}),
        ({}, {}),
    ],
)
def test_only_real_numbers_are_forwarded(
    tmp_path: Path, payload: dict[str, Any], expected: dict[str, float]
) -> None:
    """A string or a boolean is not a metric; the contract types these as `number`.

    Omitting is safer than coercing: the dashboard then falls back to its own count instead of
    rendering whatever a malformed report happened to contain.
    """
    write_report(tmp_path, "2026-09-26T09-30-00", payload)

    assert latest_eval_metrics(tmp_path) == expected


@pytest.mark.parametrize(
    ("content", "expected_warning"),
    [
        ('{"evalPrecision": "0.9"}', "lacks usable numbers"),
        ("{ not json", "eval report unreadable"),
        ("[1, 2, 3]", "is not an object"),
    ],
)
def test_a_useless_report_says_so_rather_than_failing_quietly(
    tmp_path: Path, capture_warnings: list[logging.LogRecord], content: str, expected_warning: str
) -> None:
    """Each broken shape on its own, because the newest report is the only one read."""
    target = tmp_path / "2026-09-26T09-30-00"
    target.mkdir(parents=True)
    (target / "report.json").write_text(content, encoding="utf-8")

    assert latest_eval_metrics(tmp_path) == {}
    assert expected_warning in " | ".join(record.getMessage() for record in capture_warnings)


def test_the_endpoint_quotes_the_newest_report_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the API, with the numbers picked to differ from the real ones."""
    from fastapi.testclient import TestClient

    from pipeline.api import repository as repository_module
    from pipeline.api.main import create_app

    root = tmp_path / "reports"
    write_report(root, "2026-09-01T00-00-00", OLDER)
    newer = {**NEWER, "generatedAt": dt.datetime.now(dt.UTC).isoformat()}
    write_report(root, "2026-09-26T09-30-00", newer)
    monkeypatch.setattr(repository_module, "EVAL_REPORTS_DIR", root)

    client = TestClient(create_app(tmp_path / "var"))
    payload = client.get("/metrics/summary").json()

    assert payload["evalPrecision"] == 0.94
    assert payload["evalRecall"] == 0.88
