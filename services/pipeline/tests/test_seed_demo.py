"""I2 prep: the demo seeder must produce a store the officer UI can open and defend.

Asserted against the real dataset-v1 (rebuilt into a temp dir on a fresh clone that has not
generated it yet). The load-bearing properties are: it is idempotent, it only ever touches
generator-shaped ids, every seeded application ends up with a contract-valid report, and the
high-risk count is not luck.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from contract import assert_valid
from corpus import corpus_or_rebuild

from pipeline.api.repository import Repository
from pipeline.scripts import seed_demo


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The corpus directory to seed from, generating it if this clone lacks it."""
    return corpus_or_rebuild(tmp_path_factory).root


@pytest.fixture()
def seeded(tmp_path: Path, dataset: Path) -> seed_demo.SeedResult:
    return seed_demo.seed(tmp_path / "var", limit=20, dataset=dataset)


def reports(repository: Repository) -> dict[str, dict[str, object]]:
    return {
        record["id"]: repository.get_report(record["id"]) or {} for record in repository.all()
    }


def test_the_seeder_loads_twenty_applications_with_reports(
    seeded: seed_demo.SeedResult, tmp_path: Path
) -> None:
    store = Repository(tmp_path / "var")
    records = store.all()

    assert len(seeded.seeded) == 20
    assert len(records) == 20
    assert [record["id"] for record in records] == [f"APP-{index:04d}" for index in range(1, 21)]
    assert all(record["documents"] for record in records)
    assert all(record["status"] == "scrutiny_done" for record in records)
    assert len(reports(store)) == 20


def test_every_seeded_application_carries_a_contract_valid_report(
    seeded: seed_demo.SeedResult, tmp_path: Path
) -> None:
    store = Repository(tmp_path / "var")

    for record in store.all():
        report = store.get_report(str(record["id"]))
        assert report is not None, record["id"]
        assert_valid(report, "ScrutinyReport")
        for check in report["checks"]:
            assert_valid(check, "ScrutinyCheck")
        assert [check["checkId"] for check in report["checks"]] == ["C1", "C2", "C3", "C4", "C5"]
        assert all(check["evidence"] and check["explanation"] for check in report["checks"])
        assert report["applicationId"] == record["id"]
        assert 0 <= int(report["riskScore"]) <= 100


def test_at_least_two_seeded_applications_are_high_risk(
    seeded: seed_demo.SeedResult, tmp_path: Path
) -> None:
    """The demo has to show the queue doing its job, not a wall of approvals."""
    store = Repository(tmp_path / "var")
    threshold = 60

    assert len(seeded.high_risk) >= 2
    for app_id, score in seeded.high_risk:
        report = store.get_report(app_id)
        assert report is not None and int(report["riskScore"]) == score >= threshold
        assert len(report["checks"]) == 5
        assert report["recommendation"] in {"manual_review", "reject"}

    flagged_by_check = [
        app_id
        for app_id, report in reports(store).items()
        if any(
            check["checkId"] == "C5" and check["status"] == "fail" for check in report["checks"]
        )
    ]
    assert set(flagged_by_check) & set(seeded.flagged)


def test_seeding_is_idempotent_and_reports_what_it_replaced(
    tmp_path: Path, dataset: Path
) -> None:
    root = tmp_path / "var"

    first = seed_demo.seed(root, limit=20, dataset=dataset)
    second = seed_demo.seed(root, limit=20, dataset=dataset)

    assert first.cleared == [] and sorted(second.cleared) == sorted(first.seeded)
    assert second.seeded == first.seeded
    assert len(Repository(root).all()) == 20
    assert len(list((root / "reports").glob("*.json"))) == 20


def test_re_seeding_a_smaller_slice_leaves_no_stale_demo_records(
    tmp_path: Path, dataset: Path
) -> None:
    root = tmp_path / "var"
    seed_demo.seed(root, limit=20, dataset=dataset)

    smaller = seed_demo.seed(root, limit=5, dataset=dataset)

    assert len(smaller.cleared) == 20
    assert [record["id"] for record in Repository(root).all()] == [
        f"APP-{index:04d}" for index in range(1, 6)
    ]


def test_seeding_never_touches_applications_submitted_through_the_api(
    tmp_path: Path, dataset: Path
) -> None:
    """Demo ids are `APP-0001`; API ids are `APP-<hex>`. Only the former may be cleared."""
    root = tmp_path / "var"
    store = Repository(root)
    live = store.create("income_certificate", {"fullName": "Some Citizen"})
    store.save_report(  # an unrelated report that must survive too
        seed_demo.run_scrutiny(
            store.scrutiny_request(store.get(str(live["id"])), dataset_as_of(dataset))[0],
            [],
        )
    )

    seed_demo.seed(root, limit=20, dataset=dataset)

    after = Repository(root)
    ids = [str(record["id"]) for record in after.all()]
    assert str(live["id"]) in ids
    assert len(ids) == 21
    assert after.get_report(str(live["id"])) is not None


def dataset_as_of(path: Path):  # small helper for the test above
    import datetime as dt

    return dt.date.fromisoformat(json.loads((path / "ground_truth.json").read_text())["asOf"])


def test_seeding_twice_produces_identical_scores_and_evidence(
    tmp_path: Path, dataset: Path
) -> None:
    def snapshot(root: Path) -> list[dict[str, object]]:
        seed_demo.seed(root, limit=8, dataset=dataset)
        return [
            {
                "id": record["id"],
                "status": record["status"],
                "createdAt": record["createdAt"],
                "documents": [
                    {key: doc[key] for key in ("id", "docType", "fileName", "uploadedAt", "sha256")}
                    for doc in record["documents"]
                ],
                "report": {
                    key: value
                    for key, value in (Repository(root).get_report(str(record["id"])) or {}).items()
                    if key != "generatedAt"
                },
            }
            for record in sorted(Repository(root).all(), key=lambda r: str(r["id"]))
        ]

    left = snapshot(tmp_path / "a")
    right = snapshot(tmp_path / "b")

    assert left == right
    assert len(left) == 8


def test_the_seeded_store_populates_the_officer_queue_and_metrics(
    seeded: seed_demo.SeedResult, tmp_path: Path
) -> None:
    store = Repository(tmp_path / "var")

    queue = store.queue()
    scores = [int(item["riskScore"]) for item in queue]

    assert len(queue) == 20
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == max(dict(seeded.high_risk).values() or scores)
    metrics = store.metrics(flag_threshold=60, generated_at=dataset_today())
    assert metrics["applicationsTotal"] == 20
    assert metrics["pending"] == 20 and metrics["decided"] == 0
    assert metrics["flagRate"] == round(len(seeded.high_risk) / 20, 3)


def dataset_today():
    import datetime as dt

    return dt.datetime.now(dt.UTC)


def test_missing_dataset_is_a_clear_error_not_a_traceback(tmp_path: Path) -> None:
    with pytest.raises(seed_demo.DatasetMissing, match="python -m generator"):
        seed_demo.load_cases(tmp_path / "nowhere", limit=5)

    code = seed_demo.main(["--root", str(tmp_path / "var"), "--dataset", str(tmp_path / "nope")])
    assert code == 2


def test_the_documented_module_command_runs(tmp_path: Path, dataset: Path) -> None:
    """`python -m pipeline.scripts.seed_demo` is what the runbook and I2 will type."""
    root = tmp_path / "var"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.scripts.seed_demo",
            "--root",
            str(root),
            "--limit",
            "6",
            "--dataset",
            str(dataset),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "seeded 6 applications" in result.stdout
    assert len(Repository(root).all()) == 6
