"""Smoke test: the app serves /healthz and the JSON store round-trips records."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.api.main import app
from pipeline.store.jsonstore import JsonStore


def test_healthz_returns_200() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_store_roundtrip_is_thread_safe(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: store.put("applications", {"id": f"app-{n}"}), range(20)))

    written = {rec["id"] for rec in store.list("applications")}
    assert written == {f"app-{n}" for n in range(20)}
    assert store.get("reports", "app-0") is None

    store.put("reports", {"applicationId": "app-0", "riskScore": 12})
    assert store.get("reports", "app-0") == {"applicationId": "app-0", "riskScore": 12}
    assert store.delete("reports", "app-0") is True
    assert store.get("reports", "app-0") is None
