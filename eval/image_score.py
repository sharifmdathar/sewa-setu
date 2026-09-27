"""Scoring for the image leg: compare one read against the fields the generator wrote.

The yardstick only means something if it agrees with the corpus, so `--reader text` exists: the
deterministic template parser over the same documents must score 1.00, and if it ever does not,
the manifest and the reader have drifted apart and no model number from this harness is
interpretable.

Field-level precision is reported next to recall on purpose. A model that supplies an expiry date
to a document that never had one has hallucinated, and recall alone cannot see it: the blank answer
and the invented one score identically.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.extraction import (
    DocumentContent,
    DocumentExtractor,
    ExtractedFields,
    ExtractionError,
)

MANIFEST_FILE = "image_manifest.json"
IMAGE_DIR = "docs_img"
DOCS_DIR = "docs"

# manifest key -> ExtractedFields attribute. The manifest speaks the extractor's own vocabulary,
# so a field that drifts between the two surfaces as an unknown key rather than as silence.
FIELDS: dict[str, str] = {
    "docType": "doc_type",
    "name": "name",
    "idNumber": "id_number",
    "issueDate": "issue_date",
    "expiryDate": "expiry_date",
    "issuingAuthority": "issuing_authority",
    "amounts": "amounts",
}
EMPTY_VALUES = ("", "[]")


@dataclass
class Entry:
    """One rendered document and the field values a correct read must return."""

    application_id: str
    document_id: str
    doc_type: str
    text_file_name: str
    image_file_name: str
    expected: dict[str, Any]


@dataclass
class Tally:
    """expected / returned / matched counts, which give recall and precision together."""

    expected: int = 0
    returned: int = 0
    matched: int = 0

    def add(self, *, expected: bool, returned: bool, matched: bool) -> None:
        self.expected += int(expected)
        self.returned += int(returned)
        self.matched += int(matched)

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "returned": self.returned,
            "matched": self.matched,
            "recall": round(self.matched / self.expected, 4) if self.expected else 0.0,
            "precision": round(self.matched / self.returned, 4) if self.returned else 0.0,
        }


@dataclass
class LegResult:
    documents: int = 0
    unreadable: int = 0
    clean_reads: int = 0
    overall: Tally = field(default_factory=Tally)
    by_field: dict[str, Tally] = field(default_factory=dict)
    by_type: dict[str, Tally] = field(default_factory=dict)
    latencies_ms: list[int] = field(default_factory=list)
    problems: list[dict[str, Any]] = field(default_factory=list)

    def tallies_for(self, name: str, doc_type: str) -> tuple[Tally, Tally, Tally]:
        """One add site for all three views, so no breakdown can silently miss a read."""
        return (
            self.overall,
            self.by_field.setdefault(name, Tally()),
            self.by_type.setdefault(doc_type, Tally()),
        )


def load_entries(root: Path | str) -> list[Entry]:
    """Read `<root>/image_manifest.json` into one entry per rendered document."""
    path = Path(root) / MANIFEST_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Entry(
            application_id=str(row["applicationId"]),
            document_id=str(row["documentId"]),
            doc_type=str(row["docType"]),
            text_file_name=str(row["textFileName"]),
            image_file_name=str(row["imageFileName"]),
            expected=dict(row["expectedFields"]),
        )
        for row in payload["documents"]
    ]


def normalise(name: str, value: Any) -> str:
    """Compare on content, not formatting: dates, ID spacing and case all drift in model output."""
    if value is None:
        return ""
    if name in ("issueDate", "expiryDate"):
        if isinstance(value, dt.date):
            return value.isoformat()
        return str(value).strip()[:10]
    if name == "idNumber":
        return "".join(char for char in str(value) if char.isdigit())
    if name == "amounts":
        values = value if isinstance(value, list) else [value]
        return ",".join(sorted(str(int(float(str(item).replace(",", "")))) for item in values))
    return " ".join(str(value).split()).casefold()


def document_for(entry: Entry, root: Path, reader: str) -> DocumentContent:
    """The same document, as pixels for the model and as a text layer for the control."""
    if reader == "model":
        raw = (root / IMAGE_DIR / entry.image_file_name).read_bytes()
        return DocumentContent(
            documentId=entry.document_id,
            docType=entry.doc_type,
            fileName=entry.image_file_name,
            mimeType="image/png",
            contentBase64=base64.b64encode(raw).decode("ascii"),
        )
    text = (root / DOCS_DIR / entry.text_file_name).read_text(encoding="utf-8")
    return DocumentContent(
        documentId=entry.document_id,
        docType=entry.doc_type,
        fileName=entry.text_file_name,
        text=text,
    )


def score_entry(entry: Entry, fields: ExtractedFields, result: LegResult) -> None:
    """Fold one read against one manifest row into the overall, field and type tallies."""
    complete = True
    for name, attribute in FIELDS.items():
        want = normalise(name, entry.expected.get(name))
        got = normalise(name, getattr(fields, attribute, None))
        stated = want not in EMPTY_VALUES
        answered = got not in EMPTY_VALUES
        matched = stated and answered and want == got
        if (stated or answered) and not matched:
            complete = False
        for tally in result.tallies_for(name, entry.doc_type):
            tally.add(expected=stated, returned=answered, matched=matched)
    if complete:
        result.clean_reads += 1


def score_documents(
    entries: list[Entry], extractor: DocumentExtractor, root: Path, reader: str, result: LegResult
) -> LegResult:
    """Read every document once and fold the comparison into `result`."""
    for entry in entries:
        result.documents += 1
        try:
            fields = extractor.extract(document_for(entry, root, reader))
        except (ExtractionError, OSError) as exc:
            # OSError too: a manifest row whose PNG was deleted since must land in the report as
            # one unreadable document, not abort the other nineteen that were already paid for.
            record_unreadable(result, entry, str(exc))
            continue
        score_entry(entry, fields, result)
        meta = extractor.last_meta
        if meta is not None:
            result.latencies_ms.append(meta.latency_ms)
    return result


def record_unreadable(result: LegResult, entry: Entry, reason: str) -> None:
    """Charge a failed read for exactly the values it lost, in every breakdown, and say so."""
    result.unreadable += 1
    lost = [
        name
        for name in FIELDS
        if normalise(name, entry.expected.get(name)) not in EMPTY_VALUES
    ]
    for name in lost:
        for tally in result.tallies_for(name, entry.doc_type):
            tally.add(expected=True, returned=False, matched=False)
    result.problems.append(
        {"documentId": entry.document_id, "reason": reason, "fieldsLost": len(lost)}
    )


def percentile(values: list[int], fraction: float) -> float:
    """A value that was actually observed, which matters when there are twenty of them."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return float(ordered[index])
