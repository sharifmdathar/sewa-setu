"""The image leg's scoring, driven by stub extractors plus one real control run.

The control run (`--reader text`) is the important one here: it needs no endpoint, and it fails
loudly if `image_manifest.json`'s expected values ever drift from what the pipeline's own reader
gets out of the same document.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from pipeline.extraction import ExtractedFields, ExtractionError, TemplateExtractor

from eval.image_leg import as_dict, build_extractor, load_manifest, main
from eval.image_leg_md import render_markdown
from eval.image_score import (
    Entry,
    LegResult,
    Tally,
    normalise,
    percentile,
    score_documents,
    score_entry,
)

try:
    from generator import build_dataset, ground_truth, write_dataset
    from generator.render import write_image_leg

    HAS_GENERATOR = True
except ImportError:  # pragma: no cover - the generator is an editable install
    HAS_GENERATOR = False

FIELDS_PRESENT = {
    "docType": "aadhaar",
    "name": "Anita Lohar",
    "idNumber": "5000 0000 0000",
    "issueDate": "2007-04-08",
    "expiryDate": "2027-04-08",
    "issuingAuthority": "Unique Fictiona Identity Authority",
    "amounts": [],
}


def _entry(**overrides: Any) -> Entry:
    values: dict[str, Any] = {
        "application_id": "APP-0001",
        "document_id": "APP-0001-D1",
        "doc_type": "aadhaar",
        "text_file_name": "APP-0001-aadhaar-1.txt",
        "image_file_name": "APP-0001-aadhaar-1.png",
        "expected": dict(FIELDS_PRESENT),
    }
    return Entry(**{**values, **overrides})


class StubExtractor:
    """Returns one prepared `ExtractedFields` per document, or raises what it was told to."""

    name = "stub"

    def __init__(self, fields: ExtractedFields | None = None, fails: bool = False) -> None:
        self.fields = fields
        self.fails = fails
        self._meta = None

    @property
    def last_meta(self) -> Any:
        return self._meta

    def extract(self, document: Any) -> ExtractedFields:
        if self.fails:
            raise ExtractionError(f"{document.file_name}: nothing readable")
        assert self.fields is not None
        return self.fields


def _fields(**overrides: Any) -> ExtractedFields:
    values: dict[str, Any] = {
        "doc_type": "aadhaar",
        "name": "Anita Lohar",
        "id_number": "5000 0000 0000",
        "issue_date": dt.date(2007, 4, 8),
        "expiry_date": dt.date(2027, 4, 8),
        "issuing_authority": "Unique Fictiona Identity Authority",
        "amounts": [],
    }
    return ExtractedFields(**{**values, **overrides})


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    """A tiny real corpus: applications, text documents, and a rendered image leg."""
    apps = build_dataset(n=8, anomaly_rate=0.25, seed=11)
    write_dataset(apps, ground_truth(apps, seed=11, anomaly_rate=0.25), tmp_path)
    write_image_leg(apps, tmp_path, 8)
    return tmp_path


def test_normalisation_ignores_formatting_but_not_content() -> None:
    assert normalise("idNumber", "5000 0000 0000") == normalise("idNumber", "500000000000")
    assert normalise("name", "  ANITA   lohar ") == normalise("name", "Anita Lohar")
    assert normalise("issueDate", dt.date(2007, 4, 8)) == "2007-04-08"
    assert normalise("issueDate", "2007-04-08T00:00:00Z")[:10] == "2007-04-08"
    assert normalise("amounts", [1200, 45]) == normalise("amounts", ["45", "1,200"])
    assert normalise("amounts", None) == ""
    assert normalise("name", "Anita Lohar") != normalise("name", "Anita Baruah")


def test_a_perfect_read_scores_one_everywhere() -> None:
    result = LegResult()
    score_entry(_entry(), _fields(), result)

    assert result.clean_reads == 1
    assert result.overall.as_dict()["recall"] == 1.0
    assert result.overall.as_dict()["precision"] == 1.0
    assert result.overall.expected == 6, "six of the seven fields are stated on this document"


def test_a_blank_read_loses_recall_without_inventing_precision_loss() -> None:
    result = LegResult()
    score_entry(_entry(), ExtractedFields(doc_type="aadhaar"), result)

    assert result.clean_reads == 0
    assert result.overall.matched == 1, "the doc type it was handed on the side"
    assert result.overall.returned == 1
    assert result.overall.expected == 6


def test_an_invented_expiry_date_shows_in_precision_and_nowhere_else() -> None:
    entry = _entry(expected={**FIELDS_PRESENT, "expiryDate": None})
    result = LegResult()
    score_entry(entry, _fields(), result)

    assert result.overall.expected == 5 and result.overall.matched == 5
    assert result.overall.as_dict()["recall"] == 1.0, "recall alone cannot see a hallucination"
    assert result.overall.returned == 6, "it answered a field the document never stated"
    assert result.overall.as_dict()["precision"] == round(5 / 6, 4)
    assert result.clean_reads == 0, "a clean read also means no false answers"


def test_a_minimally_formatted_answer_still_matches() -> None:
    result = LegResult()
    score_entry(
        _entry(),
        _fields(
            name="ANITA   LOHAR",
            id_number="500000000000",
            issue_date=dt.date(2007, 4, 8),
            issuing_authority="unique fictiona identity authority",
        ),
        result,
    )

    assert result.clean_reads == 1 and result.overall.matched == 6


def test_an_unreadable_document_charges_only_what_it_lost() -> None:
    entries = [_entry(), _entry(document_id="APP-0002-D1")]
    result = score_documents(
        entries, StubExtractor(fails=True), Path("/unused"), "model", LegResult()
    )

    assert result.documents == 2 and result.unreadable == 2
    assert result.overall.expected == 12 and result.overall.matched == 0
    assert {row["documentId"] for row in result.problems} == {"APP-0001-D1", "APP-0002-D1"}
    assert result.problems[0]["fieldsLost"] == 6


def test_percentile_sits_on_a_real_value() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([10, 20, 30], 0.0) == 10.0
    assert percentile([10, 20, 30], 1.0) == 30.0
    assert percentile([10, 20, 30], 0.5) == 20.0


def test_a_missing_manifest_tells_you_the_command_that_makes_one(
    tmp_path: Path, capsys: Any
) -> None:
    with pytest.raises(SystemExit) as caught:
        load_manifest(tmp_path)

    assert caught.value.code == 2
    assert "--png 20" in capsys.readouterr().err


@pytest.mark.skipif(not HAS_GENERATOR, reason="generator package not installed")
def test_the_text_control_reads_its_own_manifest_perfectly(corpus: Path, capsys: Any) -> None:
    code = main(["--dataset", str(corpus), "--out", str(corpus / "out"), "--reader", "text"])
    payload = json.loads(
        next(Path(corpus / "out").glob("*/image_leg.json")).read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["documents"] == 8
    assert payload["fields"]["recall"] == 1.0, payload["problems"]
    assert payload["fields"]["precision"] == 1.0
    assert payload["cleanReads"] == 8 and payload["unreadable"] == 0
    markdown = next(Path(corpus / "out").glob("*/image_leg.md")).read_text(encoding="utf-8")
    assert "read-back accuracy (text reader)" in markdown
    assert "Whole documents read correctly | 8 of 8 (100%)" in markdown
    assert "This is the control" in markdown, "a control table must label itself as one"
    assert "8 of 8 read completely" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_GENERATOR, reason="generator package not installed")
def test_the_model_reader_sends_pixels_not_text(corpus: Path) -> None:
    entries = load_manifest(corpus)
    seen: list[Any] = []

    class Recorder(StubExtractor):
        def extract(self, document: Any) -> ExtractedFields:
            seen.append(document)
            return _fields()

    score_documents(entries[:2], Recorder(), corpus, "model", LegResult())

    assert len(seen) == 2
    assert all(item.has_image and item.content_base64 for item in seen)
    assert all(item.text is None for item in seen)


def test_the_model_reader_refuses_to_score_pixels_with_a_text_parser(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import pipeline.agent as agent

    monkeypatch.setattr(agent, "default_extractor", TemplateExtractor)

    assert isinstance(build_extractor("text"), TemplateExtractor)
    with pytest.raises(SystemExit) as caught:
        build_extractor("model")

    assert caught.value.code == 2
    assert "--reader text" in capsys.readouterr().err


def test_the_payload_carries_the_provenance_a_reader_needs() -> None:
    result = LegResult(documents=1, clean_reads=1, latencies_ms=[1200, 900])
    result.overall = Tally(expected=5, returned=5, matched=5)
    payload = as_dict(result, "model", Path("/tmp/x"), dt.datetime(2026, 9, 27, tzinfo=dt.UTC))

    assert payload["reader"] == "model"
    assert payload["latency"]["meanMs"] == 1050.0
    assert payload["fields"]["recall"] == 1.0


def test_the_report_names_whatever_read_the_documents() -> None:
    stamp = dt.datetime(2026, 9, 27, tzinfo=dt.UTC)
    result = LegResult(documents=1, clean_reads=1, latencies_ms=[1200])
    result.overall = Tally(expected=6, returned=6, matched=6)
    model = as_dict(result, "model", Path("/tmp/x"), stamp)
    model.update({"extractor": "llm-vlm", "model": "google/gemma-3-12b-it"})
    control = as_dict(result, "text", Path("/tmp/x"), stamp)
    control.update({"extractor": "template"})

    assert "reader: `llm-vlm`, model `google/gemma-3-12b-it`" in render_markdown(model)
    assert "Time per document" in render_markdown(model)
    assert "deterministic template parser: the control" in render_markdown(control)
