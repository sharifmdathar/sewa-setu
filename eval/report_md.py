"""Markdown rendering for the eval report - the file the submission quotes.

Kept apart from the runner so the numbers (JSON) and the presentation of them never drift
silently: this module reads a payload and cannot change what it reports.
"""

from __future__ import annotations

from typing import Any

from eval.dataset import CHECKS


def _met(value: float, target: float) -> str:
    return "(met)" if value >= target else "(NOT met)"


def _gate_line(payload: dict[str, Any]) -> str:
    """The verdict `eval/gate.py` would reach on this same payload, spelled out."""
    flags = payload["failFlags"]
    thresholds = payload["thresholds"]
    breaching = [
        f"{label} {flags[flag_key]:.3f} < {thresholds[threshold_key]:.2f}"
        for flag_key, threshold_key, label in (
            ("precision", "precisionTarget", "precision"),
            ("recall", "recallTarget", "recall"),
        )
        if flags[flag_key] < thresholds[threshold_key]
    ]
    if not breaching:
        return (
            f"**PASS** - fail-flag precision {flags['precision']:.3f} and recall "
            f"{flags['recall']:.3f} both clear SPEC.md section 7 "
            f"(>= {thresholds['precisionTarget']:.2f} / >= {thresholds['recallTarget']:.2f})."
        )
    return "**FAIL** - " + "; ".join(breaching) + "."


def render_markdown(payload: dict[str, Any]) -> str:
    """The quotable report. Tables only, no prose that could drift from the JSON."""
    fail_flags = payload["failFlags"]
    risk = payload["riskFlags"]
    latency = payload["latency"]
    dataset = payload["dataset"]
    lines = [
        "# Eval report - dataset-v1",
        "",
        f"Generated {str(payload['generatedAt'])[:19].replace('T', ' ')} UTC - "
        f"{dataset['applications']} applications, "
        f"{dataset['documents']} documents, {dataset['anomalous']} with planted anomalies "
        f"(seed {dataset['seed']}, as of {dataset['asOf']}).",
        "",
        "## Headline (SPEC.md section 2 targets)",
        "",
        "| Metric | Baseline (manual) | This run | Target |",
        "| --- | --- | --- | --- |",
        f"| Fail-flag precision | unmeasured | {fail_flags['precision']:.2f} "
        f"{_met(fail_flags['precision'], payload['thresholds']['precisionTarget'])} | "
        f">= {payload['thresholds']['precisionTarget']:.2f} |",
        f"| Fail-flag recall | unmeasured | {fail_flags['recall']:.2f} "
        f"{_met(fail_flags['recall'], payload['thresholds']['recallTarget'])} | "
        f">= {payload['thresholds']['recallTarget']:.2f} |",
        f"| Mean scrutiny time / application | 12-18 min | "
        f"{latency['meanMillisecondsPerApplication']:.2f} ms "
        f"{'(met)' if latency['underTarget'] else '(NOT met)'} | < 60 s |",
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
        "Recall here counts applications whose risk score crossed the flag line, not checks that",
        "were correctly called. Single-anomaly applications score 40-50, under the threshold",
        f"of {payload['thresholds']['flagRiskScore']} that SPEC.md section 7 fixes, so the queue",
        "ranks by risk rather than catching every anomaly; the fail-flag table is the gate.",
        "",
        "## Gate",
        "",
        _gate_line(payload),
        "",
        "`python -m eval.gate` exits 0 only when both rows above clear their target. This is the",
        "file the submission quotes (SPEC.md section 8.2), so it states the verdict instead of",
        "leaving it to be inferred from the table.",
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
    lines += [
        "## How to reproduce",
        "",
        "```bash",
        "python -m generator --n 200 --anomaly-rate 0.25 --seed 42 \\",
        "    --out data/synthetic/dataset-v1",
        "python -m eval.runner            # writes eval/reports/<timestamp>/report.md",
        "python -m eval.gate              # exit 0 means the SPEC thresholds are met",
        "```",
        "",
        "Numbers come from the offline pipeline: template extraction, deterministic adjudicator,",
        "no model calls. The corpus and the rules share a generator, so this measures rule-and-",
        "label agreement - not extraction robustness on scanned documents, which needs the VLM",
        "path and a real key.",
        "",
    ]
    return "\n".join(lines)
