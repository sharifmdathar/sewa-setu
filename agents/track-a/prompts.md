# Track A prompts (Person 1). One block per agent session. Paste verbatim.

## A1 — Scaffold pipeline service
Load: ARCHITECTURE.md, AGENTS.md. Write scope: services/pipeline/**
Task: pyproject (name `pipeline`, deps fastapi, pydantic>=2, httpx, openai, PyYAML;
extra `dev`: pytest, ruff); package `pipeline/` with subpkgs api, ingestion,
extraction, rules, agent, fraud, store; FastAPI app exposing /healthz only;
JSON-file store module (store/jsonstore.py) with thread-safe read/write of
applications & reports under var/; .env.example (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL);
one smoke test. DoD: `pip install -e .[dev]`, `pytest -q` green, uvicorn boots, /healthz 200.
Commit: `track-a: pipeline scaffold + json store`

## A2 — Synthetic dataset generator
Load: SPEC.md §6. Write scope: data/synthetic/**, services/pipeline/tests/test_dataset.py
Task: package `generator` (runnable via python -m generator) producing dataset-v1:
applications.json (200 apps across 3 services), docs/ templated text docs per docType
with embedded fields, ground_truth.json labeling each check C1–C5 pass/fail + anomaly
type; flags --n --anomaly-rate --seed --out; deterministic. Include fictional name/ID pools.
DoD: generates dataset; integrity test passes (every doc referenced exists; labels cover C1–C5).
Commit: `track-a: synthetic dataset generator`

## A3 — Extraction module
Load: SPEC.md §5, contract schemas. Write scope: services/pipeline/extraction/**, tests
Task: `DocumentExtractor` protocol → ExtractedFields (pydantic: doc_type, name, id_number,
issue_date, expiry_date, issuing_authority, amounts, raw_text); TemplateExtractor parses
templated docs; LLMExtractor (VLM via openai SDK, prompt template in prompts.py, JSON-mode,
timeout/retries, modelMeta). DoD: TemplateExtractor field accuracy = 100% on dataset-v1 docs
(unit test); LLMExtractor tests skip cleanly without LLM_API_KEY.
Commit: `track-a: extraction (template + llm)`

## A4 — Rules engine C1–C5
Load: SPEC.md §5. Write scope: services/pipeline/rules/**, tests
Task: rules.yaml (weights, thresholds per check) + pure functions returning ScrutinyCheck
(status/severity/evidence/explanation) for C1–C5 given ExtractedFields + applicantFields +
doc metadata (sha256, uploadedAt). Evidence strings must quote the offending values.
DoD: ≥2 tests per check (pass + fail edge: expired, mismatch, missing, dup hash, tampered number).
Commit: `track-a: rules engine C1-C5`

## A5 — Adjudication agent
Load: SPEC.md §5. Write scope: services/pipeline/agent/**, tests
Task: orchestrator: extract all docs → run rules → for warn/ambiguous checks call LLM
adjudicator (structured output: final status + explanation rewrite in plain language);
assemble ScrutinyReport per contract (extractedFields, checks, modelMeta with latency).
No LLM → deterministic fallback explanation. DoD: integration test builds a contract-valid
report for 1 clean + 1 anomalous app (validate against openapi schemas in-test).
Commit: `track-a: adjudication agent + report assembly`

## A6 — Fraud scorer
Load: SPEC.md §5 (C5). Write scope: services/pipeline/fraud/**, tests
Task: features: duplicate sha256 across dataset, tampered-number patterns, expiry anomalies,
cross-doc identity divergence → riskScore 0–100 (weights from rules.yaml) + top-signals list;
recommendation mapping per SPEC §5. DoD: monotonicity tests (more planted anomalies ⇒ higher
score); clean apps score < 30 on dataset-v1.
Commit: `track-a: fraud scorer + risk scoring`

## A7 — Contract API
Load: shared/contracts/openapi.yaml (implement EXACTLY). Write scope: services/pipeline/api/**, tests
Task: FastAPI routes for all contract paths; scrutiny/run wires ingestion→A3→A4→A5→A6,
persists report + timeline events; officer/decisions updates status/timeline;
metrics/summary computed from store (+ optional evalPrecision/Recall read from latest
eval report if present). DoD: pytest contract tests hitting every path (incl. 404s);
response models match openapi schemas field-for-field.
Commit: `track-a: contract api implementation`

## A8 — Eval harness + gate
Load: SPEC.md §7. Write scope: eval/**
Task: runner.py: offline pass over dataset-v1 through pipeline (no HTTP), per-check P/R/F1,
risk-flag accuracy, mean latency; writes eval/reports/<ts>/{report.json,report.md} (human-
readable tables); gate.py enforcing SPEC thresholds (exit 1 on breach). DoD: `python -m eval.runner`
+ `python -m eval.gate` run clean; report.md quotable in submission.
Commit: `track-a: eval harness + threshold gate`

## A9 — Hardening + track docs
Write scope: services/pipeline/**, eval/**, docs/track-a/**
Task: error paths (bad base64, unknown service, missing docs → contract-consistent errors),
structured logging, README runbook in services/pipeline/README.md, docs/track-a/pipeline-design.md
(components, decisions, eval summary pasted from latest report). DoD: full gate suite green;
runbook followed cold by a fresh shell without questions.
Commit: `track-a: hardening + design docs`