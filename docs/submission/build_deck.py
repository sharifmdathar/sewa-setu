#!/usr/bin/env python3
"""Build the hackathon deck: docs/submission/sewa-setu.pptx (and .pdf via LibreOffice).

    python docs/submission/build_deck.py

Every figure on a slide is one the repo can reproduce; the numbers are collected in FIGURES
below with the command that produced each, so a stale slide is a one-line fix rather than a
hunt. Regenerate after changing any of them.

    python -m eval.runner && python -m eval.gate       # the gate table
    python -m eval.image_leg --reader text             # the control row
    python -m pipeline.scripts.bench_scrutiny ...      # the officer-wait row
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

# Brand palette, taken from apps/web/tailwind.config.ts so the deck matches the product.
BRAND = RGBColor(0x4F, 0x46, 0xE5)
BRAND_LIGHT = RGBColor(0xEE, 0xF2, 0xFF)
INK = RGBColor(0x18, 0x18, 0x1B)
MUTED = RGBColor(0x71, 0x71, 0x7A)
RULE = RGBColor(0xD4, 0xD4, 0xD8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.75)
BODY_W = SLIDE_W - MARGIN * 2

FIGURES = {
    "gate": "python -m eval.runner && python -m eval.gate",
    # source lines exclude test lines, so the two columns never double-count each other
    "counts": "find <area> -name '*.py' | xargs wc -l  ·  pipeline, eval minus eval/test_*.py, "
              "data/synthetic, apps/web/src minus *.test.ts(x), and all test files",
    "tests": "pytest -q in services/pipeline and eval; npm test in apps/web",
}

TITLE = "Sewa Setu"
SUBTITLE = "Agentic Application Scrutiny & Document Verification"
FOOTER = "Problem Statement 1 · AI & Automation in Digital Public Service Delivery"
# `git remote get-url origin`. Update here and the deck follows on slides 1 and 11.
REPO_URL = "https://github.com/sharifmdathar/sewa-setu"


def add_slide(prs: Presentation) -> object:
    return prs.slides.add_slide(prs.slide_layouts[6])


def box(slide: object, left: Emu, top: Emu, width: Emu, height: Emu) -> object:
    shape = slide.shapes.add_textbox(left, top, width, height)
    shape.text_frame.word_wrap = True
    return shape


def write(
    frame: object,
    text: str,
    size: float,
    color: RGBColor = INK,
    bold: bool = False,
    first: bool = True,
    space_after: float = 6,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
    paragraph.space_after = Pt(space_after)
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Verdana"


def bullets(slide: object, items: list[tuple[str, bool]], top: Emu, marker: str = "•  ") -> None:
    frame = box(slide, MARGIN, top, BODY_W, SLIDE_H - top - Inches(0.9)).text_frame
    for index, (text, strong) in enumerate(items):
        # A blank item is a spacer, not a list entry: it gets no bullet glyph.
        write(
            frame,
            (marker if text.strip() and not strong else "") + text,
            19 if strong else 17,
            INK,
            bold=strong,
            first=index == 0,
            space_after=10 if strong else 14,
        )


def header(slide: object, title: str, kicker: str = "") -> Emu:
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(0.14))
    band.fill.solid()
    band.fill.fore_color.rgb = BRAND
    band.line.fill.background()
    title_top = Inches(0.68) if kicker else Inches(0.5)
    if kicker:
        write(
            box(slide, MARGIN, Inches(0.42), BODY_W, Inches(0.3)).text_frame,
            kicker,
            11,
            BRAND,
            True,
        )
    write(
        box(slide, MARGIN, title_top, BODY_W, Inches(0.75)).text_frame,
        title,
        30,
        INK,
        True,
    )
    return Inches(1.62) if kicker else Inches(1.42)


def footer(slide: object, number: int) -> None:
    frame = box(slide, MARGIN, SLIDE_H - Inches(0.62), BODY_W, Inches(0.35)).text_frame
    write(frame, f"{FOOTER}   ·   slide {number}", 10, MUTED)


def table(slide: object, rows: list[list[str]], top: Emu, widths: list[float]) -> None:
    shape = slide.shapes.add_table(
        len(rows), len(rows[0]), MARGIN, top, BODY_W, Inches(0.4 * len(rows))
    )
    grid = shape.table
    for column, fraction in enumerate(widths):
        grid.columns[column].width = Emu(int(BODY_W * fraction))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = grid.cell(r, c)
            cell.text = ""
            write(
                cell.text_frame,
                value,
                13,
                WHITE if r == 0 else INK,
                bold=(r == 0 or c == 0),
            )
            cell.fill.solid()
            cell.fill.fore_color.rgb = BRAND if r == 0 else (BRAND_LIGHT if r % 2 == 0 else WHITE)


def title_slide(prs: Presentation) -> None:
    slide = add_slide(prs)
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(2.5))
    band.fill.solid()
    band.fill.fore_color.rgb = BRAND
    band.line.fill.background()
    write(box(slide, MARGIN, Inches(0.85), BODY_W, Inches(0.9)).text_frame, TITLE, 46, WHITE, True)
    write(
        box(slide, MARGIN, Inches(1.75), BODY_W, Inches(0.5)).text_frame,
        SUBTITLE,
        20,
        BRAND_LIGHT,
    )
    bullets(
        slide,
        [
            ("An agentic pipeline that pre-scrutinizes every certificate application and hands "
             "the officer a ranked, explained report - while the decision stays with the "
             "officer.", False),
        ],
        Inches(3.2),
    )
    bullets(
        slide,
        [
            ("Team:  <fill in names, roles, emails>", False),
            (f"Repository:  {REPO_URL}", False),
            ("Live demo:  <deployment link, if applicable>", False),
            ("Demo credentials:  none - the prototype has no auth by design (SPEC §3)", False),
        ],
        Inches(4.45),
        marker="",
    )
    footer(slide, 1)


def content(prs: Presentation, number: int, title: str, items: list[tuple[str, bool]],
            kicker: str = "", table_rows: list[list[str]] | None = None,
            widths: list[float] | None = None) -> None:
    slide = add_slide(prs)
    top = header(slide, title, kicker)
    if table_rows:
        table(slide, table_rows, top, widths or [0.42, 0.2, 0.19, 0.19])
        top = top + Inches(0.42 * len(table_rows)) + Inches(0.3)
    if items:
        bullets(slide, items, top)
    footer(slide, number)


def build() -> Path:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    title_slide(prs)

    content(prs, 2, "The problem is scrutiny time, not application time", [
        ("A certificate application takes an officer 12-18 minutes to scrutinize by hand.", True),
        ("Two officers reading the same file can reach two different decisions.", False),
        ("Forged, expired and mismatched documents get through under volume pressure.", False),
        ("Every application is re-read from scratch: identity, dates, amounts, duplicates.", False),
        ("", False),
        ("The bottleneck is not the citizen submitting - it is the official reading.", True),
    ], kicker="PROBLEM")

    content(prs, 3, "What we built", [
        ("Extraction  ->  rule checks  ->  adjudication  ->  fraud scoring  ->  "
         "recommendation", True),
        ("A VLM or template parser reads each uploaded document into typed fields.", False),
        ("Five deterministic checks (C1-C5) run over the application and its documents.", False),
        ("Only the checks a rule cannot settle go to the LLM adjudicator, which re-words the "
         "verdict for an officer - it never overturns evidence.", False),
        ("A fraud scorer weights the outcomes into riskScore 0-100 and one recommendation.", False),
        ("", False),
        ("The agent recommends. The officer decides. That boundary is enforced in code and "
         "in tests.", True),
    ], kicker="SOLUTION")

    content(prs, 4, "Five checks, and no verdict without evidence", [
        ("C1 identity match  -  the same person across every document and the declared "
         "fields", False),
        ("C2 document validity  -  expiry, issue order, plausible issuing authority", False),
        ("C3 completeness  -  every required document type present and legible", False),
        ("C4 cross-field consistency  -  declared amounts against stated amounts", False),
        ("C5 fraud signals  -  duplicate file hashes across applicants, order-of-ten "
         "amounts", False),
        ("", False),
        ("Real C5 evidence from the demo store:", True),
        ("\"APP-0014-fee_receipt-5.txt has hash 8c7ce8117b88 which also appears in another "
         "application; APP-0014-self_income_declaration-4.txt states 4240000, exactly an order "
         "of ten away from the declared 424000.\"  ->  riskScore 100, recommend reject", False),
    ], kicker="HOW IT DECIDES")

    content(prs, 5, "Evaluation on 200 synthetic applications", [
        ("917 documents, 50 applications with planted anomalies, seed 42.", False),
        ("74 planted check failures: 74 caught, 0 false alarms, 0 missed. The gate asks whether "
         "each defect lit up exactly the check that owns it.", True),
        ("Risk-flag recall is 0.540 and we disclose it: single-anomaly applications score 40-50, "
         "under the spec-pinned threshold of 60. The queue ranks; it does not catch.", False),
    ], kicker="RESULTS", table_rows=[
        ["Metric", "Manual baseline", "This run", "Target"],
        ["Fail-flag precision", "unmeasured", "1.000", ">= 0.90"],
        ["Fail-flag recall", "unmeasured", "1.000", ">= 0.85"],
        ["Risk-flag recall", "unmeasured", "0.540", "disclosed, not gated"],
        ["Officer wait per application", "12-18 min", "3.0 ms p50", "< 60 s"],
    ], widths=[0.34, 0.22, 0.22, 0.22])

    content(prs, 6, "We put a real model in the loop, and reported what it did", [
        ("Same corpus, real vision model (llama-3.2-11b-vision), 20 rendered documents:", True),
        ("107 of 124 stated field values read correctly  -  recall 0.86, precision 0.98", False),
        ("5 of 20 documents read with no omission at all", False),
        ("Control, same documents through the deterministic parser: 124 of 124", False),
        ("", False),
        ("The failure is not uniform. Identity fields read at 1.00; expiryDate at 0.22.", True),
        ("We built a targeted second-pass fix for it, measured it recovering nothing, and "
         "reverted it rather than shipping a call that buys nothing.", False),
        ("What shipped instead costs zero calls: C2 warns when an expiry-carrying document "
         "yields no expiry, so a null becomes an officer-visible gap instead of a silent "
         "pass.", True),
    ], kicker="THE HONEST MEASUREMENT")

    content(prs, 7, "Latency: three different true answers", [
        ("Which number is honest depends on what was timed. We quote the officer's wait.", True),
    ], kicker="PERFORMANCE", table_rows=[
        ["What was timed", "Result"],
        ["Pipeline in-process, offline, no HTTP", "0.12 ms per application"],
        ["The officer's real wait over HTTP (rules-only)", "p50 3.0 ms  p95 3.2 ms  (100 runs)"],
        ["One document through a live VLM", "p50 2.8 s  p95 18.2 s  max 23.8 s"],
        ["One application through a live VLM", "13.3 s mean  15.5 s worst (2 apps)"],
    ], widths=[0.55, 0.45])

    content(prs, 8, "Why the numbers can be trusted", [
        ("310 automated tests passing, 2 skipped pending a paid model key.", True),
        ("Contract conformance is judged by a validator against openapi.yaml itself - in-process "
         "and over a real HTTP socket, not against a hand-written expectation.", False),
        ("Every eval figure regenerates from one command, and each report titles itself "
         "rules-only or live model leg so the two can never be quoted for each other.", False),
        ("A local OpenAI-compatible endpoint in the test suite asserts request counts over a "
         "socket - that is how we found a retry budget being multiplied, and fixed it.", False),
        ("", False),
        ("4,080 lines pipeline  ·  1,402 eval harness  ·  3,179 web  ·  1,052 generator  ·  "
         "5,794 test lines", True),
    ], kicker="RIGOUR")

    content(prs, 9, "Contract-first, two tracks, one week", [
        ("FastAPI pipeline + Next.js officer and citizen UI, joined by one frozen OpenAPI "
         "contract of 10 paths.", True),
        ("Two people worked in separate paths without editing each other's files.", False),
        ("Five change requests raised; three applied in a paired integration session.", False),
        ("Nothing personal is logged, and the corpus is fictional by construction - names, IDs "
         "and addresses come from generated pools.", False),
        ("", False),
        ("The contract held everywhere it spoke. Where it was silent - applicantFields is a bare "
         "object - both tracks guessed differently and both test suites passed. We found it, "
         "fixed it, and wrote CR-5 to close the hole.", True),
    ], kicker="HOW WE WORKED")

    content(prs, 10, "Pilot plan", [
        ("P0 - what this is", True),
        ("Two services, synthetic evidence, officer shadow mode. The pipeline runs beside the "
         "manual process; officers see the report and the queue but decide alone. Nothing "
         "touches a registry, so the worst case is a wrong recommendation an officer "
         "overrides.", False),
        ("P1 - next", True),
        ("Choose an OCR/VLM vendor on measured accuracy, not on a demo. Registry adapters behind "
         "the same extractor interface - which one runs is configuration, not a call site.", False),
        ("P2 - at scale", True),
        ("Multilingual, mobile, a real database. The store here is single-process by "
         "design.", False),
    ], kicker="ROADMAP")

    content(prs, 11, "What we are asking for", [
        ("An anonymised real document set, so the eval can run against scans rather than "
         "renders - our 0.86 read-back figure is a ceiling, not an expectation.", True),
        ("A vendor endpoint to measure accuracy and cost on that set.", False),
        ("Officer time to validate the recommendation format, because the ranking is the thing "
         "they will argue with - and a 0.54 risk recall gives them reason to.", False),
        ("", False),
        (f"Repository:  {REPO_URL}", True),
        ("Live demo:  <deployment link>          Video:  <demo video link>", True),
        ("Synthetic data only. No real PII, no registry access, no production auth.", False),
    ], kicker="THE ASK")

    out = Path(__file__).resolve().parent / "sewa-setu.pptx"
    prs.save(str(out))
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
