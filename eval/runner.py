"""Offline eval pass: run the pipeline over dataset-v1 and score it against ground truth.

    python -m eval.runner [--dataset PATH] [--out eval/reports] [--limit N]

By default this is fully offline: template extraction, deterministic adjudication, no HTTP. Set
`LLM_API_KEY` (and `LLM_BASE_URL`/`LLM_MODEL`) and the same command runs the *live model leg*
instead, because `run_scrutiny` picks its extractor and adjudicator from the environment - the
report records which one it got, so the two legs can never be confused for each other. Writes
`eval/reports/<timestamp>/{report.json,report.md}`; the markdown is the file the submission
quotes numbers from (SPEC.md section 8.2).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from pipeline.agent import ScrutinyReport, run_scrutiny
from pipeline.llmcache import combined_stats
from pipeline.rules import RuleConfig, load_rule_config

from eval.dataset import CHECKS, Case, Dataset, load
from eval.metrics import Tally, tally, total
from eval.report_md import render_markdown

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


def pipeline_of(rows: list[tuple[Case, ScrutinyReport, float]]) -> dict[str, Any]:
    """Which extractor and adjudicator this pass actually used, straight off the reports.

    A live run and an offline one produce the same table shape, so the provenance has to travel
    with the numbers or the two legs get quoted against each other by mistake.
    """
    if not rows:
        return {"extractor": "n/a", "adjudicator": "n/a", "models": {}, "live": False}
    meta = rows[0][1].model_meta
    live = meta.extractor != "template" or meta.adjudicator != "deterministic"
    provenance: dict[str, Any] = {
        "extractor": meta.extractor,
        "adjudicator": meta.adjudicator,
        "models": {
            "rules": meta.versions.get("rules", ""),
            "extractor": meta.versions.get("extractor", ""),
            "adjudicator": meta.versions.get("adjudicator", ""),
        },
        "live": live,
    }
    if live:
        from pipeline.config import get_llm_settings

        provenance["cache"] = {
            **combined_stats(),
            "enabled": get_llm_settings().cache_enabled,
        }
    return provenance


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
        "pipeline": pipeline_of(rows),
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
    used = payload["pipeline"]
    model = used["models"].get("extractor") or used["extractor"]
    print(f"path      : {used['extractor']} + {used['adjudicator']} ({model})")
    if used.get("cache"):
        cache = used["cache"]
        if cache.get("enabled"):
            print(f"llm calls : {cache['misses']} new, {cache['hits']} served from cache")
        else:
            print("llm calls : cache off (LLM_CACHE=0), so every read reached the endpoint")
    print(
        f"fail-flags: precision {payload['evalPrecision']:.2f} "
        f"recall {payload['evalRecall']:.2f} | risk-flag recall "
        f"{payload['riskFlags']['recall']:.2f} | mean "
        f"{payload['latency']['meanMillisecondsPerApplication']:.2f}ms/application"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())