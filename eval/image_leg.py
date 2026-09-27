"""Read-back accuracy over the rendered image leg of the corpus.

    python -m eval.image_leg                     # the model leg, over docs_img/*.png
    python -m eval.image_leg --reader text       # the control: same documents, template-parsed
    python -m eval.image_leg --limit 5 --out /tmp/image-leg

`--png N` on the generator records, for every rendered document, the exact field values a correct
read must return (`image_manifest.json`). Nothing compared them, so "the vision path measures
read-back accuracy" was a claim about plumbing rather than a measurement. The comparison itself is
`eval.image_score`; this module runs it and writes the report.

Two readers, deliberately: `model` sends the PNG through the VLM extractor, which is the number
worth quoting, and `text` template-parses the same document's text layer as a control that should
score 1.00. Sitting beside the control, the model's number says how much of the loss is reading
and how much is reasoning.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from pipeline.extraction import DocumentExtractor, TemplateExtractor

from eval.dataset import DEFAULT_DATASET
from eval.image_leg_md import render_markdown
from eval.image_score import (
    MANIFEST_FILE,
    Entry,
    LegResult,
    load_entries,
    percentile,
    score_documents,
)

STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
DEFAULT_OUT = Path(__file__).resolve().parent / "reports" / "image-leg"


def load_manifest(root: Path | str = DEFAULT_DATASET) -> list[Entry]:
    """The corpus's own answer key, or the command that would have produced it."""
    try:
        return load_entries(root)
    except FileNotFoundError:
        missing = Path(root) / MANIFEST_FILE
        print(f"{missing} not found. Render the image leg first:", file=sys.stderr)
        print(
            f"  python -m generator --n 200 --anomaly-rate 0.25 --seed 42 "
            f"--out {root} --png 20",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


def build_extractor(reader: str) -> DocumentExtractor:
    """`text` is the deterministic control; `model` needs an endpoint to mean anything."""
    if reader == "text":
        return TemplateExtractor()
    from pipeline.agent import default_extractor

    extractor = default_extractor()
    if isinstance(extractor, TemplateExtractor):
        print(
            "LLM_API_KEY is unset, so the model leg would template-parse pixels and score every "
            "document unreadable. Set an endpoint, or run --reader text for the control.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return extractor


def as_dict(
    result: LegResult, reader: str, root: Path, generated_at: dt.datetime
) -> dict[str, Any]:
    latencies = result.latencies_ms
    return {
        "generatedAt": generated_at.isoformat(),
        "reader": reader,
        "dataset": str(root),
        "documents": result.documents,
        "unreadable": result.unreadable,
        "cachedReads": result.cached_reads,
        "cleanReads": result.clean_reads,
        "cleanReadRate": round(result.clean_reads / (result.documents or 1), 4),
        "fields": result.overall.as_dict(),
        "byField": {name: tally.as_dict() for name, tally in result.by_field.items()},
        "byDocType": {name: tally.as_dict() for name, tally in result.by_type.items()},
        "reads": result.reads,
        "latency": {
            "calls": len(latencies),
            "meanMs": round(statistics.fmean(latencies), 2) if latencies else 0.0,
            "p50Ms": percentile(latencies, 0.50),
            "p95Ms": percentile(latencies, 0.95),
            "maxMs": float(max(latencies)) if latencies else 0.0,
        },
        "problems": result.problems,
    }


def write_output(payload: dict[str, Any], markdown: str, out_root: Path, stamp: str) -> Path:
    directory = out_root / stamp
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "image_leg.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directory / "image_leg.md").write_text(markdown, encoding="utf-8")
    return directory


def report_console(payload: dict[str, Any]) -> None:
    """The same headline numbers as the file, so a run reports itself without a pager."""
    fields = payload["fields"]
    latency = payload["latency"]
    print(
        f"fields    : recall {fields['recall']:.2f} precision {fields['precision']:.2f} "
        f"({fields['matched']}/{fields['expected']} stated values read right)"
    )
    print(
        f"documents : {payload['cleanReads']} of {payload['documents']} read completely "
        f"({payload['cleanReadRate']:.0%}), {payload['unreadable']} unreadable"
    )
    if latency["calls"]:
        print(
            f"latency   : p50 {latency['p50Ms']:.0f} ms  p95 {latency['p95Ms']:.0f} ms  "
            f"max {latency['maxMs']:.0f} ms"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--limit", type=int, default=None, help="score only the first N documents"
    )
    parser.add_argument(
        "--reader",
        choices=("model", "text"),
        default="model",
        help="pixels through the model, or the text-layer control",
    )
    arguments = parser.parse_args(argv)

    entries = load_manifest(arguments.dataset)
    if arguments.limit:
        entries = entries[: arguments.limit]
    extractor = build_extractor(arguments.reader)
    print(f"scoring {len(entries)} documents with the {arguments.reader} reader")

    started = dt.datetime.now(dt.UTC)
    result = score_documents(
        entries, extractor, arguments.dataset, arguments.reader, LegResult()
    )
    payload = as_dict(result, arguments.reader, arguments.dataset, started)
    payload["extractor"] = extractor.name
    meta = extractor.last_meta
    payload["model"] = meta.model if meta is not None else "code"
    if arguments.reader == "model":
        from pipeline.llmcache import combined_stats

        payload["cache"] = combined_stats()

    directory = write_output(
        payload, render_markdown(payload), arguments.out, started.strftime(STAMP_FORMAT)
    )
    print(f"{directory / 'image_leg.md'}")
    report_console(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
