"""A local OpenAI-compatible endpoint, so the model path is tested over HTTP rather than assumed.

The extractor and the adjudicator have only ever met injected stubs, which means the part that
actually breaks in production — socket behaviour, status codes, the SDK's own error types, whether
a cached answer really avoids a request — was never exercised. This stands up a real server on an
ephemeral port (never 8000, which is the shared demo instance) and answers the chat-completions
shape, with knobs for exactly the failures a $0 key produces: rate limits, a model that refuses
`response_format`, a hard auth rejection, and prose where JSON was asked for.

Nothing here reaches the internet, and nothing here is a fixture for the API suite: it is the
other side of `pipeline/llmcall.py`.
"""

from __future__ import annotations

import json
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

JSON_MODE_ERROR = "Error code: 400 - 'response_format' is not supported by this model"


class _State:
    """Everything the handler needs, kept off the handler so each request sees one source."""

    def __init__(
        self,
        reply: dict[str, Any],
        *,
        served_model: str,
        fail_first: int,
        reject_json_mode: bool,
        hard_status: int | None,
        raw_content: str | None,
        delay: float,
    ) -> None:
        self.reply = reply
        self.served_model = served_model
        self.fail_first = fail_first
        self.reject_json_mode = reject_json_mode
        self.hard_status = hard_status
        self.raw_content = raw_content
        self.delay = delay
        self.requests: list[dict[str, Any]] = []

    @property
    def json_mode_seen(self) -> bool:
        return any("response_format" in request for request in self.requests)

    @property
    def image_seen(self) -> bool:
        return "image_url" in json.dumps(self.requests)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # every reply below carries an accurate Content-Length

    def log_message(self, *_args: Any) -> None:
        pass  # the suite's output stays readable; assertions read `state.requests` instead

    def do_POST(self) -> None:  # noqa: N802 - http.server's own name
        state: _State = self.server.state  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._reply(400, {"error": {"message": "body was not JSON"}})
            return

        state.requests.append(body)
        seen = len(state.requests)
        if state.delay:
            time.sleep(state.delay)  # a model that is slow, not broken

        if state.hard_status is not None:
            self._reply(state.hard_status, {"error": {"message": "rejected by the endpoint"}})
            return
        if seen <= state.fail_first:
            self._reply(
                429,
                {"error": {"message": "rate limit exceeded, slow down"}},
                retry_after="0",
            )
            return
        if state.reject_json_mode and "response_format" in body:
            self._reply(400, {"error": {"message": JSON_MODE_ERROR}})
            return

        content = (
            state.raw_content if state.raw_content is not None else json.dumps(state.reply)
        )
        self._reply(
            200,
            {
                "id": f"gen-{seen}",
                "model": state.served_model,
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}}
                ],
            },
        )

    def _reply(self, status: int, payload: dict[str, Any], retry_after: str | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if retry_after is not None:
            self.send_header("Retry-After", retry_after)
        self.end_headers()
        self.wfile.write(raw)


class FakeEndpoint:
    """Start/stop a threaded local endpoint; `base_url` is what `LLM_BASE_URL` wants."""

    def __init__(
        self,
        reply: dict[str, Any] | None = None,
        *,
        served_model: str = "fake-vlm-1",
        fail_first: int = 0,
        reject_json_mode: bool = False,
        hard_status: int | None = None,
        raw_content: str | None = None,
        delay: float = 0.0,
    ) -> None:
        self._state = _State(
            reply=reply or {"ok": True},
            served_model=served_model,
            fail_first=fail_first,
            reject_json_mode=reject_json_mode,
            hard_status=hard_status,
            raw_content=raw_content,
            delay=delay,
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.state = self._state  # type: ignore[attr-defined]
        # serve_forever() polls at half a second by default, and shutdown() waits out that poll,
        # so the default costs 0.5 s of every test's teardown for no reason.
        self._thread = threading.Thread(
            target=partial(self._server.serve_forever, poll_interval=0.02), daemon=True
        )

    @property
    def base_url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/v1"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return list(self._state.requests)

    @property
    def count(self) -> int:
        return len(self._state.requests)

    @property
    def json_mode_seen(self) -> bool:
        return self._state.json_mode_seen

    @property
    def image_seen(self) -> bool:
        return self._state.image_seen

    def __enter__(self) -> FakeEndpoint:
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
