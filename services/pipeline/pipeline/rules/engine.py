"""Rule engine entry point: run C1-C5 over one application."""

from __future__ import annotations

from pipeline.rules.checks import (
    CHECK_IDS,
    check_completeness,
    check_cross_field_consistency,
    check_document_validity,
    check_fraud_signals,
    check_identity_match,
)
from pipeline.rules.loader import load_rule_config
from pipeline.rules.models import RuleConfig, ScrutinyCheck, ScrutinyInput

RUNNERS = (
    check_identity_match,
    check_document_validity,
    check_completeness,
    check_cross_field_consistency,
    check_fraud_signals,
)


def run_rules(data: ScrutinyInput, config: RuleConfig | None = None) -> list[ScrutinyCheck]:
    """Return exactly one ScrutinyCheck per catalogued check, in C1..C5 order."""
    rules = config if config is not None else load_rule_config()
    checks = [runner(data, rules) for runner in RUNNERS]
    if [check.check_id for check in checks] != list(CHECK_IDS):
        raise AssertionError("rule engine returned an unexpected check set")
    return checks
