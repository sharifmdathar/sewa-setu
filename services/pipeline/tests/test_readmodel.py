"""The read model judged as the pure function it is: no store, no server, no pipeline run.

The queue ordering, the "what counts as open" rule and the two CR-3 chart series are all decisions
about shapes, so they are tested against shapes. `test_api_journey.py` covers the same code through
HTTP, and `test_api_live_contract.py` covers it over a socket.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pipeline.api import readmodel
from pipeline.rules import load_rule_config

CONFIG = load_rule_config()
GENERATED_AT = dt.datetime(2026, 6, 30, 12, 0, tzinfo=dt.UTC)


def record(application_id: str, status: str, created: str = "2026-06-01T09:00:00+00:00") -> dict:
    return {
        "id": application_id,
        "serviceId": "income_certificate",
        "status": status,
        "createdAt": created,
        "updatedAt": created,
    }


def reports(scores: dict[str, int]) -> Any:
    """A report lookup answering `riskScore` for the named applications, nothing for the rest."""
    return lambda application_id: (
        {"riskScore": scores[application_id]} if application_id in scores else None
    )


def test_the_queue_lists_everything_and_scores_the_unseen_zero() -> None:
    records = [
        record("APP-A", "submitted"),
        record("APP-B", "decided"),
        record("APP-C", "scrutiny_done"),
    ]

    items = readmodel.queue_items(records, reports({"APP-B": 12, "APP-C": 70}))

    assert [item["applicationId"] for item in items] == ["APP-C", "APP-B", "APP-A"]
    assert [item["riskScore"] for item in items] == [70, 12, 0]
    assert {item["status"] for item in items} == {"submitted", "decided", "scrutiny_done"}


def test_equal_risk_orders_by_id_so_two_runs_agree() -> None:
    records = [record("APP-B", "submitted"), record("APP-A", "submitted")]

    assert [item["applicationId"] for item in readmodel.queue_items(records, reports({}))] == [
        "APP-A",
        "APP-B",
    ]


def test_an_info_request_is_open_work_for_both_reader_and_writer() -> None:
    """`pending` and the queue must never disagree, so they share one definition."""
    records = [record("APP-A", "info_requested"), record("APP-B", "decided")]

    summary = readmodel.metrics(records, reports({"APP-B": 90}), CONFIG, GENERATED_AT)

    assert readmodel.open_count(records) == 1
    assert summary["pending"] == 1 and summary["decided"] == 1
    assert summary["applicationsTotal"] == 2


def test_nothing_to_plot_is_absent_rather_than_empty() -> None:
    summary = readmodel.metrics([], reports({}), CONFIG, GENERATED_AT)

    # The read model says "nothing" with None; the route is what drops the key (exclude_none).
    assert summary["applicationsByDay"] is None and summary["riskDistribution"] is None
    assert summary["applicationsTotal"] == 0
    assert summary["avgScrutinySeconds"] == 0.0 and summary["flagRate"] == 0.0


def test_unscored_applications_chart_days_but_not_bands() -> None:
    """The two series answer different questions, so only one of them is empty here."""
    records = [
        record("APP-A", "submitted", "2026-06-02T09:00:00+00:00"),
        record("APP-B", "submitted", "2026-06-01T09:00:00+00:00"),
    ]

    summary = readmodel.metrics(records, reports({}), CONFIG, GENERATED_AT)

    assert summary["applicationsByDay"] == [
        {"date": "2026-06-01", "count": 1},
        {"date": "2026-06-02", "count": 1},
    ]
    assert summary["riskDistribution"] is None  # no band without a score


def test_the_bands_follow_the_spec_numbers_and_keep_the_same_denominator() -> None:
    scores = {"APP-A": 29, "APP-B": 30, "APP-C": 59, "APP-D": 60}
    records = [record(application_id, "scrutiny_done") for application_id in scores]

    summary = readmodel.metrics(records, reports(scores), CONFIG, GENERATED_AT)

    assert summary["riskDistribution"] == [
        {"band": "low", "count": 1},
        {"band": "medium", "count": 2},
        {"band": "high", "count": 1},
    ]
    assert summary["flagRate"] == 0.25  # 1 of the 4 scored, not 1 of the 4 stored


def test_an_older_record_falls_back_to_the_latency_it_did_record() -> None:
    """Records written before the timing fix must still produce a number, not zero."""
    report = {"modelMeta": {"latencyMs": 37}}

    assert readmodel.scrutiny_ms({"id": "APP-0001"}, report) == 37.0
    assert readmodel.scrutiny_ms({"scrutinyMs": 0.42}, report) == 0.42
    assert readmodel.scrutiny_ms({"scrutinyMs": True}, report) == 37.0  # a bool is not a count
    assert readmodel.scrutiny_ms({"scrutinyMs": -1}, report) == 37.0  # nor is a negative
    assert readmodel.scrutiny_ms({}, {"modelMeta": {}}) == 0.0
