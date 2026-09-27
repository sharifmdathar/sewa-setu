"""Offline eval pass: run the pipeline over dataset-v1 and score it against ground truth.

    python -m eval.runner [--dataset PATH] [--out eval/reports] [--limit N]

No HTTP and no model endpoint: the same `run_scrutiny` the API calls, on the same synthetic
corpus, timed per application. Writes `eval/reports/<timestamp>/{report.json,report.md}`; the
markdown is the file the submission quotes numbers from (SPEC.md section 8.2).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from pipeline.agent import ScrutinyReport, run_scrutiny
from pipeline.rules import RuleConfig, load_rule_config

from eval.dataset import CHECKS, Case, Dataset, load
from eval.metrics import Tally, tally, total

DEFAULT_OUT = Path(__file__).resolve().parent / "reports"
STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"

# SPEC.md sections 2 and 7.
PRECISION_TARGET = 0.90
RECALL_TARGET = 0.85
LATENCY_TARGET_SECONDS = 60.0


def status_of(report: ScrutinyReport, check: str) -> str:
    found = next((row for row in report.checks if row.check_id == check), None)
    assert found is not None, f"{check} missing from {report.application_id}"
    return found.status


def run_pass(
    dataset: Dataset, config: RuleConfig, limit: int | None = None
) -> list[tuple[Case, ScrutinyReport, float]]:
    """One scrutiny run per application, timed on the wall clock."""
    rows: list[tuple[Case, ScrutinyReport, float]] = []
    cases = dataset.cases[:limit] if limit else dataset.cases
    for case in cases:
        started = time.perf_counter()
        report = run_scrutiny(case.data, case.documents, config=config)
        rows.append((case, report, time.perf_counter() - started))
    return rows


def check_tallies(rows: list[tuple[Case, ScrutinyReport, float]]) -> dict[str, Tally]:
    universe = [case.application_id for case, _, _ in rows]
    tallies: dict[str, Tally] = {}
    for check in CHECKS:
        predicted = [
            case.application_id for case, report, _ in rows if status_of(report, check) == "fail"
        ]
        actual = [case.application_id for case, _, _ in rows if case.expected[check] == "fail"]
        tallies[check] = tally(predicted, actual, universe)
    return tallies


def risk_tally(
    rows: list[tuple[Case, ScrutinyReport, float]], flag_threshold: int
) -> Tally:
    """The application-level flag: is this in the officer's way, and should it be?"""
    universe = [case.application_id for case, _, _ in rows]
    predicted = [
        case.application_id
        for case, report, _ in rows
        if report.risk_score >= flag_threshold
    ]
    actual = [case.application_id for case, _, _ in rows if not case.clean]
    return tally(predicted, actual, universe)


def misses(rows: list[tuple[Case, ScrutinyReport, float]]) -> list[dict[str, Any]]:
    """Applications where a planted failure did not read as a fail, for the writeup."""
    found: list[dict[str, Any]] = []
    for case, report, _ in rows:
        for check in case.expected_fails:
            if status_of(report, check) != "fail":
                found.append(
                    {
                        "applicationId": case.application_id,
                        "check": check,
                        "anomalies": list(case.anomalies),
                        "reported": status_of(report, check),
                    }
                )
    return found


def build_payload(
    dataset: Dataset,
    rows: list[tuple[Case, ScrutinyReport, float]],
    config: RuleConfig,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    tallies = check_tallies(rows)
    micro = total(tallies.values())
    flags = risk_tally(rows, config.flag_threshold)
    seconds = [elapsed for _, _, elapsed in rows]
    reported = [
        report.model_meta.latency_ms for _, report, _ in rows if report.model_meta.latency_ms
    ]
    mean_seconds = sum(seconds) / len(seconds) if seconds else 0.0
    return {
        "generatedAt": generated_at.isoformat(),
        "dataset": {
            "root": str(dataset.root),
            "seed": dataset.seed,
            "asOf": dataset.as_of.isoformat(),
            "requestedAnomalyRate": dataset.requested_anomaly_rate,
            "applications": len(rows),
            "documents": int(dataset.counts.get("documents", 0)),
            "anomalous": sum(1 for case, _, _ in rows if not case.clean),
            "failByCheck": {
                check: int(dataset.counts.get("failByCheck", {}).get(check, 0))
                for check in CHECKS
            },
        },
        "thresholds": {
            "flagRiskScore": config.flag_threshold,
            "precisionTarget": PRECISION_TARGET,
            "recallTarget": RECALL_TARGET,
            "latencyTargetSeconds": LATENCY_TARGET_SECONDS,
        },
        "latency": {
            "meanSecondsPerApplication": round(mean_seconds, 4),
            "meanMillisecondsPerApplication": round(mean_seconds * 1000, 2),
            "maxSecondsPerApplication": round(max(seconds), 4) if seconds else 0.0,
            "meanReportedLatencyMs": round(sum(reported) / len(reported), 2) if reported else 0.0,
            "underTarget": mean_seconds < LATENCY_TARGET_SECONDS,
        },
        "failFlags": micro.as_dict(),
        "checks": {check: tallies[check].as_dict() for check in CHECKS},
        "riskFlags": flags.as_dict(),
        "misses": misses(rows),
        "evalPrecision": round(micro.precision, 4),
        "evalRecall": round(micro.recall, 4),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """The quotable report. Tables only, no prose that could drift from the JSON."""
    fail_flags = payload["failFlags"]
    risk = payload["riskFlags"]
    latency = payload["latency"]
    dataset = payload["dataset"]
    lines = [
        "# Eval report - dataset-v1",
        "",
        f"Generated {payload['generatedAt']} - {dataset['applications']} applications, "
        f"{dataset['documents']} documents, {dataset['anomalous']} with planted anomalies "
        f"(seed {dataset['seed']}, as of {dataset['asOf']}).",
        "",
        "## Headline (SPEC.md section 2 targets)",
        "",
        "| Metric | Baseline (manual) | This run | Target |",
        "| --- | --- | --- | --- |",
        f"| Fail-flag precision | unmeasured | {fail_flags['precision']:.2f} | "
        f">= {payload['thresholds']['precisionTarget']:.2f} |",
        f"| Fail-flag recall | unmeasured | {fail_flags['recall']:.2f} | "
        f">= {payload['thresholds']['recallTarget']:.2f} |",
        f"| Mean scrutiny time / application | 12-18 min | "
        f"{latency['meanMillisecondsPerApplication']:.1f} ms | < 60 s |",
        f"| Every check carries evidence + explanation | inconsistent | "
        f"{'yes' if fail_flags['support'] else 'n/a'} | yes |",
        "",
        "## Per-check fail flags",
        "",
        "| Check | Support | Predicted | TP | FP | FN | Precision | Recall | F1 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for check in CHECKS:
        row = payload["checks"][check]
        lines.append(
            f"| {check} | {row['support']} | {row['predicted']} | {row['truePositive']} | "
            f"{row['falsePositive']} | {row['falseNegative']} | {row['precision']:.2f} | "
            f"{row['recall']:.2f} | {row['f1']:.2f} |"
        )
    lines += [
        f"| **all** | **{fail_flags['support']}** | **{fail_flags['predicted']}** | "
        f"**{fail_flags['truePositive']}** | **{fail_flags['falsePositive']}** | "
        f"**{fail_flags['falseNegative']}** | **{fail_flags['precision']:.2f}** | "
        f"**{fail_flags['recall']:.2f}** | **{fail_flags['f1']:.2f}** |",
        "",
        "## Application-level risk flag",
        "",
        f"At `riskScore >= {payload['thresholds']['flagRiskScore']}`: "
        f"precision {risk['precision']:.2f}, recall {risk['recall']:.2f}, "
        f"accuracy {risk['accuracy']:.2f}, F1 {risk['f1']:.2f} "
        f"({risk['truePositive']} of {risk['support']} anomalous applications flagged, "
        f"{risk['falsePositive']} false alarms).",
        "",
        "## Latency",
        "",
        f"Mean {latency['meanMillisecondsPerApplication']:.2f} ms per application "
        f"(worst {latency['maxSecondsPerApplication'] * 1000:.2f} ms), against a target of "
        f"{payload['thresholds']['latencyTargetSeconds']:.0f} s "
        f"({'met' if latency['underTarget'] else 'NOT met'}).",
        "",
        "Measured offline: template extraction, no model calls and no HTTP. The demo path "
        "adds VLM extraction latency and request overhead on top of this.",
        "",
    ]
    if payload["misses"]:
        lines += ["## Planted failures that did not read as fail", ""]
        lines += [
            f"- {row['applicationId']} {row['check']} reported `{row['reported']}` "
            f"(planted: {', '.join(row['anomalies']) or 'none'})"
            for row in payload["misses"]
        ]
        lines += [""]
    else:
        lines += ["No planted failure was missed on this corpus.", ""]
    return "\n".join(lines)


def write_report(payload: dict[str, Any], markdown: str, out_root: Path, stamp: str) -> Path:
    directory = out_root / stamp
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directory / "report.md").write_text(markdown, encoding="utf-8")
    return directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="score only the first N apps")
    arguments = parser.parse_args(argv)

    started = dt.datetime.now(dt.UTC)
    dataset = load(arguments.dataset) if arguments.dataset else load()
    config = load_rule_config()
    rows = run_pass(dataset, config, arguments.limit)
    payload = build_payload(dataset, rows, config, started)
    stamp = started.strftime(STAMP_FORMAT)
    directory = write_report(payload, render_markdown(payload), arguments.out, stamp)

    print(f"{directory}/report.md")
    print(
        f"fail-flags: precision {payload['evalPrecision']:.2f} "
        f"recall {payload['evalRecall']:.2f} | risk-flag recall "
        f"{payload['riskFlags']['recall']:.2f} | mean "
        f"{payload['latency']['meanMillisecondsPerApplication']:.2f}ms/application"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
