"""The eval harness's own tests: metric math, the gate's exit codes, and one real corpus pass.

Run with `pytest -q` from inside `eval/` (see conftest.py) or from the repository root.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from pipeline.api.repository import latest_eval_metrics
from pipeline.rules import load_rule_config

from eval.dataset import DEFAULT_DATASET, load
from eval.gate import BREACH_EXIT, MISSING_EXIT, latest_report, violations
from eval.gate import main as gate_main
from eval.metrics import Tally, tally, total
from eval.runner import (
    STAMP_FORMAT,
    build_payload,
    render_markdown,
    run_pass,
    write_report,
)

CONFIG = load_rule_config()
STAMP = "2026-09-26T09-30-00"


def report_payload(precision: float = 0.95, recall: float = 0.9) -> dict[str, object]:
    return {
        "generatedAt": "2026-09-26T09:30:00+00:00",
        "dataset": {"applications": 200, "seed": 42, "asOf": "2026-06-30"},
        "thresholds": {"flagRiskScore": 60, "latencyTargetSeconds": 60},
        "latency": {
            "meanSecondsPerApplication": 0.0002,
            "meanMillisecondsPerApplication": 0.2,
            "maxSecondsPerApplication": 0.001,
            "underTarget": True,
        },
        "failFlags": {
            "truePositive": 70,
            "falsePositive": 4,
            "falseNegative": 8,
            "support": 78,
            "predicted": 74,
            "precision": precision,
            "recall": recall,
            "f1": 0.92,
        },
        "riskFlags": {
            "precision": 1.0,
            "recall": 0.54,
            "accuracy": 0.88,
            "f1": 0.7,
            "support": 50,
            "truePositive": 27,
            "falsePositive": 0,
        },
        "checks": {},
        "evalPrecision": precision,
        "evalRecall": recall,
    }


def test_tally_counts_all_four_quadrants() -> None:
    row = tally(
        predicted=["a", "b", "c"], actual=["a", "b", "d"], universe=["a", "b", "c", "d", "e"]
    )

    assert (row.true_positive, row.false_positive, row.false_negative) == (2, 1, 1)
    assert row.true_negative == 1  # "e" was neither planted nor flagged
    assert row.support == 3 and row.predicted == 3
    assert round(row.precision, 2) == 0.67 and round(row.recall, 2) == 0.67


def test_a_check_with_no_positives_scores_one() -> None:
    """An empty class cannot be wrong: 0/0 is reported as 1.0, not as a crash or a 0.0."""
    row = tally(predicted=[], actual=[], universe=["a", "b"])

    assert row.support == 0 and row.precision == 1.0 and row.recall == 1.0
    assert row.accuracy == 1.0


def test_flagging_everything_trades_precision_for_recall() -> None:
    everyone = tally(predicted=["a", "b", "c", "d"], actual=["a"], universe=["a", "b", "c", "d"])
    nobody = tally(predicted=[], actual=["a"], universe=["a", "b", "c", "d"])

    assert everyone.recall == 1.0 and everyone.precision == 0.25
    assert nobody.recall == 0.0 and nobody.precision == 1.0


def test_total_pools_the_counts_not_the_ratios() -> None:
    pooled = total([Tally(9, 1, 0, 0), Tally(0, 0, 10, 0)])

    assert pooled.true_positive == 9 and pooled.false_positive == 1
    assert pooled.precision == 0.9 and round(pooled.recall, 3) == 0.474
    assert pooled.support == 19


def test_the_gate_reads_only_the_two_spec_thresholds() -> None:
    assert violations(report_payload(precision=0.95, recall=0.90)) == []
    assert "precision" in violations(report_payload(precision=0.89, recall=1.0))[0]
    assert "recall" in violations(report_payload(precision=1.0, recall=0.849))[0]
    assert len(violations(report_payload(precision=0.5, recall=0.5))) == 2


def write_run(directory: Path, payload: dict[str, object], stamp: str = STAMP) -> Path:
    target = directory / stamp
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_the_gate_exits_on_the_newest_report_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_run(tmp_path, report_payload(precision=0.10, recall=0.10), stamp="2026-09-01T00-00-00")
    write_run(tmp_path, report_payload(precision=0.99, recall=0.99), stamp="2026-09-26T00-00-00")

    assert gate_main(["--dir", str(tmp_path)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert latest_report(tmp_path) == tmp_path / "2026-09-26T00-00-00" / "report.json"


def test_the_gate_fails_and_says_which_number_breached(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_run(tmp_path, report_payload(precision=0.95, recall=0.40))

    assert gate_main(["--dir", str(tmp_path)]) == BREACH_EXIT
    printed = capsys.readouterr().out
    assert "recall 0.400" in printed and "FAIL" in printed


def test_a_missing_report_is_not_a_pass(tmp_path: Path) -> None:
    assert gate_main(["--dir", str(tmp_path)]) == MISSING_EXIT
    assert latest_report(tmp_path) is None


def test_run_directory_names_sort_chronologically() -> None:
    stamps = ["2026-01-02T03-04-05", "2026-09-26T09-30-00", "2025-12-31T23-59-59"]

    assert sorted(stamps) == ["2025-12-31T23-59-59", "2026-01-02T03-04-05", "2026-09-26T09-30-00"]
    assert dt.datetime.strptime(STAMP, STAMP_FORMAT).year == 2026


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    """One real offline pass over dataset-v1, shared by the assertions below."""
    if not (DEFAULT_DATASET / "ground_truth.json").is_file():
        pytest.skip(f"{DEFAULT_DATASET} not generated; run python -m generator first")
    dataset = load()
    return build_payload(dataset, run_pass(dataset, CONFIG), CONFIG, dt.datetime.now(dt.UTC))


def test_the_dataset_loads_as_the_pipeline_expects_it() -> None:
    dataset = load()

    assert dataset.size == 200
    assert dataset.as_of == dt.date(2026, 6, 30)  # noqa: ERA001
    assert len(dataset.anomalous) == 50
    assert all(case.data.required_doc_types for case in dataset.cases)
    assert any(case.data.duplicate_sha256 for case in dataset.cases)


def test_the_full_corpus_pass_clears_the_gate(payload: dict[str, object]) -> None:  # <=100
    assert violations(payload) == []
    assert payload["evalPrecision"] == 1.0 and payload["evalRecall"] == 1.0
    assert payload["misses"] == []
    assert payload["riskFlags"]["falsePositive"] == 0  # nothing clean is sent to an officer
    assert payload["dataset"]["applications"] == 200
    assert payload["latency"]["underTarget"]


def test_the_markdown_is_quotable_and_matches_the_json(payload: dict[str, object]) -> None:
    markdown = render_markdown(payload)

    assert "| Fail-flag precision | unmeasured | 1.00 | >= 0.90 |" in markdown
    assert "| C5 | 21 | 21 | 21 | 0 | 0 | 1.00 | 1.00 | 1.00 |" in markdown
    assert "Measured offline" in markdown  # the latency caveat must travel with the number
    for check in ("C1", "C2", "C3", "C4", "C5"):
        assert f"| {check} |" in markdown


def test_the_api_reads_what_the_runner_writes(
    payload: dict[str, object], tmp_path: Path
) -> None:
    """A7's /metrics/summary and A8's report.json must agree, or the dashboard lies."""
    directory = write_report(payload, render_markdown(payload), tmp_path, STAMP)

    assert (directory / "report.json").is_file() and (directory / "report.md").is_file()
    assert latest_eval_metrics(tmp_path) == {
        "evalPrecision": payload["evalPrecision"],
        "evalRecall": payload["evalRecall"],
    }


def test_a_limited_run_is_still_scored(tmp_path: Path) -> None:
    dataset = load()
    rows = run_pass(dataset, CONFIG, limit=25)

    small = build_payload(dataset, rows, CONFIG, dt.datetime.now(dt.UTC))

    assert len(rows) == 25
    assert small["dataset"]["applications"] == 25
    assert small["failFlags"]["support"] <= 74
