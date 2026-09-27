# Integration prompts (PAIR session, both humans, main branch). M4.

## I1 — Contract conformance
Task: boot Track A API + Track B with API_MODE=real; run B8 checklist against real API;
fix mismatches (pair may edit both tracks); add conformance test in services/pipeline/tests
asserting schema parity. DoD: checklist green on real API. Commit: `integration: conformance`

## I2 — Seed real demo data
Task: load dataset-v1 (first 20 apps incl. planted anomalies) into pipeline store via script
services/pipeline/scripts/seed_demo.py; verify UI queue/timeline show them. DoD: queue shows
≥2 high-risk apps with full reports. Commit: `integration: demo seed script`

## I3 — Eval + metrics wiring
Task: run eval.runner + gate; paste numbers into metrics/summary (evalPrecision/Recall);
verify dashboard shows them. DoD: gate exit 0; dashboard numbers == report.md. Commit: `integration: eval wiring`

## I4 — Demo rehearsal + recording
Task: run docs/demo/script.md twice; record fallback video; freeze repo (tag v1.0-poc).
Commit: `integration: demo freeze`