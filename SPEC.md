# SPEC — Use Case: Agentic Scrutiny & Document Verification

## 1. Use case definition
Manual scrutiny of Sewa Setu certificate/service applications (identity proof,
income/caste/residence certificates, affidavits) takes ~12–18 min/application,
is inconsistent across officers, and misses forged/expired/mismatched documents.
Use case: an agentic pipeline that pre-scrutinizes every application and hands
the officer a ranked, explained ScrutinyReport + recommendation.

## 2. Baseline vs target (synthetic-evidence claims for submission)
| Metric | Baseline (manual) | Target (POC, synthetic set) |
|---|---|---|
| Scrutiny time/application | 12–18 min | < 60 s |
| Fail-flag precision | n/a (unmeasured) | ≥ 0.90 |
| Fail-flag recall | n/a | ≥ 0.85 |
| Officer decision support | none | every check has evidence + plain-language explanation |

## 3. Scope
IN: extraction, 5 checks (§5), risk score, recommendation, officer queue +
decision UI, citizen status timeline, metrics summary, eval harness, synthetic data.
OUT: real government registries/PII, payments, mobile apps, production auth
(use role switcher), multilingual UI (note as roadmap).

## 4. Journeys
- J1 Citizen: browse services → apply (dynamic fields) → upload docs → see timeline.
- J2 System: on docs uploaded → run scrutiny → store ScrutinyReport → update timeline.
- J3 Officer: queue sorted by risk → open report (checks, evidence, explanations) → approve / reject / request_info with notes.
- J4 Citizen: sees decision or info-request on timeline.

## 5. Check catalog (every check MUST emit evidence + explanation)
- C1 identity_match: name/ID consistent across documents & application fields
- C2 doc_validity: expiry dates, issuing authority plausible
- C3 completeness: all required docTypes present & legible
- C4 cross_field_consistency: extracted fields vs declared applicant fields
- C5 fraud_signals: duplicate doc hash across applications, tamper patterns, numeric anomalies
riskScore 0–100 from weighted check outcomes + fraud signals.
recommendation ∈ {approve, request_info, manual_review, reject} (reject only on high-severity fails).

## 6. Synthetic data spec
Generator: `python -m generator --n 200 --anomaly-rate 0.25 --seed 42 --out data/synthetic/dataset-v1/`
Outputs: `applications.json`, `docs/*.txt|png` (templated), `ground_truth.json`
(per-application labels per check C1–C5 + planted anomaly types:
name_mismatch, expired_doc, missing_doc, field_mismatch, duplicate_hash, tampered_number).
NO real PII ever. Names/IDs from fictional pools.

## 7. Eval spec
`eval/runner.py` runs pipeline offline over dataset-v1, compares to ground truth:
per-check precision/recall/F1, risk-flag accuracy (flag = riskScore ≥ 60),
mean latency. Writes `eval/reports/<timestamp>/{report.json,report.md}`.
Gate: `eval/gate.py` exits non-zero if precision < 0.90 or recall < 0.85 on fail flags.

## 8. Acceptance criteria (demo-day definition of done)
1. J1–J4 runnable end-to-end on Track A real API + Track B UI.
2. Eval gate passes on dataset-v1; numbers quoted in submission come from report.md.
3. Every ScrutinyCheck rendered in UI shows evidence + explanation.
4. Officer decision updates citizen timeline.
5. 5-min demo script (docs/demo/script.md) rehearsed + fallback video recorded.