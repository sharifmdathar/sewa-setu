"""TemplateExtractor accuracy over the whole synthetic corpus (prompt A3 DoD)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from pipeline.extraction import DocumentContent, ExtractionError, TemplateExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS = REPO_ROOT / "data" / "synthetic" / "dataset-v1"

needs_corpus = pytest.mark.skipif(
    not (CORPUS / "applications.json").is_file(),
    reason="run `python -m generator --n 200 --anomaly-rate 0.25 --seed 42 "
    "--out data/synthetic/dataset-v1` first",
)


def reference_fields(text: str) -> dict[str, object]:
    """Deliberately naive independent parser used as the accuracy oracle."""

    def value(key: str) -> str | None:
        for line in text.splitlines():
            head, separator, tail = line.partition(":")
            if separator and head.strip() == key:
                return tail.strip()
        return None

    def every(key: str) -> list[str]:
        return [
            line.partition(":")[2].strip()
            for line in text.splitlines()
            if line.partition(":")[0].strip() == key
        ]

    return {
        "doc_type": value("DOC_TYPE"),
        "name": value("FULL_NAME"),
        "id_number": value("AADHAAR_NUMBER"),
        "issue_date": dt.date.fromisoformat(value("ISSUE_DATE") or ""),
        "expiry_date": (
            dt.date.fromisoformat(value("EXPIRY_DATE")) if value("EXPIRY_DATE") else None
        ),
        "issuing_authority": value("ISSUING_AUTHORITY"),
        "amounts": [int(raw) for raw in every("AMOUNT_INR")],
    }


@needs_corpus
def test_template_extractor_is_exactly_accurate_on_every_corpus_document() -> None:
    extractor = TemplateExtractor()
    applications = json.loads((CORPUS / "applications.json").read_text())
    checked = 0
    for app in applications:
        for doc in app["documents"]:
            text = (CORPUS / "docs" / doc["fileName"]).read_text(encoding="utf-8")
            content = DocumentContent(
                documentId=doc["id"],
                docType=doc["docType"],
                fileName=doc["fileName"],
                text=text,
            )
            fields = extractor.extract(content)
            assert fields.model_dump() == {
                **reference_fields(text),
                "raw_text": text,
            }, f"field mismatch in {doc['fileName']}"
            checked += 1

    assert checked > 900, f"only {checked} documents checked"


@needs_corpus
def test_extracted_names_match_declaration_unless_identity_was_planted() -> None:
    """C1 pass => every document's name equals the declaration; C1 fail => exactly the
    one planted document disagrees. This pins the corpus to the contract semantics."""
    extractor = TemplateExtractor()
    truth = {
        entry["applicationId"]: entry
        for entry in json.loads((CORPUS / "ground_truth.json").read_text())["applications"]
    }
    for app in json.loads((CORPUS / "applications.json").read_text()):
        declared = app["applicantFields"]["fullName"]
        names = []
        for doc in app["documents"]:
            text = (CORPUS / "docs" / doc["fileName"]).read_text(encoding="utf-8")
            fields = extractor.extract(
                DocumentContent(
                    documentId=doc["id"],
                    docType=doc["docType"],
                    fileName=doc["fileName"],
                    text=text,
                )
            )
            names.append(fields.name)

        divergent = [name for name in names if name != declared]
        if truth[app["id"]]["expected"]["C1"] == "pass":
            assert not divergent, f"{app['id']} undeclared identity divergence"
        else:
            assert len(divergent) == 1, f"{app['id']} planted name_mismatch not visible"


def test_documents_without_a_text_layer_are_rejected() -> None:
    extractor = TemplateExtractor()
    blank = DocumentContent(documentId="D1", docType="aadhaar", fileName="a.txt", text="")
    with pytest.raises(ExtractionError):
        extractor.extract(blank)


def test_unreadable_text_is_not_reported_as_legible() -> None:
    extractor = TemplateExtractor()
    noise = DocumentContent(
        documentId="D2", docType="aadhaar", fileName="n.txt", text="blurry scan, no fields\n"
    )
    with pytest.raises(ExtractionError):
        extractor.extract(noise)


def test_amounts_tolerate_rupee_signs_and_digit_grouping() -> None:
    text = (
        "DOC_TYPE: bank_statement\nFULL_NAME: Anita Baruah\nAADHAAR_NUMBER: 4123 8890 1177\n"
        "ISSUE_DATE: 2026-01-05\nEXPIRY_DATE: 2027-01-05\nISSUING_AUTHORITY: X\n"
        "AMOUNT_INR: ₹1,50,000\n"
    )
    fields = TemplateExtractor().extract(
        DocumentContent(documentId="D3", docType="bank_statement", fileName="b.txt", text=text)
    )
    assert fields.amounts == [150000]
    assert fields.legible is True
