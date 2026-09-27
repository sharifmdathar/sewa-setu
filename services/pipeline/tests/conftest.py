"""Server lifecycle for the I1 conformance suite.

Only test_api_live_contract.py asks for these. An in-process TestClient cannot catch a mismatch
between what the code returns and what a real ASGI server puts on the wire, so those tests run
against uvicorn over HTTP. The server is reused when the port is already taken - it may be
someone's demo instance - and never killed; cleanup deletes only the applications this suite
submitted, so a concurrent real client's records stay untouched.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from pipeline.store.jsonstore import DEFAULT_ROOT

PORT = int(os.environ.get("SEWA_CONFORMANCE_PORT") or 8000)
BASE_URL = f"http://127.0.0.1:{PORT}"
PIPELINE_DIR = Path(__file__).resolve().parents[1]


def _health(client: httpx.Client) -> bool:
    try:
        return client.get("/healthz").status_code == 200
    except Exception:  # any transport or protocol failure means "no API here"
        return False


def _wait_ready(client: httpx.Client, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if _health(client):
            return
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited with {process.returncode}")
        time.sleep(0.25)
    raise RuntimeError("uvicorn did not answer /healthz within 25s")


def _track_created(client: httpx.Client, created: list[str]) -> None:
    """Remember every application this suite submits, so teardown deletes exactly those.

    Diffing the store directory instead would also delete anything a *real* client submitted
    while the suite ran - the demo instance is shared, so that is not a trade to make.
    """

    def hook(response: httpx.Response) -> None:
        request = response.request
        if (
            request.method == "POST"
            and request.url.path == "/applications"
            and response.status_code == 201
        ):
            # An event hook sees the response before its body is streamed in, so read first.
            with contextlib.suppress(ValueError, KeyError, httpx.ResponseNotRead):
                response.read()
                created.append(str(response.json()["id"]))

    client.event_hooks["response"].append(hook)


def _remove(root: Path, app_id: str) -> None:
    for collection in ("applications", "reports"):
        (root / collection / f"{app_id}.json").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[httpx.Client]:
    """A real HTTP client against port 8000, spawning the server only when nobody else has it."""
    created: list[str] = []
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    _track_created(client, created)
    borrowed = _health(client)
    process: subprocess.Popen[str] | None = None
    cleanup_root: Path | None = Path(DEFAULT_ROOT)

    if borrowed:
        # Only clean up a shared server we can positively identify as ours (default store, and
        # the contract's own service catalog answering) - never someone else's data directory.
        known_services = {str(entry["id"]) for entry in client.get("/services").json()}
        if known_services != {"income_certificate", "caste_certificate", "residence_certificate"}:
            cleanup_root = None
    else:
        store = tmp_path_factory.mktemp("live-api-store")
        environment = {**os.environ, "PIPELINE_VAR_DIR": str(store)}
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "pipeline.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--no-access-log",
            ],
            cwd=str(PIPELINE_DIR),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_ready(client, process)
        except Exception:
            process.terminate()
            raise

    yield client

    client.close()
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    elif cleanup_root is not None:  # exactly the applications this suite submitted
        for app_id in created:
            _remove(cleanup_root, app_id)
