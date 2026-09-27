"""Preflight one or more OpenAI-compatible models before spending a batch run on them.

    python -m pipeline.scripts.probe_llm                       # one JSON-mode call
    python -m pipeline.scripts.probe_llm --model a --model b   # compare candidates
    python -m pipeline.scripts.probe_llm --image some.png      # also test the vision path

Why this exists: the free-tier endpoints that make this POC affordable are also the ones that
disagree about `response_format: json_object` and about base64 image input. One call per
question answers that; a 917-document eval pass started on a model that rejects JSON mode is
answered fifty requests later by a dead daily quota.

Every probe disables the disk cache, because the whole point is to reach the network. The
request is synthetic and carries no personal data, so a probe logs nothing but its verdict.
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from pipeline.config import LlmSettings, get_llm_settings
from pipeline.extraction import DocumentContent, LLMExtractor
from pipeline.llmcall import ModelCallFailed, complete_json

PROBE_MODEL = "probe-model"
TEXT_PROMPT = (
    "Reply with a JSON object only, no prose: keys 'answer' (string) and 'checks' "
    "(array of strings)."
)
TEXT_MESSAGES = [
    {"role": "system", "content": "You emit strict JSON objects and nothing else."},
    {"role": "user", "content": TEXT_PROMPT},
]
# The corpus documents are fictional, so the probe can use one of their shapes directly.
PROBE_DOCUMENT = DocumentContent(
    documentId="PROBE-1",
    docType="aadhaar",
    fileName="probe.png",
    mimeType="image/png",
    contentBase64="",
)


def _no_cache(settings: LlmSettings) -> LlmSettings:
    """A probe that hit the cache would report success without ever calling the endpoint."""
    return replace(settings, cache_enabled=False)


def probe_json_mode(settings: LlmSettings) -> tuple[bool, str, dict[str, Any]]:
    """One call. Returns (usable, detail, facts) where facts report what the model accepted."""
    try:
        result = complete_json(
            _no_cache(settings), messages=TEXT_MESSAGES, component="json probe", client=None
        )
    except ModelCallFailed as exc:
        return False, str(exc), {}
    payload = result.value
    if not isinstance(payload, dict) or not payload:
        return False, f"reply was not a JSON object: {str(payload)[:120]}", {}
    detail = f"answered in {result.latency_ms} ms"
    if not result.json_mode:
        detail += " (JSON mode rejected; it worked only without response_format)"
    return True, detail, {"model": result.model, "jsonMode": result.json_mode}


def probe_vision(settings: LlmSettings, image: Path) -> tuple[bool, str]:
    """Read a rendered document back through the real extractor, image data URI included."""
    raw = image.read_bytes()
    mime = mimetypes.guess_type(str(image))[0] or "image/png"
    document = PROBE_DOCUMENT.model_copy(
        update={"mime_type": mime, "content_base64": base64.b64encode(raw).decode()}
    )
    try:
        fields = LLMExtractor(settings=_no_cache(settings)).extract(document)
    except Exception as exc:  # the point is to report whatever the endpoint throws
        return False, f"{type(exc).__name__}: {exc}"
    if not fields.legible:
        return False, f"answered but read no identity fields: {fields.model_dump_json()[:160]}"
    return True, f"read name={fields.name!r} doc_type={fields.doc_type!r}"


def print_budget(applications: int, documents: int) -> None:
    """What a full corpus pass costs in requests, so a daily quota cannot surprise anyone."""
    lines = [
        "",
        f"Budget for the whole corpus: {documents} documents = {documents} extraction calls,",
        "plus one adjudication call per check that lands on warn/info, so treat",
        f"{applications + documents} as the floor for a run over {applications} applications.",
    ]
    for name, ceiling in (("a $0 OpenRouter key", 50), ("a credited key", 1000)):
        days = -(-documents // ceiling)
        lines.append(f"  {name} (~{ceiling} requests/day): about {days} day(s) per pass")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        help="model to probe; repeat to compare candidates (default: $LLM_MODEL)",
    )
    parser.add_argument("--image", type=Path, default=None, help="PNG to test the vision path")
    parser.add_argument("--applications", type=int, default=200)
    parser.add_argument("--documents", type=int, default=917)
    parser.add_argument("--no-budget", action="store_true", help="skip the request-count note")
    arguments = parser.parse_args(argv)

    settings = get_llm_settings()
    if not settings.enabled:
        print("LLM_API_KEY is unset, so there is nothing to probe.", file=sys.stderr)
        return 2
    print(f"endpoint : {settings.base_url or 'the openai SDK default'}")
    print(f"cache    : disabled for probes (configured at {settings.resolved_cache_dir})")
    if arguments.image is not None and not arguments.image.is_file():
        print(f"--image {arguments.image} is not a readable file", file=sys.stderr)
        return 2

    names = arguments.model or [settings.model]
    failures = 0
    for name in names:
        probe = replace(settings, model=name)
        usable, detail, facts = probe_json_mode(probe)
        print(f"\njson  {name:<48} {'OK  ' if usable else 'FAIL'} {detail}")
        if usable and arguments.image is not None:
            seen, vision_detail = probe_vision(probe, arguments.image)
            print(f"vision {name:<47} {'OK  ' if seen else 'FAIL'} {vision_detail}")
            usable = usable and seen
        if facts.get("model") and facts["model"] != name:
            print(f"       served by {facts['model']}")
        failures += 0 if usable else 1

    if not arguments.no_budget:
        print_budget(arguments.applications, arguments.documents)
    print(
        f"\nverdict : {len(names) - failures} of {len(names)} model(s) usable"
        + ("" if arguments.image is None else " for the probed paths")
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
