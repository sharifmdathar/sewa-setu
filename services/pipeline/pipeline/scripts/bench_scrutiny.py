"""Time a real scrutiny end to end over HTTP (integration step I4, submission M5).

    python -m pipeline.scripts.bench_scrutiny [--base-url URL] [--sample 20]
        [--repeat 1] [--json PATH]

The eval harness reports ~0.13 ms/application, but that figure is *offline*: template
extraction, no HTTP, no store, one process. It cannot substantiate the demo's headline
("12-18 minutes of manual scrutiny per application"), so this script measures the thing the
officer actually waits for: a `POST /applications/{id}/scrutiny/run` to a running uvicorn,
answered by the full pipeline and written back to the JSON store.

Applications come from `/officer/queue` and are kept only if they hold at least one document -
an empty application answers 409, and scoring nothing is not the workload being timed. Re-runs
append scrutiny events to each application's timeline, which is what the officer's "run again"
button does too.

What this does NOT cover: the model path. With `LLM_API_KEY` unset the template extractor and
the deterministic adjudicator run, and the artifact records their names in `modelMeta` so the
caveat travels with the number rather than living in a footnote.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from pipeline.logs import event, get_logger

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_SAMPLE = 20
TARGET_SECONDS = 60.0  # SPEC.md section 2: scrutiny time per application < 60 s
LOGGER = get_logger("scripts.bench_scrutiny")


class NoServer(RuntimeError):
    """Nothing answered, or answered with something that is not this API."""


@dataclass(frozen=True)
class Sample:
    application_id: str
    documents: int
    seconds: float
    recommendation: str
    first: bool = True


def filing(client: httpx.Client, application_ids: list[str]) -> list[tuple[str, int]]:
    """Applications that actually have documents, richest filing first."""
    filed = []
    for application_id in application_ids:
        documents = len(client.get(f"/applications/{application_id}/documents").json())
        if documents:
            filed.append((application_id, documents))
    return sorted(filed, key=lambda item: (-item[1], item[0]))


def run(client: httpx.Client, applications: list[tuple[str, int]], repeat: int) -> list[Sample]:
    """One timed scrutiny per application, `repeat` times, in application order."""
    samples: list[Sample] = []
    for round_number in range(repeat):
        for application_id, documents in applications:
            started = time.perf_counter()
            response = client.post(f"/applications/{application_id}/scrutiny/run")
            elapsed = time.perf_counter() - started
            if response.status_code != 200:
                raise NoServer(
                    f"{application_id}: scrutiny answered {response.status_code} - re-seed the "
                    "store (python -m pipeline.scripts.seed_demo)"
                )
            samples.append(
                Sample(
                    application_id,
                    documents,
                    elapsed,
                    str(response.json()["recommendation"]),
                    first=round_number == 0,
                )
            )
    return samples


def summarise(samples: list[Sample], target_seconds: float = TARGET_SECONDS) -> dict[str, Any]:
    """Distribution of the measured runs, in the shape the submission table wants."""
    seconds = [sample.seconds for sample in samples]
    ordered = sorted(seconds)

    def at(fraction: float) -> float:
        """Nearest-rank percentile, because a 20-sample list has no interpolated meaning."""
        index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
        return ordered[index]

    return {
        "runs": len(seconds),
        "applications": len({sample.application_id for sample in samples}),
        "minSeconds": round(ordered[0], 4),
        "p50Seconds": round(at(0.50), 4),
        "p95Seconds": round(at(0.95), 4),
        "maxSeconds": round(ordered[-1], 4),
        "meanSeconds": round(statistics.fmean(seconds), 4),
        "targetSeconds": target_seconds,
        "targetMet": all(value < target_seconds for value in seconds),
        "applicationsPerMinute": round(60 / statistics.fmean(seconds)),
    }


def report(client: httpx.Client, samples: list[Sample]) -> dict[str, Any]:
    """What the server itself recorded for the last run, so the two clocks can be compared."""
    last = samples[-1].application_id
    payload = client.get(f"/applications/{last}/scrutiny").json()
    return {
        "applicationId": last,
        "riskScore": payload["riskScore"],
        "recommendation": payload["recommendation"],
        "checks": {check["checkId"]: check["status"] for check in payload["checks"]},
        "modelMeta": payload["modelMeta"],
        "serverAvgScrutinySeconds": client.get("/metrics/summary").json()["avgScrutinySeconds"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time live scrutinies over HTTP")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, help="applications to time")
    parser.add_argument("--repeat", type=int, default=1, help="times per application")
    parser.add_argument("--json", type=Path, default=None, help="also write the artifact here")
    arguments = parser.parse_args(argv)

    with httpx.Client(base_url=arguments.base_url, timeout=60.0) as client:
        try:
            if client.get("/healthz").status_code != 200:
                raise NoServer(f"{arguments.base_url} did not answer /healthz")
            queue = client.get("/officer/queue").json()
            filed = filing(client, [str(item["applicationId"]) for item in queue])
            chosen = filed[: arguments.sample]
            if not chosen:
                raise NoServer(
                    f"no application at {arguments.base_url} has documents - run "
                    "`python -m pipeline.scripts.seed_demo` first"
                )
            samples = run(client, chosen, arguments.repeat)
            summary = summarise(samples)
            summary["measured"] = report(client, samples)
        except (httpx.HTTPError, NoServer) as exc:
            print(f"error: {exc}")
            return 2

    event(
        LOGGER,
        "live scrutiny benchmark",
        base=str(arguments.base_url),
        runs=summary["runs"],
        p50Seconds=summary["p50Seconds"],
        p95Seconds=summary["p95Seconds"],
        maxSeconds=summary["maxSeconds"],
        targetMet=summary["targetMet"],
    )
    for sample in samples:
        print(f"  {sample.application_id}  {sample.seconds * 1000:8.1f} ms")
    print(
        f"{summary['runs']} runs over {summary['applications']} applications: "
        f"p50 {summary['p50Seconds']}s  p95 {summary['p95Seconds']}s  "
        f"max {summary['maxSeconds']}s  target <{summary['targetSeconds']}s "
        f"{'met' if summary['targetMet'] else 'MISSED'}"
    )
    print(
        f"  extractor {summary['measured']['modelMeta']['extractor']} / "
        f"adjudicator {summary['measured']['modelMeta']['adjudicator']} "
        f"(model path needs LLM_API_KEY)"
    )
    if arguments.json is not None:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(
            json.dumps({"summary": summary, "samples": [asdict(s) for s in samples]}, indent=2)
        )
        print(f"  artifact: {arguments.json}")
    return 0 if summary["targetMet"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
