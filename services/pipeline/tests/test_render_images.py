"""The PNG leg of the synthetic corpus: rendered documents for the vision extraction path.

Skipped without Pillow (`pip install -e data/synthetic[images]`), because the text corpus and
every other test in this repo must not need a graphics library.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import PIL  # noqa: F401  (presence check only)

    HAS_PILLOW = True
except ImportError:  # pragma: no cover - exercised on machines without the images extra
    HAS_PILLOW = False

pytestmark = pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")

from generator import build_dataset  # noqa: E402  (after the skip guard)
from generator.__main__ import main as generator_main  # noqa: E402
from generator.render import (  # noqa: E402
    IMAGE_DIR,
    MANIFEST_FILE,
    pick_documents,
    render_png,
    write_image_leg,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture()
def apps() -> list:
    return build_dataset(n=12, anomaly_rate=0.25, seed=7)


def test_a_rendered_document_is_a_real_png() -> None:
    body = "FULL_NAME: Anita Baruah\nDOC_TYPE: aadhaar\n"

    rendered = render_png(body)

    assert rendered.startswith(PNG_MAGIC) and len(rendered) > 1000


def test_a_small_selection_still_spans_the_document_shapes(apps: list) -> None:
    picked = pick_documents(apps, 8)
    types = {doc.doc_type for _, doc in picked}

    assert len(picked) == 8
    assert len(types) >= 4, f"only {sorted(types)} were picked"
    assert [doc.document_id for _, doc in picked] == [
        doc.document_id for _, doc in pick_documents(apps, 8)
    ], "selection must be deterministic"


def test_a_selection_larger_than_the_corpus_returns_every_document(apps: list) -> None:
    total = sum(len(app.docs) for app in apps)
    assert len(pick_documents(apps, total + 50)) == total


def test_the_image_leg_lands_beside_the_text_corpus_and_never_over_it(
    apps: list, tmp_path: Path
) -> None:
    manifest = write_image_leg(apps, tmp_path, 5)

    assert manifest["count"] == 5
    written = sorted(path.name for path in (tmp_path / IMAGE_DIR).iterdir())
    assert len(written) == 5 and all(name.endswith(".png") for name in written)
    assert all(Path(entry["imageFileName"]).name in written for entry in manifest["documents"])
    # The text corpus is what every other consumer reads, so it must stay untouched here.
    assert not (tmp_path / "docs").exists()


def test_the_manifest_carries_what_a_correct_read_should_return(
    apps: list, tmp_path: Path
) -> None:
    manifest = write_image_leg(apps, tmp_path, 3)
    entry = manifest["documents"][0]

    assert entry["expectedFields"]["name"]
    assert entry["expectedFields"]["docType"] == entry["docType"]
    assert entry["sha256"] and entry["applicationId"].startswith("APP-")
    assert json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))["count"] == 3


def test_rerendering_replaces_the_previous_leg_instead_of_accumulating(
    apps: list, tmp_path: Path
) -> None:
    directory = tmp_path / IMAGE_DIR
    directory.mkdir()
    (directory / "STALE.png").write_bytes(b"not a document")

    write_image_leg(apps, tmp_path, 2)

    assert not (directory / "STALE.png").exists()
    assert len(list(directory.glob("*.png"))) == 2


def test_the_cli_flag_reports_the_rendered_leg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = generator_main(["--n", "6", "--seed", "3", "--out", str(tmp_path), "--png", "4"])

    printed = capsys.readouterr().out
    assert code == 0 and "rendered 4 PNGs" in printed
    assert len(list((tmp_path / IMAGE_DIR).glob("*.png"))) == 4


def test_zero_requested_means_no_image_leg_at_all(apps: list, tmp_path: Path) -> None:
    assert write_image_leg(apps, tmp_path, 0)["count"] == 0
    assert not (tmp_path / IMAGE_DIR).exists()
