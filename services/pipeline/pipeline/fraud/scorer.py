"""riskScore and recommendation: weighted check outcomes + fraud signals (SPEC.md section 5)."""

from __future__ import annotations

from collections.abc import Sequence

from pipeline.fraud.features import extract_signals
from pipeline.fraud.models import FraudScore, Recommendation
from pipeline.rules.loader import load_rule_config
from pipeline.rules.models import RuleConfig, ScrutinyCheck, ScrutinyInput

# A passed or informational check adds nothing; a warn counts at its (lower) severity.
RISK_STATUSES = ("fail", "warn")


def check_points(checks: Sequence[ScrutinyCheck], config: RuleConfig) -> float:
    """What the adjudicated checks contribute, before the mechanical signals."""
    return sum(
        config.checks[check.check_id].weight * config.severity_multipliers[check.severity]
        for check in checks
        if check.status in RISK_STATUSES
    )


def recommend(
    risk_score: int, checks: Sequence[ScrutinyCheck], config: RuleConfig
) -> Recommendation:
    """SPEC.md section 5: the agent only recommends, and rejects only on high-severity fails."""
    thresholds = config.recommendation_thresholds
    high_severity_fail = any(
        check.status == "fail" and check.severity == "high" for check in checks
    )
    if risk_score >= thresholds["rejectMinScore"] and high_severity_fail:
        return "reject"
    if risk_score >= thresholds["manualReviewMinScore"]:
        return "manual_review"
    if risk_score >= thresholds["requestInfoMinScore"]:
        return "request_info"
    return "approve"


def score_fraud(
    data: ScrutinyInput,
    checks: Sequence[ScrutinyCheck],
    config: RuleConfig | None = None,
) -> FraudScore:
    """Score one application: the checks the officer reads, plus the features that back them."""
    rules = config if config is not None else load_rule_config()
    signals = extract_signals(data, rules)
    from_checks = check_points(checks, rules)
    from_signals = sum(signal.weight for signal in signals)
    risk_score = max(0, min(100, round(from_checks + from_signals)))
    return FraudScore(
        riskScore=risk_score,
        recommendation=recommend(risk_score, checks, rules),
        flagged=risk_score >= rules.flag_threshold,
        checkPoints=round(from_checks, 2),
        signalPoints=from_signals,
        signals=signals,
    )
