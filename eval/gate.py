"""SPEC.md section 7 gate: exit non-zero when the fail-flag numbers fall short.

    python -m eval.gate [--dir eval/reports]

Judges the newest report the runner wrote. It fails on exactly the two thresholds the spec
names - fail-flag precision and recall - and prints the rest (risk-flag numbers, latency) for
context without gating on it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.api.evalfeed import newest_eval_report

from eval.runner import DEFAULT_OUT, PRECISION_TARGET, RECALL_TARGET

MISSING_EXIT = 2
BREACH_EXIT = 1


def _stamp(raw: str) -> str:
    """The report's own instant, as readable as the markdown renders it."""
    return str(raw)[:19].replace("T", " ") + " UTC"


def latest_report(reports_dir: Path) -> Path | None:
    """The newest report - delegated to the same selection `/metrics/summary` uses.

    Two notions of "newest" would let the gate pass on one run while the dashboard quoted
    another, which is precisely the disagreement a demo never notices.
    """
    return newest_eval_report(reports_dir)


def violations(payload: dict[str, Any]) -> list[str]:
    """The spec's two thresholds, as human-readable complaints."""
    found: list[str] = []
    precision = float(payload["evalPrecision"])
    recall = float(payload["evalRecall"])
    if precision < PRECISION_TARGET:
        found.append(
            f"fail-flag precision {precision:.3f} is below the required {PRECISION_TARGET:.2f}"
        )
    if recall < RECALL_TARGET:
        found.append(f"fail-flag recall {recall:.3f} is below the required {RECALL_TARGET:.2f}")
    return found


def describe(payload: dict[str, Any]) -> list[str]:
    flags = payload["failFlags"]
    risk = payload["riskFlags"]
    latency = payload["latency"]
    return [
        "report      : "
        f"{_stamp(payload['generatedAt'])} - "
        f"{payload['dataset']['applications']} applications",
        f"fail flags  : precision {flags['precision']:.3f} "
        f"(>= {PRECISION_TARGET:.2f}), recall {flags['recall']:.3f} "
        f"(>= {RECALL_TARGET:.2f}), f1 {flags['f1']:.3f}",
        f"            : {flags['truePositive']} true, {flags['falsePositive']} false, "
        f"{flags['falseNegative']} missed of {flags['support']} planted",
        f"risk flags  : precision {risk['precision']:.3f}, recall {risk['recall']:.3f}, "
        f"accuracy {risk['accuracy']:.3f} at riskScore >= "
        f"{payload['thresholds']['flagRiskScore']}",
        f"latency     : {latency['meanMillisecondsPerApplication']:.2f}ms/application, target "
        f"< {payload['thresholds']['latencyTargetSeconds']:.0f}s "
        f"({'met' if latency['underTarget'] else 'NOT met'})",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_OUT, help="eval/reports directory")
    arguments = parser.parse_args(argv)

    report = latest_report(arguments.dir)
    if report is None:
        print(f"no eval report under {arguments.dir}; run `python -m eval.runner` first")
        return MISSING_EXIT

    payload = json.loads(report.read_text(encoding="utf-8"))
    for line in describe(payload):
        print(line)

    found = violations(payload)
    for complaint in found:
        print(f"GATE FAIL   : {complaint}")
    print("gate        :", "PASS" if not found else f"FAIL ({len(found)} breach)")
    return 0 if not found else BREACH_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
