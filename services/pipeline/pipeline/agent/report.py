"""Scrutiny orchestrator: extract -> rule -> adjudicate -> score -> contract report."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import time
from collections.abc import Sequence

from pipeline.agent.adjudicator import (
    AMBIGUOUS_STATUSES,
    AdjudicationError,
    Adjudicator,
    DeterministicAdjudicator,
    LLMAdjudicator,
)
from pipeline.agent.models import Adjudication, ModelMeta, ScrutinyReport
from pipeline.config import get_llm_settings
from pipeline.extraction import (
    DocumentContent,
    DocumentExtractor,
    ExtractedFields,
    ExtractionError,
    LLMExtractor,
    TemplateExtractor,
)
from pipeline.fraud.scorer import score_fraud
from pipeline.rules import (
    DocEvidence,
    RuleConfig,
    ScrutinyCheck,
    ScrutinyInput,
    load_rule_config,
    run_rules,
)
from pipeline.rules.models import CheckConfig, CheckSeverity, CheckStatus


def sha256_of_content(document: DocumentContent) -> str:
    """Content hash the fraud checks compare across applications (A7 ingestion reuses it)."""
    if document.content_base64 is not None:
        raw = base64.b64decode(document.content_base64, validate=True)
        return hashlib.sha256(raw).hexdigest()
    return hashlib.sha256((document.text or "").encode("utf-8")).hexdigest()


def default_extractor() -> DocumentExtractor:
    """Template parsing is exact on the synthetic corpus, so the model stays opt-in."""
    settings = get_llm_settings()
    return LLMExtractor(settings) if settings.enabled else TemplateExtractor()


def default_adjudicator() -> Adjudicator:
    """Without an endpoint the deterministic adjudicator only re-words the rule verdict."""
    settings = get_llm_settings()
    return LLMAdjudicator(settings) if settings.enabled else DeterministicAdjudicator()


def _evidence_of(document: DocumentContent, extractor: DocumentExtractor) -> DocEvidence:
    """Attach one document's metadata to what was read from it.

    An unreadable file keeps empty fields rather than failing the run: that is C3's finding
    to report, and crashing here would leave the officer with no report at all.
    """
    try:
        fields = extractor.extract(document)
    except ExtractionError:
        fields = ExtractedFields(doc_type=document.doc_type)
    return DocEvidence(
        documentId=document.document_id,
        docType=document.doc_type,
        fileName=document.file_name,
        sha256=sha256_of_content(document),
        fields=fields,
    )


def _severity_for(status: CheckStatus, rule: CheckConfig) -> CheckSeverity:
    if status == "fail":
        return rule.fail_severity
    if status == "warn":
        return rule.warn_severity
    return "low"


def _settle(check: ScrutinyCheck, verdict: Adjudication, rule: CheckConfig) -> ScrutinyCheck:
    """Apply a verdict to one check: its evidence is the rules' work and stays untouched."""
    unchanged = verdict.status == check.status
    return check.model_copy(
        update={
            "status": verdict.status,
            "severity": check.severity if unchanged else _severity_for(verdict.status, rule),
            "explanation": verdict.explanation.strip() or check.explanation,
        }
    )


def _adjudicate(
    checks: Sequence[ScrutinyCheck],
    data: ScrutinyInput,
    adjudicator: Adjudicator,
    config: RuleConfig,
) -> list[ScrutinyCheck]:
    """Ask the adjudicator only about verdicts the rules could not settle."""
    settled: list[ScrutinyCheck] = []
    for check in checks:
        if check.status not in AMBIGUOUS_STATUSES:
            settled.append(check)
            continue
        try:
            verdict = adjudicator.adjudicate(check, data)
        except AdjudicationError:
            settled.append(check)
            continue
        settled.append(_settle(check, verdict, config.checks[check.check_id]))
    return settled


def _component_model(component: DocumentExtractor | Adjudicator) -> str:
    meta = component.last_meta
    return meta.model if meta is not None else "code"


def _model_meta(
    extractor: DocumentExtractor,
    adjudicator: Adjudicator,
    latency_ms: int,
    config: RuleConfig,
) -> ModelMeta:
    return ModelMeta(
        extractor=extractor.name,
        adjudicator=adjudicator.name,
        latencyMs=latency_ms,
        versions={
            "rules": str(config.version),
            "extractor": _component_model(extractor),
            "adjudicator": _component_model(adjudicator),
        },
    )


def run_scrutiny(
    application: ScrutinyInput,
    documents: Sequence[DocumentContent],
    *,
    extractor: DocumentExtractor | None = None,
    adjudicator: Adjudicator | None = None,
    config: RuleConfig | None = None,
    generated_at: dt.datetime | None = None,
) -> ScrutinyReport:
    """Scrutinize one application's documents and return the contract report."""
    started = time.perf_counter()
    reader = extractor if extractor is not None else default_extractor()
    judge = adjudicator if adjudicator is not None else default_adjudicator()
    rules = config if config is not None else load_rule_config()

    evidence = [_evidence_of(document, reader) for document in documents]
    data = application.model_copy(update={"documents": evidence})
    checks = _adjudicate(run_rules(data, rules), data, judge, rules)
    risk = score_fraud(data, checks, rules)

    return ScrutinyReport(
        applicationId=data.application_id,
        generatedAt=generated_at or dt.datetime.now(dt.UTC),
        extractedFields={item.document_id: item.fields.as_json() for item in evidence},
        checks=checks,
        riskScore=risk.risk_score,
        recommendation=risk.recommendation,
        modelMeta=_model_meta(
            reader, judge, int(round((time.perf_counter() - started) * 1000)), rules
        ),
    )
