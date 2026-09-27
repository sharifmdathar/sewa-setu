"""Markdown for the image-leg report. Reads the payload, cannot change what it reports."""

from __future__ import annotations

from typing import Any

FIELD_ORDER = (
    "docType",
    "name",
    "idNumber",
    "issueDate",
    "expiryDate",
    "issuingAuthority",
    "amounts",
)

READER_NOTE = {
    "model": "Every document below was sent to the endpoint as a PNG. A different model is a "
    "different result, not a reproduction of this table.",
    "text": "This is the control: the same documents read through the deterministic template "
    "parser, so it should score 1.00 on the fields the template defines. The model leg's number "
    "is only meaningful beside it.",
}


def _row(label: str, tally: dict[str, Any]) -> str:
    return (
        f"| {label} | {tally['expected']} | {tally['returned']} | {tally['matched']} | "
        f"{tally['recall']:.2f} | {tally['precision']:.2f} |"
    )


def _cells(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "—"


def _per_document_lines(reads: list[dict[str, Any]]) -> list[str]:
    """The aggregate says 0.86; this says which page lost which field, which is what you act on."""
    lines = [
        "",
        "## Per document",
        "",
        "| Document | Type | Stated | Correct | Not transcribed | Read incorrectly | Invented |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in reads:
        lines.append(
            f"| `{row['documentId']}` | {row['docType']} | {row['stated']} | "
            f"{row['correct']} | {_cells(row['missed'])} | {_cells(row['wrong'])} | "
            f"{_cells(row['invented'])} |"
        )
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    reader = payload["reader"]
    fields = payload["fields"]
    latency = payload["latency"]
    source = f"- reader: `{payload.get('extractor', reader)}`"
    source += (
        f", model `{payload.get('model', '?')}`"
        if reader == "model"
        else " (deterministic template parser: the control)"
    )
    lines = [
        f"# Image leg - read-back accuracy ({reader} reader)",
        "",
        f"Generated {str(payload['generatedAt'])[:19].replace('T', ' ')} UTC over "
        f"{payload['documents']} rendered documents from `{payload['dataset']}`.",
        "",
        source,
    ]
    if payload.get("cache"):
        cache = payload["cache"]
        lines.append(
            f"- model calls: {cache['misses']} answered by the endpoint, "
            f"{cache['hits']} served from the disk cache"
        )
    lines += [
        "",
        "These documents are clean text rendered to an image, not a phone photo of paper. This "
        "table measures how much of a document a model reads correctly; it says nothing about "
        "skew, glare or low-DPI robustness, and must not be quoted as if it did.",
        "",
        f"{READER_NOTE.get(reader, '')}",
        "",
        "## Headline",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Whole documents read correctly | {payload['cleanReads']} of {payload['documents']} "
        f"({payload['cleanReadRate']:.0%}) |",
        f"| Field recall (stated values read right) | {fields['recall']:.2f} "
        f"({fields['matched']}/{fields['expected']}) |",
        f"| Field precision (answers given that were right) | {fields['precision']:.2f} "
        f"({fields['matched']}/{fields['returned']}) |",
        f"| Documents that could not be read at all | {payload['unreadable']} |",
    ]
    if latency["calls"]:
        lines.append(
            f"| Time per document | p50 {latency['p50Ms']:.0f} ms, p95 {latency['p95Ms']:.0f} ms, "
            f"max {latency['maxMs']:.0f} ms ({latency['calls']} calls) |"
        )
    elif payload.get("cachedReads"):
        lines.append(
            f"| Time per document | not measured: all "
            f"{payload['cachedReads']} reads were served from the disk cache |"
        )
    lines += [
        "",
        "Precision is reported alongside recall because an invented value is worse than a blank "
        "one: a model that supplies an expiry date to a document that never had one is a "
        "hallucination, and recall alone would never show it.",
        "",
        "## Per field",
        "",
        "| Field | Stated | Answered | Correct | Recall | Precision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in FIELD_ORDER:
        tally = payload["byField"].get(name)
        if tally:
            lines.append(_row(f"`{name}`", tally))
    for name, tally in payload["byField"].items():
        if name not in FIELD_ORDER:
            lines.append(_row(f"`{name}`", tally))
    lines += [
        _row("**all**", fields),
        "",
        "## Per document type",
        "",
        "| Doc type | Stated | Answered | Correct | Recall | Precision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(payload["byDocType"]):
        lines.append(_row(name, payload["byDocType"][name]))
    reads = payload.get("reads") or []
    if reads and len(reads) <= 25:
        # A whole-corpus run would render 917 rows nobody reads; the aggregate covers that.
        lines += _per_document_lines(reads)
    if payload["problems"]:
        lines += ["", "## Documents that could not be read", ""]
        lines += [
            f"- `{row['documentId']}` - {row['fieldsLost']} stated values lost: {row['reason']}"
            for row in payload["problems"]
        ]
    lines += [
        "",
        "## How to reproduce",
        "",
        "```bash",
        "python -m generator --n 200 --anomaly-rate 0.25 --seed 42 \\",
        "    --out data/synthetic/dataset-v1 --png 20",
        "python -m eval.image_leg --reader text   # the control",
        "LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \\",
        "    python -m eval.image_leg             # this report",
        "```",
        "",
    ]
    return "\n".join(lines)
