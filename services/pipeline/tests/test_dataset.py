"""Dataset integrity tests for the synthetic generator (prompt A2 DoD).

The generator is a separate Track A distribution under data/synthetic; install it with
`pip install -e ../../data/synthetic` from services/pipeline (see the runbook).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

generator = pytest.importorskip("generator")

from generator.anomalies import ANOMALY_TYPES, CHECKS  # noqa: E402
from generator.services import SERVICES, required_doc_types  # noqa: E402

N = 200
ANOMALY_RATE = 0.25
SEED = 42
FLAGS = {"n": N, "anomaly_rate": ANOMALY_RATE, "seed": SEED}


def _corpus(out_dir: Path) -> Path:
    apps = generator.build_dataset(**FLAGS)
    labels = generator.ground_truth(apps, seed=SEED, anomaly_rate=ANOMALY_RATE)
    return generator.write_dataset(apps, labels, out_dir)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_corpus_is_integrity_clean(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    applications = json.loads((root / "applications.json").read_text())
    truth = json.loads((root / "ground_truth.json").read_text())
    by_id = {entry["applicationId"]: entry for entry in truth["applications"]}

    assert len(applications) == N
    assert {app["serviceId"] for app in applications} == {s["id"] for s in SERVICES}

    referenced: set[str] = set()
    for app in applications:
        entry = by_id[app["id"]]
        assert sorted(entry["expected"]) == sorted(CHECKS)
        assert set(entry["anomalies"]) <= set(ANOMALY_TYPES)
        assert all(verdict in {"pass", "fail"} for verdict in entry["expected"].values())
        assert entry["clean"] == (entry["anomalies"] == [])

        docs = app["documents"]
        assert docs, f"{app['id']} has no documents"
        attached = set()
        for doc in docs:
            path = root / "docs" / doc["fileName"]
            assert path.is_file(), f"missing document file {doc['fileName']}"
            assert _sha(path) == doc["sha256"], f"hash mismatch for {doc['fileName']}"
            assert "FULL_NAME: " in path.read_text(encoding="utf-8")
            referenced.add(doc["fileName"])
            attached.add(doc["docType"])

        if not set(required_doc_types(app["serviceId"])) <= attached:
            assert entry["expected"]["C3"] == "fail", f"unlabelled missing doc in {app['id']}"

    written = {p.name for p in (root / "docs").iterdir()}
    assert written == referenced, "orphan or missing document files"


def test_every_anomaly_type_and_check_is_represented(tmp_path: Path) -> None:
    counts = json.loads((_corpus(tmp_path) / "ground_truth.json").read_text())["counts"]

    for a_type in ANOMALY_TYPES:
        assert counts["byAnomalyType"][a_type] > 0, f"{a_type} never planted"
    for check in CHECKS:
        assert counts["failByCheck"][check] > 0, f"{check} has no failing example"

    assert abs(counts["anomalous"] / N - ANOMALY_RATE) <= 0.10


def test_generator_is_deterministic(tmp_path: Path) -> None:
    first = _corpus(tmp_path / "a")
    second = _corpus(tmp_path / "b")
    for name in ("applications.json", "ground_truth.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert sorted(p.read_bytes() for p in (first / "docs").iterdir()) == sorted(
        p.read_bytes() for p in (second / "docs").iterdir()
    )
